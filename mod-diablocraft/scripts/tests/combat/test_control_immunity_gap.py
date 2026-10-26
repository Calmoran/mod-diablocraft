"""Nothing in the module applies a knockout or a daze to a player (diablocraft-aura-fixes, Part 2, ruling 2026-10-03).

    python3 mod-diablocraft/scripts/tests/combat/test_control_immunity_gap.py

Ignore Pain and Nerves of Steel carry their control immunity on their own records now. This core's aura 147 takes a
lookup id, not a mask: misc 96 gives the stock "immune to every control" set, which has neither KNOCKOUT (mechanic 14)
nor DAZE (mechanic 27), and the three effect slots beside the marker's DUMMY effect hold 147 and one aura 77 (silence).
The designer ruled to keep silence and drop knockout and daze, provided nothing in the module can apply either to a player.
This test is that provision: it fails if any of these ever does, so the gap cannot open silently.

What it scans (the whole module, from the checkout):
  spell data    every spell_dbc row the module writes (the generated shells and every migration): Mechanic and
                EffectMechanic_1..3;
  aura data     the sheets in data/d3 for the words knockout and daze;
  SmartAI data  smart_scripts rows whose action casts or adds an aura (actions 11, 75, 85, 86, 134) of a spell whose
                record carries either mechanic (the client's Spell.dbc, stock and ours);
  C++           AddAura, CastSpell and CastCustomSpell calls in src/ whose spell argument is a literal or a constexpr
                constant naming such a spell.
The scans are run on planted inputs first (a knockout, a daze, a cast of a daze spell) and must find them; then on the
real module and must find nothing.
What it does not scan: spells chosen at run time (a table lookup or a computed id) and what the core itself casts.
"""
import csv
import io
import re
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / "mod-diablocraft"
CLIENT_SPELL = ROOT / "client-patch/dbc/Spell.dbc"

MECHANICS = {14: "knockout", 27: "daze"}
CAST_ACTIONS = {11, 75, 85, 86, 134}      # SMART_ACTION_CAST, ADD_AURA, SELF_CAST, CROSS_CAST, INVOKER_CAST
WORDS = re.compile(r"\b(knock-?out|daze[d]?)\b", re.I)


# --- a small SQL INSERT reader -------------------------------------------------------------------------------------

def insert_rows(text, table):
    """Yield dict rows of every `INSERT INTO table (cols) VALUES (...),(...);` (quotes and '' escapes understood)."""
    pattern = re.compile(r"INSERT\s+INTO\s+`?%s`?\s*\(([^)]*)\)\s*VALUES" % re.escape(table), re.I)
    for header in pattern.finditer(text):
        columns = [c.strip(" `\n") for c in header.group(1).split(",")]
        i = header.end()
        while True:
            while i < len(text) and text[i] in " \n\r\t,":
                i += 1
            if i >= len(text) or text[i] != "(":
                break
            i += 1
            values, token, quoted = [], "", False
            while True:
                c = text[i]
                if quoted:
                    if c == "'" and text[i + 1] == "'":
                        token += "'"
                        i += 1
                    elif c == "'":
                        quoted = False
                    else:
                        token += c
                elif c == "'":
                    quoted = True
                elif c in ",)":
                    values.append(token.strip())
                    token = ""
                    if c == ")":
                        i += 1
                        break
                else:
                    token += c
                i += 1
            yield dict(zip(columns, values))


