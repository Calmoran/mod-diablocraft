#pragma once
// What a skill or passive adds to the maximum of a class's second resource (the Demon Hunter's Discipline), kept per
// player and source. The second resource's maximum is its pool (class_resources.csv) and the stats add this to it.
// Header-only so the harness of a skill that uses it compiles this exact code.
#include <cstdint>
#include <map>
#include <mutex>

namespace DC::Resources::Pool
{
    namespace Detail
    {
        inline std::mutex& Mutex()
        {
            static std::mutex mutex;
            return mutex;
        }

        // Points by player, then by the source (a spell id) that gives them.
        inline std::map<std::uint64_t, std::map<std::uint32_t, double>>& Table()
        {
            static std::map<std::uint64_t, std::map<std::uint32_t, double>> table;
            return table;
        }
    } // namespace Detail

    // The points the player's sources add to the second resource's maximum.
    inline double Bonus(std::uint64_t guid)
    {
        std::lock_guard<std::mutex> guard(Detail::Mutex());
        auto found = Detail::Table().find(guid);
        double sum = 0;
        if (found != Detail::Table().end())
            for (auto const& [source, points] : found->second)
                sum += points;
        return sum;
    }

    // The second resource's maximum in points: its pool, what skills add (Bonus) and what gear adds (Stat::MaxSecond).
    inline double Maximum(double pool, std::uint64_t guid, double gear)
    {
        return pool + Bonus(guid) + gear;
    }

    // `source` gives `points` (none removes it). True when the player's bonus changed.
    inline bool Set(std::uint64_t guid, std::uint32_t source, double points)
    {
        std::lock_guard<std::mutex> guard(Detail::Mutex());
        auto& mine = Detail::Table()[guid];
        auto found = mine.find(source);
        double const before = found == mine.end() ? 0.0 : found->second;
        if (points > 0)
            mine[source] = points;
        else if (found != mine.end())
            mine.erase(found);
        if (mine.empty())
            Detail::Table().erase(guid);
        return before != (points > 0 ? points : 0.0);
    }

    inline void Clear(std::uint64_t guid)
    {
        std::lock_guard<std::mutex> guard(Detail::Mutex());
        Detail::Table().erase(guid);
    }
} // namespace DC::Resources::Pool
