/*
 * Haunt and its five runes. The cast is the engine's single-enemy cast (a spell record and the sheet's numbers: the
 * Mana cost, each rune's school); here: the spirit that damages its host tick by tick, jumps to another enemy when the
 * host dies, and is one of five at most; Consuming Spirit's Life, Lingering Spirit's search, Poisoned Spirit's
 * weakness, Draining Spirit's Mana, Resentful Spirits' second spirit.
 */

#include "dc_witch_doctor_haunt.h"
#include "dc_witch_doctor_common.h"
#include "dc_witch_doctor_effects.h"
#include "dc_witch_doctor_mana.h"
#include "../dc_classes.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_enemy_effects.h"
#include "../../combat/dc_healing_table.h"
#include "../../combat/dc_periodic_strike.h"
#include "../../combat/dc_spell_numbers.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Unit.h"

#include <algorithm>
#include <chrono>
#include <map>
#include <mutex>

namespace DC::Combat::WitchDoctor::Haunt
{
    namespace
    {
        constexpr std::string_view Skill = "Haunt";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        struct Spirit
        {
            std::uint64_t stamp = 0;
            std::uint64_t order = 0; // the order spirits were released in
            std::uint32_t spellId = 0;
            ObjectGuid host;
            Position lastSeen;      // where the host stood when it was last struck
            double leftSeconds = 0; // what is left of the haunt
            bool lingering = false; // the host fell and no enemy was near
            double waited = 0;      // seconds lingered
            double checkClock = 0;  // ms since the last search
        };
        std::mutex mutex;
        std::map<std::uint64_t, std::vector<Spirit>> spirits; // by player
        std::uint64_t counter = 0;

        double Duration()
        {
            return Numbers::Num(BaseId(Skill), "dot_duration_seconds");
        }

        std::uint32_t TickMs()
        {
            return std::uint32_t(Tune("haunt_tick_seconds") * 1000.0 + 0.5);
        }

        // The hosts of the Witch Doctor's spirits, and what is left of each haunt.
        std::map<ObjectGuid, double> Hosts(Player* player)
        {
            std::map<ObjectGuid, double> out;
            std::lock_guard<std::mutex> guard(mutex);
            for (Spirit const& spirit : spirits[player->GetGUID().GetRawValue()])
                if (!spirit.lingering)
                    out[spirit.host] = spirit.leftSeconds;
            return out;
        }

        // The enemy nearest `center` within `radius` that no spirit holds (and not `except`).
        Unit* NearestFree(Player* player, std::uint32_t spellId, Position const& center, double radius, Unit* except)
        {
            auto const held = Hosts(player);
            std::vector<Unit*> free;
            std::vector<double> distances;
            for (Unit* enemy : Combat::Enemies(player, spellId, center, radius))
                if (enemy != except && enemy->IsAlive() && !held.count(enemy->GetGUID()))
                {
                    free.push_back(enemy);
                    distances.push_back(center.GetExactDist(enemy));
                }
            auto const nearest = Nearest(distances);
            return nearest ? free[*nearest] : nullptr;
        }

        // Poisoned Spirit: "Haunted enemies take {damage_taken_pct} more damage from your attacks."
        void Weaken(Unit* host, std::uint32_t spellId, double seconds)
        {
            if (RuneAt(spellId) == Rune::PoisonedSpirit)
                EnemyEffects::Taken(host, spellId, Numbers::Num(spellId, "damage_taken_pct"), seconds);
        }

        void Drop(Player* player, std::uint64_t stamp)
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto& mine = spirits[player->GetGUID().GetRawValue()];
            mine.erase(std::remove_if(mine.begin(), mine.end(), [stamp](Spirit const& s) { return s.stamp == stamp; }),
                       mine.end());
        }

        void Tick(Player* player, std::uint64_t stamp);

        void Schedule(Player* player, std::uint64_t stamp)
        {
            player->m_Events.AddEventAtOffset([player, stamp] { Tick(player, stamp); },
                                              std::chrono::milliseconds(TickMs()));
        }

