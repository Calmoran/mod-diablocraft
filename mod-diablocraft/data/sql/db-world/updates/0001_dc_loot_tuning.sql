-- Generated from data/d3/loot_tuning.csv; edit the CSV and rerun generate_sql.py.
-- Apply to the world database.
SET NAMES utf8mb4;
DROP TABLE IF EXISTS `dc_loot_tuning`;
CREATE TABLE `dc_loot_tuning` (
  `source` LONGTEXT NOT NULL,
  `drops_min` BIGINT NULL,
  `drops_max` BIGINT NULL,
  `legendary_base_pct` DECIMAL(4,1) NULL,
  `normal_pct` BIGINT NULL,
  `magic_pct` BIGINT NULL,
  `rare_pct` BIGINT NULL,
  `chest_multiplier` BIGINT NULL,
  `deaths_breath_pct` BIGINT NULL,
  `elite_promotion_pct` BIGINT NULL,
  `gold_divisor` BIGINT NULL,
  `mystic_base_gold` BIGINT NULL,
  `mystic_cost_multiplier` DECIMAL(3,2) NULL,
  `repair_multiplier` BIGINT NULL,
  `notes` LONGTEXT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
INSERT INTO `dc_loot_tuning` (`source`, `drops_min`, `drops_max`, `legendary_base_pct`, `normal_pct`, `magic_pct`, `rare_pct`, `chest_multiplier`, `deaths_breath_pct`, `elite_promotion_pct`, `gold_divisor`, `mystic_base_gold`, `mystic_cost_multiplier`, `repair_multiplier`, `notes`) VALUES
('normal', 1, 1, 0.1, 60, 30, 10, 1, 0, 0, 1, 1000, 1.15, 100, 'L1 base legendary 0.1% and L6 split 60/30/10; L6 drop count ~1 per normal kill; Artisan tunables: Mystic base 1000 gold, multiplier 1.15; repair multiplier 100 (level-70 kit full repair about 6.8% of a Normal 90-kill rift gold baseline)'),
('elite', 3, 5, 1, 60, 30, 10, 1, 15, 8, 1, 1000, 1.15, 100, 'L1 base legendary 1% for champion/rare/minion; L6 drop count 3-5 per elite pack. deaths_breath_pct is the Normal-tier figure stated in difficulty_tiers.csv prose; that column is prose, not a number, so per-tier scaling is not available yet; Artisan tunables: Mystic base 1000 gold, multiplier 1.15; repair multiplier 100 (level-70 kit full repair about 6.8% of a Normal 90-kill rift gold baseline)'),
('boss', 3, 5, 1, 60, 30, 10, 1, 0, 0, 1, 1000, 1.15, 100, 'L1 gives no boss rate and drop_rates.csv records it NOT PUBLISHED; set to the elite rate as a tunable. The act-boss first-kill guarantee is L11 and is applied separately, not from this row; Artisan tunables: Mystic base 1000 gold, multiplier 1.15; repair multiplier 100 (level-70 kit full repair about 6.8% of a Normal 90-kill rift gold baseline)'),
('rift_guardian', 3, 5, 100, 60, 30, 10, 1, 0, 0, 1, 1000, 1.15, 100, 'L1 rift guardian 100%; the guarantee applies to the first drop and the rest roll as elite per 06 section 2; Artisan tunables: Mystic base 1000 gold, multiplier 1.15; repair multiplier 100 (level-70 kit full repair about 6.8% of a Normal 90-kill rift gold baseline)'),
('chest', 1, 1, 0.1, 60, 30, 10, 2, 0, 0, 1, 1000, 1.15, 100, 'Chest multiplier is not published (06 section 6 open item); 2 is a tunable first value and multiplies the drop count; Artisan tunables: Mystic base 1000 gold, multiplier 1.15; repair multiplier 100 (level-70 kit full repair about 6.8% of a Normal 90-kill rift gold baseline)');
