// diablocraft-a491a: a cubed or set stat saved in dc_character_stats that the character no longer has is swept at the first
// Items::RefreshCubedStats after the login. The real dc_common.cpp round-trips the save as Stats::Save and Stats::Load do; the real
// ItemPower::CubedStatId picks what the sweep takes as placed, and the real RemoveContribution and SetContribution apply it the way
// RefreshCubedStats does through Stats (dc_items_equip.cpp; scripts/tests/items/test_cubed_stats_login_sweep.py pins those lines).
// Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "common/dc_common.h"
#include "combat/dc_item_power_math.h"

#include <cstdio>
#include <stdexcept>
#include <utility>
#include <vector>

// dc_common.cpp asks the world for these when it calculates a sheet; the sweep never does, so they only link.
namespace DC::NumericData
{
double Rule(char const*) { throw std::logic_error("not asked by the sweep"); }
unsigned MaximumLevel() { throw std::logic_error("not asked by the sweep"); }
double BaseFury(unsigned) { throw std::logic_error("not asked by the sweep"); }
BlockTuning Block() { throw std::logic_error("not asked by the sweep"); }
}

using namespace DC;
using DC::Combat::ItemPower::CubeContributionId;
using DC::Combat::ItemPower::CubedStatId;
using DC::Combat::ItemPower::SetStatContributionId;

static int failures = 0, cases = 0;

static void expect(bool ok, char const* what)
{
    ++cases;
    if (!ok && !failures++)
        std::printf("FAIL %s\n", what);
}

static bool Has(std::vector<Contribution> const& list, Source source, Stat stat, std::uint64_t id, double value)
{
    for (Contribution const& c : list)
        if (c.source == source && c.stat == stat && c.id == id)
            return c.value == value;
    return false;
}

// The login: what Stats::Load keeps of the save, then the first RefreshCubedStats with the list it has now.
static std::vector<Contribution> Login(std::vector<Contribution> const& saved, std::vector<Contribution> const& wanted)
{
    CharacterStats character;
    character.contributions = DeserializeContributions(Serialize(saved));
    DropRebuiltSources(character.contributions);
    std::vector<std::pair<Stat, std::uint64_t>> had;
    for (Contribution const& c : character.contributions)
        if (c.source == Source::Items && CubedStatId(c.id))
            had.push_back({c.stat, c.id});
    for (auto const& [stat, id] : had)
        RemoveContribution(character, Source::Items, stat, id);
    for (Contribution const& c : wanted)
        SetContribution(character, c);
    return character.contributions;
}

int main()
{
    std::uint64_t const cubeOne = CubeContributionId(1, 0), cubeTwo = CubeContributionId(2, 0), cubeLast = CubeContributionId(255, 255);
    std::uint64_t const setFirst = SetStatContributionId(0), setLast = SetStatContributionId(252);
    std::uint64_t const itemOwn = (std::uint64_t(7) << 16) | 0;
    std::vector<Contribution> const saved = {
        {Source::Items, Stat::WeaponAPS, 1, 1.4, Bucket::Flat},          // the weapon source's 1 and 2
        {Source::Items, Stat::AttackSpeed, 2, 15, Bucket::Flat},
        {Source::Items, Stat::Strength, itemOwn, 500, Bucket::Flat},     // a worn item's own roll
        {Source::Gems, Stat::CritDamage, cubeOne, 50, Bucket::Flat},     // another source on a cube-range id
        {Source::Items, Stat::EliteDamage, cubeOne, 20, Bucket::Flat},   // still cubed: comes back from the Cube list
        {Source::Items, Stat::Vitality, cubeTwo, 300, Bucket::Flat},     // STALE: the power left the Cube while away
        {Source::Items, Stat::Intelligence, cubeLast, 9, Bucket::Flat},  // STALE: the last id the Cube can hold
        {Source::Items, Stat::AllResistance, setFirst, 100, Bucket::Flat}, // STALE: the set's 2 pieces are no longer worn
        {Source::Items, Stat::Armor, setLast, 7, Bucket::Flat},          // STALE: the last set stat id
    };
    std::vector<Contribution> const wanted = {{Source::Items, Stat::EliteDamage, cubeOne, 20, Bucket::Flat}};

    std::vector<Contribution> const after = Login(saved, wanted);
    expect(!Has(after, Source::Items, Stat::Vitality, cubeTwo, 300), "a cubed stat whose power left the Cube is swept");
    expect(!Has(after, Source::Items, Stat::Intelligence, cubeLast, 9), "the Cube's last id is swept too");
    expect(!Has(after, Source::Items, Stat::AllResistance, setFirst, 100), "a set stat no longer reached is swept");
    expect(!Has(after, Source::Items, Stat::Armor, setLast, 7), "the last set stat id is swept too");
    expect(Has(after, Source::Items, Stat::EliteDamage, cubeOne, 20), "the power still cubed is on the sheet once");
    expect(Has(after, Source::Items, Stat::WeaponAPS, 1, 1.4), "the weapon's APS is kept");
    expect(Has(after, Source::Items, Stat::AttackSpeed, 2, 15), "the dual wield speed is kept");
    expect(Has(after, Source::Items, Stat::Strength, itemOwn, 500), "a worn item's own stat is kept");
    expect(Has(after, Source::Gems, Stat::CritDamage, cubeOne, 50), "another source's contribution on a cube-range id is kept");
    expect(after.size() == 5, "exactly the five kept contributions remain");

    // Nothing cubed now: every saved cubed and set stat goes, nothing else does.
    std::vector<Contribution> const bare = Login(saved, {});
    expect(bare.size() == 4, "with an empty Cube only the weapon, item and gem rows stay");

    // The id rule against its neighbours.
    expect(!CubedStatId(0) && !CubedStatId(1) && !CubedStatId(2), "the weapon ids are not the Cube's");
    expect(CubedStatId(3) && CubedStatId(255) && CubedStatId(256) && CubedStatId(65535), "3..65535 are the set's and the Cube's");
    expect(!CubedStatId(65536), "an item's first id is not the Cube's");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
