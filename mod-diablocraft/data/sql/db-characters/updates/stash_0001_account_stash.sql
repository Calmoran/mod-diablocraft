-- Account stash storage (11-hardcore §4, decisions 2026-09-10). Characters DB.
--
-- A3: the key is (account_id, mode). There is no character column and no
-- foreign key to one, so nothing in the core's character-deletion or guild
-- paths can reach these rows.
-- A5: deleting the last normal or hardcore character, disbanding a guild or
-- restarting the server leaves both containers intact. Only an explicit
-- account deletion removes them.
--
-- dc_account_stash_item holds links, not items. The item itself stays in
-- item_instance with owner and container cleared, exactly as the guild bank
-- parks its own (Guild.cpp:473), so the item guid never changes and every
-- dc_item_instance, dc_item_affix and gem row that hangs off that guid is
-- untouched by a deposit or a withdrawal.
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `dc_account_stash` (
    `account_id`   INT UNSIGNED NOT NULL,
    `mode`         ENUM('normal','hardcore') NOT NULL,
    `tabs_granted` TINYINT UNSIGNED NOT NULL DEFAULT 1,
    `revision`     BIGINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (`account_id`, `mode`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `dc_account_stash_tab` (
    `account_id` INT UNSIGNED NOT NULL,
    `mode`       ENUM('normal','hardcore') NOT NULL,
    `tab_id`     TINYINT UNSIGNED NOT NULL,
    `name`       VARCHAR(32) NOT NULL DEFAULT '',
    `icon`       VARCHAR(128) NOT NULL DEFAULT '',
    `text`       VARCHAR(255) NOT NULL DEFAULT '',
    PRIMARY KEY (`account_id`, `mode`, `tab_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- item_guid is unique across every stash: one item can be linked in one slot of
-- one container and nowhere else, so a failed move can never leave a duplicate.
CREATE TABLE IF NOT EXISTS `dc_account_stash_item` (
    `account_id` INT UNSIGNED NOT NULL,
    `mode`       ENUM('normal','hardcore') NOT NULL,
    `tab_id`     TINYINT UNSIGNED NOT NULL,
    `slot_id`    TINYINT UNSIGNED NOT NULL,
    `item_guid`  INT UNSIGNED NOT NULL,
    PRIMARY KEY (`account_id`, `mode`, `tab_id`, `slot_id`),
    UNIQUE KEY `dc_account_stash_item_guid` (`item_guid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
