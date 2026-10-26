/*
 * The Necromancer's passives that need code: Life from Death, Fueled by Death, Stand Alone, Bone Prison, Swift
 * Harvesting, Commander of the Risen Dead; Extended Servitude, Rigor Mortis, Overwhelming Essence, Dark Reaping,
 * Spreading Malediction, Eternal Torment and Final Service; Grisly Tribute, Draw Life, Serration, Aberrant Animator, Blood
 * for Blood, Blood Is Power and Rathma's Shield. The numbers are necromancer_passive_values.csv (skill = the passive's
 * name) and the passives' power files, read through each passive's record.
 *
 * A passive is on when it sits in one of the Necromancer's passive slots, or a worn item grants it (Passives::Has).
 * Stand Alone is a number that follows the minions, kept by a small update script; Life from Death and Fueled by Death
 * hear the corpses a skill consumes; Bone Prison rides the hits (Landed); Swift Harvesting rides the attack speed of a
 * skill; Commander of the Risen Dead and Eternal Torment ride the cast of the skill whose cost they cut; Overwhelming Essence
 * is a stat the update script keeps; Dark Reaping rides the kill; Rigor Mortis rides the hit; Spreading Malediction rides
 * the hit's multipliers; Final Service rides the damage taken; Extended Servitude and Eternal Torment give the minions' and the
 * curses' seconds to the skills that ask.
 */

#include "dc_necromancer_passives.h"
#include "dc_necromancer_passives_math.h"
#include "dc_necromancer_common.h"
#include "dc_necromancer_curses.h"
#include "../../combat/dc_corpses.h"
#include "../../combat/dc_cost_cut.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_minions.h"
#include "../../combat/dc_passives.h"
#include "../../common/dc_numeric_data.h"
#include "../../items/dc_items.h"
#include "../../stats/dc_stats.h"

#include "DatabaseEnv.h"
#include "GameTime.h"
#include "Random.h"
#include "ScriptMgr.h"
#include "Spell.h"
#include "SpellInfo.h"
#include "SpellMgr.h"

#include <mutex>
#include <unordered_map>
#include <unordered_set>

namespace DC::Combat::Necromancer::Passive
{
    namespace
    {
        constexpr Resources::Resource const& Essence = *Resources::Find("Necromancer", "essence");

        double Tune(char const* name)
        {
            return DC::Tunables::Get("necromancer", name);
        }

        std::uint32_t Id(std::string_view name)
        {
            for (auto const& passive : Shells::Passives)
                if (name == passive.name)
                    return passive.id;
            return 0;
        }

        bool IsNecromancer(Player const* player)
        {
            return player && Classes::ClassIdOf(player) == Essence.classId;
        }

        bool On(Player* player, char const* name)
        {
            return IsNecromancer(player) && Passives::Has(player, name);
        }

        double Num(char const* name, char const* token, char const* qualifier = "")
        {
            return Numbers::Num(Id(name), token, qualifier);
        }

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        // Life from Death's globes, per Necromancer: the window its cap counts in.
        std::mutex mutex;
        std::unordered_map<std::uint64_t, GlobeWindow> globes;
        // Stand Alone's look at the minions (ms since the last), per Necromancer.
        std::unordered_map<std::uint64_t, std::uint32_t> standAloneClock;
        // Overwhelming Essence is on the sheet for these Necromancers, and Final Service's sustain and wait for each.
        std::unordered_set<std::uint64_t> overwhelming;
        std::unordered_map<std::uint64_t, Sustain> sustains;
        // Rathma's Shield's window, Blood for Blood's stacks, Blood Is Power's Life lost and the skills it has already shortened since their last use.
        std::unordered_map<std::uint64_t, Ward> wards;
        std::unordered_map<std::uint64_t, FreeCosts> freeCosts;
        std::unordered_map<std::uint64_t, LostLife> lostLife;
        std::unordered_map<std::uint64_t, std::unordered_set<std::uint32_t>> shortened;
        // Commander of the Risen Dead's and Eternal Torment's cuts as they stand now, per player (CostCuts).
        std::unordered_map<std::uint64_t, std::pair<bool, bool>> cutting;
        // The base items that are scythes (dc_base_item), for Dark Reaping.
        std::unordered_set<std::uint32_t> scythes;

