/*
 * Fist of the Heavens and its five runes: the explosion is the engine's (the ground area it resolves), and what follows
 * it is here: the bolts that arc outward, and each rune's cloud, fissures, zaps, knockback and slow. The dispatch is in
 * dc_crusader.cpp.
 */

#include "dc_crusader_fist_of_the_heavens.h"
#include "dc_crusader_common.h"
#include "dc_crusader_dot.h"
#include "dc_crusader_zone.h"
#include "../../combat/dc_movement_effects.h"

#include <algorithm>

namespace DC::Combat::Crusader::FistOfTheHeavens
{
    namespace
    {
        constexpr std::string_view Skill = "Fist of the Heavens";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        double Tune(char const* name)
        {
            return DC::Tunables::Get("crusader", name);
        }

        // The fissures burning now, per Crusader: where each is and when it ends (Fissure's arcs run between two of
        // them).
        struct Fissure
        {
            Position where;
            std::uint64_t until = 0;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, std::vector<Fissure>> fissures;

        // An enemy's place along a ray from `from` heading `heading`, and across it.
        void Along(Position const& from, double heading, Unit const* enemy, double& along, double& across)
        {
            double const dx = enemy->GetPositionX() - from.GetPositionX(),
                         dy = enemy->GetPositionY() - from.GetPositionY();
            along = dx * std::cos(heading) + dy * std::sin(heading);
            across = -dx * std::sin(heading) + dy * std::cos(heading);
        }

        // The bolts: `count` of them from the explosion, each flying `length` yards, every enemy on one struck for
        // `pct`. The width of a bolt is a tunable with no number yet: with none a bolt strikes nobody.
        std::vector<Unit*> Bolts(Player* player, std::uint32_t spellId, Position const& center, double first)
        {
            std::vector<Unit*> struck;
            unsigned const count = unsigned(Numbers::Num(spellId, "projectile_count"));
            double const length = Tune("fist_bolt_travel_yards"), width = Tune("fist_bolt_width_yards");
            auto const pct = Numbers::Get(spellId, "damage_pct", "bolt");
            if (width <= 0)
                return struck;
            std::vector<Unit*> around = Combat::Enemies(player, spellId, center, length);
            for (unsigned index = 0; index < count; ++index)
            {
                double const heading = BoltHeading(index, count, first);
                for (Unit* enemy : around)
                {
                    double along, across;
                    Along(center, heading, enemy, along, across);
                    if (OnBolt(along, across, length, width) && Combat::Strike(player, enemy, spellId, pct))
                        struck.push_back(enemy);
                }
            }
            return struck;
        }

        // Divine Well: "The holy bolts ... zap enemies within {radius_yards} yards as they travel": every enemy within
        // the radius of a bolt's ray, once for each bolt.
        void Zaps(Player* player, std::uint32_t spellId, Position const& center, double first)
        {
            unsigned const count = unsigned(Numbers::Num(spellId, "projectile_count"));
            double const length = Tune("fist_bolt_travel_yards"), radius = Numbers::Num(spellId, "radius_yards");
            auto const pct = Numbers::Own(spellId, "damage_pct");
            std::vector<Unit*> around = Combat::Enemies(player, spellId, center, length + radius);
            for (unsigned index = 0; index < count; ++index)
                for (Unit* enemy : around)
                {
                    double along, across;
                    Along(center, BoltHeading(index, count, first), enemy, along, across);
                    if (RayDistance(along, across, length) <= radius)
                        Combat::Strike(player, enemy, spellId, pct);
                }
        }

        // Fissure's arcs: "If there is another fissure nearby, lightning will arc between them dealing an additional
        // {damage_pct:arc} weapon damage": every tick while both burn, the enemies within a bolt's width of the line
        // between them.
        void ArcTick(Player* player, std::uint32_t spellId, Position a, Position b, unsigned left,
                     std::uint32_t intervalMs)
        {
            if (!player->IsInWorld() || !player->IsAlive() || left == 0)
                return;
            double const width = Tune("fist_bolt_width_yards"), heading = a.GetAngle(&b);
            double const length = std::hypot(b.GetPositionX() - a.GetPositionX(), b.GetPositionY() - a.GetPositionY());
            auto const pct = Numbers::Get(spellId, "damage_pct", "arc");
            for (Unit* enemy : Combat::Enemies(player, spellId, a, length + width))
            {
                double along, across;
                Along(a, heading, enemy, along, across);
                if (OnBolt(along, across, length, width))
                    Combat::Strike(player, enemy, spellId, pct, true);
            }
            if (left > 1)
                player->m_Events.AddEventAtOffset([player, spellId, a, b, left, intervalMs]
                                                  { ArcTick(player, spellId, a, b, left - 1, intervalMs); },
                                                  std::chrono::milliseconds(intervalMs));
        }

