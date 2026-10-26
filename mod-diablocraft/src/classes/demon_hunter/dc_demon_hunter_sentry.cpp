/*
 * Sentry and its five runes. The cast is the engine's self-summon (a record and the sheet's numbers) that hits nothing;
 * here: the cast spends one of the stored charges, the turret is set down where the Demon Hunter stands as a periodic
 * device of the shared ground-device piece (it shoots the nearest enemy at the Demon Hunter's attack speed), and the
 * rune's own pulse: Chain of Torment's chains, Impaling Bolt's piercing, Spitfire Turret's rockets, Polar Station's
 * chill and Guardian Turret's shield. The piece counts the turrets, ends their time and takes them away.
 */

#include "dc_demon_hunter_sentry.h"
#include "dc_demon_hunter_buffs.h"
#include "dc_demon_hunter_common.h"
#include "dc_demon_hunter_effects.h"
#include "dc_demon_hunter_passives.h"
#include "dc_demon_hunter_seek.h"
#include "../dc_classes.h"
#include "../../combat/dc_charge_store.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_ground_device.h"
#include "../../combat/dc_spell_numbers.h"
#include "GameTime.h"
#include "Group.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Position.h"
#include "Unit.h"
#include "Util.h"

#include <chrono>
#include <cmath>
#include <mutex>
#include <unordered_map>

namespace DC::Combat::DemonHunter::Sentry
{
    namespace
    {
        constexpr std::string_view Skill = "Sentry";

        std::mutex mutex;
        std::unordered_map<std::uint64_t, ChargeStore> charges; // by Demon Hunter

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        // The key a rune's pulse device is kept under: apart from the turrets, so each is counted and given way to on
        // its own, and no spell id.
        std::uint32_t PulseKind()
        {
            return ~BaseId(Skill);
        }

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        std::uint64_t Millis(double seconds)
        {
            return std::uint64_t(std::llround(std::max(0.0, seconds) * 1000.0));
        }

        void Later(Player* player, std::uint32_t ms, std::function<void()> work)
        {
            if (!ms)
                work();
            else
                player->m_Events.AddEventAtOffset(std::move(work), std::chrono::milliseconds(ms));
        }

        // "You gain a charge every {charge_recharge_seconds} seconds and can have up to {charge_count} charges stored":
        // the cast spends one; the button waits for the next while none is left.
        void SpendCharge(Player* player, std::uint32_t spellId)
        {
            unsigned const cap =
                Passive::MostStanding(player, "sentry", unsigned(Numbers::Num(spellId, "charge_count")));
            std::uint32_t const period = ReducedCooldownMilliseconds(
                player, spellId, std::uint32_t(Millis(Numbers::Num(spellId, "charge_recharge_seconds"))));
            std::uint64_t wait;
            {
                std::lock_guard<std::mutex> guard(mutex);
                wait = charges[player->GetGUID().GetRawValue()].Spend(Now(), cap, period);
            }
            SendSkillCooldown(player, spellId, std::uint32_t(wait));
        }

        // One shot of the turret at `place`: the nearest enemy takes the skill's damage; Impaling Bolt's bolt goes on
        // through every enemy on the line beyond; Polar Station's chills what it hits.
        void Shoot(Player* owner, std::uint32_t spellId, Rune rune, Position const& place,
                   std::vector<Unit*> const& enemies)
        {
            std::vector<double> distances;
            for (Unit* enemy : enemies)
                distances.push_back(enemy->GetExactDist(&place));
            std::size_t const aimed = Nearest(distances);
            if (aimed == none)
                return;
            Unit* target = enemies[aimed];
            std::uint32_t const base = BaseId(Skill), striker = ShotTakesRuneElement(rune) ? spellId : base;
            double const pct = Numbers::Num(base, "damage_pct");
            if (rune == Rune::ImpalingBolt)
            {
                // "The turret now fires piercing bolts" (the file's pierce chance is 1): the bolt flies the turret's
                // reach along the line to the nearest enemy.
                double const length = Tune("sentry_attack_radius_yards"), width = Tune("sentry_pierce_width_yards"),
                             heading = place.GetAngle(target->GetPositionX(), target->GetPositionY());
                for (Unit* enemy : enemies)
                    if (OnLine(enemy->GetPositionX() - place.GetPositionX(),
                               enemy->GetPositionY() - place.GetPositionY(), heading, length, width))
                        Combat::Strike(owner, enemy, striker, pct);
                return;
            }
            Combat::Strike(owner, target, striker, pct);
            // Polar Station: the shots chill.
            if (rune == Rune::PolarStation)
                Slow(owner, target, Tune("sentry_shot_chill_pct"), Tune("sentry_chill_seconds"));
        }

