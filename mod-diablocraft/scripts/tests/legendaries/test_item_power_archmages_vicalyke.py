"""Legendary 016, bead diablocraft-6cw6f: Archmage's Vicalyke (Wizard hat).

  "Your Mirror Images have a chance to multiply when killed by enemies."
  * the words are read from d3planner (item_head.js, leg_archmagesvicalyke, args 0: no number) and the catalogue row; the item is a Wizard
    legendary of the pool. The CHANCE is in no source: it is the tunables row wizard.archmages_vicalyke_multiply_chance_pct, the designer's 50
    (card q-1013-16, diablocraft-e8q7g; blank would read 0 and the power would do nothing), and the table row carries no
    chance of its own (the generator refuses one);
  * the table (data/legendary_powers.csv) holds ONE `effect` row, `multiply_image` 1 (one more Image per fire: the reading as written,
    decisions.md 2026-10-10 (b)), fired on the new event `image_death`; the generator refuses a bad one;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table;
  * the production rules (src/combat/dc_item_power_math.h: Fire, ImageDeathCounts, ImageMultiplies, ImageCopyMs) are compiled and driven
    with the generated rows: the event fires only for the item worn and only on `image_death`, an Image killed by an enemy counts and one
    that nobody killed (or a friend killed) does not, the chance is honoured at both ends (0 never, 100 always, between by the draw), the
    new Image is the owner's own and has the dead one's remaining time (none left: none);
  * mutants fail the same driver and the source-text guards (a chance that is not the tunable, a death that is not a kill, an event that
    anything else fires, an Image outside State.images);
  * source-text guards that the death reaches Fire only through the Image's own JustDied (a despawn at the end of the duration and
    ClearSummons never do), that the executor runs outside the item powers' lock, reads the tunable by the sheet's name and hands the dead
    Image to the Wizard, whose copy is made by the one routine SummonImages uses and is counted in State.images (the C++ is compile-checked
    by syntax_check.sh; the in-game steps are in docs/test-diablocraft-6cw6f.md).
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
import wizard_source  # noqa: E402
import harness_env
import generate_legendary_powers as generator
import generate_tunables

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_vicalyke/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_WizardHat_101_x1"
TUNABLE = ("wizard", "archmages_vicalyke_multiply_chance_pct")
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
WANT_ROW = (OWNER, 0, "effect", "", "multiply_image", 1.0, 1.0, "", 0.0, "", 0.0, 0, "image_death", "", 100.0, 0.0)
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731


def read_csv_path(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def read_csv(name):
    return read_csv_path(MODULE / name)


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


def mutate(source, old, new):
    assert source.count(old) == 1, "mutation target %r is not there exactly once" % old
    return source.replace(old, new)


class Table(unittest.TestCase):
    def test_the_words_are_the_planners_and_the_item_is_a_wizard_legendary(self):
        text = (REPO / "reference/d3planner/item_head.js").read_text(encoding="utf-8")
        start = text.index('id: "%s"' % OWNER)
        item = text[start:text.index("},\n\n", start)]
        self.assertIn('format: "Your Mirror Images have a chance to multiply when killed by enemies.", args: 0', item)
        row = next(r for r in read_csv_path(REPO / "docs/research/legendary-catalogue.csv") if r["d3_id"] == OWNER)
        self.assertEqual("Your Mirror Images have a chance to multiply when killed by enemies.", row["power_text"])
        self.assertEqual("K3", row["kind"])
        base = next(r for r in read_csv("data/d3/base_items.csv") if r["d3_id"] == OWNER)
        self.assertEqual(("Archmage's Vicalyke", "legendary", "wizard", "yes", "no"),
                         (base["d3_name"], base["rarity"], base["designated_class"], base["pool_version"], base["craft_only"]))

    def test_the_mirror_image_the_power_copies_is_the_wizards_own_summon(self):
        skill = next(r for r in read_csv("data/d3/wizard_skills.csv") if r["skill_name"] == "Mirror Image")
        self.assertIn("Summon {pet_count} illusionary duplicates", skill["full_tooltip_text"])
        values = {(r["rune"], r["token"], r["qualifier"]) for r in read_csv("data/d3/wizard_skill_values.csv") if r["skill"] == "Mirror Image"}
        for token in (("", "pet_count", ""), ("", "duration_seconds", "image"), ("", "pet_life_pct", "")):
            self.assertIn(token, values)

    def test_one_effect_row_on_the_new_event(self):
        self.assertEqual([WANT_ROW], mine())

    def test_the_row_carries_no_chance_and_the_tunable_is_a_marked_placeholder(self):
        csv_row = next(r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER)
        self.assertEqual(("", "", ""), (csv_row["chance_pct"], csv_row["icd_seconds"], csv_row["fire_skills"]))
        sheet = [r for r in read_csv("data/tunables/wizard.csv") if r["name"] == TUNABLE[1]]
        self.assertEqual(1, len(sheet))
        tunable = sheet[0]
        # The designer's number (card q-1013-16, diablocraft-e8q7g): no D3 value, the value 50
        self.assertEqual(("", "50", "percent"), (tunable["d3_value"], tunable["value"], tunable["unit"]))
        self.assertIn("q-1013-16", tunable["notes"])
        self.assertIn("the designer", tunable["notes"])
        self.assertIn("diablocraft-6cw6f", tunable["notes"])
        # it reaches the tunables migration with the value and no D3 number
        migration = (MODULE / "data/sql/db-world/updates" / generate_tunables.CURRENT_MIGRATION).read_text(encoding="utf-8")
        self.assertIn("('wizard', 'archmages_vicalyke_multiply_chance_pct', NULL, 50.0, 'percent', ", migration)

    def test_the_generator_refuses_a_bad_row(self):
        base = next(r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER)
        refused = {
            "the effect on another event": dict(base, fire_on="kill"),
            "a chance of its own in the row": dict(base, chance_pct="50"),
            "an internal cooldown": dict(base, icd_seconds="3"),
            "more than one Image": dict(base, value_min="2", value_max="2"),
            "a range": dict(base, value_min="1", value_max="2"),
            "a skill": dict(base, skill="Mirror Image"),
            "fire_skills on the death": dict(base, fire_skills="Mirror Image"),
            "another effect on the death": dict(base, stat="resource_refund"),
            "a condition": dict(base, cond="triggered", cond_arg="3"),
        }
        for name, row in refused.items():
            with self.subTest(name), self.assertRaises(ValueError):
                self.rows_of([row])
        self.assertEqual(1, len(self.rows_of([base])))

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
        work = Path(tempfile.mkdtemp(prefix="itemvical-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the item's words, not from the code."""
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        # the event fires the effect only for the worn item, as many times as Images die (no internal cooldown), whatever the draw
        out += clear + [(T("now", 1000), None), (T("fire", "image_death", 0), "")]                 # not worn: nothing
        out += clear + [(T("now", 1000), None), (T("wears", "Unique_Gloves_003_x1", 0), None), (T("fire", "image_death", 0), "")]   # another item
        out += clear + [(T("now", 1000), None), (T("wears", OWNER, 0), None)]
        for draw in (0, 50, 99.99, 100):
            out += [(T("fire", "image_death", draw), "multiply_image=1;")]
        out += [(T("now", 1001), None), (T("fire", "image_death", 0), "multiply_image=1;")]       # a second death a millisecond later: again
        # no other event fires it: a kill, a hit, a cast, a hit taken, a kill of an elite
        for event in ("kill", "kill_elite", "taken", "cast", "hit", "hit_spender", "hit_generator", "image", "death", ""):
            out += [(T("fire", event, 0), "")]
        # a death counts when something killed the Image and it was an enemy of its owner
        out += [(T("killed", 1, 1), "1"), (T("killed", 1, 0), "0"), (T("killed", 0, 1), "0"), (T("killed", 0, 0), "0")]
        # the chance is a tunable's number: 0 never, 100 always, between by the draw (a draw below the percent falls)
        for draw in (-1, 0, 25, 50, 99.99, 100):
            out += [(T("multiplies", 0, draw), "0"), (T("multiplies", -5, draw), "0"), (T("multiplies", 100, draw), "1"), (T("multiplies", 250, draw), "1")]
        out += [(T("multiplies", 50, 49.99), "1"), (T("multiplies", 50, 50), "0"), (T("multiplies", 0.5, 0.49), "1"), (T("multiplies", 0.5, 0.5), "0"),
                (T("multiplies", 99, 98.9), "1"), (T("multiplies", 99, 99), "0")]
        # the copy: the owner's own Image only, with the dead one's remaining milliseconds, none when none are left
        out += [(T("copy", 1, 7000), "7000"), (T("copy", 1, 1), "1"), (T("copy", 1, 0), "0"), (T("copy", 0, 7000), "0"), (T("copy", 0, 0), "0")]
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

    def test_every_rule_agrees_with_the_item(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(want), 50)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        row_mutants = {
            "the_wrong_event": [r[:12] + ("kill",) + r[13:] for r in rows],
            "the_wrong_effect": [r[:4] + ("resource_refund",) + r[5:] for r in rows],
            "a_chance_in_the_row": [r[:14] + (50.0,) + r[15:] for r in rows],
            "an_internal_cooldown": [r[:15] + (3.0,) + r[16:] for r in rows],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {
            "a_death_nobody_caused_counts": mutate(real, "return killerKnown && killerHostileToOwner;", "return killerHostileToOwner;"),
            "a_friends_kill_counts": mutate(real, "return killerKnown && killerHostileToOwner;", "return killerKnown;"),
            "a_certain_chance_still_rolls": mutate(real, "(chancePct >= 100 || roll(chancePct))", "roll(chancePct)"),
            "a_zero_chance_rolls": mutate(real, "chancePct > 0 && (chancePct >= 100 || roll(chancePct))", "(chancePct >= 100 || roll(chancePct))"),
            "a_chance_of_100_is_not_certain": mutate(real, "chancePct >= 100 ||", "chancePct > 100 ||"),
            "the_roll_is_inverted": mutate(real, "|| roll(chancePct));", "|| !roll(chancePct));"),
            "another_players_image_is_copied": mutate(real, "return own ? remainingMs : 0;", "return remainingMs;"),
            "the_copy_has_a_fresh_time": mutate(real, "return own ? remainingMs : 0;", "return own ? 7000 : 0;"),
            "a_dead_event_fires_for_anything": mutate(real, "if (row.fireOn != fireOn || !Owned(row, counts, situation, number))", "if (!Owned(row, counts, situation, number))"),
        }
        for name, header in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, header, name + " did not apply")
                want, got = self.drive(header, rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
