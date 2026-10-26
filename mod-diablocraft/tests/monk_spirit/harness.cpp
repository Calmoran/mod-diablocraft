// diablocraft-4usi7 (Monk 2.1): the real dc_monk_spirit.h, dc_resources.h and the generated
// dc_resource_data.h over the registry harness's shim Player. Every number comes from the
// generated registry row or from argv (the sheet's values, read by test_monk_spirit.py); nothing
// is typed in here. Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/monk/dc_monk_spirit.h"

#include <cstdio>
#include <cstdlib>

using namespace DC;
using DC::Combat::Monk::Generate;

static int failures = 0;
static double percentOver = 0;
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
    // argv: primary generated values (Fists of Thunder, Quickening, Deadly Reach), then Lashing Tail Kick's cost, then Inspire's Spirit percent.
    if (argc < 6)
        return 2;
    double const fists = std::atof(argv[1]), quickening = std::atof(argv[2]), reach = std::atof(argv[3]),
                 kick = std::atof(argv[4]), inspire = std::atof(argv[5]);
    auto const& spirit = Resources::Spirit;
    uint32_t const monk = spirit.classId, barbarian = Resources::Fury.classId, wizard = Resources::ArcanePower.classId;

    // The registry row: Spirit lives in Runic Power at one unit a point (class powers P2), 250 points, nothing refills it.
    expect(Resources::Slot(spirit) == POWER_RUNIC_POWER, "slot is Runic Power");
    expect(spirit.scale == 1.0, "one unit a point", spirit.scale);
    expect(spirit.pool == 250.0, "pool", spirit.pool);
    expect(spirit.regenPerSecond == 0.0, "no regeneration", spirit.regenPerSecond);
    expect(spirit.decay == Resources::Data::Decay::None, "no decay");

    auto fresh = [&]
    {
        Player* p = new Player();
        p->display = POWER_RUNIC_POWER;
        p->SetMaxPower(POWER_RUNIC_POWER, uint32_t(Resources::ToUnits(spirit, spirit.pool)));
        return p;
    };

    // A level-70 Monk: the orb reads 0 of 250.
    Player* p = fresh();
    expect(Resources::Get(p, spirit) == 0 && Resources::Max(p, spirit) == 250, "orb 0/250", Resources::Get(p, spirit),
           Resources::Max(p, spirit));

    // Fists of Thunder: +14 a hit, stored as 14 units.
    expect(Generate(p, monk, 1, fists), "Fists of Thunder pays");
    expect(Resources::Get(p, spirit) == fists, "Fists of Thunder adds its sheet value", Resources::Get(p, spirit),
           fists);
    expect(Resources::Units(p, spirit) == uint32_t(fists), "stored at one unit a point");
    Generate(p, monk, 2, quickening);
    expect(Resources::Get(p, spirit) == fists + quickening, "Quickening's 20 adds");

    // A spender takes its sheet cost, in units, through the core's modify (more hits first, so the pool can pay).
    for (int hit = 0; hit < 5; ++hit)
        Generate(p, monk, 1, fists);
    double const pooled = Resources::Get(p, spirit);
    Resources::SpendUnits(p, spirit, int32_t(Resources::ToUnits(spirit, kick)));
    expect(Resources::Get(p, spirit) == pooled - kick, "Lashing Tail Kick costs its sheet value", Resources::Get(p, spirit),
           pooled - kick);

    // The pool stops at 250 and never goes negative.
    Player* full = fresh();
    for (int hit = 0; hit < 40; ++hit)
        Generate(full, monk, 1, reach);
    expect(Resources::Get(full, spirit) == 250, "capped at 250", Resources::Get(full, spirit), 250);
    Player* empty = fresh();
    Resources::SpendUnits(empty, spirit, 500);
    expect(Resources::Get(empty, spirit) == 0, "a spend cannot go below 0");

    // Who is not paid: another class (its primaries are paid elsewhere), a Monk not showing Spirit, nothing generated.
    for (uint32_t other : {barbarian, wizard, uint32_t(0)})
    {
        Player* q = fresh();
        expect(!Generate(q, other, 1, fists) && Resources::Units(q, spirit) == 0, "another class is not paid", other);
    }
    Player* shown = fresh();
    shown->display = POWER_RAGE;
    expect(!Generate(shown, monk, 1, fists) && Resources::Units(shown, spirit) == 0, "Spirit not shown, not paid");
    Player* zero = fresh();
    expect(!Generate(zero, monk, 1, 0) && !Generate(zero, monk, 1, -3) && !Generate(nullptr, monk, 1, fists),
           "zero, negative, no player");

    // Paragon: +1 Spirit per point, whole (paragon.csv resource_keys spirit).
    expect(Resources::ParagonMaximum(spirit, 50) == 50, "50 Paragon points, +50 Spirit",
           Resources::ParagonMaximum(spirit, 50));
    expect(Resources::ParagonMaximum(spirit, 7) == 7, "7 points, +7");
    expect(Resources::ParagonMaximum(Resources::ArcanePower, 7) == 3, "the Wizard's half point still pays per pair");

    // A source outside the class (the Templar's Inspire) scales what is generated of Spirit and of nothing else: a cost given back, a loss
    // and another resource pass unchanged, and a source that answers nothing sensible changes nothing.
    percentOver = inspire;
    Resources::GenerationSourceOf() = [](Player const*, Resources::Resource const& r)
    { return &r == &Resources::Spirit ? 1.0 + percentOver / 100.0 : 1.0; };
    double const factor = 1.0 + inspire / 100.0;
    Player* scaled = fresh();
    for (int hit = 0; hit < 5; ++hit)
        Generate(scaled, monk, 1, fists);
    expect(Resources::Get(scaled, spirit) > 5 * fists && std::fabs(Resources::Get(scaled, spirit) - 5 * fists * factor) < 1.0,
           "Inspire's percent more Spirit is generated, the part below a unit carried", Resources::Get(scaled, spirit), 5 * fists * factor);
    Player* back = fresh();
    expect(Generate(back, monk, 1, fists, false) && Resources::Get(back, spirit) == fists, "a cost given back is not scaled", Resources::Get(back, spirit), fists);
    Player* wiz = new Player();
    wiz->display = Resources::Slot(Resources::ArcanePower);
    wiz->SetMaxPower(Resources::Slot(Resources::ArcanePower), uint32_t(Resources::ToUnits(Resources::ArcanePower, 100)));
    Resources::Energize(wiz, Resources::ArcanePower, 1, 10);
    expect(Resources::Get(wiz, Resources::ArcanePower) == 10, "another resource is not scaled", Resources::Get(wiz, Resources::ArcanePower), 10);
    expect(Resources::Generated(scaled, spirit, -3) == -3 && Resources::Generated(scaled, spirit, 0) == 0 &&
               Resources::Generated(nullptr, spirit, 7) == 7,
           "a loss, nothing and no player pass unchanged");
    expect(std::fabs(Resources::Generated(scaled, spirit, 10) - 10 * factor) < 1e-9, "a gain is scaled by the factor", Resources::Generated(scaled, spirit, 10), 10 * factor);
    percentOver = -100;
    expect(Resources::Generated(scaled, spirit, 10) == 10, "a source that answers nothing is no scale");
    Resources::GenerationSourceOf() = nullptr;
    expect(Resources::Generated(scaled, spirit, 10) == 10, "no source, no scale");

    std::printf("cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
