"""Step 0 checker: the tokenised barbarian sheets plus their values sheets say
exactly what the numbered sheets said, and what d3planner says.

The sheets now carry `{token}` (or `{token:qualifier}`) where a number used to
be, and `barbarian_skill_values.csv` / `barbarian_passive_values.csv` carry the
numbers. Putting the numbers back has to reproduce the old sentence, so every
check the accepted token report ran against d3planner is re-run here on the
reconstructed text -- 331 rows, barbarian rebuilt from tokens and wizard
straight from its untouched sheets.

    python3 mod-diablocraft/scripts/tests/classes/test_skill_values.py

The one-time proof that the split lost nothing is stronger than anything this
file can assert after the fact: rebuilding the three sheets from the tokens and
the values reproduced the pre-step-0 files BYTE for byte. To re-run it, write
`git show <the step 0 commit>~1:mod-diablocraft/data/d3/<sheet>` to a scratch
file and compare it with `SkillValuesTests.rebuilt()`.
"""
import csv
import importlib.util
import io
import pathlib
import re
import subprocess
import shutil
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
MODULE_ROOT = pathlib.Path(__file__).resolve().parents[2].parent
D3 = MODULE_ROOT / "data/d3"
PLACEHOLDER = re.compile(r"\{([a-z_]+)(?::([a-z_]+))?\}")
UNITS = ("pct", "seconds", "minutes", "yards", "count", "resource", "life", "points", "coefficient")
# Approved with the mapping brief on 2026-09-20: the six new names plus the
# share token, none of which the classifier could name from the sentence alone.
APPROVED_EXTRA = {"cc_duration_reduction_pct", "duration_bonus_pct", "pet_life_pct",
                  "radius_share_pct", "resistance_share_pct", "resource_cost_share_pct",
                  "damage_share_pct"}
# Approved with the step 5 cost ruling (Architect, 2026-09-20): Whirlwind's
# channel terms are stated for the module to read and appear in no sentence, so
# they are the one kind of values row with no placeholder. Every other row still
# has to have one, which is what the placeholder check below proves.
# Step 8 adds Inspiring Presence's duration_bonus_pct on the same terms: its
# sentence says "doubled" and the +100 percent behind that word is carried by
# the SPELLMOD_DURATION record, not printed anywhere.
MODULE_READ = {"channel_cost_speed_term_resource", "channel_cost_flat_resource",
               "channel_tick_frames_count", "channel_frames_per_second_count",
               "duration_bonus_pct",
               # diablocraft-proc-coefficients-wiring (the designer, q-0929-11): each skill's and
               # rune's D3 proc coefficient, read by the crit procs; in no sentence.
               "proc_coefficient"}
APPROVED_EXTRA |= MODULE_READ