def number(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


FULL_SPELL_RENDER = "DELETE FROM `spell_dbc` WHERE `ID` BETWEEN"   # what generate_spells.py's full spell render starts with


def newest_spell_render(updates):
    """The newest combat migration that is a full spell render. Not every combat_0* is one: combat_0067_monk_summons.sql
    carries the ability tunables and summons, not the spell_dbc block."""
    return [p for p in sorted(updates.glob("combat_0*.sql")) if FULL_SPELL_RENDER in p.read_text(encoding="utf-8")][-1]


# --- the scans -----------------------------------------------------------------------------------------------------

def scan_spell_sql(text, where="sql"):
    hits = []
    for row in insert_rows(text, "spell_dbc"):
        for field in ("Mechanic", "EffectMechanic_1", "EffectMechanic_2", "EffectMechanic_3"):
            if number(row.get(field)) in MECHANICS:
                hits.append("%s: spell %s %s = %s (%s)" % (where, row.get("ID"), field, row[field],
                                                           MECHANICS[number(row[field])]))
    return hits


def scan_words(text, where="csv"):
    return ["%s: line %d: %s" % (where, n + 1, line.strip()[:80])
            for n, line in enumerate(text.splitlines()) if WORDS.search(line)]


def bad_spell_ids(dbc_bytes):
    """The ids of every record in a Spell.dbc whose Mechanic (field 3) or EffectMechanic (fields 83-85) is one."""
    _, count, fields, size, _ = struct.unpack_from("<4sIIII", dbc_bytes)
    bad = set()
    for index in range(count):
        record = struct.unpack_from("<%dI" % fields, dbc_bytes, 20 + index * size)
        if any(record[field] in MECHANICS for field in (3, 83, 84, 85)):
            bad.add(record[0])
    return bad


def scan_smart_sql(text, bad, where="sql"):
    hits = []
    for row in insert_rows(text, "smart_scripts"):
        if number(row.get("action_type")) in CAST_ACTIONS and number(row.get("action_param1")) in bad:
            hits.append("%s: smart_scripts %s id %s casts spell %s" % (where, row.get("entryorguid"), row.get("id"),
                                                                       row["action_param1"]))
    return hits


APPLIES = re.compile(r"\b(AddAura|CastSpell|CastCustomSpell)\s*\(")


def split_arguments(text, start):
    """The top-level arguments of the call whose '(' is at text[start - 1]."""
    depth, args, token = 1, [], ""
    for c in text[start:]:
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                args.append(token.strip())
                return args
        if c == "," and depth == 1:
            args.append(token.strip())
            token = ""
        else:
            token += c
    return args


def scan_cpp(text, bad, constants, where="cpp"):
    hits = []
    for call in APPLIES.finditer(text):
        for argument in split_arguments(text, call.end()):
            value = int(argument) if argument.isdigit() else constants.get(argument.split("::")[-1])
            if value in bad:
                hits.append("%s: %s(...%s...) names spell %d" % (where, call.group(1), argument, value))
    return hits


def cpp_constants(texts):
    found = {}
    for text in texts:
        for name, value in re.findall(r"constexpr\s+(?:std::)?u?int\d*(?:_t)?\s+([A-Za-z_]\w*)\s*=\s*(\d+)\s*;", text):
            found[name] = int(value)
    return found


# --- the real module -----------------------------------------------------------------------------------------------

def module_files(pattern, folder=MODULE):
    return sorted(path for path in folder.rglob(pattern) if path.is_file() and "azerothcore-wotlk" not in path.parts)


def stock_bad():
    if not CLIENT_SPELL.exists():
        return None
    return bad_spell_ids(CLIENT_SPELL.read_bytes())


class ScansFindWhatTheyAreFor(unittest.TestCase):
    """Red first: each scan is shown a planted knockout or daze and must find it; clean input finds nothing."""

    SPELL = ("INSERT INTO `spell_dbc` (`ID`, `Mechanic`, `EffectMechanic_1`, `EffectMechanic_2`, `EffectMechanic_3`) "
             "VALUES\n(%s);")

    def test_a_planted_spell_with_either_mechanic_is_found(self):
        self.assertEqual(len(scan_spell_sql(self.SPELL % "91001,14,0,0,0")), 1)
        self.assertEqual(len(scan_spell_sql(self.SPELL % "91002,0,0,27,0")), 1)
        self.assertEqual(len(scan_spell_sql(self.SPELL % "91003,5,12,7,0")), 0)       # fear, stun, root: fine

    def test_a_planted_word_in_a_sheet_is_found(self):
        self.assertEqual(len(scan_words("name,effect\nHammer,Knockout the target\n")), 1)
        self.assertEqual(len(scan_words("name,effect\nHowl,Dazed for 2 seconds\n")), 1)
        self.assertEqual(len(scan_words("name,effect\nBash,Knockback and stun\n")), 0)

    def test_a_planted_smart_cast_of_a_bad_spell_is_found(self):
        row = ("INSERT INTO `smart_scripts` (`entryorguid`, `id`, `action_type`, `action_param1`) VALUES "
               "(7001, 0, %d, 555);")
        self.assertEqual(len(scan_smart_sql(row % 11, {555})), 1)
        self.assertEqual(len(scan_smart_sql(row % 134, {555})), 1)
        self.assertEqual(len(scan_smart_sql(row % 1, {555})), 0)                          # a talk action: not a cast
        self.assertEqual(len(scan_smart_sql(row % 11, {556})), 0)

    def test_a_planted_cpp_application_of_a_bad_spell_is_found(self):
        constants = {"DAZE_SPELL": 555}
        self.assertEqual(len(scan_cpp("player->AddAura(DAZE_SPELL, target);", {555}, constants)), 1)
        self.assertEqual(len(scan_cpp("caster->CastSpell(target, 555, true);", {555}, constants)), 1)
        self.assertEqual(len(scan_cpp("caster->CastCustomSpell(target, D::DAZE_SPELL, &v, nullptr, nullptr, true);",
                                      {555}, constants)), 1)
        self.assertEqual(len(scan_cpp("caster->CastSpell(target, 556, true);", {555}, constants)), 0)
        self.assertEqual(len(scan_cpp("player->RemoveAurasDueToSpell(DAZE_SPELL);", {555}, constants)), 0)

    def test_the_stock_table_is_read_from_the_dbc(self):
        bad = stock_bad()
        if bad is None:
            self.skipTest("no client Spell.dbc in this checkout")
        self.assertGreater(len(bad), 50)      # the stock game has plenty of knockouts and dazes to name


class NothingInTheModuleAppliesThem(unittest.TestCase):
    def test_no_spell_record_carries_either_mechanic(self):
        hits = []
        for path in module_files("*.sql"):
            if "spell_dbc" in (text := path.read_text(encoding="utf-8", errors="replace")):
                hits += scan_spell_sql(text, str(path.relative_to(ROOT)))
        self.assertEqual(hits, [], "a module spell record carries KNOCKOUT or DAZE:\n" + "\n".join(hits[:20]))

    def test_no_sheet_mentions_them(self):
        hits = []
        for path in module_files("*.csv", MODULE / "data/d3"):
            hits += scan_words(path.read_text(encoding="utf-8", errors="replace"), str(path.relative_to(ROOT)))
        self.assertEqual(hits, [], "a sheet names a knockout or a daze:\n" + "\n".join(hits[:20]))

    def test_no_smartai_row_casts_a_spell_that_carries_either(self):
        bad = stock_bad()
        if bad is None:
            self.skipTest("no client Spell.dbc in this checkout")
        hits = []
        for path in module_files("*.sql"):
            text = path.read_text(encoding="utf-8", errors="replace")
            if "smart_scripts" in text:
                hits += scan_smart_sql(text, bad, str(path.relative_to(ROOT)))
        self.assertEqual(hits, [], "SmartAI casts a KNOCKOUT or DAZE spell:\n" + "\n".join(hits[:20]))

    def test_no_cpp_applies_a_spell_that_carries_either(self):
        bad = stock_bad()
        if bad is None:
            self.skipTest("no client Spell.dbc in this checkout")
        sources = [(path, path.read_text(encoding="utf-8", errors="replace")) for path in module_files("*.cpp", MODULE / "src")
                   + module_files("*.h", MODULE / "src")]
        constants = cpp_constants(text for _, text in sources)
        hits = []
        for path, text in sources:
            hits += scan_cpp(text, bad, constants, str(path.relative_to(ROOT)))
        self.assertEqual(hits, [], "C++ applies a KNOCKOUT or DAZE spell to something:\n" + "\n".join(hits[:20]))


if __name__ == "__main__":
    unittest.main()
