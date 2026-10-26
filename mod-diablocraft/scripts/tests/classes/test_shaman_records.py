"""diablocraft-xnrvn.6 (Shaman 2a): every Shaman skill, rune and passive has its record, its tooltip and its place in the picker.

The Witch Doctor's spec in test_witch_doctor_records.py, for the Shaman's block 86300-86499 (generate_spells.py CLASS_BLOCKS, family 27):

  * **A record per sheet row.** shaman_skills.csv (24), shaman_runes.csv (120) and shaman_passives.csv (20) each have exactly one
    record in the manifest (spell_shells.csv), inside the block; no other class's record sits there.
  * **The record is the sheet.** Read back from spell_shells.sql: the name the player reads, the family 27, a skill's cooldown in
    RecoveryTime and its cost in Rage units (PowerType 1, one unit a Maelstrom point, the registry's); and a tooltip that is
    non-empty, has no unfilled "{token}" or "NEW:" and carries a "$" variable where the sheet's sentence has placeholders.
  * **The rulings.** The four Primaries, Thunderstorm and every other cooldown-only skill cost nothing; the six spenders (Chain
    Lightning, Lava Burst, Earthquake, Elemental Blast, Searing Totem, Elemental Weapon) are paid in Rage; Ancestral Protection keeps
    its 90 second timer; the class has its regeneration mask record (the core's Rage tick off, the module's pulse the one source);
    every element cell resolves to a school (the sheets' Attuned, Copied and blank cells became Lightning, Physical and the skill's).
  * **The name two classes share.** The Shaman's Earthquake is keyed `Earthquake (Shaman)` in every sheet and the value map, its
    record and its runes' records are named for the player `Earthquake` and `Earthquake - <rune>`, and the Barbarian's Earthquake keeps
    its own key, ids and record.
  * **The numbers are the sheet's.** Every row of the two values sheets has its value map row.
  * **The picker.** The class catalogue lists the Shaman as playable, its 24 skills and 120 runes in the six categories of
    class_skill_categories.csv at the sheets' unlock levels, and its 20 passives.
  * **The client class row.** ChrClasses.dbc row 7 carries the records' family 27, since the client applies a spell modifier only
    inside the class's own SpellClassSet; the stock (server) row keeps the Shaman's 11 for the stock-spell strip.
  * **Nothing else moved.** Every manifest row outside the class blocks is unchanged against the commit that brought the records.
  * **A planted difference is seen**: a record dropped, renamed, moved out of the block, a cost off by ten or paid in the wrong
    power, a leftover token, a cost left on a free skill, an element left unresolved.

What it does not prove: the icons and tooltips as the client draws them (the test sheet's Checks), or that a cast does anything:
casts land with no effect until the skill beads.

    python mod-diablocraft/scripts/tests/classes/test_shaman_records.py
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

FIRST, LAST = 86300, 86499
HELPERS = (86500, 86599)
FAMILY = 27
STOCK_FAMILY = 11
WOW_CLASS = 7
RAGE = 1
PREVENT_REGENERATE_POWER = 294
SPENDERS = ("Chain Lightning", "Lava Burst", "Earthquake (Shaman)", "Elemental Blast", "Searing Totem", "Elemental Weapon")
PRIMARIES = ("Lightning Bolt", "Flame Shock", "Elemental Lash", "Frost Lance")
SHARED_KEY = "Earthquake (Shaman)"
SHARED_SHOWN = "Earthquake"
RECORDS_MIGRATION = "combat_0125_shaman_records.sql"
SCHOOLS = {"Physical", "Fire", "Cold", "Lightning"}


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
    """The commit that added the Shaman's records migration and its first parent, or None without that history."""
    path = "mod-diablocraft/data/sql/db-world/updates/" + RECORDS_MIGRATION
    found = subprocess.run(["git", "log", "--diff-filter=A", "--format=%H", "--", path], cwd=REPO, capture_output=True,
                           text=True)
    commits = found.stdout.split()
    if found.returncode != 0 or not commits:
        return None
    return commits[-1] + "^", commits[-1]


