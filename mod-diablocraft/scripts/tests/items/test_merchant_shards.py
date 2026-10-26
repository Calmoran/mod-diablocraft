"""diablocraft-2qp4: test_merchant_shards.lua run again on a mutated copy of Torment/Economy.lua
(or of lua/aio/dc_account.lua) with one rule taken away.

The behaviour test pins Blood Shards on screen: the Materials panel row from the ledger's own
material list, and the merchant window's foot line - only for a list priced in the shard item,
holding the account's count, following a snapshot, off on the buyback tab and on a closed
window. A test that cannot fail proves nothing, so every one of those rules is removed from a
copy of the production file in turn and the run must fail; the unmutated files must pass.
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
ECON = ROOT / "client-patch/addons/Torment/Economy.lua"
ACCOUNT = MODULE / "lua/aio/dc_account.lua"
TEST = HERE / "tests/items/test_merchant_shards.lua"
SCRATCH = ROOT / "azerothcore-wotlk/build/_agent-scratch/merchant-shards"
LUA = shutil.which("lua5.2") or shutil.which("lua5.1") or shutil.which("lua")

# (target, what the rule is for, the production text, the same text with the rule taken away)
# target "account" mutates lua/aio/dc_account.lua; anything else mutates Torment/Economy.lua.
MUTATIONS = [
    ("econ", "the Blood Shards row on the Materials panel",
     '    {entry = SHARD, name = "Blood Shard"},\n', ""),
    ("account", "the shard entry in the server-Lua material list",
     "A.MATERIALS = {102000, 102001, 102002, 102003, 102004, 102005, 102007,",
     "A.MATERIALS = {102000, 102001, 102002, 102003, 102004, 102005,"),
    ("econ", "the hook that draws the line when the window updates",
     'hooksecurefunc("MerchantFrame_Update", drawShardLine)', ""),
    ("econ", "the shard-priced check",
     "if frame.selectedTab ~= 1 or not shardPriced() then", "if frame.selectedTab ~= 1 then"),
    ("econ", "the shard's own icon as the price",
     "(icon and texture == icon)", "false"),
    ("econ", "the count coming from the account ledger",
     "local count = Econ.Material(SHARD)", "local count = Econ.Balance()"),
    ("econ", "the buyback tab shown nothing",
     "if frame.selectedTab ~= 1 or not shardPriced() then", "if not shardPriced() then"),
    ("econ", "no line before the snapshot",
     "    if not count then\n        line:Hide()\n        return\n    end\n", ""),
    ("econ", "the line beside the gold count, not under it (diablocraft-hzlnh)",
     '"RIGHT", _G["MerchantMoneyFrameGoldButton"], "LEFT", -8, 0', '"RIGHT", _G["MerchantMoneyFrameGoldButton"], "RIGHT", 0, -11'),
    ("econ", "the anchor reset on every draw",
     "    shardLine:ClearAllPoints()\n", ""),
    ("econ", "a closed window never redrawn",
     "if not frame or not frame.IsShown or not frame:IsShown() then return end",
     "if not frame then return end"),
]


def run(econ=ECON, account=ACCOUNT):
    env = dict(os.environ, DC_ECON_LUA=str(econ), DC_ACCOUNT_LUA=str(account))
    return subprocess.run([LUA, str(TEST)], cwd=ROOT, env=env, text=True, capture_output=True)


@unittest.skipUnless(LUA, "no lua interpreter")
class MerchantShards(unittest.TestCase):
    def test_the_panel_row_and_the_foot_line_fail_when_removed(self):
        econ_source = ECON.read_text(encoding="utf-8")
        account_source = ACCOUNT.read_text(encoding="utf-8")
        sources = {"econ": econ_source, "account": account_source}
        SCRATCH.mkdir(parents=True, exist_ok=True)
        survived = []
        with tempfile.TemporaryDirectory(prefix="mutant-", dir=SCRATCH) as folder:
            for index, (target, rule, old, new) in enumerate(MUTATIONS):
                source = sources[target]
                self.assertEqual(source.count(old), 1, f"mutation anchor is not unique or not found: {rule}")
                mutant = Path(folder) / f"mutant{index}.lua"
                mutant.write_text(source.replace(old, new), encoding="utf-8")
                done = run(account=mutant) if target == "account" else run(econ=mutant)
                if done.returncode == 0:
                    survived.append(rule)
        self.assertEqual(survived, [], "the test passed with the rule removed")


if __name__ == "__main__":
    unittest.main()