        // Chain of Torment: "a chain between you and the Sentry and between each Sentry that deals {damage_pct} weapon
        // damage every second to each enemy it touches". Each turret answers for the chain to itself and the one to the
        // turret laid after it.
        void Chain(Player* owner, std::uint32_t spellId, Position const& place, std::vector<Unit*> const& enemies)
        {
            double const reach = Tune("sentry_chain_max_yards"), touch = Tune("sentry_chain_touch_yards"),
                         pct = PulsePct(Numbers::Num(spellId, "damage_pct"), Tune("sentry_chain_pulse_seconds"));
            std::vector<std::pair<Position, Position>> links{{owner->GetPosition(), place}};
            std::vector<Position> const turrets = GroundDevice::Places(owner, BaseId(Skill));
            for (std::size_t i = 0; i + 1 < turrets.size(); ++i)
                if (turrets[i].GetExactDist2d(&place) < 0.01)
                {
                    links.emplace_back(place, turrets[i + 1]);
                    break;
                }
            for (auto const& [from, to] : links)
            {
                if (!Linked(from.GetExactDist2d(&to), reach))
                    continue;
                for (Unit* enemy : enemies)
                    if (Touches(DistanceToSegment(enemy->GetPositionX(), enemy->GetPositionY(), from.GetPositionX(),
                                                  from.GetPositionY(), to.GetPositionX(), to.GetPositionY()),
                                touch))
                        Combat::Strike(owner, enemy, spellId, pct);
            }
        }

        // Spitfire Turret: "will also fire homing rockets at random nearby enemies": one rocket a pulse, landing after
        // its flight.
        void Rocket(Player* owner, std::uint32_t spellId, Position const& place, std::vector<Unit*> const& enemies)
        {
            if (enemies.empty())
                return;
            Unit* target = enemies[urand(0, uint32(enemies.size() - 1))];
            std::uint32_t const delay =
                RocketDelayMs(Tune("sentry_rocket_warmup_seconds"), Tune("sentry_rocket_seconds_per_yard"),
                              target->GetExactDist(&place));
            ObjectGuid const guid = target->GetGUID();
            Later(owner, delay,
                  [owner, spellId, guid]
                  {
                      Unit* enemy = ObjectAccessor::GetUnit(*owner, guid);
                      if (owner->IsAlive() && owner->IsInWorld() && enemy && enemy->IsAlive())
                          Combat::Strike(owner, enemy, spellId,
                                         Numbers::Num(spellId, "damage_pct") * Passive::RocketFactor(owner));
                  });
        }

        // Polar Station: "Chills all nearby enemies within {radius_yards} yards, Slowing their movement speed by
        // {slow_pct}."
        void Chill(Player* owner, std::uint32_t spellId, std::vector<Unit*> const& enemies)
        {
            for (Unit* enemy : enemies)
                Slow(owner, enemy, Numbers::Num(spellId, "slow_pct"), Tune("sentry_chill_seconds"));
        }

