/*
 * Corpse loot - the decisions, as pure inline functions.
 *
 * dc_corpse_loot.cpp owns the window and dc_loot.cpp the kill path; both take
 * their yes/no answers from here so scripts/tests/loot/corpse_tests.cpp can run
 * the same code without linking the core, the way dc_loot.h's roll maths are.
 */

#ifndef DC_CORPSE_RULES_H
#define DC_CORPSE_RULES_H

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

// Literal audit (docs/research/literal-audit-claude.md): constants, not tunables.
// Constant (16): rows per loot window page. The 3.3.5a core builds windows of at
//   most 18 rows (LootMgr.h MAX_NR_LOOT_ITEMS) and the client is unproven above
//   16, the number the catalogue's area-loot module also uses; it is a client
//   limit, not a game number. Rows past it stay on the corpse for the next click.
// Constant (2): a window stays open out to this many interaction distances. The
//   stock core never closes a loot window for distance and the client closes its
//   own frame; this only stops a stale window from taking items from afar.

namespace DC::Loot::Corpse
{
    constexpr std::size_t PageRows = 16;
    constexpr float ReleaseDistanceFactor = 2.0f;

    // A kill's corpse can hold personal rows only while the core still treats it as
    // a lootable kill: dead, tagged by someone who earned the reward, loot not
    // disabled. Anything else (a pet kill, too little player damage) keeps the old
    // direct delivery, so a drop is never stranded on a corpse nobody can open.
    inline bool CanHoldRows(bool ready, bool dead, bool hasLootRecipient, unsigned lootMode)
    {
        return ready && dead && hasLootRecipient && lootMode > 0;
    }

    // The rows one window shows: the looter's own, in drop order, one page.
    inline std::vector<std::uint64_t> Page(std::vector<std::uint64_t> const& owned, std::size_t pageRows = PageRows)
    {
        return {owned.begin(), owned.begin() + std::min(owned.size(), pageRows)};
    }

    // Area looting (M6). The range is a tunable (loot/aoe_range_yards); the code only keeps
// it inside the bounds the catalogue's area-loot module also uses, so a bad row can
// neither shrink the window to nothing nor sweep the map.
constexpr double MinAoeRange = 5.0;
constexpr double MaxAoeRange = 100.0;

inline double ClampRange(double yards)
{
    return std::clamp(yards, MinAoeRange, MaxAoeRange);
}

// A drop's rank in the window: legendary and set drops first, then rare, magic, normal.
// Gems and boss materials carry the rarity their row was written with.
inline unsigned RarityRank(std::string const& rarity)
{
    if (rarity == "legendary" || rarity == "set")
        return 4;
    if (rarity == "rare")
        return 3;
    if (rarity == "magic")
        return 2;
    return rarity == "normal" ? 1 : 0;
}

struct Candidate
{
    std::uint64_t id = 0; // dc_loot_buffer row
    unsigned rank = 0;
    float distance = 0;   // player to the row's corpse
};

// The window's order: best rank first, then the nearest corpse, then the order of the drop.
inline std::vector<std::uint64_t> Order(std::vector<Candidate> rows)
{
    std::stable_sort(rows.begin(), rows.end(),
                     [](Candidate const& a, Candidate const& b)
                     {
                         if (a.rank != b.rank)
                             return a.rank > b.rank;
                         if (a.distance != b.distance)
                             return a.distance < b.distance;
                         return a.id < b.id;
                     });
    std::vector<std::uint64_t> ids;
    for (Candidate const& row : rows)
        ids.push_back(row.id);
    return ids;
}

// A corpse is in reach of an area window (to list its rows, and again to take one).
inline bool InAoeRange(float distance, double range)
{
    return distance <= range;
}

enum class Packet
    {
        Open,
        Release,
        Pickup,
        Money
    };

    // Whether the module answers a loot packet (true) or lets the stock handler run.
    // `tracked`: the packet's corpse holds module rows. `windowOpen`: this player has
    // a module window. The money packet is always ours while a window is open: the
    // corpse carries a one-copper placeholder and a crafted CMSG_LOOT_MONEY would
    // pay it to the whole group and strip the sparkle for everyone.
    inline bool Answers(Packet packet, bool tracked, bool windowOpen)
    {
        switch (packet)
        {
            case Packet::Open:
                return tracked;
            case Packet::Release:
                return tracked || windowOpen;
            case Packet::Pickup:
                return windowOpen;
            case Packet::Money:
                return windowOpen;
        }
        return false;
    }

