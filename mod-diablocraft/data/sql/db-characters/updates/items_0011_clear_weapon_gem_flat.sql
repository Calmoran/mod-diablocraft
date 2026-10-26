-- One-time clear of the saved weapon-gem flat damage (the designer, q-1016-19). Before the weapon-gem fix a socketed
-- weapon Ruby's "+X Damage" reached the swing twice: through the weapon's own per-item cache and through a
-- Source::Gems WeaponFlatDamage contribution on the stat sheet. The fix stopped writing the second, but a character
-- saved before it keeps that contribution in dc_character_stats.contributions, and Load restores it (only Paragon
-- and Temporary are dropped there), so its swing stays doubled.
--
-- After the fix nothing writes a Source::Gems WeaponFlatDamage (or WeaponFlatDamageDelta) contribution: the
-- weapon gem goes to the per-item cache only, which OnPlayerLogin clears and rebuilds from the socketed gems, and
-- the legendary gems' powers write other stats. Every such saved contribution is the doubled half, so this drops
-- exactly those and nothing else; the gem's single value comes back from the cache at the next login.
--
-- contributions is Serialize's "1 <count>" followed by six tokens per contribution: source stat id value bucket
-- element. Source::Gems is 2, Stat::WeaponFlatDamage 27, Stat::WeaponFlatDamageDelta 37 (dc_common.h). The kept
-- tokens are copied unchanged, the count is rewritten, and the sheet column is left alone: Load recomputes the
-- sheet from the contributions. A row with no such contribution is not touched, so a rerun changes nothing.
SET SESSION group_concat_max_len = 1073741824;

UPDATE `dc_character_stats` AS s
JOIN (
    WITH tokens AS (
        SELECT c.guid, t.n, t.token
        FROM `dc_character_stats` AS c,
             JSON_TABLE(CONCAT('["', REPLACE(c.contributions, ' ', '","'), '"]'), '$[*]'
                        COLUMNS (n FOR ORDINALITY, token VARCHAR(64) PATH '$')) AS t
        WHERE c.contributions LIKE '1 %'
    ),
    entries AS (
        SELECT guid, n, token, (n - 3) DIV 6 AS k FROM tokens WHERE n >= 3
    ),
    dropped AS (
        SELECT guid, k FROM entries
        GROUP BY guid, k
        HAVING MAX(CASE WHEN (n - 3) MOD 6 = 0 THEN token END) = '2'
           AND MAX(CASE WHEN (n - 3) MOD 6 = 1 THEN token END) IN ('27', '37')
    )
    SELECT a.guid,
           CONCAT('1 ', COUNT(e.n) DIV 6,
                  IF(COUNT(e.n) > 0, CONCAT(' ', GROUP_CONCAT(e.token ORDER BY e.n SEPARATOR ' ')), '')) AS kept
    FROM (SELECT DISTINCT guid FROM dropped) AS a
    LEFT JOIN entries AS e
           ON e.guid = a.guid AND NOT EXISTS (SELECT 1 FROM dropped AS d WHERE d.guid = e.guid AND d.k = e.k)
    GROUP BY a.guid
) AS r ON r.guid = s.guid
SET s.contributions = r.kept;
