"""Every skill, rune and passive of the Monk and the Necromancer has its record, its tooltip and its place in the picker.

One file for both classes (the Monk's and the Necromancer's tests were the same checks with other names and numbers); each class is a
`ClassSpec` and runs the same tests.

  * **A record per sheet row.** `<class>_skills.csv`, `_runes.csv` and `_passives.csv` each have exactly one record in the generated
    manifest (spell_shells.csv), named "Skill", "Skill - Rune" or the passive's name, inside the class's reserved block
    (generate_spells.py CLASS_BLOCKS); no other class's record sits there.
  * **The record is the sheet.** Read back from the spell_dbc rows the generator wrote (spell_shells.sql): the name, the class's
    spell family, a skill's cooldown in RecoveryTime and its cost in Runic Power units (PowerType 6, ManaCost = cost x the
    resource's storage_scale; Life costs are test_life_costs.py's), and a tooltip that is non-empty, has no unfilled "{token}" or
    "NEW:" in it and carries the "$" variable of every placeholder the sheet's sentence has.
  * **The numbers are the sheet's.** Every row of the class's skill and passive values sheets has its row in the value map
    (spell_value_map.csv) for the record that states it (proc coefficients are module-read and have none).
  * **The picker.** The class catalogue (generate_class_catalogue.catalogue()) lists the class's skills and runes in its six
    categories, each at the sheet's unlock level, plus its passives.
  * **Nothing else moved.** Against the last commit the branch shares with nightly, the manifest rows outside the class's block are
    unchanged (the Monk's rule: the ids below its block; the Necromancer's: every old id, and a new one only in some class's blocks).
  * **The Necromancer's client class row** carries the records' family, and its server row keeps the Warlock's 5.
  * **A planted difference is seen**: a record dropped, renamed, moved out of the block, a cost off by ten, a leftover token.

What it does not prove: that the client draws the icons or that a tooltip reads well in game (the test sheets' Checks), or that a
cast does anything.

    python mod-diablocraft/scripts/tests/classes/test_class_records.py
"""

import csv
import re
import subprocess
import sys
import unittest
from collections import namedtuple
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
GENERATED = MODULE / "data" / "generated"
sys.path.insert(0, str(MODULE / "scripts"))

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_class_catalogue as gcc  # noqa: E402
import generate_spells  # noqa: E402

RUNIC_POWER = 6

ClassSpec = namedtuple("ClassSpec", "name stem first last family counts categories picked scale moved dropped renamed outside costed bad_cost tokened nothing_waits")


def monk_scale():
    """Slot units per Spirit point, the registry's (one since class powers P2)."""
    import generate_class_resources
    return next(e["scale"] for e in generate_class_resources.registry() if e["key"] == "spirit")


def necromancer_scale():
    """Runic Power units per Essence point, from data/tunables/class_resources.csv (not the generator)."""
    path = MODULE / "data" / "tunables" / "class_resources.csv"
    with path.open(encoding="utf-8-sig", newline="") as stream:
        row = next(r for r in csv.DictReader(stream) if (r["d3_class"], r["resource_key"]) == ("Necromancer", "essence"))
    return float(row["storage_scale"])


MONK = ClassSpec(
    name="Monk", stem="monk", first=83650, last=83849, family=22, counts=(22, 110, 18),
    categories=["Primary", "Secondary", "Defensive", "Techniques", "Focus", "Mantras"], picked=132, scale=monk_scale,
    moved="below", dropped="Fists of Thunder - Wind Blast", renamed=("Fists of Thunder", "Fists of Thunders"), outside="Serenity",
    costed="Lashing Tail Kick", bad_cost="500", tokened="Dashing Strike", nothing_waits=False)
NECROMANCER = ClassSpec(
    name="Necromancer", stem="necromancer", first=85100, last=85299, family=23, counts=(21, 105, 20),
    categories=["Primary", "Secondary", "Corpses", "Reanimation", "Curses", "Blood & Bone"], picked=126, scale=necromancer_scale,
    moved="all", dropped="Bone Spikes - Path of Bones", renamed=("Bone Spear", "Bone Spear!"), outside="Simulacrum",
    costed="Skeletal Mage", bad_cost="400", tokened="Bone Spear", nothing_waits=True)   # 40 Essence at one unit a point: the old ten-a-point 400 is caught
