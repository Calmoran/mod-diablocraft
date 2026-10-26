/*
 * Rain of Vengeance and its five runes. The cast is the engine's ground cast (a record, its cooldown and the sheet's
 * numbers) that hits nothing of its own; here: the rain that falls after the skill's delay, Dark Cloud's storms over
 * random enemies, Anathema's grenades, Flying Strike's crashing Shadow Beasts that freeze, Stampede's wave across the
 * ground that knocks back. Every hit is a damage-over-time strike (an average critical hit), the rune's total shared
 * among them.
 */

#include "dc_demon_hunter_rain_of_vengeance.h"
#include "dc_demon_hunter_common.h"
#include "dc_demon_hunter_effects.h"
#include "dc_demon_hunter_passives.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_movement_effects.h"
#include "../../combat/dc_spell_numbers.h"
#include "Player.h"
#include "Position.h"
#include "Random.h"
#include "Unit.h"

#include <chrono>
#include <functional>
#include <vector>

namespace DC::Combat::DemonHunter::RainOfVengeance
{
    namespace
    {
        constexpr std::string_view Skill = "Rain of Vengeance";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        double Roll()
        {
            return frand(0.0f, 1.0f);
        }

        // Work that comes due `ms` after the cast, on the player's own queue, if the Demon Hunter is still there.
        void After(Player* player, std::uint32_t ms, std::function<void()> work)
        {
            player->m_Events.AddEventAtOffset(
                [player, work = std::move(work)]
                {
                    if (player->IsAlive() && player->IsInWorld())
                        work();
                },
                std::chrono::milliseconds(ms));
        }

        // One strike of `pct` on every enemy within `radius` of `at`; the enemies struck.
        std::vector<Unit*> Rain(Player* player, std::uint32_t spellId, Position const& at, double radius, double pct)
        {
            std::vector<Unit*> struck;
            for (Unit* enemy : Combat::Enemies(player, spellId, at, radius))
                if (Combat::Strike(player, enemy, spellId, pct, true))
                    struck.push_back(enemy);
            return struck;
        }

        Position At(Spot const& spot, Position const& center)
        {
            return Position(float(spot.x), float(spot.y), center.GetPositionZ());
        }

        double DelaySeconds()
        {
            return Tune("rain_of_vengeance_delay_seconds");
        }

        // The rain: the area struck every tick for the rune's seconds.
        void Falls(Player* player, std::uint32_t spellId, Position const& center)
        {
            unsigned const ticks =
                Count(Numbers::Num(spellId, "dot_duration_seconds"), Tune("rain_of_vengeance_tick_seconds"));
            double const pct = Share(Numbers::Num(spellId, "damage_pct"), ticks);
            for (unsigned i = 0; i < ticks; ++i)
                After(player, StartMs(i, DelaySeconds(), Tune("rain_of_vengeance_tick_seconds")),
                      [=] { Rain(player, spellId, center, Tune("rain_of_vengeance_radius_yards"), pct); });
        }

        // Dark Cloud: a storm over a random enemy near the cast every interval for the rune's seconds.
        void Storms(Player* player, std::uint32_t spellId, Position const& center)
        {
            unsigned const storms = Count(Numbers::Num(spellId, "dot_duration_seconds"),
                                          Tune("rain_of_vengeance_cloud_storm_interval_seconds"));
            double const pct = Share(Numbers::Num(spellId, "damage_pct"), storms);
            for (unsigned i = 0; i < storms; ++i)
                After(player, StartMs(i, DelaySeconds(), Tune("rain_of_vengeance_cloud_storm_interval_seconds")),
                      [=]
                      {
                          auto const enemies =
                              Combat::Enemies(player, spellId, center, Tune("rain_of_vengeance_cloud_search_yards"));
                          if (!enemies.empty())
                              Rain(player, spellId, enemies[PickAt(Roll(), enemies.size())]->GetPosition(),
                                   Tune("rain_of_vengeance_cloud_storm_radius_yards"), pct);
                      });
        }

