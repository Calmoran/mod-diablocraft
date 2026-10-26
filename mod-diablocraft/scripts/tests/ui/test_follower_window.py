"""diablocraft-gh1c1.5, the Follower window: the generated skills file is what the generator writes, and the client Lua test
fails when any rule of dc_follower.lua it pins is removed.

test_follower_window.lua drives the real file against a stub client. A test that cannot fail proves nothing, so each rule is removed from a
copy of the source in turn (DC_FOLLOWER_LUA names the copy) and the run must fail; the unmutated file must pass.
"""
import csv
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
MODULE = HERE.parent
ROOT = MODULE.parent
sys.path.insert(0, str(HERE))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
FOLLOWER = MODULE / "lua/aio/dc_follower.lua"
SKILLS = MODULE / "lua/aio/dc_follower_skills.lua"
TEST = HERE / "tests/ui/test_follower_window.lua"
SCRATCH = harness_env.private_scratch(ROOT / "azerothcore-wotlk/build/_agent-scratch/follower-window")
SOURCE = FOLLOWER.read_text(encoding="utf-8")
LUA = shutil.which("lua5.2") or shutil.which("lua5.1") or shutil.which("lua")

spec = importlib.util.spec_from_file_location("generate_follower_window", HERE / "generate/campaign/generate_follower_window.py")
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)

# (what the test is for, the production text, the same text with the rule removed)
MUTATIONS = [
    ("a stray decimal is cut", 'local digits=tostring(text or "0"):match("^%-?%d+") or "0"', 'local digits=tostring(text or "0")'),
    ("seconds are whole", 'line=line:gsub("(%d+)%.0+ (seconds?)","%1 %2")', "line=line"),
    ("the backpack's index", "if bag==0 then return 25500+22+slot end", "if bag==0 then return 25500+slot end"),
    ("a bag's index", "return (18+bag)*100+(slot-1)", "return (18+bag)*100+slot"),
    ("a tier opens at its level", "return (level or 0)<(tier.level or 0) end", "return (level or 0)<=(tier.level or 0) end"),
    ("a locked tier wins", 'if Logic.locked(tier,level) then return "Unlocks at level "..tier.level,"Locked","locked" end\n', ""),
    ("a relic that gives every skill names both", 'if tier.all then return "Level "..tier.level.." Skills",skills[1].name.." and "..skills[2].name,"all" end\n', ""),
    ("equip carries the slot", "equip={whole,whole,token}", "equip={whole,whole}"),
    ("a slot key is a token", 'value:match("^[%w_]+$")~=nil', "true"),
    ("one click is one request", "    if awaiting and GetTime()-awaiting<=3 then return false end\n", ""),
    ("the window waits for E", 'attrs={"0","0","0","0","0","0"},details={},gear={},tiers={}}', 'attrs={"0","0","0","0","0","0"},details={},gear={},tiers={}};frame:Show()'),
    ("a refusal is said", 'say(f[2] or "That did not work.",true);awaiting=nil', "awaiting=nil"),
    ("a refusal frees the next request", 'say(f[2] or "That did not work.",true);awaiting=nil', 'say(f[2] or "That did not work.",true)'),
    ("the tooltip records are asked once per worn set", 'if key=="" or key==askedTooltips then return end', 'if key=="" then return end'),
    ("a slot the follower cannot use is grey", "b.icon:SetDesaturated(not cell.usable)", "b.icon:SetDesaturated(false)"),
    ("a slot the follower cannot use is dim", "b:SetAlpha(cell.usable and 1 or .45)", "b:SetAlpha(1)"),
    ("an empty slot shows the stock art", 'b.icon:SetTexture("Interface\\\\PaperDoll\\\\"..def.art)', "b.icon:SetTexture(nil)"),
    ("Dismiss sends nothing for a follower that is not hired", "    if not model or not model.hired then return end\n    send(\"dismiss\",model.follower)", "    if not model then return end\n    send(\"dismiss\",model.follower)\n    if false then return end"),
    ("only the hired follower has a Dismiss button", "if model.hired then dismissButton:Show() else dismissButton:Hide() end", "dismissButton:Show()"),
    ("Dismiss sends dismiss", 'send("dismiss",model.follower)', 'send("open",model.follower)'),
    ("the window sends no hire", "unequip={whole,token},dismiss={whole}", "unequip={whole,token},hire={whole},dismiss={whole}"),
    ("only a right-click takes an item off", 'elseif button=="RightButton" and cell.entry~=0 then', "elseif cell.entry~=0 then"),
    ("a locked tier picks nothing", "if not model or not self.skill or self.locked then return end", "if not model or not self.skill then return end"),
    ("closing the window shuts Details", 'frame:SetScript("OnHide",function() details:Hide();', 'frame:SetScript("OnHide",function()'),
    ("the Details groups in order", 'local DETAIL_ORDER={"offense","defense","life","adventure"}', 'local DETAIL_ORDER={"adventure","life","defense","offense"}'),
    ("the cursor's bag is watched", "function(bag,slot) cursorBag,cursorSlot=bag,slot end", "function(bag,slot) end"),
    ("the cursor is cleared on equip", '        ClearCursor()\n        send("equip"', '        send("equip"'),
    ("Damage is a whole grouped number", "damageValue:SetText(Logic.whole(model.attrs[5]))", "damageValue:SetText(model.attrs[5])"),
    ("the unpicked icon is grey", 'b.icon:SetDesaturated(state=="locked" or (state=="picked" and not lit))', 'b.icon:SetDesaturated(state=="locked")'),
    ("the picked icon is outlined", "b:SetBackdropBorderColor(lit and GOLD[1] or U.SLOT_BORDER[1],", "b:SetBackdropBorderColor(U.SLOT_BORDER[1],"),
    ("a follower's portrait", "portrait.icon:SetTexture(info and info.portrait or U.QUESTION)", "portrait.icon:SetTexture(U.QUESTION)"),
    ("the status colour", 'colour(statusText,state=="following" and GREEN or GREY)', "colour(statusText,GREEN)"),
    ("a worn item's rolled lines", "if DCShowItemTooltip and cell.guid~=0 then DCShowItemTooltip(GameTooltip,cell.guid) end", ""),
    ("the server answer reaches the tooltip addon", "if payload and DCAddItemTooltips then DCAddItemTooltips(payload.records) end", ""),
    ("the server asks for a real follower", 'if type(follower)~="number" or follower~=math.floor(follower) or follower<1 or follower>3 then return end\n', ""),
    ("a skill id is letters, digits and hyphens", 'value:match("^[%a%d%-]+$")~=nil', "true"),
    ("a pick is matched by its skill id", "if skill.id==tier.pick then return", "if true then return"),
    ("an icon sends its own skill id", 'send("skill",model.follower,tier,self.skill.id)', 'send("skill",model.follower,tier,"heal")'),
    ("the lit icon is the pick's", "entry.pick==skills[choice].id", "entry.pick==skills[1].id"),
    ("the server is throttled", 'if not DCThrottle.Allow(player,"follower:tooltips",5,10) then return end\n', ""),
    ("the server reads the player's own gear", "WHERE g.guid=%d AND g.follower=%d", "WHERE g.follower=%d AND g.guid=%d"),
]


