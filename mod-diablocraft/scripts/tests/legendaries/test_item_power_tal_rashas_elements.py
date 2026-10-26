"""Legendary set, bead diablocraft-fkcp2: Tal Rasha's Elements (Wizard set; builds N-ELEMEV, N-STACKBUFF and N-ELEMIMM).

  2-piece "Damaging enemies with Arcane, Cold, Fire or Lightning will grant immunity to that element and cause a Meteor of the same damage type to
           fall from the sky. This only occurs if the Wizard has Meteor on their action bar, and the same meteor cannot happen twice in a row."
  4-piece "Arcane, Cold, Fire, and Lightning attacks each increase all of your resistances by 100% for 8 seconds. Attacking with Meteor reduces the
           cooldown of Teleport by 1 second."
  6-piece "Attacks increase your damage by 1000% for 8 seconds. Arcane, Cold, Fire, and Lightning attacks each add one stack. At 4 stacks, each
           different elemental attack extends the duration by 2 seconds, up to a maximum of 8 seconds."
  * the words are d3planner's (data.json itemSets talrasha, the current text); the immunity's SECONDS are in no source: the tunables row
    wizard.tal_rashas_elements_immunity_seconds is the designer's 8 (decisions.md 2026-10-16, card q-1016-09; blank would read 0: the Meteor falls, no immunity);
  * the 6-piece is the designer's reading of that card, one test per clause in SixPiece below;
  * the table holds the rows (the generator refuses a bad one); the generated SQL and the committed migration are what it renders, the migration
    the newest full table;
  * the production rules (dc_item_power_math.h: Fire with the new `hit_element` event, Holds `element_window`, ElementState, Touch, CountOn,
    WindowAttack, MeteorDrops, MeteorRune) are compiled and driven with the generated rows; mutants fail the same driver and the source guards;
  * source-text guards for the server wiring (the hit's element, the buffs on the sheet, the Meteor cast by code, the tunable by the sheet's
    name); the C++ is compile-checked by syntax_check.sh, the in-game steps are in docs/test-diablocraft-fkcp2.md.
"""
import csv
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
import generate_legendary_powers as generator  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_tal_rashas_elements/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Tal Rasha's Elements"
TUNABLE = ("wizard", "tal_rashas_elements_immunity_seconds")
ELEMENTS = "arcane;cold;fire;lightning"
ROW = re.compile(r"\('([^']*(?:''[^']*)*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
# owner, pieces, kind, skill, stat, min, max, cond, arg, condSkills, stackSeconds, stackMax, fireOn, fireSkills, chance, icd
WANT_ROWS = [
    (OWNER, 2, "effect", "", "element_meteor", 1.0, 1.0, "", 0.0, "", 0.0, 0, "hit_element", ELEMENTS, 100.0, 0.0),
    (OWNER, 4, "effect", "", "element_resist", 100.0, 100.0, "", 0.0, "", 8.0, 0, "hit_element", ELEMENTS, 100.0, 0.0),
    (OWNER, 4, "effect", "Teleport", "cooldown_cut_named_seconds", 1.0, 1.0, "", 0.0, "", 0.0, 0, "hit_spender", "Meteor", 100.0, 0.0),
    (OWNER, 6, "effect", "", "element_window", 1.0, 1.0, "", 0.0, "", 8.0, 4, "hit_element", ELEMENTS, 100.0, 0.0),
    (OWNER, 6, "player", "", "damage_dealt_pct", 1000.0, 1000.0, "element_window", 0.0, "", 0.0, 0, "", "", 100.0, 0.0),
    (OWNER, 6, "player", "", "element_extend_seconds", 2.0, 2.0, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0),
    (OWNER, 6, "player", "", "element_extend_max_seconds", 8.0, 8.0, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0),
]
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731


def read_csv_path(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def read_csv(name):
    return read_csv_path(MODULE / name)


def all_rows():
    return [(m[1].replace("''", "'"), int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13],
             m[14], float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


def mutate(source, old, new):
    assert source.count(old) == 1, "mutation target %r is not there exactly once" % old
    return source.replace(old, new)


class Table(unittest.TestCase):
    def test_the_words_are_the_planners(self):
        text = (REPO / "reference/d3planner/data.json").read_text(encoding="utf-8")
        for words in ("Damaging enemies with Arcane, Cold, Fire or Lightning will grant immunity to that element and cause a Meteor of the same damage type",
                      "the same meteor cannot happen twice in a row",
                      "Arcane, Cold, Fire, and Lightning attacks each increase all of your resistances by 100%% for 8 seconds",
                      "Attacking with Meteor reduces the cooldown of Teleport by 1 second",
                      "Attacks increase your damage by 1000%% for 8 seconds",
                      "At 4 stacks, each different elemental attack extends the duration by 2 seconds, up to a maximum of 8 seconds"):
            self.assertIn(words, text)

    def test_the_meteor_runes_are_the_elements(self):
        rune = {r["rune_name"]: r["element"] for r in read_csv("data/d3/wizard_runes.csv") if r["skill_name"] == "Meteor"}
        self.assertEqual({"Comet": "Cold", "Star Pact": "Arcane", "Thunder Crash": "Lightning", "Molten Impact": "Fire", "Meteor Shower": "Fire"}, rune)

    def test_the_rows(self):
        self.assertEqual(WANT_ROWS, mine())

    def test_the_tunable_is_alexs_eight(self):
        sheet = [r for r in read_csv("data/tunables/wizard.csv") if r["name"] == TUNABLE[1]]
        self.assertEqual(1, len(sheet))
        self.assertEqual(("", "8", "seconds"), (sheet[0]["d3_value"], sheet[0]["value"], sheet[0]["unit"]))
        self.assertNotIn("PLACEHOLDER", sheet[0]["notes"])
        for word in ("decisions.md 2026-10-16", "q-1016-09", "diablocraft-fkcp2"):
            self.assertIn(word, sheet[0]["notes"])
        migration = (MODULE / "data/sql/db-world/updates/tunables_0012.sql").read_text(encoding="utf-8")
        self.assertIn("('wizard', 'tal_rashas_elements_immunity_seconds', NULL, 8.0, 'seconds', ", migration)
        self.assertEqual(migration, (MODULE / "data/generated/tunables_0012.sql").read_text(encoding="utf-8"))

    def test_the_generator_refuses_a_bad_row(self):
        sheet = [r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER]
        by = {r["stat"]: r for r in sheet}
        refused = {
            "a meteor effect fired by another event": ("element_meteor", dict(by["element_meteor"], fire_on="hit")),
            "a meteor on an item (no pieces)": ("element_meteor", dict(by["element_meteor"], pieces="")),
            "an element that is none of the four": ("element_meteor", dict(by["element_meteor"], fire_skills="fire;poison")),
            "hit_element without elements": ("element_resist", dict(by["element_resist"], fire_skills="")),
            "a resist effect with no seconds": ("element_resist", dict(by["element_resist"], stack_seconds="")),
            "a resist effect with a stack_max": ("element_resist", dict(by["element_resist"], stack_max="4")),
            "a window with no stack_max": ("element_window", dict(by["element_window"], stack_max="")),
            "a window row with a range": ("element_window", dict(by["element_window"], value_max="2")),
            "a named cut fired by a cast": ("cooldown_cut_named_seconds", dict(by["cooldown_cut_named_seconds"], fire_on="cast")),
            "a named cut of a skill nobody has": ("cooldown_cut_named_seconds", dict(by["cooldown_cut_named_seconds"], skill="Nonesuch")),
            "a named cut with no skill": ("cooldown_cut_named_seconds", dict(by["cooldown_cut_named_seconds"], skill="")),
            "the window condition with no window effect": ("damage_dealt_pct", None),
            "a window condition with an argument": ("damage_dealt_pct", dict(by["damage_dealt_pct"], cond_arg="3")),
            "an extension with a range": ("element_extend_seconds", dict(by["element_extend_seconds"], value_max="3")),
            "an extension that fires": ("element_extend_seconds", dict(by["element_extend_seconds"], fire_on="hit")),
        }
        for name, (stat, bad) in refused.items():
            with self.subTest(name), self.assertRaises(ValueError):
                if bad is None:
                    self.rows_of([r for r in sheet if r["stat"] != "element_window"])
                else:
                    self.rows_of([bad if r["stat"] == stat else r for r in sheet])
        self.assertEqual(7, len(self.rows_of(sheet)))

    @staticmethod
    def rows_of(sheet_rows):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=str(SCRATCH)) as folder:
            module = Path(folder)
            (module / "data/d3").mkdir(parents=True)
            for name in ("base_items.csv", "affix_pools.csv", "legendary_potions.csv", *sorted(p.name for p in (MODULE / "data/d3").glob("*_skills.csv")),
                         *sorted(p.name for p in (MODULE / "data/d3").glob("*_skill_values.csv")),
                         *sorted(p.name for p in (MODULE / "data/d3").glob("*_runes.csv"))):
                shutil.copy(MODULE / "data/d3" / name, module / "data/d3" / name)
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", module / "data/legendary_power_buffs.csv")
            with (module / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(sheet_rows[0]))
                writer.writeheader()
                writer.writerows(sheet_rows)
            return [row for row in generator.rows(module) if row[2] != "potion"]


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemtal-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        """[(command line, expected output or None)]: worked out from the set's words, not from the code."""
        out = [(T("row", *r), None) for r in rows]
        wear = lambda n: [(T("clear"), None), (T("count", OWNER, n), None), (T("now", 1000), None)]  # noqa: E731
        # which bonuses a hit of an element fires: the 2-piece at 2 worn, the 4-piece's resist at 4, the 6-piece's window at 6
        want = {0: "", 1: "", 2: "element_meteor=1@%s;", 3: "element_meteor=1@%s;", 4: "element_meteor=1@%s;element_resist=100@%s;",
                5: "element_meteor=1@%s;element_resist=100@%s;", 6: "element_meteor=1@%s;element_resist=100@%s;element_window=1@%s;"}
        for pieces, text in want.items():
            for element in ("arcane", "cold", "fire", "lightning"):
                out += wear(pieces) + [(T("fire", "hit_element", element), text.replace("%s", element))]
        # other schools / skills are none of the set's elements; other events fire none of its rows
        out += wear(6) + [(T("fire", "hit_element", "physical"), ""), (T("fire", "hit_element", "poison"), ""), (T("fire", "hit_element", ""), ""),
                          (T("fire", "hit_element", "Fire"), ""), (T("fire", "hit", "fire"), ""), (T("fire", "cast", "Meteor"), ""),
                          (T("fire", "kill", "fire"), "")]
        # the Teleport cut: a spender's hit with Meteor at 4 worn, once a cast (the event is the cast's), no other skill, not at 3
        out += wear(4) + [(T("fire", "hit_spender", "Meteor"), "cooldown_cut_named_seconds=1@;"), (T("fire", "hit_spender", "Frost Nova"), ""),
                          (T("fire", "hit_generator", "Meteor"), ""), (T("fire", "hit", "Meteor"), "")]
        out += wear(6) + [(T("fire", "hit_spender", "Meteor"), "cooldown_cut_named_seconds=1@;")]
        out += wear(3) + [(T("fire", "hit_spender", "Meteor"), "")]
        # 1000 percent more damage (a factor of 11) at 6 worn while the window is open, none with it shut or with 5 worn
        out += wear(6) + [(T("factor", "damage_dealt_pct"), "1"), (T("attack", "fire", 8, 4, 2, 8), None), (T("factor", "damage_dealt_pct"), "11"),
                          (T("now", 8999), None), (T("factor", "damage_dealt_pct"), "11"), (T("now", 9000), None), (T("factor", "damage_dealt_pct"), "1")]
        out += wear(5) + [(T("attack", "fire", 8, 4, 2, 8), None), (T("factor", "damage_dealt_pct"), "1")]
        # the window: the first attack opens 8 s with one stack; attacks do not renew it; the 4th element is the 4th stack and extends nothing
        out += wear(6) + [(T("window"), "0 0 0 0"), (T("attack", "arcane", 8, 4, 2, 8), None), (T("window"), "1 8000 0 1"),
                          (T("now", 2000), None), (T("attack", "arcane", 8, 4, 2, 8), None), (T("window"), "1 7000 0 1"),
                          (T("attack", "cold", 8, 4, 2, 8), None), (T("window"), "1 7000 0 2"),
                          (T("now", 3000), None), (T("attack", "fire", 8, 4, 2, 8), None), (T("window"), "1 6000 0 3"),
                          (T("now", 4000), None), (T("attack", "lightning", 8, 4, 2, 8), None), (T("window"), "1 5000 0 4"),
                          # at 4 stacks each DIFFERENT element from the last attack's extends by 2 s: the same one again does not
                          (T("attack", "lightning", 8, 4, 2, 8), None), (T("window"), "1 5000 0 4"),
                          (T("attack", "arcane", 8, 4, 2, 8), None), (T("window"), "1 7000 2000 4"),
                          (T("attack", "arcane", 8, 4, 2, 8), None), (T("window"), "1 7000 2000 4"),
                          (T("attack", "cold", 8, 4, 2, 8), None), (T("window"), "1 9000 4000 4"),
                          (T("attack", "fire", 8, 4, 2, 8), None), (T("window"), "1 11000 6000 4"),
                          (T("attack", "lightning", 8, 4, 2, 8), None), (T("window"), "1 13000 8000 4"),
                          # all the extensions together are at most 8 s
                          (T("attack", "arcane", 8, 4, 2, 8), None), (T("window"), "1 13000 8000 4"),
                          (T("attack", "cold", 8, 4, 2, 8), None), (T("window"), "1 13000 8000 4"),
                          # the window runs out (4000 + 13000) and the next attack opens a new one whose extensions start from nothing
                          (T("now", 17000), None), (T("window"), "0 0 8000 4"), (T("attack", "arcane", 8, 4, 2, 8), None), (T("window"), "1 8000 0 1")]
        # a maximum that is not a multiple of the extension: the last extension is cut to what is left (8 s max, 3 s each: 3, 3, 2)
        out += wear(6) + [(T("attack", "arcane", 8, 1, 3, 8), None), (T("attack", "cold", 8, 1, 3, 8), None), (T("attack", "fire", 8, 1, 3, 8), None),
                          (T("window"), "1 14000 6000 3"), (T("attack", "cold", 8, 1, 3, 8), None), (T("window"), "1 16000 8000 3"),
                          (T("attack", "fire", 8, 1, 3, 8), None), (T("attack", "arcane", 8, 1, 3, 8), None), (T("window"), "1 16000 8000 3")]
        # fewer than 4 stacks never extend; a window that ended starts anew with one stack and its extensions back at 0
        out += wear(6) + [(T("attack", "fire", 8, 4, 2, 8), None), (T("attack", "cold", 8, 4, 2, 8), None), (T("attack", "fire", 8, 4, 2, 8), None),
                          (T("window"), "1 8000 0 2"), (T("now", 9000), None), (T("window"), "0 0 0 2"), (T("attack", "cold", 8, 4, 2, 8), None),
                          (T("window"), "1 8000 0 1")]
        # a buff of an element (the 4-piece's resistances, the 2-piece's immunity): off to on starts it, an attack again only moves its end
        for kind in ("resist", "immune"):
            out += wear(6) + [(T("on", kind), "0"), (T("touch", kind, "fire", 8000), "1"), (T("on", kind), "1"), (T("now", 5000), None),
                              (T("touch", kind, "fire", 8000), "0"), (T("on", kind), "1"), (T("touch", kind, "cold", 9000), "1"), (T("on", kind), "2"),
                              (T("now", 12999), None), (T("on", kind), "2"), (T("now", 13000), None), (T("on", kind), "1"), (T("now", 13999), None),
                              (T("on", kind), "1"), (T("now", 14000), None), (T("on", kind), "0"), (T("touch", kind, "fire", 8000), "1")]
        # the two kinds are separate; the clock wraps
        out += wear(6) + [(T("touch", "resist", "fire", 8000), "1"), (T("on", "immune"), "0"), (T("touch", "immune", "fire", 8000), "1")]
        out += wear(6) + [(T("now", 4294967000), None), (T("touch", "resist", "fire", 8000), "1"), (T("now", 4294967295), None), (T("on", "resist"), "1"),
                          (T("now", 7000), None), (T("on", "resist"), "1"), (T("now", 7704), None), (T("on", "resist"), "0")]
        # the Meteor: with Meteor on the bar, not the element of the last one it dropped
        out += wear(2) + [(T("drops", "fire", 1), "1"), (T("drops", "fire", 0), "0"), (T("setmeteor", "fire"), None), (T("drops", "fire", 1), "0"),
                          (T("drops", "cold", 1), "1"), (T("drops", "cold", 0), "0"), (T("setmeteor", "cold"), None), (T("drops", "fire", 1), "1"),
                          (T("drops", "cold", 1), "0")]
        for element, rune in (("fire", ""), ("cold", "Comet"), ("arcane", "Star Pact"), ("lightning", "Thunder Crash"), ("poison", "")):
            out += [(T("rune", element), "[%s]" % rune)]
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

    def test_every_rule_agrees_with_the_set(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(want), 100)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(7, len(rows))
        row_mutants = {
            "the_wrong_event": [r[:12] + ("hit",) + r[13:] if r[4] == "element_meteor" else r for r in rows],
            "a_fifth_element": [r[:13] + (ELEMENTS + ";poison",) + r[14:] if r[4] == "element_resist" else r for r in rows],
            "the_cut_on_a_cast": [r[:12] + ("cast",) + r[13:] if r[4] == "cooldown_cut_named_seconds" else r for r in rows],
            "no_window_condition": [r[:7] + ("",) + r[8:] if r[4] == "damage_dealt_pct" else r for r in rows],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {
            "the_window_condition_is_always_on": mutate(real, "return situation.elementWindow;", "return true;"),
            "the_window_condition_is_never_on": mutate(real, "return situation.elementWindow;", "return false;"),
            "the_element_is_not_carried": mutate(real, "out.back().on = skill;", "out.back().on = \"fire\";"),
            "a_buff_on_its_last_millisecond_is_on": mutate(real, "static_cast<std::int32_t>(until - now) > 0", "static_cast<std::int32_t>(until - now) >= 0"),
            "an_unset_buff_is_on": mutate(real, "return until != 0 && static_cast<std::int32_t>", "return static_cast<std::int32_t>"),
            "touch_always_starts": mutate(real, "bool const was = Before(now, ends[element]);", "bool const was = false;"),
            "touch_does_not_move_the_end": mutate(real, "ends[element] = now + ms;\n        return !was;", "if (!was)\n            ends[element] = now + ms;\n        return !was;"),
            "count_on_counts_all": mutate(real, "on += Before(now, until) ? 1u : 0u;", "on += 1u;"),
            "the_window_is_renewed_by_an_attack": mutate(real, "bool const full = state.stacks.size() >= fullAt;", "state.windowUntil = now + static_cast<std::uint32_t>(seconds * 1000.0);\n        bool const full = state.stacks.size() >= fullAt;"),
            "the_stack_that_fills_extends": mutate(real, "bool const full = state.stacks.size() >= fullAt;\n        state.stacks.insert(element);", "state.stacks.insert(element);\n        bool const full = state.stacks.size() >= fullAt;"),
            "the_same_element_extends": mutate(real, "if (full && element != state.lastHit)", "if (full)"),
            "extends_before_four": mutate(real, "bool const full = state.stacks.size() >= fullAt;", "bool const full = state.stacks.size() >= 1;"),
            "extends_without_a_maximum": mutate(real, "most - std::min(state.extendedMs, most)", "static_cast<std::uint32_t>(extendSeconds * 1000.0)"),
            "a_new_window_keeps_the_old_extensions": mutate(real, "            state.extendedMs = 0;\n", ""),
            "a_new_window_keeps_the_old_stacks": mutate(real, "            state.stacks = {element};", "            state.stacks.insert(element);"),
            "the_meteor_ignores_the_bar": mutate(real, "return meteorOnBar && element != state.lastMeteor;", "return element != state.lastMeteor;"),
            "the_meteor_repeats": mutate(real, "return meteorOnBar && element != state.lastMeteor;", "return meteorOnBar;"),
            "comet_is_fire": mutate(real, 'return "Comet";', 'return "";'),
            "star_pact_is_cold": mutate(real, 'return "Star Pact";', 'return "Comet";'),
            "thunder_crash_is_arcane": mutate(real, 'return "Thunder Crash";', 'return "Star Pact";'),
        }
        for name, header in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, header, name + " did not apply")
                want, got = self.drive(header, rows, name)
                self.assertNotEqual(want, got, name + " survived")


class SixPiece(unittest.TestCase):
    """the designer's reading of the 6-piece (decisions.md 2026-10-16, card q-1016-09), one test per clause, each driving the production WindowAttack with the
    numbers the generated rows carry (8 s window, 4 stacks, 2 s each, 8 s at most). The times are worked out from the clause, not from the code."""
    work = binary = None

    @classmethod
    def setUpClass(cls):
        cls.work, cls.binary = Rules.build(MATH.read_text(encoding="utf-8"), "six")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    @staticmethod
    def numbers():
        rows = {r[4]: r for r in mine() if r[1] == 6}
        window = rows["element_window"]
        return window[10], window[11], rows["element_extend_seconds"][5], rows["element_extend_max_seconds"][5]

    def play(self, *steps, built=None):
        """Each step is (ms the clock reads, element or None for a look, expected "open remainingMs extendedMs stacks" after it); `built` is a
        (folder, binary) of another header."""
        work, binary = built or (self.work, self.binary)
        seconds, stacks, extend, most = self.numbers()
        lines, want = [T("clear")], []
        for now, element, expected in steps:
            lines.append(T("now", now))
            if element:
                lines.append(T("attack", element, seconds, stacks, extend, most))
            lines.append(T("window"))
            want.append(expected)
        path = work / "six.txt"
        path.write_text("\n".join(lines) + "\n")
        run = harness_env.run([str(binary), str(path)], capture_output=True, text=True)
        self.assertEqual(0, run.returncode, run.stderr)
        return want, run.stdout.split("\n")[:-1]

    def check(self, *steps):
        want, got = self.play(*steps)
        self.assertEqual(want, got)

    def test_the_numbers_are_alexs(self):
        self.assertEqual((8.0, 4, 2.0, 8.0), self.numbers())

    def test_a_the_window_opens_on_the_first_hit(self):
        self.check((1000, None, "0 0 0 0"), (1000, "fire", "1 8000 0 1"), (8999, None, "1 1 0 1"), (9000, None, "0 0 0 1"))
        # a window that is open holds the damage bonus; before the first hit there is none
        rows = [(T("row", *r), None) for r in mine()]
        lines = [l for l, _ in rows] + [T("count", OWNER, 6), T("now", 1000), T("factor", "damage_dealt_pct"), T("attack", "fire", *self.numbers()),
                                        T("factor", "damage_dealt_pct")]
        path = self.work / "bonus.txt"
        path.write_text("\n".join(lines) + "\n")
        run = harness_env.run([str(self.binary), str(path)], capture_output=True, text=True)
        self.assertEqual(["1", "11"], run.stdout.split("\n")[:-1])

    def test_b_four_different_elements_within_the_window_stack_it_to_4(self):
        # the last one lands 1 ms before the 8 seconds are over: four stacks, the window still the first 8 seconds, nothing added by the fourth
        self.check((0, "arcane", "1 8000 0 1"), (2000, "cold", "1 6000 0 2"), (4000, "fire", "1 4000 0 3"), (7999, "lightning", "1 1 0 4"))
        # a fourth element after the 8 seconds is a new window with one stack, not the fourth stack
        self.check((0, "arcane", "1 8000 0 1"), (2000, "cold", "1 6000 0 2"), (4000, "fire", "1 4000 0 3"), (8000, "lightning", "1 8000 0 1"))

    def test_c_after_that_each_different_element_adds_2_seconds(self):
        full = [(0, "arcane", "1 8000 0 1"), (1000, "cold", "1 7000 0 2"), (2000, "fire", "1 6000 0 3"), (3000, "lightning", "1 5000 0 4")]
        self.check(*full, (4000, "arcane", "1 6000 2000 4"), (5000, "cold", "1 7000 4000 4"), (6000, "fire", "1 8000 6000 4"))
        # a different element than the attack before it counts even when it was stacked already (the set cycles through all four)
        self.check(*full, (4000, "arcane", "1 6000 2000 4"), (4500, "lightning", "1 7500 4000 4"), (5000, "arcane", "1 9000 6000 4"))

    def test_d_the_extensions_are_capped_at_8_seconds(self):
        full = [(0, "arcane", "1 8000 0 1"), (1000, "cold", "1 7000 0 2"), (2000, "fire", "1 6000 0 3"), (3000, "lightning", "1 5000 0 4")]
        self.check(*full, (3100, "arcane", "1 6900 2000 4"), (3200, "cold", "1 8800 4000 4"), (3300, "fire", "1 10700 6000 4"),
                   (3400, "lightning", "1 12600 8000 4"), (3500, "arcane", "1 12500 8000 4"), (3600, "cold", "1 12400 8000 4"))
        # the 8 seconds is the extensions together and not the window: the first hit at 0 and the end at 3400 + 12600 = 16000, never later

    def test_e_attacks_never_renew_the_base_window(self):
        # every kind of attack in the first 8 seconds leaves the end where the first hit put it
        self.check((0, "arcane", "1 8000 0 1"), (3000, "arcane", "1 5000 0 1"), (6000, "arcane", "1 2000 0 1"), (7500, "cold", "1 500 0 2"))
        self.check((0, "arcane", "1 8000 0 1"), (1000, "cold", "1 7000 0 2"), (2000, "fire", "1 6000 0 3"), (3000, "lightning", "1 5000 0 4"),
                   (3000, "lightning", "1 5000 0 4"), (7000, "lightning", "1 1000 0 4"))

    def test_f_a_repeat_adds_nothing(self):
        # the same element again, and an element already stacked, add no stack
        self.check((0, "fire", "1 8000 0 1"), (500, "fire", "1 7500 0 1"), (900, "fire", "1 7100 0 1"), (1000, "cold", "1 7000 0 2"),
                   (1100, "fire", "1 6900 0 2"), (1200, "cold", "1 6800 0 2"))
        # at 4 stacks the element just used, again, adds no seconds, however often
        self.check((0, "arcane", "1 8000 0 1"), (1000, "cold", "1 7000 0 2"), (2000, "fire", "1 6000 0 3"), (3000, "lightning", "1 5000 0 4"),
                   (3100, "lightning", "1 4900 0 4"), (3200, "lightning", "1 4800 0 4"), (3300, "arcane", "1 6700 2000 4"),
                   (3400, "arcane", "1 6600 2000 4"), (3500, "arcane", "1 6500 2000 4"))

    def test_a_window_that_ran_out_starts_over(self):
        self.check((0, "arcane", "1 8000 0 1"), (1000, "cold", "1 7000 0 2"), (2000, "fire", "1 6000 0 3"), (3000, "lightning", "1 5000 0 4"),
                   (3100, "arcane", "1 6900 2000 4"), (10000, None, "0 0 2000 4"), (10000, "cold", "1 8000 0 1"))

    def test_the_clauses_have_mutants_that_fail(self):
        real = MATH.read_text(encoding="utf-8")
        mutants = {
            "the_window_is_renewed_by_an_attack": mutate(real, "bool const full = state.stacks.size() >= fullAt;", "state.windowUntil = now + static_cast<std::uint32_t>(seconds * 1000.0);\n        bool const full = state.stacks.size() >= fullAt;"),
            "the_stack_that_fills_extends": mutate(real, "bool const full = state.stacks.size() >= fullAt;\n        state.stacks.insert(element);", "state.stacks.insert(element);\n        bool const full = state.stacks.size() >= fullAt;"),
            "the_same_element_extends": mutate(real, "if (full && element != state.lastHit)", "if (full)"),
            "an_element_stacked_before_never_extends": mutate(real, "if (full && element != state.lastHit)", "if (full && element != state.lastHit && !state.stacks.count(element))"),
            "extends_before_four": mutate(real, "bool const full = state.stacks.size() >= fullAt;", "bool const full = state.stacks.size() >= 3;"),
            "no_maximum": mutate(real, "most - std::min(state.extendedMs, most)", "static_cast<std::uint32_t>(extendSeconds * 1000.0)"),
            "a_repeat_adds_a_stack": mutate(real, "state.stacks.insert(element);\n        if (full", "state.stacks.insert(element + std::to_string(now));\n        if (full"),
            "the_window_is_not_opened_by_the_first_hit": mutate(real, "state.windowUntil = now + static_cast<std::uint32_t>(seconds * 1000.0);\n            state.extendedMs = 0;", "state.windowUntil = now + static_cast<std::uint32_t>(seconds * 500.0);\n            state.extendedMs = 0;"),
        }
        for name, header in mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, header, name + " did not apply")
                built = Rules.build(header, name)
                try:
                    want, got = self.play((0, "arcane", "1 8000 0 1"), (1000, "cold", "1 7000 0 2"), (2000, "fire", "1 6000 0 3"), (3000, "lightning", "1 5000 0 4"),
                                          (3100, "lightning", "1 4900 0 4"), (3200, "arcane", "1 6800 2000 4"), (3300, "cold", "1 8700 4000 4"),
                                          (3400, "fire", "1 10600 6000 4"), (3500, "lightning", "1 12500 8000 4"), (3600, "arcane", "1 12400 8000 4"),
                                          (4000, "arcane", "1 11900 8000 4"), (20000, None, "0 0 8000 4"), (20000, "arcane", "1 8000 0 1"),
                                          (20100, "arcane", "1 7900 0 1"), (20200, "cold", "1 7800 0 2"), built=built)
                    self.assertNotEqual(want, got, name + " survived")
                finally:
                    shutil.rmtree(built[0], ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
