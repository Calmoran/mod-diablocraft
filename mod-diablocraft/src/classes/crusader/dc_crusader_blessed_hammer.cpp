/*
 * Blessed Hammer and its five runes: the hammer's spiral round the Crusader, the hit it deals to each enemy it reaches,
 * and what each rune does about them (Burning Wrath's pools, Thunderstruck's arcs, Brute Force's slow and explosion,
 * Dominion's orbit). The dispatch is in dc_crusader.cpp.
 */

#include "dc_crusader_blessed_hammer.h"
#include "dc_crusader_common.h"
#include "../../combat/dc_item_powers.h"
#include "ObjectAccessor.h"
#include "Util.h"

#include <memory>
#include <set>

namespace DC::Combat::Crusader::BlessedHammer
{
    namespace
    {
        constexpr std::string_view Skill = "Blessed Hammer";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        double Tune(char const* name)
        {
            return DC::Tunables::Get("crusader", name);
        }

        // Burning Wrath's pools burning now, per Crusader: when each ends.
        std::mutex mutex;
        std::unordered_map<std::uint64_t, std::vector<std::uint64_t>> pools;

        // One tick of a pool. The ticks left bound the pool by themselves: the last one lands as the pool's seconds
        // end, so no clock test may stop it.
        void PoolTick(Player* player, std::uint32_t spellId, Position where, unsigned left, std::uint32_t intervalMs)
        {
            if (!player->IsInWorld() || !player->IsAlive() || !PoolFires(left))
                return;
            auto const pct = Numbers::Get(spellId, "damage_pct");
            for (Unit* enemy : Combat::Enemies(player, spellId, where, Tune("blessed_hammer_pool_radius_yards")))
                Combat::Strike(player, enemy, spellId, pct, true);
            if (PoolFires(PoolLeftAfter(left)))
                player->m_Events.AddEventAtOffset(
                    [player, spellId, where, left, intervalMs]
                    { PoolTick(player, spellId, where, PoolLeftAfter(left), intervalMs); },
                    std::chrono::milliseconds(intervalMs));
        }

        void LayPool(Player* player, std::uint32_t spellId, Unit* enemy)
        {
            double const seconds = Tune("blessed_hammer_pool_seconds"), tick = Tune("blessed_hammer_pool_tick_seconds");
            unsigned const ticks = PoolTicks(seconds, tick);
            if (!ticks)
                return;
            std::uint64_t const guid = player->GetGUID().GetRawValue(), now = Now(),
                                until = now + std::uint64_t(seconds * 1000);
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto& mine = pools[guid];
                std::erase_if(mine, [now](std::uint64_t end) { return end <= now; });
                if (!PoolRoom(mine.size(), std::size_t(Tune("blessed_hammer_pools_at_once"))))
                    return;
                mine.push_back(until);
            }
            auto const interval = std::uint32_t(tick * 1000 + 0.5);
            Position const where = enemy->GetPosition();
            // "take {damage_pct} weapon damage as Fire per second": the first tick comes a second in.
            player->m_Events.AddEventAtOffset([player, spellId, where, ticks, interval]
                                              { PoolTick(player, spellId, where, ticks, interval); },
                                              std::chrono::milliseconds(interval));
        }

        // One hammer in flight: where it started and which way the Crusader faced, how it was cast, and the enemies it
        // touches now.
        struct Hammer
        {
            std::uint32_t spellId = 0;
            Rune rune = Rune::None;
            Position center;
            double heading = 0, lifetime = 0, reach = 0, loops = 0, hitRadius = 0, pct = 0, step = 0;
            unsigned steps = 0, done = 0;
            bool connected = false;
            std::set<std::uint64_t> touching;
        };

