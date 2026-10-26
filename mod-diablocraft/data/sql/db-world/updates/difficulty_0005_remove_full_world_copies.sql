-- Retire full-world tier copies; replacement uses the open-area allow-list.

-- Remove only owned copies; preserve stock and GM-created placements.

CREATE TABLE IF NOT EXISTS dc_tier_spawn (kind CHAR(1) NOT NULL, source_guid INT UNSIGNED NOT NULL, tier TINYINT UNSIGNED NOT NULL, spawn_guid INT UNSIGNED NOT NULL, PRIMARY KEY(kind,source_guid,tier), UNIQUE KEY(kind,spawn_guid)) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS dc_tier_pool (source_pool INT UNSIGNED NOT NULL, tier TINYINT UNSIGNED NOT NULL, pool_entry INT UNSIGNED NOT NULL, PRIMARY KEY(source_pool,tier), UNIQUE KEY(pool_entry)) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS dc_tier_spawn_group (source_group INT UNSIGNED NOT NULL, tier TINYINT UNSIGNED NOT NULL, group_id INT UNSIGNED NOT NULL, PRIMARY KEY(source_group,tier), UNIQUE KEY(group_id)) ENGINE=InnoDB;

START TRANSACTION;

DELETE s FROM `creature_addon` s JOIN dc_tier_spawn m ON m.kind='c' AND m.spawn_guid=s.`guid`;

DELETE s FROM `creature_movement_override` s JOIN dc_tier_spawn m ON m.kind='c' AND m.spawn_guid=s.`SpawnId`;

DELETE s FROM `creature_multispawn` s JOIN dc_tier_spawn m ON m.kind='c' AND m.spawn_guid=s.`spawnId`;

DELETE s FROM `creature_sparring` s JOIN dc_tier_spawn m ON m.kind='c' AND m.spawn_guid=s.`GUID`;

DELETE s FROM `vehicle_accessory` s JOIN dc_tier_spawn m ON m.kind='c' AND m.spawn_guid=s.`guid`;

DELETE s FROM `gameobject_addon` s JOIN dc_tier_spawn m ON m.kind='g' AND m.spawn_guid=s.`guid`;

DELETE s FROM `game_event_creature` s JOIN dc_tier_spawn m ON m.kind='c' AND m.spawn_guid=s.`guid`;

DELETE s FROM `game_event_gameobject` s JOIN dc_tier_spawn m ON m.kind='g' AND m.spawn_guid=s.`guid`;

DELETE s FROM `game_event_model_equip` s JOIN dc_tier_spawn m ON m.kind='c' AND m.spawn_guid=s.`guid`;

DELETE s FROM `game_event_npc_vendor` s JOIN dc_tier_spawn m ON m.kind='c' AND m.spawn_guid=s.`guid`;

DELETE s FROM `game_event_npcflag` s JOIN dc_tier_spawn m ON m.kind='c' AND m.spawn_guid=s.`guid`;

DELETE s FROM `pool_creature` s JOIN dc_tier_spawn m ON m.kind='c' AND m.spawn_guid=s.`guid`;

DELETE s FROM `pool_gameobject` s JOIN dc_tier_spawn m ON m.kind='g' AND m.spawn_guid=s.`guid`;

DELETE s FROM creature_formations s JOIN dc_tier_spawn m ON m.kind='c' AND m.spawn_guid=s.leaderGUID;

DELETE s FROM creature_formations s JOIN dc_tier_spawn m ON m.kind='c' AND m.spawn_guid=s.memberGUID;

DELETE s FROM spawn_group s JOIN dc_tier_spawn m ON m.spawn_guid=s.spawnId AND m.kind=IF(s.spawnType=0,'c','g');

DELETE s FROM linked_respawn s JOIN dc_tier_spawn m ON m.spawn_guid=s.guid AND m.kind=IF(s.linkType IN (0,1),'c','g');

DELETE s FROM linked_respawn s JOIN dc_tier_spawn m ON m.spawn_guid=s.linkedGuid AND m.kind=IF(s.linkType IN (0,3),'c','g');

DELETE s FROM smart_scripts s JOIN dc_tier_spawn m ON m.spawn_guid=-s.entryorguid AND m.kind=IF(s.source_type=0,'c','g') WHERE s.entryorguid<0 AND s.source_type IN (0,1);

DELETE s FROM conditions s JOIN dc_tier_spawn m ON m.spawn_guid=-s.SourceEntry AND m.kind=IF(s.SourceId=0,'c','g') WHERE s.SourceTypeOrReferenceId=22 AND s.SourceEntry<0 AND s.SourceId IN (0,1);

DELETE s FROM pool_creature s JOIN dc_tier_pool m ON m.pool_entry=s.pool_entry;

DELETE s FROM pool_gameobject s JOIN dc_tier_pool m ON m.pool_entry=s.pool_entry;

DELETE s FROM pool_pool s JOIN dc_tier_pool m ON m.pool_entry=s.pool_id;

DELETE s FROM pool_pool s JOIN dc_tier_pool m ON m.pool_entry=s.mother_pool;

DELETE s FROM pool_template s JOIN dc_tier_pool m ON m.pool_entry=s.entry;

DELETE s FROM spawn_group s JOIN dc_tier_spawn_group m ON m.group_id=s.groupId;

DELETE s FROM spawn_group_template s JOIN dc_tier_spawn_group m ON m.group_id=s.groupId;

DELETE s FROM creature s JOIN dc_tier_spawn m ON m.kind='c' AND m.spawn_guid=s.guid;

DELETE s FROM gameobject s JOIN dc_tier_spawn m ON m.kind='g' AND m.spawn_guid=s.guid;

DELETE FROM dc_tier_spawn;

DELETE FROM dc_tier_pool;

DELETE FROM dc_tier_spawn_group;

COMMIT;
