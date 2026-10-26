// Compiles dc_family_ability.h (the production header) and drives it. Argument 1: a TSV of the generated
// dc_family_ability_ai rows (kind, trigger_code, built); argument 2: the generator's built kinds, space separated.
#include "dc_family_ability.h"

#include <cassert>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <set>
#include <sstream>

using namespace DC::Rifts::Family;

// EventMap.cpp asks Util.cpp for randtime on a ranged schedule; the brain never schedules one, so any value serves.
Milliseconds randtime(Milliseconds min, Milliseconds) { return min; }

static bool near(double a, double b, double e = 1e-4) { return std::fabs(a - b) < e; }

static Ability make(Kind kind, Trigger trigger, unsigned cooldownMs, float minYd, float maxYd)
{
    Ability a;
    a.kind = kind;
    a.trigger = trigger;
    a.cooldownMs = cooldownMs;
    a.minYd = minYd;
    a.maxYd = maxYd;
    return a;
}

int main(int argc, char** argv)
{
    assert(argc == 3);
    // --- the generated rows parse: every built row has a kind and a trigger the AI knows --------------------------
    std::set<std::string> built;
    {
        std::istringstream kinds(argv[2]);
        std::string k;
        while (kinds >> k)
            built.insert(k);
    }
    assert(built.size() == 14);
    for (auto const& k : built)
    {
        assert(ParseKind(k) != Kind::Held);
        assert(k == KindName(ParseKind(k)));            // the name the sheets use is the name the code reports
    }
    assert(ParseKind("shield_deflection") == Kind::Held && ParseKind("passive") == Kind::Held && ParseKind("") == Kind::Held);
    std::ifstream rows(argv[1]);
    std::string line;
    unsigned total = 0, runnable = 0;
    while (std::getline(rows, line))
    {
        std::istringstream cells(line);
        std::string kind, trigger, flag;
        std::getline(cells, kind, '\t');
        std::getline(cells, trigger, '\t');
        std::getline(cells, flag, '\t');
        ++total;
        if (flag == "1")
        {
            ++runnable;
            assert(ParseKind(kind) != Kind::Held);      // a built row names a kind the AI runs
            assert(ParseTrigger(trigger) != Trigger::None);
        }
    }
    assert(total == 123 && runnable == 91);
    assert(ParseTrigger("none") == Trigger::None && ParseTrigger("nonsense") == Trigger::None);
    for (char const* t : {"melee", "range", "gap", "proximity", "death", "combat", "hit"})
        assert(ParseTrigger(t) != Trigger::None);

    // --- numbers: the cell wins, then the ability's tunable, then the kind's default --------------------------------
    Layer cell, tuned, kind;
    kind.cooldownS = 6.0;
    kind.rangeMaxYd = 30.0;
    kind.areaYd = 5.0;
    tuned.cooldownS = 4.5;
    cell.rangeMaxYd = 25.0;
    Layer got = FirstOf(cell, tuned, kind);
    assert(*got.cooldownS == 4.5 && *got.rangeMaxYd == 25.0 && *got.areaYd == 5.0 && !got.windupS);
    cell.cooldownS = 1.0;
    assert(*FirstOf(cell, tuned, kind).cooldownS == 1.0);            // a published cell beats the designer's row (it has no row)
    assert(*FirstOf(Layer{}, Layer{}, kind).cooldownS == 6.0 && !FirstOf(Layer{}, Layer{}, Layer{}).cooldownS);

    // --- Resolve: units, the donor's cast time, the donor's reach ------------------------------------------------
    Donor bolt{9053, 3000, 0.0, 40.0};
    Layer n;
    n.cooldownS = 3.0;
    n.rangeMinYd = 8.0;
    n.rangeMaxYd = 60.0;
    n.windupS = std::nullopt;
    Ability a = Resolve(2, "Fireball", Kind::RangedBolt, Trigger::Range, bolt, 0, std::nullopt, n, 1.5);
    assert(a.cooldownMs == 3000 && a.windupMs == 3000);              // the row has no wind-up: the donor's cast time
    assert(near(a.minYd, 8.0) && near(a.maxYd, 40.0));               // asked 60 yd, the spell reaches 40
    assert(a.direct && near(a.damageMultiplier, 1.5) && a.count == 1);
    n.windupS = 1.5;
    assert(Resolve(1, "x", Kind::RangedBolt, Trigger::Range, bolt, 0, std::nullopt, n, 1).windupMs == 1500);   // the row's own wins
    Donor throwing{15607, 0, 5.0, 30.0};
    n.rangeMinYd = 0.0;
    a = Resolve(1, "Spear", Kind::RangedBolt, Trigger::Range, throwing, 0, std::nullopt, n, 1);
    assert(near(a.minYd, 5.0) && near(a.maxYd, 30.0));               // the spell cannot start inside 5 yd
    Layer area;
    area.rangeMaxYd = 5.0;
    area.areaYd = 5.0;
    area.arcDeg = 90;
    a = Resolve(1, "Slam", Kind::MeleeHeavySlam, Trigger::Melee, Donor{1464, 1500, 0, 5}, 0, std::nullopt, area, 1);
    assert(!a.direct && near(a.arcRad, 3.14159265 / 2) && a.windupMs == 1500 && near(a.maxYd, 5.0));
    Layer longer;
    longer.rangeMaxYd = 40.0;
    a = Resolve(1, "Cone", Kind::ConeBreath, Trigger::Range, Donor{8873, 1700, 0, 5}, 0, std::nullopt, longer, 1);
    assert(near(a.maxYd, 40.0));                                     // an area ability is not limited by the donor's own reach
    Layer counts;
    counts.count = 3;
    assert(Resolve(1, "v", Kind::ProjectileVolley, Trigger::Range, bolt, 0, std::nullopt, counts, 1).count == 3);
    assert(Resolve(1, "v", Kind::ProjectileVolley, Trigger::Range, bolt, 0, 4u, counts, 1).count == 4);          // the sheet's count wins
    assert(Resolve(1, "v", Kind::SummonMinions, Trigger::Combat, Donor{}, 950016, std::nullopt, Layer{}, 1).count == 1);
    assert(Resolve(1, "v", Kind::SummonMinions, Trigger::Combat, Donor{}, 950016, std::nullopt, Layer{}, 1).summonEntry == 950016);

    // --- Choose: sheet order, cooldowns, and what never starts from here ----------------------------------------------
    std::vector<Ability> list = {make(Kind::MeleeSwing, Trigger::Melee, 1000, 0, 5),
                                 make(Kind::SummonMinions, Trigger::Death, 0, 0, 0),
                                 make(Kind::Held, Trigger::Range, 0, 0, 40),
                                 make(Kind::MeleeHeavySlam, Trigger::Melee, 6000, 0, 5),
                                 make(Kind::RangedBolt, Trigger::Range, 3000, 8, 35),
                                 make(Kind::BuffRoar, Trigger::Hit, 0, 0, 0),
                                 make(Kind::SummonMinions, Trigger::None, 0, 0, 0)};
    EventMap clock;                                                  // the brain's own clock type: stock EventMap
    double distance = 3.0;
    auto can = [&](Ability const& x) { return InWindow(distance, x.minYd, x.maxYd); };
    assert(Choose(list, clock, can) == 3);                           // the swing, the death summon, the held one and none are skipped
    distance = 20.0;
    assert(Choose(list, clock, can) == 4);                           // out of slam reach, into bolt range
    StartCooldown(clock, 4, 5000);
    Tick(clock, 4999, [](std::uint32_t) { assert(false); });
    assert(Choose(list, clock, can) == -1);
    Tick(clock, 1, [](std::uint32_t) { assert(false); });            // a cooldown expiring is not an event for the brain
    assert(Choose(list, clock, can) == 4);                           // the cooldown gates it to the millisecond
    StartCooldown(clock, 4, 5000);
    distance = 3.0;
    assert(Choose(list, clock, can) == 3);                           // the slam is not behind the bolt's cooldown
    StartCooldown(clock, 3, 7000);
    assert(Choose(list, clock, can) == -1);
    StartCooldown(clock, 3, 0);                                      // a cooldown of 0 never holds an ability back
    assert(IsReady(clock, 3) && Choose(list, clock, can) == 3);
    assert(Choose(std::vector<Ability>{}, clock, can) == -1);
    std::vector<Ability> both = {make(Kind::RangedBolt, Trigger::Range, 0, 0, 40), make(Kind::ConeBreath, Trigger::Range, 0, 0, 40)};
    assert(Choose(both, EventMap(), [](Ability const&) { return true; }) == 0);   // the sheet's order is the priority
    int asked = 0;
    list[3].kind = Kind::Held;
    Choose(list, clock, [&](Ability const&) { ++asked; return false; });
    assert(asked == 0);                                              // the bolt is cooling and the rest never start from here
    clock.Reset();
    Choose(list, clock, [&](Ability const&) { ++asked; return false; });
    assert(asked == 1);                                              // only the bolt was ever considered
    // The scan and the phase deadline are the same clock: a due scan reaches the brain, a cooled ability does not.
    clock.Reset();
    clock.ScheduleEvent(EVENT_SCAN, Milliseconds(250));
    StartCooldown(clock, 0, 100);
    clock.RescheduleEvent(EVENT_PHASE, Milliseconds(400));
    std::vector<std::uint32_t> heard;
    auto hear = [&](std::uint32_t id) { heard.push_back(id); };
    Tick(clock, 249, hear);
    assert(heard.empty() && IsReady(clock, 0));
    Tick(clock, 1, hear);
    assert(heard == std::vector<std::uint32_t>{EVENT_SCAN});
    clock.CancelEvent(EVENT_PHASE);                                  // Finish cancels the phase deadline
    Tick(clock, 1000, hear);
    assert(heard.size() == 1);
    assert(FirstReadyAt(1000, 4000, 0.0) == 1000 && FirstReadyAt(1000, 4000, 0.5) == 3000 && FirstReadyAt(1000, 4000, 7.0) == 5000);
    assert(InWindow(5.0, 5.0, 30.0) && InWindow(30.0, 5.0, 30.0) && !InWindow(4.9, 5.0, 30.0) && !InWindow(30.1, 5.0, 30.0) && InWindow(99, 0, 0));

    // --- geometry ----------------------------------------------------------------------------------------------------
    double const pi = 3.14159265358979323846;
    assert(InCone(0, 0, 0, 4, 0, 5, pi / 2) && !InCone(0, 0, 0, 6, 0, 5, pi / 2));
    assert(InCone(0, 0, 0, 3, 2.9, 5, pi / 2) && !InCone(0, 0, 0, 3, 3.1, 5, pi / 2));       // 45 degrees is the edge of a 90 degree cone
    assert(!InCone(0, 0, 0, -3, 0, 5, pi / 2) && InCone(0, 0, 0, -3, 0, 5, 0));              // behind is out unless the arc is the circle
    assert(InCone(0, 0, pi, -3, 0.1, 5, pi / 2) && InCone(0, 0, 2 * pi, 3, 0.1, 5, pi / 2)); // the facing wraps around
    assert(InCone(10, 10, 3 * pi / 2, 10, 7, 5, pi / 3) && !InCone(10, 10, 3 * pi / 2, 10, 13, 5, pi / 3));
    for (unsigned i = 0; i < 4; ++i)
    {
        Spot s = RingSpot(10, 20, i, 4, 3, 0);
        assert(near(std::hypot(s.x - 10, s.y - 20), 3.0));
    }
    assert(near(RingSpot(0, 0, 0, 1, 2, 0).x, 2.0) && near(RingSpot(0, 0, 1, 2, 2, 0).x, -2.0));
    Spot end = ChargeEnd(0, 0, 10, 0, 3);
    assert(near(end.x, 7.0) && near(end.y, 0.0));
    end = ChargeEnd(0, 0, 0, -8, 2);
    assert(near(end.x, 0.0) && near(end.y, -6.0));
    end = ChargeEnd(1, 1, 2, 1, 3);
    assert(near(end.x, 1.0) && near(end.y, 1.0));                    // already inside the reach: stays put

    // --- damage and the picker ---------------------------------------------------------------------------------------
    assert(near(AbilityDamage(100, 1.5), 150) && AbilityDamage(100, -1) == 0 && AbilityDamage(0, 3) == 0);
    std::vector<Candidate> c = {{1, 12.0, false}, {2, 4.0, false}, {3, 30.0, true}};
    assert(PickIndex({}, Rule::Random, 0.5) == -1 && PickIndex({}, Rule::Victim, 0) == -1 && PickIndex({}, Rule::Nearest, 0) == -1);
    assert(PickIndex(c, Rule::Victim, 0) == 2 && PickIndex(c, Rule::Nearest, 0) == 1);
    c[2].victim = false;
    assert(PickIndex(c, Rule::Victim, 0) == 1);                      // the victim is out of the window: the nearest
    assert(PickIndex(c, Rule::Random, 0.0) == 0 && PickIndex(c, Rule::Random, 0.5) == 1 && PickIndex(c, Rule::Random, 0.99) == 2 &&
           PickIndex(c, Rule::Random, 1.0) == 2);                    // every candidate is reachable by a roll, none past the list
    std::set<int> seen;
    for (int i = 0; i < 30; ++i)
        seen.insert(PickIndex(c, Rule::Random, i / 30.0));
    assert(seen.size() == 3);

    // --- what a donor cast carries ----------------------------------------------------------------------------------------
    assert(CarryOf(false, true) == Carry::Keep && CarryOf(false, false) == Carry::Keep);
    assert(CarryOf(true, true) == Carry::OurNumber && CarryOf(true, false) == Carry::Zero);
    // What the wind-up cast carries, per kind, from Resolve's own `direct`: a bolt, a beam and a trap put the damage in the
    // cast; a volley (each projectile is cast on its own), a roar, a slam, a breath, a blast and the rest do not.
    Donor const spell{8873, 1700, 0, 30};
    for (Kind kind : {Kind::RangedBolt, Kind::ChanneledBeam, Kind::CrowdControlTrap})
        assert(WindupCarriesOurNumber(Resolve(1, "k", kind, Trigger::Range, spell, 0, std::nullopt, Layer{}, 1)));
    for (Kind kind : {Kind::ProjectileVolley, Kind::BuffRoar, Kind::MeleeHeavySlam, Kind::ConeBreath, Kind::GroundDetonation,
                      Kind::SuicideBomb, Kind::GroundHazardDot, Kind::ChargeRush, Kind::LeapSlam, Kind::SummonMinions})
        assert(!WindupCarriesOurNumber(Resolve(1, "k", kind, Trigger::Range, spell, 0, std::nullopt, Layer{}, 1)));
    std::puts("family ability harness: ok");
    return 0;
}