        // Anathema: the Shadow Beast drops a grenade every interval for the rune's seconds, each at a random place
        // within the beast's range and exploding after its lifetime.
        void Grenades(Player* player, std::uint32_t spellId, Position const& center)
        {
            unsigned const grenades = Count(Numbers::Num(spellId, "dot_duration_seconds"),
                                            Tune("rain_of_vengeance_grenade_interval_seconds"));
            double const pct = Share(Numbers::Num(spellId, "damage_pct"), grenades);
            std::uint32_t const lifetime =
                std::uint32_t(Tune("rain_of_vengeance_grenade_lifetime_seconds") * 1000.0 + 0.5);
            for (unsigned i = 0; i < grenades; ++i)
            {
                Position const at = At(DiscPoint(center.GetPositionX(), center.GetPositionY(),
                                                 Tune("rain_of_vengeance_anathema_radius_yards"), Roll(), Roll()),
                                       center);
                After(player, StartMs(i, DelaySeconds(), Tune("rain_of_vengeance_grenade_interval_seconds")) + lifetime,
                      [=]
                      {
                          Rain(player, spellId, at,
                               Passive::GrenadeRadius(player, spellId, Tune("rain_of_vengeance_grenade_radius_yards")), pct);
                      });
            }
        }

        // Flying Strike: `pet_count` Shadow Beasts crash down at random places in the area, each hitting its share and
        // freezing what it hits.
        void Flyers(Player* player, std::uint32_t spellId, Position const& center)
        {
            unsigned const flyers = unsigned(Numbers::Num(spellId, "pet_count"));
            double const pct = Share(Numbers::Num(spellId, "damage_pct"), flyers);
            for (unsigned i = 0; i < flyers; ++i)
            {
                Position const at = At(DiscPoint(center.GetPositionX(), center.GetPositionY(),
                                                 Tune("rain_of_vengeance_radius_yards"), Roll(), Roll()),
                                       center);
                After(player, StartMs(i, DelaySeconds(), Tune("rain_of_vengeance_flyer_interval_seconds")),
                      [=]
                      {
                          // "Freezing enemies hit for {freeze_duration_seconds} seconds": a freeze is a stun.
                          for (Unit* enemy :
                               Rain(player, spellId, at, Tune("rain_of_vengeance_flyer_radius_yards"), pct))
                              Stun(player, enemy,
                                   Numbers::Num(spellId, "freeze_duration_seconds") * ItemPowers::StunFactor(player));
                      });
            }
        }

        // Stampede: `pet_count` Shadow Beasts across the ground from the Demon Hunter to the point aimed at, the wave
        // reaching each in turn over the rune's seconds; each hits its share and knocks back what it hits.
        void Wave(Player* player, std::uint32_t spellId, Position const& center)
        {
            unsigned const beasts = unsigned(Numbers::Num(spellId, "pet_count"));
            double const pct = Share(Numbers::Num(spellId, "damage_pct"), beasts);
            Position const start = player->GetPosition();
            double const heading = start.GetAbsoluteAngle(&center), length = start.GetExactDist2d(center);
            for (unsigned i = 0; i < beasts; ++i)
            {
                Position const at =
                    At(WavePoint(start.GetPositionX(), start.GetPositionY(), heading, i, beasts, length), start);
                After(player, WaveMs(i, beasts, DelaySeconds(), Numbers::Num(spellId, "dot_duration_seconds")),
                      [=]
                      {
                          for (Unit* enemy :
                               Rain(player, spellId, at, Tune("rain_of_vengeance_stampede_radius_yards"), pct))
                              Abilities::Knockback(player, enemy, Tune("rain_of_vengeance_stampede_knockback_yards"));
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
        switch (RuneAt(spellId))
        {
            case Rune::DarkCloud:
                Storms(player, spellId, center);
                break;
            case Rune::Anathema:
                Grenades(player, spellId, center);
                break;
            case Rune::FlyingStrike:
                Flyers(player, spellId, center);
                break;
            case Rune::Stampede:
                Wave(player, spellId, center);
                break;
            default:
                Falls(player, spellId, center);
                break;
        }
    }
} // namespace DC::Combat::DemonHunter::RainOfVengeance
