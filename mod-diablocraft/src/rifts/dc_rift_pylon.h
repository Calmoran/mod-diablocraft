/*
 * World of DiabloCraft - where and when pylons and shrines stand in rifts (pylons and shrines Part P4,
 * docs/proposals/pylons.md 4.4, 4.5, 6.5, 6.6, 6.11).
 *
 * The decisions with no core in them: which spots may roll, what a Nephalem floor puts where (a replayable plan from
 * the run's seed), the Greater Rift's chance and its limits, and which buffs end when a player leaves the run or a
 * Greater Rift starts. No summon, no map, no database: dc_rift_pylon.cpp is the glue (the spot table, `.dc pylon
 * spot`), and tests/rift_pylon compiles this very file.
 *
 * The plan's stream is its own (Rng seeded by the run's seed xor STREAM_SALT and the floor), so the spawner's picks,
 * which
 * `.dc rift picks` replays from the same seed, do not move when a floor also rolls pylons.
 *
 * Internal to the rifts folder.
 */

#ifndef DC_RIFT_PYLON_H
#define DC_RIFT_PYLON_H

#include "dc_rift_spawn.h"
#include "dc_rift_touchup.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace DC::Rifts::Pylons
{
    // Identities, not game numbers. STREAM_SALT keeps the plan's stream apart from the spawner's; the near radius is
    // how close
    // `.dc pylon spot here` and `clear` look for a hand-placed spot to move or remove (a lookup aid, as the exit marker's
    // minute is).
    inline constexpr std::uint64_t STREAM_SALT = 0x50594C4F4E000001ull;
    inline constexpr double NEAR_YARDS = 12.0;

    struct Spot
    {
        unsigned id = 0, area = 0;
        double x = 0, y = 0, z = 0, o = 0;
        double walk = -1; // yards from the dungeon's entry point; negative: not known (a spot placed by hand)
        bool alex = false; // the sheet's `source`: placed or moved by hand, not the survey's
    };

    // One buff kind a placement may pick: `pylon` or shrine, and its weight (0: never). The glue builds the list from
    // the buff sheet.
    struct Kind
    {
        std::string name;
        bool pylon = true;
        double weight = 1;
    };

    inline double Distance(Spot const& a, Spot const& b)
    {
        return std::sqrt((a.x - b.x) * (a.x - b.x) + (a.y - b.y) * (a.y - b.y) + (a.z - b.z) * (a.z - b.z));
    }

    // Both rift kinds: no two placed objects, pylon or shrine, nearer than
    // `minSpacing` yards (pylon_min_spacing_yd); a spot that would be is skipped. 0 keeps nothing apart.
    inline bool Crowded(Spot const& spot, std::vector<Spot> const& placed, double minSpacing)
    {
        return std::any_of(placed.begin(), placed.end(),
                           [&](Spot const& other) { return Distance(spot, other) < minSpacing; });
    }

    // 6.6: a spot within the entry clearance of where the party arrives is not used. Clearance 0 (or unset) clears
    // nothing; a spot whose walk is not known stays, as a hand-placed anchor does (monster spawning 3.5.1 step 8).
    inline std::vector<Spot> Usable(std::vector<Spot> spots, double entryClear)
    {
        spots.erase(std::remove_if(spots.begin(), spots.end(),
                                   [&](Spot const& s) { return entryClear > 0 && s.walk >= 0 && s.walk < entryClear; }),
                    spots.end());
        std::sort(spots.begin(), spots.end(), [](Spot const& a, Spot const& b) { return a.id < b.id; });
        return spots;
    }

    // --- Nephalem Rifts (6.5 recommended (c)): rolled when a floor opens, everything summoned at once
    // -------------------------

    struct NephalemKnobs
    {
        double pylonPct = 0, shrinePct = 0; // each spot: a pylon at this chance, a shrine at this one, else nothing
        unsigned pylonsMin = 0, pylonsMax = ~0u, shrinesMin = 0, shrinesMax = ~0u;
        double minSpacing = 0; // pylon_min_spacing_yd
    };

    struct Placed
    {
        std::size_t spot = 0, kind = 0; // indexes into the spot list and the kind list the plan was made from
    };

    inline Spawn::Rng StreamOf(std::uint64_t runSeed, unsigned floor)
    {
        return Spawn::Rng(runSeed ^ STREAM_SALT, floor);
    }

    // What a floor puts where. Every spot rolls once, in id order (a roll is always taken); a hit nearer than the
    // minimum spacing to a hit before it is skipped; the class caps and minimums then trim or top up at random, the
    // top-up only at spots the spacing allows; each object's kind is picked by weight among its class's kinds. A class
    // with no kind of weight above zero places none. Same seed, floor, spots and sheet: the same plan.
    inline std::vector<Placed> PlanNephalem(std::vector<Spot> const& spots, std::vector<Kind> const& kinds,
                                            NephalemKnobs const& knobs, Spawn::Rng& rng)
    {
        enum
        {
            None,
            Pylon,
            Shrine
        };
        std::vector<int> what(spots.size(), None);
        auto placed = [&]
        {
            std::vector<Spot> out;
            for (std::size_t i = 0; i < spots.size(); ++i)
                if (what[i] != None)
                    out.push_back(spots[i]);
            return out;
        };
        for (std::size_t i = 0; i < spots.size(); ++i)
        {
            double const roll = rng.Real() * 100.0;
            int const hit = roll < knobs.pylonPct ? Pylon : roll < knobs.pylonPct + knobs.shrinePct ? Shrine : None;
            what[i] = hit != None && Crowded(spots[i], placed(), knobs.minSpacing) ? None : hit;
        }
        auto trim = [&](int cls, unsigned max)
        {
            std::vector<std::size_t> of;
            for (std::size_t i = 0; i < spots.size(); ++i)
                if (what[i] == cls)
                    of.push_back(i);
            rng.Shuffle(of);
            for (std::size_t i = max; i < of.size(); ++i)
                what[of[i]] = None;
        };
        trim(Pylon, knobs.pylonsMax);
        trim(Shrine, knobs.shrinesMax);
        auto topUp = [&](int cls, unsigned min)
        {
            std::vector<std::size_t> empty;
            for (std::size_t i = 0; i < spots.size(); ++i)
                if (what[i] == None)
                    empty.push_back(i);
            std::size_t have = 0;
            for (int w : what)
                have += w == cls;
            rng.Shuffle(empty);
            for (std::size_t i = 0; have < min && i < empty.size(); ++i)
                if (!Crowded(spots[empty[i]], placed(), knobs.minSpacing))
                    what[empty[i]] = cls, ++have;
        };
        topUp(Pylon, knobs.pylonsMin);
        topUp(Shrine, knobs.shrinesMin);

        std::vector<Placed> out;
        for (std::size_t i = 0; i < spots.size(); ++i)
        {
            if (what[i] == None)
                continue;
            std::vector<double> weights;
            for (Kind const& k : kinds)
                weights.push_back(k.pylon == (what[i] == Pylon) ? k.weight : 0);
            int const pick = rng.Weighted(weights);
            if (pick >= 0)
                out.push_back(Placed{i, static_cast<std::size_t>(pick)});
        }
        return out;
    }

    // --- Greater Rifts (6.5 recommended (a)): a spot rolls once, when the first player comes within `checkYards`
    // -------------------

    struct GreaterKnobs
    {
        double baseChancePct = 1; // after the last pylon, or at the start
        double fullAtPct = 50;    // progress since the last pylon, as a share of the bar, at which the chance is 100%
        double checkYards = 0; // rifts.csv pylon_gr_check_yards; Approach always fills it from the sheet
        unsigned maxPerRun = 4;
        double minSpacing = 0; // pylon_min_spacing_yd
    };

    // What a Greater Rift run has had: how many pylons stood, which kinds, and the bar's share when the last one did.
    struct RunHad
    {
        unsigned count = 0;
        std::vector<std::string> kinds;
        double shareAtLast = 0;
    };

    // The chance in percent for a spot that rolls now: `base` right after the last pylon, rising in a line to 100 at
    // `fullAtPct` of the bar since then. Shares are percent of the bar (progress units over the quest's required units,
    // times 100).
    inline double GreaterChancePct(double shareNow, double shareAtLast, GreaterKnobs const& k)
    {
        if (k.fullAtPct <= 0)
            return 100;
        double const since = std::max(0.0, shareNow - shareAtLast);
        return std::clamp(k.baseChancePct + (100.0 - k.baseChancePct) * since / k.fullAtPct, 0.0, 100.0);
    }

    // None: a spot may roll. Otherwise why not: the Guardian is up (the run's state past "open", or its instance is
    // recorded), or the run has had its fill. An unclicked pylon still counts, so `had.count` is spawns, not uses.
    enum class NoRoll
    {
        None,
        Guardian,
        Full,
    };

    inline NoRoll MayRoll(std::string const& state, std::uint32_t guardianInstance, RunHad const& had,
                          GreaterKnobs const& k)
    {
        if (guardianInstance || (state != "open"))
            return NoRoll::Guardian;
        return had.count >= k.maxPerRun ? NoRoll::Full : NoRoll::None;
    }

    // One spot's roll: the kind index in `kinds` that stands, or -1 for nothing. Never a kind the run has had, never a
    // shrine. Its own stream per spot (run seed, floor, spot id), so the same progress path gives the same pylons.
    inline int RollGreater(std::uint64_t runSeed, unsigned floor, unsigned spotId, double chancePct,
                           std::vector<Kind> const& kinds, RunHad const& had)
    {
        Spawn::Rng spotRng(runSeed ^ STREAM_SALT, (static_cast<std::uint64_t>(floor) << 32) | spotId);
        bool const stands = spotRng.Real() * 100.0 < chancePct;
        std::vector<double> weights;
        for (Kind const& k : kinds)
            weights.push_back(
                k.pylon && std::find(had.kinds.begin(), had.kinds.end(), k.name) == had.kinds.end() ? k.weight : 0);
        int const pick = spotRng.Weighted(weights); // the spot's own stream: the kind is the same at any chance
        return stands ? pick : -1;
    }

    // One spot's roll on approach, with the minimum spacing: the kind index that stands, with `had` taking it (one more, its
    // kind, the bar's share now), or -1. A hit nearer than the minimum to an object already placed on the floor
    // (`placed`) is dropped and nothing is stored, so the chance keeps rising, as for a miss (6.5: not stored).
    inline int ApproachGreater(std::uint64_t runSeed, unsigned floor, Spot const& spot, double shareNow,
                               GreaterKnobs const& k, std::vector<Kind> const& kinds, std::vector<Spot> const& placed,
                               RunHad& had)
    {
        int const pick =
            RollGreater(runSeed, floor, spot.id, GreaterChancePct(shareNow, had.shareAtLast, k), kinds, had);
        if (pick < 0 || Crowded(spot, placed, k.minSpacing))
            return -1;
        ++had.count;
        had.kinds.push_back(kinds[pick].name);
        had.shareAtLast = shareNow;
        return pick;
    }

    inline bool Within(Spot const& spot, double x, double y, double z, double yards)
    {
        return std::sqrt((spot.x - x) * (spot.x - x) + (spot.y - y) * (spot.y - y) + (spot.z - z) * (spot.z - z)) <=
               yards;
    }

    // --- 6.11: what ends a buff
    // -------------------------------------------------------------------------------------------------

    enum class Leaves
    {
        LeftRun, // the player is no longer on a floor of their run: a town portal, a revive in town, leaving the party
        GreaterRift, // a Greater Rift starts for them
    };
    enum class Fate
    {
        Keeps,
        Ends,
        EndsKnockOnly, // Speed: the speed and the attack speed stay, only the knock-up aura goes
    };

    // What a player's arrival on a map means for the buffs: off the rift floors is leaving the run (a town portal, a
    // revive in town, a party left behind all end there); a Greater Rift floor is a Greater Rift starting for them, as far
    // as the buffs go (a pylon's crossed in from the floor before keeps, 6.11); another rift floor changes nothing.
    inline std::optional<Leaves> Leaving(bool onRiftFloor, bool greater)
    {
        if (!onRiftFloor)
            return Leaves::LeftRun;
        if (greater)
            return Leaves::GreaterRift;
        return std::nullopt;
    }

    // A pylon buff ends when the player leaves the run's floors (Speed keeps all but its knock-up); a shrine buff
    // outlasts that and is cleared when a Greater Rift starts. A floor change and a death are not here: the self-cast
    // buff crosses floors on its own (OnPlayerMapChanged keeps it), and the records' death flag does the rest (P1).
    inline Fate FateOf(bool pylon, bool speed, Leaves when)
    {
        if (when == Leaves::LeftRun)
            return !pylon ? Fate::Keeps : speed ? Fate::EndsKnockOnly : Fate::Ends;
        return pylon ? Fate::Keeps : Fate::Ends;
    }

    // --- `.dc pylon spot`
    // --------------------------------------------------------------------------------------------------------

    inline unsigned NextSpotId(std::vector<Spot> const& rows)
    {
        unsigned top = 0;
        for (Spot const& s : rows)
            top = std::max(top, s.id);
        return top + 1;
    }

    // The spot nearest the point within NEAR_YARDS, or -1.
    inline int NearestSpot(std::vector<Spot> const& rows, double x, double y, double z)
    {
        int best = -1;
        double bestD = NEAR_YARDS;
        for (std::size_t i = 0; i < rows.size(); ++i)
        {
            double const d = std::sqrt((rows[i].x - x) * (rows[i].x - x) + (rows[i].y - y) * (rows[i].y - y) +
                                       (rows[i].z - z) * (rows[i].z - z));
            if (d <= bestD)
                best = static_cast<int>(i), bestD = d;
        }
        return best;
    }

    // A new hand-placed spot, and the same spot moved. `walk` unknown is NULL, as for a hand-placed anchor.
    inline std::string AddSql(std::string const& dungeon, unsigned id, Spot const& at)
    {
        return "INSERT INTO `dc_rift_pylon_spot` (`dungeon`, `spot`, `area`, `x`, `y`, `z`, `o`, `entry_walk_yards`, "
               "`source`) "
               "VALUES (" +
               TouchUp::Quote(dungeon) + ", " + std::to_string(id) + ", " + std::to_string(at.area) + ", " +
               TouchUp::Number(at.x) + ", " + TouchUp::Number(at.y) + ", " + TouchUp::Number(at.z) + ", " +
               TouchUp::Number(at.o) + ", NULL, 'alex')";
    }

    inline std::string MoveSql(std::string const& dungeon, unsigned id, Spot const& at)
    {
        return "UPDATE `dc_rift_pylon_spot` SET `x` = " + TouchUp::Number(at.x) + ", `y` = " + TouchUp::Number(at.y) +
               ", `z` = " + TouchUp::Number(at.z) + ", `o` = " + TouchUp::Number(at.o) +
               ", `entry_walk_yards` = NULL, `source` = 'alex' WHERE "
               "`dungeon` = " +
               TouchUp::Quote(dungeon) + " AND `spot` = " + std::to_string(id);
    }

    inline std::string RemoveSql(std::string const& dungeon, unsigned id)
    {
        return "DELETE FROM `dc_rift_pylon_spot` WHERE `dungeon` = " + TouchUp::Quote(dungeon) +
               " AND `spot` = " + std::to_string(id);
    }
} // namespace DC::Rifts::Pylons

#endif // DC_RIFT_PYLON_H
