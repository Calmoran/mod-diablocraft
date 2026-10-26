/*
 * Spirit Wolves and its five runes. The cast is the engine's aimed line (a record and the sheet's numbers) that hits
 * nothing itself; here: the wave of wolves that runs down the lane(s) at the sheet's speed, each wolf's hit on every
 * enemy its lane touches as the wave reaches it, and each rune's part (Spirit Pack's fan, Lightning Wolves' arcs, Fiery
 * Wolves' trail, Frost Wolves' freeze, Spirit of the Pack's Maelstrom).
 */

#include "dc_shaman_spirit_wolves.h"
#include "dc_shaman_common.h"
#include "dc_shaman_effects.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_ground_device.h"
#include "../../combat/dc_item_powers.h"
#include "ObjectAccessor.h"
#include "Unit.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <memory>

namespace DC::Combat::Shaman::SpiritWolves
{
    namespace
    {
        constexpr std::string_view Skill = "Spirit Wolves";

        Shells::Ability const* RowOf(std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && Skill == row->skill ? row : nullptr;
        }

        std::uint32_t BaseId()
        {
            for (auto const& row : Shells::Abilities)
                if (Skill == row.skill && !*row.rune)
                    return row.id;
            return 0;
        }

        std::uint32_t Millis(double seconds)
        {
            return std::uint32_t(seconds * 1000.0 + 0.5);
        }

        // What one cast of the wolves carries to the enemies they reach.
        struct Wave
        {
            std::uint32_t spellId = 0;
            Rune rune = Rune::None;
            double hitPct = 0; // each wolf's hit
            double gained = 0; // Maelstrom the cast has paid
        };

        // One enemy reached by `hits` wolves of the wave: each wolf's hit and its arc, then the rune's part, once.
        void Arrive(Player* player, std::shared_ptr<Wave> wave, ObjectGuid guid, unsigned hits)
        {
            if (!player->IsAlive() || !player->IsInWorld())
                return;
            Unit* enemy = ObjectAccessor::GetUnit(*player, guid);
            if (!enemy || !enemy->IsAlive())
                return;
            for (unsigned wolf = 0; wolf < hits && enemy->IsAlive(); ++wolf)
            {
                Combat::Strike(player, enemy, wave->spellId, wave->hitPct);
                // "Each wolf hit arcs to {target_count} nearby enemies for {damage_pct} weapon damage as Lightning."
                if (Arcs(wave->rune))
                {
                    std::vector<Unit*> near = Combat::Enemies(player, wave->spellId, enemy->GetPosition(),
                                                              Tunable("spirit_wolves_arc_radius_yards"));
                    near.erase(std::remove(near.begin(), near.end(), enemy), near.end());
                    std::vector<double> distances;
                    for (Unit* other : near)
                        distances.push_back(other->GetExactDist(enemy));
                    for (std::size_t index :
                         Nearest(distances, std::size_t(Numbers::Num(wave->spellId, "target_count"))))
                        Combat::Strike(player, near[index], wave->spellId, Numbers::Num(wave->spellId, "damage_pct"));
                }
            }
            if (Freezes(wave->rune) && enemy->IsAlive())
                Shaman::Freeze(player, enemy,
                               Numbers::Num(wave->spellId, "freeze_duration_seconds") * ItemPowers::StunFactor(player));
            // "Each enemy hit generates {per_hit} Maelstrom (up to {cap} per cast)."
            if (Pays(wave->rune))
            {
                double const pay = Pay(wave->gained, Numbers::Num(wave->spellId, "gain_resource", "per_hit"),
                                       Numbers::Num(wave->spellId, "gain_resource", "cap"));
                if (pay > 0)
                {
                    wave->gained += pay;
                    Gain(player, wave->spellId, pay);
                }
            }
        }

