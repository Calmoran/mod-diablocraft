/*
 * Acid Cloud and its five runes. The skill is the engine's ground-aimed cast (a record and the sheet's numbers) that
 * hits nothing; here: the impact that lands a moment after the cast, the pool of acid (a periodic device of the shared
 * ground-device piece) that hurts what stays in it, Corpse Bomb's explosion, Acid Rain's outer ring, Lob Blob Bomb's
 * slime, Slow Burn's frost and Kiss of Death's cone.
 */

#include "dc_witch_doctor_acid_cloud.h"
#include "dc_witch_doctor_common.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_ground_device.h"
#include "../../combat/dc_spell_numbers.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Position.h"
#include "Unit.h"

#include <chrono>
#include <functional>

namespace DC::Combat::WitchDoctor::AcidCloud
{
    namespace
    {
        constexpr std::string_view Skill = "Acid Cloud";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        void Later(Player* player, std::uint32_t ms, std::function<void()> work)
        {
            if (!ms)
                work();
            else
                player->m_Events.AddEventAtOffset(std::move(work), std::chrono::milliseconds(ms));
        }

        std::uint32_t Millis(double seconds)
        {
            return std::uint32_t(seconds * 1000.0 + 0.5);
        }

        // The impact's damage: the skill's initial hit; Corpse Bomb's own explosion; Kiss of Death's own initial hit.
        double ImpactPct(std::uint32_t spellId, Rune rune)
        {
            return rune == Rune::CorpseBomb ? Numbers::Num(spellId, "damage_pct")
                                            : Numbers::Num(spellId, "damage_pct", "initial");
        }

        // What the pool (or the cone's cloud) deals over its seconds: the skill's, Lob Blob Bomb's and Slow Burn's own
        // totals, Kiss of Death's own.
        double PoolPct(std::uint32_t spellId, Rune rune)
        {
            return rune == Rune::LobBlobBomb || rune == Rune::SlowBurn ? Numbers::Num(spellId, "damage_pct")
                                                                       : Numbers::Num(spellId, "damage_pct", "dot");
        }

        std::uint32_t PoolRecord(std::uint32_t spellId, Rune rune)
        {
            return PoolTakesRuneElement(rune) ? spellId : BaseId(Skill);
        }

        // Every enemy in the band of the impact at `center` takes `pct`.
        void Burst(Player* player, std::uint32_t spellId, Position const& center, double inner, double outer,
                   double pct)
        {
            if (!player->IsAlive() || !player->IsInWorld())
                return;
            Rune const rune = RuneAt(spellId);
            std::uint32_t const striker = ImpactTakesRuneElement(rune) ? spellId : BaseId(Skill);
            for (Unit* enemy : Combat::Enemies(player, spellId, center, outer))
                if (InBand(enemy->GetExactDist(&center), inner, outer))
                    Combat::Strike(player, enemy, striker, pct);
        }

        // The pool of acid where the impact fell: it arms when the impact lands and hurts every enemy in it each tick
        // for its seconds. Lob Blob Bomb's slime is a pool that is wider and lasts longer.
        void Pool(Player* player, std::uint32_t spellId, Rune rune, Position const& center, double delaySeconds)
        {
            double const seconds = Numbers::Num(spellId, "dot_duration_seconds"),
                         tick = Tune("acid_cloud_tick_seconds");
            double const pct = TickPct(PoolPct(spellId, rune), seconds, tick);
            std::uint32_t const striker = PoolRecord(spellId, rune);
            bool const slime = rune == Rune::LobBlobBomb;
            GroundDevice::Setup pool;
            pool.kind = BaseId(Skill);
            pool.record = spellId;
            pool.spec.mode = GroundDevice::Mode::Periodic;
            pool.spec.radiusYards = Tune(slime ? "acid_cloud_slime_radius_yards" : "acid_cloud_pool_radius_yards");
            pool.spec.armMs = delaySeconds * 1000.0;
            pool.spec.lifetimeMs = (delaySeconds + seconds) * 1000.0;
            pool.spec.intervalMs = tick * 1000.0;
            pool.spec.most = std::size_t(Tune(slime ? "acid_cloud_max_slimes" : "acid_cloud_max_pools"));
            pool.fire = [striker, pct](Player* owner, Position const&, std::vector<Unit*> const& enemies)
            {
                for (Unit* enemy : enemies)
                    Combat::Strike(owner, enemy, striker, pct);
            };
            GroundDevice::Place(player, pool, center);
        }

