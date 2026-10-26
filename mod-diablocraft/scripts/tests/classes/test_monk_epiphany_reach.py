"""diablocraft-a1noc: Epiphany's reach, the designer's card q-1014-09 (2026-10-14): +15 yards on every Monk skill while Epiphany is up.

What this proves, and how:

  * **The record.** generate_spells.py writes one hidden record, "Epiphany - reach": a SPELL_AURA_ADD_FLAT_MODIFIER (107)
    of SPELLMOD_RANGE (5), exactly 15 (no die side) on the caster, passive (so a logout does not save it), in the Monk's
    family 22, its mask every Monk skill's bit, lasting Epiphany's own duration_seconds (SpellDuration.dbc). The generated
    SQL and the newest full combat migration (what the server ends with) both carry it, and the module's header names it.
  * **It reaches every Monk record.** The core's SpellInfo::IsAffected rule (same family, mask & the record's
    SpellClassMask word one nonzero), run over every Monk skill and rune record of the generated table: each is reached,
    and no record of another class is.
  * **The module puts it on and takes it off.** dc_monk_epiphany.cpp's Start adds it after ending the previous Epiphany,
    and End (expiry, death, a new Epiphany) removes it.
  * Mutants of the record (no effect, another aura, another mod, another amount, a die side, a mask missing one skill, the
    wrong family, the wrong duration, not passive) and of the module's two calls each fail the checks.

What it does not prove: anything on a running server or client - that the client honours the modifier when it range-checks
a cast is docs/test-diablocraft-a1noc.md's, live, after the next client patch.

    python mod-diablocraft/scripts/tests/classes/test_monk_epiphany_reach.py
"""

import csv
import io
import re
import struct
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
GENERATED = MODULE / "data" / "generated"
DURATION_DBC = REPO / "azerothcore-wotlk" / "build" / "server" / "data" / "dbc" / "SpellDuration.dbc"
EPIPHANY = MODULE / "src" / "classes" / "monk" / "dc_monk_epiphany.cpp"
HEADER = MODULE / "src" / "combat" / "dc_spell_shells.h"
NAME = "Epiphany - reach"
MONK_FAMILY = 22
MONK_RECORDS = (83650, 83849)   # generate_spells.py CLASS_BLOCKS["monk"].records
REACH_YARDS = 15                # ruling q-1014-09
SPELL_EFFECT_APPLY_AURA, SPELL_AURA_ADD_FLAT_MODIFIER, SPELLMOD_RANGE, TARGET_UNIT_CASTER = 6, 107, 5, 1
SPELL_ATTR0_PASSIVE = 0x40


def records(sql):
    """Every spell_dbc row of a generated or migration SQL text, as {id: {column: text}}."""
    rows = {}
    for insert in re.finditer(r"INSERT INTO `?spell_dbc`? \((.*?)\) VALUES\n?(.*?);\n", sql, re.S):
        columns = [name.strip(" `") for name in insert.group(1).split(",")]
        for row in re.finditer(r"\((\d+),(.*?)\)(?=,\n?\(|\s*$)", insert.group(2), re.S):
            cells = next(csv.reader(io.StringIO(row.group(1) + "," + row.group(2)), quotechar="'", escapechar="\\"))
            rows[int(cells[0])] = dict(zip(columns, cells))
    return rows


def manifest():
    with (GENERATED / "spell_shells.csv").open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def epiphany_seconds():
    with (MODULE / "data" / "d3" / "monk_skill_values.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = [r for r in csv.DictReader(stream)
                if (r["skill"], r["rune"], r["token"]) == ("Epiphany", "", "duration_seconds")]
    assert len(rows) == 1
    return float(rows[0]["value"])


def duration_ms(index):
    raw = DURATION_DBC.read_bytes()
    count, _fields, size, _strings = struct.unpack("<4xIIII", raw[:20])
    for i in range(count):
        ident, base, _per, most = struct.unpack("<iiii", raw[20 + i * size:20 + i * size + 16])
        if ident == index:
            return base, most
    return None


def affected(modifier, record):
    """SpellInfo::IsAffected for a word-one mask: the same family, and a bit of the mask in the record's flags."""
    return (int(modifier["SpellClassSet"]) == int(record["SpellClassSet"])
            and int(modifier["EffectSpellClassMaskA_1"]) & int(record["SpellClassMask_1"]) != 0)


def record_failures(rows, shells):
    """What is wrong with the reach record in `rows` ([] when it is right)."""
    found = [r for r in rows.values() if r["Name_Lang_enUS"] == NAME]
    if len(found) != 1:
        return ["%d records named %r" % (len(found), NAME)]
    reach = found[0]
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    need("an aura effect", int(reach["Effect_1"]) == SPELL_EFFECT_APPLY_AURA)
    need("a flat spell modifier", int(reach["EffectAura_1"]) == SPELL_AURA_ADD_FLAT_MODIFIER)
    need("of the range", int(reach["EffectMiscValue_1"]) == SPELLMOD_RANGE)
    need("exactly 15 yards", int(reach["EffectBasePoints_1"]) == REACH_YARDS and int(reach["EffectDieSides_1"]) == 0)
    need("on the caster", int(reach["ImplicitTargetA_1"]) == TARGET_UNIT_CASTER)
    need("in the Monk's family", int(reach["SpellClassSet"]) == MONK_FAMILY)
    need("passive, so a logout does not save it", int(reach["Attributes"]) & SPELL_ATTR0_PASSIVE != 0)
    need("only the first effect", all(int(reach["Effect_%d" % slot]) == 0 for slot in (2, 3)))
    if DURATION_DBC.is_file():
        want = int(round(epiphany_seconds() * 1000))
        need("Epiphany's duration", duration_ms(int(reach["DurationIndex"])) == (want, want))
    monk = [rows[int(s["spell_id"])] for s in shells if s["kind"] in ("active", "rune")
            and MONK_RECORDS[0] <= int(s["spell_id"]) <= MONK_RECORDS[1]]
    others = [rows[int(s["spell_id"])] for s in shells if s["kind"] in ("active", "rune")
              and not MONK_RECORDS[0] <= int(s["spell_id"]) <= MONK_RECORDS[1] and int(s["spell_id"]) in rows]
    need("Monk records to reach", len(monk) > 20)
    missed = sorted(r["Name_Lang_enUS"] for r in monk if not affected(reach, r))
    need("every Monk skill and rune reached (missed: %s)" % missed[:5], not missed)
    need("no other class's record reached", not any(affected(reach, r) for r in others))
    return wrong


