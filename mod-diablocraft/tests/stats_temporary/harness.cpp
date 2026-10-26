// diablocraft-n9s4n: a character saved with a Temporary buff up comes back without it. The real dc_common.cpp
// serializes the contributions as Stats::Save writes them, reads them back as Stats::Load does and keeps what
// DropRebuiltSources keeps. Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "../../src/common/dc_common.h"

#include <cstdio>
#include <vector>

#include <stdexcept>

// dc_common.cpp asks the world for these when it calculates a sheet; the round trip never does, so they only link.
namespace DC::NumericData
{
double Rule(char const*) { throw std::logic_error("not asked by the round trip"); }
unsigned MaximumLevel() { throw std::logic_error("not asked by the round trip"); }
double BaseFury(unsigned) { throw std::logic_error("not asked by the round trip"); }
BlockTuning Block() { throw std::logic_error("not asked by the round trip"); }
}

using namespace DC;

static int failures = 0, cases = 0;

static void expect(bool ok, char const* what)
{
    ++cases;
    if (!ok)
    {
        std::printf("FAIL %s\n", what);
        ++failures;
    }
}

static bool Has(std::vector<Contribution> const& all, Source source, Stat stat, std::uint64_t id, double value)
{
    for (Contribution const& c : all)
        if (c.source == source && c.stat == stat && c.id == id && c.value == value)
            return true;
    return false;
}

int main()
{
    std::vector<Contribution> const saved = {
        {Source::Items, Stat::Strength, 70001, 500, Bucket::Flat, Element::Physical},
        {Source::Gems, Stat::CritDamage, 12, 50, Bucket::Flat, Element::Physical},
        {Source::Passives, Stat::AttackSpeed, 3, 10, Bucket::Flat, Element::Physical},
        {Source::Augments, Stat::Vitality, 4, 25, Bucket::Flat, Element::Physical},
        {Source::Paragon, Stat::Vitality, 1, 5, Bucket::Flat, Element::Physical},
        // two buffs up at the logout: a mantra's and a pylon's
        {Source::Temporary, Stat::AttackSpeed, 900001, 25, Bucket::Flat, Element::Physical},
        {Source::Temporary, Stat::ElementalDamage, 900002, 20, Bucket::Flat, Element::Fire},
    };
    std::vector<Contribution> loaded = DeserializeContributions(Serialize(saved));
    expect(loaded.size() == saved.size(), "the save round-trips every contribution");
    DropRebuiltSources(loaded);

    bool anyTemporary = false, anyParagon = false;
    for (Contribution const& c : loaded)
    {
        anyTemporary |= c.source == Source::Temporary;
        anyParagon |= c.source == Source::Paragon;
    }
    expect(!anyTemporary, "no Temporary contribution survives the load");
    expect(!anyParagon, "Paragon is still left to its login hook");
    expect(Has(loaded, Source::Items, Stat::Strength, 70001, 500), "an item's stat is kept");
    expect(Has(loaded, Source::Gems, Stat::CritDamage, 12, 50), "a gem's stat is kept");
    expect(Has(loaded, Source::Passives, Stat::AttackSpeed, 3, 10), "a passive's stat is kept");
    expect(Has(loaded, Source::Augments, Stat::Vitality, 4, 25), "an augment's stat is kept");
    expect(loaded.size() == 4, "exactly the four kept sources remain");

    // The sheet a load calculates from them has no buff in it: the attack speed is the passive's alone.
    double attackSpeed = 0;
    for (Contribution const& c : loaded)
        if (c.stat == Stat::AttackSpeed)
            attackSpeed += c.value;
    expect(attackSpeed == 10, "the attack speed is the passive's 10, not 10 + the buff's 25");

    std::vector<Contribution> none;
    DropRebuiltSources(none);
    expect(none.empty(), "an empty save stays empty");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