SPECS = (MONK, NECROMANCER)
HELPER_BLOCKS = {"Necromancer": (85300, 85399)}


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def sheet(name):
    return read(D3 / name)


def manifest():
    return read(GENERATED / "spell_shells.csv")


def split_values(text):
    """The comma-separated SQL values of one row, strings and all."""
    out, current, quoted, index = [], [], False, 0
    while index < len(text):
        char = text[index]
        if quoted:
            if char == "\\" and index + 1 < len(text):
                current.append(text[index + 1])
                index += 1
            elif char == "'" and text[index + 1:index + 2] == "'":
                current.append("'")
                index += 1
            elif char == "'":
                quoted = False
            else:
                current.append(char)
        elif char == "'":
            quoted = True
        elif char == ",":
            out.append("".join(current))
            current = []
        else:
            current.append(char)
        index += 1
    out.append("".join(current))
    return out


def records(spec):
    """{spell id: {column: value}} of the class's block, from the SQL the generator wrote."""
    text = (GENERATED / "spell_shells.sql").read_text(encoding="utf-8")
    out = {}
    for insert in text.split("INSERT INTO `spell_dbc`")[1:]:
        header, _, body = insert.partition("VALUES")
        columns = re.findall(r"`(\w+)`", header)
        for line in body.splitlines():
            match = re.match(r"^\((\d+),(.*)\)[,;]$", line)
            if match and spec.first <= int(match.group(1)) <= spec.last:
                values = split_values(match.group(1) + "," + match.group(2))
                out[int(match.group(1))] = dict(zip(columns, values))
    return out


def expected_names(spec):
    skills = [r["skill_name"] for r in sheet("%s_skills.csv" % spec.stem)]
    runes = ["%s - %s" % (r["skill_name"], r["rune_name"]) for r in sheet("%s_runes.csv" % spec.stem)]
    passives = [r["passive_name"] for r in sheet("%s_passives.csv" % spec.stem)]
    return skills, runes, passives


def check_manifest(spec, rows):
    """Raises AssertionError unless the manifest holds each sheet row once, in the class's block."""
    skills, runes, passives = expected_names(spec)
    by_name = {}
    for row in rows:
        if spec.first <= int(row["spell_id"]) <= spec.last:
            by_name.setdefault(row["name"], []).append(row)
    for name, kind in ([(n, "active") for n in skills] + [(n, "rune") for n in runes] + [(n, "passive") for n in passives]):
        found = by_name.get(name, [])
        assert len(found) == 1, "%s: %d records in the %s's block" % (name, len(found), spec.name)
        assert found[0]["kind"] == kind, "%s is a %s, not a %s" % (name, found[0]["kind"], kind)
    for row in rows:
        if row["kind"] in ("active", "rune", "passive") and row["name"] in set(skills + runes + passives):
            assert spec.first <= int(row["spell_id"]) <= spec.last, "%s sits outside the %s's block" % (row["name"], spec.name)


def check_records(spec, recs):
    skills = {r["skill_name"]: r for r in sheet("%s_skills.csv" % spec.stem)}
    ids = {row["name"]: int(row["spell_id"]) for row in manifest()}
    for name, row in skills.items():
        record = recs[ids[name]]
        assert record["Name_Lang_enUS"] == name, name
        assert int(record["SpellClassSet"]) == spec.family, (name, record["SpellClassSet"])
        cost = float(row["resource_cost"] or 0)
        if cost:
            assert int(record["PowerType"]) == RUNIC_POWER, name
            assert int(record["ManaCost"]) == round(cost * spec.scale()), (name, record["ManaCost"], cost)
        cooldown = float(row["cooldown_seconds"] or 0)
        if cooldown:
            assert int(record["RecoveryTime"]) == round(cooldown * 1000), (name, record["RecoveryTime"])
    texts = {}
    for r in sheet("%s_skills.csv" % spec.stem):
        texts[r["skill_name"]] = r["full_tooltip_text"]
    for r in sheet("%s_runes.csv" % spec.stem):
        texts["%s - %s" % (r["skill_name"], r["rune_name"])] = r["full_rune_text"]
    for r in sheet("%s_passives.csv" % spec.stem):
        texts[r["passive_name"]] = r.get("full_tooltip_text") or r.get("full_passive_text") or ""
    for name, sentence in texts.items():
        record = recs[ids[name]]
        shown = record["Description_Lang_enUS"] + record["AuraDescription_Lang_enUS"]
        assert shown.strip(), "%s has no tooltip" % name
        # "${$x1-1}" is the client's own grammar for a computed number, not a leftover sheet token
        bare = re.sub(r"\$\{[^}]*\}", "", shown)
        assert "{" not in bare and "NEW:" not in bare, "%s has a leftover token: %s" % (name, shown[:80])
        if re.search(r"\{[a-z_]+(?::[a-z_]+)?\}", sentence):
            assert "$" in shown, "%s: the sentence has placeholders and the tooltip has no variable" % name


