/*
 * Frost Lance and its five runes: the chill every lance gives, Icefury's stacks, Shattering Lance's shards, Frostfire
 * Bolt's burn, Glacial Boulder's freeze and Thunderhail's arcs. The cast is the engine's line through every enemy
 * (Shattering Lance and Glacial Boulder stop on the first, their targeting rows); the Maelstrom it generates is
 * Maelstrom's (dc_shaman_maelstrom.cpp). The dispatch is in dc_shaman.cpp.
 */

#include "dc_shaman_frost_lance.h"
#include "dc_shaman_burning.h"
#include "dc_shaman_chill.h"
#include "dc_shaman_common.h"
#include "dc_shaman_effects.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_periodic_strike.h"
#include "ObjectGuid.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <algorithm>
#include <map>
#include <mutex>
#include <unordered_map>
#include <utility>
#include <vector>

namespace DC::Combat::Shaman::FrostLance
{
    namespace
    {
        constexpr std::string_view Skill = "Frost Lance";
        // The most freeze records kept before the ended ones are swept out.
        constexpr std::size_t SweepAt = 512;

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

        // The record of Icefury, whose numbers the stacks use whichever rune is cast.
        std::uint32_t IcefuryId()
        {
            for (auto const& row : Shells::Abilities)
                if (Skill == row.skill && std::string_view(row.rune) == "Icefury")
                    return row.id;
            return 0;
        }

        double Tune(char const* name)
        {
            return Tunables::Get("combat", name);
        }

        // A strike this file starts is itself a hit of the skill and starts nothing.
        thread_local bool striking = false;

        void Strikes(Player* player, Unit* target, std::uint32_t spellId, double pct)
        {
            striking = true;
            Combat::Strike(player, target, spellId, pct);
            striking = false;
        }

        struct Fury
        {
            unsigned stacks = 0;
            std::uint64_t until = 0; // game time, ms
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, Fury> furies; // by the Shaman
        std::map<std::pair<std::uint64_t, std::uint64_t>, std::uint64_t>
            freezes; // the Shaman, the enemy: when it was frozen

        // "Each Chilled enemy hit gives a stack of Icefury, up to {max_stacks_count}": every stack lasts
        // {duration_seconds} from the latest one.
        void GainStack(Player* player)
        {
            std::uint32_t const id = IcefuryId();
            std::uint64_t const now = Now();
            std::lock_guard<std::mutex> guard(mutex);
            Fury& fury = furies[player->GetGUID().GetRawValue()];
            unsigned const held = Holds(now, fury.until) ? fury.stacks : 0;
            fury.stacks = Stacked(held, 1, unsigned(Numbers::Num(id, "max_stacks_count")));
            fury.until = now + std::uint64_t(Numbers::Num(id, "duration_seconds") * 1000.0);
        }

        // "Stops piercing and shatters on the first enemy, sending {projectile_count} shards in a cone behind it": one
        // shard to each of the nearest enemies in the cone.
        void Shatter(Player* player, Unit* first, std::uint32_t spellId)
        {
            double const length = Tune("frost_lance_shatter_cone_yards"),
                         degrees = Tune("frost_lance_shatter_cone_degrees");
            std::vector<Unit*> behind = Combat::Enemies(player, spellId, first->GetPosition(), length);
            behind.erase(std::remove_if(behind.begin(), behind.end(),
                                        [&](Unit* enemy)
                                        {
                                            return enemy == first ||
                                                   !BehindInCone(player->GetPositionX(), player->GetPositionY(),
                                                                 first->GetPositionX(), first->GetPositionY(),
                                                                 enemy->GetPositionX(), enemy->GetPositionY(), length,
                                                                 degrees);
                                        }),
                         behind.end());
            std::sort(behind.begin(), behind.end(),
                      [first](Unit* a, Unit* b) { return first->GetExactDist(a) < first->GetExactDist(b); });
            auto const shards = std::size_t(Numbers::Num(spellId, "projectile_count"));
            if (behind.size() > shards)
                behind.resize(shards);
            for (Unit* enemy : behind)
                Strikes(player, enemy, spellId, Numbers::Num(spellId, "damage_pct"));
        }

