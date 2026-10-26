/*
 * The follower skills, the part every follower shares: the sheet's numbers and the tiers (dc_follower_skill,
 * dc_follower_skill_value), the picks a character keeps for each follower (dc_character_follower_skill) and the commands that
 * set them, the cooldowns, the stock holds the skills put on enemies, the look the companion's AI asks for and the fatal-blow
 * seam. Each follower's skills are in its own file (dc_follower_templar.cpp).
 */

#include "dc_follower_skills.h"
#include "dc_follower_internal.h"
#include "../../campaign/dc_campaign.h"
#include "../../combat/dc_combat.h"
#include "../../stats/dc_stats.h"
#include "../../common/dc_world.h"
#include "Chat.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "GameTime.h"
#include "Log.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "SpellAuraEffects.h"
#include "SpellAuras.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <array>
#include <cctype>
#include <cmath>
#include <map>
#include <mutex>
#include <string>
#include <tuple>
#include <unordered_map>
#include <vector>

namespace DC::Classes::Follower
{
    namespace
    {
        constexpr unsigned FollowerCount = 3;
        constexpr unsigned TierCount = 4;
        char const* const Keys[FollowerCount] = {"templar", "scoundrel", "enchantress"};

        // Stock auras the skills put on: "Ice Blast" (one MOD_STUN effect), "Dazed" (one MOD_DECREASE_SPEED effect, its amount set
        // to the slow) and "Challenging Shout" (the taunt).
        constexpr std::uint32_t StunHold = 15878;
        constexpr std::uint32_t SlowHold = 50259;
        constexpr std::uint32_t TauntHold = 1161;
        // Stock "Super Invis": one MOD_INVISIBILITY effect, infinite, broken by nothing; the skill sets its time.
        constexpr std::uint32_t InvisibleHold = 8149;
        // Stock "Slow" (10371): one MOD_MELEE_HASTE effect on an enemy; its amount is set to the attack speed it takes off.
        constexpr std::uint32_t WearyHold = 10371;

        struct SkillRow
        {
            unsigned follower = 0;
            unsigned tier = 0;
            unsigned level = 0;
            std::string id;
            double cooldown = 0; // seconds; 0 for a passive
        };

        struct Number
        {
            double low = 0;
            double high = 0;
        };

        struct Data
        {
            bool ready = false;
            std::vector<SkillRow> skills;
            std::map<std::tuple<unsigned, std::string, std::string>, Number> numbers; // follower, skill ("" for a rule), token
        } data;

        struct Held
        {
            Stat stat = Stat::Strength;
            Bucket bucket = Bucket::Flat;
            Element element = Element::Physical;
            double value = 0;
        };

        struct State
        {
            std::unordered_map<std::uint64_t, Held> standing; // what skills hold on the player's sheet, by their key
            std::array<std::array<std::string, TierCount>, FollowerCount> picks;
            std::unordered_map<std::string, std::uint64_t> readyAt; // follower and skill -> game time
            std::uint64_t shieldUntil = 0;
            std::uint32_t sinceLook = 0;
            std::uint32_t sinceUpkeep = 0;
        };

        std::mutex mutex;
        std::unordered_map<std::uint64_t, State> states; // by the player's guid

        std::uint64_t Key(Player const* player)
        {
            return player->GetGUID().GetRawValue();
        }

        SkillRow const* RowOf(unsigned follower, std::string_view skill)
        {
            for (SkillRow const& row : data.skills)
                if (row.follower == follower && row.id == skill)
                    return &row;
            return nullptr;
        }

        std::string CooldownKey(unsigned follower, std::string_view skill)
        {
            return std::to_string(follower) + ":" + std::string(skill);
        }

