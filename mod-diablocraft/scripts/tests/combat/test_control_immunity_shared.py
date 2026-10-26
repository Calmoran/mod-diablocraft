"""Immunity to control impairing effects has one list, in Combat::ControlImmunity::Set (diablocraft-rx0u7).

The gem powers (Invigorating Gemstone), Temple of Protection (Monk) and Bone Armor's Limited Immunity each kept their own copy of the same two lists:
the control-impairing mechanics, and the aura types that put them on. Bone Armor's was the shared Set; the other two now call it and Bane of the Trapped
asks ControlImmunity::Impaired, so there is one list to keep.

What this proves, and how (the code needs the core, so this is source text with mutants, like the other wiring tests):

  * **The list did not change.** The 14 mechanics and the 5 aura types the three copies held are written out here, and the shared Set applies exactly those,
    in the same order of calls: each mechanic as IMMUNITY_MECHANIC and each aura as IMMUNITY_STATE under the key, then, only when going on, strips every
    aura of those mechanics. Impaired tests the same mechanics.
  * **Each caller gives it as before.** The gem under key 0 (its own on/off bookkeeping kept), Temple of Protection under the rune's own key (on at entry,
    off when no circle holds it), Bone Armor under its spell id; no caller has a list of its own or applies the immunity itself.
  * **Mutants.** A dropped mechanic or aura, the key lost, the strip on both ways, a caller with its own copy again: each fails.

    python mod-diablocraft/scripts/tests/combat/test_control_immunity_shared.py
"""
import re
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[3]
SRC = MODULE / "src"
SHARED = SRC / "combat/dc_control_immunity.cpp"
HEADER = SRC / "combat/dc_control_immunity.h"
GEM = SRC / "combat/dc_gem_powers.cpp"
MONK = SRC / "classes/monk/dc_monk_inner_sanctuary.cpp"
BONE = SRC / "classes/necromancer/dc_necromancer_bone_armor.cpp"

MECHANICS = ["CHARM", "DISORIENTED", "FEAR", "ROOT", "SILENCE", "SLEEP", "SNARE", "STUN", "FREEZE", "KNOCKOUT", "POLYMORPH", "HORROR", "DAZE", "SAPPED"]
AURAS = ["SPELL_AURA_MOD_STUN", "SPELL_AURA_MOD_ROOT", "SPELL_AURA_MOD_FEAR", "SPELL_AURA_MOD_CONFUSE", "SPELL_AURA_MOD_DECREASE_SPEED"]


def read(path):
    return path.read_text(encoding="utf-8")


def shared_failures(text):
    flat = re.sub(r"\s+", " ", text)
    wrong = []
    listed = re.search(r"constexpr std::uint64_t ControlImpairing = (.*?);", flat)
    if not listed or re.findall(r"MECHANIC_(\w+)", listed[1]) != MECHANICS:
        wrong.append("the mechanics are the fourteen, in order")
    auras = re.search(r"for \(AuraType aura : \{(.*?)\}\)", flat)
    if not auras or [a.strip() for a in auras[1].split(",")] != AURAS:
        wrong.append("the aura types are the five, in order")
    for need, why in (
            ("if (!player) return;", "no player, nothing"),
            ("if (ControlImpairing & (1ull << mechanic)) player->ApplySpellImmune(key, IMMUNITY_MECHANIC, mechanic, on);", "each mechanic under the key"),
            ("player->ApplySpellImmune(key, IMMUNITY_STATE, aura, on);", "each aura type under the key"),
            ("if (on) Strip(player);", "going on strips what is already on"),
            ("void Strip(Player* player) { if (player) player->RemoveAurasWithMechanic(ControlImpairing); }", "Strip takes every control aura off and leaves no immunity"),
            ("return unit && unit->HasAuraWithMechanic(ControlImpairing);", "Impaired tests the same mechanics")):
        if need not in flat:
            wrong.append(why)
    if "for (unsigned mechanic = 1; mechanic < MAX_MECHANIC; ++mechanic)" not in flat:
        wrong.append("the loop runs over the mechanics")
    return wrong


