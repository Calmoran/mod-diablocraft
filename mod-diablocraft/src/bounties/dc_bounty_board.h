/*
 * World of DiabloCraft - the bounty board, without the core (docs/research/bounties.md 5.1
 * and 5.4, contract docs/contracts/bounty-messages.md).
 *
 * A board is five columns of five cells (D3's 25: five acts, five bounties an act). A column is an act and draws its
 * cells from its pool of bounties (dc_bounties rows of that column, one a zone of the act), so a
 * board is up to five random zones of each act; a column with no rows is locked, and so is a cell the pool cannot fill
 * (an act with fewer than five live zones draws what it has). Each bounty completes on its own; a column is done when all its live cells are; "New bounties"
 * (a fresh draw) is allowed only once every live cell is done (no partial reroll).
 *
 * No core header: dc_bounties.cpp keeps the database, the parties and the wire; scripts/tests/bounties/test_bounties.py compiles this
 * file as it is and drives it with the generated catalogue.
 */
#ifndef DC_BOUNTY_BOARD_H
#define DC_BOUNTY_BOARD_H

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <functional>
#include <string>
#include <vector>

namespace DC::Bounties
{
    // D3's shape (maxroll bounties: "Completing all 5 bounties in an Act"; five acts). Constants, not tunables.
    constexpr unsigned Columns = 5, Cells = 5;

    struct Spot
    {
        std::uint32_t anchor = 0;
        float x = 0, y = 0, z = 0, o = 0;
        // A Click objective's guard pack (W2): the survey's own pack at this anchor (dc_rift_anchor native_entry and
        // pack_size), 0 when the survey has none.
        std::uint32_t guardEntry = 0, guardCount = 0;
    };

    struct Bounty
    {
        std::uint32_t id = 0;
        unsigned column = 0, index = 0;
        std::string type; // "kill" or "click"
        std::string zoneKey, zoneName, title; // title: a Click's; a Kill's is its drawn target's (CellTitle)
        std::uint32_t mapId = 0, zoneId = 0;
        std::vector<Spot> spots;
        std::uint32_t objectiveEntry = 0; // a Click's objective object (dc_bounties_objective, W2); 0 for Kill
    };

    struct Cell
    {
        unsigned column = 0, cell = 0;
        std::uint32_t bounty = 0, objectives = 0, need = 0, progress = 0; // objectives: a Click's spots still to click
        bool done = false;
        std::uint32_t target = 0; // a Kill's named target, drawn from the master list; 0 for a Click
    };

    // A named target of the master list (bounty_targets.csv, dc_bounties_target): the creature a Kill bounty's Unique is,
    // and the bounty's title with it.
    struct Target
    {
        std::uint32_t entry = 0;
        std::string title;
    };

    using Board = std::vector<Cell>; // the live cells only, column then cell order

    // The rifts tunables bounty_kill_monster_count, bounty_click_objectives_min and _max, read when a board is drawn.
    struct Rules
    {
        unsigned killMonsters = 0, clickMin = 0, clickMax = 0;
    };

    // A uniform whole number in [lo, hi]; urand in the server, a fixed sequence in the test.
    using Rng = std::function<std::uint32_t(std::uint32_t lo, std::uint32_t hi)>;

    inline Bounty const* Find(std::vector<Bounty> const& catalog, std::uint32_t id)
    {
        for (Bounty const& b : catalog)
            if (b.id == id)
                return &b;
        return nullptr;
    }

