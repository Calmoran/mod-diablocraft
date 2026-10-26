"""The source-text guards of monk seven sided strike: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_monk_seven_sided_strike.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_monk_seven_sided_strike import MODULE, SOURCE  # noqa: E402


class Wiring(unittest.TestCase):
    def setUp(self):
        self.combat = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat" / "dc_combat_internal.h", *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])
        self.monk = (MODULE / "src/classes/monk/dc_monk.cpp").read_text(encoding="utf-8")

    def test_the_cast_path_hands_the_cast_over_before_any_hit(self):
        call = "if (Monk::Delayed(player, shell.spellId, targets, explicitTarget))\n                return;"
        self.assertEqual(self.combat.count(call), 1)
        order = [self.combat.index(m) for m in ("auto targets = ResolveTargets(player, info, shell.targeting",
                                                "Monk::Delayed(", "Monk::Begin(", "ResolveHit(player, target, punch.pct")]
        self.assertEqual(order, sorted(order))

    def test_dc_monk_dispatches_to_the_skills_file(self):
        self.assertIn("if (SevenSided::Is(spellId))\n            return SevenSided::BasePct(spellId);", self.monk)
        self.assertIn("return SevenSided::Start(player, spellId, targets, aimed);", self.monk)

    def test_the_strikes_ride_the_event_queue_and_restart_the_cooldown(self):
        text = (MODULE / SOURCE).read_text(encoding="utf-8")
        self.assertIn("player->m_Events.AddEventAtOffset([player, series, i] { StrikeNext(player, series, i); }", text)
        self.assertIn("Combat::SendSkillCooldown(player, id, Combat::SkillCooldownMilliseconds(player, id));", text)

    def test_a_press_with_no_enemy_is_refused_before_its_cost(self):
        # PM default (docs/decisions.md 2026-10-14): the skill needs a target, so no Spirit and no cooldown are spent.
        check = self.combat[self.combat.index("void OnSpellCheckCast(Spell* spell, bool, SpellCastResult& result) override"):]
        check = check[:check.index("\n            }\n")]
        refuse = ("if (!spell->IsTriggered() && !Monk::CanCast(player, spell->GetSpellInfo()->Id))\n                {\n"
                  "                    result = SPELL_FAILED_NO_VALID_TARGETS;\n                    return;")
        self.assertEqual(check.count(refuse), 1)
        self.assertIn("return SevenSided::CanCast(player, spellId);", self.monk)
        text = (MODULE / SOURCE).read_text(encoding="utf-8")
        can = text[text.index("bool CanCast(Player* player, std::uint32_t spellId)"):text.index("bool Start(")]
        self.assertIn("if (!Combat::Enemies(player, spellId, player->GetPosition(), Combat::TargetRadius(spellId)).empty())\n"
                      "            return true;", can)
        self.assertIn('return IsRune(spellId, "Sudden Assault") && selected && player->IsValidAttackTarget(selected) &&', can)
        self.assertIn('player->GetExactDist(selected) <= Tune("seven_sided_strike_teleport_yards");', can)

    def test_the_monk_is_immune_from_the_cast_to_the_last_strike(self):
        text = (MODULE / SOURCE).read_text(encoding="utf-8")
        self.assertIn("player->ApplySpellImmune(spellId, IMMUNITY_DAMAGE, SPELL_SCHOOL_MASK_ALL, on);", text)
        self.assertIn("player->ApplySpellImmune(spellId, IMMUNITY_SCHOOL, SPELL_SCHOOL_MASK_ALL, on);", text)
        start = text[text.index("bool Start("):]
        self.assertLess(start.index("Immune(player, spellId, true);"), start.index("AddEventAtOffset"))
        last = text[text.index("if (i + 1 == series->count)"):]
        self.assertIn("Immune(player, id, false);", last[:last.index("}")])

    def test_the_skill_is_named_only_in_the_monks_folder(self):
        for path in (MODULE / "src").rglob("*"):
            # dc_spell_shells.h is generated from the catalogue: every class's skill names, by design.
            if path.suffix in (".cpp", ".h") and "classes/monk" not in path.as_posix() and path.name != "dc_spell_shells.h":
                text = path.read_text(encoding="utf-8", errors="replace")
                self.assertNotIn("Seven-Sided", text, path)
                self.assertNotIn("SevenSided", text, path)


if __name__ == "__main__":
    unittest.main()
