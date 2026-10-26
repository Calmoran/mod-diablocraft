-- Apply to the CHARACTERS database.
--
-- Hand-written schema migration, like rifts_0001-0005 (the 2026-09-16 rule
-- allows it where no generator owns the table). One nullable column, no data.
--
-- guardian_killed_at is the moment the rift guardian died and the run became
-- complete, written once by RewardGuardian (dc_rift_ai.cpp) with a
-- `WHERE guardian_killed_at IS NULL` guard. Clear time is
-- guardian_killed_at - opened_at. Rows that existed before this migration, and
-- runs abandoned or closed before the guardian died, stay NULL: their time is
-- unknown and is deliberately not backfilled.
ALTER TABLE `dc_rift`
  ADD COLUMN `guardian_killed_at` TIMESTAMP NULL DEFAULT NULL
    COMMENT 'When the guardian died and the run completed. NULL if it never did. Written once. Clear time = this - opened_at' AFTER `closing_at`;