        void LoadData()
        {
            data = Data{};
            QueryResult skills = WorldDatabase.Query(
                "SELECT follower_id, tier, d3_level, skill_id, cooldown_seconds FROM dc_follower_skill");
            QueryResult numbers = WorldDatabase.Query(
                "SELECT follower_id, skill_id, token, value, value_max FROM dc_follower_skill_value");
            if (!skills || !numbers)
            {
                LOG_WARN("server", "[DC followers] the follower skill tables are missing or empty: follower skills are off");
                return;
            }
            do
            {
                Field* f = skills->Fetch();
                SkillRow row;
                row.follower = f[0].Get<std::uint8_t>();
                row.tier = f[1].Get<std::uint8_t>();
                row.level = f[2].Get<std::uint8_t>();
                row.id = f[3].Get<std::string>();
                row.cooldown = f[4].IsNull() ? 0.0 : f[4].Get<double>();
                if (row.follower < 1 || row.follower > FollowerCount || row.tier < 1 || row.tier > TierCount)
                {
                    LOG_ERROR("server", "[DC followers] dc_follower_skill has a bad row: follower skills are off");
                    return;
                }
                data.skills.push_back(row);
            } while (skills->NextRow());
            do
            {
                Field* f = numbers->Fetch();
                Number number;
                number.low = f[3].Get<double>();
                number.high = f[4].IsNull() ? number.low : f[4].Get<double>();
                data.numbers[{unsigned(f[0].Get<std::uint8_t>()), f[1].Get<std::string>(), f[2].Get<std::string>()}] = number;
            } while (numbers->NextRow());
            data.ready = data.numbers.count({0, "", "main_stat_cap"}) != 0;
            if (!data.ready)
                LOG_ERROR("server", "[DC followers] dc_follower_skill_value has no main_stat_cap: follower skills are off");
        }

        // The follower a command names: 1 to 3, or its name.
        unsigned FollowerOf(std::string text)
        {
            for (char& c : text)
                c = char(std::tolower(static_cast<unsigned char>(c)));
            for (unsigned i = 0; i < FollowerCount; ++i)
                if (text == Keys[i] || text == std::to_string(i + 1))
                    return i + 1;
            return 0;
        }

        void LoadPicks(Player* player)
        {
            State state;
            QueryResult result = CharacterDatabase.Query(
                "SELECT follower, tier, skill_id FROM dc_character_follower_skill WHERE guid={}", player->GetGUID().GetCounter());
            if (result)
            {
                do
                {
                    Field* f = result->Fetch();
                    unsigned const follower = f[0].Get<std::uint8_t>(), tier = f[1].Get<std::uint8_t>();
                    if (follower >= 1 && follower <= FollowerCount && tier >= 1 && tier <= TierCount)
                        state.picks[follower - 1][tier - 1] = f[2].Get<std::string>();
                } while (result->NextRow());
            }
            std::lock_guard<std::mutex> guard(mutex);
            states[Key(player)] = std::move(state);
        }

        bool Refuse(ChatHandler* handler, char const* text)
        {
            handler->SendErrorMessage(text);
            return false;
        }

        // The pick's checks, in the order the Follower window shows them. The refusal's words, or "" when the pick was made
        // and saved. `choice` is "1" or "2", or a skill's id.
        std::string TryPick(Player* player, std::string const& who, unsigned tier, std::string const& choice)
        {
            unsigned const follower = FollowerOf(who);
            if (!data.ready)
                return "Followers are not available right now.";
            if (!follower)
                return "Name a follower: 1, 2, 3 or its name.";
            if (tier < 1 || tier > TierCount)
                return "A tier is 1 to 4.";
            if (!player->IsAlive() || player->IsInCombat() || !World::IsInHub(player))
                return "Skills are picked in the hub, out of combat.";
            std::vector<SkillRow const*> pair;
            for (SkillRow const& row : data.skills)
                if (row.follower == follower && row.tier == tier)
                    pair.push_back(&row);
            if (pair.size() != 2)
                return "That follower has no skills in that tier.";
            int const which = ChoiceOf(choice, pair[0]->id, pair[1]->id);
            if (which < 0)
                return "Choose 1 or 2, or the skill's id.";
            if (!TierOpen(player->GetLevel(), pair[0]->level))
                return "That tier opens at level " + std::to_string(pair[0]->level) + ".";
            std::string const& skill = pair[which]->id;
            {
                std::lock_guard<std::mutex> guard(mutex);
                states[Key(player)].picks[follower - 1][tier - 1] = skill;
            }
            CharacterDatabase.Execute("REPLACE INTO dc_character_follower_skill (guid, follower, tier, skill_id) VALUES ({}, {}, {}, '{}')",
                                      player->GetGUID().GetCounter(), follower, tier, skill);
            return "";
        }

        bool Pick(ChatHandler* handler, Player* player, std::string const& who, unsigned tier, std::string const& choice)
        {
            std::string const refusal = TryPick(player, who, tier, choice);
            if (!refusal.empty())
            {
                handler->SendErrorMessage("{}", refusal);
                return false;
            }
            handler->SendSysMessage("Done.");
            return true;
        }