        // Kiss of Death: the cloud's ticks over the cone, which stays where it was spat.
        void CloudTick(Player* player, std::uint32_t spellId, Position const& from, double heading, unsigned left,
                       double pct)
        {
            if (!left || !player->IsAlive() || !player->IsInWorld())
                return;
            double const length = Tune("acid_cloud_barf_range_yards"), degrees = Tune("acid_cloud_barf_angle_degrees");
            for (Unit* enemy : Combat::Enemies(player, spellId, from, length))
                if (InCone(enemy->GetPositionX() - from.GetPositionX(), enemy->GetPositionY() - from.GetPositionY(),
                           heading, length, degrees))
                    Combat::Strike(player, enemy, PoolRecord(spellId, Rune::KissOfDeath), pct);
            Later(player, Millis(Tune("acid_cloud_tick_seconds")), [player, spellId, from, heading, left, pct]
                  { CloudTick(player, spellId, from, heading, left - 1, pct); });
        }

        // Kiss of Death: "Spit a cloud of acid that deals {damage_pct:initial} weapon damage as Poison, followed by
        // {damage_pct:dot} weapon damage as Poison over {dot_duration_seconds} seconds": a cone from the Witch Doctor
        // toward the aim.
        void Spit(Player* player, std::uint32_t spellId, Rune rune, Position const& center)
        {
            Position const from = player->GetPosition();
            double const heading = from.GetAngle(center.GetPositionX(), center.GetPositionY());
            double const length = Tune("acid_cloud_barf_range_yards"), degrees = Tune("acid_cloud_barf_angle_degrees");
            double const delay =
                ImpactDelaySeconds(rune, Tune("acid_cloud_impact_delay_seconds"),
                                   Tune("acid_cloud_corpse_delay_seconds"), Tune("acid_cloud_barf_delay_seconds"));
            double const seconds = Numbers::Num(spellId, "dot_duration_seconds"),
                         tick = Tune("acid_cloud_tick_seconds");
            double const impact = ImpactPct(spellId, rune), each = TickPct(PoolPct(spellId, rune), seconds, tick);
            unsigned const ticks = PeriodicStrike::Ticks(seconds, tick);
            Later(player, Millis(delay),
                  [player, spellId, from, heading, length, degrees, impact, each, ticks]
                  {
                      if (!player->IsAlive() || !player->IsInWorld())
                          return;
                      for (Unit* enemy : Combat::Enemies(player, spellId, from, length))
                          if (InCone(enemy->GetPositionX() - from.GetPositionX(),
                                     enemy->GetPositionY() - from.GetPositionY(), heading, length, degrees))
                              Combat::Strike(player, enemy, spellId, impact);
                      Later(player, Millis(Tune("acid_cloud_tick_seconds")),
                            [player, spellId, from, heading, ticks, each]
                            { CloudTick(player, spellId, from, heading, ticks, each); });
                  });
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        return Is(spellId) ? std::optional<double>(0.0) : std::nullopt;
    }

    void Ground(Player* player, std::uint32_t spellId, Position const& center)
    {
        if (!player || !Is(spellId))
            return;
        Rune const rune = RuneAt(spellId);
        if (rune == Rune::KissOfDeath)
        {
            Spit(player, spellId, rune, center);
            return;
        }
        double const delay =
            ImpactDelaySeconds(rune, Tune("acid_cloud_impact_delay_seconds"), Tune("acid_cloud_corpse_delay_seconds"),
                               Tune("acid_cloud_barf_delay_seconds"));
        double const inner = Tune("acid_cloud_impact_radius_yards"), pct = ImpactPct(spellId, rune);
        Later(player, Millis(delay), [player, spellId, center, inner, pct] { Burst(player, spellId, center, -1.0, inner, pct); });
        // Acid Rain: "Increase the initial area of effect of Acid Cloud to {radius_yards} yards": the outer ring takes
        // the impact a little after the first.
        if (rune == Rune::AcidRain)
            Later(player, Millis(Tune("acid_cloud_splash_delay_seconds")),
                  [player, spellId, center, inner, pct]
                  { Burst(player, spellId, center, inner, Numbers::Num(spellId, "radius_yards"), pct); });
        Pool(player, spellId, rune, center, delay);
    }
} // namespace DC::Combat::WitchDoctor::AcidCloud
