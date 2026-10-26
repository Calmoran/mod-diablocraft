"""diablocraft-jeweler-window: the stock socketing hint on rolled items with a socket, mutation-checked.

test_item_tooltip.lua pins the line (the client's ITEM_SOCKETABLE global, green, once, after Account Bound and
before the sell line, never on an item without a socket, never twice). Each rule is removed from a copy of
dc_tooltip.lua in turn (DC_TOOLTIP_LUA names the copy) and the run must fail; the real file must pass.
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
TEST = HERE / "tests/items/test_item_tooltip.lua"
SCRATCH = ROOT / "azerothcore-wotlk/build/_agent-scratch/jeweler-window"
LUA = shutil.which("lua5.2") or shutil.which("lua5.1") or shutil.which("lua")

HINT = "    if sockets and not item.preview then tooltip:AddLine(SOCKETABLE,0,1,0) end\n"
# (rule, [(production text, replacement), ...]): every pair is applied to one copy.
MUTATIONS = [
    ("the line is drawn", [(HINT, "")]),
    ("only for an item with a socket", [(HINT, "    tooltip:AddLine(SOCKETABLE,0,1,0)\n")]),
    ("green", [("tooltip:AddLine(SOCKETABLE,0,1,0)", "tooltip:AddLine(SOCKETABLE,1,1,1)")]),
    ("the client's own global", [('local SOCKETABLE=_G.ITEM_SOCKETABLE or "<Shift Right Click to Socket>"',
                                  'local SOCKETABLE="<Shift Right Click to Socket>"')]),
    ("directly under the last socket line, not after Account Bound",
     [(HINT, ""), ('    if item.bound then tooltip:AddLine("Account Bound",1,1,1) end\n',
                   '    if item.bound then tooltip:AddLine("Account Bound",1,1,1) end\n' + HINT)]),
    ("under the sockets, not above the set and the power",
     [(HINT, ""), ('    tooltip:AddLine(" ");tooltip:AddLine("Required Level "..item.level,1,1,1)\n',
                   '    tooltip:AddLine(" ");tooltip:AddLine("Required Level "..item.level,1,1,1)\n' + HINT)]),
    ("under the last socket line, not the first",
     [(HINT, ""), ('        if not sockets then tooltip:AddLine(" ");sockets=true end\n',
                   '        if not sockets then tooltip:AddLine(" ");sockets=true;tooltip:AddLine(SOCKETABLE,0,1,0) end\n')]),
    ("a native copy is not drawn twice", [("if left and left~=SOCKETABLE and not footerLine(left)", "if left and not footerLine(left)")]),
]


def run(source):
    env = dict(os.environ, DC_TOOLTIP_LUA=str(source))
    return subprocess.run([LUA, str(TEST)], cwd=ROOT, env=env, text=True, capture_output=True)


@unittest.skipUnless(LUA, "no lua interpreter")
class SocketableLine(unittest.TestCase):
    def test_every_rule_fails_when_removed(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        survived = []
        with tempfile.TemporaryDirectory(prefix="mutant-", dir=SCRATCH) as folder:
            for index, (rule, pairs) in enumerate(MUTATIONS):
                text = SOURCE
                for old, new in pairs:
                    self.assertEqual(text.count(old), 1, f"mutation anchor is not unique or not found: {rule}")
                    text = text.replace(old, new)
                mutant = Path(folder) / f"mutant{index}.lua"
                mutant.write_text(text, encoding="utf-8")
                if run(mutant).returncode == 0:
                    survived.append(rule)
        self.assertEqual(survived, [], "the tooltip test passed with the rule removed")


if __name__ == "__main__":
    unittest.main()
