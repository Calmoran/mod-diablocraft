"""The tier rules of dc_tiers.h, driven: unlock boundaries, the tier x party x elite Life product and its 64-bit limits.

The harness is difficulty_tests.cpp (it includes the production header; nothing is copied). It used to be built only by hand from
its CMakeLists; this compiles it through harness_env (cached) and runs it. Every rule is also broken in a copy of the header
and the harness must then fail.

    python3 mod-diablocraft/scripts/tests/difficulty/test_tier_rules.py
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402

HERE = Path(__file__).resolve().parent
MODULE = HERE.parents[2]
HARNESS = HERE / "difficulty_tests.cpp"
HEADER = MODULE / "src/common/dc_tiers.h"
SCRATCH = MODULE.parent / "azerothcore-wotlk/build/_agent-scratch"
FLAGS = ["-std=c++17", "-O1"]

# (what the mutant breaks, the text in dc_tiers.h, what it becomes)
MUTANTS = [
    ("the character level bound is exclusive", "level >= rule.characterLevel", "level > rule.characterLevel"),
    ("the account level is ignored", "accountLevel >= rule.accountLevel", "true"),
    ("the solo Greater Rift is ignored", "beatenSoloGreaterRift >= rule.soloGreaterRift", "true"),
    ("the elite multiplier is ignored", "std::floor(base * tier * party * elite)", "std::floor(base * tier * party)"),
    ("the party multiplier is ignored", "std::floor(base * tier * party * elite)", "std::floor(base * tier * elite)"),
    ("a Life of zero is accepted", "life < 1 ||", "life < 0 ||"),
    ("a Life past 2^64 is accepted", "life >= 18446744073709551616.0", "life >= 1e30"),
    ("a Life that is not a number is accepted", "!std::isfinite(life) ||", "std::isinf(life) ||"),
]


def passes(header_text):
    """Compile the harness against `header_text` as dc_tiers.h and run it: (it passed, its output). The header is included by a
    relative path, so a changed header and the harness stand in a scratch tree of the same shape; the repo's own header compiles
    through the cache."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="tier-rules-", dir=SCRATCH) as folder:
        source = HARNESS
        if header_text != HEADER.read_text(encoding="utf-8"):
            source = Path(folder) / "scripts/tests/difficulty/difficulty_tests.cpp"
            for path, data in ((source, HARNESS.read_bytes()), (Path(folder) / "src/common/dc_tiers.h", header_text.encode())):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        ran = harness_env.run([str(harness_env.build([source], flags=FLAGS))], capture_output=True, text=True)
    return ran.returncode == 0, ran.stdout + ran.stderr


class TierRules(unittest.TestCase):
    def test_production_passes_every_rule(self):
        ok, out = passes(HEADER.read_text(encoding="utf-8"))
        self.assertTrue(ok, out)
        self.assertIn("overflow checks passed", out)

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