        void Maximum(Player* player);
        void DrawLife(Player* player);
        void ShortenCooldowns(Player* player);

        // Whether the Necromancer's main hand holds a scythe.
        bool UsesScythe(Player* player)
        {
            Item const* hand = player->GetItemByPos(INVENTORY_SLOT_BAG_0, EQUIPMENT_SLOT_MAINHAND);
            if (!hand)
                return false;
            auto const rolled = Items::Get(hand->GetGUID().GetCounter());
            std::lock_guard<std::mutex> guard(mutex);
            return scythes.count(rolled ? rolled->baseItem : hand->GetEntry()) > 0;
        }

        // Commander of the Risen Dead's and Eternal Torment's Essence cuts: the cost the core charges is lower BEFORE the cast, through the skill's hidden
        // cost aura (CostCut), for as long as the passive is slotted or worn. Kept to what the passives are now: a change puts the cut on or takes it off.
        void CostCuts(Player* player)
        {
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            bool const commander = On(player, "Commander of the Risen Dead"), torment = On(player, "Eternal Torment");
            bool changedCommander, changedTorment;
            {
                std::lock_guard<std::mutex> guard(mutex);
                std::pair<bool, bool>& held = cutting[guid];
                changedCommander = held.first != commander;
                changedTorment = held.second != torment;
                held = {commander, torment};
            }
            // "The Essence cost of Command Skeletons ... reduced by {cooldown_reduction_pct}"
            if (changedCommander)
                CostCut::Stand(player, "Command Skeletons", Id("Commander of the Risen Dead"),
                               commander ? Num("Commander of the Risen Dead", "cooldown_reduction_pct") : 0.0);
            // "Your curses cost {cost_reduction_pct} less Essence"
            if (changedTorment)
                for (std::string_view curse : CurseSkills)
                    CostCut::Stand(player, curse, Id("Eternal Torment"), torment ? Num("Eternal Torment", "cost_reduction_pct") : 0.0);
        }

        // The health globe a corpse leaves. The globe itself belongs to the health globes work (on hold): nothing stands on the
        // ground until it lands, so this is where its spawn goes.
        void SpawnGlobe(Player* /*player*/, Corpses::Spot const& /*where*/) {}

        // Consuming a corpse: Fueled by Death's speed for each, Life from Death's roll for each.
        void Consumed(Player* player, std::vector<Corpses::Spot> const& taken)
        {
            if (!IsNecromancer(player) || taken.empty())
                return;
            if (On(player, "Fueled by Death"))
                // "increases your movement speed by {movement_speed_pct} for {duration_seconds} seconds ... up to
                // {max_stacks_count} times"
                Buffs::Stack(player, Id("Fueled by Death"), Stat::MovementSpeed, Bucket::Flat,
                             Num("Fueled by Death", "movement_speed_pct"),
                             unsigned(Num("Fueled by Death", "max_stacks_count")),
                             Num("Fueled by Death", "duration_seconds"), unsigned(taken.size()));
            if (!On(player, "Life from Death"))
                return;
            for (Corpses::Spot const& spot : taken)
            {
                if (!Procs(frand(0.0f, 100.0f), Tune("life_from_death_chance_pct")))
                    continue;
                bool allowed;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    allowed = globes[player->GetGUID().GetRawValue()].Allow(
                        Now(), std::uint64_t(Tune("life_from_death_window_seconds") * 1000.0 + 0.5),
                        unsigned(Tune("life_from_death_max_globes")));
                }
                if (allowed)
                    SpawnGlobe(player, spot);
            }
        }

        // Stand Alone: the armor follows the minions standing, a look every tick of the power ("Buff Tick Rate").
        class Update final : public PlayerScript
        {
        public:
            Update()
                : PlayerScript("dc_necromancer_passives", {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_CREATURE_KILL})
            {
            }

