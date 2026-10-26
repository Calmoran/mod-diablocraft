-- Approved tenth Warrior race. The pinned core keeps race and class stats
-- separately, so no invented race/class stats or core changes are needed.
INSERT INTO playercreateinfo(race,class,map,zone,position_x,position_y,position_z,orientation)
SELECT 10,1,map_id,area_id,x,y,z,o FROM dc_world_hub WHERE id=1
ON DUPLICATE KEY UPDATE map=VALUES(map),zone=VALUES(zone),position_x=VALUES(position_x),position_y=VALUES(position_y),position_z=VALUES(position_z),orientation=VALUES(orientation);
