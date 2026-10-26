"""diablocraft-vxrcu.5 (Witch Doctor 2a): every Witch Doctor skill, rune and passive has its record, its tooltip and its place in the picker.

The Demon Hunter's spec in test_demon_hunter_records.py, for the Witch Doctor's block 86000-86199 (generate_spells.py CLASS_BLOCKS, family 26):

  * **A record per sheet row.** witch_doctor_skills.csv (23), witch_doctor_runes.csv (115) and witch_doctor_passives.csv (19)
    each have exactly one record in the manifest (spell_shells.csv), inside the block; no other class's record sits there.
  * **The record is the sheet.** Read back from spell_shells.sql: the name, the family 26, a skill's cooldown in RecoveryTime
    and its cost in Mana (PowerType 0, one unit a point, the registry's); and a tooltip that is non-empty, has no unfilled
    "{token}" or "NEW:" and carries a "$" variable where the sheet's sentence has placeholders.
  * **The rulings.** The four Primaries are free; the eight spenders (Grasp of the Dead, Firebats, Haunt, Locust Swarm, Zombie
    Charger, Spirit Barrage, Acid Cloud, Piranhas) are paid in Mana; Firebats - Vampire Bats costs 250 Mana; Grasp of the Dead -
    Unbreakable Grasp carries no cost; the cooldown runes (Desperate Grasp, Unstable Realm, Piranhado, Devoted Following) keep
    their own timer; the class has its regeneration mask record (the core's Mana tick off, the module's pulse the one source);
    Poison Dart's blank cast range carries a marked placeholder and the two blank line widths are the designer's standing 3 yd default.
  * **The numbers are the sheet's.** Every row of the two values sheets has its value map row.
  * **The picker.** The class catalogue lists the Witch Doctor as playable, its 23 skills and 115 runes in the six categories of
    class_skill_categories.csv at the sheets' unlock levels, and its 19 passives.
  * **The client class row.** ChrClasses.dbc row 14 carries the records' family 26, since the client applies a spell modifier
    only inside the class's own SpellClassSet; the server row keeps the Warlock's 5 for the stock-spell strip.
  * **Nothing else moved.** Every manifest row outside the class blocks is unchanged against the commit that brought the records.
  * **A planted difference is seen**: a record dropped, renamed, moved out of the block, a cost off by ten or paid in the wrong
    power, a leftover token, a cost left on Unbreakable Grasp, the mask record dropped.

What it does not prove: the icons and tooltips as the client draws them (the test sheet's Checks), or that a cast does anything:
casts land with no effect until the skill beads.

    python mod-diablocraft/scripts/tests/classes/test_witch_doctor_records.py
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

FIRST, LAST = 86000, 86199
HELPERS = (86200, 86299)
FAMILY = 26
STOCK_FAMILY = 5
WOW_CLASS = 14
MANA = 0
PREVENT_REGENERATE_POWER = 294
SPENDERS = ("Grasp of the Dead", "Firebats", "Haunt", "Locust Swarm", "Zombie Charger", "Spirit Barrage", "Acid Cloud",
            "Piranhas")
PRIMARIES = ("Poison Dart", "Corpse Spiders", "Plague of Toads", "Firebomb")
RECORDS_MIGRATION = "combat_0107_witch_doctor_records.sql"
# The Witch Doctor's channels the module pays (generate_spells.py CHANNEL_DRAIN_SKILLS): the start and each tick, not the record.
MODULE_PAID = {"Firebats"}


def sheet(name):
    return read(D3 / name)


def manifest():
    return read(GENERATED / "spell_shells.csv")


def records(first=FIRST, last=LAST):
    """{spell id: {column: value}} of the ids first..last, from the SQL the generator wrote."""
    text = (GENERATED / "spell_shells.sql").read_text(encoding="utf-8")
    out = {}
    for insert in text.split("INSERT INTO `spell_dbc`")[1:]:
        header, _, body = insert.partition("VALUES")
        columns = re.findall(r"`(\w+)`", header)
        for line in body.splitlines():
            match = re.match(r"^\((\d+),(.*)\)[,;]$", line)
            if match and first <= int(match.group(1)) <= last:
                out[int(match.group(1))] = dict(zip(columns, split_values(match.group(1) + "," + match.group(2))))
    return out


def arrival():
    """The commit that added the Witch Doctor's records migration and its first parent, or None without that history."""
    path = "mod-diablocraft/data/sql/db-world/updates/" + RECORDS_MIGRATION
    found = subprocess.run(["git", "log", "--diff-filter=A", "--format=%H", "--", path], cwd=REPO, capture_output=True,
                           text=True)
    commits = found.stdout.split()
    if found.returncode != 0 or not commits:
        return None
    return commits[-1] + "^", commits[-1]


