/*
 * Piranhas and its five runes. The skill is the engine's ground-aimed cast (a record and the sheet's numbers) that hits
 * nothing; here: the pool of piranhas (a periodic device of the shared ground-device piece) that hurts and amplifies
 * the damage of what stands in it, the Bogadile's bite and stun, Zombie Piranhas' longer leap, the Piranhado's pull,
 * Wave of Mutilation's wave and Frozen Piranhas' chill.
 */

#include "dc_witch_doctor_piranhas.h"
#include "dc_witch_doctor_common.h"
#include "dc_witch_doctor_effects.h"
#include "dc_witch_doctor_skill_passives.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_enemy_effects.h"
#include "../../combat/dc_ground_device.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_movement_effects.h"
#include "../../combat/dc_spell_numbers.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Position.h"
#include "Unit.h"

#include <chrono>
#include <functional>

namespace DC::Combat::WitchDoctor::Piranhas
{
    namespace
    {
        constexpr std::string_view Skill = "Piranhas";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        // The key a rune's pull device is kept under: apart from the pool, and no spell id.
        std::uint32_t PullKind()
        {
            return ~BaseId(Skill);
        }

        void Later(Player* player, std::uint32_t ms, std::function<void()> work)
        {
            if (!ms)
                work();
            else
                player->m_Events.AddEventAtOffset(std::move(work), std::chrono::milliseconds(ms));
        }

        // The Bogadile: "A giant bogadile emerges from the pool of water, Stuns, and bites a monster dealing
        // {damage_pct} weapon damage as Physical": after its spawn delay every enemy within its damage radius of the
        // pool's middle takes the bite and the stun.
        void Bite(Player* player, std::uint32_t spellId, Position const& center)
        {
            Later(player, std::uint32_t(Tune("piranhas_bogadile_delay_seconds") * 1000.0 + 0.5),
                  [player, spellId, center]
                  {
                      if (!player->IsAlive() || !player->IsInWorld())
                          return;
                      for (Unit* enemy :
                           Combat::Enemies(player, spellId, center, Tune("piranhas_bogadile_radius_yards")))
                          if (Combat::Strike(player, enemy, spellId, Numbers::Num(spellId, "damage_pct")))
                              Stun(player, enemy,
                                   Tune("piranhas_bogadile_stun_seconds") * ItemPowers::StunFactor(player));
                  });
        }

        // Piranhado: "Nearby enemies are periodically sucked into the tornado": a pulse of its own draws every enemy
        // within the vacuum radius to the pool's middle.
        void Vacuum(Player* player, std::uint32_t spellId, Position const& center, double life)
        {
            GroundDevice::Setup pull;
            pull.kind = PullKind();
            pull.record = spellId;
            pull.spec.mode = GroundDevice::Mode::Periodic;
            pull.spec.radiusYards = Tune("piranhas_vacuum_radius_yards");
            pull.spec.lifetimeMs = life * 1000.0;
            pull.spec.intervalMs = Tune("piranhas_pull_pulse_seconds") * 1000.0;
            pull.fire = [center](Player*, Position const&, std::vector<Unit*> const& enemies)
            {
                for (Unit* enemy : enemies)
                    if (Sucked(enemy->GetExactDist(&center), Tune("piranhas_vacuum_radius_yards")))
                        Abilities::Pull(enemy, center);
            };
            GroundDevice::Place(player, pull, center);
        }

        // The pool where the cast fell: every tick every enemy in it takes its share of the damage and the amplified
        // damage the skill gives, for its seconds.
        void Pool(Player* player, std::uint32_t spellId, Rune rune, Position const& center)
        {
            double const tick = Tune("piranhas_tick_seconds"),
                         life = rune == Rune::Piranhado ? Numbers::Num(spellId, "duration_seconds")
                                                        : Numbers::Num(spellId, "dot_duration_seconds"),
                         pct = TickPct(Numbers::Num(PoolTakesRuneElement(rune) ? spellId : BaseId(Skill), "damage_pct"),
                                       Numbers::Num(spellId, "dot_duration_seconds"), tick);
            std::uint32_t const striker = PoolTakesRuneElement(rune) ? spellId : BaseId(Skill);
            GroundDevice::Setup pool;
            pool.kind = BaseId(Skill);
            pool.record = spellId;
            pool.spec.mode = GroundDevice::Mode::Periodic;
            pool.spec.radiusYards =
                PoolReach(rune, Tune("piranhas_pool_radius_yards"), Tune("piranhas_leap_radius_yards"));
            pool.spec.lifetimeMs = life * 1000.0;
            pool.spec.intervalMs = tick * 1000.0;
            pool.fire = [spellId, striker, pct, rune](Player* owner, Position const&, std::vector<Unit*> const& enemies)
            {
                for (Unit* enemy : enemies)
                {
                    Combat::Strike(owner, enemy, striker, pct);
                    // "Affected enemies will also take {damage_taken_pct} increased damage": for at least the file's
                    // minimum after the last tick.
                    double const seconds = Passive::Skills::Lasting(owner, Tune("piranhas_debuff_seconds"));
                    EnemyEffects::Taken(enemy, spellId, Numbers::Num(spellId, "damage_taken_pct"), seconds);
                    // Frozen Piranhas: "chilling enemies for the entire duration".
                    if (rune == Rune::FrozenPiranhas)
                        Slow(owner, enemy, Tune("piranhas_frozen_chill_pct"), seconds);
                }
            };
            GroundDevice::Place(player, pool, center);
            if (rune == Rune::Piranhado)
                Vacuum(player, spellId, center, life);
            if (rune == Rune::Bogadile)
                Bite(player, spellId, center);
        }

        // Wave of Mutilation: "Turn each cast into a wave of piranhas that crash forward dealing {damage_pct} weapon
        // damage and causing all enemies affected to take {damage_taken_pct} increased damage for {duration_seconds}
        // seconds": each enemy the wave passes over is hit when the wave reaches it.
        void Crash(Player* player, std::uint32_t spellId, Position const& center)
        {
            Position const from = player->GetPosition();
            double const heading = from.GetAngle(center.GetPositionX(), center.GetPositionY()),
                         distance = Tune("piranhas_wave_distance_yards"), width = Tune("piranhas_wave_width_yards");
            for (Unit* enemy : Combat::Enemies(player, spellId, from, distance + width))
            {
                double const dx = enemy->GetPositionX() - from.GetPositionX(),
                             dy = enemy->GetPositionY() - from.GetPositionY(), ahead = Ahead(dx, dy, heading);
                if (!WaveCovers(ahead, Across(dx, dy, heading), distance, width))
                    continue;
                ObjectGuid const guid = enemy->GetGUID();
                Later(player,
                      WaveReachesMs(ahead, Tune("piranhas_wave_offset_yards"), Tune("piranhas_wave_length_yards"),
                                    Tune("piranhas_wave_yards_per_second")),
                      [player, spellId, guid]
                      {
                          Unit* hit = ObjectAccessor::GetUnit(*player, guid);
                          if (!player->IsAlive() || !player->IsInWorld() || !hit || !hit->IsAlive())
                              return;
                          if (Combat::Strike(player, hit, spellId, Numbers::Num(spellId, "damage_pct")))
                              EnemyEffects::Taken(hit, spellId, Numbers::Num(spellId, "damage_taken_pct"),
                                                  Numbers::Num(spellId, "duration_seconds"));
                      });
            }
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
        if (rune == Rune::WaveOfMutilation)
            Crash(player, spellId, center);
        else
            Pool(player, spellId, rune, center);
    }
} // namespace DC::Combat::WitchDoctor::Piranhas
