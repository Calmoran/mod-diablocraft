-- Torment art slots: the named slots every Torment screen draws from, and the SetArt
-- call that paints a texture from one.
--
-- The art is named slots, not paths scattered through the code. Rebuild the
-- textures with `python client-patch/build_ui_art.py` and they land in art\
-- under the file names below; nothing here changes. Set USE_ART = false to fall
-- back to the flat-colour placeholders, which is also what happens to any slot
-- whose file is missing.

Diablocraft = Diablocraft or {}
local DC = Diablocraft

-- ---------------------------------------------------------------- art slots

DC.ART_PATH = [[Interface\AddOns\Torment\art\]]
DC.USE_ART = true
DC.ART = {
    -- coords crops the transparent padding build_ui_art.py added to reach a
    -- power-of-two canvas, so the banner is never stretched to fill it.
    ["titlebar"]         = {file = "title_bar_strip",  colour = {0.20, 0.16, 0.10, 1.00},
                            coords = {0, 1, 0, 0.7421875}},
    -- The panel border is a tiling kit, not one nine-slice: four corners, four
    -- edge strips repeated along their run, one slate tile repeated in both axes
    -- behind them. Every screen that wants the Diablocraft look calls
    -- DC.PanelFrame and gets all nine, drawn at half the painted scale
    -- (PANEL_CORNER below).
    ["panel-frame-fill"]          = {file = "frame_bg_slate",           colour = {0.165, 0.165, 0.153, 0.96}},
    ["panel-frame-edge-top"]      = {file = "frame_edge_top",           colour = {0.259, 0.176, 0.107, 1.00}},
    ["panel-frame-edge-bottom"]   = {file = "frame_edge_bottom",        colour = {0.259, 0.176, 0.107, 1.00}},
    ["panel-frame-edge-left"]     = {file = "frame_edge_left",          colour = {0.259, 0.176, 0.107, 1.00}},
    ["panel-frame-edge-right"]    = {file = "frame_edge_right",         colour = {0.259, 0.176, 0.107, 1.00}},
    -- RETIRED: the four ornament corners are drawn on no
    -- panel any more. The slots stay declared so the art keeps a name and a
    -- revert is one line, but PANEL_CORNERS below decides what is drawn.
    ["panel-frame-corner-tl"]     = {file = "frame_corner_top_left",    colour = {0.236, 0.177, 0.118, 1.00}},
    ["panel-frame-corner-tr"]     = {file = "frame_corner_top_right",   colour = {0.236, 0.177, 0.118, 1.00}},
    ["panel-frame-corner-bl"]     = {file = "frame_corner_bottom_left", colour = {0.236, 0.177, 0.118, 1.00}},
    ["panel-frame-corner-br"]     = {file = "frame_corner_bottom_right", colour = {0.236, 0.177, 0.118, 1.00}},
    -- The plain corners, the canonical spelling. Two sizes ship;
    -- the 32 set is the one drawn, because the band square is 16 and 32 down to
    -- 16 is a clean 2:1 rather than the 64 set's 4:1.
    ["panel-frame-plain-tl"]      = {file = "frame_corner_plain_32_tl", colour = {0.236, 0.177, 0.118, 1.00}},
    ["panel-frame-plain-tr"]      = {file = "frame_corner_plain_32_tr", colour = {0.236, 0.177, 0.118, 1.00}},
    ["panel-frame-plain-bl"]      = {file = "frame_corner_plain_32_bl", colour = {0.236, 0.177, 0.118, 1.00}},
    ["panel-frame-plain-br"]      = {file = "frame_corner_plain_32_br", colour = {0.236, 0.177, 0.118, 1.00}},
    ["slot"]             = {file = "slot_empty",       colour = {0.13, 0.12, 0.11, 1.00}},
    ["slot-hover"]       = {file = "slot_hover",       colour = {1.00, 0.85, 0.40, 0.22}},
    ["slot-selected"]    = {file = "slot_hover",       colour = {1.00, 0.72, 0.20, 0.45},
                            tint = {1.00, 0.78, 0.25}},
    ["slot-rarity-grey"]   = {file = "rarity_grey",   colour = {0.42, 0.42, 0.42, 1.00}},
    ["slot-rarity-green"]  = {file = "rarity_green",  colour = {0.10, 0.45, 0.10, 1.00}},
    ["slot-rarity-blue"]   = {file = "rarity_blue",   colour = {0.10, 0.24, 0.55, 1.00}},
    ["slot-rarity-yellow"] = {file = "rarity_yellow", colour = {0.50, 0.44, 0.08, 1.00}},
    ["slot-rarity-orange"] = {file = "rarity_orange", colour = {0.55, 0.28, 0.04, 1.00}},
    ["tab-normal"]       = {file = "tab_normal",      colour = {0.16, 0.15, 0.13, 1.00}},
    ["tab-selected"]     = {file = "tab_selected",    colour = {0.42, 0.33, 0.14, 1.00}},
    ["tab-locked"]       = {file = "tab_locked",      colour = {0.10, 0.09, 0.09, 1.00}},
    ["button"]           = {file = "button_normal",   colour = {0.22, 0.19, 0.14, 1.00}},
    ["button-pressed"]   = {file = "button_pressed",  colour = {0.34, 0.28, 0.18, 1.00}},
    ["close"]            = {file = "close_x_button",  colour = {0.40, 0.12, 0.10, 1.00}},
    ["coin"]             = {file = "gold_coin",       colour = {0.85, 0.70, 0.25, 1.00}},

    -- The /bug button icon (BugReport.lua). Not D3 art: the later client's own
    -- Blizzard bug icon, shipped as a BLP in this addon's art folder; the
    -- 3.3.5a base client has none. Source and pin are in
    -- client-patch/art/ui/bug/manifest.json.
    ["bug-report"]       = {file = "bug_report",       colour = {0.30, 0.55, 0.95, 1.00}},

    -- The bounty map panel's zone waypoint marker (BountyMap.lua): a compass of our own, cut by
    -- client-patch/art/ui/bounties/cut_bounty_waypoint.py. Not Blizzard art, not D3 art.
    ["bounty-waypoint"]  = {file = "bounty_waypoint",  colour = {1.00, 1.00, 1.00, 1.00}},

    -- ------------------------------------------------ the death window (dc_revive.lua)
    -- No image ships for these: without a skin the window draws its own flat colours and the
    -- bronze edge (a slot with no `path` and no `file` is its `colour`), and a skin fills the
    -- slots with the D3 button frames and the glow (the D3 death window).
    ["death-button"]          = {colour = {0.30, 0.05, 0.05, 1.00}},
    ["death-button-hover"]    = {colour = {0.42, 0.09, 0.07, 1.00}},
    ["death-button-pressed"]  = {colour = {0.20, 0.03, 0.03, 1.00}},
    ["death-button-disabled"] = {colour = {0.16, 0.14, 0.13, 1.00}},
    ["death-button-glow"]     = {colour = {0.00, 0.00, 0.00, 0.00}},

    -- --------------------------------------------------------------------- window parts
    -- Every Torment window's generic parts, read by DC.Style and through it
    -- by the server windows' kit (dc_aio_ui.lua, DCUI) and this addon's own windows. Empty by
    -- default, so a client with no skin draws exactly today's windows: a part that is stock art
    -- today (the dialog backdrop, the title, the close and native buttons, inputs, scrollbars)
    -- stays stock until a skin gives it a `path` or a `colour`; a part drawn in the palette gets
    -- the palette's value as its `colour` (and `edge`) below, at PALETTE_PARTS. `slot`,
    -- `slot-hover`, `button` and `button-pressed` are the slots above (SKINNING.md, "Windows").
    ["window-panel"]       = {},
    ["window-flat"]        = {},
    ["window-title"]       = {},
    ["window-close"]       = {},
    ["window-close-hover"] = {},
    ["button-hover"]       = {},
    ["button-disabled"]    = {},
    ["tab"]                = {},
    ["tab-active"]         = {},
    ["box"]                = {},
    ["box-active"]         = {},
    ["row-select"]         = {},
    ["row-hilite"]         = {},
    ["bar-bg"]             = {},
    ["bar-fill"]           = {},
    ["input"]              = {},
    ["scroll-track"]       = {},
    ["scroll-thumb"]       = {},

    -- ------------------------------------------- whole windows
    -- One slot per Torment window, empty by default. A skin fills one with a canvas (`path`,
    -- `width`, `height` in canvas pixels, `coords`) and its `anchors`: `content` (where the
    -- window's own body goes), `title`, `close`, and `tabs` / `buttons` (one spot per tab or
    -- button, in the order the window makes them), each {left, top, width, height} in canvas
    -- pixels from the top-left, the bar slot's `wells` rule. Filled, the window hides its
    -- generic frame and draws the canvas around its body, the declared parts on their spots
    -- (DC.Style.Window). The parts inside still read the generic slots above.
    ["window-cube"]        = {},
    ["window-blacksmith"]  = {},
    ["window-jeweler"]     = {},
    ["window-mystic"]      = {},
    ["window-paragon"]     = {},
    ["window-stash"]       = {},
    ["window-inventory"]   = {},
    ["window-urshi"]       = {},
    ["window-greater-rift"] = {},
    ["window-revive"]      = {},
    ["window-bug-report"]  = {},
    ["window-bounty-map"]  = {},
    ["window-tier"]        = {},
    -- Declared and unread: no Torment window draws these yet (the account and elite code draw no
    -- window, the Mystic is window-mystic, the Dungeon Finder is the stock frame). A window that comes later reads its slot with DC.Style.Window.
    ["window-account"]     = {},
    ["window-elite"]       = {},
    ["window-crafting"]    = {},
    ["window-dungeon-finder"] = {},
    -- ------------------------------------------------- skill bar (stock art)
    -- dc_skillbar.lua's two textures, now named slots: a skin replaces the `path`
    -- and the skill bar picks the new art up through DC.SetArt.
    ["skill-slotted"]    = {path = "Interface\\Buttons\\UI-ActionButton-Border", colour = {1.00, 0.82, 0.00, 0.35}},
    ["skill-chosen"]     = {path = "Interface\\Buttons\\CheckButtonHilight",     colour = {1.00, 1.00, 1.00, 0.35}},

    -- ------------------------------------------- ElvUI_Torment (skin slots)
    -- The bottom bar and the orbs ElvUI_Torment draws (SKINNING.md). Nothing
    -- here goes through DC.SetArt: ElvUI_Torment reads these directly, because
    -- the bar and the globes are several textures and an animation, not one
    -- texture like every slot above. A skin replaces any of them; the private
    -- TormentD3 (client-patch/skins/) fills every one and is never shipped. An
    -- empty slot draws the mock HUD's part. More orb-resource keys join when
    -- their class's globe is packed (media/README.md).
    --
    -- `bar` and `orb-back` ship our own generated hotbar (not
    -- Blizzard art): the whole sheet - both orb frames, the demon, the angel and
    -- the bar - cut on a black key by client-patch/art/ui/elvui/cut_hotbar_art.py,
    -- which prints this geometry. Art units: the orbs sit on the mock's centres,
    -- everything else is the sheet's own proportions. Each well is its opening
    -- plus the icon inset (2) a side; `micro` is the micro menu's opening. The
    -- glass shine is in the bar art (the two orbs' shines differ, orb-gloss is
    -- one image), and the liquid stays the mock's fills, sized by globeWells.
    ["bar"]              = {path = [[Interface\AddOns\ElvUI_Torment\media\hud_bar]],
                            width = 1420.86, height = 224.86, coords = {0, 0.98730469, 0, 0.625},
                            wells = {
                                {left = 370.43, top = 131.51, width = 63.03, height = 67.95},
                                {left = 445.62, top = 131.51, width = 63.73, height = 67.95},
                                {left = 520.11, top = 131.51, width = 63.73, height = 67.95},
                                {left = 595.30, top = 131.51, width = 63.73, height = 67.95},
                                {left = 670.49, top = 131.51, width = 63.03, height = 67.95},
                                {left = 744.97, top = 131.51, width = 63.03, height = 67.95},
                                {left = 819.46, top = 131.51, width = 63.03, height = 67.95},
                                {left = 896.05, top = 131.51, width = 32.81, height = 67.95},
                            },
                            micro = {left = 944.43, top = 133.51, width = 108.22, height = 63.95},
                            globeWells = {
                                health = {centreX = 245.24, centreY = 113.14, diameter = 205.77},
                                power  = {centreX = 1181.24, centreY = 112.08, diameter = 208.75},
                            },
                            strip = {left = 356.97, top = 111.03, width = 714.65, height = 8.43},
                            stripTexture = [[Interface\AddOns\ElvUI_Torment\media\hud_xp_fill]],
                            fills = {blue = {0, 1, 0, 1}, orange = {0, 1, 0, 1}}},
    -- Empty: no portal sprite, so button 8 is an ordinary well and the Town
    -- Portal's own icon sits in the sheet's gold-rimmed slot.
    ["bar-buttons"]      = {},
    ["orb-health"]       = {},
    ["orb-resource-fury"]         = {},
    ["orb-resource-arcane_power"] = {},
    ["orb-resource-spirit"]       = {},
    ["orb-back"]         = {path = [[Interface\AddOns\ElvUI_Torment\media\hud_orb_back]]},
    ["orb-gloss"]        = {},
    ["orb-spark"]        = {},
    ["orb-lowhp-glow"]   = {},
    ["orb-skull"]        = {},
}

