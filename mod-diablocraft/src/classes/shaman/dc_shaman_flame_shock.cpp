/*
 * Flame Shock and its five runes: the burn the base cast and Lava Shock leave, Lava Shock's eruption, Frost Shock's chill,
 * Earth Shock's stun, Static Shock's arcs and Primal Shock, which deals the Attunement's element and adds a small effect of
 * it. The cast is the engine's single-enemy spell; the Maelstrom it generates is Maelstrom's (dc_shaman_maelstrom.cpp). The
 * dispatch is in dc_shaman.cpp.
 */

#include "dc_shaman_flame_shock.h"
#include "dc_shaman_burning.h"
#include "dc_shaman_chill.h"
#include "dc_shaman_common.h"
#include "dc_shaman_earthquake.h"
#include "dc_shaman_effects.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_periodic_strike.h"
#include "ObjectGuid.h"
#include "Unit.h"

#include <algorithm>
#include <mutex>
#include <unordered_map>
#include <vector>

namespace DC::Combat::Shaman::FlameShock
{
    namespace
    {
        constexpr std::string_view Skill = "Flame Shock";

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

        double Tune(char const* name)
        {
            return Tunables::Get("combat", name);
        }

        // A strike this file starts is itself a hit of the skill and starts nothing.
        thread_local bool striking = false;

        struct Marked
        {
            ObjectGuid owner;
            std::uint64_t until = 0; // game time, ms
            double pct = 0;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, Marked> marks; // by the marked enemy

        // "... making the target Burning for another {damage_pct:dot} weapon damage as Fire over {dot_duration_seconds}
        // seconds": a burn of `totalPct` over `seconds`, and the enemy Burning for as long.
        void Burn(Player* player, Unit* target, std::uint32_t spellId, double totalPct, double seconds)
        {
            Burning::Burn(player, target, spellId, totalPct, seconds, Tune("flame_shock_burn_tick_seconds"));
        }

        // The skill's own burn.
        void BaseBurn(Player* player, Unit* target, std::uint32_t spellId)
        {
            Burn(player, target, spellId, Numbers::Num(spellId, "damage_pct", "dot"),
                 Numbers::Num(spellId, "dot_duration_seconds"));
        }

        void Strikes(Player* player, Unit* target, std::uint32_t spellId, double pct)
        {
            striking = true;
            Combat::Strike(player, target, spellId, pct);
            striking = false;
        }

        // Up to `count` enemies near `from`, the nearest first: the arcs of Static Shock and of a Lightning Primal Shock.
        void Arc(Player* player, Unit* from, std::uint32_t spellId, unsigned count, double pct)
        {
            std::vector<Unit*> near = Combat::Enemies(player, spellId, from->GetPosition(), Tune("flame_shock_arc_radius_yards"));
            near.erase(std::remove(near.begin(), near.end(), from), near.end());
            std::sort(near.begin(), near.end(),
                      [from](Unit* a, Unit* b) { return from->GetExactDist(a) < from->GetExactDist(b); });
            if (near.size() > count)
                near.resize(count);
            for (Unit* enemy : near)
                Strikes(player, enemy, spellId, pct);
        }

        void Mark(Player* player, Unit* target, double pct, double seconds)
        {
            Marked mark;
            mark.owner = player->GetGUID();
            mark.until = Now() + std::uint64_t(seconds * 1000.0);
            mark.pct = pct;
            std::lock_guard<std::mutex> guard(mutex);
            marks[target->GetGUID().GetRawValue()] = mark;
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        auto const* row = Shells::FindAbility(spellId);
        return row && std::string_view(row->skill) == Skill;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        if (!Is(spellId))
            return std::nullopt;
        switch (HitOf(RuneAt(spellId)))
        {
            case HitFrom::RuneOnly:
                return Numbers::Num(spellId, "damage_pct");
            case HitFrom::RuneHit:
                return Numbers::Num(spellId, "damage_pct", "hit");
            default:
                return Numbers::Num(BaseId(), "damage_pct", "hit");
        }
    }