def caller_failures(gem, monk, bone):
    wrong = []
    flat = lambda t: re.sub(r"\s+", " ", t)
    gem, monk, bone = flat(gem), flat(monk), flat(bone)
    body = gem[gem.index("void SetControlImmunity("):] if "void SetControlImmunity(" in gem else ""
    body = body[:body.index("void PutShield(")] if "void PutShield(" in body else body
    if "ControlImmunity::Set(player, 0, on);" not in body:
        wrong.append("the gem gives it under key 0")
    if "changed = buffs.immune != on;" not in body or "if (!changed) return;" not in body:
        wrong.append("the gem keeps its on/off bookkeeping")
    if "ControlImmunity::Impaired(target)" not in gem:
        wrong.append("Bane of the Trapped asks the shared test")
    if "ControlImmunity::Set(ally, id, true);" not in monk or "ControlImmunity::Set(ally, key, false);" not in monk:
        wrong.append("Temple of Protection gives and takes it under the rune's key")
    if "ControlImmunity::Set(player, spellId, true);" not in bone or "ControlImmunity::Set(player, spellId, false);" not in bone:
        wrong.append("Limited Immunity gives and takes it under its spell id")
    for name, text in (("the gem powers", gem), ("Temple of Protection", monk), ("Bone Armor", bone)):
        if "ControlImpairing" in text or "ApplySpellImmune(" in text and name != "the gem powers":
            wrong.append(name + " has a list or an immunity of its own")
    if "IMMUNITY_MECHANIC" in gem and "ControlImmunity" in gem and "ApplySpellImmune(0, IMMUNITY_MECHANIC" in gem:
        wrong.append("the gem applies the mechanics itself")
    return wrong


class Shared(unittest.TestCase):
    def test_the_list_is_the_one_the_three_copies_held(self):
        self.assertEqual([], shared_failures(read(SHARED)))

    def test_the_header_names_the_two_calls(self):
        text = re.sub(r"\s+", " ", read(HEADER))
        self.assertIn("void Set(Player* player, std::uint32_t key, bool on);", text)
        self.assertIn("bool Impaired(Unit const* unit);", text)

    def test_each_caller_gives_it_as_before_with_no_copy(self):
        self.assertEqual([], caller_failures(read(GEM), read(MONK), read(BONE)))

    def test_the_shared_mutants_fail(self):
        real = read(SHARED)
        mutants = {
            "a_mechanic_dropped": ("(1ull << MECHANIC_DAZE) | (1ull << MECHANIC_SAPPED);", "(1ull << MECHANIC_DAZE);"),
            "mechanic_order": ("(1ull << MECHANIC_CHARM) | (1ull << MECHANIC_DISORIENTED)", "(1ull << MECHANIC_DISORIENTED) | (1ull << MECHANIC_CHARM)"),
            "an_aura_dropped": ("SPELL_AURA_MOD_CONFUSE,\n                              SPELL_AURA_MOD_DECREASE_SPEED", "SPELL_AURA_MOD_CONFUSE"),
            "the_key_lost_for_mechanics": ("player->ApplySpellImmune(key, IMMUNITY_MECHANIC, mechanic, on);", "player->ApplySpellImmune(0, IMMUNITY_MECHANIC, mechanic, on);"),
            "the_key_lost_for_auras": ("player->ApplySpellImmune(key, IMMUNITY_STATE, aura, on);", "player->ApplySpellImmune(0, IMMUNITY_STATE, aura, on);"),
            "stripped_going_off_too": ("if (on)\n            Strip(player);", "Strip(player);"),
            "never_stripped": ("player->RemoveAurasWithMechanic(ControlImpairing);", ""),
            "impaired_tests_nothing": ("unit->HasAuraWithMechanic(ControlImpairing)", "unit->HasAuraWithMechanic(0)"),
            "no_null_player": ("if (!player)\n            return;", ""),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply")
                self.assertNotEqual([], shared_failures(real.replace(old, new, 1)), name + " survived")

    def test_the_caller_mutants_fail(self):
        gem, monk, bone = read(GEM), read(MONK), read(BONE)
        mutants = {
            "gem_key": ("gem", "ControlImmunity::Set(player, 0, on);", "ControlImmunity::Set(player, 1, on);"),
            "gem_own_list_again": ("gem", "ControlImmunity::Set(player, 0, on);", "ControlImmunity::Set(player, 0, on);\n            constexpr std::uint64_t ControlImpairing = 0;"),
            "gem_trapped_own_test": ("gem", "ControlImmunity::Impaired(target)", "target->HasAuraWithMechanic(1)"),
            "gem_bookkeeping_gone": ("gem", "if (!changed)\n                return;", ""),
            "monk_on_key": ("monk", "ControlImmunity::Set(ally, id, true);", "ControlImmunity::Set(ally, 0, true);"),
            "monk_off_key": ("monk", "ControlImmunity::Set(ally, key, false);", "ControlImmunity::Set(ally, 0, false);"),
            "monk_own_apply": ("monk", "ControlImmunity::Set(ally, id, true);", "ally->ApplySpellImmune(id, IMMUNITY_STATE, SPELL_AURA_MOD_STUN, true);"),
            "bone_key": ("bone", "ControlImmunity::Set(player, spellId, true);", "ControlImmunity::Set(player, 0, true);"),
        }
        texts = {"gem": gem, "monk": monk, "bone": bone}
        for name, (which, old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertGreaterEqual(texts[which].count(old), 1, name + " does not apply")
                changed = dict(texts, **{which: texts[which].replace(old, new, 1)})
                self.assertNotEqual([], caller_failures(changed["gem"], changed["monk"], changed["bone"]), name + " survived")


if __name__ == "__main__":
    unittest.main()
