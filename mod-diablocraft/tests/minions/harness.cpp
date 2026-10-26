// The real combat/dc_minions_math.h. The numbers come from argv (read from the sheets and tunables by test_minions.py);
// nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "combat/dc_minions_math.h"

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::Minions;

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
    // argv: the Skeletal Mage cap, the Skeleton cap (max_count), the skeleton interval (seconds), the hits a skeleton
    // takes, the Command Skeletons damage and bonus, the Skeletal Mage damage, the mage's duration (seconds), the
    // Simulacrum's Life share
    if (argc < 11)
        return 2;
    unsigned const mageCap = unsigned(std::atoi(argv[1])), skeletonCap = unsigned(std::atoi(argv[2])),
                   hitsToDie = unsigned(std::atoi(argv[4]));
    double const interval = std::atof(argv[3]) * 1000.0, damage = std::atof(argv[5]), bonus = std::atof(argv[6]),
                 mageDamage = std::atof(argv[7]), mageSeconds = std::atof(argv[8]), lifePct = std::atof(argv[9]),
                 frenzyPct = std::atof(argv[10]);

    // Admission: room is made by sending the oldest away, never by refusing; no cap is no limit.
    for (unsigned alive = 0; alive < mageCap; ++alive)
        expect(Admit(alive, mageCap).raise && !Admit(alive, mageCap).dismissOldest, "room: raised, nobody sent away",
               alive, mageCap);
    expect(Admit(mageCap, mageCap).raise && Admit(mageCap, mageCap).dismissOldest, "a full group sends its oldest away",
           mageCap, mageCap);
    expect(Admit(mageCap + 3, mageCap).dismissOldest, "above the cap still sends one away");
    expect(Admit(500, 0).raise && !Admit(500, 0).dismissOldest, "a cap of 0 is no cap");

    // The keeper raises one at a time, only below the wanted number, only when its clock has run.
    expect(KeeperDue(1000, 1000, 0, skeletonCap), "due on the moment of its clock", 1000, 1000);
    expect(!KeeperDue(999, 1000, 0, skeletonCap), "not due a moment early");
    expect(!KeeperDue(5000, 1000, skeletonCap, skeletonCap), "not due when the wanted number stands");
    expect(KeeperDue(5000, 1000, skeletonCap - 1, skeletonCap), "due with one short");
    expect(!KeeperDue(5000, 0, 0, 0), "nothing wanted, nothing raised");

    // The clock: one every interval after a raise, and nothing before the return time after a loss.
    expect(NextAfterRaise(4000, std::uint64_t(interval)) == 4000 + std::uint64_t(interval), "a raise sets the next one",
           double(NextAfterRaise(4000, std::uint64_t(interval))), 4000 + interval);
    expect(NextAfterLoss(1000, 0, 10000) == 11000, "a loss holds the next for the return time",
           double(NextAfterLoss(1000, 0, 10000)), 11000);
    expect(NextAfterLoss(1000, 50000, 10000) == 50000, "a loss never brings the next one earlier",
           double(NextAfterLoss(1000, 50000, 10000)), 50000);
    expect(NextAfterLoss(1000, 0, 0) == 1000, "no return time: at once", double(NextAfterLoss(1000, 0, 0)), 1000);

    // A timed minion is over at its time, a permanent one never.
    std::uint64_t const life = std::uint64_t(mageSeconds * 1000.0);
    expect(!Expired(2000 + life - 1, 2000, life), "a moment before its time it stands");
    expect(Expired(2000 + life, 2000, life), "at its time it is over", double(2000 + life), double(life));
    expect(!Expired(99999999, 2000, 0), "no life given: it stays");

    // A skeleton that dies after so many hits.
    HitLimit hits;
    bool died = false;
    unsigned taken = 0;
    for (; taken < hitsToDie + 5 && !died; ++taken)
        died = hits.Take(hitsToDie);
    expect(died && taken == hitsToDie, "dies on the last hit and not before", taken, hitsToDie);
    HitLimit own;
    bool ever = false;
    for (int i = 0; i < 1000; ++i)
        ever = ever || own.Take(0);
    expect(!ever, "no limit: it has its own Life");

    // A commanded blow: the bonus against the ordered target only.
    expect(BlowPct(damage, false, bonus) == damage, "another target takes the plain blow",
           BlowPct(damage, false, bonus), damage);
    expect(std::abs(BlowPct(damage, true, bonus) - damage * (1.0 + bonus / 100.0)) < 1e-9,
           "the ordered target takes the bonus", BlowPct(damage, true, bonus), damage * (1.0 + bonus / 100.0));
    expect(BlowPct(damage, true, bonus) > damage, "the bonus adds");
    expect(BlowPct(damage, true, 0) == damage, "no bonus, no change");
    expect(BlowPct(damage, true, -10) == damage, "a negative bonus is no bonus");

    // A commanded blow's rate (Frenzy's attack speed, argv 10): faster against the ordered target only.
    expect(CommandedRate(1.5, false, frenzyPct) == 1.5, "another target keeps the plain rate", CommandedRate(1.5, false, frenzyPct), 1.5);
    expect(std::abs(CommandedRate(1.5, true, frenzyPct) - 1.5 * (1.0 + frenzyPct / 100.0)) < 1e-9,
           "the ordered target is struck faster", CommandedRate(1.5, true, frenzyPct), 1.5 * (1.0 + frenzyPct / 100.0));
    expect(CommandedRate(1.5, true, 0) == 1.5 && CommandedRate(1.5, true, -20) == 1.5, "no speed bonus, no change");

    // A kind that fixes its own swing time waits it out whatever the owner's speed; every other kind waits one over the owner's rate.
    expect(SwingMs(2.0, 0) == 500.0 && SwingMs(1.0, 0) == 1000.0, "the owner's rate sets the wait", SwingMs(2.0, 0), 500.0);
    expect(SwingMs(2.0, 3000) == 3000.0 && SwingMs(0, 3000) == 3000.0, "the kind's own swing time replaces it", SwingMs(2.0, 3000), 3000.0);
    expect(SwingMs(0, 0) == 0.0 && SwingMs(-1, 0) == 0.0, "no rate and no swing time, no attack", SwingMs(0, 0), 0.0);

    // A boosted blow (Decay Golem's meal): the percent more, none for no boost.
    expect(std::abs(BoostedPct(damage, 120) - damage * 2.2) < 1e-9, "a boost adds its percent", BoostedPct(damage, 120), damage * 2.2);
    expect(BoostedPct(damage, 0) == damage && BoostedPct(damage, -30) == damage, "no boost, no change");

    // Over N attacks: equal shares that add back to the skill's number.
    expect(std::abs(PerHit(mageDamage, 2) * 2 - mageDamage) < 1e-9, "two hits add back to the skill's damage",
           PerHit(mageDamage, 2) * 2, mageDamage);
    expect(PerHit(mageDamage, 1) == mageDamage, "one attack is the whole");
    expect(PerHit(mageDamage, 0) == mageDamage, "no attacks is one");

    // The copy: its share of the owner's Life, never nothing.
    expect(CopyLife(10000, lifePct) == std::uint32_t(10000 * lifePct / 100.0), "the share of the owner's Life",
           CopyLife(10000, lifePct), 10000 * lifePct / 100.0);
    expect(CopyLife(0, lifePct) == 1, "never less than 1");
    expect(CopyLife(10000, -5) == 1, "a negative share is 1");
    expect(CopyLife(10000, 50) == 5000, "half is half", CopyLife(10000, 50), 5000);

    // A decoy stands where it was raised; every other minion follows its owner.
    expect(!Follows(true) && Follows(false), "a stay-put kind does not follow, every other does");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
