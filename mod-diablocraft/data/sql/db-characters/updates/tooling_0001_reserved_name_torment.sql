-- The Lua error drop (diablocraft-g74u4, the designer's brief bugsack-to-server-2026-10-14 step 1b): BugSack's "send to
-- player" goes to Torment, which nobody plays. Reserved on every realm so no one can make a character by that name
-- and read the sends (ObjectMgr::IsReservedName compares lowercased, so every capitalisation is held).
INSERT IGNORE INTO `reserved_name` (`name`) VALUES ('Torment');
