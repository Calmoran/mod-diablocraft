"""The source-text guards of storm crow: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_storm_crow.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path
import re

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
import generate_legendary_powers as generator
from test_item_power_storm_crow import GENERATED, OWNER, REPO, SRC, TUNABLE, mutate, read_csv, source# noqa: E402


def definition(marker, source):
    assert source.count(marker) == 1, "%r is not there exactly once" % marker
    start = source.index(marker)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def problems(powers, proc, proc_h, combat, item_powers_h, sheet_names):
    """What the source-text guards find wrong in the server files (the C++ is compile-checked, not run, here)."""
    out = []
    fire = definition("void Fire(Player* player, char const* event, std::string const& skill, double scale, Unit* target, unsigned enemies,", powers)
    loop = fire.index("for (ItemPower::Fired const& one : fired)")
    at = fire.find('one.stat == "proc_damage"')
    if at < 0:
        out.append("no executor for proc_damage")
    else:
        if at < loop:
            out.append("proc_damage is done before the lock is released")
        if "lock_guard" in fire[loop:]:
            out.append("the executors take the item powers' lock")
        executor = fire[at:fire.index("\n                else", at + 1) if "\n                else" in fire[at + 1:] else len(fire)]
        if "ItemProc::Damage(player, target, one.row->owner, one.value, scale);" not in executor:
            out.append("the executor does not hand the enemy, the item, its rolled chance and the hit's proc coefficient to ItemProc::Damage")
    hit = definition("void Hit(Player* player, Unit* target, std::uint32_t spellId)", powers)
    if 'Fire(player, "hit", name, scale, target);' not in hit or "double const scale = coefficient && *coefficient > 0 ? *coefficient : 0;" not in hit:
        out.append("a hit does not fire `hit` with its proc coefficient")
    if '#include "dc_item_proc.h"' not in powers:
        out.append("dc_item_powers.cpp does not include the proc file")
    if "void Damage(Player* player, Unit* target, std::string const& owner, double chancePct, double coefficient);" not in proc_h:
        out.append("dc_item_proc.h does not declare Damage")
    damage = definition("void Damage(Player* player, Unit* target, std::string const& owner, double chancePct, double coefficient)", proc)
    for need, why in (("ItemProc::Pct(chancePct, coefficient, ", "the rule decides"),
                      ('Shells::PowerBuffFor(owner.c_str(), "proc_damage")', "the ball is dealt under the item's hit record"),
                      ("ComputeHit(player, target, record, hit, pct)", "the formula at the tunable's percent of weapon damage"),
                      ("DealHit(player, target, record, hit);", "the core's damage log"),
                      ("target->IsAlive()", "a dead enemy takes no ball")):
        if need not in damage:
            out.append("Damage lacks %s (%s)" % (need, why))
    if "Strike(" in damage or "Passives::Hit" in damage:
        out.append("Damage goes through Strike or Passives::Hit, so the ball would proc itself")
    if 'return DC::Tunables::Has("combat", name) ? DC::Tunables::Get("combat", name) : 0.0;' not in proc:
        out.append("a blank tunable does not read 0")
    if '{"%s", "%s"}' % (OWNER, TUNABLE) not in proc:
        out.append("the item's damage tunable is not the sheet's")
    for name in re.findall(r'\{"[A-Za-z0-9_]+", "(\w+_damage_pct)"\}', proc):
        if name not in sheet_names:
            out.append("the tunable %s is not on data/tunables/combat.csv" % name)
    load = 'Shells::PowerBuffFor("%s", "proc_damage")' % OWNER
    if load not in combat or "loaded[shell.spellId] = shell;" not in combat[combat.find(load):combat.find(load) + 600]:
        out.append("dc_combat.cpp does not load the ball's record as a shell, so ComputeHit refuses it")
    if "void Hit(Player*, Unit* target, std::uint32_t spellId);" not in item_powers_h:
        out.append("ItemPowers::Hit is not declared")
    return out


class Hooks(unittest.TestCase):
    powers = item_powers_source.text()
    proc = source("dc_item_proc.cpp")
    proc_h = source("dc_item_proc.h")
    combat = source("dc_combat.cpp")
    item_powers_h = source("dc_item_powers.h")
    names = {r["name"] for r in read_csv("data/tunables/combat.csv")}

    def args(self, **changed):
        base = dict(powers=self.powers, proc=self.proc, proc_h=self.proc_h, combat=self.combat, item_powers_h=self.item_powers_h,
                    sheet_names=self.names)
        base.update(changed)
        return base

    def test_the_guards_hold_on_the_source(self):
        self.assertEqual([], problems(**self.args()))

    def test_one_caller(self):
        self.assertEqual(["dc_item_powers_effects.cpp"], [p.name for p in SRC.rglob("*.cpp") if "ItemProc::Damage(" in p.read_text(encoding="utf-8")])

    def test_the_stat_is_in_the_generator_and_the_contracts(self):
        self.assertIn("proc_damage", generator.EFFECT_STATS)
        text = (REPO / "docs/contracts/legendary-powers.md").read_text(encoding="utf-8")
        self.assertRegex(text, r"\| `proc_damage` \(")
        self.assertIn("### Storm Crow (`diablocraft-lm3ka`", text)
        self.assertIn(GENERATED.name, text)

    def test_the_server_mutants_fail_the_guards(self):
        p, s, c = self.powers, self.proc, self.combat
        mutants = {
            "no_executor": dict(powers=mutate(p, 'one.stat == "proc_damage"', 'one.stat == "fiery_ball"')),
            "the_coefficient_dropped": dict(powers=mutate(p, "ItemProc::Damage(player, target, one.row->owner, one.value, scale);", "ItemProc::Damage(player, target, one.row->owner, one.value, 1.0);")),
            "the_chance_dropped": dict(powers=mutate(p, "ItemProc::Damage(player, target, one.row->owner, one.value, scale);", "ItemProc::Damage(player, target, one.row->owner, 100.0, scale);")),
            "the_damage_a_literal": dict(proc=mutate(s, '{"%s", "%s"}' % (OWNER, TUNABLE), '{"%s", "other_damage_pct"}' % OWNER)),
            "the_damage_not_on_the_sheet": dict(sheet_names=self.names - {TUNABLE}),
            "the_ball_proccing_itself": dict(proc=mutate(s, "ComputeHit(player, target, record, hit, pct)", "Strike(player, target, record, pct)")),
            "the_damage_not_dealt": dict(proc=mutate(s, "DealHit(player, target, record, hit);", ";")),
            "the_rule_not_asked": dict(proc=mutate(s, "ItemProc::Pct(chancePct, coefficient, ", "ItemProc::Pct(100.0, 1.0, ")),
            "a_dead_enemy_takes_a_ball": dict(proc=mutate(s, "target->IsAlive()", "true")),
            "the_record_not_loaded": dict(combat=mutate(c, 'Shells::PowerBuffFor("%s", "proc_damage")' % OWNER, "0")),
        }
        for name, changed in mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual([], problems(**self.args(**changed)), name + " survived")


if __name__ == "__main__":
    unittest.main()