def at_arrival(name):
    """(text before, text after) of data/generated/<name> across the arrival of the Shaman's records."""
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
    mine = generate_spells.CLASS_BLOCKS["shaman"]
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


SHOWN = generate_spells.shown_names()


def shown(key):
    """The name the player reads for the record keyed `key`."""
    return generate_spells.shown_name(SHOWN, key)


def expected_names():
    skills = [r["skill_name"] for r in sheet("shaman_skills.csv")]
    runes = ["%s - %s" % (r["skill_name"], r["rune_name"]) for r in sheet("shaman_runes.csv")]
    passives = [r["passive_name"] for r in sheet("shaman_passives.csv")]
    return skills, runes, passives


def check_manifest(rows):
    """Raises AssertionError unless the manifest holds each sheet row once, in the Shaman's block."""
    skills, runes, passives = expected_names()
    by_name = {}
    for row in rows:
        if FIRST <= int(row["spell_id"]) <= LAST:
            by_name.setdefault(row["name"], []).append(row)
    for name, kind in ([(n, "active") for n in skills] + [(n, "rune") for n in runes]
                       + [(n, "passive") for n in passives]):
        found = by_name.get(name, [])
        assert len(found) == 1, "%s: %d records in the Shaman's block" % (name, len(found))
        assert found[0]["kind"] == kind, "%s is a %s, not a %s" % (name, found[0]["kind"], kind)
    for row in rows:
        if row["kind"] in ("active", "rune", "passive") and row["name"] in set(skills + runes + passives):
            assert FIRST <= int(row["spell_id"]) <= LAST, "%s sits outside the Shaman's block" % row["name"]


def rage_scale():
    """Rage units per Maelstrom point, from data/tunables/class_resources.csv (not the generator)."""
    path = MODULE / "data" / "tunables" / "class_resources.csv"
    with path.open(encoding="utf-8-sig", newline="") as stream:
        row = next(r for r in csv.DictReader(stream) if (r["d3_class"], r["resource_key"]) == ("Shaman", "maelstrom"))
    return float(row["storage_scale"])


def check_records(recs):
    index = ids()
    scale = rage_scale()
    for row in sheet("shaman_skills.csv"):
        name = row["skill_name"]
        record = recs[index[name]]
        assert record["Name_Lang_enUS"] == shown(name), (name, record["Name_Lang_enUS"])
        assert int(record["SpellClassSet"]) == FAMILY, (name, record["SpellClassSet"])
        cost = float(row["resource_cost"] or 0)
        if cost:
            assert int(record["PowerType"]) == RAGE, (name, record["PowerType"])
            assert int(record["ManaCost"]) == round(cost * scale), (name, record["ManaCost"], cost)
        cooldown = float(row["cooldown_seconds"] or 0)
        if cooldown:
            assert int(record["RecoveryTime"]) == round(cooldown * 1000), (name, record["RecoveryTime"])
    texts = {r["skill_name"]: r["full_tooltip_text"] for r in sheet("shaman_skills.csv")}
    texts.update({"%s - %s" % (r["skill_name"], r["rune_name"]): r["full_rune_text"] for r in sheet("shaman_runes.csv")})
    texts.update({r["passive_name"]: r["full_text"] for r in sheet("shaman_passives.csv")})
    for name, sentence in texts.items():
        record = recs[index[name]]
        text = record["Description_Lang_enUS"] + record["AuraDescription_Lang_enUS"]
        assert text.strip(), "%s has no tooltip" % name
        # "${$x1-1}" is the client's own grammar for a computed number, not a leftover sheet token
        bare = re.sub(r"\$\{[^}]*\}", "", text)
        assert "{" not in bare and "NEW:" not in bare, "%s has a leftover token: %s" % (name, text[:80])
        if re.search(r"\{[a-z_]+(?::[a-z_]+)?\}", sentence):
            assert "$" in text, "%s: the sentence has placeholders and the tooltip has no variable" % name


