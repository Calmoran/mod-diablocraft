-- luacheck: globals AIO UIParent CreateFrame
-- The one strip the Torment on-screen buttons share.
--
-- The bug button (Torment/BugReport.lua) is the strip's button: it sits in it, the whole strip
-- moves when the button is dragged, and the strip's place and scale are remembered across a
-- relog by the AIO client's LibWindow (AIO.SavePosition), the mechanism the /bug button used on
-- its own before the strip.
--
-- A button keeps what it draws, its tooltip and its OnClick; it hands its pulling around to the
-- strip. Add() is safe to call for the only button that exists (a strip of one looks and behaves
-- like the button did on its own). The strip was two buttons - the bug button and the Bounty
-- Board's - until the board retired; the strip stays for the bug
-- button and any button a later task adds.
--
-- The strip is the one frame that moves, and Strip.StartDrag/Strip.StopDrag are the single pair
-- of handlers every button is bound to (the per-button closures it used to hand
-- out could only ever drag the one strip they captured). The strip itself takes no mouse:
-- it is the button's own ground, so an enabled strip would be either a
-- duplicate of the button or, for a button that is hidden, an invisible click-blocker.
local DC = Diablocraft
DC.ButtonStrip = DC.ButtonStrip or {}
local Strip = DC.ButtonStrip

Strip.SIZE = 64
Strip.GAP = 6
Strip.buttons = {}

-- The strip's one drag path, and the ONLY one: every button in it is bound to these two, so there
-- is nothing per-button to drift, and a button added later by another addon drags exactly like the
-- first one. Handlers rather than `strip.StartMoving` passed by name, because the frame is not
-- known until the first Add.
function Strip.StartDrag()
    if Strip.strip then Strip.strip:StartMoving() end
end

function Strip.StopDrag()
    if Strip.strip then Strip.strip:StopMovingOrSizing() end
end

-- The strip frame, built on the first Add. Left of the minimap and clear of it: the stock and
-- ElvUI minimaps both keep the "Minimap" frame, so the buttons follow a moved minimap. Only the
-- first run anchors there; a remembered position wins.
function Strip.frame()
    if Strip.strip then return Strip.strip end
    local strip = CreateFrame("Frame", "TormentButtonStrip", UIParent)
    strip:SetSize(Strip.SIZE, Strip.SIZE)
    strip:SetClampedToScreen(true)
    strip:SetMovable(true)
    -- The strip takes no mouse of its own. The Bounty Board retired
    -- leaves the bug button as the only button, and it covers the strip; a
    -- mouse-enabled strip ground would add nothing and would turn any hidden button into an
    -- invisible click-blocker. Dragging is the buttons' job and StartMoving needs no mouse on the
    -- frame it moves, so the strip keeps only SetMovable and the buttons' shared handlers.

    local store = _G.AIO_FRAMEPOSITIONS
    local saved = store and store[strip:GetName()]
    if not (saved and saved.x) then
        if _G.Minimap then
            strip:SetPoint("TOPRIGHT", _G.Minimap, "TOPLEFT", -16, 0)
        else
            strip:SetPoint("TOPRIGHT", UIParent, "TOPRIGHT", -220, -40)
        end
    end
    Strip.strip = strip

    -- Registers, restores a remembered place (nothing to restore on the first run, which keeps
    -- the anchor above) and saves this one. A later login's restore sets the point itself.
    if AIO and AIO.SavePosition then AIO.SavePosition(strip) end
    return strip
end

-- Put a button in the strip, in the order Add is called.
function Strip.Add(button)
    if not button then return end
    local strip = Strip.frame()
    local slot = #Strip.buttons
    button:SetParent(strip)
    button:ClearAllPoints()
    button:SetPoint("TOPLEFT", strip, "TOPLEFT", slot * (Strip.SIZE + Strip.GAP), 0)
    -- The strip is what moves and what is remembered: dragging any button moves all of them, and
    -- a button never moves on its own (Add hands each one the strip's own two handlers).
    button:SetMovable(true)
    button:RegisterForDrag("LeftButton")
    button:SetScript("OnDragStart", Strip.StartDrag)
    button:SetScript("OnDragStop", Strip.StopDrag)
    Strip.buttons[slot + 1] = button
    strip:SetSize(#Strip.buttons * Strip.SIZE + (#Strip.buttons - 1) * Strip.GAP, Strip.SIZE)
    return button
end
