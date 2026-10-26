/*
 * Army of the Dead and its five runes. The engine hits nothing; the army strikes after the power's payload delay: three blasts
 * on the place for the skill and Death Valley (which also draws the enemies in), hands that stay and strike for Blighted Grasp,
 * waves along a line for Frozen Army, attacks on random enemies for Unconventional Warfare, ticks around the Necromancer for
 * Dead Storm, which takes Life.
 */

#include "dc_necromancer_army_of_the_dead.h"
#include "dc_necromancer_army_of_the_dead_math.h"
#include "dc_necromancer_common.h"

#include "Random.h"

#include <chrono>
#include <cmath>
#include <utility>
#include <vector>

namespace DC::Combat::Necromancer::ArmyOfTheDead
{
    namespace
    {
        constexpr std::string_view Skill = "Army of the Dead";

        double Tune(char const* name)
        {
            return DC::Tunables::Get("necromancer", name);
        }

        unsigned Count(char const* name)
        {
            return unsigned(std::max(0.0, Tune(name)));
        }

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        // Runs `act` on the player `seconds` from now.
        template <class Act>
        void After(Player* player, double seconds, Act act)
        {
            if (seconds <= 0)
                act();
            else
                player->m_Events.AddEventAtOffset(std::move(act), std::chrono::milliseconds(std::uint32_t(seconds * 1000.0 + 0.5)));
        }

        // Every living enemy the caster may hit within `radius` of `at`, struck for `pct`.
        void Blast(Player* player, std::uint32_t spellId, Position const& at, double radius, double pct,
                   std::vector<Unit*> const* only = nullptr)
        {
            if (!player->IsInWorld() || !player->IsAlive())
                return;
            unsigned hit = 0;
            for (Unit* enemy : only ? *only : Combat::Enemies(player, spellId, at, radius))
                if (enemy->IsAlive() && Combat::Strike(player, enemy, spellId, pct))
                    ++hit;
            if (hit)
                Combat::Connected(player, spellId, hit);
        }

        // The skill and Death Valley: "dealing {damage_pct} weapon damage ... in a {radius_yards} yard radius", in the power's
        // number of blasts a short time apart, after its payload delay.
        void Blasts(Player* player, std::uint32_t spellId, Position const& center)
        {
            unsigned const hits = Count("army_hits");
            double const radius = Numbers::Num(spellId, "radius_yards");
            double const pct = Share(Numbers::Num(spellId, "damage_pct"), hits);
            for (unsigned i = 0; i < hits; ++i)
                After(player, Tune("army_payload_delay_seconds") + i * Tune("army_blast_gap_seconds"),
                      [player, spellId, center, radius, pct] { Blast(player, spellId, center, radius, pct); });
        }

        // Death Valley: "knocks all affected enemies towards the center": every step the enemies outside the closing radius
        // are drawn in to it.
        void Pull(Player* player, std::uint32_t spellId, Position const& center)
        {
            double const start = Tune("death_valley_start_radius_yards"), end = Tune("death_valley_end_radius_yards"),
                         size = Tune("death_valley_segment_yards");
            unsigned const steps = PullSteps(start, end, size);
            for (unsigned step = 1; step <= steps; ++step)
                After(player, OffsetSeconds(step, Tune("death_valley_seconds"), steps),
                      [player, spellId, center, start, end, size, step]
                      {
                          double const radius = PullRadius(step, start, end, size);
                          for (Unit* enemy : Combat::Enemies(player, spellId, center, start))
                          {
                              double const distance = enemy->GetExactDist2d(center);
                              if (!Drawn(distance, radius) || distance <= 0)
                                  continue;
                              double const share = radius / distance;
                              enemy->NearTeleportTo(float(center.GetPositionX() + (enemy->GetPositionX() - center.GetPositionX()) * share),
                                                    float(center.GetPositionY() + (enemy->GetPositionY() - center.GetPositionY()) * share),
                                                    enemy->GetPositionZ(), enemy->GetOrientation());
                          }
                      });
        }

        // Blighted Grasp: "Skeletal hands raise from the ground damaging enemies within {radius_yards} yards ... Lasts
        // {duration_seconds} seconds": the power's hits over the duration.
        void Hands(Player* player, std::uint32_t spellId, Position const& center)
        {
            unsigned const hits = Count("blighted_grasp_hits");
            double const radius = Numbers::Num(spellId, "radius_yards");
            double const pct = Share(Numbers::Num(spellId, "damage_pct"), hits);
            for (unsigned i = 0; i < hits; ++i)
                After(player, Tune("army_payload_delay_seconds") + OffsetSeconds(i, Numbers::Num(spellId, "duration_seconds"), hits),
                      [player, spellId, center, radius, pct] { Blast(player, spellId, center, radius, pct); });
        }

