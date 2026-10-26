-- One row per character, written once, the moment that character has its two
-- Horadric Satchels (ruling 2026-09-12). Both paths write it: the starter grant
-- in dc_world.cpp puts the bags straight into bag slots 1 and 2 on a new
-- character, and the login sweep tops an existing character up. The row is what
-- stops the sweep ever running a second time; `granted` records how many that
-- character was actually handed, which is 0 for anyone who already had two.
CREATE TABLE IF NOT EXISTS dc_character_bag_grant (
  guid INT UNSIGNED NOT NULL PRIMARY KEY,
  granted TINYINT UNSIGNED NOT NULL DEFAULT 0,
  granted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