-- box overrides the slot's own coords; the panel kit passes one per clipped tile.
-- A slot with `path` uses that full path instead of ART_PATH..file, which is how a
-- skin replaces one image without touching this table (SKINNING.md).
local artTextures = setmetatable({}, {__mode = "k"})

function DC.SetArt(texture, slot, box)
    if not texture then return end
    local art = DC.ART[slot]
    if not art then
        texture:SetTexture(1, 0, 1, 1) -- an unnamed slot should be obvious
        return
    end
    artTextures[texture] = {slot = slot, box = box}
    texture:SetVertexColor(1, 1, 1)
    -- A slot with neither `path` nor `file` draws its flat `colour`: a window can name a slot
    -- for skins without shipping an image (the death window's buttons).
    if not DC.USE_ART or not (art.path or art.file) then
        local colour = art.colour or {1, 0, 1, 1}
        texture:SetTexture(colour[1], colour[2], colour[3], colour[4])
        texture:SetTexCoord(0, 1, 0, 1)
        return
    end
    -- SetTexture answers false when the client cannot load the file, and the
    -- client only indexes Interface\AddOns at startup - so art dropped in while
    -- it is running is missing until it is restarted, and /reload will not do
    -- it. Recorded rather than guessed at, because a texture that failed to
    -- load looks exactly like one that was never drawn.
    local file = art.path or (DC.ART_PATH .. art.file)
    local loaded = texture:SetTexture(file)
    texture.dcMissing = loaded == false and file or nil
    box = box or art.coords
    if box then texture:SetTexCoord(box[1], box[2], box[3], box[4]) else texture:SetTexCoord(0, 1, 0, 1) end
    if art.tint then texture:SetVertexColor(art.tint[1], art.tint[2], art.tint[3]) end
end

-- Re-apply the current slot to every texture SetArt has drawn, so a skin that
-- loaded after Torment (it needs Diablocraft.ART, so Torment is already up) is
-- what the player sees without a /reload. Torment calls this once at
-- PLAYER_LOGIN; a skin that changes a slot later calls it itself.
function DC.RefreshArt()
    for texture, record in pairs(artTextures) do
        DC.SetArt(texture, record.slot, record.box)
    end
    -- And every window part painted from a slot (DC.Style.Paint).
    for region, kinds in pairs(DC.Style and DC.Style.painted or {}) do
        for _, paint in pairs(kinds) do paint(region) end
    end
end

local refreshArt = CreateFrame("Frame")
refreshArt:RegisterEvent("PLAYER_LOGIN")
refreshArt:SetScript("OnEvent", function(self)
    self:UnregisterEvent("PLAYER_LOGIN")
    DC.RefreshArt()
end)
