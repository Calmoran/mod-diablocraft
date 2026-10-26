"""The generated C++ index says exactly what the value map says.

Step 2 reads every number out of the spell record through
`src/combat/dc_spell_values.h`, so that header and
`data/generated/spell_value_map.csv` must be the same table: one row per
number, naming the same holder record, field, slot and origin. A key that
appears twice would make the accessor's lookup ambiguous, and a holder that
does not exist would make it read nothing.

    python mod-diablocraft/scripts/tests/classes/test_spell_index.py
"""

from __future__ import annotations

import csv
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
GENERATED = REPO_ROOT / "mod-diablocraft" / "data" / "generated"
INDEX = REPO_ROOT / "mod-diablocraft" / "src" / "combat" / "dc_spell_values.h"
ACCESSOR = REPO_ROOT / "mod-diablocraft" / "src" / "combat" / "dc_spell_numbers.h"

ROW = re.compile(r'\{(\d+), "([a-z_]*)", "([a-z_]*)", Source::(\w+), (\d+), (\d+), '
                 r'Origin::(\w+), (\d+)\},')


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


class SpellIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = INDEX.read_text(encoding="utf-8")
        cls.rows = ROW.findall(cls.text)
        cls.shells = read_csv(GENERATED / "spell_shells.csv")

    # The two records that state a token they also inherit, and why (Architect
    # ruling, decisions.md 8d89601). The record's DurationIndex has to hold the
    # SHOUT's duration, because Inspiring Presence's SPELLMOD_DURATION doubles
    # what that field holds, and the record's own number - Hardened Wrath's
    # armour window, Demoralize's taunt - must not double, so it lives as an
    # exact value beside it instead of replacing it.
    #
    # 83248 (Archon - Teleport) joins them (diablocraft-0lri, 2026-09-30): it inherits
    # the Archon skill's 120 s cooldown and states its own 2 s, which is the cooldown of
    # the Archon Teleport ability (83278) that is actually cast, and what its tooltip says.
    #
    # 83184 (Teleport - Reversal) joins them (diablocraft-teleport-reversal, GitHub #94): its tooltip's
    # {cooldown_seconds} is the 1 s the Wizard is left with after the return, so it states 1 and
    # inherits Teleport's 11 s. The record's 11 s is the real cooldown and stays: the server takes it
    # off for the window and puts on 1 s (return) or 11 s less the window (lapse), never the tooltip's
    # number alone. dc_wizard.cpp reads the 1 s with Numbers::Own.
    BOTH_ORIGINS = {("81108", "duration_seconds", ""), ("81118", "duration_seconds", ""),
                    ("83248", "cooldown_seconds", ""), ("83184", "cooldown_seconds", "")}

    # A known bug, not a ruling: add it here with its GitHub number, and delete the entry when it is
    # fixed; the test then insists the key is back to one row.
    KNOWN_ISSUES = {}

    def test_a_key_is_unique_unless_the_record_both_states_and_inherits_it(self):
        """The accessor indexes by (spell, token, qualifier).

        One row per key everywhere but the ruled records (BOTH_ORIGINS) and the
        known issues, and each of those is one own row and one inherited row - never two of either, and
        never a third.
        """
        seen = {}
        for spell, token, qualifier, _source, _holder, _slot, origin, _origin_spell in self.rows:
            seen.setdefault((spell, token, qualifier), []).append(origin.lower())
        repeated = {key: origins for key, origins in seen.items() if len(origins) > 1}
        self.assertEqual(set(repeated), self.BOTH_ORIGINS | set(self.KNOWN_ISSUES),
                         "a key appears twice outside the ruled records and the known issues "
                         "(%s)" % ", ".join(self.KNOWN_ISSUES.values()))
        for key, origins in repeated.items():
            self.assertEqual(sorted(origins), ["inherited", "own"], key)

    def test_every_holder_exists_and_every_slot_is_real(self):
        known = {row["spell_id"] for row in self.shells}
        for spell, token, _qualifier, source, holder, slot, _origin, origin_spell in self.rows:
            self.assertIn(holder, known, "%s holds %s and is not a generated record"
                          % (holder, token))
            self.assertIn(origin_spell, known)
            if source in ("BasePoints", "Radius", "Period", "Chain"):
                self.assertIn(int(slot), (1, 2, 3), "%s %s: effect slot %s" % (spell, token, slot))
            else:
                self.assertEqual(int(slot), 0 if source != "Radius" else 1,
                                 "%s %s: a record-level field has no slot" % (spell, token))

    def test_the_exact_rows_are_the_table_rows(self):
        """Source::Exact is the only thing that may read from dc_spell_values."""
        sql = (GENERATED / "spell_shells.sql").read_text(encoding="utf-8")
        published = {(int(spell), token, qualifier) for spell, token, qualifier, _value
                     in re.findall(r"\((\d+),'([a-z_]+)','([a-z_]*)',([0-9.]+)\)", sql)}
        wanted = {(int(spell), token, qualifier)
                  for spell, token, qualifier, source, *_ in self.rows if source == "Exact"}
        self.assertEqual(wanted, published,
                         "the exact rows and dc_spell_values disagree")

    def test_the_header_compiles(self):
        """It is generated C++; a generator typo must not reach a build."""
        compiler = shutil.which("g++") or shutil.which("clang++")
        if not compiler:
            raise unittest.SkipTest("no C++ compiler on this host")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "index.cpp"
            source.write_text('#include "%s"\nint main() { return int(DC::Combat::SpellValues'
                              '::Rows[0].spell); }\n' % INDEX, encoding="utf-8")
            result = subprocess.run([compiler, "-std=c++17", "-fsyntax-only", str(source)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr[-2000:])

    def test_the_accessor_keeps_the_base_and_rune_reads_apart(self):
        """Own() and Inherited() are the new b->n[k] and r->n[k]."""
        text = ACCESSOR.read_text(encoding="utf-8")
        for name in ("Get(", "Own(", "Inherited(", "Num(", "Has(", "Load("):
            self.assertIn(name, text, "the accessor lost %s" % name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
