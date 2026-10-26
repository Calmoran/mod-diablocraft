-- Nephalem Rifts snapshot the admitted party, using dc_party_scaling.open_world.
ALTER TABLE `dc_rift`
  ADD COLUMN `party_size` TINYINT UNSIGNED NOT NULL DEFAULT 1 AFTER `tier`;