            void OnPlayerUpdate(Player* player, uint32 diff) override
            {
                if (!IsNecromancer(player))
                    return;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    std::uint32_t& clock = standAloneClock[player->GetGUID().GetRawValue()];
                    if ((clock += diff) < std::uint32_t(Tune("stand_alone_tick_seconds") * 1000.0 + 0.5))
                        return;
                    clock = 0;
                }
                // "Increase armor by {armor_pct:base}, reduced by {armor_pct:per_minion} for each active minion."
                double const pct =
                    On(player, "Stand Alone")
                        ? StandAloneArmorPct(Num("Stand Alone", "armor_pct", "base"),
                                             Num("Stand Alone", "armor_pct", "per_minion"), Minions::Count(player))
                        : 0.0;
                Buffs::Set(player, Id("Stand Alone"), Stat::Armor, Bucket::Percent, pct);
                Maximum(player);
                CostCuts(player);
                DrawLife(player);
            }

            // Dark Reaping: "While using a scythe, gain {gain_pct} Essence and Life per kill."
            void OnPlayerCreatureKill(Player* killer, Creature*) override
            {
                if (!On(killer, "Dark Reaping") || !UsesScythe(killer))
                    return;
                double const pct = Num("Dark Reaping", "gain_pct");
                Resources::Energize(killer, Essence, Id("Dark Reaping"), ReapGain(Resources::Max(killer, Essence), pct), false);
                Heal(killer, Id("Dark Reaping"), ReapGain(killer->GetMaxHealth(), pct));
            }

