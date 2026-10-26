"""diablocraft-9rhz: the client's native "Classes:" line survives dc_tooltip.lua's clear-and-redraw.

test_tooltip_class_line.lua feeds the tooltip the client's own lines for a Wizard-only item (the Classes line
red, as the client draws it for another class) and requires it once, in that colour, under the slot line.
Each mutant below breaks one way of losing it in a copy of dc_tooltip.lua (DC_TOOLTIP_LUA names the copy) and
the run must fail; the real file must pass. Covers the Torment addon path only: ElvUI-WotLK 6.09 is third
party and not in this repo, so its own tooltip module is not exercised here.
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
MODULE = HERE.parent
ROOT = MODULE.parent
SOURCE_PATH = MODULE / "lua/aio/dc_tooltip.lua"
SOURCE = SOURCE_PATH.read_text(encoding="utf-8")
TEST = HERE / "tests/items/test_tooltip_class_line.lua"
SCRATCH = ROOT / "azerothcore-wotlk/build/_agent-scratch/class-line"
LUA = shutil.which("lua5.2") or shutil.which("lua5.1") or shutil.which("lua")

FOOTER = 'or value:find("Binds",1,true)'
CAPTURE = "if left and left~=SOCKETABLE and not footerLine(left) and not footerLine(right) then"
COLOUR = "local lr,lg,lb=nativeColour(line.colour)"
MUTATIONS = [
    ("the footer filter takes the Classes line", [(FOOTER, 'or value:find("Classes",1,true) ' + FOOTER)]),
    ("capture skips the second native line", [(CAPTURE, "if left and i~=3 and left~=SOCKETABLE and not footerLine(left) and not footerLine(right) then")]),
    ("the native colour is dropped", [(COLOUR, "local lr,lg,lb=1,1,1")]),
    ("the native lines are not redrawn", [("    for _,line in ipairs(native) do\n        if isDescription(item,line) or",
                                           "    for _,line in ipairs({}) do\n        if isDescription(item,line) or")]),
]


def run(source):
    env = dict(os.environ, DC_TOOLTIP_LUA=str(source))
    return subprocess.run([LUA, str(TEST)], cwd=ROOT, env=env, text=True, capture_output=True)


@unittest.skipUnless(LUA, "no lua interpreter")
class ClassLine(unittest.TestCase):
    def test_every_mutant_fails(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        survived = []
        with tempfile.TemporaryDirectory(prefix="mutant-", dir=SCRATCH) as folder:
            for index, (rule, pairs) in enumerate(MUTATIONS):
                text = SOURCE
                for old, new in pairs:
                    self.assertEqual(text.count(old), 1, "%s: production text not found exactly once" % rule)
                    text = text.replace(old, new)
                copy = Path(folder) / ("mutant%d.lua" % index)
                copy.write_text(text, encoding="utf-8")
                if run(copy).returncode == 0:
                    survived.append(rule)
        self.assertEqual(survived, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
