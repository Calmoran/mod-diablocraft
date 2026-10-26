-- Account stash tuning and the hub Stash NPC (decisions 2026-09-10). World DB.
--
-- A14: one tab at launch, four more bought with gold at the designer's price. The rows
-- exist so the price has somewhere to go; price_gold stays NULL until the designer sets
-- it, and an unset price refuses the purchase rather than picking a number.
-- Tab 1 is free and therefore has no row.
--
--     UPDATE dc_stash_tuning SET price_gold = <gold> WHERE next_tab = 2;
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `dc_stash_tuning` (
    `next_tab`   TINYINT UNSIGNED NOT NULL,
    `price_gold` BIGINT UNSIGNED NULL DEFAULT NULL,
    PRIMARY KEY (`next_tab`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO `dc_stash_tuning` (`next_tab`, `price_gold`) VALUES (2, NULL), (3, NULL), (4, NULL), (5, NULL);

-- 910002 was cloned from a stock banker and still carries UNIT_NPC_FLAG_BANKER
-- (131072) on top of UNIT_NPC_FLAG_GOSSIP (1). The native bank window is off the
-- table (decision 2026-09-10 closes patch 0006), so the banker bit is removed
-- and the click reaches our gossip hook instead. scripts/generate_hub.py still
-- emits 131073 and world_0002_hub.sql is not edited; this migration runs after
-- it, the same way world_0006_hub_object_use.sql corrects the hub objects.
UPDATE `creature_template` SET `npcflag` = 1 WHERE `entry` = 910002;
