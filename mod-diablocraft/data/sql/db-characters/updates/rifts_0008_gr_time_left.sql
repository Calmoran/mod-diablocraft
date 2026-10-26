-- Apply to the CHARACTERS database.
--
-- Hand-written schema migration, like rifts_0001-0007 (the 2026-09-16 rule allows it where no
-- generator owns the table). No data.
--
-- Greater Rifts part 4 (docs/briefs/greater-rifts-brief.md; 09-rifts 7.4, 7.6). dc_rift.outcome
-- already records the in-time or expired result of a run (rifts_0005); for a Greater Rift it holds
-- `success` (the Guardian died before 0:00: beaten) or `expired` (the clock ran out first: failed),
-- written once, at the Guardian's death or at 0:00, whichever comes first. This adds the other half
-- the brief asks the run to keep: the whole seconds left on the clock when the Guardian died, which
-- part 6 reads for the unlock and part 5's tracker shows. NULL for a Nephalem Rift and for a run
-- that has no result yet; 0 for a failed one.
ALTER TABLE `dc_rift`
  ADD COLUMN `time_left` INT UNSIGNED NULL
    COMMENT 'Greater Rift only: whole seconds left on the clock when the Guardian died; 0 for an expired run, NULL until the result is set (part 4)' AFTER `outcome`;
