/*
 * Bloodlust and its five runes: the buff on the Shaman and every ally in reach (attack and movement speed, and what the
 * rune adds), refreshed and never stacked by a second cast, and Thirst for Battle's extension for each kill. The cast
 * is the engine's group spell (the allies in reach are the targets the class is told of); the buff lives on each
 * player's stat sheet and ends by a stamped event. The dispatch is in dc_shaman.cpp.
 */

#include "dc_shaman_bloodlust.h"
#include "dc_shaman_common.h"
#include "../../combat/dc_combat.h"
#include "../../items/dc_inventory.h"
#include "../../stats/dc_stats.h"
#include "Creature.h"
#include "ScriptMgr.h"
#include "Unit.h"

#include <chrono>
#include <mutex>
#include <unordered_map>

namespace DC::Combat::Shaman::Bloodlust
{
    namespace
    {
        constexpr std::string_view Skill = "Bloodlust";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && std::string_view(row->skill) == Skill ? RuneOf(row->rune) : Rune::None;
        }

        // The record of the skill itself: the numbers a rune takes from it are stated there.
        std::uint32_t BaseId()
        {
            for (auto const& row : Shells::Abilities)
                if (Skill == row.skill && !*row.rune)
                    return row.id;
            return 0;
        }

        // The buff a player carries: the record of the cast that gave it, the rune, until when and the stamp its end
        // answers to.
        struct Buff
        {
            std::uint32_t spellId = 0;
            Rune rune = Rune::None;
            std::uint64_t until = 0; // game time, ms
            std::uint64_t extended = 0;
            std::uint64_t stamp = 0;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, Buff> buffs; // by the player
        std::uint64_t stamps = 0;

        // The sheet numbers of the buff, taken off.
        void Strip(std::uint64_t guid)
        {
            std::uint32_t const id = BaseId();
            for (Stat stat : {Stat::AttackSpeed, Stat::MovementSpeed, Stat::SpecificReduction,
                              Stat::MaelstromGeneration, Stat::CooldownReduction})
                Stats::RemoveContribution(guid, Source::Temporary, stat, id);
            for (unsigned element = 0; element < ElementCount; ++element)
                Stats::RemoveContribution(guid, Source::Temporary, Stat::ElementalDamage,
                                          std::uint64_t(id) * ElementCount + element);
        }

        // The sheet numbers of the buff the record `spellId` gives, put on (after Strip).
        void Put(Player* player, std::uint32_t spellId, Rune rune)
        {
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            std::uint32_t const id = BaseId();
            Strip(guid);
            // "gain +{attack_speed_pct} attack speed and +{movement_speed_pct} movement speed".
            Stats::AddContribution(guid, {Source::Temporary, Stat::AttackSpeed, id,
                                          Numbers::Num(spellId, "attack_speed_pct"), Bucket::Flat});
            Stats::AddContribution(guid, {Source::Temporary, Stat::MovementSpeed, id,
                                          Numbers::Num(spellId, "movement_speed_pct"), Bucket::Flat});
            switch (AddsOf(rune))
            {
                case Adds::DamageReduction:
                    Stats::AddContribution(guid, {Source::Temporary, Stat::SpecificReduction, id,
                                                  Numbers::Num(spellId, "damage_reduction_pct"), Bucket::Flat});
                    break;
                case Adds::DamageBonus:
                    for (unsigned element = 0; element < ElementCount; ++element)
                        Stats::AddContribution(guid, {Source::Temporary, Stat::ElementalDamage,
                                                      std::uint64_t(id) * ElementCount + element,
                                                      Numbers::Num(spellId, "damage_bonus_pct"), Bucket::Flat,
                                                      static_cast<DC::Element>(element)});
                    break;
                case Adds::MaelstromGeneration:
                    Stats::AddContribution(guid, {Source::Temporary, Stat::MaelstromGeneration, id,
                                                  Numbers::Num(spellId, "regen_pct"), Bucket::Flat});
                    break;
                case Adds::CooldownReduction:
                    Stats::AddContribution(guid, {Source::Temporary, Stat::CooldownReduction, id,
                                                  Numbers::Num(spellId, "cooldown_reduction_pct"), Bucket::Flat});
                    break;
                default:
                    break;
            }
            Stats::Recompute(player);
            Inventory::PushSheet(player);
        }

