"""diablocraft-qulab (Crusader 2a): every Crusader skill, rune and passive has its record, its tooltip and its place in the picker.

The Necromancer's spec in test_class_records.py, for the Crusader's block 85400-85599 (generate_spells.py CLASS_BLOCKS, family 24):

  * **A record per sheet row.** crusader_skills.csv (24), crusader_runes.csv (120) and crusader_passives.csv (18) each
    have exactly one record in the manifest (spell_shells.csv), inside the block; no other class's record sits there.
  * **The record is the sheet.** Read back from spell_shells.sql: the name, the family 24, a skill's cooldown in
    RecoveryTime and its Wrath cost in Energy units (PowerType 3, ManaCost = Wrath x the sheet's storage_scale), and a
    tooltip that is non-empty, has no unfilled "{token}" or "NEW:" and carries a "$" variable where the sheet's sentence
    has placeholders.
  * **The PM's rulings on the generator's stops.** Heaven's Fury - Fires of Heaven costs 40 Wrath and has no cooldown
    and no shared category (its parent's timer does not reach it); Blessed Shield and its runes keep D3's ricochet in
    chain slot 1 (3 more enemies, field 4) and nothing on the donor's other slots, and Piercing Shield's slot 1 is 1
    (it no longer bounces); Justice and Bombardment carry their marked placeholder ranges, Phalanx its sourced width.
  * **The numbers are the sheet's.** Every row of the two values sheets has its value map row.
  * **The picker.** The class catalogue lists the Crusader as playable, its 24 skills and 120 runes in the six
    categories of class_skill_categories.csv at the sheets' unlock levels, and its 18 passives.
  * **The client class row.** ChrClasses.dbc row 2 (the Paladin's slot) carries the records' family 24, since the
    client applies a spell modifier only inside the class's own SpellClassSet; the server row keeps the stock 10 for
    the stock-spell strip.
  * **Nothing else moved.** Every manifest row outside the class blocks is unchanged against the fork point with nightly.
  * **A planted difference is seen**: a record dropped, renamed, moved out of the block, a cost off by ten, a leftover
    token, a cooldown left on Fires of Heaven, a donor chain left on Blessed Shield.

What it does not prove: the icons and tooltips as the client draws them (the test sheet's Checks), or that a cast does
anything: casts land with no effect until the skill beads.

    python mod-diablocraft/scripts/tests/classes/test_crusader_records.py
"""

import csv
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
GENERATED = MODULE / "data" / "generated"
sys.path.insert(0, str(MODULE / "scripts"))

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_class_catalogue as gcc  # noqa: E402
import generate_spells  # noqa: E402
from test_class_records import read, split_values  # noqa: E402

FIRST, LAST = 85400, 85599
FAMILY = 24
STOCK_FAMILY = 10
CLASS_ID = 2
ENERGY = 3


def sheet(name):
    return read(D3 / name)


def manifest():
    return read(GENERATED / "spell_shells.csv")


def records():
    """{spell id: {column: value}} of the Crusader's block, from the SQL the generator wrote."""
    text = (GENERATED / "spell_shells.sql").read_text(encoding="utf-8")
    out = {}
    for insert in text.split("INSERT INTO `spell_dbc`")[1:]:
        header, _, body = insert.partition("VALUES")
        columns = re.findall(r"`(\w+)`", header)
        for line in body.splitlines():
            match = re.match(r"^\((\d+),(.*)\)[,;]$", line)
            if match and FIRST <= int(match.group(1)) <= LAST:
                out[int(match.group(1))] = dict(zip(columns, split_values(match.group(1) + "," + match.group(2))))
    return out


def arrival():
    """The commit that added combat_0088 (the Crusader's records) and its first parent, or None without that history."""
    path = "mod-diablocraft/data/sql/db-world/updates/combat_0088_crusader_records.sql"
    found = subprocess.run(["git", "log", "--diff-filter=A", "--format=%H", "--", path], cwd=REPO, capture_output=True,
                           text=True)
    commits = found.stdout.split()
    if found.returncode != 0 or not commits:
        return None
    return commits[-1] + "^", commits[-1]


