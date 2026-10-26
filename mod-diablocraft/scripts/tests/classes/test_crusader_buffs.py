"""The Crusader's timed sheet numbers (src/classes/crusader/dc_crusader_buffs.h and .cpp).

What this proves, and how:

  * **The rule that needs no core type.** tests/crusader_buffs/harness.cpp compiles the real dc_crusader_buffs.h with the
    numbers of the sheet rows that use it (Celerity's attack speed and its 3 seconds): a buff lasts to its last
    millisecond, a second cast adds a stack up to the cap and restarts the whole time, a buff that ran out starts again
    from one stack, a cap below one is one. Five mutations planted in a scratch copy (the end is a millisecond late, the
    cap is lost, a cast does not restart the time, an expired buff keeps its old stacks, an expired buff is still worth
    its number) must each make it fail.
  * **The wiring.** The sheet half puts the worth on the sheet as a Temporary contribution of the buff's own key, takes
    it off when the end time has passed, and a later cast moves the end (the earlier event finds it not over and leaves
    it).

What it does not prove: anything on a running server. The numbers reach the sheet in game: the Punish checks of
docs/test-diablocraft-7t4gv.1.md.

    python mod-diablocraft/scripts/tests/classes/test_crusader_buffs.py
"""

import csv
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
HEADER = "src/classes/crusader/dc_crusader_buffs.h"
SOURCES = [HEADER, "tests/crusader_buffs/harness.cpp"]
CODE = MODULE / "src/classes/crusader/dc_crusader_buffs.cpp"


def value(skill, rune, token):
    with (D3 / "crusader_skill_values.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = [r for r in csv.DictReader(stream) if (r["skill"], r["rune"], r["token"]) == (skill, rune, token)]
    assert len(rows) == 1, (skill, rune, token, len(rows))
    return float(rows[0]["value"])


def scratch_tree(mutate=None):
    """The headers one build stages ({path under src/: text}); the mutation edits one of them."""
    files = {source[len("src/"):]: (MODULE / source).read_text(encoding="utf-8")
             for source in SOURCES if source.startswith("src/")}
    if mutate:
        path, old, new = mutate
        key = path[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([MODULE / "tests/crusader_buffs/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("Punish", "Celerity", "duration_seconds"), value("Punish", "Celerity", "attack_speed_pct"), 3]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 10, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("the end is a millisecond late", (HEADER, "return held.until <= now;", "return held.until < now;")),
            ("the cap is lost", (HEADER, "std::min(held.stacks + std::max(1u, adds), std::max(1u, maxStacks))", "held.stacks + std::max(1u, adds)")),
            ("a cast does not restart the time", (HEADER, "held.until = now + ms;", "held.until = held.until ? held.until : now + ms;")),
            ("an expired buff keeps its stacks", (HEADER, "    if (held.until <= now)\n            held.stacks = 0;\n", "")),
            ("a cast adds one stack whatever it brings", (HEADER, "std::min(held.stacks + std::max(1u, adds), std::max(1u, maxStacks))",
                                                         "std::min(held.stacks + 1, std::max(1u, maxStacks))")),
            ("an expired buff is still worth its number", (HEADER, "return Over(held, now) ? 0.0 : perStack * held.stacks;",
                                                           "return perStack * held.stacks;")),
        ]
        for label, mutation in mutations:
            with self.subTest(label):
                try:
                    tree = scratch_tree(mutation)
                except AssertionError as error:
                    self.fail(str(error))
                out = build_and_run(tree)
                self.assertNotEqual(out.returncode, 0, f"{label} was not caught: {out.stdout[-500:]}")


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = CODE.read_text(encoding="utf-8")

    def test_the_sheet_takes_the_worth_and_gives_it_back(self):
        self.assertIn("Add(entry, Now(), ms, maxStacks, adds);", self.code)
        self.assertIn("worth = Worth(entry, Now(), perStack);", self.code)
        self.assertIn("Stats::AddContribution(key.guid, {Source::Temporary, key.stat, key.id, value, bucket});", self.code)
        self.assertIn("Stats::RemoveContribution(key.guid, Source::Temporary, key.stat, key.id);", self.code)

    def test_a_later_cast_moves_the_end(self):
        lapse = self.code[self.code.index("void Lapse("):self.code.index("} // namespace\n")]
        self.assertIn("!Over(found->second, Now())", lapse)
        # The sheet is touched outside the lock.
        self.assertLess(lapse.index("held.erase(found);"), lapse.index("Sheet(player, key, bucket, 0);"))
        self.assertEqual(lapse.count("lock_guard"), 1)

    def test_the_end_event_fires_after_the_end(self):
        self.assertIn("std::chrono::milliseconds(ms + 1)", self.code)


if __name__ == "__main__":
    unittest.main()
