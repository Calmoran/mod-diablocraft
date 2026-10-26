-- Generated from data/d3/class_starts.csv by generate_sql.py --class-starts.
-- Ruling 2026-09-23 (diablocraft-class-parity Q2 option a): characters that existed
-- before their class had a start profile get mode and account setup on login
-- (dc_world.cpp Setup) and never the kit or the starter Satchels. Existing rows
-- are kept (INSERT IGNORE), so a recorded start or bag grant is never changed.
INSERT IGNORE INTO dc_character_start (guid,complete) SELECT guid,1 FROM characters WHERE class IN (14);
INSERT IGNORE INTO dc_character_bag_grant (guid,granted) SELECT guid,0 FROM characters WHERE class IN (14);
