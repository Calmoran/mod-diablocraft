// Runs the production decisions of corpse loot (src/loot/dc_corpse_rules.h) with no core.
// Exit 0 when every check holds; the first failing check aborts with its name.
#include "dc_corpse_rules.h"

#include <cstdio>
#include <cstdlib>
#include <vector>

using namespace DC::Loot::Corpse;

static void check(bool ok, char const* name)
{
    if (!ok)
    {
        std::fprintf(stderr, "FAIL: %s\n", name);
        std::exit(1);
    }
    std::printf("PASS %s\n", name);
}

int main()
{
    // A corpse holds rows only while the core treats it as a lootable kill.
    check(CanHoldRows(true, true, true, 1), "a dead, tagged, loot-enabled corpse holds rows");
    check(!CanHoldRows(false, true, true, 1), "migration not applied: no rows");
    check(!CanHoldRows(true, false, true, 1), "an alive creature holds no rows");
    check(!CanHoldRows(true, true, false, 1), "an untagged corpse (pet kill, too little player damage) holds no rows");
    check(!CanHoldRows(true, true, true, 0), "loot mode off holds no rows");

    // The window shows one page of the looter's own rows, in drop order.
    std::vector<std::uint64_t> twenty;
    for (std::uint64_t i = 1; i <= 20; ++i)
        twenty.push_back(i);
    auto page = Page(twenty);
    check(PageRows == 16 && page.size() == 16, "a window page is 16 rows");
    check(page.front() == 1 && page.back() == 16, "the page is the first 16, in drop order");
    check(Page({1, 2, 3}).size() == 3, "fewer rows than a page show whole");
    check(Page({}).empty(), "no rows show nothing");

    // Who answers which packet.
    check(Answers(Packet::Open, true, false), "CMSG_LOOT on a tracked corpse is ours");
    check(!Answers(Packet::Open, false, true), "CMSG_LOOT on any other creature is stock");
    check(Answers(Packet::Release, true, false) && Answers(Packet::Release, false, true),
          "a release is swallowed for a tracked corpse or an open window");
    check(!Answers(Packet::Release, false, false), "a release with nothing of ours is stock");
    check(Answers(Packet::Pickup, false, true) && !Answers(Packet::Pickup, true, false),
          "a pickup is ours only with a window open");
    check(Answers(Packet::Money, false, true), "CMSG_LOOT_MONEY is swallowed while a window is open");
    check(!Answers(Packet::Money, true, false), "and left to the stock handler with none");

    // A pickup that does not pay says why: a store refusal (the core's own
    // result, which the caller sends as it is) or a row that was already gone.
    check(PickupOutcome(true, StoreOk) == PickupError::None, "a claimed row is no error");
    check(PickupOutcome(false, 1) == PickupError::StoreFailed,
          "a store refusal is reported as the store's own failure");
    check(PickupOutcome(false, 25) == PickupError::StoreFailed,
          "EQUIP_ERR_ITEM_MAX_COUNT is a store refusal too, not a full bag");
    check(PickupOutcome(false, StoreOk) == PickupError::AlreadyLooted, "a missing row answers already looted");

    // A window closes when its corpse is gone or its looter has walked off.
    check(KeepWindow(true, 9.9f, 5.0f), "just inside twice the interaction distance keeps the window");
    check(!KeepWindow(true, 10.1f, 5.0f), "past twice the interaction distance closes it");
    check(!KeepWindow(false, 0.0f, 5.0f), "a gone corpse closes it");

    // Area looting: the range is clamped, the window is ordered best first then nearest.
    check(ClampRange(30.0) == 30.0, "a range of 30 yards is kept");
    check(ClampRange(1.0) == 5.0 && ClampRange(-4.0) == 5.0, "a range below 5 is raised to 5");
    check(ClampRange(500.0) == 100.0, "a range above 100 is cut to 100");
    check(RarityRank("legendary") == RarityRank("set") && RarityRank("set") > RarityRank("rare") &&
              RarityRank("rare") > RarityRank("magic") && RarityRank("magic") > RarityRank("normal") &&
              RarityRank("normal") > RarityRank("unknown"),
          "legendary and set rank first, then rare, magic, normal");
    auto order = Order({{1, 1, 2.0f}, {2, 4, 25.0f}, {3, 4, 3.0f}, {4, 3, 1.0f}, {5, 1, 2.0f}});
    check(order == std::vector<std::uint64_t>({3, 2, 4, 1, 5}),
          "best rank first, then the nearer corpse, then the order of the drop");
    check(InAoeRange(30.0f, 30.0) && !InAoeRange(30.1f, 30.0), "a corpse at the range edge is in, past it is out");

    // Rows die with the corpse.
    check(KeepRows(true, true, false, false), "a corpse in the world keeps its rows");
    check(!KeepRows(false, true, false, false), "a corpse that left the map loses its rows");
    check(!KeepRows(true, false, false, false), "a corpse whose timer ended (no longer in the corpse state) loses its rows");
    check(KeepRows(true, true, true, true), "a rift corpse keeps its rows while the rift is live");
    check(!KeepRows(true, true, true, false), "a rift corpse loses its rows when the rift closes");

    check(CorpseEmpty(0) && !CorpseEmpty(1), "a corpse with no rows left is finished");
    // Rift floors F7: a player still owed a roll keeps the corpse open however few rows it holds.
    check(CorpseEmpty(0, 0) && !CorpseEmpty(0, 1) && !CorpseEmpty(1, 0) && !CorpseEmpty(2, 3),
          "a corpse is finished only with no rows left and nobody owed a roll");

    // Who is owed once the kill has paid its own: the party without those paid, each once; nobody outside the party.
    check(OwedAfterPayout({1, 2, 3, 4}, {2, 4}) == std::vector<std::uint64_t>({1, 3}),
          "the members the kill paid are not owed; the others are, in party order");
    check(OwedAfterPayout({1, 2, 2, 1}, {}) == std::vector<std::uint64_t>({1, 2}), "a member listed twice is owed once");
    check(OwedAfterPayout({1, 2}, {1, 2}).empty() && OwedAfterPayout({}, {7}).empty(),
          "nobody is owed when the kill paid the whole party, and a paid stranger adds nobody");
    check(OwedAfterPayout({1, 2}, {1, 9}) == std::vector<std::uint64_t>({2}), "someone outside the party is never owed");

    // The loot beam (docs/contracts/loot-beam-tier.md): each player's own drops on a corpse, highest tier wins,
    // legendary 6 < set 7 < Primal Ancient 8, and nothing else beams.
    check(BeamNone == 0 && BeamLegendary == 6 && BeamSet == 7 && BeamPrimal == 8, "the values are the client's tier table");
    check(BeamTier("legendary", "normal") == BeamLegendary && BeamTier("legendary", "ancient") == BeamLegendary,
          "a legendary beams orange, Ancient or not");
    check(BeamTier("set", "normal") == BeamSet && BeamTier("set", "ancient") == BeamSet, "a set item beams green, Ancient or not");
    check(BeamTier("legendary", "primal") == BeamPrimal && BeamTier("set", "primal") == BeamPrimal,
          "a Primal Ancient legendary or set item beams red");
    check(BeamTier("rare", "primal") == BeamNone && BeamTier("ethereal", "normal") == BeamNone &&
              BeamTier("magic", "normal") == BeamNone && BeamTier("normal", "normal") == BeamNone && BeamTier("", "") == BeamNone,
          "no other rarity beams, whatever its quality");
    check(!Beams(BeamNone) && !Beams(5) && Beams(BeamLegendary) && Beams(BeamSet) && Beams(BeamPrimal) && !Beams(9),
          "only 6, 7 and 8 are beam tiers");
    BeamCounts counts{};
    check(BeamValue(counts) == BeamNone, "no beam rows, no beam");
    AddBeam(counts, BeamLegendary);
    check(BeamValue(counts) == BeamLegendary, "one legendary row beams orange");
    AddBeam(counts, BeamSet);
    check(BeamValue(counts) == BeamSet, "the highest tier wins: set over legendary");
    AddBeam(counts, BeamPrimal);
    AddBeam(counts, BeamNone);
    check(BeamValue(counts) == BeamPrimal, "Primal over set; a row of no tier counts for nothing");
    TakeBeam(counts, BeamPrimal);
    check(BeamValue(counts) == BeamSet, "taking the Primal falls back to the set");
    TakeBeam(counts, BeamSet);
    check(BeamValue(counts) == BeamLegendary, "then to the legendary");
    TakeBeam(counts, BeamLegendary);
    check(BeamValue(counts) == BeamNone, "and to none once every beam row is taken");
    TakeBeam(counts, BeamLegendary);
    TakeBeam(counts, BeamNone);
    check(BeamValue(counts) == BeamNone && counts[0] == 0, "a take with nothing left, or of no tier, stays at none");
    BeamCounts two{};
    AddBeam(two, BeamSet);
    AddBeam(two, BeamSet);
    TakeBeam(two, BeamSet);
    check(BeamValue(two) == BeamSet, "two set rows: one taken, the other still beams green");
    return 0;
}
