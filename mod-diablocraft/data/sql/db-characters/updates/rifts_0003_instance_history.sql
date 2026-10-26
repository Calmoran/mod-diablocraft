-- Core instance IDs are reused after saves expire; preserve older rift history.
-- The live map cache owns a single run per instance; id is the run's identity.
ALTER TABLE `dc_rift`
  DROP INDEX `uk_dc_rift_instance`,
  ADD KEY `idx_dc_rift_instance` (`instance_id`, `id`);
