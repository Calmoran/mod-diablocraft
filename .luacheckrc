-- Lua linting for mod-diablocraft/lua. Two environments share this file: the
-- server side runs inside mod-ale (Eluna), the client side inside the 3.3.5a
-- WoW client, and AIO files run in both. Globals below are the APIs those
-- environments provide, so luacheck stops reporting them as undefined.
std = "lua51"
-- Not enforced: 631 is ignored below. Kept as the intent for anything new.
max_line_length = 200
codes = true

-- Warnings that fire constantly in WoW addon code and say nothing useful.
-- luacheck's job here is catching Lua mistakes - typos, undefined globals,
-- shadowing. Dead code and unused handler arguments are review matters, not
-- lint gates: AIO and WoW hand every handler the same signature whether it
-- uses each argument or not.
ignore = {
    "211",  -- unused local/function
    "212",  -- unused argument (AIO and frame handler signatures are fixed)
    "213",  -- unused loop variable
    "542",  -- empty if branch, used as an explicit "do nothing"
    -- Long lines are left as they are (ruling 2026-09-12). The ones that trip this
    -- are data rows and client-facing strings in the AIO screens, where wrapping
    -- costs more than it buys.
    "631",
    -- Every /command in this project is SLASH_<NAME>1 = "/cmd", which is how the
    -- WoW client wants it declared. The name is meant to be a new global.
    "111/SLASH_.*",
}

read_globals = {
    -- AIO and Eluna
    "AIO", "require", "PlayerEvents", "RegisterPlayerEvent", "RegisterServerEvent",
    "RegisterCreatureEvent", "RegisterGameObjectEvent", "RegisterPlayerGossipEvent",
    "RegisterCreatureGossipEvent", "RegisterGameObjectGossipEvent",
    "WorldDBQuery", "CharDBQuery", "AuthDBQuery", "WorldDBExecute", "CharDBExecute",
    "GetPlayerByGUID", "GetPlayersInWorld", "PrintInfo", "PrintError", "SendWorldMessage",
    "CreateLuaEvent", "RemoveEventById", "GetLuaEngine", "GetCoreName", "GetCoreVersion",

    -- WoW 3.3.5a client API used by our AIO screens
    -- ChannelObserver.lua observes the stock action bar and channel paths (3.3.5a FrameXML); the
    -- client DLL's read-only key table TormentKeyDown (docs/contracts/client-key-state.md).
    "TormentKeyDown", "GetMouseFocus", "IsMouseButtonDown",
    "UnitChannelInfo", "ActionButton_GetPagedID", "VehicleMenuBar", "VEHICLE_MAX_ACTIONBUTTONS",
    "BonusActionBarFrame",
    "CreateFrame", "UIParent", "GameTooltip", "GameTooltip_ShowCompareItem",
    "ShoppingTooltip1", "ShoppingTooltip2", "ShoppingTooltip3",
    "GetItemInfo", "GetItemIcon", "GetInventoryItemLink", "GetInventoryItemTexture",
    "GetContainerItemLink", "GetContainerItemInfo", "GetContainerNumSlots",
    "GetActionInfo", "GetSpellInfo", "GetSpellLink", "IsShiftKeyDown", "IsControlKeyDown",
    "_G", "SendAddonMessage",
    "UnitName", "UnitLevel", "UnitClass", "UnitHealth", "UnitHealthMax", "UnitPower",
    "UnitPowerMax", "UnitExists", "UnitGUID", "PlaySound", "PlaySoundFile",
    -- The HUD's own reads: Fury rides the Rage bar, and the XP bar needs the
    -- stock XP pair. PlayerFrame and the three panel toggles are the stock UI
    -- the HUD replaces or drives.
    "UnitMana", "UnitManaMax", "UnitXP", "UnitXPMax", "GetItemCount",
    "PlayerFrame", "ToggleWorldMap", "ToggleFriendsFrame", "ToggleGameMenu",
    "hooksecurefunc", "issecurevariable", "securecall",
    "ShowUIPanel", "HideUIPanel", "ToggleFrame", "StaticPopup_Show",
    "SpellBookFrame", "ToggleSpellBook", "BOOKTYPE_SPELL", "SPELL_CAST_TIME_INSTANT",
    -- Talents are removed (04-classes K3): dc_skillbar.lua hides the way in.
    "TalentMicroButton", "ToggleTalentFrame", "PlayerTalentFrame",
    "GetTime", "GetLocale", "GetCVar", "SetCVar", "DEFAULT_CHAT_FRAME",
    "ChatFrame1", "SendChatMessage", "InCombatLockdown", "GetNumPartyMembers",
    "GetMoney", "GetCoinTextureString", "BreakUpLargeNumbers", "FormatLargeNumber",
    "ITEM_DELTA_DESCRIPTION", "ITEM_DELTA_DUAL_WIELD_DESCRIPTION",
    "MoneyFrame_Update", "MoneyTypeInfo", "TokenFrame", "CharacterFrame",
    "PaperDollFrame", "ToggleCharacter", "CharacterMicroButton", "CharacterFrameTab1",
    "ContainerFrame1", "NUM_BAG_SLOTS", "MAX_CONTAINER_ITEMS",
    "ClearCursor", "GetCursorInfo", "ClearOverrideBindings", "SetOverrideBindingClick",
    "GetBindingKey", "GetSpellTexture", "GetRealmName", "IsInGuild", "IsInInstance",
    "ExhaustionTick", "MainMenuExpBar", "MainMenuBarMaxLevelBar", "UIErrorsFrame",
    "UISpecialFrames", "WorldFrame", "ACCEPT", "CANCEL",
    "GuildBankFrame", "GuildBankFrame_LoadUI", "GetNumGuildBankTabs", "GetGuildBankTabInfo",
    "GetGuildBankItemInfo", "GetGuildBankItemLink", "QueryGuildBankTab",
    "CreatePacket", "RegisterPacketEvent",
    -- Used by the real addon in client-patch/addons/Torment
    "CreateFont", "GameFontNormal", "GameFontHighlight", "NumberFontNormalSmall",
    "GameFontNormalLarge", "ChatFontNormal", "UIPanelButtonTemplate", "GetItemQualityColor",
    "SetItemButtonTexture", "CloseSpecialWindows", "PlaySoundKitID", "ContainerIDToInventoryID",
    "bit", "table", "string", "math", "wipe", "strsplit", "strjoin", "strtrim",
    "format", "tinsert", "tremove", "tContains", "date", "time", "unpack",
}