class Records:
    SPEC = None

    def test_every_sheet_row_has_one_record_in_the_block(self):
        spec = self.SPEC
        check_manifest(spec, manifest())
        skills, runes, passives = expected_names(spec)
        self.assertEqual((len(skills), len(runes), len(passives)), spec.counts)
        mine = [row for row in manifest() if spec.first <= int(row["spell_id"]) <= spec.last]
        for kind, count in zip(("active", "rune", "passive"), spec.counts):
            self.assertEqual(len([r for r in mine if r["kind"] == kind]), count, kind)

    def test_the_records_say_what_the_sheets_say(self):
        check_records(self.SPEC, records(self.SPEC))

    def test_nothing_outside_the_block_moved(self):
        spec = self.SPEC
        # Against the last commit this branch shares with nightly: records nightly gained since are not this branch's to hold.
        fork = subprocess.run(["git", "merge-base", "HEAD", "nightly"], cwd=REPO, capture_output=True, text=True)
        if fork.returncode != 0:
            self.skipTest("no nightly ref to compare with")
        base = subprocess.run(["git", "show", fork.stdout.strip() + ":mod-diablocraft/data/generated/spell_shells.csv"], cwd=REPO,
                              capture_output=True, text=True)
        if base.returncode != 0:
            self.skipTest("no nightly ref to compare with")
        old = {r["spell_id"]: r for r in csv.DictReader(base.stdout.splitlines())}
        new = {r["spell_id"]: r for r in manifest()}
        if spec.moved == "below":
            # Moved, not added: a later bead's new helper below the block (diablocraft-dupme's Barbarian mask, 82419) moves nothing.
            self.assertEqual({k: v for k, v in old.items() if int(k) < spec.first}, {k: new.get(k) for k in old if int(k) < spec.first})
        else:
            self.assertEqual(old, {k: new.get(k) for k in old})
            # Added since the fork: only into a class's own blocks (this one's, or a later class's).
            blocks = [r for block in generate_spells.CLASS_BLOCKS.values() for r in (block.records, block.helpers)]
            # (a legendary's power record, `power_buff`, is a row of legendary_power_buffs.csv and sits in no class block)
            added = sorted(int(k) for k in set(new) - set(old) if new[k]["kind"] != "power_buff")
            self.assertEqual([k for k in added if not any(first <= k <= last for first, last in blocks)], [])

    def test_every_value_row_is_in_the_value_map(self):
        spec = self.SPEC
        mapped = {(r["skill"], r["rune"], r["token"], r["qualifier"])
                  for r in read(GENERATED / "spell_value_map.csv") if spec.first <= int(r["spell_id"]) <= spec.last}
        wanted = {(r["skill"], r["rune"], r["token"], r["qualifier"]) for r in sheet("%s_skill_values.csv" % spec.stem)}
        # a passive's rows are keyed by the passive's name in the skill column
        wanted |= {(r["passive"] if "passive" in r else r.get("skill", ""), r.get("rune", ""), r["token"], r["qualifier"])
                   for r in sheet("%s_passive_values.csv" % spec.stem)}
        # module-read tokens (proc coefficients, the Spirit regen sources the module ticks) have no record field
        missing = {key for key in wanted - mapped if key[2] != "proc_coefficient"}
        self.assertEqual(missing, set())


