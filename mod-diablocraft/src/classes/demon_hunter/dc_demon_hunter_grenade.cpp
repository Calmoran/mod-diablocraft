/*
 * Grenade and its five runes. The grenade is the engine's ground blast (a spell record and the sheet's numbers) that
 * hits every enemy within its radius of the point aimed at; here: Cold Grenade's cloud that chills and hurts over time,
 * Cluster Grenades' pulses over the larger radius, Grenade Cache's other grenades in a fan, Stun Grenade's chance to
 * stun. Tinkerer's Hatred is a sheet number the same code reads.
 */

#include "dc_demon_hunter_grenade.h"
#include "dc_demon_hunter_common.h"
#include "dc_demon_hunter_dot.h"
#include "dc_demon_hunter_effects.h"
#include "dc_demon_hunter_passives.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_spell_numbers.h"
#include "Player.h"
#include "Unit.h"
#include "Util.h"

#include <chrono>
#include <cmath>
#include <functional>
#include <mutex>
#include <unordered_map>

namespace DC::Combat::DemonHunter::Grenade
{
    namespace
    {
        constexpr std::string_view Skill = "Grenade";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        // The blast a grenade's hits are being dealt in: its middle and its radius. The engine's own hit runs between the aim and the
        // explosion (the point is kept for it by the Demon Hunter), the explosion's own strikes run inside a Scope.
        struct Blast
        {
            Position center;
            double radius = 0;
            bool on = false;
        };

        std::mutex mutex;
        std::unordered_map<std::uint64_t, Blast> blasts; // by Demon Hunter: the blast between its aim and its explosion
        thread_local Blast current;

        // The radius a grenade's blast reaches: the larger one of Cluster Grenades, else the record's own.
        double BlastRadius(std::uint32_t spellId)
        {
            return RuneAt(spellId) == Rune::ClusterGrenades ? Numbers::Num(spellId, "radius_yards")
                                                              : Combat::TargetRadius(spellId);
        }

        // Holds a blast as the current one for as long as it lives.
        struct Scope
        {
            Scope(Position const& center, double radius)
            {
                current = Blast{center, radius, true};
            }
            ~Scope()
            {
                current.on = false;
            }
            Scope(Scope const&) = delete;
            Scope& operator=(Scope const&) = delete;
        };

        unsigned Pulses()
        {
            return unsigned(Tune("grenade_cluster_pulses"));
        }

        void After(Player* player, double seconds, std::function<void()> work)
        {
            player->m_Events.AddEventAtOffset(std::move(work),
                                              std::chrono::milliseconds(std::uint32_t(seconds * 1000 + 0.5)));
        }

        // Cluster Grenades: "Throw cluster grenades that deal {damage_pct} weapon damage as Fire over a {radius_yards}
        // yard radius": the total shared by the pulses. The first pulse is the engine's hit within its own radius, so
        // here it reaches only the ring beyond; the later pulses reach the whole of the larger radius.
        void Cluster(Player* player, std::uint32_t spellId, Position const& center)
        {
            double const radius = Passive::GrenadeRadius(player, spellId, Numbers::Num(spellId, "radius_yards")),
                         inner = Combat::TargetRadius(spellId);
            double const pct = PulsePct(Numbers::Num(spellId, "damage_pct"), Pulses()),
                         gap = Tune("grenade_cluster_pulse_seconds");
            {
                Scope scope(center, radius);
                for (Unit* enemy : Combat::Enemies(player, spellId, center, radius))
                    if (enemy->GetExactDist(center) > inner)
                        Combat::Strike(player, enemy, spellId, pct);
            }
            for (unsigned pulse = 1; pulse < Pulses(); ++pulse)
                After(player, PulseAfter(pulse, gap),
                      [player, spellId, center, radius, pct]
                      {
                          if (!player->IsAlive() || !player->IsInWorld())
                              return;
                          Scope scope(center, radius);
                          for (Unit* enemy : Combat::Enemies(player, spellId, center, radius))
                              Combat::Strike(player, enemy, spellId, pct);
                      });
        }

        // Cold Grenade: "leaves a cloud that deals an additional {damage_pct:cloud} weapon damage as Cold over
        // {dot_duration_seconds} seconds to enemies who stand in the area and Chills them."
        void Cloud(Player* player, std::uint32_t spellId, Position const& center, unsigned left, double pct,
                   double tick)
        {
            if (!player->IsAlive() || !player->IsInWorld() || !left)
                return;
            for (Unit* enemy : Combat::Enemies(player, spellId, center, Passive::GrenadeRadius(player, spellId, Tune("grenade_cloud_radius_yards"))))
            {
                Combat::Strike(player, enemy, spellId, pct, true);
                // The chill lasts a little past the tick, so an enemy that walks out of the cloud is freed at once.
                Slow(player, enemy, Tune("grenade_cloud_chill_pct"), tick * 2);
            }
            if (left > 1)
                After(player, tick, [player, spellId, center, left, pct, tick]
                      { Cloud(player, spellId, center, left - 1, pct, tick); });
        }

