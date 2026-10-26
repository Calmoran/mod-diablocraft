-- diablocraft-nw0w: dc_legendary_gem took the world database's default collation (legendary_gems_0001 names none) while
-- dc_legendary_gem_item names utf8mb4_unicode_ci, so a bare join on gem_id raised an illegal mix of collations.
ALTER TABLE `dc_legendary_gem` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
