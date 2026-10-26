/*
 * Spike Trap and its five runes. The cast is the engine's ground-aimed spell (a record and the sheet's numbers) that
 * hits nothing; here: the trap laid at the point as a command device of the shared ground-device piece (dormant until
 * another Hatred spender detonates every trap in a chain reaction), Scatter's two traps, Impaling Spines' immobilize on
 * laying, Echoing Blast's slow and Lightning Rod's chain. The piece counts the traps, arms them, ends their time and
 * takes them away.
 */

#include "dc_demon_hunter_spike_trap.h"
#include "dc_demon_hunter_common.h"
#include "dc_demon_hunter_effects.h"
#include "dc_demon_hunter_passives.h"
#include "../dc_classes.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_ground_device.h"
#include "../../combat/dc_spell_numbers.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Position.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <chrono>

namespace DC::Combat::DemonHunter::SpikeTrap
{
    namespace
    {
        constexpr std::string_view Skill = "Spike Trap";

        // The place of a trap in the chain reaction that is going off: the traps fire in the order they were laid, a
        // gap apart.
        thread_local unsigned explosionOrder = 0;

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        // A skill that costs Hatred: the record's Energy cost, or the start the module pays.
        bool CostsHatred(std::uint32_t spellId)
        {
            SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId);
            return (info && info->PowerType == POWER_ENERGY && info->ManaCost > 0) ||
                   Numbers::Get(spellId, "cost_resource", "initial").value_or(0) > 0;
        }

        // The rune of the Spike Trap on the Demon Hunter's bar: the one a Hatred generator is asked about.
        Rune SlottedRune(Player* player)
        {
            for (Classes::Slot const& slot : Classes::Bar(player))
                if (Is(slot.spellId))
                    return RuneAt(slot.spellId);
            return Rune::None;
        }

        void Later(Player* player, std::uint32_t ms, std::function<void()> work)
        {
            if (!ms)
                work();
            else
                player->m_Events.AddEventAtOffset(std::move(work), std::chrono::milliseconds(ms));
        }

        // One trap going off at `at`: every enemy in its blast takes the rune's hit, a gap after the trap before it.
        void Explode(Player* player, std::uint32_t spellId, Position const& at, std::vector<Unit*> const& enemies)
        {
            Rune const rune = RuneAt(spellId);
            std::uint32_t const delay = ExplosionDelayMs(explosionOrder++, Tune("spike_trap_explosion_gap_seconds"));
            double const pct =
                rune == Rune::Scatter ? Tune("spike_trap_scatter_damage_pct") : Numbers::Num(spellId, "damage_pct");
            std::vector<ObjectGuid> guids;
            if (rune == Rune::LightningRod)
            {
                std::vector<double> distances;
                for (Unit* enemy : enemies)
                    distances.push_back(enemy->GetExactDist(&at));
                for (std::size_t index : Chain(distances, Numbers::Num(spellId, "radius_yards", "chain"),
                                               unsigned(Numbers::Num(spellId, "target_count"))))
                    guids.push_back(enemies[index]->GetGUID());
            }
            else
                for (Unit* enemy : enemies)
                    guids.push_back(enemy->GetGUID());
            Later(player, delay,
                  [player, spellId, rune, pct, guids]
                  {
                      if (!player->IsAlive() || !player->IsInWorld())
                          return;
                      for (ObjectGuid guid : guids)
                      {
                          Unit* enemy = ObjectAccessor::GetUnit(*player, guid);
                          if (!enemy || !enemy->IsAlive())
                              continue;
                          if (rune == Rune::LightningRod)
                          {
                              // "All enemies are hit for {damage_pct} weapon damage as Lightning over {hit_count}
                              // hits."
                              unsigned const hits = unsigned(Numbers::Num(spellId, "hit_count"));
                              for (unsigned hit = 0; hit < hits; ++hit)
                                  Later(player, ExplosionDelayMs(hit, Tune("spike_trap_chain_gap_seconds")),
                                        [player, spellId, guid, each = HitPct(pct, hits)]
                                        {
                                            Unit* target = ObjectAccessor::GetUnit(*player, guid);
                                            if (player->IsAlive() && target && target->IsAlive())
                                                Combat::Strike(player, target, spellId, each);
                                        });
                              continue;
                          }
                          if (Combat::Strike(player, enemy, spellId, pct) && rune == Rune::EchoingBlast)
                              // "the blast slows any targets hit for {slow_duration_seconds} seconds"
                              Slow(player, enemy, Tune("spike_trap_echoing_slow_pct"),
                                   Numbers::Num(spellId, "slow_duration_seconds"));
                      }
                  });
        }

