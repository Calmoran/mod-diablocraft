// The real dc_shaman_chain_lightning.h. The rune names and numbers come from argv (read from the sheets by
// test_shaman_chain_lightning.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing
// case and exits 1.
#include "classes/shaman/dc_shaman_chain_lightning.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

using namespace DC::Combat::Shaman::ChainLightning;

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
    // argv: the five runes A to E, the jumps of the skill and of Forked Lightning, the jump radius, Chain Frost's
    // percent per jump, Chain Heal's percent of Life, Thunderhead's enemies and refund, the bolt's damage percent, and
    // the runes whose record the loader would give no hit (comma-separated).
    if (argc < 15)
        return 2;
    std::string const forked = argv[1], lava = argv[2], frost = argv[3], heal = argv[4], head = argv[5];
    unsigned const jumps = unsigned(std::atoi(argv[6])), forkedJumps = unsigned(std::atoi(argv[7]));
    double const radius = std::atof(argv[8]), bonus = std::atof(argv[9]), healPct = std::atof(argv[10]),
                 needed = std::atof(argv[11]), gain = std::atof(argv[12]), base = std::atof(argv[13]);

    expect(RuneOf(forked) == Rune::ForkedLightning && RuneOf(lava) == Rune::ChainLava &&
               RuneOf(frost) == Rune::ChainFrost && RuneOf(heal) == Rune::ChainHeal &&
               RuneOf(head) == Rune::Thunderhead,
           "each rune name is its rune");
    expect(RuneOf("") == Rune::None && RuneOf("Chain Lightning") == Rune::None && RuneOf("Electrocute") == Rune::None,
           "and nothing else is");

    // Only Chain Lava states a damage that is not the bolt's hit.
    expect(HitIsSkills(Rune::ChainLava) && !HitIsSkills(Rune::None) && !HitIsSkills(Rune::ForkedLightning) &&
               !HitIsSkills(Rune::ChainFrost) && !HitIsSkills(Rune::ChainHeal) && !HitIsSkills(Rune::Thunderhead),
           "only Chain Lava leaves the bolt's own hit the skill's");

    // The walk: enemies on a line, the jump radius from the sheet.
    std::vector<double> const enemies = {0, 5, 3, 10, radius * 4};
    auto near = [&](double on)
    {
        std::vector<double> out;
        for (double candidate : enemies)
            if (std::fabs(candidate - on) <= radius)
                out.push_back(candidate);
        return out;
    };
    auto distance = [](double a, double b) { return std::fabs(a - b); };
    std::vector<double> const walk = Walk(0.0, jumps, near, distance);
    // From 0 the nearest unhit is 3, then 5, then 10; the enemy beyond the radius is never reached.
    expect(walk.size() == 4 && walk[0] == 0 && walk[1] == 3 && walk[2] == 5 && walk[3] == 10,
           "each jump goes to the nearest enemy not hit yet", double(walk.size()), 4);
    expect(Walk(0.0, 0, near, distance).size() == 1, "no jumps hits the first enemy only");
    expect(Walk(0.0, 2, near, distance).size() == 3, "and two jumps hit three enemies");
    expect(Walk(0.0, forkedJumps, near, distance).size() == 4,
           "and the jumps stop when no enemy is left within the radius");
    expect(forkedJumps > jumps, "Forked Lightning jumps more");
    expect(Walk(
               7.0, 3, [](double) { return std::vector<double>{}; }, distance)
                   .size() == 1,
           "an enemy on its own ends the walk");

    // Chain Frost.
    expect(JumpPct(base, bonus, 0) == base &&
               std::fabs(JumpPct(base, bonus, 2) - base * (1 + bonus / 100) * (1 + bonus / 100)) < 1e-9 &&
               JumpPct(base, bonus, 1) > base && JumpPct(base, 0, 3) == base && JumpPct(base, -5, 3) == base,
           "each jump deals its percent more than the one before");

    // Chain Heal and Thunderhead.
    expect(std::fabs(HealAmount(1000, healPct) - 1000 * healPct / 100) < 1e-9 && HealAmount(0, healPct) == 0 &&
               HealAmount(1000, 0) == 0,
           "Chain Heal heals its percent of the maximum Life");
    unsigned const n = unsigned(needed);
    expect(Refund(n, needed, gain) == gain && Refund(n + 3, needed, gain) == gain && Refund(n - 1, needed, gain) == 0 &&
               Refund(n, 0, gain) == 0 && Refund(n, needed, 0) == 0,
           "Thunderhead refunds for its crowd and more, nothing for fewer");

    // Every record the loader would give no hit of its own (it states a duration) is left the skill's by the rule
    // above.
    std::string waiting = argv[14];
    int claimed = 0;
    for (std::size_t from = 0; from <= waiting.size();)
    {
        std::size_t to = waiting.find(',', from);
        if (to == std::string::npos)
            to = waiting.size();
        std::string const name = waiting.substr(from, to - from);
        expect(HitIsSkills(RuneOf(name)), name.c_str());
        ++claimed;
        from = to + 1;
    }
    expect(claimed >= 1, "at least one record waits");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
