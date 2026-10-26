"""Legendary rest, bead diablocraft-z1q6q: Krede's Flame (a ring, list row 62, K3), and the event it builds, N-SCHOOLEV.

  "Taking Fire damage restores your primary resource."
  * the words are d3planner's (item_finger.js, Unique_Ring_003_x1: custom leg_kredesflame, no number); the number is the power file's, read through decode_pow.py
    (Item_Power_Passive ItemPassive_Unique_Ring_669_x1.pow: 1; SF_0 'Resource % Gain Per 1% HP Lost' = 1). The table (data/legendary_powers.csv) holds ONE
    `effect` row for the ring: `resource_per_life_lost_pct` 1, fired by the new `taken_element` event for the element `fire`;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator accepts the stat only
    on `taken_element` and the event only with elements (SET_ELEMENTS) and that stat;
  * the production rules (src/combat/dc_item_power_math.h: Fire, LifeLostPct, ResourceFromLifeLost) are compiled and driven with the generated row: while the ring
    is worn, a hit of Fire fires the effect with the power file's number and nothing else does (another element, no element, another event, an unworn ring, another
    owner's); the Life a hit takes is its share of the maximum and no more than the Life there is; the resource it gives is the number's percent of the maximum
    for each percent of Life lost; mutants of the row and the rules fail the same driver;
  * source-text guards that Passives::Taken hands the hit's damage on, every hook that calls it passes the damage after the defence, ItemPowers::TakenElement fires
    `taken_element` with the school's element and the Life before and after, and the executor gives the resource for the Life the hit took. The C++ is
    compile-checked by syntax_check.sh and the in-game steps are in docs/test-diablocraft-z1q6q.md.
"""
import csv
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
import generate_legendary_powers as generator  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
EVENTS = SRC / "combat/dc_item_powers_events.cpp"
EFFECTS = SRC / "combat/dc_item_powers_effects.cpp"
PASSIVES = SRC / "combat/dc_passives.cpp"
HOOKS = SRC / "combat/dc_combat_hooks.cpp"
COMBAT = SRC / "combat/dc_combat.cpp"
HARNESS = MODULE / "tests/item_power_kredes_flame/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_Ring_003_x1"
STAT = "resource_per_life_lost_pct"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
g = lambda x: "%.10g" % x  # noqa: E731


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


