"""Two classes can have a skill of one name (diablocraft-xnrvn.5; ruling 2026-10-23, q-1021-130: the Shaman keeps Earthquake, no renames).

The Barbarian's Earthquake and the Shaman's Earthquake both read `Earthquake` to the player. Every lookup the module has (the
sheets, the value map, the legendary sheet, the saved bar, dc_spell_shells.h) is keyed by the skill's name, so the later class
keys its skill `Earthquake (Shaman)`, the way the Demon Hunter's passive is `Leech (Demon Hunter)` (test_shown_names.py), and
data/d3/shown_names.csv (`kind` skill or passive) gives the player the plain name. The Barbarian's records keep their keys.

What this proves:

  * **The rule.** A key two classes share is refused with the fix in the message; the class-qualified key is accepted when
    shown_names.csv has its row, and refused without one (the player would read the suffix); a row must name a real key of its
    kind, once.
  * **Both build.** A full render in a scratch copy of the data where the Crusader's Provoke is keyed `Earthquake (Crusader)`
    beside the Barbarian's Earthquake: two skill records with two ids, each under its own key in the manifest, the value map
    (the Crusader's numbers are Provoke's, the Barbarian's are untouched) and dc_spell_shells.h; both records and both rune
    sets read `Earthquake` / `Earthquake - <rune>` in Spell.dbc and spell_dbc, and no record name carries the class.
  * **Each legendary reaches its own.** In the same scratch data a legendary row naming `Earthquake` and one naming
    `Earthquake (Crusader)` both pass the legendary generator and each resolves, through the manifest, to its own class's
    record; a row naming a class-qualified key no class has is refused.
  * **The bar shows the plain name.** dc_skillbar.lua's skill query returns the record's name beside the key, the overview slot
    and the picker draw it, and the chosen mark, the drag and the pick still use the key (the Lua tests run the data).

What it does not prove: a Shaman. Its sheets, and so its Earthquake, arrive with the Shaman's 2a (diablocraft-xnrvn); this
bead makes the rule and proves it on a stand-in so 2a can use it.

    python mod-diablocraft/scripts/tests/classes/test_shared_skill_names.py
"""
import contextlib
import csv
import io
import re
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_legendary_powers as glp  # noqa: E402
import generate_spells as gs  # noqa: E402
import test_demon_hunter_records as dh  # noqa: E402
import test_shown_names as sn  # noqa: E402

MODULE = dh.MODULE
REPO = MODULE.parent
SCRATCH = REPO / "azerothcore-wotlk" / "build" / "_agent-scratch" / "shared_skill_names"
SKILLBAR = (MODULE / "lua/aio/dc_skillbar.lua").read_text(encoding="utf-8")

# The stand-in for the Shaman's Earthquake: a Crusader skill with no code of its own in the generator.
STAND_IN, KEY = "Provoke", "Earthquake (Crusader)"
BARBARIAN = "Earthquake"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def classes(**named):
    """{stem: (d3_class, skill rows, passive rows)} from {stem: ([skill names], [passive names])}."""
    return {stem: (stem.title(), [{"skill_name": n} for n in skills], [{"passive_name": n} for n in passives])
            for stem, (skills, passives) in named.items()}


def refused(call, *args):
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            call(*args)
        except SystemExit as stop:
            return str(stop)
    return None


