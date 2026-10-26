"""Legendary rest, bead diablocraft-y27fd: Lut Socks (Barbarian boots). Builds N-CHG: a skill that can be cast several times in a window before its cooldown begins.

  "Leap can be cast up to three times within 2 seconds before the cooldown begins."
  * the numbers are in the text (d3planner data.json, Unique_Boots_009_x1, custom leg_lutsocks, args 0); the table (data/legendary_powers.csv) holds TWO fixed `skill`
    rows for the pool item, both on Leap: `reuse_casts` 3 and `reuse_window_seconds` 2;
  * the generated SQL and the committed migration are what the generator renders; the generator accepts the pair only for the skills whose cast code reads them
    (Leap), fixed whole casts of at least 2, a positive window, simply on, and refuses one row without the other;
  * the production rule (src/combat/dc_item_power_math.h: ReuseCast / ReuseEnded, with SkillSetTo for the two numbers) is compiled and driven: the first cast opens the
    window, the next casts inside it (the end inclusive) keep the skill open, the last one closes it and leaves the cooldown, a cast after the end opens a new window,
    the window's end event closes only its own window; mutants of the rule and of the rows fail the same driver;
  * source-text guards that ItemPowers::Cast keeps the skill open (cooldown cleared, the end event scheduled, the In-geom cut skipped) and that the end of the window,
    and a logout inside it, install the cooldown the skill would have had; mutants of that text fail the same guards. The in-game steps are in docs/test-diablocraft-y27fd.md.
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
HARNESS = MODULE / "tests/item_power_events/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_Boots_009_x1"
SKILL = "Leap"
CASTS, WINDOW = "reuse_casts", "reuse_window_seconds"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
BLANK = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


class Table(unittest.TestCase):
    def test_the_sources_say_what_the_rows_say(self):
        data = (REPO / "reference/d3planner/data.json").read_text(encoding="utf-8")
        m = re.search(r'"id":"%s".{0,400}?"format":"([^"]*)"' % OWNER, data)
        self.assertTrue(m)
        self.assertEqual("Leap can be cast up to three times within 2 seconds before the cooldown begins.", m[1])
        self.assertIn(SKILL, [r["skill_name"] for r in read_csv("data/d3/barbarian_skills.csv")])

    def test_two_fixed_rows_name_the_casts_and_the_window(self):
        self.assertEqual([(OWNER, 0, "skill", SKILL, CASTS, 3.0, 3.0, *BLANK), (OWNER, 0, "skill", SKILL, WINDOW, 2.0, 2.0, *BLANK)],
                         sorted(mine(), key=lambda r: r[4]))

    def test_the_tooltip_shows_the_text(self):
        m = re.search(r"\('%s','[^']*','((?:[^']|'')*)'" % OWNER, (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertEqual("Leap can be cast up to three times within 2 seconds before the cooldown begins.", m[1])


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "skill", "skill": SKILL, "stat": CASTS, "value_min": "3", "value_max": "3", "cond": "",
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}
    PAIR = [{"stat": CASTS, "value_min": "3", "value_max": "3"}, {"stat": WINDOW, "value_min": "2", "value_max": "2"}]

    def render_with(self, *edits):
        work = Path(tempfile.mkdtemp(prefix="lutsocks-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            sheet = read_csv("data/legendary_powers.csv")
            kept = [r for r in sheet if r["owner"] != OWNER]
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(sheet[0].keys()))
                writer.writeheader()
                writer.writerows(kept + [{**self.BASE, **e} for e in edits])
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_real_pair_passes(self):
        self.assertEqual(2, len([r for r in self.render_with(*self.PAIR) if r[0] == OWNER]))

    def test_it_refuses_what_the_code_does_not_read(self):
        def with_(**kw):
            return [{**p, **{k: v for k, v in kw.items() if k != "only"}} if p["stat"] == kw.get("only", p["stat"]) else p for p in self.PAIR]
        refused = {
            "the casts alone": [self.PAIR[0]],
            "the window alone": [self.PAIR[1]],
            "a skill that does not read them": with_(skill="Frenzy"),
            "two skills": with_(skill="Leap;Frenzy"),
            "one cast (nothing to re-use)": with_(only=CASTS, value_min="1", value_max="1"),
            "a part cast": with_(only=CASTS, value_min="2.5", value_max="2.5"),
            "a range of casts": with_(only=CASTS, value_min="2", value_max="3"),
            "a range of seconds": with_(only=WINDOW, value_min="1", value_max="2"),
            "no window": with_(only=WINDOW, value_min="0", value_max="0"),
            "a set bonus": with_(pieces="2"),
            "a condition": with_(cond="triggered", cond_arg="3"),
            "an event": with_(fire_on="hit_generator"),
        }
        for name, edits in refused.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    self.render_with(*edits)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemlut-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None), (T("reuseclear"), None)]
        setto = lambda stat, want: (T("setto", SKILL, stat, 0), "%g" % want)  # noqa: E731
        cast = lambda now, want: (T("reuse", 3, 2, now), want)  # noqa: E731  -> "keepOpen opened used token"
        out += clear
        # not worn: the two numbers are the base (0), so a reader asks for no window
        out += [setto(CASTS, 0), setto(WINDOW, 0)]
        out += [(T("wears", OWNER, 0), None), setto(CASTS, 3), setto(WINDOW, 2)]
        # three casts inside the window: the first opens it, the second keeps it, the third closes it and the cooldown stays
        out += clear + [cast(1000, "1 1 1 1"), cast(1500, "1 0 2 1"), cast(1900, "0 0 0 1")]
        # the end is inclusive: the second cast exactly 2000 ms after the first is still in the window
        out += clear + [cast(0, "1 1 1 1"), cast(2000, "1 0 2 1")]
        # one ms past the end it is a new window (the first's end event has not run in this driver)
        out += clear + [cast(0, "1 1 1 1"), cast(2001, "1 1 1 2")]
        # the window's end event closes its own window and no other
        out += clear + [cast(0, "1 1 1 1"), (T("reuseend", 1), "1"), (T("reuseend", 1), "0"), cast(3000, "1 1 1 2"), (T("reuseend", 1), "0"), (T("reuseend", 2), "1")]
        # the last cast closes the window, so its end event finds nothing
        out += clear + [cast(0, "1 1 1 1"), cast(100, "1 0 2 1"), cast(200, "0 0 0 1"), (T("reuseend", 1), "0")]
        # a skill with fewer than two casts or no window has none
        out += clear + [(T("reuse", 1, 2, 0), "0 0 0 0"), (T("reuse", 3, 0, 0), "0 0 0 0"), (T("reuse", 0, 0, 0), "0 0 0 0")]
        # two casts: the second closes it
        out += clear + [(T("reuse", 2, 2, 0), "1 1 1 1"), (T("reuse", 2, 2, 500), "0 0 0 1")]
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
        self.assertGreater(len(want), 20)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(2, len(rows))
        want, _ = self.drive(real, rows, "want")
        row_mutants = {
            "the_casts_row_lost": [r for r in rows if r[4] != CASTS],
            "the_window_row_lost": [r for r in rows if r[4] != WINDOW],
            "four_casts": [r[:5] + (4.0, 4.0) + r[7:] if r[4] == CASTS else r for r in rows],
            "a_longer_window": [r[:5] + (5.0, 5.0) + r[7:] if r[4] == WINDOW else r for r in rows],
            "another_skill": [r[:3] + ("Frenzy",) + r[4:] for r in rows],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {
            "the_end_is_exclusive": real.replace("static_cast<std::int32_t>(state.until - now) < 0", "static_cast<std::int32_t>(state.until - now) <= 0"),
            "the_window_never_ends": real.replace("static_cast<std::int32_t>(state.until - now) < 0", "false"),
            "the_last_cast_leaves_it_open": real.replace("state.used < casts", "state.used <= casts"),
            "a_new_window_keeps_the_old_count": real.replace("state.used = 1;", "state.used += 1;"),
            "the_end_ignores_the_token": real.replace("state.token != token", "false"),
            "one_cast_has_a_window": real.replace("casts < 2 ||", "casts < 1 ||"),
            "no_window_seconds_still_opens": real.replace("windowSeconds <= 0", "windowSeconds < 0"),
        }
        for name, header in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, header, name + " did not apply")
                _, got = self.drive(header, rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