class Table(unittest.TestCase):
    def test_the_sources_say_fire_damage_restores_the_primary_resource(self):
        text = (REPO / "reference/d3planner/item_finger.js").read_text(encoding="utf-8")
        start = text.index('id: "%s"' % OWNER)
        item = text[start:text.index("},\n\n", start)]
        self.assertIn('format: "Taking Fire damage restores your primary resource.", args: 0', item)
        self.assertIn("Taking Fire damage restores your primary resource.", (REPO / "docs/research/legendary-catalogue.csv").read_text(encoding="utf-8"))

    def test_the_power_file_has_the_number_one(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("no D3 archives on this machine")
        run = lambda *a: harness_env.run([sys.executable, str(MODULE / "scripts/decode_pow.py"), *a], capture_output=True, text=True).stdout  # noqa: E731
        self.assertRegex(run("power", "ItemPassive_Unique_Ring_669_x1"), r"'Resource % Gain Per 1% HP Lost' = 1\b")
        self.assertIn("ItemPassive_Unique_Ring_669_x1.pow: 1", run("item", OWNER))

    def test_one_effect_row_on_the_fire_hit(self):
        self.assertEqual([(OWNER, 0, "effect", "", STAT, 1.0, 1.0, "", 0.0, "", 0.0, 0, "taken_element", "fire", 100.0, 0.0)], mine())

    def test_the_render_is_the_newest_full_table_and_the_applied_one_is_left(self):
        self.assertEqual(GENERATED.read_bytes(), (MODULE / "data/sql/db-world/updates" / GENERATED.name).read_bytes())
        self.assertGreaterEqual(GENERATED.name, "legendary_powers_0065_table.sql")


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "effect", "skill": "", "stat": STAT, "value_min": "1", "value_max": "1", "cond": "", "cond_arg": "",
            "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "taken_element", "fire_skills": "fire", "chance_pct": "", "icd_seconds": "",
            "source": "s", "note": "n"}

    def render_with(self, edit):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="kredes-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            rows = read_csv("data/legendary_powers.csv")
            kept = [r for r in rows if r["owner"] != OWNER]
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(kept + [{**self.BASE, **edit}])
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_real_row_passes(self):
        self.assertEqual(1, len([r for r in self.render_with({}) if r[0] == OWNER]))

    def test_it_refuses_what_it_cannot_carry(self):
        refused = {
            "no element named": {"fire_skills": ""},
            "a skill, not an element": {"fire_skills": "Rend"},
            "an element the set does not read": {"fire_skills": "poison"},
            "the stat on another event": {"fire_on": "taken", "fire_skills": ""},
            "another stat on taken_element": {"stat": "resource_refund"},
            "no number": {"value_min": "0", "value_max": "0"},
            "a range": {"value_min": "1", "value_max": "2"},
            "a set level": {"pieces": "2"},
            "a stat row": {"kind": "player"},
        }
        for name, edit in refused.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    self.render_with(edit)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files={"combat/dc_item_power_math.h": header_text})
        return Path(tempfile.mkdtemp(prefix="itemkredes-%s-" % name, dir=str(SCRATCH))), binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the item's words and the power file's number, not from the code."""
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        wear = clear + [(T("wears", OWNER), None), (T("now", 1000), None)]
        # the ring worn: a hit of Fire gives the power file's 1, whatever the school's other names are
        out += wear + [(T("fire", "taken_element", "fire"), "%s:1" % STAT)]
        # no other element, no element at all, no skill, another case, another event: nothing
        for element in ("cold", "arcane", "lightning", "physical", "poison", "holy", "", "Fire", "fire "):
            out += wear + [(T("fire", "taken_element", element), "none")]
        for event in ("taken", "hit_element", "hit", "kill", "cast", "block", "chest", "taken_elements", ""):
            out += wear + [(T("fire", event, "fire"), "none")]
        # not worn, worn by a bag, another owner's ring
        out += clear + [(T("now", 1000), None), (T("fire", "taken_element", "fire"), "none")]
        out += clear + [(T("wears", "Other Ring"), None), (T("fire", "taken_element", "fire"), "none")]
        # the Life a hit takes: its share of the maximum, no more than the Life there is, nothing for nothing
        for health, most, damage, want in ((1000, 1000, 100, 10), (1000, 1000, 1000, 100), (1000, 1000, 2500, 100), (30, 1000, 50, 3), (0, 1000, 50, 0), (500, 0, 50, 0),
                                           (500, -1, 50, 0), (500, 1000, 0, 0), (500, 1000, -5, 0), (1000, 2000, 50, 2.5), (1, 1000, 1000, 0.1)):
            out.append((T("lost", health, most, damage), g(want)))
        # the resource it gives: the number's percent of the maximum for each percent of Life lost
        for number, lost, most, want in ((1, 10, 100, 10), (1, 10, 150, 15), (1, 0.5, 100, 0.5), (2, 10, 100, 20), (0.5, 10, 100, 5), (1, 100, 125, 125),
                                         (0, 10, 100, 0), (-1, 10, 100, 0), (1, 0, 100, 0), (1, -5, 100, 0), (1, 10, 0, 0), (1, 10, -100, 0)):
            out.append((T("gain", number, lost, most), g(want)))
        return out

    def drive(self, header_text, rows, name):
        cases = self.cases(rows)
        work, binary = self.build(header_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_every_rule_agrees_with_the_item_text(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(want), 40)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        want, _ = self.drive(real, rows, "want")
        row = rows[0]
        row_mutants = {
            "another_element": [row[:13] + ("cold",) + row[14:]],
            "another_event": [row[:12] + ("taken",) + row[13:]],
            "a_number_of_two": [row[:5] + (2.0, 2.0) + row[7:]],
            "another_stat": [row[:4] + ("resource_refund",) + row[5:]],
            "every_element": [row[:13] + ("",) + row[14:]],
            "no_row": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        for name, (old, new) in {
            "a_killing_hit_loses_all_the_damage": ("100.0 * std::min(damage, health) / maxHealth", "100.0 * damage / maxHealth"),
            "life_lost_of_the_life_left": ("100.0 * std::min(damage, health) / maxHealth", "100.0 * std::min(damage, health) / health"),
            "no_maximum_still_counts": ("if (maxHealth <= 0 || damage <= 0 || health <= 0)", "if (damage <= 0 || health <= 0)"),
            "the_gain_is_per_point_not_a_percent": ("return maxResource * pctPerPct * lostPct / 100.0;", "return pctPerPct * lostPct;"),
            "the_gain_ignores_the_number": ("return maxResource * pctPerPct * lostPct / 100.0;", "return maxResource * lostPct / 100.0;"),
            "a_negative_number_takes_resource": ("if (pctPerPct <= 0 || lostPct <= 0 || maxResource <= 0)", "if (lostPct <= 0 || maxResource <= 0)"),
            "no_resource_still_gives": ("if (pctPerPct <= 0 || lostPct <= 0 || maxResource <= 0)", "if (pctPerPct <= 0 || lostPct <= 0)"),
        }.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply")
                _, got = self.drive(real.replace(old, new, 1), rows, name)
                self.assertNotEqual(want, got, name + " survived")


def wiring_failures(events, effects, passives, hooks, combat):
    """What is wrong with the hit's way to the `taken_element` event in the given sources ([] when it is right)."""
    flat = lambda text: re.sub(r"\s+", " ", text)  # noqa: E731
    events, effects, passives = flat(events), flat(effects), flat(passives)
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    need("Passives::Taken takes the damage and hands it to the element event",
         "void Taken(Player* p, unsigned school, bool ranged, double damage) { ItemPowers::Taken(p); ItemPowers::TakenElement(p, school, damage);" in passives)
    need("the melee, spell and periodic hooks pass the damage after the defence", hooks.count(",damage);") >= 3 and "false,damage);" in hooks
         and hooks.count("SPELL_DAMAGE_CLASS_RANGED,damage);") == 2)
    need("the monster hit passes its damage after the mitigation", "Passives::Taken(victim,school,false,damage);" in combat)
    need("the event is asked only when a row listens, for a hit with damage", 'if (!player || damage <= 0 || !Data().events.count("taken_element")) return;' in events)
    need("the school is read as an element", "char const* element = ElementOfSchool(school);" in events and "if (!element || most <= 0) return;" in events)
    need("it fires the element with the Life before and after the hit",
         'Fire(player, "taken_element", element, 1.0, nullptr, 0, 0.0, 100.0 * health / most, 100.0 * (health - std::min(damage, health)) / most);' in events)
    need("the executor gives the resource for the Life the hit took",
         'else if (one.stat == "resource_per_life_lost_pct")' in effects and
         "ItemPower::ResourceFromLifeLost(one.value, lifeBefore - lifeAfter, Resources::Max(player, *resource))" in effects)
    need("the resource_refund branch is braced, so the next branch is not its inner if's else",
         'else if (one.stat == "resource_refund") { if (Resources::Resource const* resource' in effects)
    return wrong


