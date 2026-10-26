// The real dc_witch_doctor_passives_math.h. The passives' numbers come from argv (read from the sheet by
// test_witch_doctor_passives.py); the pools are the Witch Doctor's own (Mana 750; a level 70 Life). Prints "cases=N"
// and exits 0, or names the first failing case and exits 1.
#include "classes/witch_doctor/dc_witch_doctor_passives_math.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::WitchDoctor::Passive;

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
    // argv: Jungle Fortitude's reduction, Circle of Life's radius and chance, Spiritual Attunement's pool and
    // regeneration, Gruesome Feast's Mana, Blood Ritual's share and Life regeneration
    if (argc < 9)
        return 2;
    double const reduction = std::atof(argv[1]), radius = std::atof(argv[2]), chance = std::atof(argv[3]),
                 pool = std::atof(argv[4]), regen = std::atof(argv[5]), gain = std::atof(argv[6]),
                 share = std::atof(argv[7]), lifeRegen = std::atof(argv[8]);
    double const mana = 750, life = 15016;

    // A share of a pool.
    expect(near(Share(mana, pool), mana * pool / 100), "a share of the Mana pool", Share(mana, pool),
           mana * pool / 100);
    expect(near(Share(mana, regen), mana * regen / 100), "Spiritual Attunement's regeneration is a share of the pool");
    expect(near(Share(mana, gain), mana * gain / 100), "Gruesome Feast's Mana is a share of the pool");
    expect(near(Share(life, lifeRegen), life * lifeRegen / 100), "Blood Ritual's regeneration is a share of the Life");
    expect(Share(0, pool) == 0 && Share(-mana, pool) == 0 && Share(mana, 0) == 0 && Share(mana, -pool) == 0,
           "no pool, no percent or a negative number gives nothing");

    // Jungle Fortitude.
    expect(near(Reduced(1000, reduction), 1000 * (1 - reduction / 100)), "damage after the reduction",
           Reduced(1000, reduction), 1000 * (1 - reduction / 100));
    expect(Reduced(1000, 100) == 0 && Reduced(1000, 250) == 0, "a share of a hundred or more takes it all");
    expect(Reduced(1000, 0) == 1000 && Reduced(1000, -reduction) == 1000, "no reduction, or a negative one, leaves it");
    expect(Reduced(0, reduction) == 0 && Reduced(-5, reduction) == 0, "no damage stays none");

    // Spiritual Attunement: the pool's added points are a share of the pool without them, however often it is asked.
    expect(near(PoolBonus(mana, 0, pool), mana * pool / 100), "the bonus on a bare pool");
    double const bonus = PoolBonus(mana, 0, pool);
    expect(near(PoolBonus(mana + bonus, bonus, pool), bonus), "the bonus does not feed on itself",
           PoolBonus(mana + bonus, bonus, pool), bonus);
    expect(PoolBonus(mana, 0, 0) == 0 && PoolBonus(0, 0, pool) == 0, "no percent or no pool adds nothing");

    // Circle of Life.
    expect(Procs(chance - 0.01, chance) && !Procs(chance, chance), "the roll holds below the chance and not at it");
    expect(!Procs(0, 0) && Procs(99.99, 100), "no chance never rolls, a hundred always");
    expect(InRange(radius, radius, 0) && !InRange(radius + 0.01, radius, 0), "the circle ends at its radius");
    expect(InRange(radius + 5, radius, 5) && !InRange(radius + 5.01, radius, 5), "the gold pickup radius widens it");
    expect(!InRange(radius + 5, radius, -5) && InRange(radius, radius, -5), "a negative pickup radius widens nothing");
    expect(!InRange(0, 0, 10), "no radius is no range");

    // Bad Medicine: the Poison school only (the module's Poison is the shadow mask).
    expect(PoisonMask(32u) && PoisonMask(32u | 4u), "a Poison record");
    expect(!PoisonMask(1u) && !PoisonMask(4u) && !PoisonMask(8u) && !PoisonMask(0u), "another school is not Poison");

    // Blood Ritual: the share of a cost, as the same fraction of the Life pool, never past 1 Life left.
    Payment p = Sacrifice(150, share, mana, life, 1.0, life);
    double const want = 150 * share / 100, wanted = want / mana * life;
    expect(near(p.manaBack, want) && near(p.life, wanted), "a full pool pays the whole share in Life", p.life, wanted);
    p = Sacrifice(150, share, mana, life, 2.0, life);
    expect(near(p.manaBack, want) && near(p.life, wanted * 2), "the scale multiplies the Life paid", p.life,
           wanted * 2);
    p = Sacrifice(150, share, mana, life, 1.0, 100);
    expect(near(p.life, 99) && near(p.manaBack, want * 99 / wanted),
           "Life leaves 1: what it cannot pay stays a Mana cost", p.life, 99);
    p = Sacrifice(150, share, mana, life, 1.0, 1);
    expect(p.life == 0 && p.manaBack == 0, "at 1 Life nothing is paid in Life and the whole cost stays Mana");
    p = Sacrifice(150, 0, mana, life, 1.0, life);
    expect(p.life == 0 && p.manaBack == 0, "no share pays nothing");
    p = Sacrifice(0, share, mana, life, 1.0, life);
    expect(p.life == 0 && p.manaBack == 0, "a free skill pays nothing");
    p = Sacrifice(150, share, 0, life, 1.0, life);
    expect(p.life == 0 && p.manaBack == 0, "no Mana pool pays nothing");
    p = Sacrifice(150, share, mana, life, 0, life);
    expect(p.life == 0 && p.manaBack == 0, "a scale of none pays nothing");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