def check_rulings(recs):
    index = ids()
    scale = rage_scale()
    sheet_costs = {r["skill_name"]: r["resource_cost"] for r in sheet("shaman_skills.csv")}
    assert {name for name, cost in sheet_costs.items() if cost} == set(SPENDERS), "the spenders are not the six"
    for name in PRIMARIES + ("Thunderstorm",):
        assert int(recs[index[name]]["ManaCost"]) == 0, "%s (a generator) costs Maelstrom" % name
    for name in SPENDERS:
        record = recs[index[name]]
        assert int(record["PowerType"]) == RAGE and int(record["ManaCost"]) == round(float(sheet_costs[name]) * scale), name
    for name in ("Ghost Wolf", "Elemental Shield", "Purge", "Earthbind Totem", "Healing Stream Totem", "Tempest Totem",
                 "Spirit Link", "Call of the Ancestors", "Spirit Wolves", "Bloodlust", "Fire Elemental", "Earth Elemental",
                 "Ascendance"):
        assert int(recs[index[name]]["ManaCost"]) == 0, "%s is a cooldown-only skill and costs Maelstrom" % name
    assert int(recs[index["Healing Stream Totem - Ancestral Protection"]]["RecoveryTime"]) == 90 * 1000


def check_mask(recs):
    """The class's regeneration mask: a hidden record that stops the core's own Rage tick."""
    index = ids()
    name = "Shaman - resource pulse - core regeneration mask"
    assert name in index, "no regeneration mask record"
    record = recs[index[name]]
    assert HELPERS[0] <= int(record["ID"]) <= HELPERS[1], "the mask sits outside the helper block"
    assert int(record["EffectAura_1"]) == PREVENT_REGENERATE_POWER, record["EffectAura_1"]
    assert int(record["EffectMiscValue_1"]) == RAGE + 1, "the mask is not on the Rage slot"


def targeting():
    return {r["skill"]: r for r in read(D3 / "skill_targeting.csv")}


