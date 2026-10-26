/*
 * Firebomb and its five runes. The cast is the engine's single-enemy throw (a spell record and the sheet's numbers:
 * free to cast, the hit on the enemy aimed at, each rune's school); here: the explosion round that enemy, Ghost Bomb's
 * larger blast, Roll the Bones' bounces, Fire Pit's pool, Pyrogeist's columns of flame, Flash Fire's bounce from enemy
 * to enemy in place of the explosion.
 */

#include "dc_witch_doctor_firebomb.h"
#include "dc_witch_doctor_common.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_spell_numbers.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Position.h"
#include "Unit.h"

#include <algorithm>
#include <chrono>
#include <deque>
#include <functional>
#include <mutex>
#include <unordered_map>

namespace DC::Combat::WitchDoctor::Firebomb
{
    namespace
    {
        constexpr std::string_view Skill = "Firebomb";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        // The Pyrogeists each Witch Doctor has standing, oldest first, by the stamp of each: one that gave way finds
        // its stamp gone and stops.
        std::mutex mutex;
        std::unordered_map<std::uint64_t, std::deque<std::uint64_t>> geists;
        std::uint64_t stamps = 0;

        // Work that comes due `ms` after the cast, on the player's own queue, if the Witch Doctor is still there.
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

        // One strike of `pct` on every enemy within `radius` of `at`, but `except`.
        void Blast(Player* player, std::uint32_t spellId, Position const& at, double radius, double pct,
                   Unit const* except)
        {
            for (Unit* enemy : Combat::Enemies(player, spellId, at, radius))
                if (enemy != except)
                    Combat::Strike(player, enemy, spellId, pct);
        }

        // Roll the Bones: "The skull can bounce up to {max_count} times": from where it exploded to the nearest enemy
        // not yet hit within the file's bounce distance, exploding there as it did the first time.
        void Bounces(Player* player, std::uint32_t spellId, Unit* first, double pct)
        {
            std::vector<ObjectGuid> hit{first->GetGUID()};
            Position where = first->GetPosition();
            for (unsigned bounce = 0, most = unsigned(Numbers::Num(spellId, "max_count")); bounce < most; ++bounce)
            {
                auto const enemies = Combat::Enemies(player, spellId, where, Tune("firebomb_bounce_distance_yards"));
                std::vector<double> distances;
                std::vector<bool> seen;
                for (Unit* enemy : enemies)
                {
                    distances.push_back(enemy->GetExactDist(&where));
                    seen.push_back(std::find(hit.begin(), hit.end(), enemy->GetGUID()) != hit.end());
                }
                std::size_t const next = NextBounce(distances, seen, Tune("firebomb_bounce_distance_yards"));
                if (next >= enemies.size())
                    return;
                hit.push_back(enemies[next]->GetGUID());
                where = enemies[next]->GetPosition();
                Combat::Strike(player, enemies[next], spellId, pct);
                Blast(player, spellId, where, Numbers::Num(BaseId(Skill), "radius_yards"), pct, enemies[next]);
            }
        }

        // Fire Pit: "a pool of fire that deals {damage_pct} weapon damage as Fire over {dot_duration_seconds} seconds"
        // where it exploded.
        void Pool(Player* player, std::uint32_t spellId, Position const& where)
        {
            unsigned const ticks =
                PeriodicStrike::Ticks(Numbers::Num(spellId, "dot_duration_seconds"), Tune("firebomb_pit_tick_seconds"));
            double const pct = PeriodicStrike::TickPct(Numbers::Num(spellId, "damage_pct"), ticks);
            for (unsigned tick = 0; tick < ticks; ++tick)
                After(player, SpewMs(tick, Tune("firebomb_pit_tick_seconds")),
                      [=]
                      {
                          for (Unit* enemy :
                               Combat::Enemies(player, spellId, where, Numbers::Num(BaseId(Skill), "radius_yards")))
                              Combat::Strike(player, enemy, spellId, pct, true);
                      });
        }

