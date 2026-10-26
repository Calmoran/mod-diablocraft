"""The source-text guards of ahavarion: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_ahavarion.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
import generate_legendary_powers as generator
from test_item_power_ahavarion import GENERATED, OWNER, REPO, SRC, core_creature_types, mutate, read_csv# noqa: E402


def definition(marker, source):
    assert source.count(marker) == 1, "%r is not there exactly once" % marker
    start = source.index(marker)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def problems(powers, pylons, pylons_h, sheet_names):
    """What the source-text guards find wrong in the server files (the C++ is compile-checked, not run, here)."""
    out = []
    fire = definition("void Fire(Player* player, char const* event, std::string const& skill, double scale, Unit* target, unsigned enemies,", powers)
    loop = fire.index("for (ItemPower::Fired const& one : fired)")
    lock = fire.index("std::lock_guard<std::mutex> lock(mutex);")
    at = fire.find('one.stat == "random_shrine"')
    if at < 0:
        out.append("no executor for random_shrine")
    else:
        if at < loop:
            out.append("random_shrine is done before the lock is released")
        if "lock_guard" in fire[loop:]:
            out.append("the executors take the item powers' lock")
        executor = fire[at:fire.index("\n                else", at + 1) if "\n                else" in fire[at + 1:] else len(fire)]
        for need, why in (('DC::Tunables::Has("combat", "ahavarion_chance_pct") ? DC::Tunables::Get("combat", "ahavarion_chance_pct") : 0.0', "the chance is the tunable and a blank one reads 0"),
                          ("Proc::Rolls(scale, chance,", "the event's coefficient scales the chance"),
                          ("roll_chance_f(static_cast<float>(pct))", "the core's roll"),
                          ("for (unsigned shrine = 0; shrine < static_cast<unsigned>(one.value); ++shrine)", "the row's number of shrines"),
                          ("Pylons::GiveRandomShrine(player, rand_norm());", "a random shrine for the player")):
            if need not in executor:
                out.append("the random_shrine executor lacks %s (%s)" % (need, why))
    if "std::string const targetType = enemy ? ItemPower::CreatureTypeName(enemy->GetCreatureType()) : std::string();" not in fire or \
            fire.find("CreatureTypeName(") > lock:
        out.append("the event's creature type is not read from the enemy before the lock")
    if "situation.targetType = targetType;" not in fire or fire.index("situation.targetType = targetType;") < lock:
        out.append("the creature type does not reach the situation inside the lock")
    for event in ('Fire(killer, "kill", "", 1.0, killed);', 'Fire(killer, "kill_elite", "", 1.0, killed);'):
        if event not in powers:
            out.append("a kill does not hand the killed creature to the event: %s" % event)
    for number, name in core_creature_types().items():
        if "CREATURE_TYPE_%s == %d" % (name.upper(), number) not in powers:
            out.append("the enum assertion lacks CREATURE_TYPE_%s == %d" % (name.upper(), number))
    if "bool GiveRandomShrine(Player* target, double roll);" not in pylons_h:
        out.append("dc_pylons.h does not declare GiveRandomShrine")
    shrine = definition("bool GiveRandomShrine(Player* target, double roll)", pylons)
    if "return Give(target, RandomShrine(roll));" not in shrine:
        out.append("GiveRandomShrine does not give a RandomShrine through Give (the shrine's own seconds and checks)")
    if '#include "dc_pylons.h"' not in powers or '#include "dc_proc_math.h"' not in powers:
        out.append("dc_item_powers.cpp lacks the pylons or proc header")
    if "ahavarion_chance_pct" not in sheet_names:
        out.append("the tunable ahavarion_chance_pct is not on data/tunables/combat.csv")
    return out


def source(name):
    path = SRC / "combat" / name
    return path.read_text(encoding="utf-8") if path.is_file() else ""


class Hooks(unittest.TestCase):
    powers = item_powers_source.text()
    pylons = source("dc_pylons.cpp")
    pylons_h = source("dc_pylons.h")
    names = {r["name"] for r in read_csv("data/tunables/combat.csv")}

    def args(self, **changed):
        base = dict(powers=self.powers, pylons=self.pylons, pylons_h=self.pylons_h, sheet_names=self.names)
        base.update(changed)
        return base

    def test_the_guards_hold_on_the_source(self):
        self.assertEqual([], problems(**self.args()))

    def test_one_caller(self):
        self.assertEqual(["dc_item_powers_effects.cpp"], [p.name for p in SRC.rglob("*.cpp") if "Pylons::GiveRandomShrine(" in p.read_text(encoding="utf-8")])

    def test_the_new_code_names_no_class(self):
        # N-CTF and N-PYLON are shared pieces (R1): neither the creature type read nor the shrine call names a class
        fire = definition("void Fire(Player* player, char const* event, std::string const& skill, double scale, Unit* target, unsigned enemies,", self.powers)
        for text in (fire[fire.index("random_shrine"):fire.index("slow_pct")], fire[fire.index("// N-CTF"):fire.index("ItemPower::Situation seen")]):
            self.assertNotRegex(text.lower(), r"barbarian|wizard|monk|demon hunter|witch doctor|necromancer|crusader")

    def test_the_stat_and_condition_are_in_the_generator_and_the_contract(self):
        self.assertIn("random_shrine", generator.EFFECT_STATS)
        self.assertIn("target_creature_type", generator.CONDITIONS)
        text = (REPO / "docs/contracts/legendary-powers.md").read_text(encoding="utf-8")
        self.assertRegex(text, r"\| `random_shrine` \(")
        self.assertRegex(text, r"\| `target_creature_type`")
        self.assertIn("### Ahavarion, Spear of Lycander (`diablocraft-zqlje`", text)
        self.assertIn("| Ahavarion, Spear of Lycander `%s` |" % OWNER, text)
        self.assertIn(GENERATED.name, text)

    def test_the_server_mutants_fail_the_guards(self):
        p, y, h = self.powers, self.pylons, self.pylons_h
        mutants = {
            "no_executor": dict(powers=mutate(p, 'one.stat == "random_shrine"', 'one.stat == "random_shrines"')),
            "the_chance_a_literal": dict(powers=mutate(p, 'DC::Tunables::Has("combat", "ahavarion_chance_pct") ? DC::Tunables::Get("combat", "ahavarion_chance_pct") : 0.0', "100.0")),
            "a_blank_chance_reads_100": dict(powers=mutate(p, '"ahavarion_chance_pct") : 0.0', '"ahavarion_chance_pct") : 100.0')),
            "the_chance_not_on_the_sheet": dict(sheet_names=self.names - {"ahavarion_chance_pct"}),
            "the_coefficient_dropped": dict(powers=mutate(p, "Proc::Rolls(scale, chance,", "Proc::Rolls(1.0, chance,")),
            "one_shrine_whatever_the_row": dict(powers=mutate(p, "shrine < static_cast<unsigned>(one.value)", "shrine < 1u")),
            "a_fixed_shrine": dict(powers=mutate(p, "Pylons::GiveRandomShrine(player, rand_norm());", "Pylons::GiveRandomShrine(player, 0.0);")),
            "the_kill_hands_over_no_enemy": dict(powers=mutate(p, 'Fire(killer, "kill", "", 1.0, killed);', 'Fire(killer, "kill", "", 1.0);')),
            "the_elite_kill_hands_over_no_enemy": dict(powers=mutate(p, 'Fire(killer, "kill_elite", "", 1.0, killed);', 'Fire(killer, "kill_elite", "", 1.0);')),
            "the_type_never_reaches_the_situation": dict(powers=mutate(p, "situation.targetType = targetType;", "")),
            "the_type_read_inside_the_lock": dict(powers=mutate(mutate(p, "std::string const targetType = enemy ? ItemPower::CreatureTypeName(enemy->GetCreatureType()) : std::string();", ""),
                                                                "situation.targetType = targetType;", "situation.targetType = enemy ? ItemPower::CreatureTypeName(enemy->GetCreatureType()) : std::string();")),
            "the_enum_assertion_off_by_one": dict(powers=mutate(p, "CREATURE_TYPE_DEMON == 3", "CREATURE_TYPE_DEMON == 4")),
            "the_shrine_not_given_through_give": dict(pylons=mutate(y, "return Give(target, RandomShrine(roll));", "return false;")),
            "a_pylon_given": dict(pylons=mutate(y, "return Give(target, RandomShrine(roll));", "return Give(target, Kind::Power);")),
            "not_declared": dict(pylons_h=mutate(h, "bool GiveRandomShrine(Player* target, double roll);", "")),
        }
        for name, changed in mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual([], problems(**self.args(**changed)), name + " survived")


if __name__ == "__main__":
    unittest.main()
