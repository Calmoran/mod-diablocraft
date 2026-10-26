-- Apply to the CHARACTERS database.
--
-- The full-size /bug window (diablocraft-bug-window-full, brief
-- build/_agent-scratch/bug-window-2026-10-04/brief.md, ruling 2026-10-04): a report
-- now carries a required title (1..50 characters after trimming), the moment the
-- window was opened (the snapshot time that is filed with the report), and the
-- client patch number the addon reported. `body` widens so 2,000 characters fit
-- whatever their encoding: the handler counts characters, not bytes
-- (docs/contracts/bug-report-messages.md). `class` now holds the D3 class name the
-- character sheet shows (dc_class_map.d3_class), which is what the window displays
-- and therefore what is filed.
--
-- Alpha data is disposable: existing rows keep an empty title and NULL opened_at,
-- and their `class` keeps the wow_class it was written with; nothing is backfilled
-- beyond what keeps old rows valid.
ALTER TABLE `dc_bug_report`
  ADD COLUMN `title` VARCHAR(64) NOT NULL DEFAULT '' COMMENT 'Required report title, trimmed; 1-50 characters' AFTER `addon_version`,
  ADD COLUMN `client_patch` VARCHAR(16) NOT NULL DEFAULT '' COMMENT 'Client-reported TOC X-Torment-Client-Patch, untrusted' AFTER `title`,
  ADD COLUMN `opened_at` DATETIME NULL DEFAULT NULL COMMENT 'When the window was opened: the snapshot time filed with the report' AFTER `created_at`,
  MODIFY COLUMN `class` VARCHAR(32) NOT NULL DEFAULT '' COMMENT 'dc_class_map.d3_class for the character class',
  MODIFY COLUMN `body` VARCHAR(8192) NOT NULL COMMENT 'The report details, trimmed; at most 2000 characters';