    char const* Element(Player* player, std::uint32_t spellId)
    {
        // "Deals {damage_pct:hit} weapon damage as your Attuned element".
        return RuneAt(spellId) == Rune::PrimalShock ? Attunement::Current(player) : nullptr;
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId)
    {
        if (striking || !player || !target || !Is(spellId))
            return;
        Rune const rune = RuneAt(spellId);
        if (Burns(rune))
        {
            // Lava Shock: "If the target is already Burning, it erupts, dealing {damage_pct} weapon damage as Fire to all
            // enemies within {radius_yards} yards and making them Burning too (same burn as base Flame Shock)."
            bool const wasBurning = Burning::Is(player, target);
            BaseBurn(player, target, spellId);
            if (Erupts(rune, wasBurning))
                for (Unit* enemy : Combat::Enemies(player, spellId, target->GetPosition(), Numbers::Num(spellId, "radius_yards")))
                {
                    Strikes(player, enemy, spellId, Numbers::Num(spellId, "damage_pct"));
                    if (enemy->IsAlive())
                        BaseBurn(player, enemy, spellId);
                }
            return;
        }
        switch (rune)
        {
            case Rune::FrostShock:
            {
                // "Chills the target by {chill_pct} for {chill_duration_seconds} seconds. Generates {gain_resource} extra
                // Maelstrom against enemies that are already Chilled": the chill the enemy already carried counts.
                bool const chilled = Chilled(player, target);
                Chill(player, target, Numbers::Num(spellId, "chill_pct"), Numbers::Num(spellId, "chill_duration_seconds"));
                Gain(player, spellId, ChilledGain(chilled, Numbers::Num(spellId, "gain_resource")));
                break;
            }
            case Rune::EarthShock:
                // "Stuns the target for {stun_duration_seconds} seconds (elites and bosses are immune)."
                if (!IsElite(target))
                    Stun(player, target, Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player));
                // "Generates {generated_resource:new} Maelstrom instead of {generated_resource:base}, plus {gain_resource} more if the target
                // is inside your Earthquake."
                Gain(player, spellId, Earthquake::EarthShockGain(Earthquake::Inside(player, target), Numbers::Num(spellId, "gain_resource")));
                break;
            case Rune::StaticShock:
                // "... and arcs to {target_count} nearby enemies for {damage_pct:arc} weapon damage as Lightning."
                Arc(player, target, spellId, unsigned(Numbers::Num(spellId, "target_count")),
                    Numbers::Num(spellId, "damage_pct", "arc"));
                break;
            case Rune::PrimalShock:
            {
                std::optional<Small> const small = SmallOf(Attunement::Current(player));
                if (!small)
                    break;
                switch (*small)
                {
                    case Small::Burn:
                        // "Fire: Burning for {damage_pct:fire} weapon damage over {dot_duration_seconds} seconds."
                        Burn(player, target, spellId, Numbers::Num(spellId, "damage_pct", "fire"),
                             Numbers::Num(spellId, "dot_duration_seconds"));
                        break;
                    case Small::Chill:
                        // "Cold: Chill {chill_pct}."
                        Chill(player, target, Numbers::Num(spellId, "chill_pct"), Tune("flame_shock_primal_chill_seconds"));
                        break;
                    case Small::Mark:
                        // "Physical: the target takes {damage_taken_pct} more damage from you for {duration_seconds} seconds."
                        Mark(player, target, Numbers::Num(spellId, "damage_taken_pct"), Numbers::Num(spellId, "duration_seconds"));
                        break;
                    case Small::Arc:
                        // "Lightning: arcs to {target_count} enemy."
                        Arc(player, target, spellId, unsigned(Numbers::Num(spellId, "target_count")),
                            Tune("flame_shock_primal_arc_damage_pct"));
                        break;
                }
                break;
            }
            default:
                break;
        }
    }

    void Multipliers(Player* player, Unit* target, std::uint32_t, DC::Combat::Factors& out)
    {
        if (!player || !target)
            return;
        double pct = 0;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = marks.find(target->GetGUID().GetRawValue());
            if (found == marks.end())
                return;
            if (!Holds(Now(), found->second.until))
            {
                marks.erase(found);
                return;
            }
            if (found->second.owner == player->GetGUID())
                pct = found->second.pct;
        }
        if (double const bonus = MarkBonus(pct > 0, pct))
            AddFactor(out, "Primal Shock", bonus);
    }
} // namespace DC::Combat::Shaman::FlameShock