class Picker:
    SPEC = None

    def setUp(self):
        (self.rows, self.passives, self.labels, _, self.class_map, self.playable, self.waiting, _) = gcc.catalogue()
        self.mine = next(row[0] for row in self.class_map if row[2] == self.SPEC.name)

    def test_the_class_is_playable_with_six_categories_and_its_skills_and_runes(self):
        spec = self.SPEC
        self.assertIn(spec.name, self.playable)
        self.assertNotIn(spec.name, self.waiting)
        if spec.nothing_waits:   # a class with sheets and no shells is absent rather than half-present: none may wait
            self.assertEqual(self.waiting, [])
        mine = [label for label in self.labels if label[1] == self.mine]
        skills = [label for label in mine if not label[3]]
        runes = [label for label in mine if label[3]]
        self.assertEqual((len(skills), len(runes)), spec.counts[:2])
        self.assertEqual(sorted({label[4] for label in skills}), sorted(spec.categories))
        self.assertEqual(len([p for p in self.passives if p[0] == self.mine]), spec.counts[2])

    def test_each_entry_is_at_the_sheets_unlock_level_and_in_the_sheets_category(self):
        spec = self.SPEC
        categories = {r["skill_name"]: r["category"] for r in sheet("%s_skills.csv" % spec.stem)}
        levels = {("%s" % r["skill_name"], ""): int(r["unlock_level"] or 1) for r in sheet("%s_skills.csv" % spec.stem)}
        levels.update({(r["skill_name"], r["rune_name"]): int(r["unlock_level"] or 1) for r in sheet("%s_runes.csv" % spec.stem)})
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
        self.assertEqual(checked, spec.picked)


class Mutants:
    """The checks above must fail on a planted difference; each is run on a doctored copy."""
    SPEC = None

    def test_a_dropped_record_is_seen(self):
        rows = [r for r in manifest() if r["name"] != self.SPEC.dropped]
        with self.assertRaises(AssertionError):
            check_manifest(self.SPEC, rows)

    def test_a_renamed_record_is_seen(self):
        old, new = self.SPEC.renamed
        rows = [dict(r, name=new if r["name"] == old else r["name"]) for r in manifest()]
        with self.assertRaises(AssertionError):
            check_manifest(self.SPEC, rows)

    def test_a_record_outside_the_block_is_seen(self):
        rows = [dict(r, spell_id=str(self.SPEC.last + 100) if r["name"] == self.SPEC.outside else r["spell_id"]) for r in manifest()]
        with self.assertRaises(AssertionError):
            check_manifest(self.SPEC, rows)

    def test_a_cost_off_by_ten_is_seen(self):
        recs = records(self.SPEC)
        ids = {row["name"]: int(row["spell_id"]) for row in manifest()}
        recs[ids[self.SPEC.costed]] = dict(recs[ids[self.SPEC.costed]], ManaCost=self.SPEC.bad_cost)
        with self.assertRaises(AssertionError):
            check_records(self.SPEC, recs)

    def test_a_leftover_token_in_a_tooltip_is_seen(self):
        recs = records(self.SPEC)
        ids = {row["name"]: int(row["spell_id"]) for row in manifest()}
        record = dict(recs[ids[self.SPEC.tokened]])
        record["Description_Lang_enUS"] = record["Description_Lang_enUS"] + " {damage_pct}"
        recs[ids[self.SPEC.tokened]] = record
        with self.assertRaises(AssertionError):
            check_records(self.SPEC, recs)


for _spec in SPECS:
    for _kind in (Records, Picker, Mutants):
        _name = "%s%s" % (_spec.name, _kind.__name__)
        globals()[_name] = type(_name, (_kind, unittest.TestCase), {"SPEC": _spec})
del _spec, _kind, _name


class NecromancerClientRow(unittest.TestCase):
    CLASS_ID = 13

    def test_the_client_class_row_carries_the_records_family(self):
        from dbc_store import Store, schema
        families = {int(r["SpellClassSet"]) for r in records(NECROMANCER).values()}
        self.assertEqual(families, {NECROMANCER.family})
        client = Store((REPO / "client-patch/dbc/ChrClasses.dbc").read_bytes(), schema(REPO, "chrclasses_dbc"))
        self.assertEqual(client.decode(self.CLASS_ID)["SpellClassSet"], NECROMANCER.family)
        # the server row keeps the Warlock's 5: dc_classes.cpp strips the parent's stock spells by it
        server = (MODULE / "data/sql/db-world/updates/world_0059_class_necromancer.sql").read_text(encoding="utf-8")
        header, _, row = server.split("INSERT INTO `chrclasses_dbc` ", 1)[1].partition(" VALUES\n(")
        values = split_values(row.split(");", 1)[0])
        self.assertEqual(int(values[re.findall(r"`(\w+)`", header).index("SpellClassSet")]), 5)


if __name__ == "__main__":
    unittest.main()