        void LayFissure(Player* player, std::uint32_t spellId, Position const& center)
        {
            double const seconds = Numbers::Num(spellId, "dot_duration_seconds"),
                         tick = Tune("fist_fissure_tick_seconds");
            unsigned const ticks = Dot::Ticks(seconds, tick);
            if (!ticks)
                return;
            // "{damage_pct:dot} weapon damage ... over {dot_duration_seconds} seconds to nearby enemies": a zone of
            // ticks.
            Zone::Lay(player, spellId, center, Tune("fist_fissure_radius_yards"),
                      Dot::TickPct(Numbers::Num(spellId, "damage_pct", "dot"), ticks), seconds, tick);
            std::uint64_t const guid = player->GetGUID().GetRawValue(), now = Now(),
                                until = now + std::uint64_t(seconds * 1000);
            std::vector<Fissure> near;
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto& mine = fissures[guid];
                std::erase_if(mine, [now](Fissure const& f) { return f.until <= now; });
                for (Fissure const& other : mine)
                    if (center.GetExactDist2d(other.where) <= Tune("fist_fissure_arc_yards"))
                        near.push_back(other);
                mine.push_back({center, until});
            }
            if (Tune("fist_bolt_width_yards") <= 0)
                return;
            auto const interval = std::uint32_t(tick * 1000 + 0.5);
            for (Fissure const& other : near)
            {
                unsigned const both = Dot::Ticks(double(std::min(until, other.until) - now) / 1000.0, tick);
                if (both)
                    player->m_Events.AddEventAtOffset([player, spellId, center, where = other.where, both, interval]
                                                      { ArcTick(player, spellId, center, where, both, interval); },
                                                      std::chrono::milliseconds(interval));
            }
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
        return Numbers::Get(spellId, "damage_pct", "explosion");
    }

    void Ground(Player* player, std::uint32_t spellId, Position const& center)
    {
        if (!player || !Is(spellId))
            return;
        Rune const rune = RuneAt(spellId);
        // The bolts leave the explosion evenly round the circle, the first toward where the Crusader aimed.
        double const first = player->GetAngle(&center);

        if (rune == Rune::Retribution)
        {
            // "Hurl a fist of Holy power that pierces through your enemies, dealing {damage_pct:hit} weapon damage":
            // the enemies on the line from the Crusader to the place, each struck for the hit.
            double const length = player->GetExactDist2d(center.GetPositionX(), center.GetPositionY()),
                         width = Tune("fist_bolt_width_yards");
            auto const pct = Numbers::Get(spellId, "damage_pct", "hit");
            if (width > 0)
                for (Unit* enemy : Combat::Enemies(player, spellId, player->GetPosition(), length + width))
                {
                    double along, across;
                    Along(player->GetPosition(), first, enemy, along, across);
                    if (OnBolt(along, across, length, width))
                        Combat::Strike(player, enemy, spellId, pct);
                }
        }

        std::vector<Unit*> const struck = Bolts(player, spellId, center, first);

        switch (rune)
        {
            case Rune::HeavensTempest:
                // "Summon a fiery storm that covers a {radius_yards} yard radius for {duration_seconds} seconds,
                // dealing {damage_pct} weapon damage as Fire every second to enemies who pass underneath it".
                Zone::Lay(player, spellId, center, Numbers::Num(spellId, "radius_yards"),
                          Numbers::Num(spellId, "damage_pct"), Numbers::Num(spellId, "duration_seconds"),
                          Tune("fist_tempest_tick_seconds"));
                break;
            case Rune::Reverberation:
                // "The bolt detonates with a shockwave on impact, causing all enemies hit to be knocked away from the
                // blast and Slowed by {slow_pct} for {slow_duration_seconds} seconds": every enemy a bolt struck. The
                // distance is a tunable with no number yet.
                for (Unit* enemy : struck)
                {
                    Slow(player, enemy, Numbers::Num(spellId, "slow_pct"),
                         Numbers::Num(spellId, "slow_duration_seconds"));
                    Abilities::Knockback(player, enemy, Tune("fist_knockback_yards"));
                }
                break;
            case Rune::Fissure:
                LayFissure(player, spellId, center);
                break;
            case Rune::DivineWell:
                Zaps(player, spellId, center, first);
                break;
            default:
                break;
        }
    }
} // namespace DC::Combat::Crusader::FistOfTheHeavens