        bool List(ChatHandler* handler, Player* player, std::string const& who)
        {
            unsigned const follower = FollowerOf(who);
            if (!data.ready)
                return Refuse(handler, "Followers are not available right now.");
            if (!follower)
                return Refuse(handler, "Name a follower: 1, 2, 3 or its name.");
            std::array<std::string, TierCount> picks;
            {
                std::lock_guard<std::mutex> guard(mutex);
                picks = states[Key(player)].picks[follower - 1];
            }
            handler->PSendSysMessage("{}, level {}:", Keys[follower - 1], player->GetLevel());
            for (unsigned tier = 1; tier <= TierCount; ++tier)
            {
                std::string line;
                unsigned level = 0;
                for (SkillRow const& row : data.skills)
                    if (row.follower == follower && row.tier == tier)
                    {
                        level = row.level;
                        line += (line.empty() ? "" : "   ") + std::string(row.id == picks[tier - 1] ? "[" + row.id + "]" : row.id);
                    }
                handler->PSendSysMessage("  tier {} (level {}, {}): {}", tier, level, TierOpen(player->GetLevel(), level) ? "open" : "closed", line);
            }
            return true;
        }

        class Commands final : public CommandScript
        {
        public:
            Commands()
                : CommandScript("dc_follower_skills_commands")
            {
            }

            // What the Follower window's bridge runs through Player:RunCommand, as the gear commands.
            Acore::ChatCommands::ChatCommandTable GetCommands() const override
            {
                using namespace Acore::ChatCommands;
                static ChatCommandTable follower = {{"skills", HandleSkills, SEC_PLAYER, Console::No},
                                                    {"skill", HandleSkill, SEC_PLAYER, Console::No}};
                static ChatCommandTable dc = {{"follower", follower}};
                static ChatCommandTable root = {{"dc", dc}};
                return root;
            }

            static bool HandleSkills(ChatHandler* handler, std::string who)
            {
                return List(handler, handler->GetSession()->GetPlayer(), who);
            }

            static bool HandleSkill(ChatHandler* handler, std::string who, std::uint32_t tier, std::string choice)
            {
                return Pick(handler, handler->GetSession()->GetPlayer(), who, tier, choice);
            }
        };

        // The player under a follower's creature: its hirer when the creature is that player's companion now.
        Player* OwnerOfCompanion(Unit* unit)
        {
            if (!unit || !unit->IsCreature() || !unit->GetOwnerGUID())
                return nullptr;
            Player* owner = ObjectAccessor::FindConnectedPlayer(unit->GetOwnerGUID());
            return owner && Campaign::Followers::Companion(owner) == unit ? owner : nullptr;
        }

        class Hits final : public UnitScript
        {
        public:
            Hits()
                : UnitScript("dc_follower_skills_hits", true, {UNITHOOK_ON_DAMAGE, UNITHOOK_MODIFY_MELEE_DAMAGE})
            {
            }

            // A melee blow on the player or on the Enchantress (Powered Shield slows who struck it).
            void ModifyMeleeDamage(Unit* target, Unit* attacker, uint32& damage) override
            {
                if (!data.ready || !damage || !target || !attacker)
                    return;
                Player* owner = target->ToPlayer() ? target->ToPlayer() : OwnerOfCompanion(target);
                Ctx c;
                if (owner && owner->IsValidAttackTarget(attacker) && Context(owner, c) && c.follower == EnchantressId)
                    Enchantress::Struck(c, attacker);
            }

            // A blow on the player (Intervene), and a blow the Templar gives or takes (Intimidate).
            void OnDamage(Unit* attacker, Unit* victim, uint32& damage) override
            {
                if (!data.ready || !damage || !attacker || !victim)
                    return;
                if (Player* hurt = victim->ToPlayer())
                {
                    Ctx c;
                    if (Context(hurt, c) && c.follower == TemplarId)
                        Templar::Hurt(c, attacker);
                    return;
                }
                Player* owner = OwnerOfCompanion(attacker);
                Unit* enemy = victim;
                if (!owner)
                {
                    owner = OwnerOfCompanion(victim);
                    enemy = attacker;
                }
                Ctx c;
                if (owner && owner->IsValidAttackTarget(enemy) && Context(owner, c) && c.follower == TemplarId)
                    Templar::Fought(c, enemy);
            }
        };

