// The real dc_witch_doctor_mana.h, dc_resources.h and the generated dc_resource_data.h over the registry harness's shim
// Player. Every number comes from the generated registry row or from argv (the sheets' values, read by
// test_witch_doctor_mana.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case and
// exits 1.
#include "classes/witch_doctor/dc_witch_doctor_mana.h"

#include <cstdio>
#include <cstdlib>

using namespace DC;
using DC::Combat::WitchDoctor::Gain;

static int failures = 0;
static int cases = 0;

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
    // argv: the four per-hit gains (Spined Dart, Blazing Spiders, Toad Affinity, The Spirit Is Willing), a spender's
    // cost (Haunt) and a second spender's (Piranhas).
    if (argc < 7)
        return 2;
    double const gains[4] = {std::atof(argv[1]), std::atof(argv[2]), std::atof(argv[3]), std::atof(argv[4])};
    double const haunt = std::atof(argv[5]), piranhas = std::atof(argv[6]);
    auto const& mana = Resources::Mana;
    uint32_t const doctor = mana.classId, monk = Resources::Spirit.classId, barbarian = Resources::Fury.classId;

    // The registry row: stock Mana, one unit a point, 750 at every level, 50 a second, no decay, full at login.
    expect(Resources::Slot(mana) == POWER_MANA, "Mana is in the Mana slot");
    expect(mana.role == Resources::Data::Role::Primary, "Mana is the primary");
    expect(mana.scale == 1.0, "one unit a point", mana.scale, 1);
    expect(mana.pool == 750.0, "pool", mana.pool, 750);
    expect(mana.regenPerSecond == 50.0, "regenerates 50 a second", mana.regenPerSecond, 50);
    expect(mana.decay == Resources::Data::Decay::None, "no decay");
    expect(mana.startsFull, "starts full");
    expect(mana.modulePaid, "the pulse is the one source");
    expect(Resources::Of(doctor) == &mana && !Resources::Of(doctor, Resources::Data::Role::Second), "one resource");

    auto fresh = [&]
    {
        Player* p = new Player();
        p->display = POWER_MANA;
        p->SetMaxPower(POWER_MANA, uint32_t(Resources::ToUnits(mana, mana.pool)));
        return p;
    };

    // Each on-hit gain pays its sheet number, once per enemy hit, and no other power moves.
    for (int which = 0; which < 4; ++which)
    {
        Player* p = fresh();
        expect(Gain(p, doctor, 1, gains[which], 1), "an on-hit rune pays");
        expect(Resources::Get(p, mana) == gains[which], "one hit adds the sheet's value", Resources::Get(p, mana),
               gains[which]);
        Gain(p, doctor, 1, gains[which], 3);
        expect(Resources::Get(p, mana) == 4 * gains[which], "three more hits add three times", Resources::Get(p, mana),
               4 * gains[which]);
        expect(Resources::Units(p, mana) == uint32_t(4 * gains[which]), "stored at one Mana unit a point");
        for (int other : {POWER_RAGE, POWER_FOCUS, POWER_ENERGY, POWER_RUNIC_POWER})
            expect(p->GetPower(Powers(other)) == 0, "no other power moves", other);
    }

    // The pool stops at 750 and a spend stops at 0.
    Player* full = fresh();
    for (int hit = 0; hit < 40; ++hit)
        Gain(full, doctor, 1, gains[0], 1);
    expect(Resources::Get(full, mana) == 750, "Mana capped at 750", Resources::Get(full, mana), 750);
    Resources::SpendUnits(full, mana, int32_t(Resources::ToUnits(mana, haunt)));
    expect(Resources::Get(full, mana) == 750 - haunt, "Haunt takes its cost", Resources::Get(full, mana), 750 - haunt);
    Resources::SpendUnits(full, mana, int32_t(Resources::ToUnits(mana, piranhas)));
    expect(Resources::Get(full, mana) == 750 - haunt - piranhas, "Piranhas takes its cost");
    Resources::SpendUnits(full, mana, 5000);
    expect(Resources::Get(full, mana) == 0, "a spend cannot go below 0");

    // Who is not paid: another class, a Witch Doctor not showing Mana, nothing generated, no hit.
    for (uint32_t other : {monk, barbarian, uint32_t(0)})
    {
        Player* q = fresh();
        expect(!Gain(q, other, 1, gains[0], 1) && Resources::Units(q, mana) == 0, "another class is not paid", other);
    }
    Player* shown = fresh();
    shown->display = POWER_RAGE;
    expect(!Gain(shown, doctor, 1, gains[0], 1) && Resources::Units(shown, mana) == 0, "Mana not shown, not paid");
    Player* zero = fresh();
    expect(!Gain(zero, doctor, 1, 0, 1) && !Gain(zero, doctor, 1, -3, 1) && !Gain(zero, doctor, 1, gains[0], 0) &&
               !Gain(nullptr, doctor, 1, gains[0], 1),
           "zero, negative, no hit, no player");

    // Paragon: +4 Mana a point, up to 50 points.
    expect(Resources::ParagonMaximum(mana, 50) == 200, "50 Paragon points, +200 Mana", Resources::ParagonMaximum(mana, 50),
           200);
    expect(Resources::ParagonMaximum(mana, 7) == 28, "7 points, +28", Resources::ParagonMaximum(mana, 7), 28);

    std::printf("cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