def at_arrival(name):
    """(text before, text after) of data/generated/<name> across the arrival of the Witch Doctor's records."""
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
    mine = generate_spells.CLASS_BLOCKS["witch_doctor"]
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
    skills = [r["skill_name"] for r in sheet("witch_doctor_skills.csv")]
    runes = ["%s - %s" % (r["skill_name"], r["rune_name"]) for r in sheet("witch_doctor_runes.csv")]
    passives = [r["passive_name"] for r in sheet("witch_doctor_passives.csv")]
    return skills, runes, passives


def check_manifest(rows):
    """Raises AssertionError unless the manifest holds each sheet row once, in the Witch Doctor's block."""
    skills, runes, passives = expected_names()
    by_name = {}
    for row in rows:
        if FIRST <= int(row["spell_id"]) <= LAST:
            by_name.setdefault(row["name"], []).append(row)
    for name, kind in ([(n, "active") for n in skills] + [(n, "rune") for n in runes]
                       + [(n, "passive") for n in passives]):
        found = by_name.get(name, [])
        assert len(found) == 1, "%s: %d records in the Witch Doctor's block" % (name, len(found))
        assert found[0]["kind"] == kind, "%s is a %s, not a %s" % (name, found[0]["kind"], kind)
    for row in rows:
        if row["kind"] in ("active", "rune", "passive") and row["name"] in set(skills + runes + passives):
            assert FIRST <= int(row["spell_id"]) <= LAST, "%s sits outside the Witch Doctor's block" % row["name"]


def mana_scale():
    """Mana units per point, from data/tunables/class_resources.csv (not the generator)."""
    path = MODULE / "data" / "tunables" / "class_resources.csv"
    with path.open(encoding="utf-8-sig", newline="") as stream:
        row = next(r for r in csv.DictReader(stream) if (r["d3_class"], r["resource_key"]) == ("Witch Doctor", "mana"))
    return float(row["storage_scale"])


