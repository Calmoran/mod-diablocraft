-- luacheck: globals AIO CreateFrame UIParent UnitName UnitIsDeadOrGhost DEAD Diablocraft DCRevive GameTooltip
-- luacheck: ignore 111 113 121 122
-- Run from the repo root: lua mod-diablocraft/scripts/tests/combat/test_revive_window.lua
--
-- The client half of dc_revive.lua (the death window) against a stub 3.3.5a API. Contract:
-- docs/contracts/revive-choices-messages.md; look: azerothcore-wotlk/build/_agent-scratch/dev-look-
-- 2026-10-05/round-1.md item 5. What it pins:
--   * the window asks the server `options` once per death (PLAYER_DEAD, and login/reload while
--     dead), and draws nothing until the O answer, so a Hardcore death (which gets X) has no buttons;
--   * the three buttons in D3's order, how they are worded, and that each sends its own verb;
--   * all three are always drawn (Revive R2, diablocraft-ka3g); each O field that is not 1 greys
--     its button (disabled, greyed label, no verb) with the field's text as its tooltip, and a
--     live button has no tooltip;
--   * a slot with an image is drawn through Diablocraft.SetArt; without the addon the flat colour
--     and the bronze edge are used;
--   * R closes the window, X keeps it up with the server's text, PLAYER_ALIVE closes it;
--   * a message on another prefix, or from another sender, is ignored;
--   * the stock DEATH dialog is never shown while this file is loaded; every other popup is.
--
-- What this does NOT cover: what the server does with the verbs (test_revive_choices.py) and how the
-- window looks (an in-game look, and ElvUI only skins the frame API, so it is a look check).

-- The window under test; DC_REVIVE_LUA points it at a mutated copy so a knocked-out rule goes red.
local SOURCE = os.getenv("DC_REVIVE_LUA") or "mod-diablocraft/lua/aio/dc_revive.lua"

-- The one shared strict 3.3.5a widget mock (diablocraft-yey2) owns CreateFrame,
-- UIParent and the rest of the client surface, and hands out only methods the
-- client has (Enable/Disable/IsEnabled, SetTextColor, the SetTexture answer and
-- the rest of what this window calls are all there; a Frame is not a Button).
local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
local frames = Mock.frames

