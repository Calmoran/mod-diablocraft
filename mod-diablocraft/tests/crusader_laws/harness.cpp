// The real dc_crusader_laws.h and dc_crusader_laws_of_valor.h. The rune names and numbers come from argv (read from the
// sheets by test_crusader_laws_of_valor.py); nothing else is typed in here. Prints "cases=N" and exits 0, or names the
// first failing case and exits 1.
#include "classes/crusader/dc_crusader_laws.h"
#include "classes/crusader/dc_crusader_laws_of_valor.h"

#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Crusader;

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
    // argv: passive speed, active speed, window seconds, per-kill seconds, max extra seconds, Frozen in Terror's chance, then
    // the five runes A to E
    if (argc < 12)
        return 2;
    double const passive = std::atof(argv[1]), active = std::atof(argv[2]), window = std::atof(argv[3]),
                 perKill = std::atof(argv[4]), maxExtra = std::atof(argv[5]), chance = std::atof(argv[6]);
    std::string const runes[5] = {argv[7], argv[8], argv[9], argv[10], argv[11]};
    std::uint64_t const windowMs = std::uint64_t(window * 1000), perKillMs = std::uint64_t(perKill * 1000),
                        maxMs = std::uint64_t(maxExtra * 1000);

    // The rune names.
    using LawsOfValor::Rune;
    expect(LawsOfValor::RuneOf(runes[0]) == Rune::Invincible && LawsOfValor::RuneOf(runes[1]) == Rune::FrozenInTerror &&
               LawsOfValor::RuneOf(runes[2]) == Rune::Critical && LawsOfValor::RuneOf(runes[3]) == Rune::UnstoppableForce &&
               LawsOfValor::RuneOf(runes[4]) == Rune::AnsweredPrayer,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : runes)
        seen.insert(int(LawsOfValor::RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(LawsOfValor::RuneOf("") == Rune::None && LawsOfValor::RuneOf("Rust") == Rune::None, "the base skill and a stranger are no rune");

    // Frozen in Terror's roll: under the chance stuns, at or over does not.
    expect(LawsOfValor::Stuns(chance - 0.01, chance) && !LawsOfValor::Stuns(chance, chance), "a roll under the chance stuns",
           chance, 0);
    expect(!LawsOfValor::Stuns(0, 0), "no chance never stuns");

    // The numbers a holder wears: the active's while the window is open, the passive's otherwise, never both.
    expect(Laws::Number(false, passive, active) == passive, "the passive form wears the passive number");
    expect(Laws::Number(true, passive, active) == active, "the empowered form wears the active number", Laws::Number(true, passive, active), active);
    expect(active > passive, "the active is the stronger", active, passive);

    // One Law at a time. Nothing cast yet: every slotted Law is in force.
    std::uint64_t const a = 1, b = 2, valor = 10, justice = 11, now = 1000;
    Laws::Forget(a);
    Laws::Forget(b);
    expect(Laws::On(a, valor) && Laws::On(a, justice), "before any cast every Law is on");
    expect(!Laws::Boosted(a, valor, now), "before any cast no window is open");
    Laws::Cast(a, valor, now, windowMs);
    expect(Laws::On(a, valor) && !Laws::On(a, justice), "the Law cast is the only one on");
    expect(Laws::Boosted(a, valor, now) && Laws::Boosted(a, valor, now + windowMs - 1), "the window is open for its length");
    expect(!Laws::Boosted(a, valor, now + windowMs), "the window is closed at its end", double(now + windowMs), 0);
    expect(!Laws::Boosted(a, justice, now), "another Law has no window");
    expect(Laws::On(b, valor) && Laws::On(b, justice), "another Crusader's Laws are not touched");
    Laws::Cast(a, justice, now + 10, windowMs);
    expect(!Laws::On(a, valor) && Laws::On(a, justice) && !Laws::Boosted(a, valor, now + 11), "casting another Law ends the first");
    Laws::Forget(a);
    expect(Laws::On(a, valor) && Laws::On(a, justice), "a Crusader who left starts with nothing cast");

    // Answered Prayer: a kill adds its seconds to the open window, the whole addition capped.
    Laws::Cast(a, valor, now, windowMs);
    expect(Laws::BoostEnd(a, valor) == now + windowMs, "the window ends where it was cast to end");
    expect(Laws::Extend(a, valor, now + 1, perKillMs, maxMs) == perKillMs, "a kill adds its second");
    expect(Laws::BoostEnd(a, valor) == now + windowMs + perKillMs, "and the window ends later by it");
    std::uint64_t added = perKillMs;
    for (int kill = 0; kill < 40; ++kill)
        added += Laws::Extend(a, valor, now + 2, perKillMs, maxMs);
    expect(added == maxMs, "kills add the seconds up to the maximum and no more", double(added), double(maxMs));
    expect(Laws::Extend(a, valor, now + 3, perKillMs, maxMs) == 0, "a window at its cap takes no more");
    expect(Laws::BoostEnd(a, valor) == now + windowMs + maxMs, "the window ends the cap later");
    expect(Laws::Extend(a, justice, now + 1, perKillMs, maxMs) == 0, "another Law's kill adds nothing to this window");
    expect(Laws::Extend(b, valor, now + 1, perKillMs, maxMs) == 0, "a Crusader with nothing cast gets no extension");
    Laws::Cast(a, valor, now + 5000, windowMs);
    expect(Laws::Extend(a, valor, now + 5001, perKillMs, maxMs) == perKillMs, "a new cast starts the count again");
    Laws::Cast(a, valor, now + 9000, windowMs);
    expect(Laws::Extend(a, valor, now + 9000 + windowMs, perKillMs, maxMs) == 0, "a fresh window that has closed takes no kill");
    Laws::Forget(a);

    // The id a Law puts on a sheet: one per Crusader and per Law.
    expect(Laws::Key(a, valor) != Laws::Key(b, valor), "two Crusaders' Laws are two contributions");
    expect(Laws::Key(a, valor) != Laws::Key(a, justice), "two Laws of one Crusader are two contributions");

    // How long one pulse's numbers last.
    expect(Laws::HoldMs(1.0, 0.25) == 1250, "a pulse and a quarter", double(Laws::HoldMs(1.0, 0.25)), 1250);
    expect(Laws::HoldMs(-1.0, 0.25) == 250 && Laws::HoldMs(1.0, -1.0) == 1000, "no negative time");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