        // Pyrogeist: "a column of flame that spews fire at the closest enemy for {damage_pct} weapon damage as Fire
        // over {dot_duration_seconds} seconds", up to `max_count` at a time (the oldest gives way).
        void Column(Player* player, std::uint32_t spellId, Position const& where)
        {
            std::uint64_t stamp;
            {
                std::lock_guard<std::mutex> guard(mutex);
                stamp = ++stamps;
                auto& standing = geists[player->GetGUID().GetRawValue()];
                for (std::size_t gone = Retired(standing.size(), std::size_t(Numbers::Num(spellId, "max_count")));
                     gone > 0; --gone)
                    standing.pop_front();
                standing.push_back(stamp);
            }
            unsigned const spews = PeriodicStrike::Ticks(Numbers::Num(spellId, "dot_duration_seconds"),
                                                         Tune("firebomb_pyrogeist_tick_seconds"));
            double const pct = PeriodicStrike::TickPct(Numbers::Num(spellId, "damage_pct"), spews);
            for (unsigned spew = 0; spew < spews; ++spew)
                After(player, SpewMs(spew, Tune("firebomb_pyrogeist_tick_seconds")),
                      [=]
                      {
                          {
                              std::lock_guard<std::mutex> guard(mutex);
                              auto const found = geists.find(player->GetGUID().GetRawValue());
                              if (found == geists.end() ||
                                  std::find(found->second.begin(), found->second.end(), stamp) == found->second.end())
                                  return;
                          }
                          Unit* closest = nullptr;
                          for (Unit* enemy :
                               Combat::Enemies(player, spellId, where, Tune("firebomb_pyrogeist_range_yards")))
                              if (!closest || enemy->GetExactDist(&where) < closest->GetExactDist(&where))
                                  closest = enemy;
                          if (closest)
                              Combat::Strike(player, closest, spellId, pct, true);
                      });
        }

        // Flash Fire: "each Firebomb can bounce to up to {target_count} additional enemies. Damage is reduced by
        // {damage_dealt_reduction_pct} per bounce": from each enemy to the nearest not yet hit within the file's
        // selection radius, a delay apart.
        void Chain(Player* player, std::uint32_t spellId, Unit* first, double pct)
        {
            std::vector<ObjectGuid> hit{first->GetGUID()};
            Position where = first->GetPosition();
            for (unsigned bounce = 0, most = unsigned(Numbers::Num(spellId, "target_count")); bounce < most; ++bounce)
            {
                auto const enemies = Combat::Enemies(player, spellId, where, Tune("firebomb_flash_radius_yards"));
                std::vector<double> distances;
                std::vector<bool> seen;
                for (Unit* enemy : enemies)
                {
                    distances.push_back(enemy->GetExactDist(&where));
                    seen.push_back(std::find(hit.begin(), hit.end(), enemy->GetGUID()) != hit.end());
                }
                std::size_t const next = NextBounce(distances, seen, Tune("firebomb_flash_radius_yards"));
                if (next >= enemies.size())
                    return;
                hit.push_back(enemies[next]->GetGUID());
                where = enemies[next]->GetPosition();
                double const reduced = FlashPct(pct, bounce + 1, Numbers::Num(spellId, "damage_dealt_reduction_pct"));
                After(player, BounceMs(bounce, Tune("firebomb_flash_delay_seconds")),
                      [player, spellId, guid = enemies[next]->GetGUID(), reduced]
                      {
                          Unit* target = ObjectAccessor::GetUnit(*player, guid);
                          if (target && target->IsAlive())
                              Combat::Strike(player, target, spellId, reduced);
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
        // Every rune's own damage_pct is its extra blast's, pool's or Pyrogeist's: the explosion is the skill's.
        return Is(spellId) ? std::optional<double>(Numbers::Num(BaseId(Skill), "damage_pct")) : std::nullopt;
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        if (!player || !Is(spellId) || targets.empty())
            return;
        Unit* aim = targets.front();
        Rune const rune = RuneAt(spellId);
        double const pct = Numbers::Num(BaseId(Skill), "damage_pct");
        if (rune == Rune::FlashFire)
        {
            // "Rather than exploding for area damage": the hit on the enemy aimed at, then the bounces.
            Chain(player, spellId, aim, pct);
            return;
        }
        // "Lob an explosive skull that deals {damage_pct} weapon damage as Fire to all enemies within {radius_yards}
        // yards": the enemy aimed at took the engine's hit, the others near it take the same.
        Position const where = aim->GetPosition();
        Blast(player, spellId, where, Numbers::Num(BaseId(Skill), "radius_yards"), pct, aim);
        switch (rune)
        {
            case Rune::GhostBomb:
                // "a larger blast that deals an additional {damage_pct} weapon damage as Cold to all other enemies
                // within {radius_yards} yards."
                Blast(player, spellId, where, Numbers::Num(spellId, "radius_yards"),
                      Numbers::Num(spellId, "damage_pct"), aim);
                break;
            case Rune::RollTheBones:
                Bounces(player, spellId, aim, pct);
                break;
            case Rune::FirePit:
                Pool(player, spellId, where);
                break;
            case Rune::Pyrogeist:
                Column(player, spellId, where);
                break;
            default:
                break;
        }
    }
} // namespace DC::Combat::WitchDoctor::Firebomb