def at_arrival(name):
    """(text before, text after) of data/generated/<name> across the arrival of the Crusader's records."""
    ends = arrival()
    if not ends:
        raise unittest.SkipTest("no history to compare with")
    texts = []
    for ref in ends:
        shown = subprocess.run(["git", "show", ref + ":mod-diablocraft/data/generated/" + name], cwd=REPO,
                               capture_output=True, text=True)
        if shown.returncode != 0:
            raise unittest.SkipTest("no history to compare with")
        texts.append(shown.stdout)
    return texts[0], texts[1]


def moved_outside_the_blocks(old_rows, new_rows):
    """What the arrival did wrong: a row that existed before and changed or went, a row added outside every class block,
    or one added to another class's block."""
    old = {r["spell_id"]: r for r in old_rows}
    new = {r["spell_id"]: r for r in new_rows}
    blocks = [r for block in generate_spells.CLASS_BLOCKS.values() for r in (block.records, block.helpers)]
    mine = generate_spells.CLASS_BLOCKS["crusader"]
    problems = [("changed", k) for k in old if old[k] != new.get(k)]
    for k in sorted(int(i) for i in set(new) - set(old)):
        if not any(first <= k <= last for first, last in blocks):
            problems.append(("outside every block", k))
        elif not any(first <= k <= last for first, last in (mine.records, mine.helpers)):
            problems.append(("in another class's block", k))
    if not any(int(k) for k in set(new) - set(old)):
        problems.append(("nothing added", 0))
    return problems


def changed_fields(old_sql, new_sql):
    def rows(text):
        return {int(m.group(1)): m.group(0).rstrip(",;") for m in re.finditer(r"^\((\d+),.*\)[,;]$", text, re.M)}
    old, new = rows(old_sql), rows(new_sql)
    return [k for k in old if old[k] != new.get(k)]


def ids():
    return {row["name"]: int(row["spell_id"]) for row in manifest()}


def expected_names():
    skills = [r["skill_name"] for r in sheet("crusader_skills.csv")]
    runes = ["%s - %s" % (r["skill_name"], r["rune_name"]) for r in sheet("crusader_runes.csv")]
    passives = [r["passive_name"] for r in sheet("crusader_passives.csv")]
    return skills, runes, passives


def check_manifest(rows):
    """Raises AssertionError unless the manifest holds each sheet row once, in the Crusader's block."""
    skills, runes, passives = expected_names()
    by_name = {}
    for row in rows:
        if FIRST <= int(row["spell_id"]) <= LAST:
            by_name.setdefault(row["name"], []).append(row)
    for name, kind in ([(n, "active") for n in skills] + [(n, "rune") for n in runes]
                       + [(n, "passive") for n in passives]):
        found = by_name.get(name, [])
        assert len(found) == 1, "%s: %d records in the Crusader's block" % (name, len(found))
        assert found[0]["kind"] == kind, "%s is a %s, not a %s" % (name, found[0]["kind"], kind)
    for row in rows:
        if row["kind"] in ("active", "rune", "passive") and row["name"] in set(skills + runes + passives):
            assert FIRST <= int(row["spell_id"]) <= LAST, "%s sits outside the Crusader's block" % row["name"]


def wrath_scale():
    """Energy units per Wrath point, from data/tunables/class_resources.csv (not the generator)."""
    path = MODULE / "data" / "tunables" / "class_resources.csv"
    with path.open(encoding="utf-8-sig", newline="") as stream:
        row = next(r for r in csv.DictReader(stream) if (r["d3_class"], r["resource_key"]) == ("Crusader", "wrath"))
    return float(row["storage_scale"])