    enum class PickupError
    {
        None,
        AlreadyLooted,
        // The row is still there; the store refused it. The caller sends the
        // core's own result (EQUIP_ERR_INVENTORY_FULL, EQUIP_ERR_ITEM_MAX_COUNT,
        // ...) rather than guessing "inventory full" - a Unique unidentified
        // shell answered that way reads as a full bag and the player cannot
        // see why.
        StoreFailed
    };

    // EQUIP_ERR_OK, as the core's InventoryResult. This header compiles into the
    // offline harness, which has no core, so the code travels as a plain byte.
    inline constexpr std::uint8_t StoreOk = 0;

    inline PickupError PickupOutcome(bool claimed, std::uint8_t storeError)
    {
        if (claimed)
            return PickupError::None;
        return storeError != StoreOk ? PickupError::StoreFailed : PickupError::AlreadyLooted;
    }

    // A window whose corpse is gone, or whose looter has walked off, is closed by
    // the server. `distance` is to the corpse.
    inline bool KeepWindow(bool corpseThere, float distance, float interactionDistance)
    {
        return corpseThere && distance <= interactionDistance * ReleaseDistanceFactor;
    }

    // Whether a tracked corpse keeps its rows this tick. Rows die with the corpse: when the
// creature is gone, or has left the corpse state (the decay timer ended, it respawned), or
// was a rift corpse whose rift has closed. `isCorpseState` is DeathState::Corpse.
inline bool KeepRows(bool found, bool isCorpseState, bool inRift, bool riftLive)
{
    return found && isCorpseState && (!inRift || riftLive);
}

// After a pickup: rows still on the corpse for anyone, and players still owed a roll
    // (rift floors F7: the rift Guardian's party members who were not paid at the kill). A corpse
    // that somebody is still owed stays open however few rows it holds.
    inline bool CorpseEmpty(std::uint32_t rowsLeft, std::uint32_t owedLeft = 0)
    {
        return rowsLeft == 0 && owedLeft == 0;
    }

    // Who is owed a roll once the kill has paid its own: the party (rift floors F7, whoever is enrolled in the
    // run, on any floor or in town) without those already paid. Order kept, each player once.
    inline std::vector<std::uint64_t> OwedAfterPayout(std::vector<std::uint64_t> const& party,
                                                      std::vector<std::uint64_t> const& paid)
    {
        std::vector<std::uint64_t> owed;
        for (std::uint64_t const guid : party)
            if (std::find(paid.begin(), paid.end(), guid) == paid.end() &&
                std::find(owed.begin(), owed.end(), guid) == owed.end())
                owed.push_back(guid);
        return owed;
    }

    // The loot beam (docs/contracts/loot-beam-tier.md): each player is told the beam tier of
    // their own drops on a corpse, the highest one, Legendary < Set < Primal Ancient.
    // The values are the client module's tier table, so constants, not tunables.
    constexpr std::uint32_t BeamNone = 0, BeamLegendary = 6, BeamSet = 7, BeamPrimal = 8;

    // A row's tier from its rarity and its quality (dc_quality_rule.h): only legendary and set rows beam, and a
    // Primal one beams red whichever it is; an Ancient keeps its rarity's beam.
    inline std::uint32_t BeamTier(std::string const& rarity, std::string const& quality)
    {
        if (rarity != "legendary" && rarity != "set")
            return BeamNone;
        if (quality == "primal")
            return BeamPrimal;
        return rarity == "set" ? BeamSet : BeamLegendary;
    }

    // One player's rows on one corpse, counted at BeamLegendary, BeamSet, BeamPrimal.
    using BeamCounts = std::array<std::uint32_t, 3>;

    inline bool Beams(std::uint32_t tier)
    {
        return tier >= BeamLegendary && tier <= BeamPrimal;
    }

    inline void AddBeam(BeamCounts& counts, std::uint32_t tier)
    {
        if (Beams(tier))
            ++counts[tier - BeamLegendary];
    }

    inline void TakeBeam(BeamCounts& counts, std::uint32_t tier)
    {
        if (Beams(tier) && counts[tier - BeamLegendary])
            --counts[tier - BeamLegendary];
    }

    // What that player is sent: the highest tier they still have a row of, or none.
    inline std::uint32_t BeamValue(BeamCounts const& counts)
    {
        if (counts[BeamPrimal - BeamLegendary])
            return BeamPrimal;
        if (counts[BeamSet - BeamLegendary])
            return BeamSet;
        return counts[0] ? BeamLegendary : BeamNone;
    }
} // namespace DC::Loot::Corpse

#endif // DC_CORPSE_RULES_H
