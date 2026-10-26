/*
 * The Earthbind Totem and its five runes. The cast and the totem itself are the totem seam's (dc_shaman_totems.cpp);
 * here is what a standing Earthbind Totem does: every earthbind_tick_seconds it slows the enemies within its
 * radius_yards by slow_pct (a hold that ends a little after they leave). Earthgrab roots each enemy the first time it
 * meets the totem; Tremor Totem makes the Shaman who stands in its radius immune to Fear, Charm and Stun; Glacial
 * Ground marks the enemies in its radius so the Shaman's skills deal more to them; Gale Vortex pulls them to the totem
 * on its own interval; Magma Seep burns them.
 */

#include "dc_shaman_earthbind_totem.h"
#include "dc_shaman_common.h"
#include "dc_shaman_earthbind_totem_math.h"
#include "dc_shaman_effects.h"
#include "dc_shaman_totems_math.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_control_immunity.h"
#include "../../combat/dc_movement_effects.h"
#include "Creature.h"
#include "Unit.h"

#include <mutex>
#include <string_view>
#include <unordered_map>

namespace DC::Combat::Shaman::Earthbind
{
    namespace
    {
        constexpr std::string_view Skill = "Earthbind Totem";

        std::mutex mutex;
        // Glacial Ground's mark on each enemy, by Shaman and then enemy: when it ends.
        std::unordered_map<std::uint64_t, std::unordered_map<std::uint64_t, std::uint64_t>> marks;
        // The record whose Tremor Totem immunity each Shaman wears now.
        std::unordered_map<std::uint64_t, std::uint32_t> tremor;

        std::string_view RuneOf(std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && std::string_view(row->skill) == Skill ? std::string_view(row->rune) : std::string_view();
        }

        // The record of one of the skill's runes.
        std::uint32_t RuneId(std::string_view rune)
        {
            for (auto const& row : Shells::Abilities)
                if (Skill == row.skill && rune == row.rune)
                    return row.id;
            return 0;
        }

        // Glacial Ground: "Enemies are Chilled and take {damage_taken_pct} more damage from all your skills" while in
        // the radius.
        void Mark(Player* player, Unit* enemy, double holdSeconds)
        {
            std::uint64_t const now = Now();
            std::lock_guard<std::mutex> guard(mutex);
            auto& mine = marks[player->GetGUID().GetRawValue()];
            for (auto it = mine.begin(); it != mine.end();)
                it = Marked(it->second, now) ? std::next(it) : mine.erase(it);
            mine[enemy->GetGUID().GetRawValue()] = HeldUntil(now, holdSeconds);
        }

        // One look at the enemies within the radius.
        void Tick(Player* player, Creature* totem, std::uint32_t source, Totems::State& state, double tick)
        {
            std::string_view const rune = RuneOf(source);
            double const radius = Numbers::Num(source, "radius_yards");
            double const hold = Tunable("earthbind_hold_seconds");
            for (Unit* enemy : Combat::Enemies(player, source, totem->GetPosition(), radius))
            {
                Slow(player, enemy, Numbers::Num(source, "slow_pct"), hold);
                if (rune == "Earthgrab" && FirstEntry(state.seen, enemy->GetGUID().GetRawValue()))
                    Root(player, enemy, Numbers::Num(source, "immobilize_duration_seconds"));
                else if (rune == "Glacial Ground")
                    Mark(player, enemy, hold);
            }
            // "Enemies in the radius burn for {damage_pct} weapon damage as Fire per second": a tick is its share of a
            // second.
            if (rune == "Magma Seep")
                Combat::StrikeArea(player, source, totem->GetPosition(), radius,
                                   Numbers::Num(source, "damage_pct") * tick);
        }
    } // namespace

    void Update(Player* player, Creature* totem, std::uint32_t source, Totems::State& state, std::uint32_t diff)
    {
        double const tick = Tunable("earthbind_tick_seconds");
        for (unsigned due = Totems::Pulses(state.clock[0], diff, tick); due; --due)
            Tick(player, totem, source, state, tick);
        // Gale Vortex: "Every {interval_seconds} seconds, pulls all enemies within {radius_yards} yards toward the
        // totem."
        if (RuneOf(source) != "Gale Vortex")
            return;
        for (unsigned due = Totems::Pulses(state.clock[1], diff, Numbers::Num(source, "interval_seconds")); due; --due)
            for (Unit* enemy :
                 Combat::Enemies(player, source, totem->GetPosition(), Numbers::Num(source, "radius_yards")))
                Combat::Abilities::Pull(enemy, totem->GetPosition());
    }

    void Upkeep(Player* player)
    {
        // Tremor Totem: "While you are within its radius, you are immune to Fear, Charm and Stun."
        std::uint32_t wanted = 0;
        if (std::uint32_t const standing = Totems::Standing(player, Totems::EarthSlot);
            standing && RuneOf(standing) == "Tremor Totem")
            if (Creature* totem = Totems::Totem(player, Totems::EarthSlot);
                totem && Within(player->GetExactDist(totem), Numbers::Num(standing, "radius_yards")))
                wanted = standing;
        std::uint32_t worn;
        {
            std::lock_guard<std::mutex> guard(mutex);
            std::uint32_t& held = tremor[player->GetGUID().GetRawValue()];
            worn = held;
            held = wanted;
        }
        if (worn == wanted)
            return;
        if (worn)
            ControlImmunity::SetFearCharmStun(player, worn, false);
        if (wanted)
            ControlImmunity::SetFearCharmStun(player, wanted, true);
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        auto const* row = Shells::FindAbility(spellId);
        return row && std::string_view(row->skill) == Skill ? Numbers::Get(spellId, "damage_pct") : std::nullopt;
    }

    void Multipliers(Player* player, Unit* target, std::uint32_t, DC::Combat::Factors& out)
    {
        if (!target)
            return;
        bool marked;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto mine = marks.find(player->GetGUID().GetRawValue());
            if (mine == marks.end())
                return;
            auto on = mine->second.find(target->GetGUID().GetRawValue());
            marked = on != mine->second.end() && Marked(on->second, Now());
        }
        if (double const pct = MorePct(marked, Numbers::Num(RuneId("Glacial Ground"), "damage_taken_pct")))
            AddFactor(out, "Glacial Ground", pct);
    }

    void Forget(Player* player)
    {
        std::uint32_t worn;
        {
            std::lock_guard<std::mutex> guard(mutex);
            marks.erase(player->GetGUID().GetRawValue());
            worn = tremor[player->GetGUID().GetRawValue()];
            tremor.erase(player->GetGUID().GetRawValue());
        }
        if (worn)
            ControlImmunity::SetFearCharmStun(player, worn, false);
    }
} // namespace DC::Combat::Shaman::Earthbind
