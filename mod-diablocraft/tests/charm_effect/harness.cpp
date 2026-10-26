// The real dc_charm_effect_math.h. The chance comes from argv (read from the Crusader's sheet by test_charm_effect.py);
// nothing else is typed in here. Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "combat/dc_charm_effect_math.h"

#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::CharmEffect;

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
    // argv: a chance in percent, the charm's seconds
    if (argc < 3)
        return 2;
    double const chance = std::atof(argv[1]), seconds = std::atof(argv[2]);

    // A plain enemy monster is charmed; each thing that rules it out does.
    Target enemy;
    enemy.creature = enemy.alive = enemy.hostile = true;
    expect(CanCharm(enemy, seconds), "an enemy monster is charmed");
    expect(!CanCharm(enemy, 0) && !CanCharm(enemy, -1), "a charm of no time takes nothing");
    Target t = enemy;
    t.creature = false;
    expect(!CanCharm(t, seconds), "a player is not charmed");
    t = enemy;
    t.alive = false;
    expect(!CanCharm(t, seconds), "a dead monster is not charmed");
    t = enemy;
    t.hostile = false;
    expect(!CanCharm(t, seconds), "a friend is not charmed");
    t = enemy;
    t.alreadyCharmed = true;
    expect(!CanCharm(t, seconds), "a charmed monster is not charmed again");
    t = enemy;
    t.controlledByPlayer = true;
    expect(!CanCharm(t, seconds), "a player's pet is not charmed");
    t = enemy;
    t.boss = true;
    expect(!CanCharm(t, seconds), "a boss is not charmed");

    // The roll: under the chance, never at it, never with none.
    expect(Rolls(chance - 0.01, chance) && !Rolls(chance, chance) && !Rolls(100, chance),
           "a roll under the chance charms", chance, 0);
    expect(Rolls(0, chance), "the lowest roll charms");
    expect(!Rolls(0, 0) && !Rolls(0, -5) && !Rolls(-1, 0), "no chance never charms");
    expect(Rolls(99.9, 100) && !Rolls(100, 100), "a chance of 100 always charms");

    // The foe the monster is sent at: the nearest, the first of a tie, none when there is none.
    expect(!NearestFoe({}).has_value(), "no foe, no target");
    expect(NearestFoe({7.0}) == std::optional<std::size_t>(0), "one foe is the target");
    expect(NearestFoe({7.0, 3.0, 5.0}) == std::optional<std::size_t>(1), "the nearest foe is the target");
    expect(NearestFoe({4.0, 4.0, 5.0}) == std::optional<std::size_t>(0), "a tie keeps the first");

    // A charmed monster is sent again when it has no victim or its victim is dead.
    expect(Retarget(false, false) && Retarget(true, false) && Retarget(false, true), "no live victim, a new one");
    expect(!Retarget(true, true), "a monster in a fight is left to it");

    // Whose charm it is: a player charmer is the master; a holder is its summoner's, when that is a player; nothing else is.
    Charmer none;
    expect(MasterKindOf(none) == Master::None, "no charmer, no master");
    Charmer core;
    core.player = true;
    expect(MasterKindOf(core) == Master::Charmer, "the core's own charm names its player");
    Charmer held;
    held.holder = held.summonerPlayer = true;
    expect(MasterKindOf(held) == Master::HoldersSummoner, "a holder's summoner is the master");
    Charmer byMonster;
    byMonster.holder = true;
    expect(MasterKindOf(byMonster) == Master::None, "a holder a monster summoned is nobody's");
    Charmer summonOfAPlayer;
    summonOfAPlayer.summonerPlayer = true;
    expect(MasterKindOf(summonOfAPlayer) == Master::None, "a player's summon that is not the holder is nobody's");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