def module_failures(text):
    """What is wrong with dc_monk_epiphany.cpp's two calls ([] when they are right)."""
    wrong = []
    start = text[text.index("        void Start(Player* player, std::uint32_t spellId)"):]
    start = start[:start.index("\n        }\n")]
    end = text[text.index("        void End(Player* player, std::uint32_t spellId)"):]
    end = end[:end.index("\n        }\n")]
    lookup = 'if (std::uint32_t const reach = Shells::HelperFor("Epiphany - reach"))'
    add = "player->AddAura(reach, player);"
    if not (lookup in start and add in start):
        wrong.append("Start puts the reach on")
    elif not start.index("End(player, previous);") < start.index(add):
        wrong.append("the reach goes on after the previous Epiphany ends")
    if not (lookup in end and "player->RemoveAurasDueToSpell(reach);" in end):
        wrong.append("End takes the reach off")
    return wrong


class TheRecord(unittest.TestCase):
    def setUp(self):
        self.sql = (GENERATED / "spell_shells.sql").read_text(encoding="utf-8")
        self.rows = records(self.sql)
        self.shells = manifest()

    def test_the_generated_record_is_the_reach(self):
        self.assertEqual([], record_failures(self.rows, self.shells))

    def test_the_header_names_it_and_the_manifest_lists_it(self):
        reach = [s for s in self.shells if s["name"] == NAME]
        self.assertEqual(1, len(reach))
        self.assertIn('{%s, "%s", 0},' % (reach[0]["spell_id"], NAME), HEADER.read_text(encoding="utf-8"))

    def test_the_number_is_alexs(self):
        decisions = (REPO / "docs" / "decisions.md").read_text(encoding="utf-8")
        generator = (MODULE / "scripts" / "generate/classes/generate_spells.py").read_text(encoding="utf-8")
        self.assertIn("q-1014-09", generator)
        self.assertIn("EPIPHANY_REACH_YARDS = %d" % REACH_YARDS, generator)
        self.assertRegex(decisions, r"q-1014-09[^\n]*\+?15 ?yd|Epiphany's reach[^\n]*15")

    def test_the_record_mutants_fail(self):
        reach_id = next(int(s["spell_id"]) for s in self.shells if s["name"] == NAME)
        some_monk = next(int(s["spell_id"]) for s in self.shells if s["kind"] == "active"
                         and MONK_RECORDS[0] <= int(s["spell_id"]) <= MONK_RECORDS[1] + 0)
        lost_bit = int(self.rows[some_monk]["SpellClassMask_1"])
        mutants = {
            "no_effect": {"Effect_1": "0"},
            "another_aura": {"EffectAura_1": "108"},
            "another_mod": {"EffectMiscValue_1": "11"},
            "another_amount": {"EffectBasePoints_1": "10"},
            "a_die_side": {"EffectDieSides_1": "1"},
            "a_skill_left_out": {"EffectSpellClassMaskA_1": str(int(self.rows[reach_id]["EffectSpellClassMaskA_1"]) & ~lost_bit)},
            "wrong_family": {"SpellClassSet": "21"},
            "not_on_the_caster": {"ImplicitTargetA_1": "6"},
            "not_passive": {"Attributes": str(int(self.rows[reach_id]["Attributes"]) & ~SPELL_ATTR0_PASSIVE)},
            "a_second_effect": {"Effect_2": "6"},
        }
        if DURATION_DBC.is_file():
            mutants["infinite"] = {"DurationIndex": "21"}
        for name, change in mutants.items():
            with self.subTest(mutant=name):
                rows = dict(self.rows)
                rows[reach_id] = dict(self.rows[reach_id], **change)
                self.assertTrue(record_failures(rows, self.shells), name + " survived")
        with self.subTest(mutant="no_record"):
            rows = {k: v for k, v in self.rows.items() if k != reach_id}
            self.assertTrue(record_failures(rows, self.shells))


class TheModule(unittest.TestCase):
    def test_start_puts_it_on_and_end_takes_it_off(self):
        self.assertEqual([], module_failures(EPIPHANY.read_text(encoding="utf-8")))

    def test_the_module_mutants_fail(self):
        text = EPIPHANY.read_text(encoding="utf-8")
        mutants = {
            "never_on": ("player->AddAura(reach, player);", "(void)reach;"),
            "never_off": ("player->RemoveAurasDueToSpell(reach);", "(void)reach;"),
            "another_name": ('Shells::HelperFor("Epiphany - reach"))\n                player->AddAura',
                             'Shells::HelperFor("Epiphany"))\n                player->AddAura'),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, text.count(old), name)
                self.assertTrue(module_failures(text.replace(old, new)), name + " survived")


if __name__ == "__main__":
    unittest.main()