def check_records(recs):
    index = ids()
    for row in sheet("crusader_skills.csv"):
        name = row["skill_name"]
        record = recs[index[name]]
        assert record["Name_Lang_enUS"] == name, name
        assert int(record["SpellClassSet"]) == FAMILY, (name, record["SpellClassSet"])
        cost = float(row["resource_cost"] or 0)
        if cost:
            assert int(record["PowerType"]) == ENERGY, name
            assert int(record["ManaCost"]) == round(cost * wrath_scale()), (name, record["ManaCost"], cost)
        cooldown = float(row["cooldown_seconds"] or 0)
        if cooldown:
            assert int(record["RecoveryTime"]) == round(cooldown * 1000), (name, record["RecoveryTime"])
    texts = {r["skill_name"]: r["full_tooltip_text"] for r in sheet("crusader_skills.csv")}
    texts.update({"%s - %s" % (r["skill_name"], r["rune_name"]): r["full_rune_text"] for r in sheet("crusader_runes.csv")})
    texts.update({r["passive_name"]: r.get("full_tooltip_text") or r.get("full_passive_text") or r.get("full_text") or ""
                  for r in sheet("crusader_passives.csv")})
    for name, sentence in texts.items():
        record = recs[index[name]]
        shown = record["Description_Lang_enUS"] + record["AuraDescription_Lang_enUS"]
        assert shown.strip(), "%s has no tooltip" % name
        # "${$x1-1}" is the client's own grammar for a computed number, not a leftover sheet token
        bare = re.sub(r"\$\{[^}]*\}", "", shown)
        assert "{" not in bare and "NEW:" not in bare, "%s has a leftover token: %s" % (name, shown[:80])
        if re.search(r"\{[a-z_]+(?::[a-z_]+)?\}", sentence):
            assert "$" in shown, "%s: the sentence has placeholders and the tooltip has no variable" % name


def check_rulings(recs):
    index = ids()
    fires = recs[index["Heaven's Fury - Fires of Heaven"]]
    assert int(fires["PowerType"]) == ENERGY and int(fires["ManaCost"]) == round(40 * wrath_scale()), fires["ManaCost"]
    assert int(fires["RecoveryTime"]) == 0 and int(fires["CategoryRecoveryTime"]) == 0, "Fires of Heaven keeps a cooldown"
    assert int(fires["Category"]) == 0, "Fires of Heaven shares its parent's cooldown category"
    parent = recs[index["Heaven's Fury"]]
    assert int(parent["RecoveryTime"]) > 0 and int(parent["Category"]) > 0, "Heaven's Fury lost its own cooldown"
    for name in ("Blessed Shield", "Blessed Shield - Staggering Shield", "Blessed Shield - Combust",
                 "Blessed Shield - Divine Aegis", "Blessed Shield - Shattering Throw"):
        record = recs[index[name]]
        assert int(record["EffectChainTargets_1"]) == 4, (name, record["EffectChainTargets_1"])
        assert (int(record["EffectChainTargets_2"]), int(record["EffectChainTargets_3"])) == (0, 0), name
    piercing = recs[index["Blessed Shield - Piercing Shield"]]
    assert [int(piercing["EffectChainTargets_%d" % n]) for n in (1, 2, 3)] == [1, 0, 0], "Piercing Shield bounces"


def targeting():
    return {r["skill"]: r for r in read(D3 / "skill_targeting.csv")}


