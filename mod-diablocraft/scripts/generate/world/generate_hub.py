# Constant (audit 166): legacy GM Island hub; live values are world_hub_points.csv.
# Constant (audit 168): legacy GM Island hub; live values are world_hub_points.csv.
# Constant (audit 169): legacy GM Island hub; live values are world_hub_points.csv.
# Constant (audit 153, 533.33333): Stock map grid width; Map coordinate format, not a gameplay distance.
# Constant (audit 167, 35): Friendly artisan faction identity; Native faction ID, not damage/scaling.
# Constant (audit 184, 1): GM Island map ID; Native/content identity or bit flags; historic hub generator.
# Constant (audit 185, 876): GM Island area ID; Native/content identity or bit flags; historic hub generator.
# Constant (audit 186, 910000): Blacksmith entry; Native/content identity or bit flags; historic hub generator.
# Constant (audit 187, 2840): Blacksmith donor; Native/content identity or bit flags; historic hub generator.
# Constant (audit 188, 910001): Mystic entry; Native/content identity or bit flags; historic hub generator.
# Constant (audit 189, 190010): Mystic donor; Native/content identity or bit flags; historic hub generator.
# Constant (audit 190, 910002): Stash entry; Native/content identity or bit flags; historic hub generator.
# Constant (audit 191, 2455): Stash donor; Native/content identity or bit flags; historic hub generator.
# Constant (audit 192, 4225): Artisan service flags; Native/content identity or bit flags; historic hub generator.
# Constant (audit 193, 131073): Bank service flags; Native/content identity or bit flags; historic hub generator.
# Constant (audit 194, 8000000): Creature/object source GUID base; Native/content identity or bit flags; historic hub generator.
# Constant (audit 195, 8000001): Obelisk GUID; Native/content identity or bit flags; historic hub generator.
# Constant (audit 196, 8000100): Wall GUID base; Native/content identity or bit flags; historic hub generator.
# Constant (audit 197, 910010): Difficulty object entry; Native/content identity or bit flags; historic hub generator.
# Constant (audit 198, 910011): Obelisk entry; Native/content identity or bit flags; historic hub generator.
# Constant (audit 199, 185193): Hub object template donor; Native/content identity or bit flags; historic hub generator.
# Constant (audit 200, 180322): Ghost Gate wall template; Native/content identity or bit flags; historic hub generator.
"""Generate GM Island hub sources and a shoreline barrier from extracted terrain.

Requires the pinned core's MAPS version 9 files and a read-only world DB connection.
Writes the same world_0002_hub.sql on rerun. Tier copies use generate_area_copies.py.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from applied_migrations import write_migration, write_coupled_outputs
from tunable_values import value as tunable_value, integer as tunable_integer, positive as tunable_positive
import argparse
import math
from pathlib import Path
import struct
from generate_area_copies import Database, insert

GRID = struct.unpack('<f', struct.pack('<f', 533.33333))[0]


class Terrain:
    def __init__(self, directory):
        self.directory, self.cache = Path(directory), {}

    def sample(self, x, y):
        gx, gy = 32-x/GRID, 32-y/GRID
        key = int(gx), int(gy)
        if key not in self.cache:
            raw = (self.directory / f'001{key[0]:02}{key[1]:02}.map').read_bytes()
            h = struct.unpack_from('<11I', raw)
            if raw[:4] != b'MAPS' or h[1] != 9:
                raise ValueError('Unsupported terrain format')
            area_magic, flags, area = struct.unpack_from('<IHH', raw, h[3])
            areas = [area]*256 if flags & 1 else struct.unpack_from('<256H',raw,h[3]+8)
            magic,flags,low,high = struct.unpack_from('<IIff',raw,h[5])
            if flags & 1:
                values = [low]*(129*129+128*128)
            else:
                form, scale = ('H',(high-low)/65535) if flags & 2 else (('B',(high-low)/255) if flags & 4 else ('f',1))
                values=struct.unpack_from('<'+str(129*129+128*128)+form,raw,h[5]+16)
                if form != 'f': values=[v*scale+low for v in values]
            if h[9] and any(struct.unpack_from('<256H',raw,h[9])):
                raise ValueError('Terrain holes require a core-resolved survey')
            self.cache[key]=(areas,values[:129*129],values[129*129:])
        areas,v9,v8=self.cache[key]
        xx,yy=(gx*128)%128,(gy*128)%128
        ix,iy=int(xx),int(yy); xx-=ix; yy-=iy
        at=ix*129+iy
        h1,h2,h3,h4,h5=v9[at],v9[at+129],v9[at+1],v9[at+130],2*v8[ix*128+iy]
        if xx+yy<1:
            a,b,c=(h2-h1,h5-h1-h2,h1) if xx>yy else (h5-h1-h3,h3-h1,h1)
        else:
            a,b,c=(h2+h4-h5,h4-h2,h5-h4) if xx>yy else (h4-h3,h3+h4-h5,h5-h4)
        return a*xx+b*yy+c, areas[(int(gx*16)&15)*16+(int(gy*16)&15)]


def shoreline(terrain, center=None):
    if center is None:
        center = (tunable_value('ui', 'legacy_shoreline_center_x_yards'), tunable_value('ui', 'legacy_shoreline_center_y_yards'))
    points=[]
    for angle in range(0,360,tunable_integer("ui", "legacy_shoreline_step_degrees", minimum=1)):
        t=math.radians(angle)
        for radius in range(tunable_integer("ui", "legacy_shoreline_radius_start_yards"),tunable_integer("ui", "legacy_shoreline_radius_end_yards")):
            x,y=center[0]+radius*math.cos(t),center[1]+radius*math.sin(t)
            height,area=terrain.sample(x,y)
            if height<tunable_value("ui", "legacy_shoreline_waterline_yards"):
                radius-=tunable_value("ui", "legacy_shoreline_inset_yards")  # Landward side of the waterline.
                x,y=center[0]+radius*math.cos(t),center[1]+radius*math.sin(t)
                height,area=terrain.sample(x,y)
                if area != 876: raise ValueError(f'Shoreline outside GM Island: {x,y,area}')
                points.append((x,y,height)); break
        else: raise ValueError(f'No shoreline at angle {angle}')
    # Every segment is covered by overlapping 22.15-yard Ghost Gate slabs.
    walls=[]
    for start,end in zip(points,points[1:]+points[:1]):
        length=math.dist(start[:2],end[:2]); count=max(1,math.ceil(length/tunable_positive("ui", "legacy_wall_spacing_yards")))
        angle=math.atan2(end[1]-start[1],end[0]-start[0])-math.pi/2
        for i in range(count):
            fraction=(i+0.5)/count
            x,y=(start[j]+(end[j]-start[j])*fraction for j in (0,1))
            z,area=terrain.sample(x,y)
            if area!=876: raise ValueError(f'Wall outside open area: {x,y,area}')
            walls.append((x,y,z-tunable_value("ui", "legacy_wall_burial_yards"),angle))
    return walls


def generate(db, terrain):
    spawn_x = tunable_value('ui', 'legacy_spawn_x_yards')
    spawn_y = tunable_value('ui', 'legacy_spawn_y_yards')
    spawn_z = tunable_value('ui', 'legacy_spawn_z_yards')
    sql=['-- Generated by scripts/generate_hub.py; GM Island (map 1, area 876) only.',
         '-- Ghost Gate display 6391 bounds: Y -5.5526..5.5245, Z -0.6868..17.5623; template scale 2.',
         'SET NAMES utf8mb4;',
         'CREATE TABLE IF NOT EXISTS dc_world_hub(id INT PRIMARY KEY,map_id INT,area_id INT,x FLOAT,y FLOAT,z FLOAT,o FLOAT);',
         f'REPLACE INTO dc_world_hub VALUES(1,1,876,{spawn_x},{spawn_y},{spawn_z},1.65007);',
         f'UPDATE playercreateinfo SET map=1,zone=876,position_x={spawn_x},position_y={spawn_y},position_z={spawn_z},orientation=1.65007 WHERE class=1;']
    # Clone only the model/template, never the stock vendor's inventory or quests.
    for entry,source,name,flags,script,x,y in [
        (910000,2840,'Blacksmith',4225,'dc_hub_blacksmith',tunable_value("ui", "legacy_blacksmith_x_yards"),tunable_value("ui", "legacy_blacksmith_y_yards")),
        (910001,190010,'Mystic',4225,'npc_transmogrifier',tunable_value("ui", "legacy_mystic_x_yards"),tunable_value("ui", "legacy_mystic_y_yards")),
        (910002,2455,'Stash',131073,'',tunable_value("ui", "legacy_stash_x_yards"),tunable_value("ui", "legacy_stash_y_yards"))]:
        row=db.rows('creature_template',f'entry={source}')[0]
        row.update(entry=entry,name=name,npcflag=flags,ScriptName=script,faction=35,AIName='')
        sql += [f'DELETE FROM creature_template WHERE entry={entry};',insert('creature_template',row),f'DELETE FROM creature_template_model WHERE CreatureID={entry};']
        for model in db.rows('creature_template_model',f'CreatureID={source}'):
            model['CreatureID']=entry; sql.append(insert('creature_template_model',model))
        guid=8000000+entry-910000
        z,area=terrain.sample(x,y)
        if area!=876: raise ValueError('Artisan outside GM Island')
        sql += [f'DELETE FROM creature WHERE guid={guid};',
                f'INSERT INTO creature(guid,id,map,zoneId,areaId,spawnMask,phaseMask,position_x,position_y,position_z,orientation,spawntimesecs) VALUES({guid},{entry},1,876,876,1,1,{x},{y},{z+0.1},3.14,{tunable_integer("monsters", "legacy_hub_npc_respawn_seconds")});']
    for entry,name in [(910010,'Difficulty'),(910011,'Rift Obelisk (inactive)')]:
        row=db.rows('gameobject_template','entry=185193')[0]
        row.update(entry=entry,name=name,size=tunable_positive("ui", "legacy_hub_object_scale_multiplier"),type=10,ScriptName='',AIName='')
        for key in row:
            if key.lower().startswith('data') and key[4:].isdigit(): row[key]=0
        sql += [f'DELETE FROM gameobject_template WHERE entry={entry};',insert('gameobject_template',row)]
    def spawn(guid,entry,x,y,z,o):
        return [f'DELETE FROM gameobject WHERE guid={guid};',
            f'INSERT INTO gameobject(guid,id,map,zoneId,areaId,spawnMask,phaseMask,position_x,position_y,position_z,orientation,rotation2,rotation3,spawntimesecs,animprogress,state) VALUES({guid},{entry},1,876,876,1,1,{x:.6f},{y:.6f},{z:.6f},{o:.8f},{math.sin(o/2):.9f},{math.cos(o/2):.9f},{tunable_integer("monsters", "legacy_hub_object_respawn_seconds")},255,1);']
    for guid,entry,x,y in [(8000000,910010,tunable_value("ui", "legacy_difficulty_x_yards"),tunable_value("ui", "legacy_difficulty_y_yards")),(8000001,910011,tunable_value("ui", "legacy_obelisk_x_yards"),tunable_value("ui", "legacy_obelisk_y_yards"))]:
        z,area=terrain.sample(x,y)
        if area!=876: raise ValueError('Hub object outside GM Island')
        sql += spawn(guid,entry,x,y,z+tunable_value("ui", "legacy_hub_object_height_offset_yards"),0)
    walls=shoreline(terrain)
    for i,wall in enumerate(walls): sql += spawn(8000100+i,180322,*wall)
    print(f'Hub: 3 NPCs, 2 objects, {len(walls)} wall segments; only phase-1 sources. Generate tier copies after the core area scan.')
    return '\n'.join(sql)+'\n'


if __name__=='__main__':
    import sys
    if '--jeweler' in sys.argv:
        from generate_crafting import read, number, quote
        from generate_hub_placements import export, generate as placements
        p=argparse.ArgumentParser()
        p.add_argument('--jeweler',action='store_true')
        p.add_argument('--export',action='store_true')
        p.add_argument('--mysql');p.add_argument('--defaults-file')
        args=p.parse_args()
        root=Path(__file__).resolve().parents[3]
        rows=read('jeweler_npc.csv')
        if len(rows)!=1: raise ValueError('Expected one Jeweler template')
        row=rows[0];entry=number(row,'entry');source=number(row,'clone_entry');flags=number(row,'npcflag')
        sql=['-- Generated by generate_hub.py --jeweler from jeweler_npc.csv; the designer places it in Shattrath.',
             'CREATE TEMPORARY TABLE dc_jeweler_template LIKE creature_template;',
             f'INSERT INTO dc_jeweler_template SELECT * FROM creature_template WHERE entry={source};',
             f'UPDATE dc_jeweler_template SET entry={entry},name={quote(row["name"])},subname=\'\',npcflag={flags},ScriptName=\'\',AIName=\'\';',
             'REPLACE INTO creature_template SELECT * FROM dc_jeweler_template;',
             'DROP TEMPORARY TABLE dc_jeweler_template;',
             f'DELETE FROM creature_template_model WHERE CreatureID={entry};',
             f'INSERT INTO creature_template_model SELECT {entry},Idx,CreatureDisplayID,DisplayScale,Probability,VerifiedBuild FROM creature_template_model WHERE CreatureID={source};']
        (root/'data/generated/world_0008_jeweler.sql').write_text('\n'.join(sql)+'\n',encoding='utf-8',newline='\n')
        write_migration(root, root/'data/sql/db-world/updates/world_0008_jeweler.sql', '\n'.join(sql)+'\n')
        # world_0008 stays as it shipped (the applied-migration guard freezes it); the Jeweler's own name is
        # a later UPDATE from the display_* columns (ruling q-1001-15: Covetous Shen, subname Jeweler).
        rename=['-- Generated by generate_hub.py --jeweler from jeweler_npc.csv; never edit.',
                f'-- {row["display_source"]}',
                f'UPDATE creature_template SET name={quote(row["display_name"])},subname={quote(row["display_subname"])} WHERE entry={entry};']
        # The Jeweler repairs nothing and sells nothing (ruling 2026-10-01): gossip only, from service_npcflag.
        flags_name='world_0026_jeweler_flags.sql'
        service=number(row,'service_npcflag')
        flags=['-- Generated by generate_hub.py --jeweler from jeweler_npc.csv; never edit.',
               f'-- {row["service_source"]}',
               f'UPDATE creature_template SET npcflag={service} WHERE entry={entry};']
        write_migration(root, root/'data/sql/db-world/updates'/flags_name, '\n'.join(flags)+'\n')
        write_coupled_outputs(root, root/'data/sql/db-world/updates'/flags_name, '\n'.join(flags)+'\n',
                              [(root/'data/generated'/flags_name, '\n'.join(flags)+'\n')])
        rename_name='world_0025_jeweler_rename.sql'
        write_migration(root, root/'data/sql/db-world/updates'/rename_name, '\n'.join(rename)+'\n')
        write_coupled_outputs(root, root/'data/sql/db-world/updates'/rename_name, '\n'.join(rename)+'\n',
                              [(root/'data/generated'/rename_name, '\n'.join(rename)+'\n')])
        path=root/'data/d3/world_jeweler_placement.csv'
        expected={'c':{entry}}
        if args.export:
            if not args.mysql or not args.defaults_file: p.error('--export requires --mysql and --defaults-file')
            export(Database(args.mysql,args.defaults_file,'acore_world'),path,expected)
        if path.exists():
            sql=placements(path,expected)
            (root/'data/generated/world_0009_jeweler_placement.sql').write_text(sql,encoding='utf-8',newline='\n')
            write_migration(root, root/'data/sql/db-world/updates/world_0009_jeweler_placement.sql', sql)
            print('Jeweler: one placement and nine tier copies generated')
        else:
            print(f'Jeweler template {entry} generated; the designer must place .npc add {entry}, then .dc areas scan 530 3703 before --export')
        sys.exit(0)
    p=argparse.ArgumentParser(); p.add_argument('--mysql',required=True); p.add_argument('--defaults-file',required=True); p.add_argument('--maps',required=True)
    args=p.parse_args(); db=Database(args.mysql,args.defaults_file,'acore_world')
    sql=generate(db,Terrain(args.maps))
    root=Path(__file__).resolve().parents[3]
    (root/'data/generated/world_0002_hub.sql').write_text(sql,encoding='utf-8',newline='\n')
    write_migration(root, root/'data/sql/db-world/updates/world_0002_hub.sql', sql)
