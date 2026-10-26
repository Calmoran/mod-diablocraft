-- Apply to the CHARACTERS database.
--
-- Hand-written schema migration (no generator owns it; a DROP is a schema
-- change, the one allowed hand-written kind). The tester Bounty Board is
-- retired (the designer, decisions.md 2026-10-10 dfcc0944; diablocraft-xq7ft): the
-- in-game board, its addon and its server half are gone, so its three tables
-- go with it. Their rows were exported before the drop to
-- azerothcore-wotlk/build/_agent-scratch/tester-board-retire-2026-10-10/
-- (66 dc_bounty rows, all status='open'; no claims; no submissions).
--
-- The board's content is also in the two applied migrations that filled it
-- (bounties_0002_web_carryover.sql, bounties_0003_aura_bounties.sql), which
-- stay as applied history.
--
-- Game bounties (the D3 way, through a bent stock Dungeon Finder) are a later
-- system with their own tables; this drop touches nothing of theirs.
DROP TABLE IF EXISTS `dc_bounty_submission`;
DROP TABLE IF EXISTS `dc_bounty_claim`;
DROP TABLE IF EXISTS `dc_bounty`;