            void OnPlayerLogout(Player* player) override
            {
                std::lock_guard<std::mutex> guard(mutex);
                standAloneClock.erase(player->GetGUID().GetRawValue());
                globes.erase(player->GetGUID().GetRawValue());
                overwhelming.erase(player->GetGUID().GetRawValue());
                sustains.erase(player->GetGUID().GetRawValue());
                wards.erase(player->GetGUID().GetRawValue());
                freeCosts.erase(player->GetGUID().GetRawValue());
                lostLife.erase(player->GetGUID().GetRawValue());
                shortened.erase(player->GetGUID().GetRawValue());
                cutting.erase(player->GetGUID().GetRawValue());
            }
        };

        // Overwhelming Essence: "Increase your maximum Essence by {max_pool_resource}", on the sheet while the passive is on.
        void Maximum(Player* player)
        {
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            bool const wanted = On(player, "Overwhelming Essence");
            {
                std::lock_guard<std::mutex> guard(mutex);
                if ((overwhelming.count(guid) > 0) == wanted)
                    return;
                if (wanted)
                    overwhelming.insert(guid);
                else
                    overwhelming.erase(guid);
            }
            std::uint32_t const id = Id("Overwhelming Essence");
            Stats::RemoveContribution(guid, Source::Passives, Stat::MaxFury, id);
            if (wanted)
                Stats::AddContribution(guid, {Source::Passives, Stat::MaxFury, id, Num("Overwhelming Essence", "max_pool_resource"),
                                              Bucket::Flat});
            Stats::Recompute(player);
        }

        // Draw Life: "Increases your Life regeneration by {life_regen_pct} for each enemy within {radius_yards} yards".
        void DrawLife(Player* player)
        {
            std::uint32_t const id = Id("Draw Life");
            double pct = 0.0;
            if (On(player, "Draw Life"))
                pct = DrawLifePct(Num("Draw Life", "life_regen_pct"),
                                  unsigned(Combat::Enemies(player, id, player->GetPosition(), Num("Draw Life", "radius_yards")).size()));
            Buffs::Set(player, id, Stat::LifeRegen, Bucket::Percent, pct);
        }

        // Blood Is Power: every ability that is cooling down is shortened by the share of what it has left, once for each time it was used.
        void ShortenCooldowns(Player* player)
        {
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            double const pct = Num("Blood Is Power", "cooldown_reduction_pct");
            for (Classes::Slot const& slot : Classes::Bar(player))
            {
                std::uint32_t const left = player->GetSpellCooldownDelay(slot.spellId);
                if (!left)
                    continue;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    if (!shortened[guid].insert(slot.spellId).second)
                        continue;
                }
                if (std::uint32_t const cut = CooldownCut(left, pct))
                    Combat::SendSkillCooldown(player, slot.spellId, left - cut);
            }
        }

        // Aberrant Animator: "Your minions gain {thorns_share_pct} of your Thorns": an enemy that strikes a minion takes that much Thorns
        // damage from the Necromancer.
        class Thorns final : public UnitScript
        {
        public:
            Thorns()
                : UnitScript("dc_necromancer_passives_thorns", true, {UNITHOOK_ON_DAMAGE})
            {
            }

            void OnDamage(Unit* attacker, Unit* victim, std::uint32_t& damage) override
            {
                Creature* minion = victim ? victim->ToCreature() : nullptr;
                Player* owner = minion && minion->GetOwner() ? minion->GetOwner()->ToPlayer() : nullptr;
                if (!damage || !attacker || !owner || minion->GetScriptName() != "dc_minion" || !On(owner, "Aberrant Animator") ||
                    !owner->IsValidAttackTarget(attacker))
                    return;
                if (auto const sheet = DC::Stats::Get(owner->GetGUID().GetRawValue()))
                    if (double const thorns = MinionThorns((*sheet)[Stat::Thorns], Num("Aberrant Animator", "thorns_share_pct")); thorns > 0)
                        Stats::ThornsHit(owner, attacker, thorns);
            }
        };

        // The base items that are scythes, read from the base item table at startup and on a reload.
        class World final : public WorldScript
        {
        public:
            World()
                : WorldScript("dc_necromancer_passives_world", {WORLDHOOK_ON_STARTUP, WORLDHOOK_ON_AFTER_CONFIG_LOAD})
            {
            }

            void OnAfterConfigLoad(bool reload) override
            {
                if (reload)
                    OnStartup();
            }

            void OnStartup() override
            {
                std::unordered_set<std::uint32_t> found;
                if (QueryResult rows = WorldDatabase.Query("SELECT entry,type FROM dc_base_item"))
                    do
                    {
                        Field* f = rows->Fetch();
                        if (ScytheType(f[1].Get<std::string>()))
                            found.insert(f[0].Get<std::uint32_t>());
                    } while (rows->NextRow());
                std::lock_guard<std::mutex> guard(mutex);
                scythes = std::move(found);
            }
        };

        // The cast of Command Skeletons and Command Golem and of the curses, after the core has taken the cost and installed
        // the cooldown.
        class CastHook final : public AllSpellScript
        {
        public:
            CastHook()
                : AllSpellScript("dc_necromancer_passives_cast", {ALLSPELLHOOK_ON_CAST})
            {
            }

            void OnSpellCast(Spell* spell, Unit* caster, SpellInfo const* info, bool) override
            {
                Player* player = caster ? caster->ToPlayer() : nullptr;
                auto const* row = info ? Shells::FindAbility(info->Id) : nullptr;
                if (!player || !row || spell->IsTriggered() || !IsNecromancer(player))
                    return;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    if (auto const found = shortened.find(player->GetGUID().GetRawValue()); found != shortened.end())
                        found->second.erase(info->Id);
                }
                if (!On(player, "Commander of the Risen Dead"))
                    return;
                double const pct = Num("Commander of the Risen Dead", "cooldown_reduction_pct");
                if (row->skill == std::string_view("Command Golem"))
                {
                    // "... and the cooldown of Command Golem": the cooldown the core installed is shortened by the
                    // share.
                    if (std::uint32_t const left = player->GetSpellCooldownDelay(info->Id))
                        if (std::uint32_t const cut = CooldownCut(left, pct))
                            Combat::SendSkillCooldown(player, info->Id, left - cut);
                }
            }
        };
    } // namespace

    void Landed(Player* player, Unit* target, std::uint32_t spellId)
    {
        auto const* row = Shells::FindAbility(spellId);
        if (!player || !target || !row)
            return;
        // "Poison abilities also slow enemies by {slow_pct} and reduce their attack speed by {attack_speed_pct:enemy} for {duration_seconds}
        // seconds."
        if (SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId); info && PoisonMask(info->GetSchoolMask()) && On(player, "Rigor Mortis"))
        {
            Slow(player, target, Num("Rigor Mortis", "slow_pct"), Num("Rigor Mortis", "duration_seconds"));
            Weary(player, target, Num("Rigor Mortis", "attack_speed_pct", "enemy"), Num("Rigor Mortis", "duration_seconds"));
        }
        if (!BonePrisonSkill(row->skill) || !On(player, "Bone Prison"))
            return;
        // "have a {proc_chance_pct} chance to trap enemies in a Bone Prison for {duration_seconds} seconds": a stun,
        // stretched by the worn stun powers.
        if (Procs(frand(0.0f, 100.0f), Num("Bone Prison", "proc_chance_pct")))
            Stun(player, target, Num("Bone Prison", "duration_seconds") * ItemPowers::StunFactor(player));
    }

    double AttackSpeed(Player* player, std::uint32_t spellId, double base)
    {
        auto const* row = Shells::FindAbility(spellId);
        if (!player || base <= 0 || !row || !SwiftHarvestingSkill(row->skill) || !On(player, "Swift Harvesting"))
            return base;
        auto const sheet = DC::Stats::Get(player->GetGUID().GetRawValue());
        if (!sheet)
            return base;
        return SwiftHarvestingAps(base, (*sheet)[Stat::AttackSpeed], Num("Swift Harvesting", "attack_speed_pct"),
                                  DC::NumericData::Rule("attack_speed_cap"));
    }

    void Multipliers(Player* player, Unit* target, std::uint32_t spellId, DC::Combat::Factors& out)
    {
        // "Receive a {damage_bonus_pct} damage bonus for each enemy afflicted by one of your curses."
        if (On(player, "Spreading Malediction"))
            if (double const bonus = MaledictionPct(Num("Spreading Malediction", "damage_bonus_pct"), Curses::Cursed(player)); bonus > 0)
                AddFactor(out, "Spreading Malediction", bonus);
        // "deal {damage_bonus_pct} increased damage for every {distance_yards} yards from you, up to a maximum of {max_bonus_pct}."
        auto const* row = Shells::FindAbility(spellId);
        if (target && row && SerrationSkill(row->skill) && On(player, "Serration"))
            if (double const bonus = SerrationPct(player->GetExactDist(target), Num("Serration", "damage_bonus_pct"),
                                                  Num("Serration", "distance_yards"), Num("Serration", "max_bonus_pct"));
                bonus > 0)
                AddFactor(out, "Serration", bonus);
    }

    // Final Service: the lethal blow starts a window in which every blow does nothing.
    static double Sustained(Player* player, double damage)
    {
        std::uint32_t const id = Id("Final Service");
        bool const has = id && Passives::Has(player, "Final Service");
        std::uint64_t const now = Now();
        bool saved;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto const found = sustains.find(player->GetGUID().GetRawValue());
            if (found != sustains.end() && found->second.Active(now))
                return 0.0;
            if (!has)
                return damage;
            saved = sustains[player->GetGUID().GetRawValue()].Save(
                now, damage, player->GetHealth(), std::uint64_t(Numbers::Num(id, "internal_cooldown_seconds") * 1000.0 + 0.5),
                std::uint64_t(Numbers::Num(id, "duration_seconds") * 1000.0 + 0.5));
        }
        if (!saved)
            return damage;
        // "When you take lethal damage, you are sustained preventing all damage ... In addition, you heal for {heal_pct} of your Life
        // per minion."
        Heal(player, id, ServiceHeal(player->GetMaxHealth(), Numbers::Num(id, "heal_pct"), Minions::Count(player)));
        return 0.0;
    }

    double Reduce(Unit* victim, double damage)
    {
        Player* player = victim ? victim->ToPlayer() : nullptr;
        if (!IsNecromancer(player) || damage <= 0)
            return damage;
        // Rathma's Shield: "You cannot lose Life" while its window is open.
        if (LifeLocked(player))
            return 0.0;
        double const taken = Sustained(player, damage);
        LifeLost(player, std::min(taken, double(player->GetHealth())));
        return taken;
    }

    void Casting(Player* player, std::uint32_t spellId)
    {
        auto const* row = Shells::FindAbility(spellId);
        if (!row || !RathmaSkill(row->skill) || !On(player, "Rathma's Shield"))
            return;
        // "You cannot lose Life for {duration_seconds} seconds after using Land of the Dead, Army of the Dead, or Simulacrum": the window opens
        // before the cast's own Life cost, and not more than once in the wait.
        std::uint32_t const id = Id("Rathma's Shield");
        std::lock_guard<std::mutex> guard(mutex);
        wards[player->GetGUID().GetRawValue()].Open(Now(), std::uint64_t(Numbers::Num(id, "duration_seconds") * 1000.0 + 0.5),
                                                    std::uint64_t(Numbers::Num(id, "internal_cooldown_seconds") * 1000.0 + 0.5));
    }

    bool LifeLocked(Player* player)
    {
        std::lock_guard<std::mutex> guard(mutex);
        auto const found = wards.find(player->GetGUID().GetRawValue());
        return found != wards.end() && found->second.Active(Now());
    }

    bool WaivesLifeCost(Player* player)
    {
        if (!On(player, "Blood for Blood"))
            return false;
        std::lock_guard<std::mutex> guard(mutex);
        return freeCosts[player->GetGUID().GetRawValue()].Spend();
    }

    void GlobePicked(Player* player)
    {
        if (!On(player, "Blood for Blood"))
            return;
        std::lock_guard<std::mutex> guard(mutex);
        freeCosts[player->GetGUID().GetRawValue()].Gain(unsigned(Num("Blood for Blood", "max_stacks_count")));
    }

    void LifeLost(Player* player, double amount)
    {
        if (!On(player, "Blood Is Power") || amount <= 0)
            return;
        unsigned whole;
        {
            std::lock_guard<std::mutex> guard(mutex);
            whole = lostLife[player->GetGUID().GetRawValue()].Add(amount, player->GetMaxHealth(),
                                                                  Num("Blood Is Power", "life_lost_threshold_pct"));
        }
        // "After cumulatively losing {life_lost_threshold_pct} of your maximum Life, all ability cooldowns are reduced by
        // {cooldown_reduction_pct}": each whole threshold is one reduction.
        for (unsigned i = 0; i < whole; ++i)
            ShortenCooldowns(player);
    }

    double DurationFactor(Player* player, std::string_view skill)
    {
        // "Increase the duration of your Skeletal Mage and Revive minions by {duration_bonus_pct}."
        return ServitudeSkill(skill) && On(player, "Extended Servitude")
                   ? ServitudeFactor(Num("Extended Servitude", "duration_bonus_pct"))
                   : 1.0;
    }

    double CurseSeconds(Player* player, double seconds)
    {
        // "Your curses ... last forever."
        return CurseSeconds(On(player, "Eternal Torment"), seconds, Tune("eternal_torment_forever_seconds"));
    }

    void Register()
    {
        Corpses::OnConsumed(Consumed);
        // Grisly Tribute: "You are healed for {life_per_hit_share_pct} of your Life on Hit when one of your minions hits an enemy."
        Minions::OnStruck(
            [](Player* owner, Unit*)
            {
                if (!On(owner, "Grisly Tribute"))
                    return;
                if (auto const sheet = DC::Stats::Get(owner->GetGUID().GetRawValue()))
                    Heal(owner, Id("Grisly Tribute"),
                         TributeHeal((*sheet)[Stat::LifePerHit], Num("Grisly Tribute", "life_per_hit_share_pct")));
            });
        new Thorns();
        new Update();
        new CastHook();
        new World();
    }
} // namespace DC::Combat::Necromancer::Passive