def check_records(recs):
    index = ids()
    scale = mana_scale()
    for row in sheet("witch_doctor_skills.csv"):
        name = row["skill_name"]
        record = recs[index[name]]
        assert record["Name_Lang_enUS"] == name, name
        assert int(record["SpellClassSet"]) == FAMILY, (name, record["SpellClassSet"])
        cost = float(row["resource_cost"] or 0)
        if cost and name not in MODULE_PAID:
            assert int(record["PowerType"]) == MANA, (name, record["PowerType"])
            assert int(record["ManaCost"]) == round(cost * scale), (name, record["ManaCost"], cost)
        cooldown = float(row["cooldown_seconds"] or 0)
        if cooldown:
            assert int(record["RecoveryTime"]) == round(cooldown * 1000), (name, record["RecoveryTime"])
    texts = {r["skill_name"]: r["full_tooltip_text"] for r in sheet("witch_doctor_skills.csv")}
    texts.update({"%s - %s" % (r["skill_name"], r["rune_name"]): r["full_rune_text"]
                  for r in sheet("witch_doctor_runes.csv")})
    texts.update({r["passive_name"]: r["full_text"] for r in sheet("witch_doctor_passives.csv")})
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
    scale = mana_scale()
    sheet_costs = {r["skill_name"]: r["resource_cost"] for r in sheet("witch_doctor_skills.csv")}
    assert {name for name, cost in sheet_costs.items() if cost} == set(SPENDERS), "the spenders are not the eight"
    for name in PRIMARIES:
        assert int(recs[index[name]]["ManaCost"]) == 0, "%s (a Signature spell) costs Mana" % name
    for name in SPENDERS:
        if name in MODULE_PAID:
            continue
        record = recs[index[name]]
        assert int(record["PowerType"]) == MANA and int(record["ManaCost"]) == round(float(sheet_costs[name]) * scale), name
    for name in index:
        if name == "Firebats" or name.startswith("Firebats - "):
            assert int(recs[index[name]]["ManaCost"]) == 0, "%s: the module pays Firebats' Mana, the record carries none" % name
    assert int(recs[index["Grasp of the Dead - Unbreakable Grasp"]]["ManaCost"]) == 0, "Unbreakable Grasp still costs Mana"
    assert int(recs[index["Grasp of the Dead - Desperate Grasp"]]["ManaCost"]) == round(150 * scale)
    for name, seconds in (("Grasp of the Dead - Desperate Grasp", 4), ("Mass Confusion - Unstable Realm", 30),
                          ("Piranhas - Piranhado", 16), ("Fetish Army - Devoted Following", 90)):
        assert int(recs[index[name]]["RecoveryTime"]) == seconds * 1000, name


def check_mask(recs):
    """The class's regeneration mask: a hidden record that stops the core's own Mana tick."""
    index = ids()
    assert "Witch Doctor - resource pulse - core regeneration mask" in index, "no regeneration mask record"
    record = recs[index["Witch Doctor - resource pulse - core regeneration mask"]]
    assert HELPERS[0] <= int(record["ID"]) <= HELPERS[1], "the mask sits outside the helper block"
    assert int(record["EffectAura_1"]) == PREVENT_REGENERATE_POWER, record["EffectAura_1"]
    assert int(record["EffectMiscValue_1"]) == MANA + 1, "the mask is not on the Mana slot"


def targeting():
    return {r["skill"]: r for r in read(D3 / "skill_targeting.csv")}


