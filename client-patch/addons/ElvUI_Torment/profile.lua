-- luacheck: globals ElvUI
-- The Torment ElvUI layout, shipped verbatim as it was exported from the
-- client.
--
-- Source: /ec -> Profiles -> Export Profile; the same bytes are kept in a
-- separate export file. It is ElvUI's
-- Distributor "text" format (LibBase64 over LibCompress over the AceSerializer
-- profile, tagged "::profile::Torment"), so install.lua decodes it with ElvUI's
-- own Distributor:Decode at apply time and writes it to the profile named
-- Torment. The string's own key is "Torment" as well; install.lua always writes
-- the profile named Torment and never uses the string's key.
--
-- The matching private export is not
-- shipped as a string: install.lua writes its three settings - namefont
-- "Continuum Medium", normTex "Minimalist" and auras.lbf.enable true - key by
-- key onto the character's own private table, so it can never replace a
-- player's other private settings the way a Distributor private import would.
--
-- Split into fixed chunks for review; the chunks are joined without a
-- separator, and the Lua test decodes the joined string and compares it with the
-- export file byte for byte, so a stray character here fails the suite.
--
-- layoutVersion is the version of the shipped layout: raise it when the layout
-- changes, and every character is offered the installer again.
local E = unpack(ElvUI)
local module = E:GetModule("ElvUI_Torment")

module.layoutVersion = 5

module.layoutExport = table.concat({
    "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",
    "pe1WARvYL+mmjAI=",
}, "")
