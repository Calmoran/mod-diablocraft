"""The source-text guards of monk epiphany: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_monk_epiphany.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_monk_epiphany import CONE_SKILLS, MODULE  # noqa: E402


class Wiring(unittest.TestCase):
    def setUp(self):
        self.monk = (MODULE / "src/classes/monk/dc_monk.cpp").read_text(encoding="utf-8")

    def body(self, signature):
        start = self.monk.index(signature)
        return self.monk[start:self.monk.index("\n    }\n", start)]

    def test_the_punch_asks_epiphany_first(self):
        body = self.body("std::optional<double> BasePct(std::uint32_t spellId)")
        self.assertLess(body.index("Epiphany::BasePct(spellId)"), body.index("FistsOf(spellId)"))

    def test_the_dash_comes_before_the_punch(self):
        body = self.body("Punch Begin(Player* player, std::uint32_t spellId, Unit* primary)")
        self.assertLess(body.index("Epiphany::Dash(player, spellId, primary);"), body.index("return punch;"))

    def test_a_cast_at_a_selected_enemy_dashes_before_its_hits_are_found(self):
        # diablocraft-q73to: Combat::ResolveCast asks Monk::Approach with the selected enemy before it resolves the targets,
        # and a dash that moved the Monk searches the cone again from where it landed.
        combat = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat" / "dc_combat_internal.h", *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])

        def order(text):
            start = text.index("void ResolveCast(Player* player, Shell const& shell, Position const& launched")
            body = text[start:text.index("\n        }\n", start)]
            try:
                call = body.index("Monk::Approach(player, shell.spellId, explicitTarget)")
                cone = body.index("reached = ConeFrom(player, info, shell.targeting.radius);")
                targets = body.index("ResolveTargets(player, info, shell.targeting, center, reached, explicitTarget)")
            except ValueError:
                return False
            return call < cone < targets and "center = player->GetPosition();" in body[call:targets]

        self.assertTrue(order(combat))
        # and the check can fail: the call after the targets, or the cone not searched again
        self.assertFalse(order(combat.replace("Monk::Approach(player, shell.spellId, explicitTarget)", "false")))
        self.assertFalse(order(combat.replace("reached = ConeFrom(player, info, shell.targeting.radius);", "")))
        self.assertFalse(order(combat.replace("center = player->GetPosition();", "")))

    def test_the_cone_is_the_cores_own_from_the_new_spot(self):
        combat = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat" / "dc_combat_internal.h", *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])
        body = combat[combat.index("std::vector<ObjectGuid> ConeFrom("):]
        body = body[:body.index("\n        }\n")]
        for token in ("G3D::toRadians(60.0f)", "sSpellMgr->GetSpellCone(info->Id)", "TARGET_UNIT_CONE_ENEMY_104",
                      "Acore::WorldObjectSpellConeTargetCheck check(angle, radius, player, info, TARGET_CHECK_ENEMY",
                      "player->GetPositionX(), player->GetPositionY()"):
            self.assertIn(token, body)

    def test_without_epiphany_up_nothing_dashes(self):
        text = (MODULE / "src/classes/monk/dc_monk_epiphany.cpp").read_text(encoding="utf-8")
        start = text.index("bool Dash(Player* player")
        body = text[start:text.index("\n    }\n", start)]
        up = body.index("found == states.end() || found->second.until <= Now()")
        self.assertIn("return false;", body[up:body.index("NearTeleportTo")])
        self.assertLess(up, body.index("NearTeleportTo"))
        self.assertEqual(body.count("return true;"), 1)
        self.assertIn("return Epiphany::Dash(player, spellId, selected);", self.body("bool Approach(Player* player"))
        for skill in CONE_SKILLS:
            self.assertIn(f'"{skill}"', text[:text.index("Shells::Ability const* Row")])

    def test_the_cast_starts_the_buff_before_the_fists_code(self):
        # the other skills' early returns above it are each for their own spell ids only
        body = self.body("void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets")
        self.assertLess(body.index("Epiphany::Cast(player, spellId);"), body.index("FistsOf(spellId)"))

    def test_ascendance_runs_in_the_cast_paths_order(self):
        # Casting (OnCast) starts the decision, the dash in Monk::Begin re-checks it, Landed asks it per hit.
        text = (MODULE / "src/classes/monk/dc_monk_epiphany.cpp").read_text(encoding="utf-8")
        for function, call in (("void Casting(Player* player", "state.ascent.Begin(spellId,"),
                               ("bool Dash(Player* player", "state.ascent.Dashed(spellId,"),
                               ("void Landed(Player* player", "ascent.Hit(spellId, Now())")):
            with self.subTest(function):
                start = text.index(function)
                self.assertIn(call, text[start:text.index("\n    }\n", start)])
        self.assertIn("Epiphany::RegisterScripts();", self.body("void RegisterScripts()"))
        self.assertIn("states.erase(player->GetGUID().GetRawValue());", text[text.index("void OnPlayerLogout"):])

    def test_every_cast_and_every_hit_reach_epiphany(self):
        self.assertIn("Epiphany::Casting(player, spellId);", self.body("void Casting(Player* player, std::uint32_t spellId)"))
        body = self.body("void Landed(Player* player, Unit* target, std::uint32_t spellId)")
        call = body.index("Epiphany::Landed(player, target, spellId);")
        self.assertEqual(body.count("return", 0, call), 1)  # only the null guard comes before it

    def test_the_oncast_hook_asks_the_monk_beside_the_wizard(self):
        combat = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat" / "dc_combat_internal.h", *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])
        self.assertEqual(combat.count("Monk::Casting(player, shell.spellId);"), 1)
        self.assertIn("Wizard::Begin(player, shell.spellId, GetExplTargetUnit());\n                Monk::Casting(player, shell.spellId);",
                      combat)

    def test_the_cast_path_calls_begin_before_the_hits_and_cast_after(self):
        combat = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat" / "dc_combat_internal.h", *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])
        order = [combat.index(m) for m in ("Monk::Begin(", "ResolveHit(player, target, punch.pct", "Monk::Cast(")]
        self.assertEqual(order, sorted(order))


if __name__ == "__main__":
    unittest.main()
