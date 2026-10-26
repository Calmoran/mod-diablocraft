/*
 * Elemental Arrow and its five runes. The arrow is the engine's shot (a spell record and the sheet's numbers); here:
 * Frost Arrow's chill and the cone of arrows it splits into, Ball Lightning's and Nether Tentacles' slow projectiles
 * that strike what is near them as they fly, Immolation Arrow's burning ground, Lightning Bolts' stun on a critical
 * hit.
 */

#include "dc_demon_hunter_elemental_arrow.h"
#include "dc_demon_hunter_common.h"
#include "dc_demon_hunter_effects.h"
#include "dc_demon_hunter_seek.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_spell_numbers.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Position.h"
#include "ScriptMgr.h"
#include "Unit.h"

#include <algorithm>
#include <cmath>
#include <mutex>
#include <unordered_map>

namespace DC::Combat::DemonHunter::ElementalArrow
{
    namespace
    {
        constexpr std::string_view Skill = "Elemental Arrow";
        // Ball Lightning's tick shocks each enemy twice: the rune's damage is for both.
        constexpr unsigned ShocksPerTick = 2;

        // The cone's strikes and the burning ground's land too; they must not split or burn anything again.
        thread_local bool splitting = false;
        thread_local bool burning = false;

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        // A slow projectile in flight: Ball Lightning's ball or Nether Tentacles' tentacle.
        struct Flight
        {
            std::uint32_t spellId = 0;
            Position origin;
            float heading = 0;
            double elapsed = 0; // ms since it left
            double clock = 0;   // ms since its last tick
        };
        // Immolation Arrow's burning ground.
        struct Burning
        {
            std::uint32_t spellId = 0;
            Position center;
            double left = 0;  // ms it burns
            double clock = 0; // ms since the last tick
        };
        struct State
        {
            std::vector<Flight> flights;
            std::vector<Burning> grounds;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, State> states;

        // "Ball Lightning ... electrocutes enemies": each tick shocks every enemy within the seek radius of the ball,
        // the second shock a moment after the first.
        void Shock(Player* player, Flight const& flight, Position const& at)
        {
            std::uint32_t const spellId = flight.spellId;
            double const pct = ShockPct(Numbers::Num(spellId, "damage_pct"), ShocksPerTick);
            std::vector<ObjectGuid> struck;
            for (Unit* enemy : Combat::Enemies(player, spellId, at, Tune("elemental_arrow_ball_seek_yards")))
                if (Combat::Strike(player, enemy, spellId, pct))
                    struck.push_back(enemy->GetGUID());
            if (struck.empty())
                return;
            player->m_Events.AddEventAtOffset(
                [player, spellId, pct, struck]
                {
                    if (!player->IsAlive() || !player->IsInWorld())
                        return;
                    for (ObjectGuid guid : struck)
                        if (Unit* enemy = ObjectAccessor::GetUnit(*player, guid); enemy && enemy->IsAlive())
                            Combat::Strike(player, enemy, spellId, pct);
                },
                std::chrono::milliseconds(std::uint32_t(Tune("elemental_arrow_ball_shock_delay_seconds") * 1000.0)));
        }

        // "Nether Tentacles ... deals {damage_pct} weapon damage ... to enemies along its path and returns {heal_pct}
        // of your maximum Life for each enemy hit": each tick strikes every enemy within the tentacle's radius.
        void Tentacle(Player* player, Flight const& flight, Position const& at)
        {
            std::uint32_t const spellId = flight.spellId;
            unsigned hits = 0;
            for (Unit* enemy : Combat::Enemies(player, spellId, at, Tune("elemental_arrow_tentacle_radius_yards")))
                if (Combat::Strike(player, enemy, spellId, Numbers::Num(spellId, "damage_pct")))
                    ++hits;
            Heal(player, spellId, TentacleHeal(player->GetMaxHealth(), Numbers::Num(spellId, "heal_pct"), hits));
        }