        // Guardian Turret: "creates a shield that reduces damage taken by allies by {damage_reduction_pct}": the Demon
        // Hunter and the party within the file's area about the turret, held until the next pulse.
        void Shield(Player* owner, std::uint32_t spellId, Position const& place)
        {
            std::vector<Player*> allies{owner};
            if (Group* group = owner->GetGroup())
                for (GroupReference* ref = group->GetFirstMember(); ref; ref = ref->next())
                    if (Player* member = ref->GetSource())
                        if (member != owner && member->IsAlive() && member->IsInWorld() &&
                            member->GetMap() == owner->GetMap())
                            allies.push_back(member);
            double const area = Tune("sentry_shield_radius_yards"),
                         hold = ShieldHoldSeconds(Tune("sentry_aura_pulse_seconds"));
            for (Player* ally : allies)
                if (ally->GetExactDist(&place) <= area)
                    Buffs::Stack(ally, spellId, Stat::SpecificReduction, Bucket::Flat,
                                 Numbers::Num(spellId, "damage_reduction_pct"), 1, hold);
        }

        void Lay(Player* player, std::uint32_t spellId)
        {
            Rune const rune = RuneAt(spellId);
            std::uint32_t const base = BaseId(Skill);
            Position const at = player->GetPosition();
            double const attacks = Combat::AttacksPerSecond(player, spellId);

            GroundDevice::Setup turret;
            turret.kind = base;
            turret.record = spellId;
            turret.spec.mode = GroundDevice::Mode::Periodic;
            turret.spec.radiusYards = Tune("sentry_attack_radius_yards");
            turret.spec.lifetimeMs =
                Numbers::Num(base, "duration_seconds") * Passive::DurationFactor(player, "Sentry") * 1000.0;
            turret.spec.intervalMs = ShotMs(attacks);
            turret.spec.most =
                std::size_t(Passive::MostStanding(player, "sentry", unsigned(Numbers::Num(base, "max_count"))));
            turret.fire = [spellId, rune](Player* owner, Position const& place, std::vector<Unit*> const& enemies)
            { Shoot(owner, spellId, rune, place, enemies); };
            // The turret is seen: it wears the stock Gnomish Flame Turret's creature display.
            turret.display = std::uint32_t(Tune("sentry_turret_display_id"));
            GroundDevice::Place(player, turret, at);

            // The rune's own pulse, a device of the same life beside the turret.
            GroundDevice::Setup pulse = turret;
            pulse.display = 0; // the pulse is nothing to look at: the turret already shows
            pulse.kind = PulseKind();
            double const beat = Tune("sentry_aura_pulse_seconds") * 1000.0;
            switch (rune)
            {
                case Rune::ChainOfTorment:
                    pulse.spec.intervalMs = Tune("sentry_chain_pulse_seconds") * 1000.0;
                    pulse.fire = [spellId](Player* owner, Position const& place, std::vector<Unit*> const& enemies)
                    { Chain(owner, spellId, place, enemies); };
                    break;
                case Rune::SpitfireTurret:
                    pulse.spec.intervalMs = RocketMs(Tune("sentry_rocket_rate_factor"), attacks);
                    pulse.fire = [spellId](Player* owner, Position const& place, std::vector<Unit*> const& enemies)
                    { Rocket(owner, spellId, place, enemies); };
                    break;
                case Rune::PolarStation:
                    pulse.spec.intervalMs = beat;
                    pulse.spec.radiusYards = Numbers::Num(spellId, "radius_yards");
                    pulse.fire = [spellId](Player* owner, Position const&, std::vector<Unit*> const& enemies)
                    { Chill(owner, spellId, enemies); };
                    break;
                case Rune::GuardianTurret:
                    pulse.spec.intervalMs = beat;
                    pulse.fire = [spellId](Player* owner, Position const& place, std::vector<Unit*> const&)
                    { Shield(owner, spellId, place); };
                    break;
                default:
                    return;
            }
            GroundDevice::Place(player, pulse, at);
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

    void Cast(Player* player, std::uint32_t spellId)
    {
        if (!player || !Is(spellId))
            return;
        SpendCharge(player, spellId);
        Lay(player, spellId);
    }
} // namespace DC::Combat::DemonHunter::Sentry