        // Grenade Cache: "Throw out {projectile_count} grenades": the others land the same distance from the Demon
        // Hunter, fanned off the line to the point aimed at, and each explodes as the first does.
        void Fan(Player* player, std::uint32_t spellId, Position const& center)
        {
            Position const from = player->GetPosition();
            double const aim = std::atan2(center.GetPositionY() - from.GetPositionY(),
                                          center.GetPositionX() - from.GetPositionX()),
                         yards = from.GetExactDist2d(center.GetPositionX(), center.GetPositionY());
            auto const pct = Numbers::Own(spellId, "damage_pct");
            for (double degrees : FanOffsets(std::size_t(Numbers::Num(spellId, "projectile_count")),
                                             Tune("grenade_cache_spread_degrees")))
            {
                double const angle = aim + degrees * M_PI / 180.0;
                Position landing = center;
                landing.Relocate(from.GetPositionX() + std::cos(angle) * yards,
                                 from.GetPositionY() + std::sin(angle) * yards, center.GetPositionZ());
                Scope scope(landing, Combat::TargetRadius(spellId));
                for (Unit* enemy : Combat::Enemies(player, spellId, landing, Combat::TargetRadius(spellId)))
                    Combat::Strike(player, enemy, spellId, pct);
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
        if (RuneAt(spellId) == Rune::ClusterGrenades)
            return PulsePct(Numbers::Num(spellId, "damage_pct"), Pulses());
        return Numbers::Get(BaseId(Skill), "damage_pct");
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId)
    {
        // Stun Grenade: "Hurl a Lightning grenade that has a {proc_chance_pct} chance to Stun enemies for
        // {stun_duration_seconds} seconds": a roll for each enemy hit, the seconds stretched by the stun duration
        // items.
        if (player && target && RuneAt(spellId) == Rune::StunGrenade &&
            roll_chance_f(float(Numbers::Num(spellId, "proc_chance_pct"))))
            Stun(player, target, Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player));
    }

    void Aim(Player* player, std::uint32_t spellId, Position& center)
    {
        if (!player || !Is(spellId))
            return;
        Position const from = player->GetPosition();
        double const dx = center.GetPositionX() - from.GetPositionX(), dy = center.GetPositionY() - from.GetPositionY(),
                     aimed = std::hypot(dx, dy),
                     thrown = ThrownYards(aimed, RuneAt(spellId) == Rune::ClusterGrenades ? Tune("grenade_cluster_min_throw_yards") : Tune("grenade_min_throw_yards"));
        if (thrown != aimed)
        {
            // Aimed at their own feet, the Demon Hunter throws the way they face.
            double const angle = aimed > 0 ? std::atan2(dy, dx) : player->GetOrientation();
            center.Relocate(from.GetPositionX() + std::cos(angle) * thrown,
                            from.GetPositionY() + std::sin(angle) * thrown, center.GetPositionZ());
        }
        // The engine's hit follows: it is dealt in this blast, until the explosion takes it away.
        std::lock_guard<std::mutex> guard(mutex);
        blasts[player->GetGUID().GetRawValue()] = Blast{center, BlastRadius(spellId), true};
    }

    void Ground(Player* player, std::uint32_t spellId, Position const& center)
    {
        if (!player)
            return;
        if (Is(spellId))
        {
            // The explosion is here: the engine's hits are done, so what is kept for them goes (a cloud's ticks are no part of the blast).
            std::lock_guard<std::mutex> guard(mutex);
            blasts.erase(player->GetGUID().GetRawValue());
        }
        switch (RuneAt(spellId))
        {
            case Rune::ClusterGrenades:
                Cluster(player, spellId, center);
                break;
            case Rune::ColdGrenade:
            {
                double const tick = Tune("grenade_cloud_tick_seconds"),
                             seconds = Numbers::Num(spellId, "dot_duration_seconds");
                unsigned const ticks = Dot::Ticks(seconds, tick);
                if (ticks)
                    After(player, tick,
                          [player, spellId, center, ticks, tick,
                           pct = Dot::TickPct(Numbers::Num(spellId, "damage_pct", "cloud"), ticks)]
                          { Cloud(player, spellId, center, ticks, pct, tick); });
                break;
            }
            case Rune::GrenadeCache:
                Fan(player, spellId, center);
                break;
            default:
                break;
        }
    }

    void Multipliers(Player* player, Unit* target, std::uint32_t spellId, Factors& out)
    {
        if (!player || !target || !Is(spellId))
            return;
        Blast blast = current;
        if (!blast.on)
        {
            std::lock_guard<std::mutex> guard(mutex);
            if (auto const found = blasts.find(player->GetGUID().GetRawValue()); found != blasts.end())
                blast = found->second;
        }
        if (!blast.on)
            return;
        // "damage falls off to {edge}% at the blast's edge": a straight line from all of it at the middle.
        double const kept = KeptPct(target->GetExactDist(&blast.center), blast.radius, Tune("grenade_edge_damage_pct"));
        if (kept < 100.0)
            AddFactor(out, "Grenade falloff", kept - 100.0);
    }
} // namespace DC::Combat::DemonHunter::Grenade