        // "Each enemy pierced releases an arc to {target_count} nearby enemy": the nearest other enemy.
        void Arc(Player* player, Unit* from, std::uint32_t spellId)
        {
            std::vector<Unit*> near =
                Combat::Enemies(player, spellId, from->GetPosition(), Tune("frost_lance_arc_radius_yards"));
            near.erase(std::remove(near.begin(), near.end(), from), near.end());
            std::sort(near.begin(), near.end(),
                      [from](Unit* a, Unit* b) { return from->GetExactDist(a) < from->GetExactDist(b); });
            if (near.size() > std::size_t(Numbers::Num(spellId, "target_count")))
                near.resize(std::size_t(Numbers::Num(spellId, "target_count")));
            for (Unit* enemy : near)
                Strikes(player, enemy, spellId, Numbers::Num(spellId, "damage_pct"));
        }

        // The freeze, once per enemy per `internal_cooldown_seconds`.
        void FreezeOnce(Player* player, Unit* target, std::uint32_t spellId)
        {
            std::uint64_t const now = Now();
            auto const key = std::make_pair(player->GetGUID().GetRawValue(), target->GetGUID().GetRawValue());
            {
                std::lock_guard<std::mutex> guard(mutex);
                if (freezes.size() >= SweepAt)
                    for (auto it = freezes.begin(); it != freezes.end();)
                        it = Freezes(now, it->second, Numbers::Num(spellId, "internal_cooldown_seconds"))
                                 ? freezes.erase(it)
                                 : std::next(it);
                std::uint64_t& last = freezes[key];
                if (!Freezes(now, last, Numbers::Num(spellId, "internal_cooldown_seconds")))
                    return;
                last = now;
            }
            Shaman::Freeze(player, target, Numbers::Num(spellId, "freeze_duration_seconds"));
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        auto const* row = Shells::FindAbility(spellId);
        return row && std::string_view(row->skill) == Skill;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        // The shards, the burn and the arc state a damage of their own and Icefury a duration; the lance still hits for the skill's.
        if (!Is(spellId) || !HitIsSkills(RuneAt(spellId)))
            return std::nullopt;
        return Numbers::Num(BaseId(), "damage_pct");
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId)
    {
        if (striking || !player || !target || !Is(spellId))
            return;
        Rune const rune = RuneAt(spellId);
        // The chill the enemy already carried counts, not the one this hit gives.
        bool const chilled = Chilled(player, target);
        // "... and Chills them by {chill_pct} for {chill_duration_seconds} seconds": every rune keeps the skill's
        // chill.
        Chill(player, target, Numbers::Num(spellId, "chill_pct"), Numbers::Num(spellId, "chill_duration_seconds"));
        switch (rune)
        {
            case Rune::Icefury:
                if (chilled)
                    GainStack(player);
                break;
            case Rune::ShatteringLance:
                Shatter(player, target, spellId);
                break;
            case Rune::FrostfireBolt:
                // "Chilled enemies it hits also burn for {damage_pct} weapon damage as Fire over {dot_duration_seconds}
                // seconds."
                if (Burns(rune, chilled))
                {
                    double const seconds = Numbers::Num(spellId, "dot_duration_seconds");
                    Burning::Burn(player, target, spellId, Numbers::Num(spellId, "damage_pct"), seconds,
                                  Tune("frost_lance_burn_tick_seconds"));
                }
                break;
            case Rune::GlacialBoulder:
                FreezeOnce(player, target, spellId);
                break;
            case Rune::Thunderhail:
                Arc(player, target, spellId);
                break;
            default:
                break;
        }
    }

    void Multipliers(Player* player, std::uint32_t spellId, DC::Combat::Factors& out)
    {
        if (!player)
            return;
        unsigned stacks = 0;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = furies.find(player->GetGUID().GetRawValue());
            if (found == furies.end())
                return;
            if (!Holds(Now(), found->second.until))
            {
                furies.erase(found);
                return;
            }
            stacks = found->second.stacks;
        }
        SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId);
        if (!info || info->GetSchoolMask() != SPELL_SCHOOL_MASK_FROST)
            return;
        if (double const bonus = IcefuryBonus(stacks, Numbers::Num(IcefuryId(), "damage_bonus_pct")))
            AddFactor(out, "Icefury", bonus);
    }
} // namespace DC::Combat::Shaman::FrostLance
