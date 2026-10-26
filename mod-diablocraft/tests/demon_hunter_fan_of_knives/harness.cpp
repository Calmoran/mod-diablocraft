// The real dc_demon_hunter_fan_of_knives.h. The rune names and numbers come from argv (read from the sheets and the
// tunables by test_demon_hunter_fan_of_knives.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the
// first failing case and exits 1.
#include "classes/demon_hunter/dc_demon_hunter_fan_of_knives.h"

#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>
#include <vector>

using namespace DC::Combat::DemonHunter::FanOfKnives;

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
    // argv: the five runes A to E, the fan's radius, the knives' search radius, the number of additional enemies.
    if (argc < 9)
        return 2;
    std::string const expert = argv[1], assassin = argv[2], daggers = argv[3], pinpoint = argv[4], armor = argv[5];
    double const fan = std::atof(argv[6]), search = std::atof(argv[7]);
    unsigned const most = unsigned(std::atoi(argv[8]));

    expect(RuneOf(expert) == Rune::KnivesExpert && RuneOf(assassin) == Rune::AssassinsKnives &&
               RuneOf(daggers) == Rune::FanOfDaggers && RuneOf(pinpoint) == Rune::PinpointAccuracy &&
               RuneOf(armor) == Rune::BladedArmor,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {expert, assassin, daggers, pinpoint, armor})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // Assassin's Knives: the enemies the fan did not reach, within the search radius, nearest first, no more than the
    // rune's number. Thirteen enemies, six of them in the band, spread from the middle to well past the search radius, listed out of order.
    std::vector<double> distances;
    for (double step : {5.0, 95.0, fan + 30, fan + 5, fan, fan - 0.1, search, search + 0.1, fan + 0.1, search + 20, 1.0, fan + 10, fan + 15})
        distances.push_back(step);
    auto const picked = ExtraTargets(distances, fan, search, most);
    expect(picked.size() == std::min<std::size_t>(most, 6),
           "no more than the rune's number, and only those in the band", double(picked.size()),
           double(std::min<std::size_t>(most, 6)));
    for (std::size_t i = 0; i < picked.size(); ++i)
    {
        expect(distances[picked[i]] > fan, "the fan's own enemies are not thrown at", distances[picked[i]], fan);
        expect(distances[picked[i]] <= search, "nothing beyond the search radius", distances[picked[i]], search);
        if (i)
            expect(distances[picked[i - 1]] <= distances[picked[i]], "nearest first", distances[picked[i - 1]],
                   distances[picked[i]]);
    }
    expect(!picked.empty() && distances[picked.front()] == fan + 0.1, "the nearest one the fan missed comes first",
           picked.empty() ? -1 : distances[picked.front()], fan + 0.1);
    // With room for them all, the same six come back; with none, nothing does.
    expect(ExtraTargets(distances, fan, search, 50).size() == 6, "all of them with room",
           double(ExtraTargets(distances, fan, search, 50).size()), 6);
    expect(ExtraTargets(distances, fan, search, 0).empty(), "none for none");
    expect(ExtraTargets({}, fan, search, most).empty() && ExtraTargets({fan - 1, 3.0}, fan, search, most).empty(),
           "no enemy, or only the fan's, no knife");
    // A tie keeps the order the enemies came in.
    auto const tied = ExtraTargets({fan + 3, fan + 3, fan + 3}, fan, search, 2);
    expect(tied.size() == 2 && tied[0] == 0 && tied[1] == 1, "a tie keeps the order given");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
