"""The source-text guards of tal rashas elements: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_tal_rashas_elements.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path
import re

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
import generate_legendary_powers as generator
from test_item_power_tal_rashas_elements import REPO, SRC, TUNABLE, mutate, read_csv  # noqa: E402


def definition(marker, source):
    assert source.count(marker) == 1, "%r is not there exactly once" % marker
    start = source.index(marker)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def problems(powers, header, passives, common, tunables_sheet):
    """What the source-text guards find wrong, for the server files (the C++ is compile-checked, not run, here)."""
    out = []
    # the event: the hit's school mask names the element, only the set's four; only a hit with a school fires it
    names = definition("char const* ElementOfSchool(unsigned school)", powers)
    for mask, element in (("SPELL_SCHOOL_MASK_ARCANE", "arcane"), ("SPELL_SCHOOL_MASK_FROST", "cold"), ("SPELL_SCHOOL_MASK_FIRE", "fire"),
                          ("SPELL_SCHOOL_MASK_NATURE", "lightning")):
        if not re.search(r"case %s:\s*return \"%s\";" % (mask, element), names):
            out.append("ElementOfSchool: %s is not %s" % (mask, element))
    if "return nullptr;" not in names:
        out.append("ElementOfSchool names a fifth element")
    hit = definition("void HitElement(Player* player, Unit* target, unsigned school)", powers)
    if 'Fire(player, "hit_element", element, 1.0, target);' not in hit or "ElementOfSchool(school)" not in hit:
        out.append("HitElement does not fire hit_element with the school's element")
    if "ItemPowers::HitElement(p, target, school);" not in passives:
        out.append("Passives::Hit does not pass the school to ItemPowers::HitElement")
    if "void HitElement(Player*, Unit* target, unsigned school);" not in header:
        out.append("dc_item_powers.h does not declare HitElement")
    # the executors
    fire = definition("void Fire(Player* player, char const* event, std::string const& skill, double scale, Unit* target, unsigned enemies,", powers)
    for need in ('one.stat == "element_resist"', 'one.stat == "element_window"', 'one.stat == "element_meteor"', 'one.stat == "cooldown_cut_named_seconds"',
                 "Abilities::ReduceSkillCooldown(player, name.c_str(), one.value * 1000.0)"):
        if need not in fire:
            out.append("Fire lacks %s" % need)
    if "lock_guard" in fire[fire.index("for (ItemPower::Fired const& one : fired)"):]:
        out.append("the executors take the item powers' lock")
    resist = fire[fire.index('one.stat == "element_resist"'):fire.index('one.stat == "element_window"')]
    if "Stat::AllResistance, Bucket::Percent" not in resist or "&ItemPower::ElementState::resistUntil" not in resist or "one.row->stackSeconds" not in resist:
        out.append("element_resist is not a percent of every resistance for the row's seconds")
    buff = definition("void ElementBuff(Player* player, std::string const& element,", powers)
    for need in ("ItemPower::Touch(", "Source::Temporary", "Stats::RemoveContribution(", "Stats::Recompute(player)", "if (index >= 4 || !ms)"):
        if need not in buff + definition("void ElementSheet(Player* player, Stat stat,", powers):
            out.append("ElementBuff/ElementSheet lack %s" % need)
    if "ItemPower::Before(getMSTime(), (mine->second.elements.*ends)[element])" not in buff:
        out.append("ElementBuff takes the buff off without looking at the clock (an attack in between moved the end)")
    window = definition("void ElementWindowHit(Player* player, std::string const& element, ItemPower::Row const& row)", powers)
    for need in ("ItemPower::WindowAttack(", "row.stackSeconds, row.stackMax", '"element_extend_seconds"', '"element_extend_max_seconds"'):
        if need not in window:
            out.append("ElementWindowHit lacks %s" % need)
    meteor = definition("void ElementMeteor(Player* player, Unit* target, std::string const& element)", powers)
    for need, why in (("Wizard::MeteorOnBar(player)", "Meteor on the bar"), ("ItemPower::MeteorDrops(state, element, onBar)", "the rule"),
                      ("state.lastMeteor = element;", "the last Meteor is remembered"), ("Wizard::CastMeteor(player, target, ItemPower::MeteorRune(element))", "the rune of the element"),
                      ('DC::Tunables::Has("%s", "%s")' % TUNABLE, "the tunable by the sheet's name"), ('DC::Tunables::Get("%s", "%s")' % TUNABLE, "the tunable's number"),
                      ("&ItemPower::ElementState::immuneUntil, Stat::ElementReduction, Bucket::Flat, ElementImmuneId, 100.0", "immunity is 100 percent element reduction")):
        if need not in meteor:
            out.append("ElementMeteor lacks %s (%s)" % (need, why))
    for need, why in (('IsSkill(slot.spellId, "Meteor")', "Meteor on the bar, in the Wizard's file"),
                      ("player->CastSpell(target, ability.id, true)", "the Meteor is cast by code at the target")):
        if need not in powers:
            out.append("the Wizard's Meteor seam lacks %s (%s)" % (need, why))
    if "MeteorDrops" in meteor and "CastMeteor" in meteor and meteor.index("MeteorDrops") > meteor.index("CastMeteor"):
        out.append("the Meteor is cast before the rule is asked")
    if "elementWindow = ItemPower::WindowOn(mine->second.elements, situation.now);" not in powers:
        out.append("the situation does not carry the window")
    if tunables_sheet != 1:
        out.append("the tunable %s.%s is on the sheet %d times" % (TUNABLE + (tunables_sheet,)))
    # the sheet: a percent of every resistance
    if not re.search(r"stat == Stat::AllResistance\s*\|\|", definition("bool PercentStat(Stat stat)", common)):
        out.append("PercentStat does not include AllResistance")
    if "sheet.resistance[element] *= 1 + percent[Index(Stat::AllResistance)] / 100;" not in common:
        out.append("Calculate does not scale every resistance by the AllResistance percent")
    return out


class Hooks(unittest.TestCase):
    powers = item_powers_source.CPP.read_text(encoding="utf-8") + "\n" + (SRC / "classes/wizard/dc_wizard_meteor.cpp").read_text(encoding="utf-8")
    header = (SRC / "combat/dc_item_powers.h").read_text(encoding="utf-8")
    passives = (SRC / "combat/dc_passives.cpp").read_text(encoding="utf-8")
    common = (SRC / "common/dc_common.cpp").read_text(encoding="utf-8")

    def sheet(self):
        return len([r for r in read_csv("data/tunables/wizard.csv") if r["name"] == TUNABLE[1]])

    def test_the_guards_hold_on_the_source(self):
        self.assertEqual([], problems(self.powers, self.header, self.passives, self.common, self.sheet()))

    def test_the_element_hit_has_one_caller(self):
        callers = [p.name for p in SRC.rglob("*.cpp") if "ItemPowers::HitElement(" in p.read_text(encoding="utf-8")]
        self.assertEqual(["dc_passives.cpp"], callers)

    def test_the_names_are_in_the_generator_and_the_contract(self):
        self.assertIn("hit_element", generator.EVENTS)
        for effect in ("element_resist", "element_window", "element_meteor", "cooldown_cut_named_seconds"):
            self.assertIn(effect, generator.EFFECT_STATS)
        self.assertIn("element_window", generator.CONDITIONS)
        text = (REPO / "docs/contracts/legendary-powers.md").read_text(encoding="utf-8")
        for name in ("hit_element", "element_resist", "element_window", "element_meteor", "cooldown_cut_named_seconds", "element_window"):
            self.assertRegex(text, r"\| `%s`" % name)
        self.assertIn("Tal Rasha's Elements", text)

    def test_the_server_mutants_fail_the_guards(self):
        p, h, ps, c = self.powers, self.header, self.passives, self.common
        sheet = self.sheet()
        mutants = {
            "comet_is_not_cold": (mutate(p, "case SPELL_SCHOOL_MASK_FROST:\n                    return \"cold\";", "case SPELL_SCHOOL_MASK_FROST:\n                    return \"fire\";"), h, ps, c, sheet),
            "physical_is_an_element": (mutate(p, "                default:\n                    return nullptr;", "                default:\n                    return \"fire\";"), h, ps, c, sheet),
            "hit_does_not_fire_the_element": (mutate(p, 'Fire(player, "hit_element", element, 1.0, target);', 'Fire(player, "hit", element, 1.0, target);'), h, ps, c, sheet),
            "the_school_is_not_passed": (p, h, mutate(ps, "ItemPowers::HitElement(p, target, school);", "ItemPowers::HitElement(p, target, 0);"), c, sheet),
            "the_cut_is_not_executed": (mutate(p, 'else if (one.stat == "cooldown_cut_named_seconds")', 'else if (one.stat == "cooldown_cut_named")'), h, ps, c, sheet),
            "the_cut_is_in_the_wrong_unit": (mutate(p, "one.value * 1000.0);\n                }\n                else if ((one.stat == \"resource_by_distance\"", "one.value);\n                }\n                else if ((one.stat == \"resource_by_distance\""), h, ps, c, sheet),
            "resist_is_flat": (mutate(p, "Stat::AllResistance, Bucket::Percent, ElementResistId", "Stat::AllResistance, Bucket::Flat, ElementResistId"), h, ps, c, sheet),
            "resist_has_its_own_seconds": (mutate(p, "static_cast<std::uint32_t>(one.row->stackSeconds * 1000.0));\n                else if (one.stat == \"element_window\"", "8000);\n                else if (one.stat == \"element_window\""), h, ps, c, sheet),
            "the_buff_never_ends": (mutate(p, "Stats::RemoveContribution(guid, Source::Temporary, stat, id);", ""), h, ps, c, sheet),
            "the_buff_ends_early": (mutate(p, "ItemPower::Before(getMSTime(), (mine->second.elements.*ends)[element])", "false"), h, ps, c, sheet),
            "the_window_extension_is_a_literal": (mutate(p, 'OwnerNumber(Data().rows, row.owner, "player", "element_extend_seconds")', "2.0"), h, ps, c, sheet),
            "the_meteor_ignores_the_rule": (mutate(p, "ItemPower::MeteorDrops(state, element, onBar)", "true"), h, ps, c, sheet),
            "the_meteor_is_forgotten": (mutate(p, "state.lastMeteor = element;", ""), h, ps, c, sheet),
            "the_meteor_is_the_base_rune": (mutate(p, "ItemPower::MeteorRune(element)", 'std::string("")'), h, ps, c, sheet),
            "the_meteor_is_not_cast": (mutate(p, "player->CastSpell(target, ability.id, true)", "(void) ability"), h, ps, c, sheet),
            "the_immunity_is_a_literal": (mutate(p, 'DC::Tunables::Get("wizard", "tal_rashas_elements_immunity_seconds")', "3.0"), h, ps, c, sheet),
            "the_immunity_is_half": (mutate(p, "ElementImmuneId, 100.0", "ElementImmuneId, 50.0"), h, ps, c, sheet),
            "the_tunable_is_not_on_the_sheet": (p, h, ps, c, 0),
            "all_resistance_is_not_a_percent_stat": (p, h, ps, mutate(c, "        stat == Stat::AllResistance ||\n", ""), sheet),
            "the_percent_is_not_applied": (p, h, ps, mutate(c, "        sheet.resistance[element] *= 1 + percent[Index(Stat::AllResistance)] / 100;\n", ""), sheet),
        }
        for name, args in mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual([], problems(*args), name + " survived")


if __name__ == "__main__":
    unittest.main()