class Records(unittest.TestCase):
    def test_every_sheet_row_has_one_record_in_the_block(self):
        check_manifest(manifest())
        skills, runes, passives = expected_names()
        self.assertEqual((len(skills), len(runes), len(passives)), (23, 115, 19))
        mine = [row for row in manifest() if FIRST <= int(row["spell_id"]) <= LAST]
        self.assertEqual([len([r for r in mine if r["kind"] == kind]) for kind in ("active", "rune", "passive")],
                         [23, 115, 19])

    def test_the_records_say_what_the_sheets_say(self):
        check_records(records())

    def test_the_rulings_hold(self):
        check_rulings(records())

    def test_the_class_has_its_regeneration_mask(self):
        check_mask(records(HELPERS[0], HELPERS[1]))

    def test_mana_is_a_registry_row_at_one_unit_a_point(self):
        self.assertEqual(mana_scale(), 1.0)

    def test_the_blank_cast_range_is_a_marked_placeholder(self):
        rows = targeting()
        self.assertEqual(rows["Poison Dart"]["range_yards"], "60")
        self.assertIn("range 60 yd placeholder", rows["Poison Dart"]["source"])
        # the placeholder is a copy of the single-target rows it follows
        self.assertEqual(rows["Poison Dart"]["range_yards"], rows["Corpse Lance"]["range_yards"])
        self.assertIn("range", rows["Poison Dart"]["unsure"])

    def test_the_line_widths_are_alexs_standing_default_not_placeholders(self):
        # AGENTS.md Numbers: a line attack is 3 yd wide, named in the report with no card
        rows = targeting()
        for skill in ("Plague of Toads", "Zombie Charger"):
            self.assertEqual(rows[skill]["target_type"], "line_pierce", skill)
            self.assertEqual(rows[skill]["width_yards"], "3", skill)
            self.assertIn("standing default", rows[skill]["source"], skill)
            self.assertNotIn("placeholder", rows[skill]["source"], skill)
            self.assertNotIn("width", rows[skill]["unsure"], skill)

    def test_the_rendered_targeting_follows_the_sheet(self):
        # the sheet is what the server reads: the skill's record and its runes' carry the sheet's numbers
        sql = (GENERATED / "spell_shells.sql").read_text(encoding="utf-8")
        for skill, kind, value in (("Plague of Toads", "line_pierce", "'NUMERIC',49.0,0.0,3.0)"),
                                   ("Zombie Charger", "line_pierce", "'NUMERIC',22.0,6.0,3.0)"),
                                   ("Poison Dart", "single_enemy", "'NUMERIC',60.0,0.0,0.0)")):
            self.assertEqual(targeting()[skill]["target_type"], kind)
            self.assertIn("'%s',%s" % (kind, value), sql, skill)

    def test_acid_rains_24_yards_has_its_own_radius_row(self):
        # the stock SpellRadius table has 23 and 25 but no 24: the module adds the row (data/spell_radius_rows.csv), the server
        # takes it from spellradius_dbc in the records migration and the client from SpellRadius.dbc
        import struct
        rows = read(MODULE / "data" / "spell_radius_rows.csv")
        self.assertEqual([(r["id"], r["yards"], r["used_by"]) for r in rows], [("1000", "24", "Acid Cloud - Acid Rain")])
        stock = (REPO / "azerothcore-wotlk/build/server/data/dbc/SpellRadius.dbc").read_bytes()
        stock_yards = {struct.unpack_from("<f", stock, 20 + i * 16 + 4)[0] for i in range(struct.unpack_from("<I", stock, 4)[0])}
        self.assertEqual({23.0, 25.0} <= stock_yards, True)
        self.assertNotIn(24.0, stock_yards)
        recs = records()
        users = [i for i, r in recs.items() if r["EffectRadiusIndex_1"] == "1000"]
        self.assertEqual(users, [ids()["Acid Cloud - Acid Rain"]])
        client = (REPO / "client-patch/dbc/SpellRadius.dbc").read_bytes()
        count = struct.unpack_from("<I", client, 4)[0]
        self.assertEqual(count, struct.unpack_from("<I", stock, 4)[0] + 1)
        self.assertEqual(client[20:20 + (count - 1) * 16], stock[20:20 + (count - 1) * 16])
        self.assertEqual(struct.unpack_from("<Ifff", client, 20 + (count - 1) * 16), (1000, 24.0, 0.0, 24.0))
        expected = "INSERT INTO spellradius_dbc (ID,Radius,RadiusPerLevel,RadiusMax) VALUES (1000,24,0,24);"
        for text in ((GENERATED / "spell_shells.sql").read_text(encoding="utf-8"),
                     (MODULE / "data/sql/db-world/updates" / RECORDS_MIGRATION).read_text(encoding="utf-8")):
            self.assertEqual(text.count(expected), 1)

    def test_no_new_token_is_left(self):
        for name in ("witch_doctor_skills.csv", "witch_doctor_runes.csv", "witch_doctor_passives.csv",
                     "witch_doctor_skill_values.csv", "witch_doctor_passive_values.csv"):
            self.assertNotIn("NEW:", (D3 / name).read_text(encoding="utf-8"), name)

    def test_no_name_is_shared_with_another_class(self):
        # records, the id manifest and the catalogue labels are keyed by name, so a shared name would be ambiguous
        skills, runes, passives = expected_names()
        mine = set(skills + passives)
        for stem in ("barbarian", "wizard", "monk", "crusader", "necromancer", "demon_hunter"):
            theirs = {r["skill_name"] for r in sheet("%s_skills.csv" % stem)}
            theirs |= {r["passive_name"] for r in sheet("%s_passives.csv" % stem)}
            self.assertEqual(mine & theirs, set(), stem)

    def test_the_research_sheets_are_the_data_sheets_but_for_the_noted_changes(self):
        research = REPO / "docs" / "research" / "witch-doctor"
        for data, source in (("witch_doctor_skills.csv", "witch_doctor_skills.tokenised.csv"),
                             ("witch_doctor_passives.csv", "witch_doctor_passives.tokenised.csv"),
                             ("witch_doctor_passive_values.csv", "witch_doctor_passive_values.csv")):
            self.assertEqual((D3 / data).read_bytes(), (research / source).read_bytes(), data)
        # the skill values are the research's rows and, after them, each spell's proc coefficient from its power file (2c, for the
        # Fetish Sycophants' chance and the class passives that read it): nothing of the research's is changed
        ours = (D3 / "witch_doctor_skill_values.csv").read_bytes()
        theirs = (research / "witch_doctor_skill_values.csv").read_bytes()
        self.assertTrue(ours.startswith(theirs))
        added = list(csv.reader(ours[len(theirs):].decode("utf-8").splitlines()))
        self.assertGreater(len(added), 100)
        self.assertEqual({r[2] for r in added}, {"proc_coefficient"})
        # Unbreakable Grasp's cell names its resource ("Mana cost removed"), as every other class's rune that drops a cost
        ours = (D3 / "witch_doctor_runes.csv").read_text(encoding="utf-8")
        theirs = (research / "witch_doctor_runes.tokenised.csv").read_text(encoding="utf-8")
        self.assertEqual(ours.replace(',"Mana cost removed",', ',"Cost removed",'), theirs)
        # Sacrifice and Big Bad Voodoo take other stock looks: the research's donors (Death Pact, Bloodlust) carry a leftover
        # 100 yd area in an unused effect slot, which would outgrow the ground cursor (test_ground_target_circles.py)
        changed = [o for o, t in zip(read(D3 / "witch_doctor_visuals.csv"), read(research / "witch_doctor_visuals.csv"))
                   if o != t]
        self.assertEqual({(o["d3_skill"], o["wow_spell_name"]) for o in changed},
                         {("Sacrifice", "Sacrifice"), ("Big Bad Voodoo", "Power Infusion")})
        self.assertEqual(len(changed), 12)

    def test_nothing_outside_the_blocks_moved(self):
        # The commit that brought the Witch Doctor's records (combat_0103) against its parent: the same on nightly and on
        # every branch after it, since it compares two commits of history and not this tree with a fork point.
        old, new = at_arrival("spell_shells.csv")
        self.assertEqual(moved_outside_the_blocks(csv.DictReader(old.splitlines()), csv.DictReader(new.splitlines())), [])

    def test_no_record_outside_the_blocks_changed_a_field(self):
        # The manifest check above sees names and kinds; this sees every field of every spell_dbc row, so a renumbered
        # description variable on an earlier class's record is caught too.
        old, new = at_arrival("spell_shells.sql")
        self.assertEqual(changed_fields(old, new), [])

    def test_every_value_row_is_in_the_value_map(self):
        mapped = {(r["skill"], r["rune"], r["token"], r["qualifier"])
                  for r in read(GENERATED / "spell_value_map.csv") if FIRST <= int(r["spell_id"]) <= LAST}
        wanted = {(r["skill"], r["rune"], r["token"], r["qualifier"]) for r in sheet("witch_doctor_skill_values.csv")}
        wanted |= {(r["skill"], r.get("rune", ""), r["token"], r["qualifier"])
                   for r in sheet("witch_doctor_passive_values.csv")}
        self.assertEqual({key for key in wanted - mapped if key[2] != "proc_coefficient"}, set())

    def test_the_cost_rows_name_the_power_they_are_paid_in(self):
        conversions = {}
        for r in read(GENERATED / "spell_value_map.csv"):
            if FIRST <= int(r["spell_id"]) <= LAST and r["token"] == "cost_resource":
                conversions.setdefault(r["skill"], set()).add(r["source"] if r["skill"] in MODULE_PAID else r["conversion"])
        self.assertTrue(conversions)
        for skill, names in conversions.items():
            self.assertEqual(names, {"exact"} if skill in MODULE_PAID else {"mana_points"}, skill)


