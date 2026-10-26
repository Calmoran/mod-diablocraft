-- Apply to the CHARACTERS database.
--
-- Hand-written schema migration (no generator owns the table). No data: the module writes the column when it draws a board.
--
-- Bounty acts A0n (diablocraft-hyoic.2; ruling 2026-10-12, decisions: one master list of named targets, each zone's bounty on
-- a new board a random pick from it). A Kill cell keeps the target its board drew.
--   target  creature_template entry of the drawn named target (world dc_bounties_target.entry); 0 for a Click cell
-- A board saved before this column reads target 0 for its Kill cells, which the module drops (dc_bounties.cpp LoadLocked),
-- so the next look draws a new board. Guarded, so a second run changes nothing.
SET @dc_column_exists=(SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='dc_bounties_board' AND column_name='target');
SET @dc_ddl=IF(@dc_column_exists=0,'ALTER TABLE dc_bounties_board ADD COLUMN target INT UNSIGNED NOT NULL DEFAULT 0','DO 0');
PREPARE dc_bounties_ddl FROM @dc_ddl;
EXECUTE dc_bounties_ddl;
DEALLOCATE PREPARE dc_bounties_ddl;