    // A fresh board: each column draws up to Cells distinct bounties of its pool, in random order. A Click bounty draws
    // between clickMin and clickMax of its spots (the two swapped if set the wrong way round, never more than it has,
    // at least one); a Kill bounty asks for killMonsters monsters besides its Unique, and its Unique is a random pick of
    // `targets`, each zone's on its own (none with an empty list).
    inline Board Draw(std::vector<Bounty> const& catalog, std::vector<Target> const& targets, Rules const& rules, Rng const& rng)
    {
        Board board;
        for (unsigned column = 1; column <= Columns; ++column)
        {
            std::vector<Bounty const*> pool;
            for (Bounty const& b : catalog)
                if (b.column == column)
                    pool.push_back(&b);
            for (unsigned cell = 1; cell <= Cells && !pool.empty(); ++cell)
            {
                std::size_t pick = rng(0, static_cast<std::uint32_t>(pool.size() - 1));
                Bounty const& b = *pool[pick];
                pool.erase(pool.begin() + pick);
                Cell c{column, cell, b.id};
                if (b.type == "click")
                {
                    std::uint32_t lo = std::min(rules.clickMin, rules.clickMax),
                                  hi = std::max(rules.clickMin, rules.clickMax);
                    std::uint32_t const have = static_cast<std::uint32_t>(b.spots.size());
                    std::uint32_t n = have ? std::clamp<std::uint32_t>(rng(lo, hi), 1, have) : 0;
                    std::vector<std::uint32_t> left;
                    for (std::uint32_t s = 0; s < have; ++s)
                        left.push_back(s);
                    for (std::uint32_t k = 0; k < n; ++k)
                    {
                        std::size_t at = rng(0, static_cast<std::uint32_t>(left.size() - 1));
                        c.objectives |= 1u << left[at];
                        left.erase(left.begin() + at);
                    }
                    c.need = n;
                }
                else
                {
                    c.need = rules.killMonsters;
                    if (!targets.empty())
                        c.target = targets[rng(0, static_cast<std::uint32_t>(targets.size() - 1))].entry;
                }
                board.push_back(c);
            }
        }
        return board;
    }

    enum class ColumnState
    {
        Locked, // no bounty of this column exists (no zone of its act is built)
        Open,
        Done
    };

    inline ColumnState StateOf(Board const& board, unsigned column)
    {
        bool any = false;
        for (Cell const& c : board)
            if (c.column == column)
            {
                any = true;
                if (!c.done)
                    return ColumnState::Open;
            }
        return any ? ColumnState::Done : ColumnState::Locked;
    }

    // Every live cell done: the only time "New bounties" may draw again.
    inline bool Cleared(Board const& board)
    {
        return !board.empty() && std::all_of(board.begin(), board.end(), [](Cell const& c) { return c.done; });
    }

    struct Change
    {
        bool changed = false;    // the board moved; save it and tell the members
        bool columnDone = false; // this change finished its column (the cache's moment, W4)
        unsigned column = 0;
        std::uint32_t bounty = 0;
        bool completed = false; // this change completed the bounty
    };

    // Complete the open bounty `id` on the board. Nothing for a bounty the board does not hold or has done.
    inline Change Complete(Board& board, std::uint32_t id)
    {
        for (Cell& c : board)
            if (c.bounty == id && !c.done)
            {
                c.done = true;
                c.progress = std::max(c.progress, c.need);
                return {true, StateOf(board, c.column) == ColumnState::Done, c.column, id, true};
            }
        return {};
    }

    // A Click bounty's objective at `spot` (0 up, dc_bounties_spot.spot - 1) is done: its bit leaves `objectives`, which
    // from the draw on holds the spots still to click, and it counts one; the last one completes the bounty.
    // Nothing for a spot the draw did not pick or that is done.
    inline Change Click(Board& board, std::uint32_t id, unsigned spot)
    {
        if (spot >= 32)
            return {};
        for (Cell& c : board)
            if (c.bounty == id && !c.done && (c.objectives & (1u << spot)))
            {
                c.objectives &= ~(1u << spot);
                ++c.progress;
                if (c.objectives)
                    return {true, false, c.column, id};
                return Complete(board, id);
            }
        return {};
    }

    // Count `amount` towards an open bounty's need, never past it. It never completes the bounty: its end (the Unique's
    // kill, the last objective) is the caller's Complete.
    inline Change AddProgress(Board& board, std::uint32_t id, std::uint32_t amount)
    {
        for (Cell& c : board)
            if (c.bounty == id && !c.done && c.progress < c.need)
            {
                c.progress = c.need - c.progress < amount ? c.need : c.progress + amount;
                return {true, false, c.column, id};
            }
        return {};
    }

    // Travel (W5): where the clicker stands, as the gate sees it. The open world is itself an instance copy (map 751, one
    // per party), so `instanced` alone does not tell it from a dungeon; `openZone` does, and a rift there is `rift`.
    struct Standing
    {
        bool sanctum = false, rift = false, instanced = false, openZone = false, inCombat = false;
    };

