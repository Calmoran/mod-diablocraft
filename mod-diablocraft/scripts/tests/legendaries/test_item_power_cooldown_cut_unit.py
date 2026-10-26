#!/usr/bin/env python3
"""diablocraft-waoo8: the item powers' cooldown cuts reach the ability code in milliseconds.

`cooldown_cut_seconds` (Messerschmidt's Reaver, Obsidian Ring of the Zodiac) is a number of seconds in data/legendary_powers.csv;
Abilities::CutRunningCooldown and Abilities::ReduceSkillCooldown take milliseconds, so the executor must multiply by a thousand. It
did not: a 1 s row took 1 ms off.

What runs: the executor's own statement, cut out of dc_item_powers_effects.cpp, compiled against a stub of Abilities that records the
milliseconds it is given, and fed each row of the sheet that carries the stat; the row's seconds must arrive as seconds * 1000.
Single-rule mutants of the statement. What is read from source: every call of the two ability functions in src/ hands over a value
in milliseconds (an allow-list of the argument of each call; a new call fails here until someone has read its unit).
Not covered: the cooldown itself being shortened in the core (Combat's tests of the ability code).
"""
import csv
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
import item_powers_source  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
SRC = MODULE / "src"
EFFECTS = (SRC / "combat/dc_item_powers_effects.cpp").read_text(encoding="utf-8")
SHEET = MODULE / "data/legendary_powers.csv"
CXX = None
for name in ("g++", "c++"):
    import shutil
    CXX = CXX or shutil.which(name)

# Every call of the two functions and the argument that carries the time, as the source writes it; all of them are milliseconds.
CALLS = {
    "src/combat/dc_item_powers_effects.cpp": ["one.value * 1000.0", "one.value * 1000.0"],
    "src/combat/dc_item_powers_events.cpp": ["left * (1.0 - factor)", "cut * 1000.0", "one.value * 1000.0"],
}
STATEMENT = re.compile(r'if \(one\.stat == "cooldown_cut_seconds"\)\n\s+(Abilities::CutRunningCooldown\(player, [^;]*\);)')


def seconds_of_the_rows():
    with SHEET.open(encoding="utf-8-sig", newline="") as stream:
        rows = [r for r in csv.DictReader(stream) if r["stat"] == "cooldown_cut_seconds"]
    assert {r["owner"] for r in rows} == {"P66_Unique_Axe_2H_011", "Unique_Ring_023_p2"}, rows
    return [float(r["value_min"]) for r in rows]


def program(statement):
    return ("#include <cstdio>\n#include <cstdlib>\n"
            "struct Player {};\n"
            "namespace Abilities { double got = -1; bool CutRunningCooldown(Player*, double milliseconds) { got = milliseconds; return true; } }\n"
            "struct Fired { double value; };\n"
            "int main(int argc, char** argv)\n{\n"
            "    Player* player = nullptr;\n"
            "    int bad = 0;\n"
            "    for (int i = 1; i < argc; ++i)\n    {\n"
            "        Fired one{std::atof(argv[i])};\n"
            "        Abilities::got = -1;\n"
            "        " + statement + "\n"
            "        double const want = one.value * 1000.0;\n"
            "        if (Abilities::got != want) { std::printf(\"FAIL: %g s reached CutRunningCooldown as %g\\n\", one.value, Abilities::got); ++bad; }\n"
            "    }\n    return bad;\n}\n")


def run(statement):
    with tempfile.TemporaryDirectory(prefix="dc-cooldown-cut-") as folder:
        cpp, binary = Path(folder) / "t.cpp", Path(folder) / "t"
        cpp.write_text(program(statement), encoding="utf-8")
        built = subprocess.run([CXX, "-std=c++17", "-o", str(binary), str(cpp)], capture_output=True, text=True)
        if built.returncode:
            return 99, built.stderr[-1500:]
        done = harness_env.run([str(binary)] + [repr(v) for v in seconds_of_the_rows()], capture_output=True, text=True)
        return done.returncode, done.stdout


class Executor(unittest.TestCase):
    def statement(self):
        found = STATEMENT.search(EFFECTS)
        self.assertIsNotNone(found, "the cooldown_cut_seconds executor moved")
        return found.group(1)

    def test_the_rows_are_one_second_each(self):
        self.assertEqual(seconds_of_the_rows(), [1.0, 1.0])

    def test_a_row_of_seconds_cuts_that_many_thousand_milliseconds(self):
        code, out = run(self.statement())
        self.assertEqual(code, 0, out)

    def test_mutants_are_caught(self):
        statement = self.statement()
        for name, new in (("seconds pass through", statement.replace(" * 1000.0", "")),
                          ("a hundred", statement.replace("1000.0", "100.0")),
                          ("divided", statement.replace("* 1000.0", "/ 1000.0"))):
            with self.subTest(name):
                self.assertNotEqual(new, statement)
                code, _ = run(new)
                self.assertNotEqual(code, 0, f"survived: {name}")


class Callers(unittest.TestCase):
    def test_every_call_of_the_two_functions_passes_milliseconds(self):
        found = {}
        for path in sorted(SRC.rglob("*.cpp")):
            text = path.read_text(encoding="utf-8")
            for call in re.finditer(r"Abilities::(?:CutRunningCooldown|ReduceSkillCooldown)\(([^;]*)\);", text):
                parts = [p.strip() for p in re.split(r",(?![^()]*\))", call.group(1))]
                found.setdefault(str(path.relative_to(MODULE)), []).append(parts[-1])
        self.assertEqual(found, CALLS)

    def test_the_functions_take_milliseconds(self):
        header = (SRC / "classes/barbarian/dc_barbarian.h").read_text(encoding="utf-8")
        self.assertIn("void ReduceSkillCooldown(Player* player, char const* skill, double milliseconds);", header)
        self.assertIn("bool CutRunningCooldown(Player* player, double milliseconds);", header)


if __name__ == "__main__":
    unittest.main()
