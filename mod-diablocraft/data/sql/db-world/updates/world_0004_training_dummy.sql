-- GM Island training target: stock hostile-targetable, passive, immortal npc_training_dummy AI.
-- One independent target per literal tier phase; excluded from DC tier scaling by existing hooks.
-- Coordinates resolve to open area 876; stock creature templates are unchanged.
INSERT INTO creature (guid,id,map,zoneId,areaId,spawnMask,phaseMask,position_x,position_y,position_z,orientation,spawntimesecs,MovementType) VALUES
(8000057,31146,1,876,876,1,1,16210,16245,12.426671,0.6435,300,0),
(8000058,31146,1,876,876,1,2,16210,16245,12.426671,0.6435,300,0),
(8000059,31146,1,876,876,1,3,16210,16245,12.426671,0.6435,300,0),
(8000060,31146,1,876,876,1,4,16210,16245,12.426671,0.6435,300,0),
(8000061,31146,1,876,876,1,5,16210,16245,12.426671,0.6435,300,0),
(8000062,31146,1,876,876,1,6,16210,16245,12.426671,0.6435,300,0),
(8000063,31146,1,876,876,1,7,16210,16245,12.426671,0.6435,300,0),
(8000064,31146,1,876,876,1,8,16210,16245,12.426671,0.6435,300,0),
(8000065,31146,1,876,876,1,9,16210,16245,12.426671,0.6435,300,0),
(8000066,31146,1,876,876,1,10,16210,16245,12.426671,0.6435,300,0)
ON DUPLICATE KEY UPDATE id=VALUES(id),map=VALUES(map),zoneId=VALUES(zoneId),areaId=VALUES(areaId),phaseMask=VALUES(phaseMask),position_x=VALUES(position_x),position_y=VALUES(position_y),position_z=VALUES(position_z),orientation=VALUES(orientation),MovementType=VALUES(MovementType);
REPLACE INTO dc_area_source (map_id,area_id,kind,source_guid,entry,source_phase,position_x,position_y,position_z,orientation) VALUES (1,876,'c',8000057,31146,1,16210,16245,12.426671,0.6435);
REPLACE INTO dc_area_spawn (map_id,area_id,kind,source_guid,tier,spawn_guid) VALUES
(1,876,'c',8000057,2,8000058),
(1,876,'c',8000057,3,8000059),
(1,876,'c',8000057,4,8000060),
(1,876,'c',8000057,5,8000061),
(1,876,'c',8000057,6,8000062),
(1,876,'c',8000057,7,8000063),
(1,876,'c',8000057,8,8000064),
(1,876,'c',8000057,9,8000065),
(1,876,'c',8000057,10,8000066);
