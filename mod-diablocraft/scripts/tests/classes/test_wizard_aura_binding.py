"""GitHub #64: Wizard aura handlers must bind to the effects their records carry.

The core validates every AuraScript hook against the record at startup
(_SpellScript::EffectAuraNameCheck) and logs "did not match dbc effect data" for
each one that finds no matching effect. This applies the same test to every
generated record the two scripts are attached to, for the hooks dc_wizard.cpp
registers, and requires zero mismatches. The old, unconditional registration is
put back as a mutation and must reproduce the 52 the worldserver logged
(42 dc_wizard_buff, 10 dc_wizard_slow).

Not covered: the core's own log at a real startup; docs/test-diablocraft-wizard-
cooldowns-auras.md has that check.
"""
import re
import unittest
from pathlib import Path
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import wizard_source  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
GENERATED = MODULE / "data" / "generated" / "spell_shells.sql"
WIZARD = wizard_source.CPP.read_text(encoding="utf-8")

SPELL_AURA_ANY = None
PERIODIC_DUMMY = 226
EFFECT_ALL = None


def rows(sql):
    columns = [c.strip(" `") for c in re.search(r"INSERT INTO `spell_dbc` \((.*?)\) VALUES", sql)[1].split(",")]
    out = {}
    for line in sql.splitlines():
        found = re.match(r"\((\d+),", line)
        if found:
            values = re.findall(r"'(?:[^']|'')*'|[^,()]+", line.strip().rstrip(",;").lstrip("(").rstrip(")"))
            out[int(found[1])] = dict(zip(columns, (v.strip() for v in values)))
    return out


def scripted(sql):
    result = {}
    for script in ("dc_wizard_buff", "dc_wizard_slow"):
        found = re.search(r"INSERT INTO spell_script_names \(spell_id,ScriptName\) VALUES ((?:\(\d+,'%s'\),?)+);" % script,
                          sql)
        result[script] = [int(n) for n in re.findall(r"\((\d+),", found[1])] if found else []
    return result


def matches(record, aura, index=EFFECT_ALL):
    """The core's EffectAuraNameCheck over one record for one (index, aura) binding."""
    for slot in (1, 2, 3):
        if index is not EFFECT_ALL and index != slot - 1:
            continue
        name = int(record["EffectAura_%d" % slot])
        if name and (aura is SPELL_AURA_ANY or name == aura):
            return True
    return False


def mismatches(records, ids, hooks):
    """(spell id, hook) for every hook the core would log for these records."""
    return [(sid, hook) for sid in ids for hook, (aura, index) in hooks(records[sid]).items()
            if not matches(records[sid], aura, index)]


def buff_hooks(conditional):
    def hooks(record):
        found = {"calc": (SPELL_AURA_ANY, EFFECT_ALL), "apply": (SPELL_AURA_ANY, 0), "remove": (SPELL_AURA_ANY, 0)}
        if not conditional or matches(record, PERIODIC_DUMMY):
            found["tick"] = (PERIODIC_DUMMY, EFFECT_ALL)
        return found
    return hooks


def slow_hooks(conditional):
    def hooks(record):
        found = {"calc": (SPELL_AURA_ANY, EFFECT_ALL), "entered": (SPELL_AURA_ANY, 0), "left": (SPELL_AURA_ANY, 0)}
        if not conditional or matches(record, SPELL_AURA_ANY, 2):
            found["ally apply"] = (SPELL_AURA_ANY, 2)
            found["ally remove"] = (SPELL_AURA_ANY, 2)
        return found
    return hooks


class WizardAuraBinding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sql = GENERATED.read_text(encoding="utf-8")
        cls.records, cls.scripts = rows(sql), scripted(sql)

    def test_every_scripted_record_exists(self):
        for script, ids in self.scripts.items():
            self.assertTrue(ids, script)
            self.assertEqual([sid for sid in ids if sid not in self.records], [], script)

    def test_the_old_unconditional_registration_reproduces_the_logged_52(self):
        buff = mismatches(self.records, self.scripts["dc_wizard_buff"], buff_hooks(False))
        slow = mismatches(self.records, self.scripts["dc_wizard_slow"], slow_hooks(False))
        self.assertEqual((len(buff), len(slow)), (42, 10), (buff[:3], slow[:3]))

    def test_the_shipped_registration_binds_everywhere(self):
        self.assertEqual(mismatches(self.records, self.scripts["dc_wizard_buff"], buff_hooks(True)), [])
        self.assertEqual(mismatches(self.records, self.scripts["dc_wizard_slow"], slow_hooks(True)), [])

    def test_the_source_registers_the_conditions_this_models(self):
        self.assertIn("if (HasAuraEffect(m_scriptSpellId, SPELL_AURA_PERIODIC_DUMMY))\n"
                      "                    OnEffectPeriodic +=", WIZARD)
        self.assertIn("if (HasAuraEffect(m_scriptSpellId, SPELL_AURA_ANY, EFFECT_2))", WIZARD)
        # The unconditional registrations must be gone.
        self.assertNotRegex(WIZARD, r"\n\s*OnEffectPeriodic \+= AuraEffectPeriodicFn\(dc_wizard_buff::Tick, EFFECT_ALL")
        self.assertNotRegex(WIZARD, r"\n {16}AfterEffectApply \+=\s*AuraEffectApplyFn\(dc_wizard_slow::Ally, EFFECT_2")

    def test_the_handlers_that_stay_run_where_they_did(self):
        """A periodic buff still ticks and Stretch Time still has its ally hooks."""
        periodic = [sid for sid in self.scripts["dc_wizard_buff"] if matches(self.records[sid], PERIODIC_DUMMY)]
        self.assertGreaterEqual(len(periodic), 3, "Storm Armor, Frozen Storm and Frozen Mist tick")
        ally = [sid for sid in self.scripts["dc_wizard_slow"] if matches(self.records[sid], SPELL_AURA_ANY, 2)]
        # Stretch Time's bubble, Archon's Slow Time, whose third slot keeps a
        # donor aura name (216) on an empty effect: it binds, and never fires,
        # and the six follow records (Crown of the Primus, 83365-83370), whose
        # third slot is Stretch Time's ally effect.
        self.assertEqual(sorted(ally), [83277, 83329, 83365, 83366, 83367, 83368, 83369, 83370])


if __name__ == "__main__":
    unittest.main()
