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
  `repair_multiplier` DECIMAL(3,2) NULL,
  `elite_scale_champion` DECIMAL(3,2) NULL,
  `elite_scale_rare` DECIMAL(3,2) NULL,
  `elite_scale_minion` BIGINT NULL,
  `champion_pack_size` BIGINT NULL,
  `notes` LONGTEXT NOT NULL,
  `base_monster_xp` BIGINT NULL,
  `gem_chance_pct` BIGINT NULL,
  `gem_imperial_share_pct` BIGINT NULL,
  `identify_item_cast_seconds` DECIMAL(2,1) NULL,
  `identify_tome_cast_seconds` BIGINT NULL,
  `unidentified_drops` BIGINT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
INSERT INTO `dc_loot_tuning` (`source`, `drops_min`, `drops_max`, `legendary_base_pct`, `normal_pct`, `magic_pct`, `rare_pct`, `chest_multiplier`, `deaths_breath_pct`, `elite_promotion_pct`, `gold_divisor`, `mystic_base_gold`, `mystic_cost_multiplier`, `repair_multiplier`, `elite_scale_champion`, `elite_scale_rare`, `elite_scale_minion`, `champion_pack_size`, `notes`, `base_monster_xp`, `gem_chance_pct`, `gem_imperial_share_pct`, `identify_item_cast_seconds`, `identify_tome_cast_seconds`, `unidentified_drops`) VALUES
('normal', 1, 1, 0.1, 60, 30, 10, 1, 0, 0, 1, 1000, 1.15, 0.01, 1.15, 1.30, 1.00, 3, 'L1 base legendary 0.1% and L6 split 60/30/10; L6 drop count ~1 per normal kill; Artisan tunables: Mystic base 1000 gold, multiplier 1.15; repair multiplier 0.01 (level-70 kit full repair about 6.8% of a Normal 90-kill rift gold baseline; was 100 while one displayed gold was 10000 copper, divided by 10000 for the 2026-09-12 gold unit so the ratio is unchanged); tunable base_monster_xp=72000: initial proposal gives 100 solo Normal kills to Paragon 1; shared by every creature rank.', 72000, NULL, NULL, NULL, NULL, NULL),
('elite', 3, 5, 1, 60, 30, 10, 1, 15, 8, 1, 1000, 1.15, 0.01, 1.15, 1.30, 1.00, 3, 'L1 base legendary 1% for champion/rare/minion; L6 drop count 3-5 per elite pack. deaths_breath_pct is the Normal-tier figure stated in difficulty_tiers.csv prose; that column is prose, not a number, so per-tier scaling is not available yet; Artisan tunables: Mystic base 1000 gold, multiplier 1.15; repair multiplier 0.01 (level-70 kit full repair about 6.8% of a Normal 90-kill rift gold baseline; was 100 while one displayed gold was 10000 copper, divided by 10000 for the 2026-09-12 gold unit so the ratio is unchanged); the designer''s tunables (03-difficulty section 5 elite look): promoted champions scale x1.15, rares x1.3, their minions x1.0; read from the elite row only.; the designer''s tunable (03-difficulty section 5, decisions.md 2026-09-07): champion_pack_size 3 identical champions in total (itself + 2); the rare pack''s 1 rare + 2-4 minions is unchanged', NULL, NULL, NULL, NULL, NULL, NULL),
('boss', 3, 5, 1, 60, 30, 10, 1, 0, 0, 1, 1000, 1.15, 0.01, 1.15, 1.30, 1.00, 3, 'L1 gives no boss rate and drop_rates.csv records it NOT PUBLISHED; set to the elite rate as a tunable. The act-boss first-kill guarantee is L11 and is applied separately, not from this row; Artisan tunables: Mystic base 1000 gold, multiplier 1.15; repair multiplier 0.01 (level-70 kit full repair about 6.8% of a Normal 90-kill rift gold baseline; was 100 while one displayed gold was 10000 copper, divided by 10000 for the 2026-09-12 gold unit so the ratio is unchanged)', NULL, NULL, NULL, NULL, NULL, NULL),
('rift_guardian', 3, 5, 100, 60, 30, 10, 1, 0, 0, 1, 1000, 1.15, 0.01, 1.15, 1.30, 1.00, 3, 'L1 rift guardian 100%; the guarantee applies to the first drop and the rest roll as elite per 06 section 2; Artisan tunables: Mystic base 1000 gold, multiplier 1.15; repair multiplier 0.01 (level-70 kit full repair about 6.8% of a Normal 90-kill rift gold baseline; was 100 while one displayed gold was 10000 copper, divided by 10000 for the 2026-09-12 gold unit so the ratio is unchanged)', NULL, NULL, NULL, NULL, NULL, NULL),
('chest', 1, 1, 0.1, 60, 30, 10, 2, 0, 0, 1, 1000, 1.15, 0.01, 1.15, 1.30, 1.00, 3, 'Chest multiplier is not published (06 section 6 open item); 2 is a tunable first value and multiplies the drop count; Artisan tunables: Mystic base 1000 gold, multiplier 1.15; repair multiplier 0.01 (level-70 kit full repair about 6.8% of a Normal 90-kill rift gold baseline; was 100 while one displayed gold was 10000 copper, divided by 10000 for the 2026-09-12 gold unit so the ratio is unchanged)', NULL, NULL, NULL, NULL, NULL, NULL),
('gem', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'the designer''s tunables (2026-09-11): 10% independent normal-gem roll per eligible monster per player; 10% Imperial share of successful level-61+ Master-or-higher gem drops. Rates are not published by D3; five normal colours use equal weights (launch tunable). Eligibility is sourced in gem_drops.csv; no chest or Greater Rift guardian route.', NULL, 10, 10, NULL, NULL, NULL),
('identify', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'the designer''s tunables (2026-09-17, decisions.md): right-click identify on one item is a 1.5 s cast; the hub Tome of Identification, which identifies every unidentified item in the bags at once, is a 2 s cast. The earlier single identify_cast_seconds=2 from the same day is superseded by those two. unidentified_drops is the on/off switch for the whole feature: 1 delivers legendary and set drops as unrolled shells, 0 rolls them at drop as before. Read from this row only, like the gem row above.', NULL, NULL, NULL, 1.5, 2, 1);