class Records(unittest.TestCase):
    def test_every_sheet_row_has_one_record_in_the_block(self):
        check_manifest(manifest())
        skills, runes, passives = expected_names()
        self.assertEqual((len(skills), len(runes), len(passives)), (24, 120, 20))
        mine = [row for row in manifest() if FIRST <= int(row["spell_id"]) <= LAST]
        self.assertEqual([len([r for r in mine if r["kind"] == kind]) for kind in ("active", "rune", "passive")],
                         [24, 120, 20])

    def test_the_records_say_what_the_sheets_say(self):
        check_records(records())

    def test_the_rulings_hold(self):
        check_rulings(records())

    def test_the_class_has_its_regeneration_mask(self):
        check_mask(records(HELPERS[0], HELPERS[1]))

    def test_maelstrom_is_a_registry_row_at_one_unit_a_point(self):
        self.assertEqual(rage_scale(), 1.0)

    def test_every_element_cell_is_a_school(self):
        # the catalogue colours a skill and a rune from this cell and the record's school mask is built from it, so a cell
        # that names none (the draft's blank, Attuned, Copied) is resolved in the sheet
        for name in ("shaman_skills.csv", "shaman_runes.csv"):
            for row in sheet(name):
                self.assertIn(row["element"], SCHOOLS, (name, row.get("skill_name"), row.get("rune_name")))

    def test_a_cell_that_named_no_element_keeps_its_skills(self):
        skills = {r["skill_name"]: r["element"] for r in sheet("shaman_skills.csv")}
        research = REPO / "docs" / "research" / "shaman"
        for row, was in zip(sheet("shaman_runes.csv"), read(research / "shaman_runes.tokenised.csv")):
            if was["element"] == "":
                key = SHARED_KEY if was["skill_name"] == "Earthquake" else was["skill_name"]
                self.assertEqual(row["element"], skills[key], (row["skill_name"], row["rune_name"]))
        resolved = {r["skill_name"]: r["element"] for r in sheet("shaman_skills.csv")}
        self.assertEqual((resolved["Elemental Blast"], resolved["Call of the Ancestors"]), ("Lightning", "Physical"))

    def test_the_stormcaller_and_earth_shock_generation_cells_parse_and_the_number_is_the_values_sheets(self):
        for skill, rune in (("Lightning Bolt", "Stormcaller"), ("Flame Shock", "Earth Shock")):
            row = next(r for r in sheet("shaman_runes.csv") if (r["skill_name"], r["rune_name"]) == (skill, rune))
            self.assertEqual(generate_spells.rune_modifiers(row["modified_cost_cooldown_damage"]).get("generation"), 16.0)
            values = [r for r in sheet("shaman_skill_values.csv")
                      if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (skill, rune, "generated_resource", "new")]
            self.assertEqual([r["value"] for r in values], ["16"])

    def test_wind_rushs_recharge_has_its_placeholder(self):
        row = next(r for r in sheet("shaman_runes.csv") if (r["skill_name"], r["rune_name"]) == ("Ghost Wolf", "Wind Rush"))
        self.assertIn("{charge_recharge_seconds}", row["full_rune_text"])
        self.assertIn("{charge_count}", row["full_rune_text"])
        values = {r["token"]: r["value"] for r in sheet("shaman_skill_values.csv")
                  if (r["skill"], r["rune"]) == ("Ghost Wolf", "Wind Rush")}
        self.assertEqual(values, {"charge_count": "2", "charge_recharge_seconds": "12"})
        index = ids()
        text = records()[index["Ghost Wolf - Wind Rush"]]["Description_Lang_enUS"]
        self.assertIn("$", text)
        self.assertNotIn("{", text)

    def test_the_cast_ranges_are_the_sheets_flagged_defaults(self):
        rows = targeting()
        for skill in ("Lightning Bolt", "Chain Lightning", "Lava Burst", "Elemental Blast", "Purge", "Spirit Link"):
            self.assertEqual(rows[skill]["range_yards"], "30", skill)
            self.assertIn("range", rows[skill]["unsure"], skill)
        for skill in ("Frost Lance", "Spirit Wolves"):
            self.assertEqual(rows[skill]["target_type"], "line_pierce", skill)
            self.assertEqual(rows[skill]["width_yards"], "3", skill)
            self.assertIn("width", rows[skill]["unsure"], skill)

    def test_the_rendered_targeting_follows_the_sheet(self):
        # the sheet is what the server reads: the skill's record and its runes' carry the sheet's numbers
        sql = (GENERATED / "spell_shells.sql").read_text(encoding="utf-8")
        for skill, kind, value in (("Frost Lance", "line_pierce", "'NUMERIC',30.0,0.0,3.0)"),
                                   ("Lightning Bolt", "single_enemy", "'NUMERIC',30.0,0.0,0.0)")):
            self.assertEqual(targeting()[skill]["target_type"], kind)
            self.assertIn("'%s',%s" % (kind, value), sql, skill)

    def test_no_new_token_is_left(self):
        for name in ("shaman_skills.csv", "shaman_runes.csv", "shaman_passives.csv",
                     "shaman_skill_values.csv", "shaman_passive_values.csv"):
            self.assertNotIn("NEW:", (D3 / name).read_text(encoding="utf-8"), name)

    def test_the_shared_name_is_keyed_by_its_class_and_shown_plain(self):
        # records, the id manifest, the value map and the catalogue labels are keyed by name, so the Shaman's Earthquake carries
        # its class in the key and the player reads the plain name (shown_names.csv); the Barbarian's keeps the bare key
        skills, runes, passives = expected_names()
        for stem in ("barbarian", "wizard", "monk", "crusader", "necromancer", "demon_hunter", "witch_doctor"):
            theirs = {r["skill_name"] for r in sheet("%s_skills.csv" % stem)}
            theirs |= {r["passive_name"] for r in sheet("%s_passives.csv" % stem)}
            self.assertEqual(set(skills + passives) & theirs, set(), stem)
        self.assertIn("Earthquake", {r["skill_name"] for r in sheet("barbarian_skills.csv")})
        self.assertNotIn("Earthquake", skills)
        self.assertIn(SHARED_KEY, skills)
        row = next(r for r in sheet("shown_names.csv") if r["key"] == SHARED_KEY)
        self.assertEqual((row["kind"], row["shown_name"]), ("skill", SHARED_SHOWN))
        index, recs = ids(), records()
        self.assertEqual(recs[index[SHARED_KEY]]["Name_Lang_enUS"], SHARED_SHOWN)
        self.assertEqual(recs[index["Earthquake (Shaman) - Aftershock"]]["Name_Lang_enUS"], "Earthquake - Aftershock")
        barbarian = generate_spells.CLASS_BLOCKS["barbarian"].records
        own = next(int(r["spell_id"]) for r in manifest() if r["name"] == "Earthquake" and r["kind"] == "active")
        self.assertTrue(barbarian[0] <= own <= barbarian[1])
        self.assertEqual(records(own, own)[own]["Name_Lang_enUS"], "Earthquake")
        for table in ("skill_targeting.csv", "shaman_skill_values.csv", "shaman_visuals.csv"):
            keys = {r.get("skill") or r.get("d3_skill") for r in sheet(table)}
            self.assertIn(SHARED_KEY, keys, table)

    def test_the_research_sheets_are_the_data_sheets_but_for_the_noted_changes(self):
        research = REPO / "docs" / "research" / "shaman"
        # the passives and their values are copied unchanged
        for data, source in (("shaman_passives.csv", "shaman_passives.tokenised.csv"),
                             ("shaman_passive_values.csv", "shaman_passive_values.csv")):
            self.assertEqual((D3 / data).read_bytes(), (research / source).read_bytes(), data)
        # the other sheets differ in the Earthquake key, the resolved element cells and Wind Rush's placeholder, nowhere else
        for data, source, key_column in (("shaman_skills.csv", "shaman_skills.tokenised.csv", "skill_name"),
                                         ("shaman_runes.csv", "shaman_runes.tokenised.csv", "skill_name"),
                                         ("shaman_skill_values.csv", "shaman_skill_values.csv", "skill"),
                                         ("shaman_visuals.csv", "shaman_visuals.csv", "d3_skill")):
            ours, theirs = read(D3 / data), read(research / source)
            self.assertEqual(len(ours), len(theirs), data)
            for a, b in zip(ours, theirs):
                for column in b:
                    if a[column] == b[column]:
                        continue
                    if column == key_column:
                        self.assertEqual((b[column], a[column]), ("Earthquake", SHARED_KEY), (data, column))
                    elif column == "element":
                        self.assertIn(b[column], ("", "Attuned", "Copied"), (data, b))
                    elif column == "notes":
                        self.assertTrue(a[column].startswith(b[column]), (data, b["skill_name"]))
                    elif column == "full_rune_text":
                        self.assertEqual((b["skill_name"], b["rune_name"]), ("Ghost Wolf", "Wind Rush"))
                    else:
                        self.fail((data, column, a[column], b[column]))
        self.assertEqual(len(read(research / "shaman_targeting.csv")), 24)

    def test_nothing_outside_the_blocks_moved(self):
        # The commit that brought the Shaman's records (combat_0125) against its parent: the same on nightly and on every
        # branch after it, since it compares two commits of history and not this tree with a fork point.
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
        wanted = {(r["skill"], r["rune"], r["token"], r["qualifier"]) for r in sheet("shaman_skill_values.csv")}
        wanted |= {(r["skill"], r.get("rune", ""), r["token"], r["qualifier"])
                   for r in sheet("shaman_passive_values.csv")}
        self.assertEqual(wanted - mapped, set())

    def test_the_cost_rows_name_the_power_they_are_paid_in(self):
        conversions = {}
        for r in read(GENERATED / "spell_value_map.csv"):
            if FIRST <= int(r["spell_id"]) <= LAST and r["token"] == "cost_resource":
                conversions.setdefault(r["skill"], set()).add(r["conversion"])
        self.assertEqual(set(conversions), set(SPENDERS))
        for skill, names in conversions.items():
            self.assertEqual(len(names), 1, skill)


