-- Apply to the CHARACTERS database.
--
-- Hand-written like rifts_0001-0004, which the designer's 2026-09-16 rule allows for a
-- schema migration no generator owns. Nothing here is data: every rift NUMBER
-- still arrives through a CSV and a generator.
--
-- Idempotent in the sense rifts_0001-0004 are: CREATE TABLE IF NOT EXISTS, and
-- a backfill that only touches rows it has not already filled. The ALTER is
-- not re-runnable; it is a one-shot numbered update like rifts_0002/0003.
--
-- 09-rifts section 7.6 and the Phase A brief step 2. The quest owns each
-- player's log presence and visible counter; dc_rift stays authoritative for
-- the shared run.

-- --------------------------------------------------------------- dc_rift ---
-- progress/required_units are section 7.6's progress_units/progress_required
-- under the brief's names. Raw `kills` and `required` are deliberately kept:
-- 7.6 says the CSV kill baseline stays for the model and diagnostics, and
-- guardian spawning must not be left keyed on kills alone.
--
-- required_units = 20 x required. The factor 20 is the reciprocal of the designer's
-- 5% orb tunable (7.3), not a second tunable, so it is derived here rather
-- than stored as a tuning input.
--
-- `gr_rank`, NOT `rank`: `rank` is reserved in MySQL 8, which is why
-- rifts_0004 already spells its own column `elite_rank`. Same convention.
--
-- leader_guid keeps its name and becomes the persisted OWNER, cleanup
-- bookkeeping only (7.9.7: the owner leaving no longer closes the run, and a
-- later group leader is never the stored owner). Renaming it would touch every
-- existing read for no gain; the comment carries the meaning.
ALTER TABLE `dc_rift`
  MODIFY COLUMN `leader_guid` BIGINT UNSIGNED NOT NULL
    COMMENT 'Persisted OWNER for cleanup bookkeeping only (7.9.7); never the current group leader',
  ADD COLUMN `progress` INT UNSIGNED NOT NULL DEFAULT 0
    COMMENT 'Shared progress units, capped at required_units (7.3)' AFTER `required`,
  ADD COLUMN `required_units` INT UNSIGNED NOT NULL DEFAULT 0
    COMMENT '20 x required; the fixed quest denominator M (7.3)' AFTER `progress`,
  ADD COLUMN `mode` ENUM('nr','gr') NOT NULL DEFAULT 'nr'
    COMMENT 'Phase A opens nr only; gr is Phase B' AFTER `required_units`,
  ADD COLUMN `gr_rank` SMALLINT UNSIGNED NULL
    COMMENT 'Greater Rift rank, NULL for nr. No cap encoded: the rank cap is still open (7.9.7)' AFTER `mode`,
  ADD COLUMN `deadline` DATETIME NULL
    COMMENT 'Shared GR deadline, absolute. NULL for nr, which has no timer (7.4)' AFTER `gr_rank`,
  ADD COLUMN `outcome` ENUM('pending','success','expired') NOT NULL DEFAULT 'pending'
    COMMENT 'Durable in-time/expired result, recorded at guardian death, independent of reward settlement (7.4)' AFTER `deadline`,
  ADD COLUMN `closing_at` DATETIME NULL
    COMMENT 'When the Keeper 30s countdown expires. NULL until the first turn-in; a repeat turn-in never moves it (7.6)' AFTER `outcome`;

-- Backfill for runs opened before this migration. Their `required` is the CSV
-- kill baseline K, so M = 20K exactly as a new run would compute it.
UPDATE `dc_rift` SET `required_units` = 20 * `required` WHERE `required_units` = 0;

-- -------------------------------------------------------- dc_rift_member ---
-- The run-to-player-to-quest association 7.6 requires. An in-memory quest id
-- alone cannot tell apart two runs that reuse the same quest template, so this
-- is persisted and swept at login.
--
-- state, per the brief:
--   enrolled  holds the quest and receives progress. A town trip stays enrolled
--             (7.9.1 item 4), and so does an ordinary death in the instance.
--   offline   logged out or disconnected, inside the 2-minute grace
--             (rift_logout_grace_seconds). Returning restores enrolled.
--   left      left or was kicked from the party; quest and rift access removed.
--   detached  grace expired, or an NR member who left and has not reaccepted.
-- NR allows enrolled -> left/detached -> enrolled while the run lives; GR makes
-- any pre-guardian departure final (7.9.2 item 7).
CREATE TABLE IF NOT EXISTS `dc_rift_member` (
  `run_id` BIGINT UNSIGNED NOT NULL COMMENT 'dc_rift.id',
  `player_guid` BIGINT UNSIGNED NOT NULL,
  `quest_id` INT UNSIGNED NOT NULL COMMENT 'The run fixed quest variant this member holds',
  `state` ENUM('enrolled','left','offline','detached') NOT NULL DEFAULT 'enrolled',
  `offline_since` DATETIME NULL COMMENT 'Set on logout/disconnect; the grace is measured from here',
  `departure_reason` VARCHAR(32) NOT NULL DEFAULT ''
    COMMENT 'left | kicked | logout | disconnected | grace_expired | closed',
  PRIMARY KEY (`run_id`, `player_guid`),
  KEY `idx_dc_rift_member_player` (`player_guid`, `state`) COMMENT 'The login sweep reads by player',
  KEY `idx_dc_rift_member_run` (`run_id`, `state`) COMMENT 'Headcount rescale and last-member-out count by run'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
