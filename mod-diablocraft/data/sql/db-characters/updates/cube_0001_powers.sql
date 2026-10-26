-- Kanai's Cube: the powers an account has extracted and the power each character has chosen for each slot
-- (docs/research/kanais-cube.md 6.2; docs/contracts/cube-messages.md). Characters DB.
--
-- dc_cube_power is keyed (account_id, mode) as the ledger and the stash are, so a hardcore account's collection is its own
-- and deleting a character never reaches it. power_id is the pool item's d3_id (dc_base_item.d3_id), the legendary
-- framework's key (docs/contracts/legendary-powers.md "The Cube source"), not an item entry: entries are renumbered when the
-- base item sheet grows. Nothing writes a row until the Archive (diablocraft-wpt7l.10) extracts a power.
-- dc_cube_slot is per character (slot 1..3: dc_cube_slot_item); its rows go when the character does.
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `dc_cube_power` (
    `account_id` INT UNSIGNED NOT NULL,
    `mode`       ENUM('normal','hardcore') NOT NULL,
    `power_id`   VARCHAR(100) NOT NULL,
    PRIMARY KEY (`account_id`, `mode`, `power_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `dc_cube_slot` (
    `guid`     INT UNSIGNED NOT NULL,
    `slot`     TINYINT UNSIGNED NOT NULL,
    `power_id` VARCHAR(100) NOT NULL,
    PRIMARY KEY (`guid`, `slot`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
