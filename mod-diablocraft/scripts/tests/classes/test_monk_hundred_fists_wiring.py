"""The source-text guards of monk hundred fists: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_monk_hundred_fists.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path
import re

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_monk_hundred_fists import D3, MODULE, SKILL, read, tunables  # noqa: E402


class Wiring(unittest.TestCase):
    def setUp(self):
        self.cpp = (MODULE / "src/classes/monk/dc_monk_hundred_fists.cpp").read_text(encoding="utf-8")
        self.monk = (MODULE / "src/classes/monk/dc_monk.cpp").read_text(encoding="utf-8")
        self.combat = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat" / "dc_combat_internal.h", *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])

    def test_every_name_the_code_reads_exists(self):
        names = set(re.findall(r'Tune\("([a-z0-9_]+)"\)', self.cpp))
        names |= set(re.findall(r'Tunables::Has\("monk", "([a-z0-9_]+)"\)', self.cpp))
        # the combo window is Fists of Thunder's pair of tunables, shared by every Monk primary (never copied)
        self.assertEqual(names - {"fists_combo_window_frames", "fists_combo_frames_per_second"},
                         {n for n in tunables() if n.startswith("hundred_fists_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own)\((?:spellId|hands|IdOf\(""\)), "([a-z_]+)"', self.cpp))
        sheet_tokens = {r["token"] for r in read(D3 / "monk_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        # the base skill's 7 is read from Hands of Lightning's "from" row: the sheets state it nowhere else
        self.assertIn('Numbers::Num(hands, "hit_count", "from")', self.cpp)

    def test_alexs_values_are_set_and_say_so(self):
        # bead 760kv, cards q-1014-01..04: the wave is 5 yards wide, Assimilation holds 10 stacks
        for name, alex in (("hundred_fists_wave_width_yards", "5"), ("hundred_fists_assimilation_max_stacks", "10")):
            row = tunables()[name]
            self.assertEqual((row["d3_value"], row["value"]), ("", alex), name)
            self.assertIn("diablocraft-760kv", row["notes"], name)

    def test_the_cast_path_aims_before_it_begins(self):
        self.assertEqual(self.combat.count("Monk::Aim(player, shell.spellId, targets, explicitTarget);"), 1)
        order = [self.combat.index(m) for m in ("Monk::Aim(", "Monk::Begin(", "Monk::Cast(")]
        self.assertEqual(order, sorted(order))

    def test_both_hit_paths_tell_the_monk_of_a_crit(self):
        self.assertEqual(self.combat.count("if (hit.critical && hit.total>0) Monk::Critical(player, shell.spellId);"), 1)
        self.assertEqual(self.combat.count("if (hit.critical) Monk::Critical(player, spellId);"), 1)
        for call in ("Monk::Critical(player, shell.spellId)", "Monk::Critical(player, spellId)"):
            at = self.combat.index(call)
            self.assertIn("Abilities::CriticalHit", self.combat[at - 400:at], call)

    def test_blazing_fists_needs_its_rune_slotted(self):
        self.assertIn('Slotted(player, spellId)', self.cpp)
        self.assertIn('GetActionButton', self.cpp)

    def test_the_monk_dispatches_to_the_skill(self):
        for call in ("HundredFists::BasePct(spellId)", "HundredFists::Begin(player, spellId, primary)",
                     "HundredFists::Cast(player, spellId, targets, punch)", "HundredFists::Landed(player, target, spellId)",
                     "HundredFists::Aim(player, spellId, targets, aimed)"):
            self.assertEqual(self.monk.count(call), 1, call)

    def test_the_skill_keeps_its_own_combo(self):
        self.assertIn("Combo combo;", self.cpp)
        self.assertNotIn("fists_combo_window_frames_hundred", self.cpp)
        self.assertEqual({n for n in tunables() if "combo" in n}, {"fists_combo_window_frames", "fists_combo_frames_per_second"})


if __name__ == "__main__":
    unittest.main()
