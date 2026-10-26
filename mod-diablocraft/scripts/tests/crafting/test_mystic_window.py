"""diablocraft-0atm: the Mystic window's test, run again on a copy of dc_crafting.lua with one rule
taken away.

test_mystic_window.lua builds the window against a stub client and the item tooltip's real formatter,
drives the whole exchange through the bridge's own listener, and pins the look, the six steps, the
four verbs and their bounds, the item's way in (drag and right-click), the `?` preview, the
one-second choices and a refusal. A test that cannot fail proves nothing, so every rule it pins is
removed from a copy of the production window in turn; each run must fail, and the unmutated file must
pass.
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
MODULE = HERE.parent
ROOT = MODULE.parent
WINDOW = MODULE / "lua/aio/dc_crafting.lua"
UI = MODULE / "lua/aio/dc_aio_ui.lua"
TOOLTIP = MODULE / "lua/aio/dc_tooltip.lua"
TEST = HERE / "tests/crafting/test_mystic_window.lua"
SCRATCH = ROOT / "azerothcore-wotlk/build/_agent-scratch/mystic-window"
LUA = shutil.which("lua5.2") or shutil.which("lua5.1") or shutil.which("lua")

# (what the rule is for, the production text, the same text with the rule taken away)
MUTATIONS = [
    # the look is the Blacksmith's (round 3, 2026-10-05): proven by the designer on dev, no mutants for layout
    # (AGENTS.md "How work moves", interim). What follows is logic.
    # the six steps' texts
    ("step 1's title", '[1] = "Place an Item to Replace a Property",', '[1] = "Place an Item",'),
    ("step 2's title", '[2] = "Select a Property to Replace",', '[2] = "Select a Property",'),
    ("step 5's title", '[5] = "Select Replacement Property",', '[5] = "Select a Property",'),
    ("step 6's title", '[6] = "Replace a Previously Enchanted Property",', '[6] = "Replace Property",'),
    ("the intro", "setShown(ui.intro, step == 1)", "setShown(ui.intro, false)"),
    ("the locked note", "setShown(ui.lockedNote, step == 6)", "setShown(ui.lockedNote, false)"),
    ("the choose note", "setShown(ui.chooseNote, step == 5)", "setShown(ui.chooseNote, false)"),
    ("step 1's button label",
     'if step == 1 then label, enabled = "Place an Item to Replace a Property", false',
     'if step == 1 then label, enabled = "Place an Item", false'),
    ("step 2's button label",
     'elseif step == 2 then label, enabled = "Select a Property to Replace", false',
     'elseif step == 2 then label, enabled = "Replace Property", false'),
    ("Select Property is greyed until a choice is clicked",
     'elseif step == 5 then label, enabled = "Select Property", currentChoice ~= nil',
     'elseif step == 5 then label, enabled = "Select Property", true'),
    # the button's price, its grey and its reason - all the server's
    ("the button's cost line", 'label = price and ("Replace Property: " .. price) or "Replace Property"',
     'label = "Replace Property"'),
    ("the cost's unit", 'return U.number(cost.gold) .. " gold"', "return U.number(cost.gold)"),
    ("the button is live only when the server says the purse can pay",
     'if cost.enough == false then return "Not enough account gold." end', "if false then return nil end"),
    ("the button is live only when the server says every material is there",
     "        if material.enough == false then\n", "        if false then\n"),
    ("the grey button's reason is shown", 'ui.short:SetText(why or "")', 'ui.short:SetText("")'),
    ("a material with no icon is left out until a property is picked",
     "local drawn = showMaterials and material ~= nil and (known or picking)",
     "local drawn = showMaterials and material ~= nil"),
    ("the any-colour gem (entry 0) has no icon", "local known = material and material.entry ~= 0 and GetItemIcon(material.entry)",
     "local known = material and GetItemIcon(material.entry)"),
    ("the server's Close hides the window", "handlers.Close = function() frame:Hide() end", "handlers.Close = function() end"),
    ("the balance through the shared formatter",
     'ui.goldValue:SetText("Your gold: " .. U.number((model and model.gold) or goldBalance))',
     'ui.goldValue:SetText("Your gold: " .. tostring(model and model.gold or "0"))'),
    ("the materials are asked for from step 2 on", "local showMaterials = item ~= nil and step ~= 5",
     "local showMaterials = true"),
    ("the material count through the shared setter",
     "U.count(line, material.have, material.need, material.enough)",
     'line.count:SetText(tostring(material.have) .. " / " .. tostring(material.need))'),
    # the rows: the server's lines, the pick, the dead ones
    ("the picked row's mark", "    setShown(row.mark, picked)", "    setShown(row.mark, false)"),
    ("the ? only on a replaceable line", "    setShown(row.help, step ~= 5 and not dead)",
     "    setShown(row.help, true)"),
    ("a line the server marks 2 or 3 cannot be picked",
     "        if dead then return end\n        if step == 5 then currentChoice = entry.seq else currentSelection = entry.seq end",
     "        if step == 5 then currentChoice = entry.seq else currentSelection = entry.seq end"),
    ("the reason beside a line the server refuses",
     'entry.text = entry.text .. " - " .. LINE_STATE[entry.state]', "entry.text = entry.text"),
    ("the socket line's count", 'return "Sockets (" .. (entry.value or 0) .. ")"', 'return "Sockets"'),
    ("the line is worded by the tooltip's own formatter",
     "return formatter({id = entry.id, name = names[entry.id], percent = percent[entry.id],",
     "return names[entry.id] or entry.id"),
    ("a two-part range only when the server sent a second bracket",
     "min2 = (entry.min2 or 0) > 0 and entry.min2 or nil, max2 = (entry.max2 or 0) > 0 and entry.max2 or nil,",
     "min2 = entry.min2, max2 = entry.max2,"),
    ("the ? popover is the tooltip's preview form", "fixed = preview, rerolled = false})",
     "fixed = false, rerolled = false})"),
    # the records
    ("an L or C record's parts start after its guid", 'elseif f[1] == "L" then\n        for index = 3, #f do',
     'elseif f[1] == "L" then\n        for index = 2, #f do'),
    ("the item's record is read", 'elseif f[1] == "N" then', "elseif false then"),
    ("a paid roll draws its three choices", "if state.item.pending then\n        model.choices = state.choices",
     "if false then\n        model.choices = state.choices"),
    ("the locked item is the server's word", "locked = state.item.enchanted, bindWarning = state.item.bind}",
     "locked = false, bindWarning = state.item.bind}"),
    ("the bind warning is the server's word", "locked = state.item.enchanted, bindWarning = state.item.bind}",
     "locked = state.item.enchanted, bindWarning = false}"),
    ("the pushed tables name a property",
     "names, percent, tables = payload.names or {}, payload.percent or {}, true", "names, percent, tables = {}, {}, true"),
    ("a refusal shows the server's own text",
     'U.say(f[2] or "The Mystic refused that.", true)', 'if false then U.say(f[2], true) end'),
    ("a stale ? answer is dropped when the item moves",
     "        previews = {}\n        M.Render(toModel(done.state))", "        M.Render(toModel(done.state))"),
    # the wire
    ("the request's fields are tab separated", 'table.concat(fields, "\\t")', 'table.concat(fields, " ")'),
    ("the four verbs are the contract's", "local VERBS = {\n    place = {{1, 4294967295}},",
     "local VERBS = {\n    offer = {{1, 4294967295}},"),
    ("one request at a time", "    if pending then\n        queued = fields\n        return false\n    end",
     "    if false then\n        queued = fields\n        return false\n    end"),
    ("the Show payload opens the window", "handlers.Show = function(_, payload) M.Show(payload) end",
     "handlers.Show = function(_, payload) end"),
    ("the index turns a bag item into its guid", "        slotted[item.bag][item.slot] = item",
     "        slotted[item.bag][item.slot] = nil"),
    # the item's way in
    ("the drag takes an item off the cursor", '    if GetCursorInfo() ~= "item" then return end',
     "    if true then return end"),
    ("the ? asks the server once per line",
     'if not previews[item.guid .. ":" .. row.entry.seq] then M.Send("preview", item.guid, row.entry.seq) end',
     'M.Send("preview", item.guid, row.entry.seq)'),
    ("a plain right-click is claimed, a left one is not",
     'if mouseButton ~= "RightButton" or not takesRightClick() then return end',
     "if not takesRightClick() then return end"),
    ("the claim stands down in combat",
     "    if not frame:IsShown() or (InCombatLockdown and InCombatLockdown()) then return false end",
     "    if not frame:IsShown() then return false end"),
    # diablocraft-zmkh: every way in puts the item in, and a refused one never leaves the window stuck
    ("the claim stands down with an item on the cursor",
     "    if GetCursorInfo and GetCursorInfo() then return false end\n    return not",
     "    return not"),
    ("the claim is registered with the Torment sheet",
     "then Diablocraft.ClaimRightClick(takesRightClick) end", "then end"),
    ("a drop always empties the cursor",
     "    ClearCursor()\n    if not placeAt(bag, slotNumber) then U.say(NOT_TAKEN, true) end",
     "    if not placeAt(bag, slotNumber) then U.say(NOT_TAKEN, true) else ClearCursor() end"),
    ("a drop says why it took nothing",
     "    ClearCursor()\n    if not placeAt(bag, slotNumber) then U.say(NOT_TAKEN, true) end",
     "    ClearCursor()\n    placeAt(bag, slotNumber)"),
    ("a drop never reuses the last pickup's slot",
     "    cursorBag, cursorSlot = nil, nil\n", "\n"),
    ("the stock character sheet is hooked",
     'if button then sheet[button] = "stock"; found[#found + 1] = button end', "if button then end"),
    ("the Torment character sheet is hooked",
     'if button then sheet[button] = "torment"; found[#found + 1] = button end', "if button then end"),
    ("the stock sheet's click is pointed at an empty worn slot",
     "then return 255, id - 1, spare end", "then return 255, id - 1, nil end"),
    ("a full bag's click is pointed past its last slot", "    return bagId, id, slots + 1", "    return bagId, id, nil"),
    ("a right-click the window cannot take is still blanked",
     "                if not placeAt(bag, slotNumber) then U.say(NOT_TAKEN, true) end\n                if spare then",
     "                if not placeAt(bag, slotNumber) then return end\n                if spare then"),
    ("a change while the window is up marks the index stale",
     "if frame:IsShown() then indexDirty = true end", "if false then indexDirty = true end"),
    ("a stale index is asked for again",
     '            indexDirty = false\n            AIO.Handle(CHANNEL, "Refresh")', "            indexDirty = false"),
    ("the refresh answer renews only the index", "    if payload.refresh then return end\n", "\n"),
    ("the Show index lists the worn items",
     "        for slot=0,18 do add(255,slot,player:GetItemByPos(255,slot)) end\n", "\n"),
    ("the answer to Refresh is marked", "then show(player,true) end", "then show(player) end"),
    ("the stock click is blanked for that one click",
     "                    blanked[self] = self:GetID()\n                    self:SetID(spare)",
     "                    blanked[self] = self:GetID()"),
    ("the button's own id comes back after the click",
     "            button:HookScript(\"PostClick\", function(self)\n                local id = blanked[self]\n"
     "                if id then self:SetID(id); blanked[self] = nil end\n            end)", "            "),
    ("the Transmogrify tab's fixed bridge verb",
     'SendAddonMessage("DCARTISAN", "transmog", "WHISPER", UnitName("player"))',
     'SendAddonMessage("DCARTISAN", "transmogrify", "WHISPER", UnitName("player"))'),
]


def run(window, ui=UI, tooltip=TOOLTIP):
    env = dict(os.environ, DC_MYSTIC_LUA=str(window), DC_UI_LUA=str(ui), DC_TOOLTIP_LUA=str(tooltip))
    return subprocess.run([LUA, str(TEST)], cwd=ROOT, env=env, text=True, capture_output=True)


@unittest.skipUnless(LUA, "no lua interpreter")
class MysticWindow(unittest.TestCase):
    def test_the_window_never_calls_set_shown(self):
        """The 3.3.5a client has no frame:SetShown (diablocraft-t0w4); the Lua test's stub has none either, and
        this catches a call on a path the stub never draws."""
        self.assertNotIn("SetShown", re.sub(r"--[^\n]*", "", WINDOW.read_text(encoding="utf-8")))

    def test_production_passes(self):
        result = run(WINDOW)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_every_rule_is_pinned(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        source = WINDOW.read_text()
        survived, missing = [], []
        for label, before, after in MUTATIONS:
            if source.count(before) != 1:
                missing.append(f"{label} ({source.count(before)} matches)")
                continue
            with tempfile.TemporaryDirectory(dir=SCRATCH) as folder:
                copy = Path(folder) / "dc_crafting.lua"
                copy.write_text(source.replace(before, after, 1))
                if run(copy).returncode == 0:
                    survived.append(label)
        self.assertEqual(missing, [], "a mutation's production text was not found exactly once")
        self.assertEqual(survived, [], "the window test passed with the rule removed")


if __name__ == "__main__":
    unittest.main()
