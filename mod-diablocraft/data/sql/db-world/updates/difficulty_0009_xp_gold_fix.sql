-- Correct XP/gold column inversion for Torment VII-XVI; applied 0001 remains immutable.
UPDATE dc_difficulty_tiers SET xp_bonus_pct=1850, gold_bonus_pct=1900 WHERE tier='Torment VII';
UPDATE dc_difficulty_tiers SET xp_bonus_pct=2150, gold_bonus_pct=2425 WHERE tier='Torment VIII';
UPDATE dc_difficulty_tiers SET xp_bonus_pct=2500, gold_bonus_pct=3100 WHERE tier='Torment IX';
UPDATE dc_difficulty_tiers SET xp_bonus_pct=2900, gold_bonus_pct=4000 WHERE tier='Torment X';
UPDATE dc_difficulty_tiers SET xp_bonus_pct=3350, gold_bonus_pct=5000 WHERE tier='Torment XI';
UPDATE dc_difficulty_tiers SET xp_bonus_pct=3900, gold_bonus_pct=6400 WHERE tier='Torment XII';
UPDATE dc_difficulty_tiers SET xp_bonus_pct=4500, gold_bonus_pct=8200 WHERE tier='Torment XIII';
UPDATE dc_difficulty_tiers SET xp_bonus_pct=5200, gold_bonus_pct=10500 WHERE tier='Torment XIV';
UPDATE dc_difficulty_tiers SET xp_bonus_pct=6050, gold_bonus_pct=13400 WHERE tier='Torment XV';
UPDATE dc_difficulty_tiers SET xp_bonus_pct=7000, gold_bonus_pct=17000 WHERE tier='Torment XVI';