        // Frozen Army: "pummel all enemies in a line": waves along the line from the Necromancer through the place aimed at.
        void Line(Player* player, std::uint32_t spellId, Position const& center)
        {
            double dx = center.GetPositionX() - player->GetPositionX(), dy = center.GetPositionY() - player->GetPositionY();
            double const reach = std::sqrt(dx * dx + dy * dy);
            if (reach < 0.01)
            {
                dx = std::cos(player->GetOrientation());
                dy = std::sin(player->GetOrientation());
            }
            else
            {
                dx /= reach;
                dy /= reach;
            }
            Position const from = player->GetPosition();
            double const length = Tune("frozen_army_line_length_yards"), width = Tune("frozen_army_line_width_yards");
            unsigned const waves = Count("frozen_army_waves");
            double const pct = Share(Numbers::Num(spellId, "damage_pct"), waves);
            for (unsigned i = 0; i < waves; ++i)
                After(player, Tune("army_payload_delay_seconds") + OffsetSeconds(i, Tune("frozen_army_seconds"), waves),
                      [player, spellId, from, dx, dy, length, width, pct]
                      {
                          std::vector<Unit*> onLine;
                          for (Unit* enemy : Combat::Enemies(player, spellId, from, length + width))
                              if (OnLine(from.GetPositionX(), from.GetPositionY(), dx, dy, enemy->GetPositionX(), enemy->GetPositionY(),
                                         length, width))
                                  onLine.push_back(enemy);
                          Blast(player, spellId, from, 0, pct, &onLine);
                      });
        }

        // Unconventional Warfare: "attack random targets for {damage_pct} total weapon damage ... over {dot_duration_seconds}
        // seconds": the power's attacks, each on an enemy chosen at random within its search radius of the place.
        void Random(Player* player, std::uint32_t spellId, Position const& center)
        {
            unsigned const attacks = Count("unconventional_warfare_attacks");
            double const pct = Share(Numbers::Num(spellId, "damage_pct"), attacks);
            for (unsigned i = 0; i < attacks; ++i)
                After(player, Tune("unconventional_warfare_delay_seconds") + OffsetSeconds(i, Numbers::Num(spellId, "dot_duration_seconds"), attacks),
                      [player, spellId, center, pct]
                      {
                          auto const enemies = Combat::Enemies(player, spellId, center, Tune("unconventional_warfare_radius_yards"));
                          if (enemies.empty())
                              return;
                          std::vector<Unit*> one{enemies[urand(0, uint32(enemies.size() - 1))]};
                          Blast(player, spellId, center, 0, pct, &one);
                      });
        }
    } // namespace

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) ? std::optional<double>(0.0) : std::nullopt;
    }

    void Casting(Player* player, std::uint32_t spellId)
    {
        // "Cost: 20% health" (Dead Storm).
        if (player && RuneAt(spellId) == Rune::DeadStorm)
            SpendLife(player, Tune("dead_storm_life_cost_pct"));
    }

    void Ground(Player* player, std::uint32_t spellId, Position const& center)
    {
        if (!player || !RowOf(spellId, Skill))
            return;
        switch (RuneAt(spellId))
        {
            case Rune::BlightedGrasp:
                Hands(player, spellId, center);
                break;
            case Rune::FrozenArmy:
                Line(player, spellId, center);
                break;
            case Rune::UnconventionalWarfare:
                Random(player, spellId, center);
                break;
            case Rune::DeathValley:
                Pull(player, spellId, center);
                Blasts(player, spellId, center);
                break;
            case Rune::DeadStorm:
            {
                // "Raise a storm of the dead that surround you damaging enemies for {damage_pct} weapon damage ... over
                // {dot_duration_seconds} seconds": the power's ticks around the Necromancer, after its delay.
                unsigned const ticks = Count("dead_storm_ticks");
                double const pct = Share(Numbers::Num(spellId, "damage_pct"), ticks);
                for (unsigned i = 0; i < ticks; ++i)
                    After(player, Tune("dead_storm_delay_seconds") + OffsetSeconds(i, Numbers::Num(spellId, "dot_duration_seconds"), ticks),
                          [player, spellId, pct]
                          { Blast(player, spellId, player->GetPosition(), Tune("dead_storm_radius_yards"), pct); });
                break;
            }
            default:
                Blasts(player, spellId, center);
                break;
        }
    }
} // namespace DC::Combat::Necromancer::ArmyOfTheDead
