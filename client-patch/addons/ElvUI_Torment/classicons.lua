-- luacheck: globals hooksecurefunc unpack CLASS_ICON_TCOORDS FriendsFrame WHOS_TO_DISPLAY GUILDMEMBERS_TO_DISPLAY GetNumWhoResults GetWhoInfo GetGuildRosterInfo
-- The in-game class icon of the Witch Doctor and the Necromancer from our own textures, not a cell of the client's stock atlas.
--
-- The stock class atlas has no cell for either class (Constants.lua points them at the Shaman's and the Death Knight's), so
-- the patch gives each its own whole texture, the one the create screen draws (Interface\Glues\CharacterCreate\Torment-<Class>,
-- built by client-patch/art/Interface/Glues/CharacterCreate/source/build_icon.py). Where a frame shows a class icon, it is
-- ElvUI's skin of the /who list and the guild roster (ElvUI 6.09 Modules/Skins/Blizzard/Friends.lua): one texture a row,
-- set once to the stock atlas and then given the class's coordinates from CLASS_ICON_TCOORDS on every WhoList_Update and
-- GuildStatus_Update. The stock UI shows no class icon there, and the other places the stock UI reads CLASS_ICON_TCOORDS
-- (the raid and calendar class buttons) walk CLASS_SORT_ORDER, the stock ten.
--
-- So the coordinates of our two classes become the whole texture, and after each of those updates every row that shows one of
-- them takes our texture and every other row the atlas again. The coordinates are set here too, so ElvUI's own hook may run
-- before or after this one: ElvUI registers its hooks at login, after this file loads.
local ATLAS = "Interface\\WorldStateFrame\\Icons-Classes"
local OWN = {
    NECROMANCER = "Interface\\Glues\\CharacterCreate\\Torment-Necromancer",
    WITCHDOCTOR = "Interface\\Glues\\CharacterCreate\\Torment-WitchDoctor",
}

for token in pairs(OWN) do
    CLASS_ICON_TCOORDS[token] = {0, 1, 0, 1}
end

-- One row's icon for the class `token`: our texture whole for ours, the atlas and the class's cell for the rest.
local function show(icon, token)
    if not (token and CLASS_ICON_TCOORDS[token]) then return end
    icon:SetTexture(OWN[token] or ATLAS)
    icon:SetTexCoord(unpack(CLASS_ICON_TCOORDS[token]))
end

local function whoRows()
    local shown = math.min(GetNumWhoResults(), WHOS_TO_DISPLAY)
    for i = 1, shown do
        local button = _G["WhoFrameButton" .. i]
        if button and button.icon then
            local _, _, _, _, _, _, token = GetWhoInfo(button.whoIndex)
            show(button.icon, token)
        end
    end
end

local function guildRows()
    if not FriendsFrame.playerStatusFrame then return end
    for i = 1, GUILDMEMBERS_TO_DISPLAY do
        local button = _G["GuildFrameButton" .. i]
        if button and button.icon then
            local _, _, _, _, _, _, _, _, _, _, token = GetGuildRosterInfo(button.guildIndex)
            show(button.icon, token)
        end
    end
end

hooksecurefunc("WhoList_Update", whoRows)
hooksecurefunc("GuildStatus_Update", guildRows)