class Picker(unittest.TestCase):
    def setUp(self):
        (self.rows, self.passives, self.labels, _, self.class_map, self.playable, self.waiting, _) = gcc.catalogue()
        self.mine = next(row[0] for row in self.class_map if row[2] == "Shaman")

    def test_the_shaman_is_playable_with_six_categories_24_skills_and_120_runes(self):
        self.assertIn("Shaman", self.playable)
        self.assertEqual(self.waiting, [])
        mine = [label for label in self.labels if label[1] == self.mine]
        skills = [label for label in mine if not label[3]]
        runes = [label for label in mine if label[3]]
        self.assertEqual((len(skills), len(runes)), (24, 120))
        categories = ("Primary", "Secondary", "Defensive", "Totems", "Ancestral", "Primal")
        self.assertEqual(sorted({label[4] for label in skills}), sorted(categories))
        self.assertEqual([len([s for s in skills if s[4] == c]) for c in categories], [4] * 6)
        self.assertEqual(len([p for p in self.passives if p[0] == self.mine]), 20)

    def test_the_category_order_is_the_briefs(self):
        self.assertEqual([category for cid, category, _ in gcc.category_orders(self.class_map) if cid == self.mine],
                         ["Primary", "Secondary", "Defensive", "Totems", "Ancestral", "Primal"])

    def test_each_entry_is_at_the_sheets_unlock_level_and_in_the_sheets_category(self):
        categories = {r["skill_name"]: r["category"] for r in sheet("shaman_skills.csv")}
        levels = {(r["skill_name"], ""): int(r["unlock_level"] or 1) for r in sheet("shaman_skills.csv")}
        levels.update({(r["skill_name"], r["rune_name"]): int(r["unlock_level"] or 1) for r in sheet("shaman_runes.csv")})
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

    def test_the_shown_name_reaches_the_picker_through_the_record(self):
        # dc_skillbar.lua reads the key from dc_class_label and the shown name from spell_dbc (xnrvn.5)
        label = next(l for l in self.labels if l[1] == self.mine and l[2] == SHARED_KEY and not l[3])
        self.assertEqual(label[4], "Secondary")
        self.assertEqual(records(label[0], label[0])[label[0]]["Name_Lang_enUS"], SHARED_SHOWN)