        // One patch of the burning trail where the wolves are now.
        void Patch(Player* player, std::uint32_t spellId, Position at)
        {
            if (!player->IsAlive() || !player->IsInWorld())
                return;
            double const tick = Tunable("spirit_wolves_trail_tick_seconds");
            double const pct = PulsePct(Numbers::Num(spellId, "damage_pct"), tick);
            GroundDevice::Setup patch;
            patch.kind = BaseId();
            patch.record = spellId;
            patch.spec.mode = GroundDevice::Mode::Periodic;
            patch.spec.radiusYards = Tunable("spirit_wolves_trail_radius_yards");
            patch.spec.lifetimeMs =
                Millis(Combat::ModifiedDurationSeconds(player, spellId, Numbers::Num(spellId, "duration_seconds")));
            patch.spec.intervalMs = tick * 1000.0;
            patch.spec.most = std::size_t(Tunable("spirit_wolves_trail_most"));
            patch.fire = [spellId, pct](Player* owner, Position const&, std::vector<Unit*> const& enemies)
            {
                for (Unit* enemy : enemies)
                    Combat::Strike(owner, enemy, spellId, pct, true);
            };
            float z = at.GetPositionZ();
            player->UpdateAllowedPositionZ(at.GetPositionX(), at.GetPositionY(), z);
            at.m_positionZ = z;
            GroundDevice::Place(player, patch, at);
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        // The wolves strike as they pass; the cast itself hits nothing. A rune's `damage_pct` is the arc's or the
        // trail's.
        return RowOf(spellId) ? std::optional<double>(0.0) : std::nullopt;
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        auto const* row = RowOf(spellId);
        if (!player || !row)
            return;
        Rune const rune = RuneOf(row->rune);
        double const range = Numbers::Num(spellId, "radius_yards");
        double const halfWidth = Tunable("spirit_wolves_lane_width_yards") / 2.0;
        double const speed = Tunable("spirit_wolves_speed_yards_per_second");
        // The wave runs toward the enemy aimed at (the cast needs one); the wolves of Spirit Pack fan across the cone
        // around it.
        Unit* aim = player->GetSelectedUnit();
        if (!aim || !aim->IsAlive())
            aim = targets.empty() ? nullptr : targets.front();
        Position const origin = player->GetPosition();
        double const bearing =
            aim ? std::atan2(aim->GetPositionY() - origin.GetPositionY(), aim->GetPositionX() - origin.GetPositionX())
                : double(player->GetOrientation());
        std::vector<double> const lanes =
            Fan(unsigned(Numbers::Num(spellId, "projectile_count")),
                rune == Rune::SpiritPack ? Numbers::Num(spellId, "cone_angle_degrees") : 0.0);
        auto wave = std::make_shared<Wave>();
        wave->spellId = spellId;
        wave->rune = rune;
        wave->hitPct = Numbers::Num(BaseId(), "damage_pct");
        for (Unit* enemy : Combat::Enemies(player, spellId, origin, range))
        {
            unsigned hits = 0;
            double nearest = range;
            for (double angle : lanes)
            {
                Reach const reach = Touch(bearing + angle, enemy->GetPositionX() - origin.GetPositionX(),
                                          enemy->GetPositionY() - origin.GetPositionY(), range, halfWidth);
                if (reach.touched)
                {
                    ++hits;
                    nearest = std::min(nearest, reach.ahead);
                }
            }
            if (!hits)
                continue;
            ObjectGuid const guid = enemy->GetGUID();
            player->m_Events.AddEventAtOffset([player, wave, guid, hits] { Arrive(player, wave, guid, hits); },
                                              std::chrono::milliseconds(Millis(Seconds(nearest, speed))));
        }
        // Fiery Wolves: "leave burning trails": a patch every spacing along the lane, laid as the wave passes.
        if (LeavesTrail(rune))
        {
            double const spacing = Tunable("spirit_wolves_trail_spacing_yards");
            for (unsigned patch = 1; patch <= Patches(range, spacing); ++patch)
            {
                double const along = patch * spacing;
                Position at = origin;
                at.m_positionX = float(origin.GetPositionX() + std::cos(bearing) * along);
                at.m_positionY = float(origin.GetPositionY() + std::sin(bearing) * along);
                player->m_Events.AddEventAtOffset([player, spellId, at] { Patch(player, spellId, at); },
                                                  std::chrono::milliseconds(Millis(Seconds(along, speed))));
            }
        }
    }
} // namespace DC::Combat::Shaman::SpiritWolves
