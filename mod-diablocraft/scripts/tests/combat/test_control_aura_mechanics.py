"""Torment's own control auras carry their mechanic (legendary powers P2, diablocraft-r2jz4).

    python3 mod-diablocraft/scripts/tests/combat/test_control_aura_mechanics.py

A condition on an enemy's control state (slowed, stunned, feared, rooted...) reads the aura's mechanic, the way Bane of the Trapped
does (`HasAuraWithMechanic`, src/combat/dc_gem_powers.cpp). A control aura with no mechanic is invisible to it. This scans every spell
record the module writes (the db-world updates, in the order the updater applies them, a later row for an id replacing an earlier one)
and lists each apply-aura effect of a control type whose spell mechanic and effect mechanic carry none of that type's mechanics.

The scan is run on planted rows first (a snare with no mechanic, a stun with the wrong one, a damage effect that only names an aura)
and must find or spare them; then on the real module, where the gaps it finds are pinned in KNOWN_GAPS: a new gap fails the test, and
so does a fixed one still listed. No row of the Wastes build reads a control state, so the gaps are reported, not fixed here.
What it does not scan: auras the C++ builds at run time, and the stock spells the client already carries.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from test_control_immunity_gap import MODULE, insert_rows, number  # noqa: E402

# aura type -> (name, the mechanics that make it visible as that control), from SpellAuraDefines.h and Mechanics (SharedDefines.h).
CONTROL = {5: ("confuse", {2}),    # SPELL_AURA_MOD_CONFUSE   -> MECHANIC_DISORIENTED
           6: ("charm", {1}),      # SPELL_AURA_MOD_CHARM     -> MECHANIC_CHARM
           7: ("fear", {5}),       # SPELL_AURA_MOD_FEAR      -> MECHANIC_FEAR
           12: ("stun", {12, 13}), # SPELL_AURA_MOD_STUN      -> MECHANIC_STUN, or FREEZE (the Wizard's Frozen)
           26: ("root", {7, 13}),  # SPELL_AURA_MOD_ROOT      -> MECHANIC_ROOT, or FREEZE
           27: ("silence", {9}),   # SPELL_AURA_MOD_SILENCE   -> MECHANIC_SILENCE
           33: ("snare", {11})}    # SPELL_AURA_MOD_DECREASE_SPEED -> MECHANIC_SNARE
# SPELL_EFFECT_APPLY_AURA, PERSISTENT_AREA_AURA, APPLY_AREA_AURA_PARTY, _RAID, _FRIEND, _ENEMY: the effects whose aura field is read.
AURA_EFFECTS = {6, 27, 35, 65, 128, 129}

# The gaps today, by spell id (name, effect slot, aura). Slows that never name MECHANIC_SNARE: Gathering Storm, Avalanche - Snow-Capped
# Mountain, Threatening Shout - Intimidate, Frozen Pulse, Knockback, the six Slow Time bubbles and the six follow records of Crown of the Primus
# (diablocraft-bl9iz; a mechanic on an aura worn by the Wizard himself would let a snare-removing effect take it off); Leap - Death from Above carries
# MECHANIC_STUN on its snare. For the PM to file (docs/workers/claude-worker.md, diablocraft-r2jz4).
KNOWN_GAPS = {
    "81197": ("Gathering Storm", 1, "snare"),
    "81404": ("Avalanche - Snow-Capped Mountain", 2, "snare"),
    "81429": ("Threatening Shout - Intimidate", 2, "snare"),
    "81797": ("Leap - Death from Above", 1, "snare"),
    "82410": ("Frozen Pulse", 1, "snare"),
    "82411": ("Knockback", 1, "snare"),
    "83324": ("Slow Time - bubble", 1, "snare"),
    "83325": ("Slow Time - Time Warp - bubble", 1, "snare"),
    "83326": ("Slow Time - Point of No Return - bubble", 1, "snare"),
    "83327": ("Slow Time - Time Shell - bubble", 1, "snare"),
    "83328": ("Slow Time - Exhaustion - bubble", 1, "snare"),
    "83329": ("Slow Time - Stretch Time - bubble", 1, "snare"),
    "83365": ("Slow Time - follow", 1, "snare"),
    "83366": ("Slow Time - Time Warp - follow", 1, "snare"),
    "83367": ("Slow Time - Point of No Return - follow", 1, "snare"),
    "83368": ("Slow Time - Time Shell - follow", 1, "snare"),
    "83369": ("Slow Time - Exhaustion - follow", 1, "snare"),
    "83370": ("Slow Time - Stretch Time - follow", 1, "snare"),
}


def gaps(rows):
    """{spell id: (name, effect slot, control)} for each control apply-aura effect with none of its mechanics."""
    found = {}
    for row in rows:
        for slot in (1, 2, 3):
            aura = number(row.get("EffectAura_%d" % slot))
            if aura not in CONTROL or number(row.get("Effect_%d" % slot)) not in AURA_EFFECTS:
                continue
            name, wanted = CONTROL[aura]
            if not ({number(row.get("Mechanic")), number(row.get("EffectMechanic_%d" % slot))} & wanted):
                found[row["ID"]] = (row.get("Name_Lang_enUS", ""), slot, name)
    return found


def module_rows():
    rows = {}
    for path in sorted((MODULE / "data/sql/db-world/updates").glob("*.sql")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if "spell_dbc" in text:
            for row in insert_rows(text, "spell_dbc"):
                rows[row["ID"]] = row
    return list(rows.values())


class ScanFindsWhatItIsFor(unittest.TestCase):
    COLUMNS = ("ID", "Name_Lang_enUS", "Mechanic", "Effect_1", "EffectAura_1", "EffectMechanic_1")

    def row(self, effect=6, aura=33, mechanic=0, effect_mechanic=0, sid="1"):
        return dict(zip(self.COLUMNS, (sid, "Planted", str(mechanic), str(effect), str(aura), str(effect_mechanic))))

    def test_a_snare_with_no_mechanic_is_found(self):
        self.assertEqual({"1": ("Planted", 1, "snare")}, gaps([self.row()]))

    def test_the_spell_mechanic_or_the_effect_mechanic_is_enough(self):
        self.assertEqual({}, gaps([self.row(mechanic=11)]))
        self.assertEqual({}, gaps([self.row(effect_mechanic=11)]))

    def test_the_wrong_mechanic_is_found_and_freeze_is_a_stun(self):
        self.assertIn("1", gaps([self.row(aura=12, mechanic=18)]))
        self.assertEqual({}, gaps([self.row(aura=12, mechanic=13)]))

    def test_each_control_is_checked_against_its_own_mechanic(self):
        for aura, (_, wanted) in CONTROL.items():
            with self.subTest(aura=aura):
                self.assertIn("1", gaps([self.row(aura=aura)]))
                for mechanic in wanted:
                    self.assertEqual({}, gaps([self.row(aura=aura, mechanic=mechanic)]))
                other = ({m for _, w in CONTROL.values() for m in w} - wanted).pop()
                self.assertIn("1", gaps([self.row(aura=aura, mechanic=other)]))

    def test_a_damage_effect_that_only_names_an_aura_is_spared(self):
        self.assertEqual({}, gaps([self.row(effect=3, aura=12)]))

    def test_an_aura_that_is_not_a_control_is_spared(self):
        self.assertEqual({}, gaps([self.row(aura=3)]))


class RealModule(unittest.TestCase):
    def test_the_gaps_are_the_known_ones(self):
        found = gaps(module_rows())
        self.assertEqual(KNOWN_GAPS, found, "a control aura gained or lost a mechanic: update KNOWN_GAPS and report it")

    def test_the_scan_reads_the_control_auras_the_module_writes(self):
        rows = module_rows()
        controlling = {name for row in rows for slot in (1, 2, 3)
                       for name in [CONTROL.get(number(row.get("EffectAura_%d" % slot)), (None,))[0]] if name}
        self.assertEqual({"confuse", "fear", "root", "snare", "stun"}, controlling)
        self.assertGreater(len(rows), 500)


if __name__ == "__main__":
    unittest.main()
