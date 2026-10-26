-- PvE-only: use the core's built-in disable registry, not nonexistent conf switches.
-- Preserve any existing disable records.
INSERT IGNORE INTO disables (sourceType,entry,flags,params_0,params_1,comment)
SELECT 5,TypeId,0,'','','Diablocraft: outdoor PvP disabled for closed world areas'
FROM outdoorpvp_template;
INSERT IGNORE INTO disables (sourceType,entry,flags,params_0,params_1,comment)
SELECT 3,id,0,'','','Diablocraft: battlegrounds and arenas disabled (PvE only)'
FROM battleground_template;
