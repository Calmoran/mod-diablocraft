// The real dc_necromancer_bone_spirit_math.h and dc_charge_store.h. The rune names and numbers come from argv (read from the sheets by
// test_necromancer_bone_spirit.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/necromancer/dc_necromancer_bone_spirit_math.h"
#include "combat/dc_charge_store.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Necromancer::BoneSpirit;
using DC::Combat::ChargeStore;

static int failures = 0, cases = 0;

static void expect(bool ok, char const* what, double a = 0, double b = 0)
{
    ++cases;
    if (!ok)
    {
        std::printf("FAIL %s (%g vs %g)\n", what, a, b);
        ++failures;
    }
}

static bool near(double a, double b)
{
    return std::fabs(a - b) < 1e-9;
}

int main(int argc, char** argv)
{
    // argv: the five runes A to E; the charges, Poltergeist's charges, the recharge seconds, the seconds a corpse takes off it, Astral
    // Projection's bonus a percent for each enemy passed
    if (argc < 11)
        return 2;
    std::string const names[5] = {argv[1], argv[2], argv[3], argv[4], argv[5]};
    unsigned const cap = unsigned(std::atoi(argv[6])), capMore = unsigned(std::atoi(argv[7]));
    std::uint64_t const period = std::uint64_t(std::atof(argv[8]) * 1000), cut = std::uint64_t(std::atof(argv[9]) * 1000);
    double const bonus = std::atof(argv[10]);

    expect(RuneOf(names[0]) == Rune::Possession && RuneOf(names[1]) == Rune::PanicAttack && RuneOf(names[2]) == Rune::Poltergeist &&
               RuneOf(names[3]) == Rune::UnfinishedBusiness && RuneOf(names[4]) == Rune::AstralProjection,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& name : names)
        seen.insert(int(RuneOf(name)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "no two runes share a name, and none is None");
    expect(RuneOf("") == Rune::None && RuneOf("Bone Spirit") == Rune::None && RuneOf("possession") == Rune::None,
           "the skill itself and a misspelling are no rune");
    expect(KeepsTheSkillsHit(Rune::UnfinishedBusiness) && !KeepsTheSkillsHit(Rune::None) && !KeepsTheSkillsHit(Rune::Possession) &&
               !KeepsTheSkillsHit(Rune::AstralProjection),
           "only Unfinished Business keeps the skill's hit under its explosion");

    // The way of the spirit: the enemies between the caster and the target, near the line.
    expect(PassedThrough(0, 0, 20, 0, 10, 0, 3), "an enemy on the way is passed");
    expect(PassedThrough(0, 0, 20, 0, 10, 1.5, 3) && !PassedThrough(0, 0, 20, 0, 10, 1.51, 3), "the edge of the way counts, past it does not");
    expect(!PassedThrough(0, 0, 20, 0, 20, 0, 3) && !PassedThrough(0, 0, 20, 0, 25, 0, 3), "the target and what lies past it are not passed");
    expect(!PassedThrough(0, 0, 20, 0, -2, 0, 3), "an enemy behind the caster is not passed");
    expect(PassedThrough(0, 0, 0, 20, 0, 10, 3) && !PassedThrough(0, 0, 0, 20, 10, 0, 3), "the way is the line to the target, whichever way it runs");
    expect(!PassedThrough(5, 5, 5, 5, 5, 5, 3), "no way to a target on the caster");
    expect(near(PassBonusPct(4, bonus), 4 * bonus) && PassBonusPct(0, bonus) == 0.0 && PassBonusPct(3, -5) == 0.0,
           "each enemy passed adds its share, none for none or a negative share");

    // The charges: full at first; the last spent holds the button for the recharge; one lands each period.
    ChargeStore store;
    std::uint64_t wait = 0;
    for (unsigned i = 0; i + 1 < cap; ++i)
        wait = store.Spend(0, cap, period);
    expect(wait == 0 && store.count == 1, "a charge left clears the button", double(wait), 0);
    wait = store.Spend(0, cap, period);
    expect(wait == period && store.count == 0, "the last charge spent holds the button for the recharge", double(wait), double(period));
    expect(store.Refill(period - 1, cap, period) == 0, "a millisecond before the period no charge has landed");
    expect(store.Refill(period, cap, period) == 1, "one lands at the period");
    expect(store.Refill(period * 2, cap, period) == 2, "and the next a period after that");
    expect(store.Refill(period * 100, cap, period) == cap, "never past the cap");

    // A corpse consumed takes its seconds off the recharge under way.
    ChargeStore more;
    for (unsigned i = 0; i < cap; ++i)
        more.Spend(0, cap, period);
    wait = more.Shorten(1000, cap, period, cut);
    expect(wait == period - 1000 - cut && more.count == 0, "a corpse shortens the recharge by its seconds", double(wait), double(period - 1000 - cut));
    wait = more.Shorten(1000, cap, period, cut * 3);
    expect(wait == period - 1000 - cut * 4 && more.count == 0, "each corpse takes its own off");
    wait = more.Shorten(1000, cap, period, period * 2);
    expect(wait == 0 && more.count >= 1, "enough corpses land the charge at once", double(wait), 0);
    ChargeStore full;
    full.Refill(0, cap, period);
    full.Shorten(0, cap, period, cut * 5);
    expect(full.count == cap && full.next == 0, "a full store has nothing to shorten");

    // Poltergeist stores one more.
    ChargeStore plus;
    expect(plus.Refill(0, capMore, period) == capMore && capMore == cap + 1, "Poltergeist stores one more charge");
    expect(plus.Refill(0, cap, period) == cap, "a rune changed back to the skill holds no more than its cap");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
