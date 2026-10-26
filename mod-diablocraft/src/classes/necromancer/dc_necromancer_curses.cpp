/*
 * The Necromancer's curses (dc_necromancer_curses.h): which curse is on which enemy and until when. A new curse on an enemy that
 * bears another of the Necromancer's lifts the old one through the way its skill defined.
 */

#include "dc_necromancer_curses.h"
#include "dc_necromancer_curses_math.h"
#include "dc_necromancer_common.h"

#include "GameTime.h"
#include "ObjectAccessor.h"

#include <chrono>
#include <map>
#include <mutex>
#include <string>
#include <tuple>
#include <vector>

namespace DC::Combat::Necromancer::Curses
{
    namespace
    {
        struct Curse
        {
            std::uint32_t spellId = 0;
            std::uint64_t until = 0;
        };
        // By Necromancer, enemy and skill; the entries that ran out are swept when the table grows.
        constexpr std::size_t SweptAt = 512;
        using Key = std::tuple<std::uint64_t, std::uint64_t, std::string>;
        std::mutex mutex;
        std::map<Key, Curse> curses;
        std::map<std::string, Lift, std::less<>> lifts;
        Together together = nullptr;

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }
    } // namespace

    void Define(std::string_view skill, Lift lift)
    {
        std::lock_guard<std::mutex> guard(mutex);
        lifts[std::string(skill)] = lift;
    }

    void StandTogether(Together allowed)
    {
        std::lock_guard<std::mutex> guard(mutex);
        together = allowed;
    }

    void Put(Player* player, Unit* enemy, std::uint32_t spellId, double seconds)
    {
        if (!player || !enemy || seconds <= 0)
            return;
        auto const* added = Shells::FindAbility(spellId);
        std::string const skill = added ? added->skill : std::string();
        std::uint64_t const owner = player->GetGUID().GetRawValue(), target = enemy->GetGUID().GetRawValue();
        bool const stand = [&]
        {
            Together allowed;
            {
                std::lock_guard<std::mutex> guard(mutex);
                allowed = together;
            }
            return allowed && allowed(player);
        }();
        std::vector<std::pair<Lift, std::uint32_t>> lifted;
        {
            std::lock_guard<std::mutex> guard(mutex);
            std::uint64_t const now = Now();
            if (curses.size() >= SweptAt)
                for (auto it = curses.begin(); it != curses.end();)
                    it = it->second.until <= now ? curses.erase(it) : std::next(it);
            auto const lifter = [&](std::uint32_t held, bool sameSkill, bool live)
            {
                if (!Lifts(stand, sameSkill, live, held, spellId))
                    return;
                if (auto const* row = Shells::FindAbility(held))
                    if (auto const found = lifts.find(row->skill); found != lifts.end())
                        lifted.emplace_back(found->second, held);
            };
            // The curses of the other skills on this enemy go unless the curses stand together.
            for (auto it = curses.lower_bound(Key{owner, target, std::string()});
                 it != curses.end() && std::get<0>(it->first) == owner && std::get<1>(it->first) == target;)
            {
                if (std::get<2>(it->first) == skill || stand)
                {
                    ++it;
                    continue;
                }
                lifter(it->second.spellId, false, now < it->second.until);
                it = curses.erase(it);
            }
            Curse& held = curses[Key{owner, target, skill}];
            lifter(held.spellId, true, now < held.until);
            held = {spellId, now + std::uint64_t(seconds * 1000.0 + 0.5)};
        }
        for (auto const& [lift, held] : lifted)
            lift(player, enemy, held);
    }

    std::uint32_t On(Player* player, Unit const* enemy, std::string_view skill)
    {
        if (!player || !enemy)
            return 0;
        std::uint64_t const owner = player->GetGUID().GetRawValue(), target = enemy->GetGUID().GetRawValue();
        std::lock_guard<std::mutex> guard(mutex);
        std::uint64_t const now = Now();
        for (auto it = curses.lower_bound(Key{owner, target, std::string()});
             it != curses.end() && std::get<0>(it->first) == owner && std::get<1>(it->first) == target; ++it)
            if (now < it->second.until && (skill.empty() || std::get<2>(it->first) == skill))
                return it->second.spellId;
        return 0;
    }

    unsigned Cursed(Player* player)
    {
        if (!player)
            return 0;
        std::uint64_t const owner = player->GetGUID().GetRawValue();
        std::vector<std::uint64_t> enemies;
        {
            std::lock_guard<std::mutex> guard(mutex);
            std::uint64_t const now = Now();
            for (auto it = curses.lower_bound(Key{owner, 0, std::string()}); it != curses.end() && std::get<0>(it->first) == owner;)
                if (it->second.until <= now)
                    it = curses.erase(it);
                else
                {
                    if (enemies.empty() || enemies.back() != std::get<1>(it->first))
                        enemies.push_back(std::get<1>(it->first));
                    ++it;
                }
        }
        unsigned count = 0;
        for (std::uint64_t guid : enemies)
            if (Unit* unit = ObjectAccessor::GetUnit(*player, ObjectGuid(guid)); unit && unit->IsAlive())
                ++count;
        return count;
    }

    std::vector<std::pair<Unit*, std::uint32_t>> CursedBy(Player* player)
    {
        std::vector<std::pair<std::uint64_t, std::uint32_t>> held;
        if (!player)
            return {};
        {
            std::lock_guard<std::mutex> guard(mutex);
            std::uint64_t const owner = player->GetGUID().GetRawValue(), now = Now();
            for (auto it = curses.lower_bound(Key{owner, 0, std::string()}); it != curses.end() && std::get<0>(it->first) == owner; ++it)
                if (now < it->second.until)
                    held.emplace_back(std::get<1>(it->first), it->second.spellId);
        }
        std::vector<std::pair<Unit*, std::uint32_t>> out;
        for (auto const& [guid, spellId] : held)
            if (Unit* unit = ObjectAccessor::GetUnit(*player, ObjectGuid(guid)); unit && unit->IsAlive())
                out.emplace_back(unit, spellId);
        return out;
    }

    double Left(Player* player, Unit const* enemy, std::string_view skill)
    {
        if (!player || !enemy)
            return 0.0;
        std::uint64_t const owner = player->GetGUID().GetRawValue(), target = enemy->GetGUID().GetRawValue();
        std::lock_guard<std::mutex> guard(mutex);
        std::uint64_t const now = Now();
        for (auto it = curses.lower_bound(Key{owner, target, std::string()});
             it != curses.end() && std::get<0>(it->first) == owner && std::get<1>(it->first) == target; ++it)
            if (now < it->second.until && (skill.empty() || std::get<2>(it->first) == skill))
                return (it->second.until - now) / 1000.0;
        return 0.0;
    }

    std::vector<std::pair<Player*, std::uint32_t>> Cursers(Unit const* enemy)
    {
        std::vector<std::pair<std::uint64_t, std::uint32_t>> held;
        if (!enemy)
            return {};
        {
            std::lock_guard<std::mutex> guard(mutex);
            std::uint64_t const now = Now();
            for (auto const& [key, curse] : curses)
                if (std::get<1>(key) == enemy->GetGUID().GetRawValue() && now < curse.until)
                    held.emplace_back(std::get<0>(key), curse.spellId);
        }
        std::vector<std::pair<Player*, std::uint32_t>> out;
        for (auto const& [guid, spellId] : held)
            if (Player* player = ObjectAccessor::FindConnectedPlayer(ObjectGuid(guid)); player && player->IsInWorld())
                out.emplace_back(player, spellId);
        return out;
    }

    namespace
    {
        struct Follower
        {
            std::uint64_t stamp = 0;
            std::uint32_t spellId = 0;
            Apply apply = nullptr;
        };
        constexpr std::chrono::milliseconds FollowEvery{1000};
        std::map<std::pair<std::uint64_t, std::string>, Follower, std::less<>> followers;
        std::uint64_t stamps = 0;

        void Tick(Player* player, std::string group, std::uint64_t stamp)
        {
            Follower follower;
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto const found = followers.find({player->GetGUID().GetRawValue(), group});
                if (found == followers.end() || found->second.stamp != stamp)
                    return;
                follower = found->second;
            }
            if (!player->IsInWorld())
                return;
            unsigned const cursed = Cursed(player);
            follower.apply(player, follower.spellId, cursed);
            if (cursed == 0)
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto const found = followers.find({player->GetGUID().GetRawValue(), group});
                if (found != followers.end() && found->second.stamp == stamp)
                    followers.erase(found);
                return;
            }
            player->m_Events.AddEventAtOffset([player, group, stamp] { Tick(player, group, stamp); }, FollowEvery);
        }
    } // namespace

    void Follow(Player* player, std::string_view group, std::uint32_t spellId, Apply apply)
    {
        if (!player || !apply)
            return;
        Follower old;
        std::uint64_t stamp;
        {
            std::lock_guard<std::mutex> guard(mutex);
            Follower& held = followers[{player->GetGUID().GetRawValue(), std::string(group)}];
            old = held;
            held = {stamp = ++stamps, spellId, apply};
        }
        if (old.stamp && old.spellId != spellId)
            old.apply(player, old.spellId, 0);
        Tick(player, std::string(group), stamp);
    }

    void Unfollow(Player* player, std::string_view group)
    {
        if (!player)
            return;
        Follower old;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto const found = followers.find({player->GetGUID().GetRawValue(), std::string(group)});
            if (found == followers.end())
                return;
            old = found->second;
            followers.erase(found);
        }
        old.apply(player, old.spellId, 0);
    }
} // namespace DC::Combat::Necromancer::Curses