        // What the rune does about an enemy the hammer has just hit.
        void Hit(Player* player, Hammer& hammer, Unit* enemy)
        {
            std::uint32_t const spellId = hammer.spellId;
            if (!Combat::Strike(player, enemy, spellId, hammer.pct))
                return;
            if (!hammer.connected)
            {
                hammer.connected = true;
                Combat::Connected(player, spellId, 1);
            }
            switch (hammer.rune)
            {
                case Rune::BurningWrath:
                    // "has a {proc_chance_pct} chance to scorch the ground over which it passes": a pool where it
                    // stands.
                    if (enemy->IsAlive() && roll_chance_f(float(Numbers::Num(spellId, "proc_chance_pct"))))
                        LayPool(player, spellId, enemy);
                    break;
                case Rune::BruteForce:
                {
                    // "Slows enemies it passes through and has a {proc_chance_pct} chance to explode on impact, dealing
                    // {damage_pct} weapon damage ... and Stunning enemies within {radius_yards} yards".
                    Slow(player, enemy, Tune("blessed_hammer_slow_pct"), Tune("blessed_hammer_slow_seconds"));
                    if (!enemy->IsAlive() || !roll_chance_f(float(Numbers::Num(spellId, "proc_chance_pct"))))
                        break;
                    double const stun = Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player);
                    auto const pct = Numbers::Own(spellId, "damage_pct");
                    for (Unit* near :
                         Combat::Enemies(player, spellId, enemy->GetPosition(), Numbers::Num(spellId, "radius_yards")))
                    {
                        Combat::Strike(player, near, spellId, pct);
                        Stun(player, near, stun);
                    }
                    break;
                }
                default:
                    break;
            }
        }

        // Thunderstruck: "occasionally arcs between you and the hammer ... dealing {damage_pct} weapon damage as
        // Lightning to enemies caught in the arcs": the enemies within the hit radius of the line from the Crusader to
        // the hammer.
        void Arc(Player* player, Hammer const& hammer, Position const& at)
        {
            auto const pct = Numbers::Own(hammer.spellId, "damage_pct");
            double const reach = player->GetExactDist2d(at.GetPositionX(), at.GetPositionY()) + hammer.hitRadius;
            for (Unit* enemy : Combat::Enemies(player, hammer.spellId, player->GetPosition(), reach))
                if (Touches(SegmentDistance(enemy->GetPositionX(), enemy->GetPositionY(), player->GetPositionX(),
                                            player->GetPositionY(), at.GetPositionX(), at.GetPositionY()),
                            hammer.hitRadius))
                    Combat::Strike(player, enemy, hammer.spellId, pct);
        }

        // One look: where the hammer is, who it has just reached, and the arc if one comes.
        void Look(Player* player, std::shared_ptr<Hammer> hammer)
        {
            if (!player->IsInWorld() || !player->IsAlive() || hammer->done >= hammer->steps)
                return;
            ++hammer->done;
            // Dominion: "The Hammer now orbits you as you move": the spiral turns about the Crusader's own place.
            Position const center = hammer->rune == Rune::Dominion ? player->GetPosition() : hammer->center;
            Offset const away =
                Orbit(hammer->done * hammer->step, hammer->lifetime, hammer->reach, hammer->loops, hammer->heading);
            Position const at(center.GetPositionX() + away.x, center.GetPositionY() + away.y, center.GetPositionZ());
            std::set<std::uint64_t> now;
            for (Unit* enemy : Combat::Enemies(player, hammer->spellId, at, hammer->hitRadius))
            {
                std::uint64_t const raw = enemy->GetGUID().GetRawValue();
                now.insert(raw);
                if (Enters(hammer->touching.count(raw) != 0, true))
                    Hit(player, *hammer, enemy);
            }
            hammer->touching = std::move(now);
            if (hammer->rune == Rune::Thunderstruck && roll_chance_f(float(Tune("blessed_hammer_arc_chance_pct"))))
                Arc(player, *hammer, at);
            if (hammer->done < hammer->steps)
                player->m_Events.AddEventAtOffset([player, hammer] { Look(player, hammer); },
                                                  std::chrono::milliseconds(std::uint64_t(hammer->step * 1000 + 0.5)));
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

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const&)
    {
        if (!player || !Is(spellId))
            return;
        auto hammer = std::make_shared<Hammer>();
        hammer->spellId = spellId;
        hammer->rune = RuneAt(spellId);
        hammer->center = player->GetPosition();
        hammer->heading = player->GetOrientation();
        // Limitless: "increase the damage of Blessed Hammer to {damage_pct} ... and its area of effect by
        // {radius_yards} yards".
        hammer->pct = hammer->rune == Rune::Limitless ? Numbers::Num(spellId, "damage_pct")
                                                      : Numbers::Num(BaseId(Skill), "damage_pct");
        hammer->reach = Reach(hammer->rune, Tune("blessed_hammer_reach_yards"),
                              hammer->rune == Rune::Limitless ? Numbers::Num(spellId, "radius_yards") : 0.0);
        hammer->lifetime =
            Lifetime(hammer->rune, Tune("blessed_hammer_seconds"), Tune("blessed_hammer_limitless_life_factor"));
        hammer->loops = Tune("blessed_hammer_loops");
        hammer->hitRadius = Tune("blessed_hammer_hit_radius_yards");
        hammer->step = Tune("blessed_hammer_step_seconds");
        hammer->steps = Steps(hammer->lifetime, hammer->step);
        // No hit radius, no life or no step: the hammer has nothing to hit with and nowhere to go.
        if (hammer->hitRadius <= 0 || !hammer->steps)
            return;
        player->m_Events.AddEventAtOffset([player, hammer] { Look(player, hammer); },
                                          std::chrono::milliseconds(std::uint64_t(hammer->step * 1000 + 0.5)));
    }
} // namespace DC::Combat::Crusader::BlessedHammer
