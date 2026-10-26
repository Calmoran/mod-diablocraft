// The real dc_shaman_attunement.h, no core. Every number comes from argv (test_shaman_maelstrom.py reads combat.csv):
// the four bonuses in the order Fire damage, Cold regeneration, Physical armor, Lightning attack speed. argv[5..] are
// the skills the sheets give a Secondary or Primal element ("category|skill|rune" each), argv after "--" the ones they
// do not. Prints "cases=N failures=M" and exits 0, or names each failing case and exits 1.
#include "classes/shaman/dc_shaman_attunement.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

using namespace DC::Combat::Shaman::Attunement;

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

static void Split(std::string const& line, std::string& category, std::string& skill, std::string& rune)
{
    auto first = line.find('|');
    auto second = line.find('|', first + 1);
    category = line.substr(0, first);
    skill = line.substr(first + 1, second - first - 1);
    rune = line.substr(second + 1);
}

int main(int argc, char** argv)
{
    if (argc < 5)
        return 2;
    Table const table{std::atof(argv[1]), std::atof(argv[2]), std::atof(argv[3]), std::atof(argv[4])};

    // The Shaman starts in Lightning.
    expect(Start == Element::Lightning, "the Shaman starts in Lightning");

    // Each element gives its own bonus and no other; a passive that triples it triples that one.
    Bonus const fire = BonusOf(Element::Fire, table), cold = BonusOf(Element::Cold, table),
                earth = BonusOf(Element::Physical, table), air = BonusOf(Element::Lightning, table);
    expect(fire.damagePct == table.fireDamagePct && fire.lifeRegenPct == 0 && fire.armorPct == 0 &&
               fire.attackSpeedPct == 0,
           "Fire: damage dealt only", fire.damagePct, table.fireDamagePct);
    expect(cold.lifeRegenPct == table.coldLifeRegenPct && cold.damagePct == 0 && cold.armorPct == 0 &&
               cold.attackSpeedPct == 0,
           "Cold: Life regeneration only", cold.lifeRegenPct, table.coldLifeRegenPct);
    expect(earth.armorPct == table.physicalArmorPct && earth.damagePct == 0 && earth.lifeRegenPct == 0 &&
               earth.attackSpeedPct == 0,
           "Physical: Armor only", earth.armorPct, table.physicalArmorPct);
    expect(air.attackSpeedPct == table.lightningAttackSpeedPct && air.damagePct == 0 && air.lifeRegenPct == 0 &&
               air.armorPct == 0,
           "Lightning: attack speed only", air.attackSpeedPct, table.lightningAttackSpeedPct);
    expect(BonusOf(Element::Fire, table, 3).damagePct == 3 * table.fireDamagePct, "tripled Fire",
           BonusOf(Element::Fire, table, 3).damagePct, 3 * table.fireDamagePct);
    expect(BonusOf(Element::Cold, table, 3).lifeRegenPct == 3 * table.coldLifeRegenPct, "tripled Cold");
    expect(BonusOf(Element::Physical, table, 3).armorPct == 3 * table.physicalArmorPct, "tripled Physical");
    expect(BonusOf(Element::Lightning, table, 3).attackSpeedPct == 3 * table.lightningAttackSpeedPct,
           "tripled Lightning");

    // Only a Secondary or Primal skill moves it, and it becomes the element cast.
    expect(After(Element::Lightning, true, Element::Fire) == Element::Fire, "a casting skill moves it");
    expect(After(Element::Fire, false, Element::Cold) == Element::Fire, "a skill that keeps it leaves it");
    for (char const* category : {"Primary", "Defensive", "Totems", "Ancestral"})
        expect(!Sets(category, "Lava Burst", ""), category);
    expect(Sets("Secondary", "Lava Burst", ""), "a Secondary sets it");
    expect(Sets("Secondary", "Chain Lightning", "Chain Frost"), "a Secondary's rune sets it");
    expect(Sets("Primal", "Fire Elemental", "Water Elemental"), "a Primal skill's rune sets it");

    // The sheets' own: every Secondary and Primal skill or rune they give an element sets it, every one they do not
    // keeps it (the lines come from the research sheets, read by the test).
    bool afterDash = false;
    unsigned sets = 0, keeps = 0;
    for (int i = 5; i < argc; ++i)
    {
        if (std::strcmp(argv[i], "--") == 0)
        {
            afterDash = true;
            continue;
        }
        std::string category, skill, rune;
        Split(argv[i], category, skill, rune);
        bool const does = Sets(category, skill, rune);
        (afterDash ? keeps : sets) += 1;
        if (does == afterDash)
            std::printf("FAIL %s | %s | %s %s\n", category.c_str(), skill.c_str(), rune.c_str(),
                        afterDash ? "carries no element and still sets the Attunement"
                                  : "carries an element and does not set it");
        expect(does != afterDash, "the sheet's element decides", does, afterDash);
    }
    expect(sets > 20 && keeps > 5, "the sheets gave both kinds", sets, keeps);

    std::printf("cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
