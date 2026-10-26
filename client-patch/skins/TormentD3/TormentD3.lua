-- luacheck: globals Diablocraft
-- TormentD3 - the designer's own Diablo III skin for the Torment UI (diablocraft-lido
-- part D).
--
-- It holds the D3 art the mock HUD replaces - the bottom bar, the button sheet,
-- the globes, the skull and the orb cosmetics - and fills the bar and orb slots
-- in Diablocraft.ART with it, so with the skin installed the game looks exactly
-- as it did before the mock. It is the proof that the slot system works: the
-- shipped addons draw the mock HUD, and this folder, installed by hand, brings
-- D3's own look back.
--
-- Never shipped. It is not in manifest.py's OWN_ADDONS or APPROVED_ADDONS, it
-- sits outside the addons the release zips, and the designer copies it into
-- Interface/AddOns himself.
--
-- Load order: Torment declares the slots (## Dependencies: Torment), so its
-- Diablocraft.ART exists here. ElvUI_Torment reads them at its Initialize,
-- which runs after every addon has loaded, so setting them now is early enough
-- and never later than the first frame is drawn.
local ART = Diablocraft and Diablocraft.ART
if not ART then return end

local MEDIA = "Interface\\AddOns\\TormentD3\\media\\"

-- The bottom bar: the padded D3 art at native size (the crop trims the power-of-
-- two padding build_ui_art.py added, so nothing is stretched), with the wells,
-- the globe wells, the XP strip and its fill sprites measured from the same art.
ART["bar"] = {
    path = MEDIA .. "BottomBar_GameRes",
    width = 1416, height = 201,
    coords = {0, 0.69140625, 0, 0.78515625},
    wells = {
        {left = 343, top = 110, width = 69, height = 67},
        {left = 417, top = 110, width = 69, height = 67},
        {left = 491, top = 110, width = 69, height = 67},
        {left = 565, top = 110, width = 69, height = 67},
        {left = 643, top = 110, width = 67, height = 67},
        {left = 716, top = 110, width = 67, height = 67},
        {left = 789, top = 110, width = 69, height = 67},
        {left = 865, top = 110, width = 42, height = 67},
    },
    globeWells = {
        health = {centreX = 243, centreY = 100, diameter = 174},
        power  = {centreX = 1179, centreY = 100, diameter = 178},
    },
    strip = {left = 329, top = 94, width = 767, height = 11},
    -- The XP fill's status bar texture: the atlas below holds the blue/orange
    -- sprites the `fills` crop, exactly as the shipped addon drew them.
    stripTexture = MEDIA .. "2DUIBottomBar",
    fills = {
        blue = {0.37646484375, 0.73974609375, 0.03125, 0.06640625},
        orange = {0.00439453125, 0.36767578125, 0.13671875, 0.171875},
    },
}

-- The button sheet: button 8 (the portal) is three sprites of it, keyed by
-- blend mode in buttonart.lua. SetTexCoord over the 2048x256 atlas.
ART["bar-buttons"] = {
    path = MEDIA .. "2DUIBottomBar",
    portal = {
        normal = {0.763183594, 0.78125, 0.234375, 0.484375},
        highlight = {0.7890625, 0.80712890625, 0.234375, 0.484375},
        disabled = {0.73681640625, 0.75439453125, 0.23828125, 0.48046875},
    },
}

-- The globes and the fills. The frame count and cell size are read off the
-- packed sheets (build_d3_globes.py), never guessed. `glow` is the health
-- sheet's own flat light, the second ADD pass the orb draws (diablocraft-cx3j).
ART["orb-health"] = {path = MEDIA .. "d3_healthglobe", frames = 60, width = 1024, height = 1024,
                     cellW = 96, cellH = 98, cols = 10, glow = true}
ART["orb-resource-fury"] = {path = MEDIA .. "d3_barbarianresourceglobe", frames = 60,
                            width = 1024, height = 256, cellW = 48, cellH = 49, cols = 20}
ART["orb-resource-arcane_power"] = {path = MEDIA .. "d3_wizardresourceglobe", frames = 60,
                                    width = 1024, height = 256, cellW = 48, cellH = 49, cols = 20}

-- The orb cosmetics: the ring and the gargoyles come from the bar art itself,
-- these are the plates, the glass gloss, the swirl spark, the low-health glow
-- and the death skull.
ART["orb-back"] = {path = MEDIA .. "orb_back2"}
ART["orb-gloss"] = {path = MEDIA .. "orb_gloss"}
ART["orb-spark"] = {path = MEDIA .. "orb_spark"}
ART["orb-lowhp-glow"] = {path = MEDIA .. "orb_lowhp_glow"}
ART["orb-skull"] = {path = MEDIA .. "d2_skull"}
-- The death window's buttons (dc_revive.lua) are deliberately NOT filled here:
-- they are the shipped plain dark-red buttons with their thin bronze edge (the designer,
-- 2026-10-05: "you don't need to worry about blizzard artwork at all right now,
-- leave it as normal interfaces"). A skin may fill the death-* slots later; see
-- SKINNING.md.

