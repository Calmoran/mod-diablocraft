"""The generator refuses a FORCED_ZERO name that is no spell_dbc column (diablocraft-u4smw).

generate_spells.py clears a list of the donor's fields on every record it renders (FORCED_ZERO). It used to skip a name that matched no
column without a word, so a misspelt name left the donor's value on every record: TotemCategory_1/2 for RequiredTotemCategoryID_1/2 kept the
stock totem tools on 37 class records (u4e8z), and four more names were no column at all (EquippedItemSubClassMask, EquippedItemInventoryTypeMask,
StackAmount, ManaCostPercentage). The numbered slots (the three effects' numbers and the reagents) were cleared by a loop with the same silent skip, and two of
its names were no column either (EffectBaseDice_n, EffectAmplitude_n, the aura period's old name): FORCED_ZERO_EFFECTS and FORCED_ZERO_REAGENTS are checked the same way.

What runs: every name of FORCED_ZERO against the real column list of the core's spell_dbc table (parsed the way the generator parses it); the
refusal with planted unknown names, which must name each of them; the four old names, which must be refused now. What is read from source: that
main() runs the check before the baseline loop uses the names, and that the loop no longer has a `if column in columns` that could skip one.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_spells as spells  # noqa: E402

SOURCE = Path(spells.__file__).read_text(encoding="utf-8")


def real_columns():
    columns, inside = [], False
    for line in spells.CORE_SQL.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("CREATE TABLE `spell_dbc`"):
            inside = True
            continue
        if inside:
            if line.startswith(")"):
                break
            if line.strip().startswith("`"):
                columns.append(line.strip().split("`")[1])
    return columns


class Names(unittest.TestCase):
    def test_every_forced_zero_name_is_a_column(self):
        columns = real_columns()
        self.assertEqual(len(columns), 234)
        self.assertEqual([name for name in spells.FORCED_ZERO if name not in columns], [])
        self.assertEqual(len(set(spells.FORCED_ZERO)), len(spells.FORCED_ZERO), "a name is listed twice")
        self.assertEqual([name for name in spells.FORCED_ZERO_EFFECTS + spells.FORCED_ZERO_REAGENTS if name not in columns], [])
        self.assertEqual(len(spells.FORCED_ZERO_EFFECTS), 12)     # four fields in three slots
        self.assertEqual(len(spells.FORCED_ZERO_REAGENTS), 16)    # eight reagents and their counts
        spells.check_forced_zero(columns)   # the real lists pass

    def test_the_numbered_slots_are_checked_by_the_default_call(self):
        columns = real_columns()
        for group in ("FORCED_ZERO_EFFECTS", "FORCED_ZERO_REAGENTS"):
            with self.subTest(group):
                real = getattr(spells, group)
                setattr(spells, group, real + ("Bogus_9",))
                try:
                    with self.assertRaises(SystemExit) as refused:
                        spells.check_forced_zero(columns)
                    self.assertIn("Bogus_9", str(refused.exception))
                finally:
                    setattr(spells, group, real)
        for old in ("EffectBaseDice_1", "EffectAmplitude_1", "EffectBaseDice_3", "EffectAmplitude_2"):
            with self.subTest(old):
                with self.assertRaises(SystemExit):
                    spells.check_forced_zero(columns, (old,))

    def test_an_unknown_name_is_refused_and_named(self):
        columns = real_columns()
        for planted in ("NoSuchColumn", "TotemCategory_1", "StackAmount"):
            with self.subTest(planted):
                with self.assertRaises(SystemExit) as refused:
                    spells.check_forced_zero(columns, spells.FORCED_ZERO + (planted,))
                self.assertIn(planted, str(refused.exception))
                self.assertIn("FORCED_ZERO", str(refused.exception))
        with self.assertRaises(SystemExit) as refused:
            spells.check_forced_zero(columns, ("SpellLevel", "Bogus_1", "Bogus_2"))
        self.assertIn("Bogus_1", str(refused.exception))
        self.assertIn("Bogus_2", str(refused.exception))

    def test_the_four_old_names_are_refused(self):
        for old in ("EquippedItemSubClassMask", "EquippedItemInventoryTypeMask", "StackAmount", "ManaCostPercentage"):
            with self.subTest(old):
                with self.assertRaises(SystemExit):
                    spells.check_forced_zero(real_columns(), (old,))

    def test_a_name_is_matched_exactly(self):
        columns = real_columns()
        for near in ("manacost", "ManaCost ", "EquippedItemSubclass_1"):
            with self.subTest(near):
                with self.assertRaises(SystemExit):
                    spells.check_forced_zero(columns, (near,))


class Mutants(unittest.TestCase):
    """The check's own rules, each broken in a copy of the function, must let a planted name through."""

    def mutated(self, old, new):
        function = SOURCE[SOURCE.index("def check_forced_zero("):]
        function = function[:function.index("\n\n\n", 10)]
        self.assertEqual(function.count(old), 1, old)
        scope = {"FORCED_ZERO": spells.FORCED_ZERO, "FORCED_ZERO_EFFECTS": spells.FORCED_ZERO_EFFECTS,
                 "FORCED_ZERO_REAGENTS": spells.FORCED_ZERO_REAGENTS}
        exec(function.replace(old, new), scope)
        return scope["check_forced_zero"]

    def test_each_rule_has_a_mutant_that_lets_a_planted_name_through(self):
        columns = real_columns()
        planted = {
            "unknown names are not refused": ("Bogus_9",),
            "only the first name is checked": ("SpellLevel", "Bogus_9"),
            "the case is ignored": ("manacost",),
            "the given names are ignored": ("Bogus_9",),
            "the numbered slots are not checked": None,
        }
        mutants = {
            "unknown names are not refused": ("    if unknown:", "    if False:"),
            "only the first name is checked": ("for name in wanted if name not in columns]", "for name in wanted[:1] if name not in columns]"),
            "the case is ignored": ("if name not in columns]", "if name.lower() not in [c.lower() for c in columns]]"),
            "the given names are ignored": ("if names is None else names", "if True else names"),
            "the numbered slots are not checked": ("FORCED_ZERO + FORCED_ZERO_EFFECTS + FORCED_ZERO_REAGENTS if", "FORCED_ZERO if"),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(name):
                # the real check refuses the planted names; the mutant must not, so the planted-name tests above would be red
                if planted[name] is None:
                    # the default call must refuse a bad name in a numbered group; the mutant (which leaves the groups out) must not
                    check = self.mutated(old, new)
                    real = spells.FORCED_ZERO_EFFECTS
                    spells.FORCED_ZERO_EFFECTS = real + ("Bogus_9",)
                    try:
                        with self.assertRaises(SystemExit):
                            spells.check_forced_zero(columns)
                        check.__globals__["FORCED_ZERO_EFFECTS"] = spells.FORCED_ZERO_EFFECTS
                        check.__globals__["FORCED_ZERO_REAGENTS"] = spells.FORCED_ZERO_REAGENTS
                        try:
                            check(columns)
                        except SystemExit:
                            self.fail(f"survived: the mutant still refuses the planted name ({name})")
                    finally:
                        spells.FORCED_ZERO_EFFECTS = real
                    continue
                with self.assertRaises(SystemExit):
                    spells.check_forced_zero(columns, planted[name])
                try:
                    self.mutated(old, new)(columns, planted[name])
                except SystemExit:
                    self.fail(f"survived: the mutant still refuses the planted name ({name})")


class Wiring(unittest.TestCase):
    def test_main_checks_before_the_baseline_loop_and_the_loop_skips_nothing(self):
        main = SOURCE[SOURCE.index("def main():"):]
        check = main.index("check_forced_zero(columns)")
        loop = main.index("for column in FORCED_ZERO:")
        self.assertLess(check, loop)
        body = main[loop:main.index("for column in FORCED_ZERO_REAGENTS:", loop)]
        self.assertNotIn("if column in columns", body)
        self.assertIn("values[columns.index(column)] = 0", body)
        # the numbered slots: one loop each over its checked tuple, and no `in columns` guard left anywhere in the baseline
        self.assertIn("for column in FORCED_ZERO_EFFECTS:\n            values[columns.index(column)] = 0", main)
        self.assertIn("for column in FORCED_ZERO_REAGENTS:\n            values[columns.index(column)] = 0", main)
        self.assertNotIn("if prefix + suffix in columns", main)
        self.assertNotIn('in columns:\n                    values[columns.index(f"{prefix}', main)

    def test_the_check_is_exact_membership(self):
        function = SOURCE[SOURCE.index("def check_forced_zero("):]
        function = function[:function.index("\ndef ", 10)]
        self.assertIn("name not in columns", function)
        self.assertIn("raise SystemExit", function)


if __name__ == "__main__":
    unittest.main()
