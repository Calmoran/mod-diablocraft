"""diablocraft-ucv5p (Monk timed effects): the module state under "for N seconds" and the hooks that read it.

What this proves, and how:

  * **The maths.** tests/monk_effects/harness.cpp compiles the real dc_monk_effects.h: a bonus counts until its last
    millisecond and not after, a key cast again is refreshed and not stacked, stacks stop at their cap and end together,
    two keys add up, "deals x% less" multiplies per entry and never goes below nothing, a read never creates a book and a
    big table is swept of the books that ran out. Five mutations planted in a scratch copy (the end is one millisecond
    late, the stack cap is gone, the cuts do not multiply, a removed key stays, a read creates a book) must each make it
    fail.
  * **The wiring.** dc_combat.cpp asks the Monk at the Wizard's sites: the additive damage bonus and the target bonus of a
    hit, the victim adjustment of a periodic snapshot (the same target bonus, so a tick and a hit cannot drift apart), and
    the incoming factor at all four places the Wizard's is applied. The Monk's name appears in no other shared file.

What it does not prove: anything on a running server. Nothing applies an effect until a skill bead (Deadly Reach's
Foresight, Crippling Wave's Concussion and Breaking Wave, Hundred Fists' Assimilation) calls Monk::Effects.

    python mod-diablocraft/scripts/tests/classes/test_monk_effects.py
"""

import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
import barbarian_source  # noqa: E402

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
SOURCES = ["src/classes/monk/dc_monk_effects.h", "tests/monk_effects/harness.cpp"]
HEADER = "src/classes/monk/dc_monk_effects.h"


def scratch_tree(mutate=None):
    """The headers one build stages ({path under src/: text}); the mutation edits one of them."""
    files = {source[len("src/"):]: (MODULE / source).read_text(encoding="utf-8") for source in SOURCES if source.startswith("src/")}
    if mutate:
        path, old, new = mutate
        key = path[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([MODULE / "tests/monk_effects/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    return harness_env.run([str(binary)], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_book_and_the_ledger(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 25, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("the end is one millisecond late", (HEADER, "return e.until <= now;", "return e.until < now;")),
            ("the stack cap is gone", (HEADER, "std::min(entry->stacks + 1, std::max(1u, maxStacks))", "entry->stacks + 1")),
            ("the cuts do not multiply", (HEADER, "factor *= std::max(0.0,", "factor = std::max(0.0,")),
            ("a removed key stays", (HEADER, "return e.key == key; }),\n                entries_.end());",
                                     "return false; }),\n                entries_.end());")),
            ("a read creates a book", (HEADER, "return found == books_.end() ? nullptr : &found->second;",
                                       "return &books_[holder];")),
        ]
        for label, mutation in mutations:
            with self.subTest(label):
                try:
                    tree = scratch_tree(mutation)
                except AssertionError as error:
                    self.fail(str(error))
                out = build_and_run(tree)
                self.assertNotEqual(out.returncode, 0, f"{label} was not caught: {out.stdout[-500:]}")


if __name__ == "__main__":
    unittest.main()