        // Where a flight is `flown` yards along its line.
        Position At(Flight const& flight, double flown)
        {
            Position at = flight.origin;
            at.m_positionX += float(std::cos(flight.heading) * flown);
            at.m_positionY += float(std::sin(flight.heading) * flown);
            return at;
        }

        void Fly(Player* player, Flight& flight, uint32 diff, bool& over)
        {
            double const speed = Tune("elemental_arrow_slow_projectile_yards_per_second"),
                         travel = Tune("elemental_arrow_travel_yards");
            bool const ball = RuneAt(flight.spellId) == Rune::BallLightning;
            flight.elapsed += diff;
            double const flown = Flown(speed, flight.elapsed, travel);
            Position const at = At(flight, flown);
            unsigned const ticks = Due(
                flight.clock, diff,
                Tune(ball ? "elemental_arrow_ball_tick_seconds" : "elemental_arrow_tentacle_tick_seconds") * 1000.0);
            for (unsigned i = 0; i < ticks; ++i)
                ball ? Shock(player, flight, at) : Tentacle(player, flight, at);
            over = Arrived(flown, travel);
        }

        // "immolating the ground for {damage_pct:ground} weapon damage as Fire over {dot_duration_seconds} seconds to
        // enemies within {radius_yards} yards": each tick of the ground strikes whoever stands in it.
        void Burn(Player* player, Burning& ground, uint32 diff, bool& over)
        {
            std::uint32_t const spellId = ground.spellId;
            double const tick = Tune("elemental_arrow_immolation_tick_seconds"),
                         seconds = Numbers::Num(spellId, "dot_duration_seconds"),
                         pct = GroundTickPct(Numbers::Num(spellId, "damage_pct", "ground"), seconds, tick);
            ground.left -= diff;
            Scope scope(burning);
            unsigned const ticks = Due(ground.clock, diff, tick * 1000.0);
            for (unsigned i = 0; i < ticks; ++i)
                for (Unit* enemy :
                     Combat::Enemies(player, spellId, ground.center, Numbers::Num(spellId, "radius_yards")))
                    Combat::Strike(player, enemy, spellId, pct, true);
            over = ground.left <= 0;
        }

        class Flights final : public PlayerScript
        {
        public:
            Flights()
                : PlayerScript("dc_demon_hunter_elemental_arrow",
                               {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_MAP_CHANGED})
            {
            }

            void OnPlayerUpdate(Player* player, uint32 diff) override
            {
                State state;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    auto found = states.find(player->GetGUID().GetRawValue());
                    if (found == states.end())
                        return;
                    state = found->second;
                }
                if (!player->IsAlive())
                {
                    Stop(player);
                    return;
                }
                State kept;
                for (Flight& flight : state.flights)
                {
                    bool over = false;
                    Fly(player, flight, diff, over);
                    if (!over)
                        kept.flights.push_back(flight);
                }
                for (Burning& ground : state.grounds)
                {
                    bool over = false;
                    Burn(player, ground, diff, over);
                    if (!over)
                        kept.grounds.push_back(ground);
                }
                std::lock_guard<std::mutex> guard(mutex);
                // Casts made during this update were added to the stored state; keep them with what is still running.
                auto found = states.find(player->GetGUID().GetRawValue());
                if (found == states.end())
                    return;
                State& stored = found->second;
                for (std::size_t i = state.flights.size(); i < stored.flights.size(); ++i)
                    kept.flights.push_back(stored.flights[i]);
                for (std::size_t i = state.grounds.size(); i < stored.grounds.size(); ++i)
                    kept.grounds.push_back(stored.grounds[i]);
                stored = std::move(kept);
            }

            void OnPlayerLogout(Player* player) override
            {
                Stop(player);
            }

            void OnPlayerMapChanged(Player* player) override
            {
                Stop(player);
            }