class Rule(unittest.TestCase):
    def test_a_shared_key_is_refused_with_the_fix(self):
        sheets = classes(barbarian=(["Earthquake"], []), shaman=(["Earthquake"], []))
        message = refused(gs.class_of_names, sheets)
        self.assertIn("'Earthquake' is both a barbarian and a shaman name", message)
        self.assertIn("'Earthquake (Shaman)'", message, "the message names the key the later class takes")
        self.assertIn("shown_names.csv", message)

    def test_a_shared_passive_and_skill_key_is_refused_too(self):
        sheets = classes(necromancer=(["Leech"], []), demon_hunter=([], ["Leech"]))
        self.assertIn("'Leech' is both", refused(gs.class_of_names, sheets))

    def test_the_qualified_key_is_accepted_and_belongs_to_its_class(self):
        sheets = classes(barbarian=(["Earthquake"], []), shaman=(["Earthquake (Shaman)"], []))
        self.assertEqual(gs.class_of_names(sheets), {"Earthquake": "barbarian", "Earthquake (Shaman)": "shaman"})

    def test_a_qualified_key_needs_its_row(self):
        sheets = classes(barbarian=(["Earthquake"], []), shaman=(["Earthquake (Shaman)"], []))
        of = gs.class_of_names(sheets)
        self.assertIn("carries its class and has no shown_names.csv row", refused(gs.check_shown_names, [], sheets, of))
        row = {"kind": "skill", "key": "Earthquake (Shaman)", "shown_name": "Earthquake", "source": "x"}
        self.assertIsNone(refused(gs.check_shown_names, [row], sheets, of))

    def test_a_row_names_a_real_key_of_its_kind_once(self):
        sheets = classes(barbarian=(["Earthquake"], []), shaman=(["Earthquake (Shaman)"], ["Blur"]))
        of = gs.class_of_names(sheets)

        def row(kind, key):
            return {"kind": kind, "key": key, "shown_name": "x", "source": "x"}
        good = row("skill", "Earthquake (Shaman)")
        self.assertIn("is not a passive", refused(gs.check_shown_names, [row("passive", "Earthquake (Shaman)")], sheets, of))
        self.assertIn("is not a skill", refused(gs.check_shown_names, [good, row("skill", "Blur"), ], sheets, of))
        self.assertIn("is not a skill", refused(gs.check_shown_names, [good, row("skill", "Nothing")], sheets, of))
        self.assertIn("kind 'rune'", refused(gs.check_shown_names, [good, row("rune", "Earthquake (Shaman)")], sheets, of))
        self.assertIn("listed twice", refused(gs.check_shown_names, [good, good], sheets, of))

    def test_a_runes_shown_name_follows_its_skills(self):
        shown = {"Earthquake (Shaman)": "Earthquake", "Leech (Demon Hunter)": "Leech"}
        self.assertEqual(gs.shown_name(shown, "Earthquake (Shaman)"), "Earthquake")
        self.assertEqual(gs.shown_name(shown, "Earthquake (Shaman) - Aftershock"), "Earthquake - Aftershock")
        self.assertEqual(gs.shown_name(shown, "Earthquake - Molten Fury"), "Earthquake - Molten Fury")
        self.assertEqual(gs.shown_name(shown, "Leech (Demon Hunter)"), "Leech")
        self.assertEqual(gs.shown_name(shown, "Bash - Onslaught"), "Bash - Onslaught")


def twin(root):
    """Key the Crusader's Provoke as `Earthquake (Crusader)` in every sheet under `root`: a cell that is the skill's name, or a
    rune record's `Provoke - <rune>`. Tooltip text that mentions the skill stays as it was."""
    for path in sorted(root.rglob("*.csv")):
        if "sql" in path.parts or STAND_IN.encode() not in path.read_bytes():
            continue
        rows = list(csv.reader(io.StringIO(path.read_bytes().decode("utf-8-sig"))))
        touched = False
        for row in rows:
            for index, cell in enumerate(row):
                if cell == STAND_IN or cell.startswith(STAND_IN + " - "):
                    row[index] = KEY + cell[len(STAND_IN):]
                    touched = True
        if touched:
            out = io.StringIO()
            csv.writer(out, lineterminator="\n").writerows(rows)
            path.write_text(out.getvalue(), encoding="utf-8", newline="\n")


