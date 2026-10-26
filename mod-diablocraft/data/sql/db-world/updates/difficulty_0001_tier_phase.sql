-- Keep launch IDs separate from regenerated CSV tables so regeneration preserves them.
CREATE TABLE IF NOT EXISTS `dc_tier_phase` (
  `tier_id` TINYINT UNSIGNED NOT NULL,
  `phase` INT UNSIGNED NOT NULL,
  `tier_name` VARCHAR(32) NOT NULL,
  PRIMARY KEY (`tier_id`),
  UNIQUE KEY (`phase`),
  UNIQUE KEY (`tier_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
INSERT INTO `dc_tier_phase` (`tier_id`, `phase`, `tier_name`) VALUES
(1,1,'Normal'),(2,2,'Hard'),(3,3,'Expert'),(4,4,'Master'),
(5,5,'Torment I'),(6,6,'Torment II'),(7,7,'Torment III'),
(8,8,'Torment IV'),(9,9,'Torment V'),(10,10,'Torment VI')
ON DUPLICATE KEY UPDATE `phase`=VALUES(`phase`), `tier_name`=VALUES(`tier_name`);