class Picker(unittest.TestCase):
    def setUp(self):
        (self.rows, self.passives, self.labels, _, self.class_map, self.playable, self.waiting, _) = gcc.catalogue()
        self.mine = next(row[0] for row in self.class_map if row[2] == "Witch Doctor")

    def test_the_witch_doctor_is_playable_with_six_categories_23_skills_and_115_runes(self):
        self.assertIn("Witch Doctor", self.playable)
        self.assertEqual(self.waiting, [])
        mine = [label for label in self.labels if label[1] == self.mine]
        skills = [label for label in mine if not label[3]]
        runes = [label for label in mine if label[3]]
        self.assertEqual((len(skills), len(runes)), (23, 115))
        self.assertEqual(sorted({label[4] for label in skills}),
                         sorted(["Primary", "Secondary", "Defensive", "Terror", "Decay", "Voodoo"]))
        self.assertEqual(sorted(len([s for s in skills if s[4] == c])
                                for c in ("Primary", "Secondary", "Defensive", "Terror", "Decay", "Voodoo")),
                         sorted([4, 4, 4, 3, 5, 3]))
        self.assertEqual(len([p for p in self.passives if p[0] == self.mine]), 19)

    def test_each_entry_is_at_the_sheets_unlock_level_and_in_the_sheets_category(self):
        categories = {r["skill_name"]: r["category"] for r in sheet("witch_doctor_skills.csv")}
        levels = {(r["skill_name"], ""): int(r["unlock_level"] or 1) for r in sheet("witch_doctor_skills.csv")}
        levels.update({(r["skill_name"], r["rune_name"]): int(r["unlock_level"] or 1)
                       for r in sheet("witch_doctor_runes.csv")})
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
        self.assertEqual(checked, 138)


