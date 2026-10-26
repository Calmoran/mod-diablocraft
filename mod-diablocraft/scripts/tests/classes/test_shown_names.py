"""The name a passive shows is not its key (diablocraft-kev3m; ruling 2026-10-21, q-1021-47 (b)).

The Demon Hunter's passive is keyed `Leech (Demon Hunter)` because the Necromancer's skill Leech holds the plain name, and
the key is what the sheets, the value map, the generated shells, the saved bar and the picker's messages use. The player
reads the plain `Leech`. data/d3/shown_names.csv names the one row; the generator writes it as the record's Spell.dbc /
spell_dbc name, and dc_skillbar.lua's picker and bar read the record's name for the text and keep the key for every lookup.

What this proves, over the files the generator wrote:

  * both records read `Leech`: the Demon Hunter's passive and the Necromancer's skill, each under its own id and its own key;
  * no other record's name moved: every record's name equals its key in the shells manifest except the sheet's rows (and the
    two elite affix slows, whose own shown name is older than this sheet);
  * the sheet's rows are real: each key is a passive in the manifest and shows a different name, and no row is listed twice;
  * the picker's query returns the record's name beside the key and draws it, the saved pick and the lookups keep the key,
    and the server's lookups stay keyed (K3).

    python mod-diablocraft/scripts/tests/classes/test_shown_names.py
"""
import csv
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import test_demon_hunter_records as dh  # noqa: E402

MODULE = dh.MODULE
GENERATED = MODULE / "data" / "generated"
SHOWN = MODULE / "data" / "d3" / "shown_names.csv"
SKILLBAR = (MODULE / "lua/aio/dc_skillbar.lua").read_text(encoding="utf-8")
CLASSES = (MODULE / "src/classes/dc_classes.cpp").read_text(encoding="utf-8")
AFFIX_SLOW = {"affix slow"}


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def record_names(generated=GENERATED):
    """{spell id: Name_Lang_enUS} of every record in the generated spell SQL."""
    out = {}
    text = (generated / "spell_shells.sql").read_text(encoding="utf-8")
    for insert in text.split("INSERT INTO `spell_dbc`")[1:]:
        header, _, body = insert.partition("VALUES")
        columns = re.findall(r"`(\w+)`", header)
        at = columns.index("Name_Lang_enUS")
        for line in body.splitlines():
            match = re.match(r"^\((\d+),(.*)\)[,;]$", line)
            if match:
                out[int(match.group(1))] = dh.split_values(match.group(1) + "," + match.group(2))[at]
    return out


def manifest():
    return read(GENERATED / "spell_shells.csv")


def lines_of(text, start, end):
    return text[text.index(start):text.index(end, text.index(start))]


