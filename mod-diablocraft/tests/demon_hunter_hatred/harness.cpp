// The real dc_demon_hunter_hatred.h, dc_resources.h and the generated dc_resource_data.h over the registry harness's
// shim Player. Every number comes from the generated registry row or from argv (the sheet's values, read by
// test_demon_hunter_resources.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing
// case and exits 1.
#include "classes/demon_hunter/dc_demon_hunter_hatred.h"

#include <cstdio>
#include <cstdlib>

using namespace DC;
using DC::Combat::DemonHunter::Generate;

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
    // argv: Hungering Arrow's generated Hatred, Serrated Arrow's, Impale's Hatred cost, Caltrops' Discipline cost.
    if (argc < 5)
        return 2;
    double const arrow = std::atof(argv[1]), serrated = std::atof(argv[2]), impale = std::atof(argv[3]),
                 caltrops = std::atof(argv[4]);
    auto const& hatred = Resources::Hatred;
    auto const& discipline = Resources::Discipline;
    uint32_t const hunter = hatred.classId, monk = Resources::Spirit.classId, barbarian = Resources::Fury.classId;

    // The registry rows: Hatred on Energy and Discipline on Focus, one unit a point, nothing decays.
    expect(hunter == discipline.classId, "one class holds both");
    expect(Resources::Slot(hatred) == POWER_ENERGY, "Hatred is in Energy");
    expect(Resources::Slot(discipline) == POWER_FOCUS, "Discipline is in Focus");
    expect(hatred.role == Resources::Data::Role::Primary && discipline.role == Resources::Data::Role::Second,
           "Hatred primary, Discipline second");
    expect(hatred.scale == 1.0 && discipline.scale == 1.0, "one unit a point", hatred.scale, discipline.scale);
    expect(hatred.pool == 125.0, "Hatred pool", hatred.pool, 125);
    expect(discipline.pool == 30.0, "Discipline pool", discipline.pool, 30);
    expect(hatred.regenPerSecond == 5.0, "Hatred regenerates 5 a second", hatred.regenPerSecond, 5);
    expect(discipline.regenPerSecond == 1.0, "Discipline regenerates 1 a second", discipline.regenPerSecond, 1);
    expect(hatred.decay == Resources::Data::Decay::None && discipline.decay == Resources::Data::Decay::None,
           "no decay");
    expect(hatred.startsFull && discipline.startsFull, "both start full");

    auto fresh = [&]
    {
        Player* p = new Player();
        p->display = POWER_ENERGY;
        p->SetMaxPower(POWER_ENERGY, uint32_t(Resources::ToUnits(hatred, hatred.pool)));
        p->SetMaxPower(POWER_FOCUS, uint32_t(Resources::ToUnits(discipline, discipline.pool)));
        return p;
    };

    // A fresh Demon Hunter shows Hatred 0 of 125 and Discipline 0 of 30 until the login fills them.
    Player* p = fresh();
    expect(Resources::Max(p, hatred) == 125 && Resources::Max(p, discipline) == 30, "pools 125 and 30");

    // A primary pays Hatred and never touches Discipline; a rune that raises it pays its own number.
    expect(Generate(p, hunter, 1, arrow), "Hungering Arrow pays");
    expect(Resources::Get(p, hatred) == arrow, "Hungering Arrow adds its sheet value", Resources::Get(p, hatred),
           arrow);
    expect(Resources::Get(p, discipline) == 0, "Discipline untouched by Hatred generation");
    Generate(p, hunter, 2, serrated);
    expect(Resources::Get(p, hatred) == arrow + serrated, "Serrated Arrow's own number adds");
    expect(Resources::Units(p, hatred) == uint32_t(arrow + serrated), "stored at one Energy unit a point");

    // A Hatred spender takes its cost from Energy only; a Discipline spender from Focus only.
    for (int hit = 0; hit < 10; ++hit)
        Generate(p, hunter, 1, arrow);
    Resources::Add(p, discipline, 30);
    double const pooled = Resources::Get(p, hatred);
    Resources::SpendUnits(p, hatred, int32_t(Resources::ToUnits(hatred, impale)));
    expect(Resources::Get(p, hatred) == pooled - impale, "Impale takes its Hatred", Resources::Get(p, hatred),
           pooled - impale);
    expect(Resources::Get(p, discipline) == 30, "a Hatred spender leaves Discipline");
    Resources::SpendUnits(p, discipline, int32_t(Resources::ToUnits(discipline, caltrops)));
    expect(Resources::Get(p, discipline) == 30 - caltrops, "Caltrops takes its Discipline",
           Resources::Get(p, discipline), 30 - caltrops);
    expect(Resources::Get(p, hatred) == pooled - impale, "a Discipline spender leaves Hatred");

    // Each pool stops at its own maximum and at 0.
    Player* full = fresh();
    for (int hit = 0; hit < 60; ++hit)
        Generate(full, hunter, 1, serrated);
    expect(Resources::Get(full, hatred) == 125, "Hatred capped at 125", Resources::Get(full, hatred), 125);
    Resources::Add(full, discipline, 100);
    expect(Resources::Get(full, discipline) == 30, "Discipline capped at 30", Resources::Get(full, discipline), 30);
    Resources::SpendUnits(full, discipline, 500);
    Resources::SpendUnits(full, hatred, 500);
    expect(Resources::Get(full, discipline) == 0 && Resources::Get(full, hatred) == 0, "a spend cannot go below 0");

    // Who is not paid: another class, a Demon Hunter not showing Hatred, nothing generated.
    for (uint32_t other : {monk, barbarian, uint32_t(0)})
    {
        Player* q = fresh();
        expect(!Generate(q, other, 1, arrow) && Resources::Units(q, hatred) == 0, "another class is not paid", other);
    }
    Player* shown = fresh();
    shown->display = POWER_RAGE;
    expect(!Generate(shown, hunter, 1, arrow) && Resources::Units(shown, hatred) == 0, "Hatred not shown, not paid");
    Player* zero = fresh();
    expect(!Generate(zero, hunter, 1, 0) && !Generate(zero, hunter, 1, -3) && !Generate(nullptr, hunter, 1, arrow),
           "zero, negative, no player");

    // Paragon: +0.5 Hatred a point paid as +1 per two points; Discipline gets none.
    expect(Resources::ParagonMaximum(hatred, 50) == 25, "50 Paragon points, +25 Hatred",
           Resources::ParagonMaximum(hatred, 50), 25);
    expect(Resources::ParagonMaximum(hatred, 7) == 3, "7 points, +3", Resources::ParagonMaximum(hatred, 7), 3);
    expect(Resources::ParagonMaximum(discipline, 50) == 0, "Paragon gives Discipline nothing",
           Resources::ParagonMaximum(discipline, 50));

    std::printf("cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