class ClientRow(unittest.TestCase):
    def test_the_client_class_row_carries_the_records_family(self):
        from dbc_store import Store, schema
        self.assertEqual({int(r["SpellClassSet"]) for r in records().values()}, {FAMILY})
        columns = schema(REPO, "chrclasses_dbc")
        client = Store((REPO / "client-patch/dbc/ChrClasses.dbc").read_bytes(), columns)
        self.assertEqual(client.decode(WOW_CLASS)["SpellClassSet"], FAMILY)
        self.assertEqual(client.decode(WOW_CLASS)["DisplayPower"], RAGE)

    def test_a_client_file_with_the_stock_family_gets_the_records_family(self):
        # The rule, not the committed file: the generator rewrites the client row it reads, so it is driven here with
        # a client ChrClasses.dbc whose row 7 still carries the stock Shaman's 11.
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

    def test_the_stock_row_keeps_the_shamans_family(self):
        # dc_classes.cpp strips the stock Shaman's spells by the server row's family, which is the stock extraction's
        import generate_class_creation as creation
        from dbc_store import Store, schema
        stock = Store((creation.STOCK / "ChrClasses.dbc").read_bytes(), schema(REPO, "chrclasses_dbc"))
        self.assertEqual(stock.decode(WOW_CLASS)["SpellClassSet"], STOCK_FAMILY)
        server = (MODULE / "data/sql/db-world/updates/world_0081_class_shaman.sql").read_text(encoding="utf-8")
        self.assertNotIn("chrclasses_dbc", server)


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

    def test_a_record_added_outside_the_shamans_blocks_is_seen(self):
        old, new = at_arrival("spell_shells.csv")
        old_rows, new_rows = list(csv.DictReader(old.splitlines())), list(csv.DictReader(new.splitlines()))
        template = new_rows[0]
        stray = new_rows + [dict(template, spell_id="84500")]
        self.assertEqual(moved_outside_the_blocks(old_rows, stray), [("outside every block", 84500)])
        taken = {int(r["spell_id"]) for r in new_rows}
        free = next(i for i in range(86000, 86200) if i not in taken)
        witch_doctor = new_rows + [dict(template, spell_id=str(free))]
        self.assertEqual(moved_outside_the_blocks(old_rows, witch_doctor), [("in another class's block", free)])
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
            check_manifest([r for r in manifest() if r["name"] != "Purge - Consuming Purge"])

    def test_a_renamed_record_is_seen(self):
        with self.assertRaises(AssertionError):
            check_manifest([dict(r, name="Purge!" if r["name"] == "Purge" else r["name"]) for r in manifest()])

    def test_a_record_outside_the_block_is_seen(self):
        with self.assertRaises(AssertionError):
            check_manifest([dict(r, spell_id=str(LAST + 200) if r["name"] == "Bloodlust" else r["spell_id"])
                            for r in manifest()])

    def test_the_shared_name_shown_with_its_suffix_is_seen(self):
        recs = records()
        identifier = ids()[SHARED_KEY]
        recs[identifier] = dict(recs[identifier], Name_Lang_enUS=SHARED_KEY)
        with self.assertRaises(AssertionError):
            check_records(recs)

    def test_a_cost_off_by_ten_is_seen(self):
        recs = records()
        identifier = ids()["Lava Burst"]
        recs[identifier] = dict(recs[identifier], ManaCost=str(int(recs[identifier]["ManaCost"]) * 10))
        with self.assertRaises(AssertionError):
            check_records(recs)

    def test_a_cost_paid_in_the_wrong_power_is_seen(self):
        for check in (check_records, check_rulings):
            recs = records()
            identifier = ids()["Searing Totem"]
            recs[identifier] = dict(recs[identifier], PowerType="0")
            with self.subTest(check=check.__name__), self.assertRaises(AssertionError):
                check(recs)

    def test_a_leftover_token_in_a_tooltip_is_seen(self):
        recs = records()
        identifier = ids()["Purge"]
        recs[identifier] = dict(recs[identifier], Description_Lang_enUS=recs[identifier]["Description_Lang_enUS"]
                                + " {duration_seconds}")
        with self.assertRaises(AssertionError):
            check_records(recs)

    def test_a_cost_on_a_primary_is_seen(self):
        recs = records()
        identifier = ids()["Lightning Bolt"]
        recs[identifier] = dict(recs[identifier], ManaCost="12")
        with self.assertRaises(AssertionError):
            check_rulings(recs)

    def test_a_cost_on_a_cooldown_only_skill_is_seen(self):
        recs = records()
        identifier = ids()["Bloodlust"]
        recs[identifier] = dict(recs[identifier], ManaCost="10", PowerType="1")
        with self.assertRaises(AssertionError):
            check_rulings(recs)

    def test_a_dropped_mask_is_seen(self):
        recs = records(HELPERS[0], HELPERS[1])
        identifier = ids()["Shaman - resource pulse - core regeneration mask"]
        for field, value in (("EffectAura_1", "0"), ("EffectMiscValue_1", "1")):
            doctored = dict(recs)
            doctored[identifier] = dict(recs[identifier], **{field: value})
            with self.subTest(field=field), self.assertRaises(AssertionError):
                check_mask(doctored)
        with self.assertRaises(KeyError):
            check_mask({k: v for k, v in recs.items() if k != identifier})

    def test_a_cooldown_rune_that_lost_its_timer_is_seen(self):
        recs = records()
        identifier = ids()["Healing Stream Totem - Ancestral Protection"]
        recs[identifier] = dict(recs[identifier], RecoveryTime="30000")
        with self.assertRaises(AssertionError):
            check_rulings(recs)


if __name__ == "__main__":
    unittest.main()