class Records(unittest.TestCase):
    def test_every_sheet_row_has_one_record_in_the_block(self):
        check_manifest(manifest())
        skills, runes, passives = expected_names()
        self.assertEqual((len(skills), len(runes), len(passives)), (24, 120, 18))
        mine = [row for row in manifest() if FIRST <= int(row["spell_id"]) <= LAST]
        self.assertEqual([len([r for r in mine if r["kind"] == kind]) for kind in ("active", "rune", "passive")],
                         [24, 120, 18])

    def test_the_records_say_what_the_sheets_say(self):
        check_records(records())

    def test_the_rulings_hold(self):
        check_rulings(records())

    def test_the_placeholder_ranges_are_marked_and_the_width_sourced(self):
        rows = targeting()
        self.assertEqual(rows["Justice"]["range_yards"], "30")
        self.assertEqual(rows["Bombardment"]["range_yards"], "60")
        for skill in ("Justice", "Bombardment"):
            self.assertIn("placeholder", rows[skill]["source"], skill)
            self.assertIn("q-1017-06", rows[skill]["source"], skill)
        # the placeholders are copies of the rows the ruling names
        self.assertEqual(rows["Justice"]["range_yards"], rows["Smite"]["range_yards"])
        self.assertEqual({rows["Bombardment"]["range_yards"]},
                         {rows["Fist of the Heavens"]["range_yards"], rows["Judgment"]["range_yards"]})
        self.assertEqual(rows["Phalanx"]["width_yards"], "20")
        self.assertIn("radius 10", rows["Phalanx"]["source"])

    def test_no_new_token_is_left(self):
        for name in ("crusader_skills.csv", "crusader_runes.csv", "crusader_passives.csv",
                     "crusader_skill_values.csv", "crusader_passive_values.csv"):
            self.assertNotIn("NEW:", (D3 / name).read_text(encoding="utf-8"), name)
        vocabulary = (REPO / "docs/research/skill-tokens.md").read_text(encoding="utf-8")
        for token in ("block_chance_share_pct", "min_cooldown_seconds"):
            self.assertIn("| `%s` |" % token, vocabulary)

    def test_nothing_outside_the_blocks_moved(self):
        # The commit that brought the Crusader's records (combat_0088) against its parent: the same on nightly and on every
        # branch after it, since it compares two commits of history and not this tree with a fork point.
        old, new = at_arrival("spell_shells.csv")
        self.assertEqual(moved_outside_the_blocks(csv.DictReader(old.splitlines()), csv.DictReader(new.splitlines())), [])

    def test_no_record_outside_the_blocks_changed_a_field(self):
        # The manifest check above sees names and kinds; this sees every field of every spell_dbc row, so a renumbered
        # description variable on an earlier class's record (the Necromancer's) is caught too.
        old, new = at_arrival("spell_shells.sql")
        self.assertEqual(changed_fields(old, new), [])

    def test_every_value_row_is_in_the_value_map(self):
        mapped = {(r["skill"], r["rune"], r["token"], r["qualifier"])
                  for r in read(GENERATED / "spell_value_map.csv") if FIRST <= int(r["spell_id"]) <= LAST}
        wanted = {(r["skill"], r["rune"], r["token"], r["qualifier"]) for r in sheet("crusader_skill_values.csv")}
        wanted |= {(r["passive"] if "passive" in r else r.get("skill", ""), r.get("rune", ""), r["token"], r["qualifier"])
                   for r in sheet("crusader_passive_values.csv")}
        self.assertEqual({key for key in wanted - mapped if key[2] != "proc_coefficient"}, set())


class Picker(unittest.TestCase):
    def setUp(self):
        (self.rows, self.passives, self.labels, _, self.class_map, self.playable, self.waiting, _) = gcc.catalogue()
        self.mine = next(row[0] for row in self.class_map if row[2] == "Crusader")

    def test_the_crusader_is_playable_with_six_categories_24_skills_and_120_runes(self):
        self.assertIn("Crusader", self.playable)
        self.assertEqual(self.waiting, [])
        mine = [label for label in self.labels if label[1] == self.mine]
        skills = [label for label in mine if not label[3]]
        runes = [label for label in mine if label[3]]
        self.assertEqual((len(skills), len(runes)), (24, 120))
        self.assertEqual(sorted({label[4] for label in skills}),
                         sorted(["Primary", "Secondary", "Defensive", "Utility", "Laws", "Conviction"]))
        self.assertEqual(len([p for p in self.passives if p[0] == self.mine]), 18)

    def test_each_entry_is_at_the_sheets_unlock_level_and_in_the_sheets_category(self):
        categories = {r["skill_name"]: r["category"] for r in sheet("crusader_skills.csv")}
        levels = {(r["skill_name"], ""): int(r["unlock_level"] or 1) for r in sheet("crusader_skills.csv")}
        levels.update({(r["skill_name"], r["rune_name"]): int(r["unlock_level"] or 1) for r in sheet("crusader_runes.csv")})
        label_of = {label[0]: label for label in self.labels}
        checked = 0
        for class_id, _skill_id, _rune_id, spell_id, unlock, _buff in self.rows:
            if class_id != self.mine:
                continue
            _, _, skill, rune, category, _ = label_of[spell_id]
            self.assertEqual(unlock, levels[(skill, rune)], (skill, rune))
            if not rune:  # a rune's label carries no category: it stands under its skill
                self.assertEqual(category, categories[skill], skill)
            checked += 1
        self.assertEqual(checked, 144)