def load_report():
    spec = importlib.util.spec_from_file_location(
        "skill_tokens_report", MODULE_ROOT / "scripts/skill_tokens_report.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def rows_of(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.reader(handle))


SHEETS = (("barbarian_skills.csv", "full_tooltip_text", "skill_name", None, csv.QUOTE_MINIMAL),
          ("barbarian_runes.csv", "full_rune_text", "skill_name", "rune_name", csv.QUOTE_ALL),
          ("barbarian_passives.csv", "full_text", "passive_name", None, csv.QUOTE_ALL))


def values_for(name):
    """(every row, {key: the rows a sentence prints}).

    The module-read rows are in the sheet and in no sentence, so they are kept
    out of the grouping the placeholder checks and the rebuild use.
    """
    rows = read_csv(D3 / name)
    grouped = {}
    for row in rows:
        if row["token"] in MODULE_READ:
            continue
        grouped.setdefault((row["skill"], row["rune"]), []).append(row)
    return rows, grouped


def substitute(text, values):
    """Put the numbers back, in sentence order, and say what was consumed."""
    used = iter(values)
    missing = []

    def one(match):
        token, qualifier = match.group(1), match.group(2) or ""
        try:
            row = next(used)
        except StopIteration:
            missing.append(("too few values", token))
            return match.group(0)
        if row["token"] != token or row["qualifier"] != qualifier:
            missing.append(("out of order", "%s:%s vs %s:%s" % (token, qualifier,
                                                                row["token"], row["qualifier"])))
        return row["value"] + ("%" if row["unit"] == "pct" else "")

    head, sep, tail = text.partition("Unlocked")
    out = PLACEHOLDER.sub(one, head) + sep + tail
    left = list(used)
    if left:
        missing.append(("unused values", ",".join(r["token"] for r in left)))
    return out, missing


class SkillValuesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = load_report()
        cls.skill_rows, cls.skill_values = values_for("barbarian_skill_values.csv")
        cls.passive_rows, cls.passive_values = values_for("barbarian_passive_values.csv")

    def rebuilt(self):
        """(sheet name, header, rows) with every number put back."""
        out = []
        for name, column, key, rune_column, quoting in SHEETS:
            values = self.passive_values if "passives" in name else self.skill_values
            rows = rows_of(D3 / name)
            header, body = rows[0], rows[1:]
            at, key_at = header.index(column), header.index(key)
            rune_at = header.index(rune_column) if rune_column else None
            for row in body:
                pair = (row[key_at], row[rune_at] if rune_at is not None else "")
                text, problems = substitute(row[at], values.get(pair, []))
                self.assertEqual(problems, [], "%s %s" % (name, pair))
                row[at] = text
            out.append((name, quoting, [header] + body))
        return out

    def test_sheets_carry_tokens_and_no_numbers(self):
        total = 0
        for name, column, key, rune_column, _ in SHEETS:
            for row in read_csv(D3 / name):
                body = row[column].partition("Unlocked")[0]
                self.assertNotRegex(body, r"\d", "%s: %s still has a number" % (name, row[key]))
                total += 1
        self.assertEqual(total, 157, "157 barbarian rows")

    def test_every_placeholder_has_exactly_one_value(self):
        placeholders = 0
        for name, column, key, rune_column, _ in SHEETS:
            values = self.passive_values if "passives" in name else self.skill_values
            for row in read_csv(D3 / name):
                pair = (row[key], row.get(rune_column, "") if rune_column else "")
                found = PLACEHOLDER.findall(row[column].partition("Unlocked")[0])
                self.assertEqual([(t, q) for t, q in found],
                                 [(v["token"], v["qualifier"]) for v in values.get(pair, [])],
                                 "%s %s" % (name, pair))
                placeholders += len(found)
        self.assertEqual(placeholders, 305, "305 barbarian values")
        module_read = [row for row in self.skill_rows + self.passive_rows
                       if row["token"] in MODULE_READ]
        terms = [row for row in module_read if row["token"] != "proc_coefficient"]
        self.assertEqual(len(terms), 5,
                         "Whirlwind's four channel terms and the duration bonus")
        self.assertEqual({row["skill"] for row in terms},
                         {"Whirlwind", "Inspiring Presence"})
        # the proc coefficients are checked skill by skill in test_proc_coefficients.py
        self.assertEqual(len(module_read) - len(terms), 48, "Barbarian proc coefficients")
        for row in module_read:
            self.assertRegex(row["source"], r"^(d3planner |D3 client data)")
            self.assertNotIn("{%s}" % row["token"], row.get("source", ""))
        self.assertEqual(len(self.skill_rows) + len(self.passive_rows), 305 + len(module_read))

    def test_keys_are_unique_and_units_match_the_token(self):
        seen = set()
        for row in self.skill_rows + self.passive_rows:
            key = (row["skill"], row["rune"], row["token"], row["qualifier"])
            self.assertNotIn(key, seen, "repeated key %s" % (key,))
            seen.add(key)
            self.assertTrue(row["token"].endswith("_" + row["unit"]),
                            "%s does not end in %s" % (row["token"], row["unit"]))
            self.assertIn(row["unit"], UNITS)
            self.assertRegex(row["value"], r"^\d+(\.\d+)?$")
            self.assertRegex(row["source"], r"^(d3planner |D3 client data)")
            if row["token"] != "proc_coefficient":
                self.assertTrue(row["source"].startswith("d3planner "), row["source"])

    def test_tokens_are_in_the_accepted_vocabulary(self):
        with open(self.report.DATA, encoding="utf-8") as handle:
            data = self.report.json.load(handle)
        vocabulary = set(APPROVED_EXTRA)
        for value in self.report.collect(data):
            self.report.name(value)
            if value.token:
                vocabulary.add(value.token)
        for row in self.skill_rows + self.passive_rows:
            self.assertIn(row["token"], vocabulary)

    def test_reconstructed_sheets_still_match_d3planner(self):
        """The accepted 331-row check, re-run on the rebuilt barbarian text."""
        report = self.report
        with open(report.DATA, encoding="utf-8") as handle:
            data = report.json.load(handle)
        with tempfile.TemporaryDirectory() as folder:
            staged = pathlib.Path(folder) / "d3"
            shutil.copytree(D3, staged)
            for name, quoting, rows in self.rebuilt():
                out = io.StringIO(newline="")
                csv.writer(out, quoting=quoting, lineterminator="\n").writerows(rows)
                (staged / name).write_text(out.getvalue(), encoding="utf-8")
            original = report.D3
            report.D3 = staged
            try:
                rows = 0
                for cls in ("barbarian", "wizard"):
                    self.assertEqual(report.cross_check(data, cls), [], "%s numbers" % cls)
                    self.assertEqual(report.text_check(data, cls), [], "%s text" % cls)
                    compared, disagreements = report.token_consistency(data, cls)
                    self.assertEqual(disagreements, [], "%s tokens" % cls)
                    sheet_rows = sum(len(read_csv(staged / ("%s_%s.csv" % (cls, part))))
                                     for part in ("skills", "runes", "passives"))
                    self.assertEqual(compared, sheet_rows, "%s rows compared" % cls)
                    rows += sheet_rows
                self.assertEqual(rows, 331, "331 rows checked")
            finally:
                report.D3 = original

    def test_values_still_equal_the_generated_tables(self):
        """The sheets still say what the positional tables said.

        Step 4 deleted those tables, so they are read at the baseline commit
        the whole rewrite is measured against rather than from the working
        tree: what they held is still the number the sheets have to carry.
        """
        checked = 0
        for path, values, pattern in (
                ("mod-diablocraft/src/combat/dc_ability_data.h", self.skill_values,
                 r'\{\d+, "([^"]*)", "([^"]*)", \{([^}]*)\}'),
                ("mod-diablocraft/src/combat/dc_passive_data.h", self.passive_values,
                 r'\{\d+, "([^"]*)()", \{([^}]*)\}')):
            frozen = subprocess.run(["git", "show", "7702de8:" + path], cwd=REPO_ROOT,
                                    capture_output=True)
            if frozen.returncode:
                self.skipTest("the baseline commit is not in this clone")
            for match in re.finditer(pattern, frozen.stdout.decode("utf-8")):
                pair = (match.group(1), match.group(2))
                theirs = [n.strip() for n in match.group(3).split(",") if n.strip()]
                ours = [row["value"] for row in values.get(pair, [])]
                self.assertEqual([float(x) for x in ours], [float(x) for x in theirs],
                                 "%s %s" % (path.rsplit("/", 1)[-1], pair))
                checked += 1
        self.assertEqual(checked, 157, "157 generated rows")


if __name__ == "__main__":
    unittest.main(verbosity=2)
