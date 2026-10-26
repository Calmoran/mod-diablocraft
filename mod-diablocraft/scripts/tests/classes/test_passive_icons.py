"""Every class passive has its own icon (the Skills window's passive slots).

Every passive's spell record is a copy of one plain passive (generate_spells.py PASSIVE_BASE_SPELL, the stock Dodge), so every
passive of every class drew that one icon, a face, in the Skills window and the passive picker (Wizard seen first, then every
class). data/d3/passive_icons.csv now names a stock client icon for each passive; the generator looks it up in SpellIcon.dbc and
writes it as the record's SpellIconID.

What this proves, and how:

  * **The sheet is complete and exact.** Every passive of every class's *_passives.csv has exactly one row of passive_icons.csv,
    and every row names a passive that exists (no one left on the shared icon, no stray row).
  * **The generated records wear them.** For each of the passives, the SpellIconID of its record in
    data/generated/spell_shells.sql is the SpellIcon.dbc id of the icon the sheet names (read from the server's own SpellIcon.dbc),
    not the base spell's icon.
  * **No two share one.** The icon ids of all the passives are distinct, class by class and across classes, and none is the base
    spell's.
  * **The newest combat migration carries them**: its record for each passive has the same icon id as spell_shells.sql.

Not proven here: how an icon looks in the client (the Skills window's checks are the designer's), and that Spell.dbc in patch-4.MPQ holds
them (the archive is rebuilt by the PM; this reads the generated server render).

    python mod-diablocraft/scripts/tests/classes/test_passive_icons.py
"""

import csv
import re
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
DBC = REPO / "azerothcore-wotlk/build/server/data/dbc"
ICON_FIELD = 133              # generate_spells.py F_SPELL_ICON
BASE_PASSIVE = 81             # generate_spells.py PASSIVE_BASE_SPELL


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def sheets():
    """class stem -> its passive names, from the class sheets."""
    return {p.name[:-len("_passives.csv")]: [r["passive_name"] for r in read(p)] for p in sorted(D3.glob("*_passives.csv"))}


def icon_ids():
    """The lower-cased icon file name -> its SpellIcon.dbc id, from the server's own SpellIcon.dbc."""
    data = (DBC / "SpellIcon.dbc").read_bytes()
    _magic, count, _fields, size, _strings = struct.unpack("<4sIIII", data[:20])
    strings = data[20 + count * size:]
    out = {}
    for index in range(count):
        record = data[20 + index * size:20 + (index + 1) * size]
        spell_icon, offset = struct.unpack_from("<II", record)
        path = strings[offset:strings.index(b"\0", offset)].decode().lower()
        out[path.rpartition("\\")[2]] = spell_icon
    return out


def base_icon():
    data = (DBC / "Spell.dbc").read_bytes()
    _magic, count, fields, size, _strings = struct.unpack("<4sIIII", data[:20])
    for index in range(count):
        record = data[20 + index * size:20 + (index + 1) * size]
        if struct.unpack_from("<I", record)[0] == BASE_PASSIVE:
            return struct.unpack_from("<I", record, ICON_FIELD * 4)[0]
    raise AssertionError("no base passive record")


def record_icons(path):
    """spell id -> SpellIconID of every record of a generated spell_dbc render."""
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"\((\d+),", line)
        if match:
            out[int(match.group(1))] = int(line.split(",", ICON_FIELD + 1)[ICON_FIELD])
    return out


def passive_ids():
    """passive name -> its spell id, from the generated shell list."""
    return {r["name"]: int(r["spell_id"]) for r in read(MODULE / "data/generated/spell_shells.csv") if r["kind"] == "passive"}


def newest_combat_migration():
    return sorted((MODULE / "data/sql/db-world/updates").glob("combat_*.sql"))[-1]


def problems(passives, rows, ids, records, base):
    """What is wrong with the passives' icons: the sheet's coverage, each record's icon, sharing."""
    found = []
    named = [(r["class"], r["passive_name"]) for r in rows]
    wanted = [(stem, name) for stem, names in passives.items() for name in names]
    if sorted(named) != sorted(wanted):
        found.append("the sheet does not name each passive once: missing %s, extra %s" % (
            sorted(set(wanted) - set(named))[:3], sorted(set(named) - set(wanted))[:3]))
    icon_of = {r["passive_name"]: r["icon_name"].lower() for r in rows}
    seen = {}
    for stem, name in wanted:
        spell = ids.get(name)
        if spell is None or name not in icon_of:
            found.append("%s: no record or no icon row" % name)
            continue
        have = records.get(spell)
        if have is None or icon_of[name] not in ids["__icons__"] or have != ids["__icons__"][icon_of[name]]:
            found.append("%s: the record wears icon %s, the sheet names %s" % (name, have, icon_of[name]))
        if have == base:
            found.append("%s: still the base passive's icon" % name)
        if have in seen:
            found.append("%s and %s share icon %s" % (name, seen[have], have))
        seen[have] = name
    return found


class PassiveIcons(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (DBC / "SpellIcon.dbc").is_file() or not (DBC / "Spell.dbc").is_file():
            raise unittest.SkipTest("no server DBCs on this machine")
        cls.passives = sheets()
        cls.rows = read(D3 / "passive_icons.csv")
        cls.ids = dict(passive_ids())
        cls.ids["__icons__"] = icon_ids()
        cls.records = record_icons(MODULE / "data/generated/spell_shells.sql")
        cls.base = base_icon()

    def check(self, **change):
        args = dict(passives=self.passives, rows=self.rows, ids=self.ids, records=self.records, base=self.base)
        args.update(change)
        return problems(**args)

    def test_the_eight_classes_and_151_passives(self):
        self.assertEqual(len(self.passives), 8)
        self.assertEqual(sum(len(v) for v in self.passives.values()), 151)

    def test_every_passive_has_its_own_icon_in_its_record(self):
        self.assertEqual(self.check(), [])

    def test_the_newest_combat_migration_carries_them(self):
        migration = record_icons(newest_combat_migration())
        for name, spell in passive_ids().items():
            self.assertEqual(migration.get(spell), self.records[spell], "%s in %s" % (name, newest_combat_migration().name))

    def test_one_icon_for_all_is_caught(self):
        every = {spell: self.base for spell in self.records}
        self.assertTrue(self.check(records=every), "every record on the base icon was not caught")

    def test_two_passives_on_one_icon_are_caught(self):
        records = dict(self.records)
        first, second = passive_ids()["Blur"], passive_ids()["Evocation"]
        records[second] = records[first]
        self.assertTrue(any("share" in p or "sheet names" in p for p in self.check(records=records)))

    def test_one_passive_left_on_the_base_icon_is_caught(self):
        records = dict(self.records)
        records[passive_ids()["Power Hungry"]] = self.base
        self.assertTrue(self.check(records=records))

    def test_a_passive_missing_from_the_sheet_or_an_extra_row_is_caught(self):
        self.assertTrue(self.check(rows=[r for r in self.rows if r["passive_name"] != "Blur"]))
        self.assertTrue(self.check(rows=self.rows + [{"class": "wizard", "passive_name": "Nothing", "icon_name": "Spell_Fire_Fire"}]))

    def test_a_record_that_wears_another_icon_than_the_sheet_names_is_caught(self):
        records = dict(self.records)
        records[passive_ids()["Blur"]] = self.records[passive_ids()["Evocation"]] + 100000
        self.assertTrue(self.check(records=records))


if __name__ == "__main__":
    unittest.main()
