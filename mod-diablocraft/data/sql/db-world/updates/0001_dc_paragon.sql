-- Generated from data/d3/paragon.csv; edit the CSV and rerun generate_sql.py.
-- Apply to the world database.
SET NAMES utf8mb4;
DROP TABLE IF EXISTS `dc_paragon`;
CREATE TABLE `dc_paragon` (
  `category` LONGTEXT NOT NULL,
  `stat` LONGTEXT NOT NULL,
  `points_per_rank` LONGTEXT NOT NULL,
  `effect_per_point` LONGTEXT NOT NULL,
  `max_rank` LONGTEXT NOT NULL,
  `notes` LONGTEXT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
INSERT INTO `dc_paragon` (`category`, `stat`, `points_per_rank`, `effect_per_point`, `max_rank`, `notes`) VALUES
('Core', 'Primary stat (Strength/Dexterity/Intelligence by class)', '1', '+5', 'UNCAPPED', ''),
('Core', 'Vitality', '1', '+5', 'UNCAPPED', ''),
('Core', 'Movement Speed', '1', '+0.50%', '50 (cap +25%)', 'Cap equals max base bonus for most classes; item +Movement Speed affixes useless beyond that'),
('Core', 'Class max resource — Mana', '1', '+4', '50', ''),
('Core', 'Class max resource — Spirit / Fury / Essence', '1', '+1', '50', ''),
('Core', 'Class max resource — Wrath / Arcane Power / Hatred', '1', '+0.5', '50', 'Demon Hunters do not gain Discipline'),
('Offensive', 'Attack Speed', '1', '+0.2%', '50 (cap +10%)', 'All Offensive stats capped at 50 points each'),
('Offensive', 'Cooldown Reduction', '1', '+0.2%', '50 (cap +10%)', 'All Offensive stats capped at 50 points each'),
('Offensive', 'Critical Hit Chance', '1', '+0.2%', '50 (cap +10%)', 'All Offensive stats capped at 50 points each'),
('Offensive', 'Critical Hit Damage', '1', '+1%', '50 (cap +50%)', 'All Offensive stats capped at 50 points each'),
('Defensive', 'Armor %', '1', '+0.5%', '50 (cap +25%)', 'All Defensive stats capped at 50 points each'),
('Defensive', 'Life %', '1', '+0.5%', '50 (cap +25%)', 'All Defensive stats capped at 50 points each'),
('Defensive', 'All Resistances', '1', '+5', '50 (cap +250)', 'All Defensive stats capped at 50 points each'),
('Defensive', 'Life Regeneration', '1', '+214.6 Life/sec (level 70 values)', '50 (cap +10,730 Life/sec)', 'Values scale with character level; in classic Diablo III these values are divided by 4'),
('Utility', 'Area Damage', '1', '+1%', '50 (cap +50%)', 'All Utility stats capped at 50 points each'),
('Utility', 'Resource Cost Reduction', '1', '+0.2%', '50 (cap +10%)', 'All Utility stats capped at 50 points each'),
('Utility', 'Life per Hit', '1', '+160.9 (level 70 values)', '50 (cap +8,045)', 'Values scale with character level; classic D3 values divided by 4'),
('Utility', 'Gold Pickup Range', '1', '+0.1 yards', '50 (cap +5 yards)', 'Before patch 2.6.10 this stat was Gold Find (+1% per point, cap +50%)'),
('System', 'Point allocation', '1 per paragon level', 'Points cycle by category: 1st to Core, 2nd to Offensive, 3rd to Defensive, 4th to Utility, then repeats; after Paragon 800 the Offensive/Defensive/Utility trees are maxed so all further points go to Core', 'Core: Main Stat and Vitality uncapped, Movement Speed 50, Max Resource 50; Offense/Defense/Utility: every stat 50', 'No paragon level cap; 1 point earned each level-up past level 70; reset free anytime out of combat (Shift=10, Ctrl=100 points since 2.5.0)'),
('System', 'XP required per paragon level (levels 1–800)', 'see paragon_xp.csv', 'linear 7,200,000 + 1,440,000×(L−1) through L50; table beyond', '800 (table); uncapped level', 'Per-level XP in paragon_xp.csv, derived from maxroll paragon calculator cumulative array — https://maxroll.gg/d3/paragon-calculator');
