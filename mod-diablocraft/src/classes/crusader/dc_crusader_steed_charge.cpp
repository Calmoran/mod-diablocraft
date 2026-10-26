/*
 * Steed Charge and its five runes. Power/X1_Crusader_SteedCharge.pow: a ride of 2 seconds (Endurance 3) on a celestial
 * war horse at a movement speed bonus, with damage ticks four times a second. The skill deals no damage; the module
 * runs the ride as ticks, each doing what the rune says. The dispatch is in dc_crusader.cpp.
 */

#include "dc_crusader_steed_charge.h"
#include "dc_crusader_common.h"
#include "dc_crusader_consecration.h"
#include "dc_crusader_dot.h"
#include "dc_crusader_nearest.h"
#include "dc_crusader_zone.h"
#include "../../combat/dc_movement_effects.h"
#include "../../stats/dc_stats.h"
#include "ObjectAccessor.h"
#include "SpellAuraEffects.h"

#include <cmath>
#include <memory>

namespace DC::Combat::Crusader::SteedCharge
{
    namespace
    {
        constexpr std::string_view Skill = "Steed Charge";
        // Stock "Summon Charger" (34767, the skill's donor): a MOUNTED aura on the war horse and a mounted-speed aura.
        constexpr std::uint32_t Horse = 34767;

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        double Tune(char const* name)
        {
            return DC::Tunables::Get("crusader", name);
        }

        // What a ride keeps from one tick to the next: the enemies Draw and Quarter bound, the last fire pool and how many
        // ticks the ride has.
        struct Ride
        {
            std::vector<ObjectGuid> bound;
            std::optional<Position> lastPool;
            unsigned ticks = 0;
        };

        // The war horse under the Crusader for `seconds`: the stock charger aura, with its own mounted speed taken to 0
        // because the ride's speed is the movement speed bonus below. Nothing when the aura will not take.
        void Mount(Player* player, double seconds)
        {
            player->RemoveAurasDueToSpell(Horse, player->GetGUID());
            Aura* mount = player->AddAura(Horse, player);
            if (!mount)
                return;
            if (AuraEffect* speed = mount->GetEffect(EFFECT_1))
                speed->ChangeAmount(0);
            mount->SetMaxDuration(int32(seconds * 1000));
            mount->SetDuration(int32(seconds * 1000));
        }

        // Spiked Barding: a share of the Crusader's Thorns, dealt as Thorns is, all Physical and never a critical hit.
        void Barding(Player* player, std::uint32_t spellId, Unit* enemy, double sharePct)
        {
            auto const sheet = Stats::Get(player->GetGUID().GetRawValue());
            if (!sheet)
                return;
            Hit hit;
            hit.skillName = "Thorns";
            hit.school = SPELL_SCHOOL_MASK_NORMAL;
            hit.total = Consecration::ThornsShare((*sheet)[Stat::Thorns], sharePct);
            hit.crit = 1.0;
            if (hit.total > 0)
                Combat::DealHit(player, enemy, spellId, hit);
        }

        // Nightmare: a pool of fire where the horse is, lasting a moment, that burns the enemies in it.
        void Pool(Player* player, std::uint32_t spellId, Position const& where)
        {
            double const tick = Tune("steed_charge_nightmare_pool_tick_seconds");
            Zone::Lay(player, spellId, where, Tune("steed_charge_nightmare_pool_radius_yards"),
                      PerTick(Numbers::Num(spellId, "damage_pct"), tick), Tune("steed_charge_nightmare_pool_seconds"),
                      tick);
        }

        // Draw and Quarter: each enemy bound that is farther than the drag distance is drawn in to it, and all of them
        // take the tick's share of the damage.
        void Drag(Player* player, std::uint32_t spellId, Ride const& ride, double tickSeconds)
        {
            double const keep = Tune("steed_charge_draw_distance_yards");
            double const pct = PerTick(Numbers::Num(spellId, "damage_pct"), tickSeconds);
            Position const here = player->GetPosition();
            for (ObjectGuid const& guid : ride.bound)
            {
                Unit* enemy = ObjectAccessor::GetUnit(*player, guid);
                if (!enemy || !enemy->IsAlive())
                    continue;
                double const distance = player->GetExactDist(enemy);
                if (Dragged(distance, keep))
                {
                    double const share = DragFraction(distance, keep);
                    Position point = here;
                    point.Relocate(here.GetPositionX() + (enemy->GetPositionX() - here.GetPositionX()) * share,
                                   here.GetPositionY() + (enemy->GetPositionY() - here.GetPositionY()) * share,
                                   here.GetPositionZ() + (enemy->GetPositionZ() - here.GetPositionZ()) * share);
                    Abilities::Pull(enemy, point);
                }
                Combat::Strike(player, enemy, spellId, pct, true);
            }
        }

