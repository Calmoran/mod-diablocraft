Verified D3 reference tables (RoS 2.7.x). Source of truth for generated SQL. Do not hand-edit generated/.

## warpath.eu Greater Rift monster data (diablocraft-au7g, 2026-10-07)

Three files below come from **warpath.eu** (silec / Basti), pinned to **patch 2.6.10.71510, 21 Nov 2020**
(its `index.html` changelog). The site was recorded unreachable on 2026-10-06 and answers again on
2026-10-07; `http://warpath.eu/mp.html` renders `http://warpath.eu/warpath.json`, which is what these
files hold. No generator reads them yet — they are reference data.

- `gr_monster_progress.csv` — every monster that appears in Greater Rifts, as warpath lists it
  (197 rows). Columns: `name, progress_points, progress_pct, avg_hp_multiplier, monster_type,
  damage_types, movable_by_abilities, monster_sets, source_url, patch`.
  - `progress_pct` = `progress_points / 650 × 100`, 4 decimals. 650 points = 100% of the bar
    (warpath's FAQ: "Dividing the monster's point value by 650 ... will give you the progression in
    percent"). The site itself shows this rounded to 2 decimals.
  - `monster_sets` = the set numbers of `gr_monster_sets.csv` (`; `-separated); `none` where a monster
    is in no set at all: the map-tied Hell Bringer, Shock Tower and Bloated Corpse, plus Voracious
    Torso (a spawn) and the `Progression Orb` pseudo-row.
  - A blank cell means the site has no value. Only `avg_hp_multiplier` (the orb), `monster_type` and
    `damage_types` (the orb, Dark Vessel) and `movable_by_abilities` (the orb) are ever blank.
  - The last row, `Progression Orb` (7.5 points = 1.1538%), is the progress orb, not a monster: keep
    it so the table is the site's table; it is the 1.15% of `greater_rifts.csv:rift_progress_elite_orbs`.
  - Elites, champions, minions and monsters they spawn are not in the table (warpath's FAQ): they
    award their normal monster's points plus progression orbs, which is why `elite_affix_*` data is
    separate.
- `gr_monster_sets.csv` — the 33 Greater Rift monster sets: `set_number, monster_names, source_url`.
  `monster_names` is `; `-joined in `warpath.json` order, which is alphabetical; sets hold 6–19
  monsters. Each rift floor gets one of the 33 sets (warpath's FAQ: "Yes, the monsters are preset in
  their Monster Sets. Each floor you will get 1 out of the 33 different Monster Sets"). The set
  numbers in `mp.html`'s "Jump to" dropdown list only three names per set and are stale against
  `ms.html`'s own tables; the tables win.
- `monster_roster.csv` gained a `warpath_name` column: the warpath monster each of our 65 roster
  monsters matches, or `none`. 44 are exact-name matches, 9 use warpath's label for the same monster
  (Walking Corpse→Hungry Corpse, Skeletal Warrior→Skeleton, Hungry/Scavenging/Tormented/Feasting
  Ghoul→Ghoul, Savage→Savage Beast, Morlu Caster→Morlu Incinerator, Succubus→Vile Temptress — each
  backed by the roster's own cited source, quotes in `docs/test-diablocraft-au7g.md`), and 12 are
  `none`: Decaying Cryptstalker, Night Clan Shaman, Ice Clan Brawler, Fallen Lunatic, Dune Thresher,
  Plague Swarm, Dune Wasp, Lacuni Warrior, Bogan Beast, Bogan Darter, Shade, Spectral Warrior
  (as of that check; on 2026-10-08 five were renamed, see below).
  **One `life_multiplier` cell was filled**, Walking Corpse: fandom says "Hungry Corpses (a.k.a.
  Walking Corpses)" and `Walking_Corpse` redirects there, so warpath's Hungry Corpse 1.5 for it is
  now in the row, with warpath added to its `source_url`. The other 8 NOT PUBLISHED rows stay NB:
  warpath lists no monster by those names or by anything its own changelog does not call removed from
  Greater Rifts (Fallen Lunatic and Lacuni Warrior are in that 47-monster removal list).

How the copies were checked against the live site, the exact supporting text, and the cross-check
against the ten maxroll example percentages already in `greater_rifts.csv`:
`docs/test-diablocraft-au7g.md`. The generator for all three files (and its asserts):
`azerothcore-wotlk/build/_agent-scratch/warpath-2026-10-07/make_gr_csv.py`.


- 2026-10-08 roster renames (the designer, card q-1007-07; diablocraft-ibrp): Night Clan Shaman → Moon Clan Shaman,
  Ice Clan Brawler → Ice Clan Warrior, Bogan Beast → Tusked Bogan, Dune Wasp → Sand Wasp, Shade → Shade
  Stalker, in `monster_roster.csv`, `monster_families.csv` and `monster_family_models.csv`. Each keeps its
  9500xx entry (the roster place) and its model pick. `warpath_name` of the five is still `none` (not
  re-matched here). `import_monster_picks.py` maps the five old slugs to the new ones (`RENAMED_SLUGS`).

- 2026-10-08 roster rename (the designer, card q-1008-01; diablocraft-yqlv): Plague Swarm → Stinging Swarm, in `monster_roster.csv`,
  `monster_families.csv`, `monster_family_models.csv`, `monster_abilities.csv` and the `family_damage_stinging_swarm` tunable. It keeps
  its 950039 entry and the designer's pick (bees 14894, size 0.2); `RENAMED_SLUGS` maps the old `plague-swarm` slug. Its `warpath_name` is
  now `Stinging Swarm` (warpath has that row: 0.56 progress, Life 1.05, the roster's own 1.05).

- 2026-10-12 bounty caches (bounties W4, diablocraft-dm9vg.4): `bounty_caches.csv` is one Horadric Cache item per
  column (an act), with its act reagent; `bounty_cache_legendaries.csv` is each column's act-only legendary pool
  (decisions 4006a91d, maxroll bounties section 5), only items Torment has (each row's `item_entry` must be a base
  item of `base_item_ids.csv`, which `generate_bounties.py` checks). **A column with no pool rows rolls no
  legendaries**: its cache still opens into everything else. The amounts are the rifts tunables `bounty_cache_*`.
  **An item in this sheet drops nowhere else** (diablocraft-dm9vg.8, ruling 2026-10-12): the loot loader keeps it out of
  every drop pool and `generate_slot_vendors.py` keeps it off the slot vendors.
