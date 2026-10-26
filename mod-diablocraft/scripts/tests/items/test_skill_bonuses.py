"""DC::Items::SkillBonuses (src/items/dc_skill_bonuses.h): affix bonuses to a skill stack per skill id, a repeated equip notice
changes nothing, a changed affix keeps its contribution identity, and removal takes exactly its own contribution.

The harness (tests/skill_bonuses/harness.cpp, asserts on the production header) was built by nothing for a long time; this compiles
it through harness_env and runs it. Every rule is also broken in a copy of the header and the harness must then fail.

    python3 mod-diablocraft/scripts/tests/items/test_skill_bonuses.py
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
HARNESS = MODULE / "tests/skill_bonuses/harness.cpp"
HEADER = MODULE / "src/items/dc_skill_bonuses.h"
SCRATCH = MODULE.parent / "azerothcore-wotlk/build/_agent-scratch"
FLAGS = ["-std=c++17", "-O0", "-UNDEBUG"]    # the harness uses assert

# (what the mutant breaks, the text in the header, what it becomes)
MUTANTS = [
    ("a repeated equip notice adds again", "        Remove(id);\n        rows[id] = {skillId, value};", "        rows[id] = {skillId, value};"),
    ("a removal leaves the total", "totals[found->second.first] -= found->second.second;", ""),
    ("a removal leaves the row", "rows.erase(found);", ""),
    ("a bonus lands on every skill", "return found == totals.end() ? 0 : found->second;",
     "double all = 0; for (auto const& t : totals) all += t.second; return all;"),
    ("a bonus lands on no skill", "totals[skillId] += value;", "totals[0] += value;"),
    ("a skill that nothing gave bonus reads non-zero", "return found == totals.end() ? 0 : found->second;",
     "return found == totals.end() ? 1 : found->second;"),
]


def passes(header_text):
    """Compile the harness against `header_text` as dc_skill_bonuses.h and run it: (it passed, its output). The harness includes
    the header by a relative path, so a changed header and the harness stand in a scratch tree of the same shape."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="skill-bonuses-", dir=SCRATCH) as folder:
        source = HARNESS
        if header_text != HEADER.read_text(encoding="utf-8"):
            source = Path(folder) / "tests/skill_bonuses/harness.cpp"
            for path, data in ((source, HARNESS.read_bytes()), (Path(folder) / "src/items/dc_skill_bonuses.h", header_text.encode())):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        ran = harness_env.run([str(harness_env.build([source], flags=FLAGS))], capture_output=True, text=True)
    return ran.returncode == 0, ran.stdout + ran.stderr


class SkillBonuses(unittest.TestCase):
    def test_production_passes(self):
        ok, out = passes(HEADER.read_text(encoding="utf-8"))
        self.assertTrue(ok, out)
        self.assertIn("Skill bonuses: stacking", out)

    def test_every_rule_fails_when_broken(self):
        text = HEADER.read_text(encoding="utf-8")
        for what, old, new in MUTANTS:
            with self.subTest(what):
                self.assertEqual(text.count(old), 1, "the mutant's target moved: " + old)
                try:
                    ok, _ = passes(text.replace(old, new))
                except harness_env.BuildError:
                    continue  # a mutant that no longer compiles is red as well
                self.assertFalse(ok, "mutant survived: " + what)


if __name__ == "__main__":
    unittest.main()
