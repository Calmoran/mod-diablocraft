"""K2+B5 - Paragon stat identities are published cells, not a list position.

`dc_character_paragon.stat` stores the stat ID, so that ID is what a saved
allocation MEANS. It used to come from `enumerate(STATS, 1)` over a list in
`generate_paragon.py`: reordering that list, or inserting a stat, would have
silently re-pointed every point every player had ever spent. The per-point
value, the cap and the unit were likewise read out of an English sentence by
regex, and the party XP rule out of another one.

The sheet carries all of it explicitly now. These tests are the two halves of
that: the numbers are exactly what the old parser produced, and the ways of
breaking the pairing are rejected - including the one contiguity cannot see.
"""
import contextlib
import csv
import io
import pathlib
import re
import shutil
import sys
import tempfile
import unittest
from decimal import Decimal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_paragon as gp
import generate_sql as gs

D3 = gp.ROOT / "data" / "d3"
PARAGON = D3 / "paragon.csv"
MONSTER_XP = D3 / "monster_xp.csv"
CPP = (gp.ROOT / "src" / "paragon" / "dc_paragon.cpp").read_text(encoding="utf-8")
GENERATED = gp.ROOT / "data" / "generated"
APPLIED_REFERENCE = gp.ROOT / "data" / "sql" / "db-world" / "updates" / "0001_dc_paragon.sql"

# The pre-change behaviour, frozen here as the oracle the acceptance names:
# the order of this list WAS the ID, and these regexes WERE the values. This
# copy is test-only evidence and is deliberately NOT importable from the
# generator, so no production path can grow a dependency on prose again.
FROZEN_STATS = [
    ('primary', 'Primary stat (Strength/Dexterity/Intelligence by class)'),
    ('vitality', 'Vitality'), ('movement', 'Movement Speed'),
    ('resource', 'Class max resource — Spirit / Fury / Essence'),
    ('ias', 'Attack Speed'), ('cdr', 'Cooldown Reduction'),
    ('chc', 'Critical Hit Chance'), ('chd', 'Critical Hit Damage'),
    ('armor', 'Armor %'), ('life', 'Life %'), ('resistance', 'All Resistances'),
    ('regen', 'Life Regeneration'), ('area', 'Area Damage'),
    ('rcr', 'Resource Cost Reduction'), ('loh', 'Life per Hit'),
    ('pickup', 'Gold Pickup Range')]


PUBLISHED_RULES = gp.ROOT / "data" / "sql" / "db-world" / "updates" / "paragon_0001_rules.sql"


def publish(root):
    """Give a temp tree the applied pairing the generator checks against."""
    updates = root / "data" / "sql" / "db-world" / "updates"
    updates.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PUBLISHED_RULES, updates / "paragon_0001_rules.sql")
    # Explicit, deliberately empty authority; the guard fails closed without it.
    (root / "data" / "sql" / "applied_migrations.csv").write_text(
        "path,sha1,provenance\n", encoding="utf-8")
    return updates / "paragon_0001_rules.sql"