class ShownNames(unittest.TestCase):
    def test_the_sheet_names_real_passives_once_and_shows_another_name(self):
        rows = read(SHOWN)
        self.assertEqual([r["kind"] for r in rows], ["passive", "skill"])
        keys = [r["key"] for r in rows]
        self.assertEqual(len(keys), len(set(keys)), "a key is listed twice")
        kinds = {"passive": "passive", "skill": "active"}
        records = {(r["name"], r["kind"]) for r in manifest()}
        for row in rows:
            self.assertIn((row["key"], kinds[row["kind"]]), records, row["key"])
            self.assertNotEqual(row["key"], row["shown_name"])
            self.assertTrue(row["source"].strip(), "a row without a source")
        self.assertEqual(keys, ["Leech (Demon Hunter)", "Earthquake (Shaman)"])

    def test_both_earthquakes_read_earthquake_and_each_is_its_own_record(self):
        names = record_names()
        by_key = {}
        for row in manifest():
            if row["kind"] == "active":   # the Barbarian's Earthquake also has a companion aura record of the same name
                by_key.setdefault(row["name"], []).append(int(row["spell_id"]))
        shaman, barbarian = by_key["Earthquake (Shaman)"], by_key["Earthquake"]
        self.assertEqual((len(shaman), len(barbarian)), (1, 1), "the Barbarian's skill keeps the plain key")
        self.assertNotEqual(shaman[0], barbarian[0])
        self.assertEqual((names[shaman[0]], names[barbarian[0]]), ("Earthquake", "Earthquake"))
        runes = {r["name"]: int(r["spell_id"]) for r in manifest() if r["name"].startswith("Earthquake (Shaman) - ")}
        self.assertEqual(len(runes), 5)
        for key, identifier in runes.items():
            self.assertEqual(names[identifier], "Earthquake - " + key.partition(" - ")[2], key)
        self.assertIn('{%d, "Earthquake (Shaman)", "", ' % shaman[0],
                      (MODULE / "src/combat/dc_spell_shells.h").read_text(encoding="utf-8"))

    def test_both_leeches_read_leech_and_each_is_its_own_record(self):
        names = record_names()
        by_key = {}
        for row in manifest():
            by_key.setdefault(row["name"], []).append(int(row["spell_id"]))
        passive, skill = by_key["Leech (Demon Hunter)"], by_key["Leech"]
        self.assertEqual(len(passive), 1)
        self.assertEqual(len(skill), 1, "the Necromancer's skill keeps the plain key")
        self.assertNotEqual(passive[0], skill[0])
        self.assertEqual(names[passive[0]], "Leech")
        self.assertEqual(names[skill[0]], "Leech")
        # the key still resolves to the Demon Hunter's own record through the sheets and the compiled table
        self.assertIn('{%d, "Leech (Demon Hunter)"}' % passive[0],
                      (MODULE / "src/combat/dc_spell_shells.h").read_text(encoding="utf-8"))

    def test_no_other_record_name_moved(self):
        names = record_names()
        moved = {r["name"] for r in manifest()
                 if names[int(r["spell_id"])] != r["name"] and not r["name"].endswith(tuple(" - " + k for k in AFFIX_SLOW))}
        # a shown skill's runes read the skill's shown name before the rune (`Earthquake (Shaman) - Aftershock` reads `Earthquake - Aftershock`)
        shown_skills = {r["key"] for r in read(SHOWN) if r["kind"] == "skill"}
        runes = {r["name"] for r in manifest() if r["kind"] == "rune" and r["name"].partition(" - ")[0] in shown_skills}
        self.assertEqual(len(runes), 5 * len(shown_skills))
        self.assertEqual(moved, {r["key"] for r in read(SHOWN)} | runes)

    def test_the_picker_reads_the_records_name_and_keeps_the_key(self):
        query = lines_of(SKILLBAR, "-- Passives: dc_class_passive_label", "-- The category columns")
        self.assertIn("COALESCE(NULLIF(s.Name_Lang_enUS, ''), pl.passive_name)", query)
        self.assertIn("LEFT JOIN spell_dbc s ON s.ID = p.spell_id", query)
        self.assertIn("name = result:GetString(1), shown = result:GetString(3)", query)
        # drawn: the overview slot and the picker cell; keyed: the chosen badge, the pick and the bar match
        self.assertIn('cell.name:SetText(name and (passive and passive.shown or name) or "|cff808080Empty|r")', SKILLBAR)
        self.assertIn("cell.name:SetText(passive.shown or passive.name)", SKILLBAR)
        self.assertIn("if row.name == name then passive = row end", SKILLBAR)
        self.assertIn("if chosen[passive.name] then", SKILLBAR)
        self.assertIn("pendingPassive = passive.name", SKILLBAR)

    def test_the_class_loader_keeps_to_keys_and_ids(self):
        # K3 (test_skill_id_migration.py keeps the loader off Spell.dbc names): a pick resolves by key and id, so the
        # shown name is the picker's to read and the loader's lookups stay as they were
        self.assertIn("passiveIdByName.find({ClassId(player), passive})", CLASSES)
        self.assertIn("PassiveUnlocked(player, passive)", CLASSES)


if __name__ == "__main__":
    unittest.main()
