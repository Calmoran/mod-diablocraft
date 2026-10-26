"""The timed damage boost, the shared piece (src/combat/dc_damage_boost*.h/.cpp), diablocraft-vawmy.33.

What this proves, and how:

  * **The rules that need no core type.** tests/damage_boost/harness.cpp compiles the real dc_damage_boost_math.h and is driven with cases from the
    meaning of "N% more damage for S seconds": a boost lasts S seconds from the moment it is given (the end exclusive), multiplies a hit by
    1 + N/100 while it stands and by 1 after, and no percent or no seconds is no boost. Planted differences in a scratch copy of the header must each
    make the driver fail.
  * **The wiring.** A hit reads the boosts of the player as multipliers of their own (ComputeHit, beside the Power Pylon's); a second boost under one key
    replaces the first and boosts under different keys are separate factors; a boost that has run out is dropped when read; the boosts go with the
    player on logout; the scripts are registered in Combat::RegisterScripts. The shared files name no class and no skill (test_class_checks.py).

    python mod-diablocraft/scripts/tests/combat/test_damage_boost.py
"""
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src/combat"
MATH = SRC / "dc_damage_boost_math.h"
ENGINE = SRC / "dc_damage_boost.cpp"
COMBAT = SRC / "dc_combat.cpp"
HARNESS = MODULE / "tests/damage_boost/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731


def cases():
    out = []
    # given: the end is seconds from now in ms; nothing for no percent or no seconds
    for pct, now, seconds, want in ((15, 1000, 10, "pct=15 until=11000"), (15, 0, 0.5, "pct=15 until=500"), (-20, 5000, 3, "pct=-20 until=8000"),
                                    (0, 1000, 10, "pct=0 until=0"), (15, 1000, 0, "pct=0 until=0"), (15, 1000, -4, "pct=0 until=0")):
        out.append((T("given", pct, now, seconds), want))
    # live: stands before its end, not at it or after, and a boost of nothing never stands
    for pct, until, now, want in ((15, 11000, 10999, 1), (15, 11000, 11000, 0), (15, 11000, 20000, 0), (15, 11000, 0, 1), (0, 11000, 5000, 0), (-20, 11000, 5000, 1)):
        out.append((T("live", pct, until, now), str(want)))
    # mult: 1 + pct / 100 while it stands, 1 after, a negative boost is a cut
    for pct, until, now, want in ((15, 11000, 5000, "1.15"), (15, 11000, 11000, "1"), (100, 11000, 5000, "2"), (-20, 11000, 5000, "0.8"), (0, 11000, 5000, "1"),
                                  (50, 11000, 99999, "1")):
        out.append((T("mult", pct, until, now), want))
    return out


def drive(header_text, name="real"):
    SCRATCH.mkdir(parents=True, exist_ok=True)
    binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files={"combat/dc_damage_boost_math.h": header_text})
    work = Path(tempfile.mkdtemp(prefix="dmgboost-%s-" % name, dir=str(SCRATCH)))
    try:
        lines = cases()
        (work / "cases.txt").write_text("\n".join(line for line, _ in lines) + "\n")
        run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
        assert run.returncode == 0, run.stderr
        return [w for _, w in lines if w is not None], run.stdout.split("\n")[:-1]
    finally:
        shutil.rmtree(work, ignore_errors=True)


