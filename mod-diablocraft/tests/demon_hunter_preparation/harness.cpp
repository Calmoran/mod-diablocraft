// The real dc_demon_hunter_preparation.h and dc_resource_pool.h. The rune names and numbers come from argv (read from
// the sheets and the tunables by test_demon_hunter_preparation.py); nothing is typed in here. Prints "cases=N" and
// exits 0, or names the first failing case and exits 1.
#include "classes/dc_resource_pool.h"
#include "classes/demon_hunter/dc_demon_hunter_preparation.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::DemonHunter;
using namespace DC::Combat::DemonHunter::Preparation;

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

int main(int argc, char** argv)
{
    // argv: the five runes A to E, then the Discipline the skill restores, Punishment's Hatred, Focused Mind's
    // Discipline and seconds, its tick, Battle Scars' Life share, Backup Plan's chance and Invigoration's maximum.
    if (argc < 14)
        return 2;
    std::string const punishment = argv[1], invigoration = argv[2], focused = argv[3], scars = argv[4],
                      backup = argv[5];
    double const base = std::atof(argv[6]), hatred = std::atof(argv[7]), over = std::atof(argv[8]),
                 seconds = std::atof(argv[9]), tick = std::atof(argv[10]), healPct = std::atof(argv[11]),
                 chance = std::atof(argv[12]), pool = std::atof(argv[13]);

    expect(RuneOf(punishment) == Rune::Punishment && RuneOf(invigoration) == Rune::Invigoration &&
               RuneOf(focused) == Rune::FocusedMind && RuneOf(scars) == Rune::BattleScars &&
               RuneOf(backup) == Rune::BackupPlan,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {punishment, invigoration, focused, scars, backup})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // What a cast restores.
    Restore plain = RestoreOf(Rune::None, base, 0);
    expect(plain.disciplineNow == base && plain.hatredNow == 0 && plain.disciplineOver == 0,
           "the base skill restores its Discipline at once");
    Restore punish = RestoreOf(Rune::Punishment, base, hatred);
    expect(punish.disciplineNow == base && punish.hatredNow == hatred && punish.disciplineOver == 0,
           "Punishment restores Hatred as well", punish.hatredNow, hatred);
    Restore focus = RestoreOf(Rune::FocusedMind, base, over);
    expect(focus.disciplineNow == 0 && focus.hatredNow == 0 && focus.disciplineOver == over,
           "Focused Mind restores its Discipline over time", focus.disciplineOver, over);
    for (Rune rune : {Rune::Invigoration, Rune::BattleScars, Rune::BackupPlan})
    {
        Restore other = RestoreOf(rune, base, 7);
        expect(other.disciplineNow == base && other.hatredNow == 0 && other.disciplineOver == 0,
               "the other runes restore the skill's Discipline", other.disciplineNow, base);
    }

    // Focused Mind: the ticks together give the whole.
    unsigned const ticks = Dot::Ticks(seconds, tick);
    expect(ticks > 1, "Focused Mind ticks more than once", ticks, 2);
    expect(std::fabs(RegenTick(over, seconds, tick) * ticks - over) < 1e-9, "the ticks make the Discipline",
           RegenTick(over, seconds, tick) * ticks, over);
    expect(RegenTick(over, seconds, 0) == 0, "no tick length, no Discipline");
    double clock = 0;
    unsigned struck = 0;
    int const updates = int(seconds * 1000.0 / 67.0);
    for (int update = 0; update < updates; ++update)
        struck += Due(clock, 67, tick * 1000.0);
    expect(std::fabs(double(struck) - updates * 0.067 / tick) < 1.0, "a tick every interval in server updates of 67 ms",
           double(struck), updates * 0.067 / tick);

    // Battle Scars: the share of the maximum Life.
    expect(std::fabs(HealOf(1000, healPct) - 1000 * healPct / 100.0) < 1e-9, "the share of the maximum Life",
           HealOf(1000, healPct), 1000 * healPct / 100.0);
    expect(HealOf(0, healPct) == 0 && HealOf(1000, 0) == 0 && HealOf(-5, healPct) == 0 && HealOf(1000, -10) == 0,
           "no Life, no share, no heal");

    // Backup Plan: a roll under the chance keeps the cooldown away; the chance as a share of the rolls.
    expect(CooldownSkipped(0.0, chance) && CooldownSkipped(chance - 0.01, chance),
           "a roll under the chance skips the cooldown");
    expect(!CooldownSkipped(chance, chance) && !CooldownSkipped(99.99, chance), "a roll at or over it does not");
    expect(!CooldownSkipped(0.0, 0) && CooldownSkipped(99.99, 100), "no chance never, all of it always");
    unsigned skipped = 0;
    for (int roll = 0; roll < 1000; ++roll)
        skipped += CooldownSkipped(roll / 10.0, chance) ? 1 : 0;
    expect(skipped == unsigned(chance * 10 + 0.5), "the chance is the share of the rolls", double(skipped),
           chance * 10);

    // Invigoration: the pool's higher maximum, one source apiece, gone when the rune is.
    using namespace DC::Resources;
    std::uint64_t const player = 4242, other = 4243;
    expect(Pool::Bonus(player) == 0, "no source, no bonus");
    expect(Pool::Set(player, 85791, pool) && Pool::Bonus(player) == pool, "a source adds its points",
           Pool::Bonus(player), pool);
    expect(!Pool::Set(player, 85791, pool) && Pool::Bonus(player) == pool, "the same points again change nothing",
           Pool::Bonus(player), pool);
    expect(Pool::Set(player, 85900, 5) && Pool::Bonus(player) == pool + 5, "a second source adds to the first",
           Pool::Bonus(player), pool + 5);
    expect(Pool::Bonus(other) == 0, "another player has none", Pool::Bonus(other), 0);
    expect(Pool::Set(player, 85791, 0) && Pool::Bonus(player) == 5, "a source set to nothing is gone",
           Pool::Bonus(player), 5);
    expect(!Pool::Set(player, 85791, 0), "taking away what is not there changes nothing");
    Pool::Clear(player);
    expect(Pool::Bonus(player) == 0, "clearing a player takes every source");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