        class Players final : public PlayerScript
        {
        public:
            Players()
                : PlayerScript("dc_follower_skills_players", {PLAYERHOOK_ON_LOGIN, PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_PLAYER_JUST_DIED,
                                                              PLAYERHOOK_ON_DELETE_FROM_DB, PLAYERHOOK_ON_UPDATE})
            {
            }

            void OnPlayerLogin(Player* player) override
            {
                LoadPicks(player);
            }

            void OnPlayerLogout(Player* player) override
            {
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    states.erase(Key(player));
                }
                Templar::Away(player);
            }

            // Once a second: a follower that is gone (dismissed, down, a party) leaves nothing standing on its player.
            void OnPlayerUpdate(Player* player, uint32 diff) override
            {
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    auto state = states.find(Key(player));
                    if (state == states.end())
                        return;
                    state->second.sinceUpkeep += diff;
                    if (state->second.sinceUpkeep < 1000)
                        return;
                    state->second.sinceUpkeep = 0;
                }
                Ctx c;
                if (!Context(player, c))
                {
                    Scoundrel::Away(player);
                    Enchantress::Away(player);
                    Templar::Away(player);
                    ClearStanding(player);
                }
            }

            // The follower goes down with the player and its cooldowns are reset.
            void OnPlayerJustDied(Player* player) override
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto found = states.find(Key(player));
                if (found != states.end())
                {
                    found->second.readyAt.clear();
                    found->second.shieldUntil = 0;
                }
            }

            void OnPlayerDeleteFromDB(CharacterDatabaseTransaction trans, uint32 guid) override
            {
                trans->Append("DELETE FROM dc_character_follower_skill WHERE guid=" + std::to_string(guid));
            }
        };

        class Startup final : public WorldScript
        {
        public:
            Startup()
                : WorldScript("dc_follower_skills_startup")
            {
            }

            void OnStartup() override
            {
                LoadData();
            }
        };

        // A stock control aura of `seconds` on `target`, a second one restarting it.
        bool Hold(Unit* caster, Unit* target, std::uint32_t aura, double seconds, int amount = 0)
        {
            if (!caster || !target || seconds <= 0 || !target->IsAlive())
                return false;
            target->RemoveAurasDueToSpell(aura, caster->GetGUID());
            Aura* hold = caster->AddAura(aura, target);
            if (!hold)
                return false;
            if (amount)
                if (AuraEffect* effect = hold->GetEffect(EFFECT_0))
                    effect->ChangeAmount(amount);
            hold->SetMaxDuration(int32(seconds * 1000));
            hold->SetDuration(int32(seconds * 1000));
            return true;
        }
    } // namespace

    std::uint64_t Now()
    {
        return std::uint64_t(GameTime::GetGameTimeMS().count());
    }

    bool Context(Player* player, Ctx& out)
    {
        if (!data.ready || !player)
            return false;
        unsigned const follower = unsigned(Campaign::Followers::Hired(player));
        Creature* companion = follower ? Campaign::Followers::Companion(player) : nullptr;
        Items::FollowerGear::SkillStats stats;
        if (!companion || !companion->IsAlive() || !Items::FollowerGear::SkillStatsOf(player, follower, stats))
            return false;
        out.player = player;
        out.companion = companion;
        out.follower = follower;
        out.stats = stats;
        out.share = MainStatShare(stats.mainStat, Rule("main_stat_cap"));
        out.level = player->GetLevel();
        out.halved = Items::FollowerGear::HasPower(player, follower, "cooldown_half");
        out.allSkills = Items::FollowerGear::HasPower(player, follower, "all_skills");
        return true;
    }

    bool On(Ctx const& c, std::string_view skill)
    {
        SkillRow const* row = RowOf(c.follower, skill);
        if (!row)
            return false;
        bool picked;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = states.find(Key(c.player));
            picked = found != states.end() && found->second.picks[c.follower - 1][row->tier - 1] == skill;
        }
        return Active(picked, c.allSkills, TierOpen(c.level, row->level));
    }

    double Rule(std::string_view token)
    {
        auto found = data.numbers.find({0, "", std::string(token)});
        return found == data.numbers.end() ? 0.0 : found->second.low;
    }

    double Raw(unsigned follower, std::string_view skill, std::string_view token)
    {
        auto found = data.numbers.find({follower, std::string(skill), std::string(token)});
        return found == data.numbers.end() ? 0.0 : found->second.low;
    }

    double Num(Ctx const& c, std::string_view skill, std::string_view token)
    {
        auto found = data.numbers.find({c.follower, std::string(skill), std::string(token)});
        return found == data.numbers.end() ? 0.0 : Scaled(found->second.low, found->second.high, c.share);
    }

    bool Ready(Ctx const& c, std::string_view skill)
    {
        std::lock_guard<std::mutex> guard(mutex);
        auto state = states.find(Key(c.player));
        if (state == states.end())
            return false;
        auto at = state->second.readyAt.find(CooldownKey(c.follower, skill));
        return at == state->second.readyAt.end() || DC::Classes::Follower::Ready(Now(), at->second);
    }

    void Spend(Ctx const& c, std::string_view skill)
    {
        SkillRow const* row = RowOf(c.follower, skill);
        if (!row)
            return;
        std::lock_guard<std::mutex> guard(mutex);
        auto state = states.find(Key(c.player));
        if (state != states.end())
            state->second.readyAt[CooldownKey(c.follower, skill)] = Now() + CooldownMs(row->cooldown, c.halved);
    }

    void Stun(Unit* caster, Unit* target, double seconds)
    {
        Hold(caster, target, StunHold, seconds);
    }

    void Slow(Unit* caster, Unit* target, double pct, double seconds)
    {
        if (pct > 0)
            Hold(caster, target, SlowHold, seconds, -static_cast<int>(std::lround(pct)));
    }

    void Taunt(Unit* caster, Unit* target, double seconds)
    {
        Hold(caster, target, TauntHold, seconds);
    }

    void Heal(Player* healer, Unit* target, std::uint32_t spellId, double amount)
    {
        if (!healer || !target || !target->IsAlive() || amount <= 0)
            return;
        if (SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId))
        {
            HealInfo heal(healer, target, std::uint32_t(std::min(amount, double(UINT32_MAX))), info, SPELL_SCHOOL_MASK_HOLY);
            healer->HealBySpell(heal);
        }
    }

    bool Strike(Ctx const& c, Unit* target, std::uint32_t spellId, double pct, unsigned schoolMask)
    {
        double low = c.stats.swingMin, high = c.stats.swingMax;
        if (high <= 0)
        {
            // A follower with no weapon keeps the creature's stock damage: its range for the swing's time.
            double const seconds = c.companion->GetAttackTime(BASE_ATTACK) / 1000.0;
            low = c.companion->GetWeaponDamageRange(BASE_ATTACK, MINDAMAGE) * seconds;
            high = c.companion->GetWeaponDamageRange(BASE_ATTACK, MAXDAMAGE) * seconds;
        }
        double more = 1.0, bonus = 0.0;
        if (c.follower == ScoundrelId)
        {
            more = Scoundrel::DamageFactor(c);
            bonus = Scoundrel::CritBonus(c, target);
        }
        bool const critical = Rolls(frand(0.0f, 1.0f), c.stats.critChance + bonus);
        double const multiplier = critical ? CritMultiplier(c.stats.critDamage) : 1.0;
        Combat::Hit hit;
        hit.total = WeaponHit(pct, low, high, frand(0.0f, 1.0f)) * more * multiplier;
        hit.crit = multiplier;
        hit.critical = critical;
        hit.school = schoolMask;
        Combat::DealHit(c.player, target, spellId, hit, true);
        if (critical && c.follower == ScoundrelId)
            Scoundrel::Crit(c);
        return critical;
    }

    void Weary(Unit* caster, Unit* target, double pct, double seconds)
    {
        if (pct > 0)
            Hold(caster, target, WearyHold, seconds, -static_cast<int>(std::lround(pct)));
    }

    void Stand(Player* player, std::uint64_t key, Stat stat, Bucket bucket, double want, Element element)
    {
        Held old;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto state = states.find(Key(player));
            if (state == states.end())
                return;
            auto found = state->second.standing.find(key);
            old = found == state->second.standing.end() ? Held{} : found->second;
            if (std::fabs(old.value - want) < 1e-9 && (want <= 0 || old.element == element))
                return;
            if (want > 0)
                state->second.standing[key] = Held{stat, bucket, element, want};
            else
                state->second.standing.erase(key);
        }
        Stats::RemoveContribution(Key(player), Source::Passives, stat, key);
        if (want > 0)
            Stats::AddContribution(Key(player), {Source::Passives, stat, key, want, bucket, element});
        Stats::Recompute(player);
    }

    double Standing(Player* player, std::uint64_t key, Element* element)
    {
        std::lock_guard<std::mutex> guard(mutex);
        auto state = states.find(Key(player));
        if (state == states.end() || !state->second.standing.count(key))
            return 0.0;
        Held const& held = state->second.standing[key];
        if (element)
            *element = held.element;
        return held.value;
    }

    void ClearStanding(Player* player)
    {
        std::unordered_map<std::uint64_t, Held> held;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto state = states.find(Key(player));
            if (state == states.end() || state->second.standing.empty())
                return;
            held.swap(state->second.standing);
        }
        for (auto const& [key, one] : held)
            Stats::RemoveContribution(Key(player), Source::Passives, one.stat, key);
        Stats::Recompute(player);
    }

    double TakenFactor(Player* player, bool melee)
    {
        return data.ready && player ? Enchantress::Taken(player, melee) : 1.0;
    }

    void Conceal(Player* player, double seconds)
    {
        Hold(player, player, InvisibleHold, seconds);
    }

    void Critical(Player* player)
    {
        Ctx c;
        if (data.ready && Context(player, c) && c.follower == ScoundrelId)
            Scoundrel::Crit(c);
    }

    double CritBonus(Player* player, Unit* target)
    {
        return data.ready ? Scoundrel::CloudBonus(player, target) : 0.0;
    }

    void Shield(Player* player, std::uint64_t untilMs)
    {
        std::lock_guard<std::mutex> guard(mutex);
        auto state = states.find(Key(player));
        if (state != states.end())
            state->second.shieldUntil = untilMs;
    }

    bool Shielded(Player* player)
    {
        std::lock_guard<std::mutex> guard(mutex);
        auto state = states.find(Key(player));
        return state != states.end() && Holds(Now(), state->second.shieldUntil);
    }

    void Tick(Player* player, Creature* companion, Unit* target, std::uint32_t diffMs)
    {
        if (!data.ready || !player || !companion)
            return;
        std::uint32_t since;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto state = states.find(Key(player));
            if (state == states.end())
                return;
            state->second.sinceLook += diffMs;
            if (state->second.sinceLook < Rule("cast_tick_ms"))
                return;
            since = state->second.sinceLook;
            state->second.sinceLook = 0;
        }
        Ctx c;
        if (!Context(player, c) || c.companion != companion)
            return;
        if (c.follower == TemplarId)
            Templar::Tick(c, target, since);
        else if (c.follower == ScoundrelId)
            Scoundrel::Tick(c, target, since);
        else if (c.follower == EnchantressId)
            Enchantress::Tick(c, target, since);
    }

    void Fatal(Player* player, std::uint32_t& damage)
    {
        if (!data.ready || !damage || !player)
            return;
        if (Shielded(player))
        {
            damage = 0;
            return;
        }
        Ctx c;
        if (!Context(player, c))
            return;
        if (c.follower == TemplarId)
            Templar::Fatal(c, damage);
        else if (c.follower == ScoundrelId)
            Scoundrel::Fatal(c, damage);
        else if (c.follower == EnchantressId)
            Enchantress::Fatal(c, damage);
    }

    void RegisterScripts()
    {
        // What the player's skills generate of Fury, Spirit and Essence is scaled by the Templar's Inspire (Resources::Generated asks).
        Resources::GenerationSourceOf() = [](Player const* player, Resources::Resource const& resource)
        { return data.ready && player ? Templar::Generation(player, resource) : 1.0; };
        new Startup();
        new Players();
        new Hits();
        new Commands();
    }

    std::string PickOf(Player const* player, unsigned follower, unsigned tier)
    {
        if (follower < 1 || follower > FollowerCount || tier < 1 || tier > TierCount)
            return {};
        std::lock_guard<std::mutex> guard(mutex);
        auto found = states.find(Key(player));
        return found == states.end() ? std::string() : found->second.picks[follower - 1][tier - 1];
    }

    std::string PickSkill(Player* player, unsigned follower, unsigned tier, std::string const& skill)
    {
        // The window sends a skill's id; the command's "1" and "2" are not ids.
        if (skill == "1" || skill == "2")
            return "Choose a skill of that tier.";
        return TryPick(player, std::to_string(follower), tier, skill);
    }
} // namespace DC::Classes::Follower