            static void Stop(Player* player)
            {
                std::lock_guard<std::mutex> guard(mutex);
                states.erase(player->GetGUID().GetRawValue());
            }
        };

        // Frost Arrow: "then splits into up to {max_count} additional frost arrows": the nearest enemies in the cone
        // behind the one struck, a moment after it, each for the arrow's hit and each chilled.
        void Split(Player* player, std::uint32_t spellId, Unit* first)
        {
            std::vector<Unit*> around;
            std::vector<double> distances, bearings;
            std::vector<bool> flags;
            double const radius = Tune("elemental_arrow_cone_radius_yards");
            for (Unit* enemy : Combat::Enemies(player, spellId, first->GetPosition(), radius))
            {
                around.push_back(enemy);
                distances.push_back(first->GetExactDist(enemy));
                bearings.push_back(first->GetAngle(enemy));
                flags.push_back(enemy == first);
            }
            std::vector<ObjectGuid> arrows;
            for (std::size_t index :
                 Seek(distances, bearings, flags, radius, player->GetAngle(first), Tune("elemental_arrow_cone_degrees"),
                      std::size_t(Numbers::Num(spellId, "max_count"))))
                arrows.push_back(around[index]->GetGUID());
            if (arrows.empty())
                return;
            player->m_Events.AddEventAtOffset(
                [player, spellId, arrows]
                {
                    if (!player->IsAlive() || !player->IsInWorld())
                        return;
                    Scope scope(splitting);
                    for (ObjectGuid guid : arrows)
                        if (Unit* enemy = ObjectAccessor::GetUnit(*player, guid); enemy && enemy->IsAlive())
                            if (Combat::Strike(player, enemy, spellId))
                                Slow(player, enemy, Numbers::Num(spellId, "chill_pct"),
                                     Numbers::Num(spellId, "chill_duration_seconds"));
                },
                std::chrono::milliseconds(std::uint32_t(Tune("elemental_arrow_cone_delay_seconds") * 1000.0)));
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        auto const rune = RuneAt(spellId);
        if (rune == Rune::BallLightning || rune == Rune::NetherTentacles)
            return 0.0;
        // The sheet states Immolation Arrow's hit and its ground apart; every other rune's hit is its own (the loader's rule).
        if (rune == Rune::ImmolationArrow)
            return Numbers::Get(spellId, "damage_pct", "hit");
        return std::nullopt;
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId, bool critical)
    {
        if (splitting || burning || !player || !target)
            return;
        switch (RuneAt(spellId))
        {
            case Rune::FrostArrow:
                Slow(player, target, Numbers::Num(spellId, "chill_pct"),
                     Numbers::Num(spellId, "chill_duration_seconds"));
                Split(player, spellId, target);
                break;
            case Rune::ImmolationArrow:
            {
                Burning ground;
                ground.spellId = spellId;
                ground.center = target->GetPosition();
                ground.left = Numbers::Num(spellId, "dot_duration_seconds") * 1000.0;
                std::lock_guard<std::mutex> guard(mutex);
                states[player->GetGUID().GetRawValue()].grounds.push_back(ground);
                break;
            }
            case Rune::LightningBolts:
                // "Stuns enemies for {stun_duration_seconds} second on a Critical Hit."
                if (critical)
                    Stun(player, target,
                         Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player));
                break;
            default:
                break;
        }
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        auto const rune = RuneAt(spellId);
        if (!player || targets.empty() || (rune != Rune::BallLightning && rune != Rune::NetherTentacles))
            return;
        Flight flight;
        flight.spellId = spellId;
        flight.origin = player->GetPosition();
        flight.heading = player->GetAngle(targets.front());
        std::lock_guard<std::mutex> guard(mutex);
        states[player->GetGUID().GetRawValue()].flights.push_back(flight);
    }

    void RegisterScripts()
    {
        new Flights();
    }
} // namespace DC::Combat::DemonHunter::ElementalArrow