-- The client owns these two tables but expects an addon to add its own field to
-- them: SlashCmdList.<NAME> is how a /command is registered and
-- StaticPopupDialogs.<NAME> is how a dialog is declared. They belong with the
-- other client globals above, but with writable fields - a plain read_global
-- reports every registration as W122 and a plain global reports it as W112.
read_globals.SlashCmdList = {read_only = false, other_fields = true}
read_globals.StaticPopupDialogs = {read_only = false, other_fields = true}

globals = {
    -- Our own cross-file globals: AIO channel names, the frames and helpers one
    -- of our files defines and another uses, and every slash command we add.
    "DCAccount", "DCGrid", "DCInventory",
    "DCSKILLS", "DCTOOLTIP", "DCRARITY", "DCCraftingResponses", "DCShowItemTooltip",
    "DCAddItemTooltips", "DCItemTooltipRecords", "Diablocraft", "DiablocraftStashFrame",
    "DiablocraftInventoryFrame", "DiablocraftOpenParagon",
    "DiablocraftHudFrame", "DIABLOCRAFTHUD", "SLASH_DIABLOCRAFTHUD1",
    "DIABLOCRAFTSTASH", "DIABLOCRAFTINVENTORY", "SLASH_DIABLOCRAFTINVENTORY1",
    "DC_ARTISAN_CONFIRM",
    "DiablocraftUI", "DIABLOCRAFTECON", "SLASH_DIABLOCRAFTECON1",
    "DIABLOCRAFTELITE", "DIABLOCRAFTMODE", "DIABLOCRAFTPARAGON", "DIABLOCRAFTRIFT",
    "DIABLOCRAFTSTASHPROBE", "DIABLOCRAFTTIER",
    "SLASH_DCSKILLS1", "SLASH_DCSTASH1", "SLASH_DCTOOLTIP1", "SLASH_DCTIER1",
    "SLASH_DCPARAGON1", "SLASH_DCMODE1", "SLASH_DCRIFT1", "SLASH_DIABLOCRAFTSTASH1",
    "SLASH_DIABLOCRAFTMODE1", "SLASH_DIABLOCRAFTTIER1",
}

-- Third-party addons we ship unmodified-in-spirit (client-patch/addons/README.md): their
-- warnings and Roth_UI's four E011 syntax errors are not ours to lint, and they failed
-- verify.sh on nightly (diablocraft-2oz3). Our own addons stay linted.
exclude_files = {
    "client-patch/addons/Roth_UI/**",
    "client-patch/addons/Bartender4/**",
}

files["mod-diablocraft/scripts/"] = { std = "lua51+luajit" }