    // The gate, written to the rule: the Sanctum and the open world only, out of combat, never from
    // inside a rift. Not Town Portal's ValidSource, which refuses the Sanctum and allows a rift. Null when the trip may go.
    inline char const* TravelRefusal(Standing const& at)
    {
        if (at.rift)
            return "You cannot travel from inside a rift.";
        if (!at.sanctum && at.instanced && !at.openZone)
            return "You can travel only from the Sanctum or the open world.";
        if (at.inCombat)
            return "You cannot travel while in combat.";
        return nullptr;
    }

    // Where a bounty's button lands: its zone's waypoint (the zone's entrance, where the compass marker sends too), Kill and
    // Click alike, as D3. The zone's key; null for a cell
    // the board does not hold (a locked one).
    inline std::string const* CellZone(Board const& board, std::vector<Bounty> const& catalog, unsigned column, unsigned cell)
    {
        for (Cell const& c : board)
            if (c.column == column && c.cell == cell)
                if (Bounty const* b = Find(catalog, c.bounty))
                    return &b->zoneKey;
        return nullptr;
    }

    // A cell's title: a Kill's is its drawn target's ("Kill <name>"), a Click's its bounty's. Empty for a target the list
    // does not hold.
    inline std::string CellTitle(Cell const& c, Bounty const& b, std::vector<Target> const& targets)
    {
        if (b.type == "click")
            return b.title;
        for (Target const& t : targets)
            if (t.entry == c.target)
                return t.title;
        return {};
    }

    inline char const* StateName(ColumnState state)
    {
        return state == ColumnState::Locked ? "locked" : state == ColumnState::Done ? "done" : "open";
    }

    // A zone's waypoint, where its marker on the map sends the player (the zone's entrance): world x and y in yards on
    // the zone's map, false for a zone with no entrance. dc_bounties.cpp hands Records DC::Rifts::OpenZoneWaypoint.
    using Waypoint = std::function<bool(std::string const& zoneKey, float& x, float& y)>;

    // One decimal of a yard: the map draws a 0.1-yard step as nothing.
    inline std::string Yards(float value)
    {
        char text[24];
        std::snprintf(text, sizeof(text), "%.1f", value);
        return text;
    }

    // The board as the window's records (contract docs/contracts/bounty-messages.md), one a record, in order:
    // L (start), Z per column (an act: its state), C per live cell (with its zone), W per live zone, E (end).
    // `leader`: the receiver may press "New bounties" (the party's leader, or a solo player); the button is live once
    // every unlocked column is done. A live zone is one the catalogue has a bounty in, drawn on this board or not
    // (docs/research/bounty-acts.md 2.3); its W carries the waypoint when `waypoint` knows one.
    inline std::vector<std::vector<std::string>> Records(Board const& board, std::vector<Bounty> const& catalog,
                                                         std::vector<Target> const& targets, bool leader,
                                                         Waypoint const& waypoint = {})
    {
        std::vector<std::vector<std::string>> out;
        out.push_back({"L", leader ? "1" : "0"});
        for (unsigned column = 1; column <= Columns; ++column)
            out.push_back({"Z", std::to_string(column), StateName(StateOf(board, column))});
        for (Cell const& c : board)
        {
            Bounty const* b = Find(catalog, c.bounty);
            out.push_back({"C", std::to_string(c.column), std::to_string(c.cell), std::to_string(c.bounty),
                           b ? b->type : "", c.done ? "1" : "0", std::to_string(c.progress), std::to_string(c.need),
                           b ? CellTitle(c, *b, targets) : "", b ? b->zoneKey : ""});
        }
        std::vector<std::string> zones;
        for (Bounty const& b : catalog)
        {
            if (std::find(zones.begin(), zones.end(), b.zoneKey) != zones.end())
                continue;
            zones.push_back(b.zoneKey);
            float x = 0, y = 0;
            bool const located = waypoint && waypoint(b.zoneKey, x, y);
            out.push_back({"W", b.zoneKey, b.zoneName, located ? Yards(x) : "", located ? Yards(y) : ""});
        }
        out.push_back({"E"});
        return out;
    }

