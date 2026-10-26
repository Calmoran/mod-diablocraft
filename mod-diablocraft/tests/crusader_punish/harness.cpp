// The real dc_crusader_punish.h. The rune names and the Fury number come from argv (read from the Crusader's sheets by
// test_crusader_punish.py); nothing is typed in here.
// Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/crusader/dc_crusader_punish.h"

#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Crusader::Punish;

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
    // argv: the Fury number, then the five runes in the sheet's order (A to E)
    if (argc < 7)
        return 2;
    double const fury = std::atof(argv[1]);
    std::string const retaliate = argv[2], celerity = argv[3], rebirth = argv[4], roar = argv[5], furyRune = argv[6];

    expect(AnswerOf(retaliate) == Answer::Retaliate, "Retaliate answers a block with a hit");
    expect(AnswerOf(celerity) == Answer::Celerity, "Celerity answers with attack speed");
    expect(AnswerOf(rebirth) == Answer::Rebirth, "Rebirth answers with Life regeneration");
    expect(AnswerOf(roar) == Answer::Roar, "Roar answers with the explosion");
    expect(AnswerOf(furyRune) == Answer::Fury, "Fury answers with the critical chance");

    // The five answers are five different ones, and the base skill and a stranger give none.
    std::set<int> seen;
    for (auto const& rune : {retaliate, celerity, rebirth, roar, furyRune})
        seen.insert(int(AnswerOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Answer::None)), "each rune has an answer of its own", double(seen.size()), 5);
    expect(AnswerOf("") == Answer::None, "the base skill answers nothing");
    expect(AnswerOf("Bash") == Answer::None, "a rune of another skill answers nothing");

    // Fury: the bonus waits for the next attack and is nothing otherwise.
    expect(FuryCrit(true, fury) == fury, "an armed Fury gives its number", FuryCrit(true, fury), fury);
    expect(FuryCrit(false, fury) == 0, "an unarmed Fury gives nothing");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