class ClientRow(unittest.TestCase):
    def test_the_client_class_row_carries_the_records_family(self):
        from dbc_store import Store, schema
        self.assertEqual({int(r["SpellClassSet"]) for r in records().values()
                          if r["Name_Lang_enUS"] in ids()}, {FAMILY})
        client = Store((REPO / "client-patch/dbc/ChrClasses.dbc").read_bytes(), schema(REPO, "chrclasses_dbc"))
        self.assertEqual(client.decode(WOW_CLASS)["SpellClassSet"], FAMILY)

    def test_a_client_file_with_the_parents_family_gets_the_records_family(self):
        # The rule, not the committed file: the generator rewrites the client row it reads, so it is driven here with
        # a client ChrClasses.dbc whose row 14 still carries the Warlock's 5.
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
            store.encode(dict(store.decode(WOW_CLASS), SpellClassSet=STOCK_FAMILY))
            (client_dir / "ChrClasses.dbc").write_bytes(store.bytes())
            _, files = creation.render(creation.MODULE, client_dir)
        self.assertEqual(Store(files["ChrClasses.dbc"], columns).decode(WOW_CLASS)["SpellClassSet"], FAMILY)

    def test_the_server_row_keeps_the_warlocks_family(self):
        # dc_classes.cpp strips the parent's stock spells by the server row's family
        server = (MODULE / "data/sql/db-world/updates/world_0075_class_witch_doctor.sql").read_text(encoding="utf-8")
        header, _, row = server.split("INSERT INTO `chrclasses_dbc` ", 1)[1].partition(" VALUES\n(")
        values = split_values(row.split(");", 1)[0])
        self.assertEqual(int(values[re.findall(r"`(\w+)`", header).index("SpellClassSet")]), STOCK_FAMILY)


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

    def test_a_record_added_outside_the_witch_doctors_blocks_is_seen(self):
        old, new = at_arrival("spell_shells.csv")
        old_rows, new_rows = list(csv.DictReader(old.splitlines())), list(csv.DictReader(new.splitlines()))
        template = new_rows[0]
        stray = new_rows + [dict(template, spell_id="84500")]
        self.assertEqual(moved_outside_the_blocks(old_rows, stray), [("outside every block", 84500)])
        taken = {int(r["spell_id"]) for r in new_rows}
        free = next(i for i in range(85700, 85900) if i not in taken)
        demon_hunter = new_rows + [dict(template, spell_id=str(free))]
        self.assertEqual(moved_outside_the_blocks(old_rows, demon_hunter), [("in another class's block", free)])
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
            check_manifest([r for r in manifest() if r["name"] != "Haunt - Poisoned Spirit"])

    def test_a_renamed_record_is_seen(self):
        with self.assertRaises(AssertionError):
            check_manifest([dict(r, name="Haunt!" if r["name"] == "Haunt" else r["name"]) for r in manifest()])

    def test_a_record_outside_the_block_is_seen(self):
        with self.assertRaises(AssertionError):
            check_manifest([dict(r, spell_id=str(LAST + 200) if r["name"] == "Hex" else r["spell_id"])
                            for r in manifest()])

    def test_a_cost_off_by_ten_is_seen(self):
        recs = records()
        identifier = ids()["Locust Swarm"]
        recs[identifier] = dict(recs[identifier], ManaCost=str(int(recs[identifier]["ManaCost"]) * 10))
        with self.assertRaises(AssertionError):
            check_records(recs)

    def test_a_cost_paid_in_the_wrong_power_is_seen(self):
        for check in (check_records, check_rulings):
            recs = records()
            identifier = ids()["Acid Cloud"]
            recs[identifier] = dict(recs[identifier], PowerType="1")
            with self.subTest(check=check.__name__), self.assertRaises(AssertionError):
                check(recs)

    def test_a_leftover_token_in_a_tooltip_is_seen(self):
        recs = records()
        identifier = ids()["Hex"]
        recs[identifier] = dict(recs[identifier], Description_Lang_enUS=recs[identifier]["Description_Lang_enUS"]
                                + " {duration_seconds}")
        with self.assertRaises(AssertionError):
            check_records(recs)

    def test_a_cost_on_a_primary_is_seen(self):
        recs = records()
        identifier = ids()["Poison Dart"]
        recs[identifier] = dict(recs[identifier], ManaCost="10")
        with self.assertRaises(AssertionError):
            check_rulings(recs)

    def test_a_cost_left_on_unbreakable_grasp_is_seen(self):
        recs = records()
        identifier = ids()["Grasp of the Dead - Unbreakable Grasp"]
        recs[identifier] = dict(recs[identifier], ManaCost="150")
        with self.assertRaises(AssertionError):
            check_rulings(recs)

    def test_a_lost_cooldown_rune_timer_is_seen(self):
        recs = records()
        identifier = ids()["Piranhas - Piranhado"]
        recs[identifier] = dict(recs[identifier], RecoveryTime="8000")
        with self.assertRaises(AssertionError):
            check_rulings(recs)

    def test_a_dropped_mask_record_is_seen(self):
        recs = records(HELPERS[0], HELPERS[1])
        name = ids()["Witch Doctor - resource pulse - core regeneration mask"]
        del recs[name]
        with self.assertRaises(KeyError):
            check_mask(recs)
        recs = records(HELPERS[0], HELPERS[1])
        recs[name] = dict(recs[name], EffectMiscValue_1="2")
        with self.assertRaises(AssertionError):
            check_mask(recs)


if __name__ == "__main__":
    unittest.main()