    // --- bounties as quests ---

    // The bounty the quest log shows in a zone: the board's first open cell, in board order (column, then cell), whose
    // bounty stands in this map and zone. Null when none does: another zone, the Sanctum, or every one there done.
    inline Cell const* Showing(Board const& board, std::vector<Bounty> const& catalog, std::uint32_t mapId,
                               std::uint32_t zoneId)
    {
        for (Cell const& c : board)
            if (!c.done)
                if (Bounty const* b = Find(catalog, c.bounty); b && b->mapId == mapId && b->zoneId == zoneId)
                    return &c;
        return nullptr;
    }

    // The quest's count: a Kill's is its Unique (1), a Click's the objectives its board drew. How far it is: a Click counts
    // its clicks, a Kill nothing until its Unique dies; a done bounty is at its count.
    inline std::uint32_t QuestNeed(Cell const& c, Bounty const& b)
    {
        return b.type == "click" ? c.need : 1;
    }
    inline std::uint32_t QuestCount(Cell const& c, Bounty const& b)
    {
        if (c.done)
            return QuestNeed(c, b);
        return b.type == "click" ? std::min(c.progress, c.need) : 0;
    }

    // dc_bounties_quest (bounties_0005_quests.sql): which quest shows a bounty at a count with a target (a Kill's drawn
    // target; 0 for a Click).
    struct QuestRow
    {
        std::uint32_t bounty = 0, need = 0, quest = 0, target = 0;
    };
    inline QuestRow const* QuestOf(std::vector<QuestRow> const& rows, std::uint32_t bounty, std::uint32_t need,
                                   std::uint32_t target)
    {
        for (QuestRow const& r : rows)
            if (r.bounty == bounty && r.need == need && r.target == target)
                return &r;
        return nullptr;
    }

    // What one player's log needs, from the board they play and where they stand (`here`: in the world on a bounty map;
    // false anywhere else, which takes every bounty quest out). `held`: the bounty quests in their log now.
    struct QuestSync
    {
        std::vector<std::uint32_t> finish; // held, its bounty now done: shown complete, then taken out
        std::vector<std::uint32_t> strip;  // held, no longer this zone's: taken out
        std::uint32_t add = 0;             // this zone's quest, not held yet
        std::uint32_t quest = 0, count = 0; // this zone's quest and its count, written absolute (the rift quests' way)
    };
    inline QuestSync SyncQuests(Board const& board, std::vector<Bounty> const& catalog, std::vector<QuestRow> const& rows,
                                std::vector<std::uint32_t> const& held, bool here, std::uint32_t mapId,
                                std::uint32_t zoneId)
    {
        QuestSync out;
        if (Cell const* c = here ? Showing(board, catalog, mapId, zoneId) : nullptr)
        {
            Bounty const& b = *Find(catalog, c->bounty);
            if (QuestRow const* row = QuestOf(rows, b.id, QuestNeed(*c, b), c->target))
            {
                out.quest = row->quest;
                out.count = QuestCount(*c, b);
            }
        }
        for (std::uint32_t quest : held)
        {
            if (quest == out.quest)
                continue;
            bool done = false;
            for (QuestRow const& r : rows)
                if (r.quest == quest)
                    for (Cell const& c : board)
                        if (c.bounty == r.bounty && c.done)
                            done = true;
            (done ? out.finish : out.strip).push_back(quest);
        }
        if (out.quest && std::find(held.begin(), held.end(), out.quest) == held.end())
            out.add = out.quest;
        return out;
    }

    // Logout loses the board, as a rift's logout ends the rift: once nobody who plays it is online and
    // the last of them left more than the rifts' grace ago (rift_logout_grace_seconds, so a disconnect is not a wipe).
    // A party with a member online keeps its board; a returning member plays it as a late joiner does.
    inline bool BoardExpired(bool anyoneOnline, std::uint64_t awaySeconds, std::uint64_t graceSeconds)
    {
        return !anyoneOnline && awaySeconds > graceSeconds;
    }
} // namespace DC::Bounties

#endif