        // The spirit's tick: the host's damage and what the rune returns, or, the host fallen, the jump.
        void Tick(Player* player, std::uint64_t stamp)
        {
            Spirit spirit;
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto& mine = spirits[player->GetGUID().GetRawValue()];
                auto found =
                    std::find_if(mine.begin(), mine.end(), [stamp](Spirit const& s) { return s.stamp == stamp; });
                if (found == mine.end())
                    return;
                spirit = *found;
            }
            if (!player->IsAlive() || !player->IsInWorld())
            {
                Drop(player, stamp);
                return;
            }
            std::uint32_t const spellId = spirit.spellId;
            Rune const rune = RuneAt(spellId);
            double const tick = Tune("haunt_tick_seconds");
            if (spirit.lingering)
            {
                // "the spirit will linger for up to {duration_seconds} seconds looking for new enemies": a search every
                // check interval.
                spirit.waited += tick;
                if (Due(spirit.checkClock, tick * 1000.0, Tune("haunt_jump_check_seconds") * 1000.0))
                    if (Unit* next = NearestFree(player, spellId, spirit.lastSeen, Tune("haunt_spread_yards"), nullptr))
                    {
                        spirit.host = next->GetGUID();
                        spirit.lastSeen = next->GetPosition();
                        spirit.lingering = false;
                        Weaken(next, spellId, spirit.leftSeconds);
                    }
                if (spirit.lingering && !StillLooking(spirit.waited, Numbers::Num(spellId, "duration_seconds")))
                {
                    Drop(player, stamp);
                    return;
                }
            }
            else if (Unit* host = ObjectAccessor::GetUnit(*player, spirit.host); host && host->IsAlive())
            {
                spirit.lastSeen = host->GetPosition();
                unsigned const ticks = PeriodicStrike::Ticks(Duration(), tick);
                Combat::Strike(player, host, spellId,
                               PeriodicStrike::TickPct(Numbers::Num(spellId, "damage_pct"), ticks), true);
                if (rune == Rune::ConsumingSpirit)
                    Heal(player, spellId,
                         PerTick(LifePerSecond(Tune("haunt_consuming_healing_share"), Healing::At(player->GetLevel())),
                                 tick));
                else if (rune == Rune::DrainingSpirit)
                    Gain(player, Classes::ClassIdOf(player), spellId,
                         PerTick(ManaPerSecond(Tune("haunt_draining_total_mana"), Duration()), tick), 1);
                spirit.leftSeconds = Left(spirit.leftSeconds, tick);
                if (spirit.leftSeconds <= 0)
                {
                    Drop(player, stamp);
                    return;
                }
            }
            else
            {
                // "If the enemy dies, the spirit will haunt another nearby enemy."
                if (Unit* next = NearestFree(player, spellId, spirit.lastSeen, Tune("haunt_spread_yards"), host))
                {
                    spirit.host = next->GetGUID();
                    spirit.lastSeen = next->GetPosition();
                    Weaken(next, spellId, spirit.leftSeconds);
                }
                else if (rune == Rune::LingeringSpirit)
                {
                    spirit.lingering = true;
                    spirit.waited = 0;
                    spirit.checkClock = 0;
                }
                else
                {
                    Drop(player, stamp);
                    return;
                }
            }
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto& mine = spirits[player->GetGUID().GetRawValue()];
                auto found =
                    std::find_if(mine.begin(), mine.end(), [stamp](Spirit const& s) { return s.stamp == stamp; });
                if (found == mine.end())
                    return;
                *found = spirit;
            }
            Schedule(player, stamp);
        }

        // One spirit on `host`: a spirit already on it is replaced, and the oldest of five gives way.
        void Release(Player* player, std::uint32_t spellId, Unit* host)
        {
            Spirit spirit;
            spirit.spellId = spellId;
            spirit.host = host->GetGUID();
            spirit.lastSeen = host->GetPosition();
            spirit.leftSeconds = Duration();
            Unit* displaced = nullptr;
            std::uint32_t displacedSpell = 0;
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto& mine = spirits[player->GetGUID().GetRawValue()];
                mine.erase(std::remove_if(mine.begin(), mine.end(),
                                          [&](Spirit const& s) { return s.host == spirit.host && !s.lingering; }),
                           mine.end());
                std::vector<std::uint64_t> orders;
                for (Spirit const& s : mine)
                    orders.push_back(s.order);
                if (auto const oldest = Displaced(orders, unsigned(Tune("haunt_max_spirits"))))
                {
                    displacedSpell = mine[*oldest].spellId;
                    displaced = ObjectAccessor::GetUnit(*player, mine[*oldest].host);
                    mine.erase(mine.begin() + *oldest);
                }
                spirit.stamp = ++counter;
                spirit.order = spirit.stamp;
                mine.push_back(spirit);
            }
            if (displaced)
                EnemyEffects::Remove(displaced, displacedSpell);
            Weaken(host, spellId, spirit.leftSeconds);
            Schedule(player, spirit.stamp);
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

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        if (!player || targets.empty() || !Is(spellId))
            return;
        Unit* aimed = targets.front();
        // "An enemy can only be affected by one Haunt at a time": a cast at an enemy a spirit holds passes to the
        // nearest free one within the cursor's reach, and renews the old spirit when there is none.
        Unit* first = aimed;
        auto const held = Hosts(player);
        if (auto const found = held.find(aimed->GetGUID());
            found != held.end() && PassesOver(found->second, Tune("haunt_skip_below_seconds")))
            if (Unit* other = NearestFree(player, spellId, aimed->GetPosition(), Tune("haunt_cursor_yards"), aimed))
                first = other;
        Release(player, spellId, first);
        // "Release two spirits with every cast": the second on the nearest free enemy to the first within the cursor's
        // reach.
        for (unsigned more = 1, count = Spirits(RuneAt(spellId), Tune("haunt_resentful_spirit_count")); more < count;
             ++more)
            if (Unit* other = NearestFree(player, spellId, first->GetPosition(), Tune("haunt_cursor_yards"), first))
                Release(player, spellId, other);
    }
} // namespace DC::Combat::WitchDoctor::Haunt