local sent, popups, drawn, boxes = {}, {}, {}, {}
function UnitName() return "Tester" end
function GetRealmName() return "Diablocraft" end
DEAD = true
function UnitIsDeadOrGhost() return DEAD end
function SendAddonMessage(prefix, body, distribution, target)
    sent[#sent + 1] = {prefix = prefix, body = body, distribution = distribution, target = target}
end
-- The stock dialog entry point the window wraps; a call reaching here means the window let it through.
StaticPopup_Show = function(which) popups[#popups + 1] = which end
AIO = {AddAddon = function() return false end}
-- No Torment addon at load: the flat look. Section 13 adds one and repaints.
Diablocraft = nil

dofile(SOURCE)

local function frameNamed(name)
    for _, f in ipairs(frames) do if f.name == name then return f end end
end
local function buttonWithText(text)
    for _, f in ipairs(frames) do
        if f.kind == "Button" and f.label and f.label.text == text then return f end
    end
end
local function click(text)
    local b = buttonWithText(text)
    assert(b and b.scripts.OnClick, "a button labelled " .. text)
    b.scripts.OnClick(b)
end
local CORPSE, CHECKPOINT, TOWN = "REVIVE AT CORPSE", "REVIVE AT CHECKPOINT", "REVIVE IN TOWN"
local window = frameNamed("DiablocraftReviveFrame")
local watcher
for _, f in ipairs(frames) do if f.events.PLAYER_DEAD then watcher = f end end
assert(window, "the death window is created at load")
assert(watcher, "the watcher registers for the death events")
local function fire(event, ...) watcher.scripts.OnEvent(watcher, event, ...) end
local function chat(prefix, body, sender)
    fire("CHAT_MSG_ADDON", prefix, body, "WHISPER", sender or "Tester")
end
local function lastSent() return sent[#sent] end
local function hintText()
    for _, f in ipairs(frames) do
        if f.kind == "FontString" and f.parent == window and f.text ~= "" and f.text ~= "YOU HAVE DIED." then
            return f.text
        end
    end
end

-- 1. Nothing is drawn at load; the title is D3's, in caps, twice (the glow behind it).
assert(not window:IsShown(), "the window starts hidden")
assert(window.backdrop == nil, "the death window draws no box")
local titles
for _, f in ipairs(frames) do
    if f.kind == "FontString" and f.text == "YOU HAVE DIED." then titles = (titles or 0) + 1 end
end
assert(titles == 2, "the title is drawn once and the glow copy behind it, got " .. tostring(titles))

-- 2. The three buttons exist at load, with D3's wording, all live until the server says otherwise.
local corpse, checkpoint, town = buttonWithText(CORPSE), buttonWithText(CHECKPOINT), buttonWithText(TOWN)
assert(corpse and checkpoint and town, "the three buttons are built at load")
assert(not buttonWithText("REVIVE AT RIFT START"), "the old name is gone")
assert(not corpse.disabled and not checkpoint.disabled and not town.disabled, "all live before any O")

-- 3. Death asks once and draws nothing until the answer.
fire("PLAYER_DEAD")
assert(#sent == 1 and lastSent().prefix == "DCREVIVE" and lastSent().body == "options"
    and lastSent().distribution == "WHISPER" and lastSent().target == "Tester",
    "death asks the server for the options")
assert(not window:IsShown(), "and draws nothing until the server answers")

-- 4. Another prefix, and another sender, are ignored.
chat("DCARTISAN", "O|1", "Tester")
chat("DCREVIVE", "O|1", "Somebody")
assert(not window:IsShown(), "a record on another prefix or from another sender is dropped")

-- 5. O|1|1|1 shows the window with all three live; each button sends its own verb.
chat("DCREVIVE", "O|1|1|1", "Tester")
assert(window:IsShown(), "the O answer draws the window")
assert(corpse:IsShown() and checkpoint:IsShown() and town:IsShown(), "all three are drawn")
assert(not corpse.disabled and not checkpoint.disabled and not town.disabled, "and all three are live")
local function topOf(b) return b.points[#b.points][5] end
assert(topOf(corpse) > topOf(checkpoint) and topOf(checkpoint) > topOf(town),
    "D3's order is Corpse, Checkpoint, Town top to bottom")
local before = #sent
click(CORPSE)
assert(#sent == before + 1 and lastSent().body == "here", "REVIVE AT CORPSE sends `here`")
click(CHECKPOINT)
assert(lastSent().body == "checkpoint", "REVIVE AT CHECKPOINT sends `checkpoint`")
click(TOWN)
assert(lastSent().body == "town", "REVIVE IN TOWN sends `town`")
corpse.scripts.OnEnter(corpse)
assert(GameTooltip.owner ~= corpse, "a live button has no tooltip")
corpse.scripts.OnLeave(corpse)

-- 6. Each field that is not 1 greys its own button, which stays drawn in its place, says the
--    server's reason on hover and sends nothing (the contract's reasons, one per field).
local REASONS = {
    {text = CORPSE, reason = "Your body is below the world.", at = 1},
    {text = CORPSE, reason = "You can revive at your body only 3 times in a row.", at = 1},
    {text = CHECKPOINT, reason = "There is no checkpoint in town.", at = 2},
    {text = TOWN, reason = "You cannot revive in town inside a Greater Rift.", at = 3},
}
local corpseTop = topOf(corpse)
for _, case in ipairs(REASONS) do
    local fields = {"1", "1", "1"}
    fields[case.at] = case.reason
    case.record = "O|" .. table.concat(fields, "|")
    chat("DCREVIVE", case.record, "Tester")
    local reason = case.reason
    for _, b in ipairs({corpse, checkpoint, town}) do
        local greyed = b == buttonWithText(case.text)
        assert(b:IsShown() and (b.disabled == true) == greyed, case.record .. ": only its own button is greyed")
    end
    local b = buttonWithText(case.text)
    assert(b.label.textColor[1] < 0.5, case.record .. ": the greyed label")
    b.scripts.OnEnter(b)
    assert(GameTooltip.owner == b and GameTooltip.lines[1] == reason and GameTooltip:IsShown(),
        case.record .. ": the tooltip is the server's text, got " .. tostring(GameTooltip.lines and GameTooltip.lines[1]))
    b.scripts.OnLeave(b)
    assert(not GameTooltip:IsShown(), "leaving the button hides the tooltip")
    local quiet = #sent
    click(case.text)
    assert(#sent == quiet, case.record .. ": a greyed button sends nothing")
end
assert(topOf(corpse) == corpseTop and topOf(town) == corpseTop - 120, "a greyed button keeps its place")
chat("DCREVIVE", "O|1|1|1", "Tester")
assert(not corpse.disabled and not checkpoint.disabled and not town.disabled, "a fresh O brings them back")
town.scripts.OnEnter(town)
assert(GameTooltip.owner ~= town or not GameTooltip:IsShown(), "and an ungreyed button drops its reason")
town.scripts.OnLeave(town)

-- 7. The flat look without the addon: the slot's fallback colour and a bronze edge.
assert(not corpse.artM:IsShown() and not corpse.artL:IsShown() and not corpse.artR:IsShown(),
    "the flat look draws no art texture")
assert(corpse.backdropColor and corpse.backdropColor[1] > 0.2 and corpse.backdropColor[3] < 0.1,
    "the flat button is dark red")
assert(corpse.borderColor and corpse.borderColor[1] > 0.5 and corpse.borderColor[3] < 0.4,
    "with a thin bronze edge")

-- 8. A refusal after the window is up keeps the buttons and shows the server's text.
chat("DCREVIVE", "X|Try again in a moment.", "Tester")
assert(window:IsShown(), "a refusal leaves the window up")
assert(hintText() == "Try again in a moment.", "the server's refusal text is shown as is, got "
    .. tostring(hintText()))

-- 9. R closes it; PLAYER_ALIVE closes it.
chat("DCREVIVE", "R|town|town", "Tester")
assert(not window:IsShown(), "R closes the window")
chat("DCREVIVE", "O|1|1|1", "Tester")
assert(window:IsShown(), "and a fresh answer reopens it")
DEAD = false
fire("PLAYER_ALIVE")
assert(not window:IsShown(), "coming alive closes the window")

-- 10. Login or /reload while dead asks once; alive, it does not.
local count = #sent
DEAD = true
fire("PLAYER_ENTERING_WORLD")
assert(#sent == count + 1 and lastSent().body == "options", "entering the world dead asks the server")
fire("PLAYER_ENTERING_WORLD")
assert(#sent == count + 1, "and only once")
DEAD = false
fire("PLAYER_ENTERING_WORLD")
assert(#sent == count + 1, "entering the world alive asks nothing")

-- 11. A Hardcore death: the answer is a refusal, so no window and no buttons ever appear.
DEAD = true
fire("PLAYER_DEAD")
chat("DCREVIVE", "X|Hardcore deaths are final.", "Tester")
assert(not window:IsShown(), "a refusal before the window is up draws no buttons")

-- 12. The unavailable state through DCRevive.Grey: greyed, not hidden, and clicking it sends nothing.
chat("DCREVIVE", "O|1|1|1", "Tester")
assert(town:IsShown(), "the town button is up before it is greyed")
DCRevive.Grey("town", true)
assert(town:IsShown() and town.disabled, "a greyed option stays on screen and is disabled")
assert(town.label.textColor[1] < 0.5, "and its label is greyed")
local quiet = #sent
click(TOWN)
assert(#sent == quiet, "a greyed button sends nothing")
DCRevive.Grey("town", false)
assert(not town.disabled and town.label.textColor[1] > 0.9, "ungreying brings it back")

-- 13. With the addon, a slot that carries an image is drawn through SetArt and the flat edge drops.
Diablocraft = {ART = {["death-button"] = {path = "Interface\\AddOns\\Skin\\death_button"}},
    SetArt = function(texture, name, box) drawn[#drawn + 1] = name; boxes[#boxes + 1] = box end}
DCRevive.Grey("town", false)
assert(drawn[#drawn] == "death-button", "a slot with an image goes through Diablocraft.SetArt, got "
    .. tostring(drawn[#drawn]))
assert(town.artM:IsShown() and not town.artL:IsShown() and not town.artR:IsShown(),
    "a slot with no slices draws the one texture")
assert(town.backdropColor[4] == 0 and town.borderColor[4] == 0,
    "the skin's frame carries its own edge, so the flat one is dropped")

-- 14. A slot with `slices` fixes its ends and stretches the middle: three textures, the caps at the
--     crops' own widths, and the middle covering the rest (a plain stretch would smear them).
drawn, boxes = {}, {}
Diablocraft.ART["death-button"] = {path = "Interface\\AddOns\\Skin\\death_button",
    coords = {0, 0.5, 0, 0.9375}, slices = {left = 0.05, right = 0.05}}
DCRevive.Grey("town", false)
assert(#drawn == 3 and drawn[1] == "death-button" and drawn[2] == "death-button" and drawn[3] == "death-button",
    "the sliced slot draws three textures through SetArt, got " .. tostring(#drawn))
assert(boxes[1][1] == 0 and boxes[1][2] == 0.05, "the left cap is the slot's own crop")
assert(boxes[2][1] == 0.45 and boxes[2][2] == 0.5, "the right cap is the slot's own crop")
assert(boxes[3][1] == 0.05 and boxes[3][2] == 0.45, "and the middle spans what is left")
assert(town.artL:IsShown() and town.artM:IsShown() and town.artR:IsShown(), "all three pieces are drawn")
assert(math.abs(town.artL:GetWidth() - 440 * 0.05 / 0.5) < 0.01,
    "the cap keeps its own width, got " .. tostring(town.artL:GetWidth()))
Diablocraft = nil

-- 15. The stock DEATH dialog is suppressed; every other popup still reaches the stock code.
StaticPopup_Show("DEATH")
assert(#popups == 0, "the stock death dialog is never shown while the window answers for it")
StaticPopup_Show("CAMP")
assert(#popups == 1 and popups[1] == "CAMP", "every other popup is passed through")

print("Revive window checks passed")
