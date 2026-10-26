-- luacheck: globals ElvUI AceGUIWidgetLSMlists
-- ElvUI_Torment options. Listed last in the TOC.
--
-- Registers with LibElvUIPlugin-1.0 exactly as ElvUI_LocPlus does, so
-- ElvUI_Torment appears in ElvUI's Plugins list with its TOC version. The sliders
-- live in the ElvUI profile (P.torment defaults below), so they export with the
-- Torment profile; each writes E.db.torment and calls
-- ElvUI_Torment:Apply(), which re-sizes the art and re-runs the button
-- anchoring. Bar1's ElvUI size/spacing no longer mean anything for these
-- buttons.
local E = unpack(ElvUI)
local addonName = ...

-- ProfileDB defaults (ElvUI[4]); AceDB is built from these, so the keys land in
-- the active profile and survive /reload and profile export.
-- iconInset 2 is an interim tunable, not a sourced D3 measurement; the frame
-- sprite it would inset from is still missing.
ElvUI[4].torment = {
    bar1Scale = 1,
    bar1OffsetX = 0,
    bar1OffsetY = 0,
    iconInset = 2,
    xpBar = true,
    orbScale = 1,
    orbNudgeX = 0,
    orbNudgeY = 0,
    orbText = true,
    -- The orb fill animation's one speed, in frames a second: it starts at 20
    -- (a 3s loop over the 60 frames) and is tuned in game.
    orbFps = 20,
    -- The Torment layout shows the castbar without the player health frame:
    -- castbar.lua hides every other part of ElvUF_Player and makes the frame
    -- click-through. On by default; the toggle brings the full frame back.
    castbarOnly = true,
    -- The rift tracker's own size (dc_riftbar.lua): D3 draws its Objectives entry
    -- 25% bigger than the list's text.
    objectiveScale = 1.25,
    -- The damage numbers (damagetext.lua). Each size slider runs 25 to 75. A hit
    -- is 40, a little over the 35 found still small in game. D3 draws a crit
    -- larger and a tick smaller but no ratio for either is on record, so the crit
    -- takes the stock client's own step (WorldText.cpp: 0.0275 of the screen's
    -- height for a crit over 0.01833 for a hit, 1.5 times), 60, and the tick the
    -- same step down, 27. All three, and the rise time (the stock text's own
    -- 1.5 s), are tuned in game. A number climbs about 300 px on a fountain arc,
    -- leaving straight up and bending out to its own angle inside a 30-degree fan
    -- centred straight up, like a firework (the angle is random per number, half
    -- the fan either side).
    damageFont = "Torment Exocet",
    damageSize = 40,
    damageCritSize = 60,
    damageDotSize = 27,
    damageRiseTime = 1.5,
    damageRise = 300,
    damageFan = 30,
    damageShort = false,
    -- The skills window's element palette (dc_skillbar.lua ELEMENT).
    damageColors = {
        physical = {r = 0.95, g = 0.95, b = 0.95},
        fire = {r = 1, g = 0.35, b = 0.1},
        cold = {r = 0.35, g = 0.8, b = 1},
        lightning = {r = 1, g = 0.9, b = 0.2},
        poison = {r = 0.4, g = 0.9, b = 0.2},
        arcane = {r = 0.75, g = 0.4, b = 1},
        holy = {r = 1, g = 0.75, b = 0.4},
    },
}

local function config()
    if not E.db.torment then
        E.db.torment = {bar1Scale = 1, bar1OffsetX = 0, bar1OffsetY = 0, iconInset = 2, xpBar = true,
                        orbScale = 1, orbNudgeX = 0, orbNudgeY = 0, orbText = true, orbFps = 20, castbarOnly = true,
                        objectiveScale = 1.25}
    end
    return E.db.torment
end

local function changed(key, value)
    config()[key] = value
    local module = E:GetModule("ElvUI_Torment")
    if module and module.Apply then module:Apply() end
end

-- The damage numbers' settings are read at each new hit (damagetext.lua), so
-- they write the profile and re-apply nothing.
local function stored(key, value)
    config()[key] = value
end

local function current(key)
    local value = config()[key]
    if value == nil then return ElvUI[4].torment[key] end
    return value
end

local ELEMENT_NAMES = {
    physical = "Physical", fire = "Fire", cold = "Cold", lightning = "Lightning",
    poison = "Poison", arcane = "Arcane", holy = "Holy",
}

local function colourOf(element)
    local picked = config().damageColors and config().damageColors[element]
    if picked and picked.r then return picked end
    return ElvUI[4].torment.damageColors[element]
end

local function setColour(element, r, g, b)
    local db = config()
    db.damageColors = db.damageColors or {}
    db.damageColors[element] = {r = r, g = g, b = b}
end

-- The three size sliders' range: wide, still readable.
local SIZE_MIN, SIZE_MAX = 25, 75

local function damageSlider(order, key, name, min, max, step, desc)
    return {
        order = order, type = "range", name = name, desc = desc, min = min, max = max, step = step,
        get = function() return current(key) end,
        set = function(_, value) stored(key, value) end,
    }
end