        // One tick of the ride. The ticks left bound the ride by themselves: no clock test may stop the last one.
        void Tick(Player* player, std::uint32_t spellId, std::shared_ptr<Ride> ride, unsigned left,
                  std::uint32_t intervalMs)
        {
            if (!player->IsInWorld() || !player->IsAlive() || left == 0)
                return;
            double const tick = intervalMs / 1000.0;
            Position const here = player->GetPosition();
            switch (RuneAt(spellId))
            {
                case Rune::SpikedBarding:
                    // "The war horse deals {thorns_share_pct} of your Thorns every second to enemies through which you
                    // ride."
                    for (Unit* enemy :
                         Combat::Enemies(player, spellId, here, Tune("steed_charge_spiked_barding_radius_yards")))
                        Barding(player, spellId, enemy, PerTick(Numbers::Num(spellId, "thorns_share_pct"), tick));
                    break;
                case Rune::Rejuvenation:
                    // "While riding the war horse, you recover {heal_pct} of your maximum Life": that much over the
                    // whole ride, in equal ticks.
                    Heal(player, player, spellId,
                         HealPerTick(player->GetMaxHealth(), Numbers::Num(spellId, "heal_pct"), ride->ticks));
                    break;
                case Rune::Nightmare:
                    if (DropsPool(ride->lastPool.has_value(),
                                  ride->lastPool ? ride->lastPool->GetExactDist(&here) : 0.0,
                                  Tune("steed_charge_nightmare_pool_spacing_yards")))
                    {
                        Pool(player, spellId, here);
                        ride->lastPool = here;
                    }
                    break;
                case Rune::DrawAndQuarter:
                    Drag(player, spellId, *ride, tick);
                    break;
                default:
                    break;
            }
            if (left > 1)
                player->m_Events.AddEventAtOffset([player, spellId, ride, left, intervalMs]
                                                  { Tick(player, spellId, ride, left - 1, intervalMs); },
                                                  std::chrono::milliseconds(intervalMs));
        }

        // The end of the ride: the horse goes.
        void Dismount(Player* player)
        {
            if (player->IsInWorld())
                player->RemoveAurasDueToSpell(Horse, player->GetGUID());
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

    void Cast(Player* player, std::uint32_t spellId)
    {
        if (!player || !Is(spellId))
            return;
        // "ride through enemies ... for {duration_seconds} seconds": the skill's 2, Endurance's own 3.
        double const seconds = Numbers::Num(spellId, "duration_seconds");
        double const tick = Tune("steed_charge_tick_seconds");
        Mount(player, seconds);
        Buffs::Stack(player, spellId, Stat::MovementSpeed, Bucket::Uncapped,
                     SpeedPct(Tune("steed_charge_movement_speed_bonus")), 1, seconds);

        auto ride = std::make_shared<Ride>();
        if (RuneAt(spellId) == Rune::DrawAndQuarter)
        {
            // "Bind {target_count} monsters near you": the nearest ones inside the herd radius, bound for the whole
            // ride.
            double const radius = Tune("steed_charge_draw_radius_yards");
            std::vector<Unit*> const near = Combat::Enemies(player, spellId, player->GetPosition(), radius);
            std::vector<double> distances;
            for (Unit* enemy : near)
                distances.push_back(player->GetExactDist(enemy));
            for (std::size_t i : Nearest(distances, radius, std::size_t(Numbers::Num(spellId, "target_count"))))
                ride->bound.push_back(near[i]->GetGUID());
        }
        if (unsigned const ticks = Dot::Ticks(seconds, tick))
        {
            ride->ticks = ticks;
            auto const interval = std::uint32_t(tick * 1000 + 0.5);
            player->m_Events.AddEventAtOffset([player, spellId, ride, ticks, interval]
                                              { Tick(player, spellId, ride, ticks, interval); },
                                              std::chrono::milliseconds(interval));
        }
        player->m_Events.AddEventAtOffset([player] { Dismount(player); },
                                          std::chrono::milliseconds(std::uint64_t(seconds * 1000.0) + 1));
    }
} // namespace DC::Combat::Crusader::SteedCharge