def rows_of(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def frozen_parser():
    """What generate_paragon.py produced before the cells existed."""
    source = {row["stat"]: row for row in rows_of(PARAGON)}
    produced = []
    for index, (key, name) in enumerate(FROZEN_STATS, 1):
        row = source[name]
        match = re.match(r'^\+([0-9]+(?:\.[0-9]+)?)(.*)$', row["effect_per_point"])
        value = Decimal(match[1])
        cap = 0 if row["max_rank"] == "UNCAPPED" else int(re.match(r'^([0-9]+)', row["max_rank"])[1])
        unit = "%" if match[2].startswith("%") else "yards" if "yards" in match[2] else ""
        produced.append((index, key, name, (index - 1) // 4, str(value), cap, unit))
    return produced


class FrozenBaseline(unittest.TestCase):
    """One-time evidence: the cells are exactly what the old parser produced.

    This is where the old-parser comparison belongs and the only place it
    exists. The parser below is a FROZEN copy of the pre-change behaviour kept
    for this proof; nothing in the generation path parses prose any more, so
    rewording a sentence cannot fail this or anything else. It is a baseline
    against today's data, not a rule the sheet has to keep satisfying: if a
    per-point value is ever deliberately retuned, this comparison is expected
    to be updated with it rather than to hold forever.
    """

    def test_every_rule_matches_what_the_old_parser_produced(self):
        self.assertEqual(gp.paragon_rules(gp.ROOT), frozen_parser())

    def test_the_per_point_strings_are_identical_not_merely_equal_in_value(self):
        # '0.50' and '0.5' are the same number and different SQL. The stored
        # rule text is what the runtime reads back, so the string has to match.
        produced = {row[1]: row[4] for row in gp.paragon_rules(gp.ROOT)}
        self.assertEqual(produced["movement"], "0.50")
        for identity, key, name, category, value, cap, unit in frozen_parser():
            self.assertEqual(produced[key], value, key)

    def test_the_party_rule_matches_the_sentence_it_replaced(self):
        row = next(r for r in rows_of(MONSTER_XP) if r["rule/level"] == "party_xp_bonus")
        said = re.fullmatch(
            r'\+([0-9]+)% per additional player; max \+([0-9]+)% with ([0-9]+) players',
            row["value"]).groups()
        self.assertEqual(gp.party_rule(gp.ROOT), tuple(int(group) for group in said))
        self.assertEqual(gp.party_rule(gp.ROOT), (10, 30, 4))


class Preservation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        shutil.copytree(D3, self.root / "data" / "d3")
        shutil.copytree(gp.ROOT / "data" / "tunables", self.root / "data" / "tunables")
        publish(self.root)

    def generated(self, name):
        import contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            gp.generate(self.root)
        return (self.root / "data" / "generated" / name).read_bytes()

    def test_the_rules_migration_is_byte_identical(self):
        # This is the file the saved allocations depend on: id, key and value.
        self.assertEqual(self.generated("paragon_0001_rules.sql"),
                         (GENERATED / "paragon_0001_rules.sql").read_bytes())

    def test_the_pools_migration_is_byte_identical(self):
        self.assertEqual(self.generated("paragon_0001_pools.sql"),
                         (GENERATED / "paragon_0001_pools.sql").read_bytes())

    def test_the_reference_table_and_its_applied_migration_do_not_move(self):
        # The new cells are deliberately not published in dc_paragon: nothing
        # queries it, and publishing them would rewrite an applied migration.
        sql, count = gs.render_table(PARAGON, gs.TABLES["paragon"])
        self.assertEqual(count, len(rows_of(PARAGON)))
        self.assertEqual(sql.encode("utf-8"), APPLIED_REFERENCE.read_bytes())
        declared = [line.strip() for line in sql.splitlines() if line.startswith("  `")]
        self.assertEqual(declared, ["`category` LONGTEXT NOT NULL,", "`stat` LONGTEXT NOT NULL,",
                                    "`points_per_rank` LONGTEXT NOT NULL,",
                                    "`effect_per_point` LONGTEXT NOT NULL,",
                                    "`max_rank` LONGTEXT NOT NULL,", "`notes` LONGTEXT NOT NULL"])


class Sheet(unittest.TestCase):
    def test_sixteen_stats_carry_ids_and_the_rest_carry_none(self):
        rows = rows_of(PARAGON)
        owned = [row for row in rows if row["stat_id"].strip()]
        self.assertEqual(len(owned), 16)
        # The D3 sheet also lists resources other classes use, and two prose
        # rows about the allocation rule. Those are reference, not ours.
        for row in rows:
            if row not in owned:
                for column in ("stat_key", "stat_id", "category_id", "per_point", "point_cap"):
                    self.assertEqual(row[column], "", row["stat"])

    def test_ids_are_unique_contiguous_and_grouped_four_by_four(self):
        rows = gp.paragon_rules(gp.ROOT)
        self.assertEqual([row[0] for row in rows], list(range(1, 17)))
        self.assertEqual(len({row[1] for row in rows}), 16)
        for identity, key, name, category, *_ in rows:
            self.assertEqual(category, (identity - 1) // 4, key)

    def test_the_binary_and_the_sheet_agree_on_every_pairing(self):
        # Two independent witnesses. If this fails, one of them was edited
        # alone, which is exactly the drift the ID contract exists to stop.
        compiled = dict((key, int(identity)) for key, identity in
                        re.findall(r'\{"([a-z]+)",\{(\d+),Stat::', CPP))
        self.assertEqual(len(compiled), 16)
        self.assertEqual(compiled, {row[1]: row[0] for row in gp.paragon_rules(gp.ROOT)})

    def test_the_runtime_refuses_a_broken_pairing_and_says_why(self):
        self.assertIn("Need(rule.id == found->second.id,", CPP)
        self.assertIn("saved allocations would change meaning", CPP)


class ProseIsDisplayOnly(unittest.TestCase):
    """Rewording a label or a sentence must never block generation.

    This is the contract the brief states and the first version of this task
    broke: `prose_agrees` regexed `effect_per_point` and `max_rank`, the party
    rule exact-matched an English sentence, and `category_id` was compared to
    the `category` label as a string. Measured against that version, a reworded
    category label, a per-point sentence that dropped its plus sign, a cap
    written in words and a differently phrased unit all refused to generate -
    and the cap case raised an uncaught TypeError rather than an error anyone
    could act on. The authoritative IDs and cells were unchanged throughout.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        shutil.copytree(D3, self.root / "data" / "d3")
        shutil.copytree(gp.ROOT / "data" / "tunables", self.root / "data" / "tunables")
        publish(self.root)
        self.paragon = self.root / "data" / "d3" / "paragon.csv"
        self.monster = self.root / "data" / "d3" / "monster_xp.csv"

    def edit(self, path, before, after):
        text = path.read_text(encoding="utf-8-sig")
        self.assertIn(before, text, "the fixture no longer contains the text to edit")
        path.write_text(text.replace(before, after, 1), encoding="utf-8")

    def gameplay(self):
        """Everything a rule means, minus the display name."""
        return [(row[0], row[1]) + tuple(row[3:]) for row in gp.paragon_rules(self.root)]

    def test_a_reworded_category_label_changes_nothing(self):
        expected = self.gameplay()
        self.edit(self.paragon, "Offensive,Attack Speed", "Offense,Attack Speed")
        self.assertEqual(self.gameplay(), expected)

    def test_a_reworded_per_point_sentence_changes_nothing(self):
        expected = self.gameplay()
        self.edit(self.paragon, "+0.2%,50 (cap +10%)", "0.2% per point,50 (cap +10%)")
        self.assertEqual(self.gameplay(), expected)

    def test_a_cap_written_in_words_changes_nothing(self):
        # This one used to raise TypeError, not even a usable error.
        expected = self.gameplay()
        self.edit(self.paragon, '"50 (cap +8,045)"', '"fifty (cap +8,045)"')
        self.assertEqual(self.gameplay(), expected)

    def test_a_differently_phrased_unit_changes_nothing(self):
        expected = self.gameplay()
        self.edit(self.paragon, "+0.1 yards", "+0.1 yds")
        self.assertEqual(self.gameplay(), expected)
        self.assertEqual(dict((row[1], row[6]) for row in gp.paragon_rules(self.root))["pickup"],
                         "yards")

    def test_a_reworded_party_sentence_changes_nothing(self):
        self.edit(self.monster, "max +30% with 4 players", "capped at +30% in a 4-player party")
        self.assertEqual(gp.party_rule(self.root), (10, 30, 4))

    def test_a_renamed_stat_keeps_its_rule_and_only_moves_the_display_name(self):
        # The display name IS carried into dc_paragon_rules by design, so the
        # label may move there - the rule behind it may not.
        expected = self.gameplay()
        self.edit(self.paragon, "Critical Hit Damage", "Crit Damage")
        self.assertEqual(self.gameplay(), expected)
        names = {row[1]: row[2] for row in gp.paragon_rules(self.root)}
        self.assertEqual(names["chd"], "Crit Damage")

    def test_every_cosmetic_edit_at_once_still_generates_the_same_rules(self):
        expected = self.gameplay()
        self.edit(self.paragon, "Offensive,Attack Speed", "Offense,Attack Speed")
        self.edit(self.paragon, "+0.2%,50 (cap +10%)", "0.2% per point,50 (cap +10%)")
        self.edit(self.paragon, '"50 (cap +8,045)"', '"fifty (cap +8,045)"')
        self.edit(self.paragon, "+0.1 yards", "+0.1 yds")
        self.edit(self.monster, "max +30% with 4 players", "capped at +30% in a 4-player party")
        self.assertEqual(self.gameplay(), expected)
        self.assertEqual(gp.party_rule(self.root), (10, 30, 4))


class CellsDriveTheOutput(unittest.TestCase):
    """The other half: the cells, and only the cells, decide what is generated."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        shutil.copytree(D3, self.root / "data" / "d3")
        shutil.copytree(gp.ROOT / "data" / "tunables", self.root / "data" / "tunables")
        publish(self.root)
        self.paragon = self.root / "data" / "d3" / "paragon.csv"
        self.monster = self.root / "data" / "d3" / "monster_xp.csv"

    def set_cell(self, path, key_column, key, column, value):
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream)
            header, body = next(reader), list(reader)
        next(row for row in body if row[header.index(key_column)] == key)[
            header.index(column)] = value
        out = io.StringIO(newline="")
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(body)
        path.write_text(out.getvalue(), encoding="utf-8")

    def test_changing_a_per_point_cell_changes_that_rule_and_no_other(self):
        before = {row[1]: row for row in gp.paragon_rules(self.root)}
        self.set_cell(self.paragon, "stat_key", "chd", "per_point", "1.5")
        after = {row[1]: row for row in gp.paragon_rules(self.root)}
        self.assertEqual(after["chd"][4], "1.5")
        self.assertNotEqual(after["chd"], before["chd"])
        for key in before:
            if key != "chd":
                self.assertEqual(after[key], before[key], key)

    def test_the_new_value_reaches_the_generated_rule_row(self):
        import contextlib
        self.set_cell(self.paragon, "stat_key", "chd", "per_point", "1.5")
        with contextlib.redirect_stdout(io.StringIO()):
            gp.generate(self.root)
        sql = (self.root / "data/generated/paragon_0001_rules.sql").read_text(encoding="utf-8")
        self.assertIn("'8','chd','Critical Hit Damage','1','1.5','50','%'", sql)
        self.assertNotEqual(sql.encode("utf-8"),
                            (GENERATED / "paragon_0001_rules.sql").read_bytes())

    def test_changing_a_cap_cell_changes_only_that_cap(self):
        before = {row[1]: row for row in gp.paragon_rules(self.root)}
        self.set_cell(self.paragon, "stat_key", "chd", "point_cap", "40")
        after = {row[1]: row for row in gp.paragon_rules(self.root)}
        self.assertEqual(after["chd"][5], 40)
        self.assertEqual({k: v for k, v in after.items() if k != "chd"},
                         {k: v for k, v in before.items() if k != "chd"})

    def test_changing_the_party_cells_changes_the_party_rule(self):
        self.set_cell(self.monster, "rule/level", "party_xp_bonus", "party_per_member_pct", "20")
        self.set_cell(self.monster, "rule/level", "party_xp_bonus", "party_bonus_cap_pct", "60")
        self.assertEqual(gp.party_rule(self.root), (20, 60, 4))


class Rejections(unittest.TestCase):
    """Each one a real way to move a saved allocation."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        shutil.copytree(D3, self.root / "data" / "d3")
        shutil.copytree(gp.ROOT / "data" / "tunables", self.root / "data" / "tunables")
        publish(self.root)
        self.paragon = self.root / "data" / "d3" / "paragon.csv"
        self.monster = self.root / "data" / "d3" / "monster_xp.csv"

    def rewrite(self, path, change):
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream)
            header, body = next(reader), list(reader)
        change(header, body)
        out = io.StringIO(newline="")
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(body)
        path.write_text(out.getvalue(), encoding="utf-8")

    def row_for(self, header, body, key):
        return next(row for row in body if row[header.index("stat_key")] == key)

    def test_the_fixture_passes_before_anything_is_broken(self):
        self.assertEqual(gp.paragon_rules(self.root), frozen_parser())

    def test_two_keys_swapping_ids_is_rejected(self):
        # The case contiguity CANNOT see: the IDs still run 1..16, the
        # categories still match, and every point ever spent changes meaning.
        def swap(header, body):
            column = header.index("stat_id")
            first, second = self.row_for(header, body, "chc"), self.row_for(header, body, "chd")
            first[column], second[column] = second[column], first[column]
        self.rewrite(self.paragon, swap)
        with self.assertRaisesRegex(ValueError, "keeps its key or every saved allocation"):
            gp.paragon_rules(self.root)

    def test_a_swap_across_categories_is_rejected_too(self):
        def swap(header, body):
            column = header.index("stat_id")
            first, second = self.row_for(header, body, "chc"), self.row_for(header, body, "armor")
            first[column], second[column] = second[column], first[column]
        self.rewrite(self.paragon, swap)
        with self.assertRaises(ValueError):
            gp.paragon_rules(self.root)

    def test_a_missing_published_pairing_fails_rather_than_passing(self):
        (self.root / "data/sql/db-world/updates/paragon_0001_rules.sql").unlink()
        with self.assertRaisesRegex(ValueError, "published paragon rules migration is missing"):
            gp.paragon_rules(self.root)

    def test_an_unparseable_published_pairing_fails(self):
        published = self.root / "data/sql/db-world/updates/paragon_0001_rules.sql"
        published.write_text("-- lost in a bad merge\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "no published paragon rules could be parsed"):
            gp.paragon_rules(self.root)

    def test_a_half_parsed_published_pairing_fails(self):
        published = self.root / "data/sql/db-world/updates/paragon_0001_rules.sql"
        lines = published.read_text(encoding="utf-8").splitlines(True)
        broken = [line.replace("VALUES ('", "VALUES (") if
                  line.startswith("INSERT INTO dc_paragon_rules") and index % 2 else line
                  for index, line in enumerate(lines)]
        published.write_text("".join(broken), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, r"parsed \d+ of \d+ published rules"):
            gp.paragon_rules(self.root)

    def test_a_missing_id_is_rejected(self):
        self.rewrite(self.paragon, lambda header, body:
                     self.row_for(header, body, "regen").__setitem__(header.index("stat_id"), ""))
        with self.assertRaisesRegex(ValueError, "was published as 'regen' and is gone"):
            gp.paragon_rules(self.root)

    def test_a_duplicate_id_is_rejected(self):
        self.rewrite(self.paragon, lambda header, body:
                     self.row_for(header, body, "regen").__setitem__(header.index("stat_id"), "11"))
        with self.assertRaisesRegex(ValueError, "stat_id 11 is used by both"):
            gp.paragon_rules(self.root)

    def test_a_duplicate_key_is_rejected(self):
        self.rewrite(self.paragon, lambda header, body:
                     self.row_for(header, body, "regen").__setitem__(header.index("stat_key"), "area"))
        with self.assertRaisesRegex(ValueError, "stat_key 'area' is used by both"):
            gp.paragon_rules(self.root)

    def test_a_gap_in_the_ids_is_rejected(self):
        # The storage reads the ID back as an array index, so a hole is fatal.
        # The published pairing sees this one first and says so more precisely
        # than the contiguity rule would; both are kept, because an append that
        # left a hole above the published range would only trip contiguity.
        self.rewrite(self.paragon, lambda header, body:
                     self.row_for(header, body, "pickup").__setitem__(header.index("stat_id"), "17"))
        with self.assertRaisesRegex(ValueError, "was published as 'pickup' and is gone"):
            gp.paragon_rules(self.root)

    def test_a_hole_above_the_published_range_still_trips_contiguity(self):
        # Both the sheet and the published pairing gain the same new stat, so
        # only the array-index rule objects to the hole it leaves.
        def append(header, body):
            row = list(self.row_for(header, body, "pickup"))
            for column, value in (("stat_key", "spare"), ("stat_id", "18"), ("category_id", "3")):
                row[header.index(column)] = value
            body.append(row)
        self.rewrite(self.paragon, append)
        published = self.root / "data/sql/db-world/updates/paragon_0001_rules.sql"
        published.write_text(published.read_text(encoding="utf-8")
                             + "INSERT INTO dc_paragon_rules VALUES ('18','spare');\n",
                             encoding="utf-8")
        with self.assertRaisesRegex(ValueError, r"stat_id must run 1\.\.17"):
            gp.paragon_rules(self.root)

    # --- numeric domains, checked on the cells and not on anybody's wording ---

    def test_a_per_point_cell_that_is_not_a_number_is_rejected(self):
        self.rewrite(self.paragon, lambda header, body:
                     self.row_for(header, body, "chd").__setitem__(header.index("per_point"), "lots"))
        with self.assertRaisesRegex(ValueError, "per_point must be a number"):
            gp.paragon_rules(self.root)

    def test_a_per_point_cell_of_zero_is_rejected(self):
        self.rewrite(self.paragon, lambda header, body:
                     self.row_for(header, body, "chd").__setitem__(header.index("per_point"), "0"))
        with self.assertRaisesRegex(ValueError, "per_point must be positive"):
            gp.paragon_rules(self.root)

    def test_an_empty_required_cell_is_rejected(self):
        self.rewrite(self.paragon, lambda header, body:
                     self.row_for(header, body, "area").__setitem__(header.index("per_point"), ""))
        with self.assertRaisesRegex(ValueError, "per_point is empty"):
            gp.paragon_rules(self.root)

    def test_a_unit_outside_the_known_set_is_rejected(self):
        self.rewrite(self.paragon, lambda header, body:
                     self.row_for(header, body, "pickup").__setitem__(header.index("unit"), "metres"))
        with self.assertRaisesRegex(ValueError, "unit must be one of"):
            gp.paragon_rules(self.root)

    def test_a_category_id_outside_the_four_is_rejected(self):
        self.rewrite(self.paragon, lambda header, body:
                     self.row_for(header, body, "chc").__setitem__(header.index("category_id"), "9"))
        with self.assertRaisesRegex(ValueError, r"category_id 9 is not one of 0\.\.3"):
            gp.paragon_rules(self.root)

    def test_a_category_id_that_does_not_match_its_stat_id_is_rejected(self):
        # Structural, from the ID itself: four categories of four, in order.
        self.rewrite(self.paragon, lambda header, body:
                     self.row_for(header, body, "chc").__setitem__(header.index("category_id"), "2"))
        with self.assertRaisesRegex(ValueError, "belongs to category 1, not 2"):
            gp.paragon_rules(self.root)

    def test_a_stat_key_that_is_not_an_identifier_is_rejected(self):
        self.rewrite(self.paragon, lambda header, body:
                     self.row_for(header, body, "chc").__setitem__(header.index("stat_key"),
                                                                   "Crit Chance"))
        with self.assertRaisesRegex(ValueError, "is not a lower-case identifier"):
            gp.paragon_rules(self.root)

    def test_party_cells_that_do_not_add_up_are_rejected(self):
        # Arithmetic on the numbers, not a match against the sentence.
        self.rewrite(self.monster, lambda header, body:
                     next(row for row in body if row[0] == "party_xp_bonus").__setitem__(
                         header.index("party_bonus_cap_pct"), "40"))
        with self.assertRaisesRegex(ValueError, "is 30%, not the 40% cap"):
            gp.party_rule(self.root)

    def test_missing_party_cells_are_rejected(self):
        self.rewrite(self.monster, lambda header, body:
                     next(row for row in body if row[0] == "party_xp_bonus").__setitem__(
                         header.index("party_max_members"), ""))
        with self.assertRaisesRegex(ValueError, "party XP cells are missing"):
            gp.party_rule(self.root)


def full_fixture(root):
    """Everything generate() reads, not only data/d3.

    It also needs data/tunables (base_monster_xp) and the applied
    paragon_0001_rules.sql, which is the published stat_id-to-stat_key pairing
    the generator refuses to run without. Copying only data/d3 used to fail
    with FileNotFoundError before either assertion below was reached."""
    shutil.copytree(D3,root/'data/d3')
    shutil.copytree(gp.ROOT/'data/tunables',root/'data/tunables')
    updates=root/'data/sql/db-world/updates'
    updates.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(gp.ROOT/'data/sql/db-world/updates/paragon_0001_rules.sql',
                    updates/'paragon_0001_rules.sql')
    # Explicit, deliberately empty authority; the guard fails closed without it.
    (root/'data/sql/applied_migrations.csv').write_text('path,sha1,provenance\n',encoding='utf-8')


class Generation(unittest.TestCase):
    """What `generate` writes into a clean tree: five files, the same twice, the committed ones, and nothing when a party cell is broken."""

    def test_generated_migrations_are_reproducible_and_preserve_pools(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder)
            full_fixture(root)
            with contextlib.redirect_stdout(io.StringIO()): gp.generate(root)
            snapshot={p.relative_to(root):p.read_bytes() for p in root.rglob('*.sql')}
            self.assertEqual(len(snapshot),5)
            with contextlib.redirect_stdout(io.StringIO()): gp.generate(root)
            self.assertEqual(snapshot,{p.relative_to(root):p.read_bytes() for p in root.rglob('*.sql')})
            for path,data in snapshot.items(): self.assertEqual((gp.ROOT/path).read_bytes(),data)
            pool=snapshot[pathlib.Path('data/generated/paragon_0001_pools.sql')].decode()
            self.assertIn('xp BIGINT UNSIGNED',pool)
            self.assertIn('PRIMARY KEY(account_id,pool)',pool)
            self.assertNotIn('DROP',pool);self.assertNotIn('DELETE',pool)
            world=snapshot[pathlib.Path('data/generated/paragon_0001_rules.sql')].decode()
            self.assertEqual(world.count('INSERT INTO dc_paragon_rules VALUES'),16)
            self.assertIn("'chc','Critical Hit Chance','1','0.2','50','%'",world)
            self.assertIn("'primary','Primary stat",world)
            self.assertIn('VALUES (1,1000,3000,4)',world)
            self.assertIn('base_monster_xp=72000',world)

    def test_missing_or_changed_party_data_refuses_generation(self):
        # The party rule lives in cells now, so this breaks the CELLS. Editing
        # the English sentence is a display change and deliberately generates
        # unchanged - test_paragon_ids.ProseIsDisplayOnly covers that side.
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder);full_fixture(root)
            path=root/'data/d3/monster_xp.csv'
            path.write_text(path.read_text(encoding='utf-8-sig').replace(',10,30,4',',10,40,4'),encoding='utf-8')
            with self.assertRaises(ValueError): gp.generate(root)
            self.assertFalse((root/'data/generated').exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