def run(source_path):
    env = dict(os.environ, DC_FOLLOWER_LUA=str(source_path))
    return subprocess.run([LUA, str(TEST)], cwd=ROOT, env=env, text=True, capture_output=True)


class Generated(unittest.TestCase):
    def test_the_skills_file_is_what_the_generator_writes(self):
        self.assertEqual(SKILLS.read_text(encoding="utf-8"), generator.render(), "run generate_follower_window.py")

    def test_every_skill_of_the_sheet_is_in_the_file_with_its_text(self):
        text = SKILLS.read_text(encoding="utf-8")
        with open(MODULE / "data/d3/followers.csv", newline="", encoding="utf-8") as handle:
            rows = [r for r in csv.DictReader(handle) if r["kind"] == "skill"]
        self.assertEqual(len(rows), 24)
        for row in rows:
            self.assertIn(f'id="{row["skill_id"]}"', text)
            self.assertIn(row["name"].replace('"', '\\"'), text)

    def test_the_generator_refuses_a_skill_with_no_icon(self):
        icons = dict(generator.ICONS)
        try:
            del generator.ICONS["heal"]
            with self.assertRaises(generator.WindowDataError):
                generator.render()
        finally:
            generator.ICONS.clear()
            generator.ICONS.update(icons)


@unittest.skipUnless(LUA, "no lua interpreter")
class Window(unittest.TestCase):
    def test_production_passes(self):
        done = run(FOLLOWER)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_every_rule_the_test_pins_fails_when_removed(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        survived = []
        with tempfile.TemporaryDirectory(prefix="mutant-", dir=SCRATCH) as folder:
            for index, (rule, old, new) in enumerate(MUTATIONS):
                self.assertEqual(SOURCE.count(old), 1, f"mutation anchor is not unique or not found: {rule}")
                mutant = Path(folder) / f"mutant{index}.lua"
                mutant.write_text(SOURCE.replace(old, new), encoding="utf-8")
                if run(mutant).returncode == 0:
                    survived.append(rule)
        self.assertEqual(survived, [], "the test passed with the rule removed")


if __name__ == "__main__":
    unittest.main()
