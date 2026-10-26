"""Legendary powers P0 (diablocraft-w6ged): the tooltip's active/inactive lines; the per-item power roll (diablocraft-v62ba).

test_item_power_tooltip.lua drives the real dc_tooltip.lua with a world whose power table lists one item and one set
bonus. Each mutant below breaks one rule in a copy of dc_tooltip.lua (DC_TOOLTIP_LUA names the copy) and the run
must fail; the real file must pass. It covers the Lua mirror of the server's count only: the C++ count is
test_item_power_counter.py.
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
SOURCE = (MODULE / "lua/aio/dc_tooltip.lua").read_text(encoding="utf-8")
TEST = HERE / "tests/legendaries/test_item_power_tooltip.lua"
LUA = shutil.which("lua5.2") or shutil.which("lua5.1") or shutil.which("lua")

MUTATIONS = [
    ("a power needs no row", [("active=b.built and wearing(record.item) or nil", "active=wearing(record.item) or nil")]),
    ("a power needs no wearer", [("active=b.built and wearing(record.item) or nil", "active=b.built or nil")]),
    ("a broken item still powers", [("local function wearing(item) return counts(item) and item", "local function wearing(item) return item")]),
    ("a set bonus needs no pieces", [("if worn>=pieces then on[pieces]=true end", "on[pieces]=true")]),
    ("a set bonus needs no row", [("for pieces in pairs(set.built or {}) do", "for pieces=2,6 do")]),
    ("a broken piece is counted", [("local function counts(item) return not (item and item.IsBroken and item:IsBroken()) end",
                                    "local function counts(item) return true end")]),
    ("the active line never reads active", [('if item.active then tooltip:AddLine("Legendary power is active."', 'if false then tooltip:AddLine("Legendary power is active."')]),
    # diablocraft-v62ba: the per-item power roll
    ("the power row stays an affix line", [('if target and rows:GetString(6)=="power" then', 'if false then')]),
    ("the range is not shown beside the number", [('string.format("%g%s [%g%s–%g%s]",value,suffix,min,suffix,max,suffix)', 'string.format("%g%s",value,suffix)')]),
    ("the roll overwrites the description text", [("target.rolledPower=rolledPower(", "target.power=rolledPower(")]),
    ("the power line ignores the roll", [("tooltip:AddLine(item.rolledPower or item.power,1,.5,0,true)", "tooltip:AddLine(item.power,1,.5,0,true)")]),
]


def run(source):
    env = dict(os.environ, DC_TOOLTIP_LUA=str(source))
    return subprocess.run([LUA, str(TEST)], cwd=ROOT, env=env, text=True, capture_output=True)


class ItemPowerTooltip(unittest.TestCase):
    def test_real_file_passes(self):
        done = run(MODULE / "lua/aio/dc_tooltip.lua")
        self.assertEqual(0, done.returncode, done.stderr + done.stdout)

    def test_each_mutant_fails(self):
        scratch = ROOT / "azerothcore-wotlk/build/_agent-scratch/item-power-tooltip"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            for name, edits in MUTATIONS:
                text = SOURCE
                for old, new in edits:
                    self.assertEqual(1, text.count(old), "%s: the mutation no longer applies" % name)
                    text = text.replace(old, new)
                copy = Path(folder) / "mutant.lua"
                copy.write_text(text, encoding="utf-8")
                self.assertNotEqual(0, run(copy).returncode, "mutant survived: " + name)


if __name__ == "__main__":
    unittest.main()
