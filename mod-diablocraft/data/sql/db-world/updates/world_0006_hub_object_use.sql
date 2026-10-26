-- 08-world hub objects: make them clickable. Applies to the world database.
--
-- The rift obelisk (910011) and the tier selector (910010) showed no cog on
-- hover, so the client never sent CMSG_GAMEOBJ_USE and neither server hook ran.
-- The displayId was not the problem: display 7017 has a real geobox
-- (3.65 x 3.65 x 4.97) and stock objects use it, including 'Legion Obelisk'
-- (185193), a type 10 goober players click in Hellfire Peninsula.
--
-- The type was. For GAMEOBJECT_TYPE_GOOBER (10) the only per-player
-- interactability AzerothCore sends is GO_DYNFLAG_LO_ACTIVATE, and
-- GameObject::BuildValuesUpdate sets it only when ActivateToQuest() is true or
-- the viewer is a GM. ActivateToQuest() returns false for our templates twice
-- over: ObjectMgr::LoadGameObjectForQuests only marks a goober IsForQuests when
-- goober.questId > 0, and ActivateToQuest bails on !IsGameObjectForQuests()
-- before it ever reaches the questId == -1 "always usable" branch. A goober
-- with no quest is therefore only ever usable by a GM - which is why this
-- never worked anywhere.
--
-- GAMEOBJECT_TYPE_SPELLCASTER (22) is interactive by type, with no quest and no
-- dynamic flag: 'Portal to Stormwind' (176296) is type 22 with charges 0 and no
-- quest, and players click mage portals constantly. GameObject::Use calls
-- sScriptMgr->OnGossipHello before its type switch, so our hooks still run and
-- still return true, and the spellcaster branch below them is never reached -
-- spellId stays 0 for that reason.
--
-- Entries, display ids, positions and spawns are unchanged; only the template
-- type and its Data fields move. world_0002_hub.sql is not edited.
SET NAMES utf8mb4;

UPDATE `gameobject_template` SET
    `type`  = 22,   -- GAMEOBJECT_TYPE_SPELLCASTER
    `Data0` = 0,    -- spellId: none, the module answers the click first
    `Data1` = 0,    -- charges: unlimited, as the stock city portals use
    `Data2` = 0,    -- partyOnly: no
    `Data3` = 1,    -- allowMounted: never dismount for a UI click
    `Data4` = 0     -- large
WHERE `entry` IN (910010, 910011, 910012, 910013);

-- The obelisk is active now that the rift module answers it (09 F3).
UPDATE `gameobject_template` SET `name` = 'Rift Obelisk' WHERE `entry` = 910011;
