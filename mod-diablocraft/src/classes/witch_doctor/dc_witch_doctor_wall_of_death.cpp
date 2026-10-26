/*
 * Wall of Death and its five runes. The skill is the engine's ground-aimed cast (a record and the sheet's numbers) that
 * hits nothing; here: the wall of zombies across the aim (a periodic device of the shared ground-device piece that
 * hurts what stands in it), Surrounded by Death's circle, Ring of Poison's ring, Communing with Spirits' circle that
 * chills and weakens, Wall of Zombies' shove and Fire Wall's flame.
 */

#include "dc_witch_doctor_wall_of_death.h"
#include "dc_witch_doctor_common.h"
#include "dc_witch_doctor_effects.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_enemy_effects.h"
#include "../../combat/dc_ground_device.h"
#include "../../combat/dc_movement_effects.h"
#include "../../combat/dc_periodic_strike.h"
#include "../../combat/dc_spell_numbers.h"
#include "GameTime.h"
#include "Player.h"
#include "Position.h"
#include "Unit.h"

#include <memory>
#include <unordered_map>

namespace DC::Combat::WitchDoctor::WallOfDeath
{
    namespace
    {
        constexpr std::string_view Skill = "Wall of Death";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        // What an enemy has been given by one wall or ring, by enemy: when (a burn, a poison), kept for that wall's
        // life.
        using Given = std::unordered_map<std::uint64_t, std::uint64_t>;

        // The seconds the wall, circle or ring stands: the skill's and Wall of Zombies' damage seconds, Surrounded by
        // Death's own, the others' duration.
        double LifeSeconds(std::uint32_t spellId, Rune rune)
        {
            switch (rune)
            {
                case Rune::RingOfPoison:
                case Rune::FireWall:
                    return Numbers::Num(spellId, "duration_seconds");
                case Rune::CommuningWithSpirits:
                    return Numbers::Num(spellId, "duration_seconds", "circle");
                default:
                    return Numbers::Num(spellId, "dot_duration_seconds");
            }
        }

        // A device that fires every `tickSeconds` for `life` seconds over `radius` yards.
        GroundDevice::Setup Device(std::uint32_t spellId, double radius, double life, double tickSeconds)
        {
            GroundDevice::Setup device;
            device.kind = BaseId(Skill);
            device.record = spellId;
            device.spec.mode = GroundDevice::Mode::Periodic;
            device.spec.radiusYards = radius;
            device.spec.lifetimeMs = life * 1000.0;
            device.spec.intervalMs = tickSeconds * 1000.0;
            return device;
        }

        // Wall of Zombies: "All enemies in front of you are knocked back behind the wall."
        void Shove(Player* player, std::uint32_t spellId, Position const& center, double heading, double width,
                   double capsule)
        {
            for (Unit* enemy : Combat::Enemies(player, spellId, center, WallReach(width, capsule) + width))
            {
                double const dx = enemy->GetPositionX() - center.GetPositionX(),
                             dy = enemy->GetPositionY() - center.GetPositionY(), along = Along(dx, dy, heading);
                if (InFront(along, Across(dx, dy, heading), width))
                    Abilities::Knock(player, enemy, KnockYards(along, capsule));
            }
        }

