-- Apply to the CHARACTERS database.
--
-- Hand-written schema migration, like rifts_0001-0008. No data.
--
-- Greater Rifts part 6 (docs/briefs/greater-rifts-brief.md; difficulty_tiers.csv unlock_solo_gr).
-- Torment VII to XVI need a SOLO Greater Rift of level 30 up to 75, so beating one alone is its own
-- number on the character: the highest Greater Rift level it has beaten in time as the only member of
-- the run, 0 for none, per realm mode like the other two (rifts_0007).
ALTER TABLE `dc_character_gr`
  ADD COLUMN `beaten_solo` SMALLINT UNSIGNED NOT NULL DEFAULT 0
    COMMENT 'Highest Greater Rift level beaten in time with a party of one; 0 none (part 6)' AFTER `beaten`;