class Rules(unittest.TestCase):
    def test_every_rule_agrees_with_the_meaning(self):
        want, got = drive(MATH.read_text(encoding="utf-8"))
        self.assertGreater(len(want), 15)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        want, _ = drive(real)
        mutants = {
            "no_percent_is_a_boost": ("if (pct == 0 || seconds <= 0)", "if (seconds <= 0)"),
            "no_seconds_is_a_boost": ("if (pct == 0 || seconds <= 0)", "if (pct == 0)"),
            "the_end_is_in_seconds": ("now + static_cast<std::uint64_t>(seconds * 1000.0)", "now + static_cast<std::uint64_t>(seconds)"),
            "the_end_is_inclusive": ("return held.pct != 0 && now < held.until;", "return held.pct != 0 && now <= held.until;"),
            "a_boost_of_nothing_stands": ("return held.pct != 0 && now < held.until;", "return now < held.until;"),
            "never_over": ("return held.pct != 0 && now < held.until;", "return held.pct != 0;"),
            "the_multiplier_is_the_percent": ("return Live(held, now) ? 1.0 + held.pct / 100.0 : 1.0;", "return Live(held, now) ? held.pct / 100.0 : 1.0;"),
            "the_multiplier_outlives_the_boost": ("return Live(held, now) ? 1.0 + held.pct / 100.0 : 1.0;", "return 1.0 + held.pct / 100.0;"),
            "a_cut_is_a_boost": ("return Live(held, now) ? 1.0 + held.pct / 100.0 : 1.0;", "return Live(held, now) ? 1.0 + std::abs(held.pct) / 100.0 : 1.0;"),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply")
                text = real.replace(old, new, 1)
                if "std::abs" in new:
                    text = "#include <cmath>\n" + text
                _, got = drive(text, name)
                self.assertNotEqual(want, got, name + " survived")


def engine_failures(engine, combat):
    flat = re.sub(r"\s+", " ", engine)
    cflat = re.sub(r"\s+", " ", combat)
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    need("a boost is held per player and per key, and a second one under the key replaces the first",
         "auto& mine = held[target->GetGUID().GetRawValue()]; if (Live(given, Now())) mine[key] = given; else mine.erase(key);" in flat)
    need("the boost is given for seconds from now", "Held const given = Given(pct, Now(), seconds);" in flat)
    need("the boosts are read under the lock", "std::lock_guard<std::mutex> guard(mutex); auto found = held.find(player->GetGUID().GetRawValue());" in flat)
    need("each live boost is a multiplier of its own and an old one is dropped",
         "if (!Live(boost->second, now)) { boost = found->second.erase(boost); continue; } AddFactor(out, \"Damage boost\", boost->second.pct);" in flat)
    need("a player with none keeps no entry", "if (found->second.empty()) held.erase(found);" in flat)
    need("the boosts go with the player on logout", "PLAYERHOOK_ON_LOGOUT" in flat and "void OnPlayerLogout(Player* player) override { Clear(player); }" in flat)
    need("the hit reads the boosts, and the scripts are registered",
         "DamageBoost::Multipliers(player, hit.factors);" in cflat and "DamageBoost::RegisterScripts();" in cflat and '#include "dc_damage_boost.h"' in combat)
    return wrong


class Wiring(unittest.TestCase):
    def test_the_engine(self):
        self.assertEqual([], engine_failures(ENGINE.read_text(encoding="utf-8"), COMBAT.read_text(encoding="utf-8")))

    def test_the_source_guards_fail_their_mutants(self):
        engine, combat = ENGINE.read_text(encoding="utf-8"), COMBAT.read_text(encoding="utf-8")
        mutants = {
            "one_boost_for_everyone": ("held[target->GetGUID().GetRawValue()]", "held[0]"),
            "keys_are_not_kept": ("mine[key] = given;", "mine[0] = given;"),
            "a_zero_boost_stays": ("else\n            mine.erase(key);", ""),
            "given_at_the_wrong_time": ("Given(pct, Now(), seconds)", "Given(pct, 0, seconds)"),
            "one_factor_for_all": ('AddFactor(out, "Damage boost", boost->second.pct);', 'AddFactor(out, "Damage boost", 0);'),
            "old_boosts_stay": ("if (!Live(boost->second, now))\n            {\n                boost = found->second.erase(boost);\n                continue;\n            }", ""),
            "stays_after_logout": ("void OnPlayerLogout(Player* player) override\n            {\n                Clear(player);\n            }", "void OnPlayerLogout(Player* player) override\n            {\n            }"),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, engine.count(old), name + " does not apply")
                self.assertNotEqual([], engine_failures(engine.replace(old, new, 1), combat), name + " survived")
        for name, old in {"not_read": "        DamageBoost::Multipliers(player, hit.factors);", "not_registered": "        DamageBoost::RegisterScripts();\n"}.items():
            with self.subTest(mutant=name):
                at = combat.index(old)
                end = combat.index("\n", at + len(old) - (1 if old.endswith("\n") else 0)) + 1
                self.assertNotEqual([], engine_failures(engine, combat[:at] + combat[end:]), name + " survived")


if __name__ == "__main__":
    unittest.main()
