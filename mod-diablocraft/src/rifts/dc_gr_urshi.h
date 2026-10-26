/*
 * World of DiabloCraft - Urshi's decisions (contract docs/contracts/urshi-messages.md).
 *
 * What has no core in it: the tries a member gets, the upgrade chance by level minus rank, the roll, the order of the
 * gem list, the gem id the window sends back, and the line that names who still holds the rift open. The numbers are
 * rifts.csv rows, read by dc_gr_urshi.cpp; this file is what the test compiles. Internal to the rifts folder.
 */

#ifndef DC_GR_URSHI_H
#define DC_GR_URSHI_H

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <string>
#include <vector>

namespace DC::Rifts::Gr
{
    // greater_rifts.csv gem_upgrade_attempts: a base number of tries and one more for a member who did not die in
    // the run; a Hardcore character always has the one more (its death is final, so it never "died in the run").
    inline unsigned Tries(unsigned base, unsigned noDeathBonus, unsigned deaths, bool hardcore)
    {
        return base + (hardcore || deaths == 0 ? noDeathBonus : 0);
    }

    // greater_rifts.csv gem_upgrade_chance: twelve bands of (Greater Rift level - the gem's rank).
    constexpr std::size_t ChanceBands = 12;
    using ChanceTable = std::array<unsigned, ChanceBands>; // percent, in the order Band() numbers them

    // +10 or more is band 0, +9 1, +8 2, +7 3, 0 to +6 4, -1 5, -2 6, -3 7, -4 8, -5 9, -6 to -15 10, -16 or less 11.
    inline std::size_t Band(long long difference)
    {
        if (difference >= 10)
            return 0;
        if (difference >= 7)
            return static_cast<std::size_t>(10 - difference);
        if (difference >= 0)
            return 4;
        if (difference >= -5)
            return static_cast<std::size_t>(4 - difference);
        return difference >= -15 ? 10 : 11;
    }

    // The chance of one try, whole percent, at the rift's level for a gem at `rank`. Never above 100.
    inline unsigned UpgradeChance(unsigned level, unsigned rank, ChanceTable const& table)
    {
        return std::min(100u, table[Band(static_cast<long long>(level) - static_cast<long long>(rank))]);
    }

    // `roll` is uniform in [0, 1): 100% always lands, 0% never does.
    inline bool Succeeds(unsigned chancePercent, double roll)
    {
        return roll * 100.0 < static_cast<double>(chancePercent);
    }

    // A gem at its maximum rank (the sheet's max_rank; 0 means the gem has no cap of its own).
    inline bool AtMaxRank(unsigned rank, unsigned maxRank)
    {
        return maxRank > 0 && rank >= maxRank;
    }

    // --- where she stands --------------------------------------------------------------------------------------

    // The ways tried for her spot, in order, as the core's orientation (radians, 0 to 2 pi): `base` first (towards the players), then to
    // each side by 45, 90 and 135 degrees, last straight away from them.
    constexpr std::size_t SpawnTries = 8;

    inline std::array<double, SpawnTries> SpawnAngles(double base)
    {
        constexpr double Pi = 3.14159265358979323846, Step = Pi / 4.0;
        constexpr double order[SpawnTries] = {0, 1, -1, 2, -2, 3, -3, 4};
        std::array<double, SpawnTries> out{};
        for (std::size_t i = 0; i < SpawnTries; ++i)
        {
            double angle = std::fmod(base + order[i] * Step, 2.0 * Pi);
            out[i] = angle < 0 ? angle + 2.0 * Pi : angle;
        }
        return out;
    }

    // The way from one spot to another as the core's orientation (radians, 0 to 2 pi); `fallback` when they are the same spot.
    inline double FacingAngle(double fromX, double fromY, double toX, double toY, double fallback)
    {
        if (fromX == toX && fromY == toY)
            return fallback;
        double const angle = std::atan2(toY - fromY, toX - fromX);
        return angle < 0 ? angle + 2.0 * 3.14159265358979323846 : angle;
    }

    // Whether a spot the core found for her fits: it has line of sight to the Guardian's spot, is at least `minSharePct` percent of the
    // `wantedYards` away along the ground (the core shortens a walk that meets a wall) and no more than `maxClimbYards` above or below it.
    inline bool SpotFits(double wantedYards, double gotYards, double climbYards, bool lineOfSight, double minSharePct, double maxClimbYards)
    {
        return lineOfSight && wantedYards > 0 && gotYards >= wantedYards * minSharePct / 100.0 && std::fabs(climbYards) <= maxClimbYards;
    }

    // --- the list ---------------------------------------------------------------------------------------------

    enum class Where : char
    {
        Worn = 'w',
        Bags = 'b',
        Stash = 's',
    };

    struct GemRow
    {
        std::string id; // the token the window sends back
        Where where = Where::Bags;
        std::uint64_t guid = 0; // the gem item (bags, stash) or the item that holds it (worn)
        unsigned seq = 0;       // worn only: the socket row of that item
        std::uint32_t entry = 0;
        std::string name;
        unsigned rank = 0, maxRank = 0;
    };

    // The server's order: worn gems first, by rank highest first; then bags and stash together, by rank highest
    // first. Equal ranks keep the order the caller read them in (stable), which is slot order for worn gems.
    inline void OrderGems(std::vector<GemRow>& rows)
    {
        std::stable_sort(rows.begin(), rows.end(),
                         [](GemRow const& a, GemRow const& b)
                         {
                             bool const wornA = a.where == Where::Worn, wornB = b.where == Where::Worn;
                             if (wornA != wornB)
                                 return wornA;
                             return a.rank > b.rank;
                         });
    }

    // The gem id: `g<item guid>` for a gem item in the bags or the stash, `w<host item guid>_<socket seq>` for a
    // socketed one (it has no item of its own). The client never builds one; the server finds the row whose id
    // equals what the client sent.
    inline std::string BagGemId(std::uint64_t itemGuid)
    {
        return "g" + std::to_string(itemGuid);
    }

    inline std::string WornGemId(std::uint64_t hostGuid, unsigned seq)
    {
        return "w" + std::to_string(hostGuid) + "_" + std::to_string(seq);
    }

    // "A", "A and B", "A, B and C".
    inline std::string NameList(std::vector<std::string> const& names)
    {
        std::string out;
        for (std::size_t i = 0; i < names.size(); ++i)
            out += (i == 0 ? "" : i + 1 == names.size() ? " and " : ", ") + names[i];
        return out;
    }

    // The refusal of every way to close the rift while a member still has tries.
    inline std::string CloseRefusal(std::vector<std::string> const& holders)
    {
        return "Your rift cannot be closed while " + NameList(holders) +
               (holders.size() == 1 ? " still has" : " still have") + " upgrade attempts left with Urshi.";
    }
} // namespace DC::Rifts::Gr

#endif // DC_GR_URSHI_H
