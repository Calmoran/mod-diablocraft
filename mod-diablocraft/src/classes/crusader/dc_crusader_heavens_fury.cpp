/*
 * Heaven's Fury and its five runes. The cast is aimed at the ground (skill_targeting.csv: 100 yards, 8 yards of area)
 * and deals no hit of its own: the ray is the ticks of a ground zone, and what each rune does is here. The dispatch is
 * in dc_crusader.cpp.
 */

#include "dc_crusader_heavens_fury.h"
#include "dc_crusader_common.h"
#include "dc_crusader_hold.h"
#include "dc_crusader_zone.h"

#include <cmath>

namespace DC::Combat::Crusader::HeavensFury
{
    namespace
    {
        constexpr std::string_view Skill = "Heaven's Fury";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        double Tune(char const* name)
        {
            return DC::Tunables::Get("crusader", name);
        }

        // A ray of `spellId`'s school at `where`: `totalPct` of weapon damage over `seconds` to the enemies within
        // `radius`.
        void Ray(Player* player, std::uint32_t spellId, Position const& where, double radius, double totalPct,
                 double seconds)
        {
            double const tick = Tune("heavens_fury_tick_seconds");
            Zone::Lay(player, spellId, where, radius, PctPerTick(totalPct, seconds, tick), seconds, tick);
        }

        // The area the skill's ray covers: Ascendancy's own radius, else the one the cast names.
        double Footprint(std::uint32_t spellId)
        {
            return Numbers::Own(spellId, "radius_yards").value_or(Combat::TargetRadius(spellId));
        }

        // Fires of Heaven: one hit on every enemy in the beam that leaves the Crusader toward `center`.
        void Beam(Player* player, std::uint32_t spellId, Position const& center)
        {
            Position const from = player->GetPosition();
            double const heading = from.GetAbsoluteAngle(&center);
            double const distance = Tune("heavens_fury_fires_distance_yards");
            double const radius = Tune("heavens_fury_fires_radius_yards");
            unsigned hits = 0;
            for (Unit* enemy : Combat::Enemies(player, spellId, from, distance + radius))
            {
                double const dx = enemy->GetPositionX() - from.GetPositionX();
                double const dy = enemy->GetPositionY() - from.GetPositionY();
                if (InBeam(Along(dx, dy, heading), Across(dx, dy, heading), distance, radius) &&
                    Combat::Strike(player, enemy, spellId, Numbers::Num(spellId, "damage_pct")))
                    ++hits;
            }
            if (hits)
                Combat::Connected(player, spellId, hits);
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        if (!Is(spellId))
            return std::nullopt;
        return 0.0;
    }

    void Ground(Player* player, std::uint32_t spellId, Position const& center)
    {
        if (!player || !Is(spellId))
            return;
        Rune const rune = RuneAt(spellId);
        std::uint32_t const base = BaseId(Skill);
        double const footprint = Footprint(spellId);
        if (KeepsBaseRay(rune))
            // "deals {damage_pct} weapon damage as Holy over {dot_duration_seconds} seconds to all enemies caught
            // within it."
            Ray(player, spellId, center, Footprint(base), Numbers::Num(base, "damage_pct"),
                Numbers::Num(base, "dot_duration_seconds"));
        switch (rune)
        {
            case Rune::Ascendancy:
                // "The ray ... grows to encompass {radius_yards} yards, dealing {damage_pct} weapon damage ... over
                // {dot_duration_seconds} seconds."
                Ray(player, spellId, center, footprint, Numbers::Num(spellId, "damage_pct"),
                    Numbers::Num(spellId, "dot_duration_seconds"));
                break;
            case Rune::BlessedGround:
                // "The ground touched by the ray becomes blessed, ... dealing {damage_pct} weapon damage over
                // {dot_duration_seconds} seconds to enemies who walk through."
                Ray(player, spellId, center, footprint, Numbers::Num(spellId, "damage_pct"),
                    Numbers::Num(spellId, "dot_duration_seconds"));
                break;
            case Rune::SplitFury:
            {
                // "The ray splits into {spawn_count} smaller beams, each dealing {damage_pct} weapon damage as Holy
                // over {dot_duration_seconds} seconds": a ring of beams inside the ray's area.
                unsigned const count = unsigned(Numbers::Num(spellId, "spawn_count"));
                double const beam = Tune("heavens_fury_split_beam_radius_yards");
                double const ring = RingYards(footprint, beam);
                double const start = player->GetPosition().GetAbsoluteAngle(&center);
                for (unsigned i = 0; i < count; ++i)
                {
                    double const heading = BeamHeading(i, count, start);
                    Position at = center;
                    at.Relocate(center.GetPositionX() + float(std::cos(heading) * ring),
                                center.GetPositionY() + float(std::sin(heading) * ring), center.GetPositionZ());
                    Ray(player, spellId, at, beam, Numbers::Num(spellId, "damage_pct"),
                        Numbers::Num(spellId, "dot_duration_seconds"));
                }
                break;
            }
            case Rune::ThouShaltNotPass:
                // "Ground touched by the ray pulses with power for {duration_seconds} seconds, stopping enemies who try
                // to pass over it."
                Hold::Place(player, spellId, center, footprint, Numbers::Num(spellId, "duration_seconds"),
                           Tune("heavens_fury_barrier_check_seconds"));
                break;
            case Rune::FiresOfHeaven:
                Beam(player, spellId, center);
                break;
            default:
                break;
        }
    }
} // namespace DC::Combat::Crusader::HeavensFury