class ClientRow(unittest.TestCase):
    def test_the_client_class_row_carries_the_records_family(self):
        from dbc_store import Store, schema
        self.assertEqual({int(r["SpellClassSet"]) for r in records().values()}, {FAMILY})
        client = Store((REPO / "client-patch/dbc/ChrClasses.dbc").read_bytes(), schema(REPO, "chrclasses_dbc"))
        self.assertEqual(client.decode(CLASS_ID)["SpellClassSet"], FAMILY)

    def test_a_client_file_with_the_stock_family_gets_the_records_family(self):
        # The rule, not the committed file: the generator rewrites the client row it reads, so it is driven here with
        # a client ChrClasses.dbc whose Paladin row still carries the stock 10.
        import tempfile
        import generate_class_creation as creation
        from dbc_store import Store, schema
        columns = schema(REPO, "chrclasses_dbc")
        with tempfile.TemporaryDirectory() as folder:
            client_dir = Path(folder)
            for source in creation.CLIENT.iterdir():
                (client_dir / source.name).symlink_to(source)
            (client_dir / "ChrClasses.dbc").unlink()
            store = Store((creation.CLIENT / "ChrClasses.dbc").read_bytes(), columns)
            store.encode(dict(store.decode(CLASS_ID), SpellClassSet=STOCK_FAMILY))
            (client_dir / "ChrClasses.dbc").write_bytes(store.bytes())
            _, files = creation.render(creation.MODULE, client_dir)
        self.assertEqual(Store(files["ChrClasses.dbc"], columns).decode(CLASS_ID)["SpellClassSet"], FAMILY)

    def test_the_server_row_keeps_the_stock_family(self):
        # dc_classes.cpp strips the stock Paladin's spells by the server row's family. The committed migrations and the
        # generator's render from today's client file (whose Paladin row carries 24) both keep 10.
        import generate_class_resources as resources
        power_sql, client, _ = resources.display_power(resources.registry())
        names_sql, names_client, _ = resources.class_names(client)
        # and the client file that generator writes back keeps the family generate_class_creation.py gave it
        from dbc_store import Store, schema
        columns = schema(REPO, "chrclasses_dbc")
        self.assertEqual(Store(names_client, columns).decode(CLASS_ID)["SpellClassSet"], FAMILY)
        sources = {"world_0064_class_display_power.sql": None, "world_0065_class_names.sql": None,
                   "display_power render": power_sql, "class_names render": names_sql}
        for migration, rendered in sources.items():
            text = rendered or (MODULE / "data/sql/db-world/updates" / migration).read_text(encoding="utf-8")
            header, _, body = text.split("INSERT INTO `chrclasses_dbc` ", 1)[1].partition(" VALUES\n")
            column = re.findall(r"`(\w+)`", header).index("SpellClassSet")
            rows = [split_values(line.strip().lstrip("(").rstrip(",;").rstrip(")")) for line in body.splitlines()
                    if line.startswith("(")]
            paladin = [row for row in rows if int(row[0]) == CLASS_ID]
            self.assertEqual(len(paladin), 1, migration)
            self.assertEqual(int(paladin[0][column]), STOCK_FAMILY, migration)


