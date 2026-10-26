"""diablocraft-blacksmith-look: the look test, run again on a mutated copy of dc_blacksmith.lua
(or of the shared look module dc_aio_ui.lua, or of dc_jeweler.lua) with one shared visual
property taken away.

test_blacksmith_look.lua builds both windows and compares every shared property. A test that cannot fail
proves nothing, so each property it pins is removed from a copy of the production run in turn
(DC_BLACKSMITH_LUA, DC_UI_LUA and DC_JEWELER_LUA name the copies) and the run must fail; the
unmutated files must pass.
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
BLACKSMITH = MODULE / "lua/aio/dc_blacksmith.lua"
UI = MODULE / "lua/aio/dc_aio_ui.lua"
JEWELER = MODULE / "lua/aio/dc_jeweler.lua"
TEST = HERE / "tests/crafting/test_blacksmith_look.lua"
SCRATCH = ROOT / "azerothcore-wotlk/build/_agent-scratch/blacksmith-look"
LUA = shutil.which("lua5.2") or shutil.which("lua5.1") or shutil.which("lua")

# (target, what the test is for, the production text, the same text with the property taken away)
# target "ui" mutates dc_aio_ui.lua; anything else mutates dc_blacksmith.lua.
MUTATIONS = [
    ("blacksmith", "the window's open position and backdrop", 'local frame=U.window("TormentBlacksmithFrame",nil,nil,"blacksmith")',
     'local frame=CreateFrame("Frame","TormentBlacksmithFrame",UIParent);frame:SetSize(560,560);frame:SetPoint("CENTER");table.insert(UISpecialFrames,"TormentBlacksmithFrame")'),
    ("blacksmith", "the title font and position", 'local title=U.title(frame,"Blacksmith")',
     'local title=text(frame,20,-20,510,"GameFontNormal");title:SetJustifyH("CENTER");colour(title,GOLD)'),
    ("blacksmith", "the grey subtitle", "local sub=U.subtitle(frame)",
     'local sub=text(frame,20,-43,510);sub:SetJustifyH("CENTER")'),
    ("blacksmith", "the active tab's bronze border", "    for _,b in ipairs(tabs) do U.tabActive(b,b.key==tab) end\n",
     '    for _,b in ipairs(tabs) do local c=b.key==tab and GOLD or GREY;b:SetBackdropBorderColor(c[1],c[2],c[3],1) end\n'),
    ("blacksmith", "the tab position", 'b:SetPoint("TOPLEFT",frame,"TOPRIGHT",-2,-70-(i-1)*56)',
     'b:SetPoint("TOPLEFT",frame,"TOPRIGHT",-2,-72-(i-1)*56)'),
    ("blacksmith", "the list row height, font and textures", "b=U.row(list);b:SetWidth(210)",
     'b=CreateFrame("Button",nil,list);b:SetHeight(19);b:SetWidth(198);b.label=text(b,2,-3,194);b.mark=b:CreateTexture(nil,"BACKGROUND")'),
    ("blacksmith", "the category indent", 'b.label:SetPoint("LEFT",U.HEAD_INDENT,0)', 'b.label:SetPoint("LEFT",6,0)'),
    ("blacksmith", "the row indent", 'b.label:SetPoint("LEFT",U.ROW_INDENT,0)', 'b.label:SetPoint("LEFT",19,0)'),
    ("blacksmith", "the row's rarity colour", "colour(b.label,TINT[row.recipe.rarity] or GREY)",
     "colour(b.label,row.recipe.enabled and (TINT[row.recipe.rarity] or GREY) or GREY)"),
    ("blacksmith", "the search box", "local searchBox=U.input(forge)\nsearchBox:SetSize(214,20);",
     'local searchBox=CreateFrame("EditBox",nil,forge);searchBox:SetBackdrop(U.FLAT);searchBox:SetSize(214,20);'),
    ("blacksmith", "the quantity box", 'local qtyBox=U.input(forge);qtyBox:SetSize(40,20);qtyBox:SetPoint("TOPLEFT",376,-377);',
     'local qtyBox=U.input(forge);qtyBox:SetSize(42,20);qtyBox:SetPoint("TOPLEFT",365,-370);'),
    ("blacksmith", "the detail pane's size", "detail:SetSize(270,368)", "detail:SetSize(270,350)"),
    ("blacksmith", "the detail pane's colour and border",
     "flat(detail,U.DETAIL_BG[1],U.DETAIL_BG[2],U.DETAIL_BG[3],U.DETAIL_BORDER[1],U.DETAIL_BORDER[2],U.DETAIL_BORDER[3])",
     "detail:SetBackdrop(U.FLAT)"),
    ("blacksmith", "the detail name's font and position",
     'detail.icon=icon(detail,54,12,-12);detail.name=text(detail,76,-18,186,"GameFontNormalLarge")',
     'detail.icon=icon(detail,54,10,-10);detail.name=text(detail,72,-12,184,"GameFontNormal")'),
    ("blacksmith", "the material slot and label",
     "local r=U.material(detail,10+((i-1)%2)*128,-164-math.floor((i-1)/2)*40,76)",
     "local r=icon(detail,34,10+((i-1)%2)*128,-152-math.floor((i-1)/2)*40);r.label=text(detail,49+((i-1)%2)*128,-155-math.floor((i-1)/2)*40,83)"),
    ("blacksmith", "the button row's position and widths",
     'local createAll=actionButton(forge,"Create All",246,-376,90,function() B.Create(true) end)',
     'local createAll=actionButton(forge,"Create All",246,-370,85,function() B.Create(true) end)'),
    ("blacksmith", "the cast bar", "local bar=U.bar(forge)",
     'local bar=CreateFrame("StatusBar",nil,frame);bar:SetSize(514,24);bar:SetPoint("TOPLEFT",22,-520);bar.label=text(bar,4,-5,506);bar.text=bar.label'),
    ("blacksmith", "the gold line's position", 'local funds=text(frame,16,-474,512,"GameFontNormal")',
     'local funds=text(frame,22,-473,514,"GameFontNormal")'),
    ("blacksmith", "the cost line red when the gold is short",
     "        if r then colour(detail.cost,Logic.atLeast(model.gold,Logic.times(r.gold,qty)) and U.WHITE or RED) end\n", ""),
    ("blacksmith", "the second-tab body framing", "local salvageBox=U.box(salvage)",
     "local salvageBox=CreateFrame(\"Button\",nil,salvage)"),
    ("blacksmith", "the Salvage rarity border above the icon",
     'tex=button:CreateTexture(nil,"OVERLAY")', 'tex=button:CreateTexture(nil,"ARTWORK")'),
    ("blacksmith", "the Salvage border thickness",
     "local SALVAGE_BORDER=2", "local SALVAGE_BORDER=1"),
    ("blacksmith", "all four Salvage border sides",
     '{"top","bottom","left","right"}', '{"top","bottom","left"}'),
    ("blacksmith", "the Salvage border colour in the 3.3.5a stock form",
     "tex:SetTexture(tint[1],tint[2],tint[3],1)", "tex:SetColorTexture(tint[1],tint[2],tint[3],1)"),
    ("jeweler", "the Death's Breath balance grouped once",
     ',"Death\'s Breath",model.balance.deathsBreath,need', ',"Death\'s Breath",commas(model.balance.deathsBreath),need'),
    ("ui", "a flat backdrop's border colour", "    frame:SetBackdropBorderColor(br,bg,bb,1)\n", ""),
]


def run(blacksmith, ui=UI, jeweler=JEWELER):
    env = dict(os.environ, DC_BLACKSMITH_LUA=str(blacksmith), DC_UI_LUA=str(ui), DC_JEWELER_LUA=str(jeweler))
    return subprocess.run([LUA, str(TEST)], cwd=ROOT, env=env, text=True, capture_output=True)


@unittest.skipUnless(LUA, "no lua interpreter")
class BlacksmithLook(unittest.TestCase):
    def test_production_passes(self):
        done = run(BLACKSMITH)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_every_shared_property_fails_when_removed(self):
        blacksmith_source = BLACKSMITH.read_text(encoding="utf-8")
        ui_source = UI.read_text(encoding="utf-8")
        jeweler_source = JEWELER.read_text(encoding="utf-8")
        sources = {"blacksmith": blacksmith_source, "ui": ui_source, "jeweler": jeweler_source}
        SCRATCH.mkdir(parents=True, exist_ok=True)
        survived = []
        with tempfile.TemporaryDirectory(prefix="mutant-", dir=SCRATCH) as folder:
            for index, (target, rule, old, new) in enumerate(MUTATIONS):
                source = sources[target]
                self.assertEqual(source.count(old), 1, f"mutation anchor is not unique or not found: {rule}")
                mutant = Path(folder) / f"mutant{index}.lua"
                mutant.write_text(source.replace(old, new), encoding="utf-8")
                if target == "ui":
                    done = run(BLACKSMITH, ui=mutant)
                elif target == "jeweler":
                    done = run(BLACKSMITH, jeweler=mutant)
                else:
                    done = run(mutant)
                if done.returncode == 0:
                    survived.append(rule)
        self.assertEqual(survived, [], "the look test passed with the property removed")


if __name__ == "__main__":
    unittest.main()