        void Over(Player* player, std::uint64_t key, std::uint64_t stamp);

        void Watch(Player* player, std::uint64_t key, std::uint64_t stamp, std::uint64_t untilMs)
        {
            std::uint64_t const now = Now();
            auto const wait = std::uint32_t(untilMs > now ? untilMs - now : 0);
            player->m_Events.AddEventAtOffset([player, key, stamp] { Over(player, key, stamp); },
                                              std::chrono::milliseconds(wait + 1));
        }

        // The end, or the wait again for a buff a kill has extended since.
        void Over(Player* player, std::uint64_t key, std::uint64_t stamp)
        {
            std::uint64_t until;
            bool over;
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto found = buffs.find(key);
                if (found == buffs.end() || found->second.stamp != stamp)
                    return;
                until = found->second.until;
                over = !Holds(Now(), until);
                if (over)
                    buffs.erase(found);
            }
            if (!over)
            {
                Watch(player, key, stamp, until);
                return;
            }
            Strip(key);
            Stats::Recompute(player);
            Inventory::PushSheet(player);
        }

        // "Casting it again refreshes the duration; it never stacks": the player's one buff is replaced.
        void Grant(Player* player, std::uint32_t spellId, double seconds)
        {
            std::uint64_t const key = player->GetGUID().GetRawValue();
            Rune const rune = RuneAt(spellId);
            std::uint64_t stamp, until;
            {
                std::lock_guard<std::mutex> guard(mutex);
                Buff& buff = buffs[key];
                stamp = buff.stamp = ++stamps;
                buff.spellId = spellId;
                buff.rune = rune;
                buff.extended = 0;
                until = buff.until = Now() + std::uint64_t(seconds * 1000.0);
            }
            Put(player, spellId, rune);
            Watch(player, key, stamp, until);
        }

        class KillScript final : public PlayerScript
        {
        public:
            KillScript()
                : PlayerScript("dc_shaman_bloodlust", {PLAYERHOOK_ON_CREATURE_KILL, PLAYERHOOK_ON_LOGOUT})
            {
            }

            // Thirst for Battle: "Each kill during Bloodlust extends it by {duration_seconds:extend} seconds, up to
            // {duration_seconds:cap} extra seconds."
            void OnPlayerCreatureKill(Player* killer, Creature*) override
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto found = buffs.find(killer->GetGUID().GetRawValue());
                if (found == buffs.end() || !Holds(Now(), found->second.until))
                    return;
                std::uint64_t const more = Extension(found->second.rune, found->second.extended,
                                                     Numbers::Num(found->second.spellId, "duration_seconds", "extend"),
                                                     Numbers::Num(found->second.spellId, "duration_seconds", "cap"));
                found->second.extended += more;
                found->second.until += more;
            }

            void OnPlayerLogout(Player* player) override
            {
                std::lock_guard<std::mutex> guard(mutex);
                buffs.erase(player->GetGUID().GetRawValue());
            }
        };
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        auto const* row = Shells::FindAbility(spellId);
        return row && std::string_view(row->skill) == Skill;
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        if (!player || !Is(spellId))
            return;
        // "gain ... for {duration_seconds} seconds": the base skill's seconds; Thirst for Battle states its extension
        // under the same name.
        double const seconds =
            Combat::ModifiedDurationSeconds(player, spellId, Numbers::Num(BaseId(), "duration_seconds"));
        Grant(player, spellId, seconds);
        for (Unit* unit : targets)
            if (Player* ally = unit ? unit->ToPlayer() : nullptr; ally && ally != player)
                Grant(ally, spellId, seconds);
    }

    void RegisterScripts()
    {
        new KillScript();
    }
} // namespace DC::Combat::Shaman::Bloodlust