local function damageArgs()
    local args = {
        note = {
            order = 0,
            type = "description",
            name = "Drawn with the Torment client extension; without it the game's own numbers show. Each change shows on the next hit. The sizes and the rise time are interim and tuned in game.",
        },
        damageFont = {
            order = 1,
            type = "select",
            dialogControl = "LSM30_Font",
            name = "Font",
            desc = "ElvUI's CombatText Font (General, Media) sets this too: the numbers take whichever was picked last, from the next frame on, numbers in flight included.",
            values = AceGUIWidgetLSMlists.font,
            get = function() return current("damageFont") end,
            set = function(_, value) stored("damageFont", value) end,
        },
        damageSize = damageSlider(2, "damageSize", "Size", SIZE_MIN, SIZE_MAX, 1),
        damageCritSize = damageSlider(3, "damageCritSize", "Critical hit size", SIZE_MIN, SIZE_MAX, 1),
        damageDotSize = damageSlider(4, "damageDotSize", "Damage over time size", SIZE_MIN, SIZE_MAX, 1),
        damageRise = damageSlider(5, "damageRise", "Rise (px)", 50, 600, 10,
            "How far a number travels before it is gone."),
        damageRiseTime = damageSlider(6, "damageRiseTime", "Rise time (seconds)", 0.3, 4, 0.05,
            "How long a number takes to travel its rise; it fades over the last fifth."),
        damageFan = damageSlider(7, "damageFan", "Fan (degrees)", 0, 90, 1,
            "Each number leaves straight up and curves out to a random angle inside this fan, centred straight up; 0 sends every number straight up."),
        damageShort = {
            order = 8,
            type = "toggle",
            name = "Short numbers (1.23b)",
            desc = "Shows a damage number as 1.23b, 45.6m or 789k instead of 1,231,204,495. Only the damage numbers: tooltips, the sheet and ElvUI stay in full.",
            get = function() return current("damageShort") == true end,
            set = function(_, value) stored("damageShort", value and true or false) end,
        },
        resetColours = {
            order = 20,
            type = "execute",
            name = "Reset to default colours",
            func = function()
                for element, colour in pairs(ElvUI[4].torment.damageColors) do
                    setColour(element, colour.r, colour.g, colour.b)
                end
            end,
        },
    }
    local DamageText = E:GetModule("ElvUI_Torment").DamageText
    for index, element in ipairs(DamageText.ELEMENTS) do
        args["colour_" .. element] = {
            order = 10 + index,
            type = "color",
            hasAlpha = false,
            name = ELEMENT_NAMES[element],
            get = function()
                local colour = colourOf(element)
                return colour.r, colour.g, colour.b
            end,
            set = function(_, r, g, b) setColour(element, r, g, b) end,
        }
    end
    return args
end

local function slider(order, key, name, min, max, step, desc)
    return {
        order = order,
        type = "range",
        name = name,
        desc = desc,
        min = min,
        max = max,
        step = step,
        -- A profile that has never carried the key (an export older than the setting)
        -- shows the ProfileDB default rather than an empty slider.
        get = function()
            local value = config()[key]
            if value == nil then return ElvUI[4].torment[key] end
            return value
        end,
        set = function(_, value) changed(key, value) end,
    }
end

E.Libs.EP:RegisterPlugin(addonName, function()
    E.Options.args.torment = {
        order = 20,
        type = "group",
        name = "Torment",
        args = {
            bar1Scale = slider(1, "bar1Scale", "Bar1 art scale", 0.5, 1.5, 0.01),
            bar1OffsetX = slider(2, "bar1OffsetX", "Bar1 offset X", -400, 400, 1),
            bar1OffsetY = slider(3, "bar1OffsetY", "Bar1 offset Y", -400, 400, 1),
            iconInset = slider(4, "iconInset", "Icon inset (native px)", 0, 20, 1),
            xpBar = {
                order = 5,
                type = "toggle",
                name = "XP bar",
                get = function() return config().xpBar ~= false end,
                set = function(_, value) changed("xpBar", value and true or false) end,
            },
            orbScale = slider(6, "orbScale", "Orb size factor", 0.5, 1.5, 0.01),
            orbNudgeX = slider(7, "orbNudgeX", "Orb nudge X", -100, 100, 1),
            orbNudgeY = slider(8, "orbNudgeY", "Orb nudge Y", -100, 100, 1),
            orbText = {
                order = 9,
                type = "toggle",
                name = "Orb values (both orbs)",
                get = function() return config().orbText ~= false end,
                set = function(_, value) changed("orbText", value and true or false) end,
            },
            orbFps = slider(10, "orbFps", "Orb animation (frames a second)", 5, 60, 1),
            -- The castbar-only player frame.
            -- Its setter re-runs the same apply as the sliders, and the pass
            -- itself refuses to run in combat (castbar.lua).
            castbarOnly = {
                order = 11,
                type = "toggle",
                name = "Castbar only (no player frame)",
                desc = "Hides every part of ElvUI's player frame except the castbar - health, power, portrait, texts, backdrop, info panel and auras - and makes the hidden frame click-through. The Torment orbs show health and resource. Turn it off to get ElvUI's full player frame back.",
                get = function() return config().castbarOnly ~= false end,
                set = function(_, value) changed("castbarOnly", value and true or false) end,
            },
            -- The Torment installer: the same window the first
            -- login with this addon shows, and /torment install.
            applyLayout = {
                order = 12,
                type = "execute",
                name = "Apply the Torment layout",
                desc = "Opens the Torment installer, which applies the designer's Torment layout as an ElvUI profile named Torment and makes it your active profile. Other profiles are left alone.",
                func = function()
                    local torment = E:GetModule("ElvUI_Torment")
                    torment.installer:Queue()
                end,
            },
            -- The rift tracker's Objective Frame scale: the entry in the objective
            -- list draws at this factor, 1.25 by default. Only the entry is scaled -
            -- the list itself keeps
            -- ElvUI's mover and its Nudge.
            objectiveScale = slider(12, "objectiveScale", "Objective Frame scale", 0.5, 1.5, 0.01,
                "How big the rift tracker's entry in the objective list draws. The list itself still moves with ElvUI's mover and its Nudge."),
            damageText = {
                order = 13,
                type = "group",
                inline = true,
                name = "Damage numbers",
                args = damageArgs(),
            },
        },
    }
end)