def build(shown_row=True):
    """A scratch module whose Crusader skill is keyed KEY, rendered; returns (module, generated folder, refusal or None)."""
    work = SCRATCH / ("with_row" if shown_row else "without_row")
    shutil.rmtree(work, ignore_errors=True)
    module = work / "module"
    shutil.copytree(MODULE / "src", module / "src")
    shutil.copytree(MODULE / "data", module / "data", ignore=shutil.ignore_patterns("updates"))
    twin(module / "data")
    if shown_row:
        with (module / "data/d3/shown_names.csv").open("a", encoding="utf-8", newline="") as stream:
            stream.write("skill,%s,%s,test: the stand-in for the Shaman's Earthquake\n" % (KEY, BARBARIAN))
    for name in ("Spell.dbc", "SpellCategory.dbc", "SpellDescriptionVariables.dbc"):
        shutil.copy(REPO / "client-patch" / "dbc" / name, work / name)
    # every path the generator holds under the module now points into the scratch copy
    saved = {name: value for name, value in vars(gs).items() if isinstance(value, Path)}
    try:
        for name, value in saved.items():
            if value == MODULE or MODULE in value.parents:
                setattr(gs, name, module / value.relative_to(MODULE))
        gs.CLIENT_DBC, gs.CLIENT_CATEGORY_DBC = work / "Spell.dbc", work / "SpellCategory.dbc"
        gs.CLIENT_VARIABLES_DBC = work / "SpellDescriptionVariables.dbc"
        stop = refused(gs.main)
        if stop is None:
            with contextlib.redirect_stdout(io.StringIO()):
                gs.generate_ability_data()
    finally:
        for name, value in saved.items():
            setattr(gs, name, value)
    return module, module / "data" / "generated", stop


