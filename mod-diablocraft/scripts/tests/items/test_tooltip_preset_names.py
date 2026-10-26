"""diablocraft-ytzea: an item's rolled line whose code its slot pool does not hold reads by name, not by bare code.

test_tooltip_preset_names.lua feeds dc_tooltip.lua the committed renders (the generated pool, the preset sheet's
items_0033, the metadata's items_0034, the base item rows) and an equipped Tal Rasha's Relentless Pursuit with three
lines: its pool main stat, its own preset-only ias (jh08v) and maxmana, which only dc_affix_metadata names. Each
mutant below breaks one way of naming them in a copy of dc_tooltip.lua (DC_TOOLTIP_LUA names the copy) and the run
must fail; the real file must pass. Not mutated: the pool before the item's own row, because
generate_item_presets.py refuses a preset row its slot pool holds, so no committed code is in both.
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
TEST = HERE / "tests/items/test_tooltip_preset_names.lua"
SCRATCH = ROOT / "azerothcore-wotlk/build/_agent-scratch/preset-names"
LUA = shutil.which("lua5.2") or shutil.which("lua5.1") or shutil.which("lua")

PRESET_ROW = "presetNames[entry][rows:GetString(1)]={name=rows:GetString(2),percent=rows:GetUInt32(3)~=0"
META_ROW = "metadata[rows:GetString(0)]={name=rows:GetString(1),percent=rows:GetUInt32(2)~=0"
MUTATIONS = [
    ("describe() skips the item's own row", [("own[id] or own[group] or ", "")]),
    ("describe() skips the metadata", [("metadata[id] or metadata[group] or ", "")]),
    ("the item's own rows are not looked up by entry", [("local own=presetNames[base.entry] or {}", "local own={}")]),
    ("the preset row's name is its code", [(PRESET_ROW, PRESET_ROW.replace("name=rows:GetString(2)", "name=rows:GetString(1)"))]),
    ("the preset row's percent is dropped", [(PRESET_ROW, PRESET_ROW.replace("percent=rows:GetUInt32(3)~=0", "percent=false"))]),
    ("the metadata's percent is forced", [(META_ROW, META_ROW.replace("percent=rows:GetUInt32(2)~=0", "percent=true"))]),
    ("the metadata's kind is forced", [("kind=rows:GetString(3),order=rows:GetUInt32(4)}", 'kind="primary",order=rows:GetUInt32(4)}')]),
]


def run(source):
    env = dict(os.environ, DC_TOOLTIP_LUA=str(source))
    return subprocess.run([LUA, str(TEST)], cwd=ROOT, env=env, text=True, capture_output=True)


@unittest.skipUnless(LUA, "no lua interpreter")
class PresetNames(unittest.TestCase):
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
