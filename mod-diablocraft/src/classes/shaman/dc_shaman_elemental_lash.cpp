/*
 * Elemental Lash and its five runes: Searing Lash's burn, Lava Surge's chance of a free Lava Burst, Stonewhip's push
 * and its extra Maelstrom against a crowd, Frost Lash's chill. The cast is the engine's cone (Thunder Lash's is a
 * longer one, its targeting row); the Maelstrom it generates is Maelstrom's (dc_shaman_maelstrom.cpp). The dispatch is
 * in dc_shaman.cpp.
 */

#include "dc_shaman_elemental_lash.h"
#include "dc_shaman_burning.h"
#include "dc_shaman_chill.h"
#include "dc_shaman_common.h"
#include "dc_shaman_effects.h"
#include "dc_shaman_free_lava_burst.h"
#include "../../combat/dc_movement_effects.h"
#include "../../combat/dc_periodic_strike.h"
#include "Random.h"
#include "Unit.h"

namespace DC::Combat::Shaman::ElementalLash
{
    namespace
    {
        constexpr std::string_view Skill = "Elemental Lash";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && std::string_view(row->skill) == Skill ? RuneOf(row->rune) : Rune::None;
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        auto const* row = Shells::FindAbility(spellId);
        return row && std::string_view(row->skill) == Skill;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        // Searing Lash states its hit and its burn apart; the plain rule would read the skill's number for the hit.
        if (!Is(spellId) || !HitIsTagged(RuneAt(spellId)))
            return std::nullopt;
        return Numbers::Num(spellId, "damage_pct", "hit");
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId)
    {
        if (!player || !target || !Is(spellId))
            return;
        switch (RuneAt(spellId))
        {
            case Rune::SearingLash:
            {
                // "... and makes enemies hit Burning for {damage_pct:dot} weapon damage as Fire over
                // {dot_duration_seconds} seconds."
                double const seconds = Numbers::Num(spellId, "dot_duration_seconds");
                Burning::Burn(player, target, spellId, Numbers::Num(spellId, "damage_pct", "dot"), seconds,
                              Tunables::Get("combat", "elemental_lash_burn_tick_seconds"));
                break;
            }
            case Rune::LavaSurge:
                // "Each enemy hit has a {proc_chance_pct} chance to make your next Lava Burst free (up to one proc per
                // cast)": the state is one, so a second proc of the same cast changes nothing.
                if (Procs(frand(0.0f, 1.0f), Numbers::Num(spellId, "proc_chance_pct")))
                    FreeLavaBurst::Grant(player);
                break;
            case Rune::Stonewhip:
                // "pushes enemies back {knockback_yards} yards (elites and bosses are immune)."
                if (Pushes(IsElite(target)))
                    Abilities::Knockback(player, target, Numbers::Num(spellId, "knockback_yards"));
                break;
            case Rune::FrostLash:
                // "Chills enemies hit by {chill_pct} for {chill_duration_seconds} seconds."
                Chill(player, target, Numbers::Num(spellId, "chill_pct"),
                      Numbers::Num(spellId, "chill_duration_seconds"));
                break;
            default:
                break;
        }
    }

    void Connected(Player* player, std::uint32_t spellId, unsigned enemies)
    {
        if (!player || RuneAt(spellId) != Rune::Stonewhip)
            return;
        // "Generates {gain_resource} extra Maelstrom when it hits {nearby_enemy_count} or more enemies."
        Gain(player, spellId,
             CrowdGain(enemies, Numbers::Num(spellId, "nearby_enemy_count"), Numbers::Num(spellId, "gain_resource")));
    }
} // namespace DC::Combat::Shaman::ElementalLash
