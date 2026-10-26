"""diablocraft-crash-ancients-summon: Call of the Ancients must not cast a swapped AI.

Live crash 2026-10-01: the rift's OnCreatureAddWorld replaced the summoned Ancients' AI with
RiftMeleeAI, and Summon static_cast it to dc_ancient's AI; ScriptedAI::me is a different field,
so Configure's SetLevel hit garbage. What runs: the module's own dc_barbarian_call_of_the_ancients.h (AiAs,
IsAncientEntry) against mock AIs of the real shape. What does not: Summon and the rift hook
need a Map and a Player, so source guards pin that they use the guards. On the pre-fix tree
the header has no AiAs, so the harness does not compile and the guards fail.
"""
import re
import shutil
import subprocess
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch/ancients_ai"
ANCIENTS = (MODULE / "src/classes/barbarian/dc_barbarian_call_of_the_ancients.cpp").read_text(encoding="utf-8")
RIFT_AI = (MODULE / "src/monsters/dc_monster_ai.cpp").read_text(encoding="utf-8")


def body(marker, source):
    start = source.index(marker)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


class AncientsAiTests(unittest.TestCase):
    def test_guards_against_mock_ais(self):
        compiler = shutil.which("c++") or shutil.which("g++")
        if not compiler:
            self.skipTest("no C++ compiler")
        SCRATCH.mkdir(parents=True, exist_ok=True)
        binary = SCRATCH / "harness"
        built = subprocess.run([compiler, "-std=c++17", "-I", str(MODULE / "src/classes/barbarian"), "-o", str(binary),
                                str(MODULE / "tests/ancients_ai/harness.cpp")], capture_output=True, text=True)
        self.assertEqual(built.returncode, 0, "harness did not compile:\n" + built.stderr[-3000:])
        ran = harness_env.run([str(binary)], capture_output=True, text=True)
        self.assertEqual(ran.returncode, 0, ran.stderr)

    def test_no_unchecked_ai_cast_in_ancients(self):
        self.assertNotRegex(ANCIENTS, r"static_cast<\s*AI\s*\*>")
        self.assertNotRegex(ANCIENTS, r"\(\s*AI\s*\*\s*\)")
        summon = body("void Summon(Player* p, uint32 id)", ANCIENTS)
        self.assertIn("AiAs<AI>(c->AI())", summon)
        self.assertLess(summon.index("AiAs<AI>"), summon.index("Configure("))
        self.assertEqual(ANCIENTS.count("AiAs<AI>"), 3)   # Summon and both places in dc_ancient_bonus

    def test_rift_hook_leaves_our_scripted_creatures_alone(self):
        # The test is IsRiftTrash (also what a Greater Rift's Guardian clear spares); Strip returns on it.
        trash = body("bool IsRiftTrash(Creature const* creature)", RIFT_AI)
        self.assertIn("IsAncientEntry(creature->GetEntry())", trash)
        self.assertIn('GetScriptName().rfind("dc_", 0) == 0', trash)
        strip = body("void StripNativeAbilities(Creature* creature)", RIFT_AI)
        self.assertIn("if (!IsRiftTrash(creature))", strip)
        self.assertLess(strip.index("IsRiftTrash"), strip.index("AIM_Initialize"))

    def test_no_static_cast_of_an_ai_anywhere_in_the_module(self):
        bad = []
        for path in (MODULE / "src").rglob("*.cpp"):
            for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if re.search(r"static_cast<\s*[\w:]*AI\s*\*>|reinterpret_cast<\s*[\w:]*AI\s*\*>", line):
                    bad.append("%s:%d" % (path.relative_to(MODULE), number))
        self.assertEqual(bad, [])


    def test_idle_ancients_follow_the_owner(self):
        # diablocraft-i8i3: UpdateAI used to return when the owner had no target, and nothing gave the
        # Ancients a movement, so they stood where they were summoned (ruling 2026-10-02).
        update = body("void UpdateAI(uint32 diff) override", ANCIENTS)
        self.assertIn("PickTarget(", update)
        self.assertIn("MoveFollow(p,", update)
        self.assertIn("FOLLOW_MOTION_TYPE", update)
        self.assertIn("AttackStop()", update)
        self.assertIn("FollowAngle(index)", update)
        # the follow order sits on the no-target path, before the attack
        self.assertLess(update.index("MoveFollow("), update.index("AttackStart(target)"))
        self.assertNotIn("GetSelectedUnit()) target", update)

    def test_no_diagnostic_left(self):
        self.assertNotIn("DC ancients trace", ANCIENTS)


if __name__ == "__main__":
    unittest.main()