class Mutants(unittest.TestCase):
    """The checks above must fail on a planted difference; each is run on a doctored copy."""

    def test_a_row_outside_the_blocks_that_moved_is_seen(self):
        old, new = at_arrival("spell_shells.csv")
        old_rows, new_rows = list(csv.DictReader(old.splitlines())), list(csv.DictReader(new.splitlines()))
        self.assertEqual(moved_outside_the_blocks(old_rows, new_rows), [])
        outside = next(r for r in new_rows if int(r["spell_id"]) < FIRST)
        renamed = [dict(r, name=r["name"] + " x") if r is outside else r for r in new_rows]
        self.assertEqual(moved_outside_the_blocks(old_rows, renamed), [("changed", outside["spell_id"])])
        dropped = [r for r in new_rows if r is not outside]
        self.assertEqual(moved_outside_the_blocks(old_rows, dropped), [("changed", outside["spell_id"])])

    def test_a_record_added_outside_the_crusaders_blocks_is_seen(self):
        old, new = at_arrival("spell_shells.csv")
        old_rows, new_rows = list(csv.DictReader(old.splitlines())), list(csv.DictReader(new.splitlines()))
        template = new_rows[0]
        stray = new_rows + [dict(template, spell_id="84500")]
        self.assertEqual(moved_outside_the_blocks(old_rows, stray), [("outside every block", 84500)])
        taken = {int(r["spell_id"]) for r in new_rows}
        free = next(i for i in range(85100, 85300) if i not in taken)
        necromancer = new_rows + [dict(template, spell_id=str(free))]
        self.assertEqual(moved_outside_the_blocks(old_rows, necromancer), [("in another class's block", free)])
        self.assertEqual(moved_outside_the_blocks(old_rows, old_rows), [("nothing added", 0)])

    def test_a_field_changed_outside_the_blocks_is_seen(self):
        old, new = at_arrival("spell_shells.sql")
        self.assertEqual(changed_fields(old, new), [])
        first = re.search(r"^\((\d+),.*\)[,;]$", old, re.M)
        self.assertTrue(first)
        self.assertEqual(changed_fields(old, new.replace(first.group(0), first.group(0).replace(",0,", ",9,", 1))),
                         [int(first.group(1))])

    def test_a_dropped_record_is_seen(self):
        with self.assertRaises(AssertionError):
            check_manifest([r for r in manifest() if r["name"] != "Punish - Roar"])

    def test_a_renamed_record_is_seen(self):
        with self.assertRaises(AssertionError):
            check_manifest([dict(r, name="Smite!" if r["name"] == "Smite" else r["name"]) for r in manifest()])

    def test_a_record_outside_the_block_is_seen(self):
        with self.assertRaises(AssertionError):
            check_manifest([dict(r, spell_id=str(LAST + 200) if r["name"] == "Condemn" else r["spell_id"])
                            for r in manifest()])

    def test_a_cost_off_by_ten_is_seen(self):
        recs = records()
        identifier = ids()["Blessed Shield"]
        recs[identifier] = dict(recs[identifier], ManaCost=str(int(recs[identifier]["ManaCost"]) * 10))
        with self.assertRaises(AssertionError):
            check_records(recs)

    def test_a_leftover_token_in_a_tooltip_is_seen(self):
        recs = records()
        identifier = ids()["Shield Bash"]
        recs[identifier] = dict(recs[identifier], Description_Lang_enUS=recs[identifier]["Description_Lang_enUS"]
                                + " {block_chance_share_pct}")
        with self.assertRaises(AssertionError):
            check_records(recs)

    def test_a_cooldown_left_on_fires_of_heaven_is_seen(self):
        for column, value in (("RecoveryTime", "20000"), ("Category", "8513")):
            recs = records()
            identifier = ids()["Heaven's Fury - Fires of Heaven"]
            recs[identifier] = dict(recs[identifier], **{column: value})
            with self.subTest(column=column), self.assertRaises(AssertionError):
                check_rulings(recs)

    def test_a_donor_chain_left_on_blessed_shield_is_seen(self):
        for name, column, value in (("Blessed Shield", "EffectChainTargets_2", "3"),
                                    ("Blessed Shield - Piercing Shield", "EffectChainTargets_1", "4")):
            recs = records()
            identifier = ids()[name]
            recs[identifier] = dict(recs[identifier], **{column: value})
            with self.subTest(name=name), self.assertRaises(AssertionError):
                check_rulings(recs)


if __name__ == "__main__":
    unittest.main()
