-- diablocraft-xw2m (the Mystic rebuilt the D3 way): a paid roll's stored choices can now be a weapon
-- damage line, which rolls TWO numbers (items_0006_weapon_damage.sql). value2 is the second endpoint
-- and range_min2/range_max2 the second bracket, beside value and range_min/range_max. Every other
-- offer keeps all three at 0, so a pending offer written by the old code is unchanged: it comes back as
-- the line's current roll (read from the item) plus its two stored choices.
-- Hand-written schema migration (ALTER only), applied by the core updater to the characters database.
-- It sorts after items_crafting_0001_artisans.sql, which creates dc_enchant_offer.
SET @dc_column_exists=(SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='dc_enchant_offer' AND column_name='value2');
SET @dc_ddl=IF(@dc_column_exists=0,'ALTER TABLE dc_enchant_offer ADD COLUMN value2 DOUBLE NOT NULL DEFAULT 0','DO 0');
PREPARE dc_enchant_offer_ddl FROM @dc_ddl;
EXECUTE dc_enchant_offer_ddl;
DEALLOCATE PREPARE dc_enchant_offer_ddl;
SET @dc_column_exists=(SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='dc_enchant_offer' AND column_name='range_min2');
SET @dc_ddl=IF(@dc_column_exists=0,'ALTER TABLE dc_enchant_offer ADD COLUMN range_min2 DOUBLE NOT NULL DEFAULT 0','DO 0');
PREPARE dc_enchant_offer_ddl FROM @dc_ddl;
EXECUTE dc_enchant_offer_ddl;
DEALLOCATE PREPARE dc_enchant_offer_ddl;
SET @dc_column_exists=(SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='dc_enchant_offer' AND column_name='range_max2');
SET @dc_ddl=IF(@dc_column_exists=0,'ALTER TABLE dc_enchant_offer ADD COLUMN range_max2 DOUBLE NOT NULL DEFAULT 0','DO 0');
PREPARE dc_enchant_offer_ddl FROM @dc_ddl;
EXECUTE dc_enchant_offer_ddl;
DEALLOCATE PREPARE dc_enchant_offer_ddl;