class Built(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module, cls.generated, stop = build()
        if stop is not None:
            raise AssertionError("the render stopped: %s" % stop)
        cls.manifest = read(cls.generated / "spell_shells.csv")
        cls.real = read(dh.GENERATED / "spell_shells.csv")
        cls.names = sn.record_names(cls.generated)

    def ids(self, key):
        return [int(r["spell_id"]) for r in self.manifest if r["name"] == key and r["kind"] == "active"]

    def test_both_skills_are_records_under_their_own_keys(self):
        barbarian, crusader = self.ids(BARBARIAN), self.ids(KEY)
        self.assertEqual((len(barbarian), len(crusader)), (1, 1))
        self.assertNotEqual(barbarian, crusader)
        real = {r["name"]: int(r["spell_id"]) for r in self.real if r["kind"] == "active"}
        self.assertEqual(barbarian[0], real[BARBARIAN], "the Barbarian's record did not move")
        self.assertEqual(crusader[0], real[STAND_IN], "the stand-in kept its id under the new key")
        self.assertEqual(self.ids(STAND_IN), [], "nothing is left under the old key")

    def test_both_read_earthquake_and_so_do_their_runes(self):
        for key in (BARBARIAN, KEY):
            self.assertEqual(self.names[self.ids(key)[0]], "Earthquake", key)
        for prefix in (BARBARIAN, KEY):
            runes = [r for r in self.manifest if r["name"].startswith(prefix + " - ") and r["kind"] == "rune"]
            self.assertEqual(len(runes), 5, prefix)
            for rune in runes:
                self.assertEqual(self.names[int(rune["spell_id"])], "Earthquake - " + rune["name"].split(" - ", 1)[1])

    def test_no_record_shows_the_class(self):
        self.assertEqual([n for n in self.names.values() if "(Crusader)" in n], [])

    def test_the_value_map_keeps_each_classes_numbers_under_its_key(self):
        now = read(self.generated / "spell_value_map.csv")
        real = read(dh.GENERATED / "spell_value_map.csv")

        def numbers(rows, key):
            return sorted((r["rune"], r["token"], r["qualifier"], r["source"], r["conversion"], r["variable"])
                          for r in rows if r["skill"] == key)
        self.assertTrue(numbers(now, KEY), "the stand-in's rows are filed under the new key")
        self.assertEqual(numbers(now, KEY), numbers(real, STAND_IN))
        self.assertEqual(numbers(now, BARBARIAN), numbers(real, BARBARIAN))
        self.assertEqual(numbers(now, STAND_IN), [])

    def test_the_compiled_table_resolves_both_keys(self):
        header = (self.module / "src/combat/dc_spell_shells.h").read_text(encoding="utf-8")
        for key in (BARBARIAN, KEY):
            self.assertRegex(header, r'\{%d, "%s", "", [\d.]+\}' % (self.ids(key)[0], re.escape(key)))

    def test_the_stand_in_is_the_only_record_that_moved(self):
        real = {r["spell_id"]: r["name"] for r in self.real}
        moved = {(real[r["spell_id"]], r["name"]) for r in self.manifest if real.get(r["spell_id"]) != r["name"]}
        self.assertEqual({new for _old, new in moved if not new.startswith(KEY)}, set())
        self.assertEqual(len(moved), 6 + len([r for r in self.manifest if r["name"].startswith(KEY + " - ") and r["kind"] != "rune"]))

    def legendary_rows(self, *skills):
        """The legendary generator's rows over the scratch data with one extra row of the Barbarian belt's per skill."""
        sheet = self.module / "data/legendary_powers.csv"
        original = sheet.read_text(encoding="utf-8")
        belt = [r for r in read(sheet) if r["owner"] == "P61_Unique_BarbBelt_EQ"][0]
        try:
            with sheet.open("a", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(belt), lineterminator="\n")
                for skill in skills:
                    writer.writerow(dict(belt, skill=skill))
            return glp.rows(self.module)
        finally:
            sheet.write_text(original, encoding="utf-8", newline="\n")

    def test_each_legendary_row_reaches_its_own_classes_record(self):
        table = [row for row in self.legendary_rows(KEY) if row[0] == "P61_Unique_BarbBelt_EQ"]
        self.assertEqual(sorted(row[3] for row in table), sorted([BARBARIAN, KEY]))
        element = {r["name"]: r["element"] for r in self.manifest if r["kind"] == "active"}
        real = {r["name"]: r["element"] for r in self.real if r["kind"] == "active"}
        self.assertEqual(element[BARBARIAN], real[BARBARIAN], "the bare name is still the Barbarian's")
        self.assertEqual(element[KEY], real[STAND_IN], "the qualified key is the Crusader's skill")
        self.assertNotEqual(self.ids(BARBARIAN), self.ids(KEY))

    def test_a_qualified_key_no_class_has_is_refused(self):
        # A qualifier no class will ever be called: the Shaman owns "Earthquake (Shaman)" since its records exist.
        with self.assertRaises(ValueError) as caught:
            self.legendary_rows("Earthquake (Nobody)")
        self.assertIn("Earthquake (Nobody) is not a skill", str(caught.exception))

    def test_the_shamans_qualified_key_is_a_skill(self):
        table = [row for row in self.legendary_rows("Earthquake (Shaman)") if row[0] == "P61_Unique_BarbBelt_EQ"]
        self.assertIn("Earthquake (Shaman)", {row[1] for row in table} | {row[2] for row in table} | {row[3] for row in table})

    def test_the_render_without_the_row_is_refused(self):
        _module, _generated, stop = build(shown_row=False)
        self.assertIn("carries its class and has no shown_names.csv row", stop or "")


class Bar(unittest.TestCase):
    def test_the_skill_query_returns_the_records_name_beside_the_key(self):
        query = sn.lines_of(SKILLBAR, "-- Skills: D3's category order", "-- Runes: c.rune_id")
        self.assertIn("COALESCE(NULLIF(s.Name_Lang_enUS, ''), l.skill_name)", query)
        self.assertIn("LEFT JOIN spell_dbc s ON s.ID = c.spell_id", query)
        self.assertIn("name = result:GetString(1),", query)
        self.assertIn("shown = result:GetString(5),", query)

    def test_the_overview_and_the_picker_draw_the_shown_name_and_keep_the_key(self):
        self.assertIn('cell.name:SetText(entry and entry.skill and (skill and skill.shown or entry.skill) or "|cff808080Empty|r")',
                      SKILLBAR)
        self.assertIn("cell.name:SetText(skill.shown or skill.name)", SKILLBAR)
        # keyed: the slot mark, the chosen mark, the drag and the pick
        self.assertIn("if onBar[skill.name] then", SKILLBAR)
        self.assertIn("cell.badge:SetText(onBar[skill.name])", SKILLBAR)
        self.assertIn("if skill.name == pendingSkill then cell.chosen:Show() end", SKILLBAR)
        self.assertIn("pendingSkill = skill.name", SKILLBAR)
        self.assertIn("dragging = (not skill.locked) and skill.name or nil", SKILLBAR)


if __name__ == "__main__":
    unittest.main()