        void Lay(Player* player, std::uint32_t spellId, Position const& at)
        {
            Rune const rune = RuneAt(spellId);
            GroundDevice::Setup setup;
            setup.kind = BaseId(Skill);
            setup.record = spellId;
            setup.spec.mode = GroundDevice::Mode::Command;
            // Grenadier's larger explosion (the power file's SF_1 multiplies a radius by the passive's radius share).
            setup.spec.radiusYards = Passive::GrenadeRadius(
                player, spellId,
                BlastRadius(rune, Numbers::Num(spellId, "radius_yards"), Tune("spike_trap_custom_trigger_radius_yards"),
                            Tune("spike_trap_lightning_rod_radius_yards")));
            setup.spec.armMs =
                ArmSeconds(rune, Tune("spike_trap_arming_seconds"), Tune("spike_trap_impaling_arming_seconds"),
                           Tune("spike_trap_custom_trigger_arming_seconds")) *
                1000.0;
            setup.spec.lifetimeMs =
                Tune("spike_trap_armed_seconds") * Passive::DurationFactor(player, "Spike Trap") * 1000.0;
            setup.spec.most = std::size_t(
                Passive::MostStanding(player, "spike_trap", unsigned(Numbers::Num(BaseId(Skill), "max_count"))));
            setup.fire = [spellId](Player* owner, Position const& place, std::vector<Unit*> const& enemies)
            { Explode(owner, spellId, place, enemies); };
            GroundDevice::Place(player, setup, at);
            // Impaling Spines: "When deployed, enemies within range are instantly immobilized for
            // {immobilize_duration_seconds} seconds."
            if (rune == Rune::ImpalingSpines)
                for (Unit* enemy : Combat::Enemies(player, spellId, at, setup.spec.radiusYards))
                    Root(player, enemy, Numbers::Num(spellId, "immobilize_duration_seconds"));
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

    void Casting(Player* player, std::uint32_t spellId)
    {
        if (!player || Shells::FindAbility(spellId) == nullptr)
            return;
        bool const generator = Classes::CategoryOf(spellId) == "Primary";
        if (!Detonates(Is(spellId), CostsHatred(spellId), generator, SlottedRune(player)))
            return;
        // "Lay a trap that remains dormant until another Hatred spender is used to detonate the trap. When detonated,
        // the trap and all other traps will explode in a chain reaction."
        explosionOrder = 0;
        GroundDevice::Detonate(player, BaseId(Skill));
    }

    void Ground(Player* player, std::uint32_t spellId, Position const& center)
    {
        if (!player || !Is(spellId))
            return;
        if (RuneAt(spellId) != Rune::Scatter)
        {
            Lay(player, spellId, center);
            return;
        }
        // Scatter: "Simultaneously lay {spawn_count} traps": side by side across the aim.
        double const aim = player->GetAngle(&center);
        for (double side :
             Layout(unsigned(Numbers::Num(spellId, "spawn_count")), Tune("spike_trap_scatter_spacing_yards")))
            Lay(player, spellId,
                Position(float(center.GetPositionX() + std::cos(aim + M_PI / 2) * side),
                         float(center.GetPositionY() + std::sin(aim + M_PI / 2) * side), center.GetPositionZ()));
    }
} // namespace DC::Combat::DemonHunter::SpikeTrap