class Hooks(unittest.TestCase):
    def sources(self):
        return [p.read_text(encoding="utf-8") for p in (EVENTS, EFFECTS, PASSIVES, HOOKS, COMBAT)]

    def test_the_hit_reaches_the_event_and_the_executor(self):
        self.assertEqual([], wiring_failures(*self.sources()))

    def test_the_declarations_agree(self):
        self.assertIn("void TakenElement(Player*, unsigned school, double damage);", (SRC / "combat/dc_item_powers.h").read_text(encoding="utf-8"))
        self.assertIn("void Taken(Player*, unsigned, bool, double damage);", (SRC / "combat/dc_passives.h").read_text(encoding="utf-8"))

    def test_the_source_guards_fail_their_mutants(self):
        events, effects, passives, hooks, combat = self.sources()
        mutants = {
            "passives_drop_the_event": ("passives", "ItemPowers::TakenElement(p, school, damage);", ""),
            "passives_lose_the_damage": ("passives", "bool ranged, double damage)", "bool ranged, double)"),
            "a_hook_passes_nothing": ("hooks", "false,damage);", "false,0);"),
            "the_monster_hit_passes_nothing": ("combat", "Passives::Taken(victim,school,false,damage);", "Passives::Taken(victim,school,false,0);"),
            "always_looks": ("events", ' || !Data().events.count("taken_element")', ""),
            "any_school": ("events", "char const* element = ElementOfSchool(school);", 'char const* element = "fire";'),
            "wrong_event": ("events", 'Fire(player, "taken_element", element,', 'Fire(player, "hit_element", element,'),
            "no_life_after": ("events", "100.0 * (health - std::min(damage, health)) / most", "100.0 * health / most"),
            "no_effect_branch": ("effects", 'else if (one.stat == "resource_per_life_lost_pct")', 'else if (one.stat == "resource_per_life_lost_pcts")'),
            "the_gain_ignores_the_life": ("effects", "lifeBefore - lifeAfter", "100.0"),
            "the_dangling_else": ("effects", 'else if (one.stat == "resource_refund")\n                {', 'else if (one.stat == "resource_refund")'),
        }
        texts = {"events": events, "effects": effects, "passives": passives, "hooks": hooks, "combat": combat}
        for name, (which, old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertGreaterEqual(texts[which].count(old), 1, name + " does not apply")
                changed = dict(texts, **{which: texts[which].replace(old, new)})
                self.assertNotEqual([], wiring_failures(changed["events"], changed["effects"], changed["passives"], changed["hooks"], changed["combat"]), name + " survived")


if __name__ == "__main__":
    unittest.main()