        // The wall across the aim: every tick every enemy standing in it takes its share of the damage; Fire Wall
        // instead sets an enemy that walks through it alight.
        void Raise(Player* player, std::uint32_t spellId, Rune rune, Position const& center)
        {
            double const width = Numbers::Num(spellId, "radius_yards"),
                         capsule = Tune("wall_of_death_capsule_radius_yards"), life = LifeSeconds(spellId, rune),
                         heading = player->GetAngle(center.GetPositionX(), center.GetPositionY()),
                         x = center.GetPositionX(), y = center.GetPositionY();
            if (rune == Rune::WallOfZombies)
                Shove(player, spellId, center, heading, width, capsule);
            bool const fire = rune == Rune::FireWall;
            double const tick = Tune(fire ? "wall_of_death_fire_tick_seconds" : "wall_of_death_tick_seconds");
            double const pct = fire ? 0.0 : TickPct(Numbers::Num(spellId, "damage_pct"), life, tick);
            auto burnt = std::make_shared<Given>();
            GroundDevice::Setup wall = Device(spellId, WallReach(width, capsule), life, tick);
            wall.fire = [spellId, heading, width, capsule, x, y, fire, pct, burnt](Player* owner, Position const&,
                                                                                   std::vector<Unit*> const& enemies)
            {
                for (Unit* enemy : enemies)
                {
                    if (!InWall(enemy->GetPositionX() - x, enemy->GetPositionY() - y, heading, width, capsule))
                        continue;
                    if (!fire)
                    {
                        Combat::Strike(owner, enemy, spellId, pct);
                        continue;
                    }
                    // "burns enemies who walk through, causing them to take {damage_pct} weapon damage as Fire over
                    // {dot_duration_seconds} seconds"
                    std::uint64_t const key = enemy->GetGUID().GetRawValue(), now = Now();
                    auto const last = burnt->find(key);
                    if (BurnsAgain(last == burnt->end() ? std::nullopt : std::optional<std::uint64_t>(last->second),
                                   now, std::uint64_t(Numbers::Num(spellId, "dot_duration_seconds") * 1000.0)))
                    {
                        (*burnt)[key] = now;
                        PeriodicStrike::Start(owner, enemy, spellId, Numbers::Num(spellId, "damage_pct"),
                                              Numbers::Num(spellId, "dot_duration_seconds"),
                                              Tune("wall_of_death_fire_tick_seconds"));
                    }
                }
            };
            GroundDevice::Place(player, wall, center);
        }

        // Surrounded by Death's circle and Communing with Spirits': every tick every enemy in it takes its share, and
        // the spirits chill and weaken what they hurt.
        void Circle(Player* player, std::uint32_t spellId, Rune rune, Position const& center)
        {
            double const life = LifeSeconds(spellId, rune), tick = Tune("wall_of_death_tick_seconds");
            double const pct = TickPct(Numbers::Num(spellId, "damage_pct"), life, tick);
            bool const spirits = rune == Rune::CommuningWithSpirits;
            GroundDevice::Setup circle = Device(spellId, Tune("wall_of_death_circle_radius_yards"), life, tick);
            circle.fire = [spellId, pct, spirits](Player* owner, Position const&, std::vector<Unit*> const& enemies)
            {
                for (Unit* enemy : enemies)
                {
                    Combat::Strike(owner, enemy, spellId, pct);
                    if (spirits)
                    {
                        // "Chills nearby enemies by {chill_pct}, and reduces their damage dealt by {enemy_damage_pct}
                        // for {duration_seconds:debuff} seconds."
                        double const seconds = Numbers::Num(spellId, "duration_seconds", "debuff");
                        Slow(owner, enemy, Numbers::Num(spellId, "chill_pct"), seconds);
                        EnemyEffects::Weaken(enemy, spellId, Numbers::Num(spellId, "enemy_damage_pct"), seconds);
                    }
                }
            };
            GroundDevice::Place(player, circle, center);
        }

        // Ring of Poison: every enemy that comes into the ring is poisoned once for the ring's life.
        void Ring(Player* player, std::uint32_t spellId, Rune rune, Position const& center)
        {
            double const tick = Tune("wall_of_death_ring_tick_seconds");
            auto poisoned = std::make_shared<Given>();
            GroundDevice::Setup ring =
                Device(spellId, Tune("wall_of_death_circle_radius_yards"), LifeSeconds(spellId, rune), tick);
            ring.fire = [spellId, tick, poisoned](Player* owner, Position const&, std::vector<Unit*> const& enemies)
            {
                for (Unit* enemy : enemies)
                    if (poisoned->emplace(enemy->GetGUID().GetRawValue(), Now()).second)
                        PeriodicStrike::Start(owner, enemy, spellId, Numbers::Num(spellId, "damage_pct"),
                                              Numbers::Num(spellId, "dot_duration_seconds"), tick);
            };
            GroundDevice::Place(player, ring, center);
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
        switch (rune)
        {
            case Rune::SurroundedByDeath:
            case Rune::CommuningWithSpirits:
                Circle(player, spellId, rune, center);
                break;
            case Rune::RingOfPoison:
                Ring(player, spellId, rune, center);
                break;
            default:
                Raise(player, spellId, rune, center);
                break;
        }
    }
} // namespace DC::Combat::WitchDoctor::WallOfDeath
