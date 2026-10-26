# Item.dbc — Diablocraft items

The 3.3.5a client resolves an item's bag icon and its equip slot from its own
Item.dbc, not from the server's item query response. Stock Item.dbc ends at entry
56806 and every Diablocraft item is 100000 or above, so before client patch 11
every one of them showed a "?" icon and could not be right-clicked to equip
(dragging to the slot still worked, because that path is validated server-side).
The server needs no rows: `ObjectMgr::LoadItemTemplates` stores the template
before it looks the entry up in Item.dbc, so a miss only skips the optional
DBC-attribute cross-check.

```text
python client-patch/dbc/build_item.py --mysql mysql --defaults-file azerothcore-wotlk/build/mysql/client.cnf
```

Append-only: it starts from the stock file (the server's `Item.dbc.stock` backup
when one exists) and skips any entry already present, so rerunning cannot double
a row. Every field — class, subclass, SoundOverrideSubclass, Material, displayid,
InventoryType, sheath — is read from `item_template`, which generate_sql.py built
from the CSVs. Client patch 11 adds 1173 rows (entries 57575–103049) to the 46096
stock ones. See docs/test-item-icons.md.
The 21 legendary gem items (103100-103120, from `legendary_gems_0002_items.sql`) were appended afterwards
(diablocraft-0189), from the dev world database, which holds them before an update applies the migration: run with
`--source client-patch/dbc/Item.dbc --database torment_devrealm_world` so only missing entries are added. See
docs/test-legendary-gem-item-dbc.md.
The 27 set caches (101114-101140, from `set_caches_0001.sql`) were appended the same way (diablocraft-ywkp, Kadala Part 9);
the six Monk caches (101146-101151) followed from `set_caches_0002.sql` (diablocraft-wna0c), the six Necromancer caches
(101158-101163) from `set_caches_0004.sql` (diablocraft-ngybv) and the six Crusader caches (101152-101157) from
`set_caches_0005.sql` (diablocraft-jfd7p, which re-renders 0004's 39 with them) the six Demon Hunter caches (101164-101169) from
`set_caches_0006.sql` (diablocraft-vawmy.4, which re-renders 0005's 45 with them) and the six Witch Doctor caches (101170-101175) from
`set_caches_0007.sql` (diablocraft-jjug3, which re-renders 0006's 51 with them), which is why `APPEND_SQL` names 0007:
`python3 client-patch/dbc/build_item.py --append-sql` reads the migrations in `APPEND_SQL`, no database; a rerun adds nothing.
`--from-sql` also sets sheath from `items_0022_item_sheath.sql` (diablocraft-pru6e, after b3gs1): the 490 weapons and
off-hands take the server's value, every other row of ours 0; `mod-diablocraft/scripts/tests/items/test_item_sheath_client.py` checks it.
The 71 gem items (50 stat gems 103000-103049, 21 legendary 103100-103120) wear their own icons since diablocraft-fpo9l:
`mod-diablocraft/scripts/generate/legendaries/generate_gem_icons.py` sets their displayid here and in its migration from `data/gem_icons.csv`, after
`build_item.py` placed the rows (see ItemDisplayInfo.dbc below).
Bottomless Potion of Regeneration (102200) wears its own icon since diablocraft-71scy: `generate_potion_icons.py` sets its
displayid the same way from `data/potion_icons.csv`, over the 24152 `build_item.py` appends. Since diablocraft-0knhj the same
generator writes every Bottomless potion's row (102200-102210), appending the ten `build_item.py` does not know.

# ItemDisplayInfo.dbc — the gem icons

Displays 90100-90120 (legendary gems) and 90200-90249 (stat gems), one per gem item, InventoryIcon only, no model: the icon is
`Interface\Icons\DC_Gem_<gem_id>` or `DC_Gem_<Colour>_<Tier>`, the designer's art from `client-patch/source/gems/` (its script's docstring
says how to re-render). Ours are replaced where they sit, so a rerun is byte-identical:

```text
python3 client-patch/source/gems/draw_gem_icons.py      # png/ -> art/Interface/Icons/*.blp (--crop re-cuts the designer's sheets)
python3 mod-diablocraft/scripts/generate/legendaries/generate_gem_icons.py   # gem_icons.csv -> Item.dbc, ItemDisplayInfo.dbc, legendary_gems_0005_gem_icons.sql
python3 mod-diablocraft/scripts/tests/legendaries/test_gem_icons.py
```

Displays 90300-90310 are the eleven potions' (diablocraft-71scy, diablocraft-0knhj): `Interface\Icons\DC_Potion_<d3_id>` from `legendary_potions.csv`'s icon column,
The designer's art from `client-patch/source/potions/` (all 11 Bottomless potions and `DC_Potion_HealthPotion` are drawn; every Bottomless potion is an item):

```text
python3 client-patch/source/potions/draw_potion_icons.py   # png/ -> art/Interface/Icons/*.blp (--crop re-cuts the designer's sheets)
python3 mod-diablocraft/scripts/generate/items/generate_potion_icons.py   # potion_icons.csv -> Item.dbc, ItemDisplayInfo.dbc, items_0027_bottomless_potions.sql
python3 mod-diablocraft/scripts/tests/items/test_potion_icons.py
```

# CurrencyTypes.dbc — Diablocraft currencies

The append-only writer preserves all 26 stock records and adds fourteen currencies.
Run from the repo root:

```text
python client-patch/dbc/build_currencytypes.py
python client-patch/dbc/test_currencytypes.py
```

The source defaults to the server's CurrencyTypes.dbc.stock backup. A patched
input is refused if any requested item, row ID or bit index collides.

| Currency | Row ID | Item entry | Category | BitIndex |
|---|---|---|---|---|
| Death's Breath | 1000 | 102000 | 1 | 30 |
| Reusable Parts | 1001 | 102001 | 1 | 31 |
| Arcane Dust | 1002 | 102002 | 1 | 32 |
| Veiled Crystal | 1003 | 102003 | 1 | 33 |
| Forgotten Soul | 1004 | 102004 | 1 | 34 |
| Greater Rift Keystone | 1005 | 102005 | 1 | 35 |
| Gold Bar | 1006 | 102006 | 1 | 36 |
| Blood Shard | 1007 | 102007 | 1 | 37 |
| Khanduran Rune | 1008 | 102008 | 1 | 38 |
| Caldeum Nightshade | 1009 | 102009 | 1 | 39 |
| Arreat War Tapestry | 1010 | 102010 | 1 | 40 |
| Corrupted Angel Flesh | 1011 | 102011 | 1 | 41 |
| Westmarch Holy Water | 1012 | 102012 | 1 | 42 |
| Primordial Ashes | 1013 | 102013 | 1 | 43 |

Category 1 is Miscellaneous, flags 0, in the stock CurrencyCategory.dbc.
Category 3 is Unused, flags 3. The old writer incorrectly described 3 as
Miscellaneous; client patch 9 corrects it. BitIndex 44–64 remain available.
The native known-currency field uses bit BitIndex−1; the module marks held
currencies known on grant/login. Currency items use BagFamily 8192.

The Blood Shard row (kadala.md 3.4) only keeps item 102007 a valid currency at load; the account ledger holds
the count and the stock Currency tab never lists it. The five act reagents (1008-1012, bounties W3, diablocraft-dm9vg.3) are the
same: ledger materials whose rows keep their items valid currencies; their Item.dbc rows come from
`account_economy_0004_act_reagents.sql` through `build_item.py --append-sql`. Primordial Ashes (1013, Kanai's Cube 1,
diablocraft-wpt7l.1) are one more, its Item.dbc row from `account_economy_0005_primordial_ashes.sql`.

# ItemExtendedCost.dbc — Kadala's prices

The vendor window draws an item's price only from this file, and the client reads the patch's copy INSTEAD of
its own, so `build_itemextendedcost.py` keeps all 972 stock rows (ids up to 2997) and appends the rows
`kadala_0001_vendor.sql` inserts into `itemextendedcost_dbc` (3000-3003: 25, 50, 75 and 100 Blood Shards,
item 102007): the price shown and the price charged are one row. A row id already in the source is refused.

```text
python client-patch/dbc/build_itemextendedcost.py
python client-patch/dbc/build_item.py --append-sql      # Item.dbc rows: the Blood Shard 102007 and Mystery 102300-102316
python3 mod-diablocraft/scripts/tests/items/test_kadala_client_rows.py
```

`--append-sql` reads the migrations' `item_template` inserts (the Blood Shard's and Kadala's) with no database;
rerunning adds nothing. Item.dbc 47327 -> 47345 records.

# SpellDescriptionVariables.dbc — the exact values a sentence prints

Seven kinds of number have no field on a spell record to live in - a radius the
stock `SpellRadius.dbc` cannot express, an internal cooldown, a per-trigger
resource amount, a charge cost - and WoW's own answer for those is a
description variable: the record points at a row here with
`SpellDescriptionVariableID`, the row names values, and the sentence renders
`$<name>` (mapping report decision 3, approved 2026-09-20). The server ignores
the file entirely - `SpellEntry` at the core pin comments out both
`Description[16]` and `SpellDescriptionVariableID` as "not used" - and reads
the same numbers from `dc_spell_values`, so this is purely what the client
prints.

`mod-diablocraft/scripts/generate/classes/generate_spells.py` writes it as part of a normal run;
there is no separate build script. Spell rewrite step 7 ships it in the MPQ for
the first time, and that is why the writer now preserves the stock rows: the
client reads the highest-numbered patch's copy INSTEAD of its own, so a file
holding only ours would take the description variables off every Blizzard spell
that uses one. All 30 stock rows (ids 1-181) are kept byte for byte, ours start
at 81000, and a collision between the two is a hard error.
`test_spell_records.py` checks all of it: every stock row present and unchanged,
none invented, every row of ours matching the sentence that renders it, and no
record pointing at a row of ours that renders nothing.

**Step 7 also drops two lines from the sentences.** The 3.3.5 client builds a
cost line from `ManaCost` with `PowerType` and a cooldown line from
`RecoveryTime` with the category timer, and steps 5 and 6 put both in the
record, so seventeen `Cost:` and `Cooldown:` label lines that would now be
printed twice are gone from `Description_Lang_enUS`. Whirlwind keeps its cost
line, because the module still pays it tick by tick and the record has no
`ManaCost` for the client to print; so do the two skills whose cost is a
charge, which no field holds.

**The two files in this archive have to match each other; the server does not
come into it.** Our variables rows are numbered by position, so dropping a row
renumbers the ones after it - the step 7 run moved 33 records'
`SpellDescriptionVariableID`. That pairing is entirely client-side:
`Spell.dbc` gives a spell its id and `SpellDescriptionVariables.dbc` gives the
id its text, both out of `patch-4.MPQ`, and one generator run writes both, so
replacing the archive replaces them together. The server is not in that path -
3.3.5 has no spell query, and the core loads neither column - so the records
migration is bookkeeping and need not land in the same window. Bump
`client_patch` in VERSION and rebuild whenever the archive changes, and close
the game before replacing it or the old file stays in use.

# SpellCategory.dbc — Diablocraft cooldown categories

Spell rewrite step 6 put the Barbarian cooldowns in the spell record and made a
base skill and its five runes share one timer through the record's `Category`
plus `CategoryRecoveryTime`, which is how the core groups a cooldown. An id in
that field is not enough on its own: `SpellInfo`'s constructor resolves it with
`sSpellCategoryStore.LookupEntry` (SpellInfo.cpp:789 at the core pin) and
`GetCategory()` returns 0 when the lookup misses (SpellInfo.cpp:882), so an id
with no SpellCategory.dbc row is no category at all and
`Player::AddSpellAndCategoryCooldowns` never reaches its sibling branch.

`mod-diablocraft/scripts/generate/classes/generate_spells.py` writes the file as part of a normal
run — there is no separate build script. It preserves all 262 stock rows and
adds one row per skill that has a shared timer, Flags 0, from the reserved block
8100–8199; today that is 11 rows, 8100–8110, for a 273-record file. The skill to
category map is persisted in
`mod-diablocraft/data/generated/spell_cooldown_categories.csv` and is append-only
in the same sense as `spell_helper_ids.csv`: a skill keeps the category it has,
so a rerun cannot move a live cooldown group onto other spells. Rows already in
the reserved block are replaced rather than appended, so running over an
already-patched file cannot double a row.

Flags 0 is deliberate. The stock values are 1, 2 and 4, and 2 is
`SPELL_CATEGORY_FLAG_COOLDOWN_STARTS_ON_EVENT`, which
`SpellInfo::IsCooldownStartedOnEvent` reads (SpellInfo.cpp:1246); ours start
when the spell is cast.

```text
python3 mod-diablocraft/scripts/tests/classes/test_spell_categories.py
python3 mod-diablocraft/scripts/tests/classes/test_spell_records.py
```

The first loads this file through the core's own `DBCStorage`/`DBCFileLoader`,
extracted from the pin, and proves two runes of one skill share a cooldown
through `AddSpellAndCategoryCooldowns` itself. The second checks the artifact:
every category the records use has a row, every stock row survives, and the
persisted map agrees with the records.

**The server needs no copy of this file** (Architect, 2026-09-20, superseding
the earlier DataDir-copy instruction): `DBCStores.cpp:357` loads
SpellCategory.dbc and then overlays the stock `spellcategory_dbc` world table
on top of it, and the writer puts the same eleven rows in the step 6 migration.
This file is the client's, and ships in the MPQ with the other DBCs here.
Whether the 3.3.5 client needs the row for its own cooldown display is not
verified and is one of the client-run checks in `docs/archive/tests/test-spell-records.md`.
The full step 6 order is `docs/archive/deploy/deploy-spell-rewrite-step6.md`.

Build with `bash client-patch/build.sh` on the build host and copy the resulting
`client-patch/patch-4.MPQ` into the client's `WoW Client/Data/` while the game is
closed; the full sequence is the Client patch bullet in AGENTS.md. Copy
CurrencyTypes.dbc to the server DataDir/dbc while the server is stopped. Bump
client_patch in VERSION when shipping DBC changes.

Version 8's Gold Bar row and all four DBCs were verified in the installed MPQ.
Version 9 is installed and all four DBCs were extracted and verified against
their sources. The owner confirmed crafting materials now appear in the native
Currency tab; see docs/archive/test-crafting.md. No item balances or known bits were reset.

# ChrClasses.dbc — each class's shown power

`ChrClasses.DisplayPower` is the power the client shows for a class and the
power the core gives it at creation and after every form update. The class
resource registry puts each class's primary resource in a slot (decisions.md
2026-09-23, Q1=1A), and `mod-diablocraft/scripts/generate/classes/generate_class_resources.py`
writes the stock file with DisplayPower set to that slot, together with the same
rows as a server `chrclasses_dbc` overlay (`world_0019_class_display_power.sql`).
Only the DisplayPower field of a stock row is changed. Today: Mage (Wizard)
0 Mana → 3 Energy (`diablocraft-resource-rollout-a`).

`ChrClasses.Name_Lang_enUS` is the second field the generator changes: a live
class takes its D3 name, Warrior → Barbarian and Mage → Wizard. The client
draws a class name from this table (character select and create, the "Classes:"
line on an item, who, guild, friends, chat, target and party frames, the
character sheet; `LOCALIZED_CLASS_NAMES_MALE/FEMALE` are filled from it by the
client, so FrameXML needs no override). The server overlay for both classes is
`world_0027_class_names.sql` (the full row with DisplayPower, because the overlay
replaces the row; `world_0019` stays as it was applied). Only enUS is renamed.
(`diablocraft-race-class-unlock`)

`ChrClasses.SpellClassSet` is the class's spell family. The client applies a spell modifier (`SMSG_SET_FLAT/PCT_SPELL_MODIFIER`,
an aura such as Epiphany's `SPELLMOD_RANGE`) only to a spell whose `SpellClassSet` is the player class's, so a created class's client
row takes its records' family (`generate_class_creation.py`, from `generate_spells.py` `CLASS_BLOCKS`: the Monk 22), while its
server row keeps the parent's (4): the core never reads it, and `dc_classes.cpp` `ClassSpellFamily` strips the parent's stock spells
by it (`diablocraft-12nrw`). The Barbarian's (20) and Wizard's (21) records sit under the stock Warrior (4) and Mage (3) rows the
same way, so the client applies none of their modifiers (the cost ones, op 14, the cooldown ones, op 11, Inspiring Presence's
duration, Archon's); the server does. Those two rows are unchanged here: moving them is its own decision.

# CharBaseInfo.dbc — the playable classes for every race

The client lists a race's classes from this table and draws a class with no row for the race disabled (greyed,
darkened, not clickable, tooltip "You must choose a different race to be this class."). `build_charbaseinfo.py` writes
only the Barbarian (1) and Wizard (8) for each of the ten races: 20 rows, so the stock create screen locks the other
eight without any GlueXML edit (the client signature-checks GlueXML; Nightly 52 broke login with one, see
`client-patch/parked/README.md`). The server does not read this table; it refuses a pair with no `playercreateinfo` row,
which `world_0028_race_class_pairs.sql` adds for the four Wizards stock lacks (Orc, Dwarf, Night Elf, Tauren), and
`dc_world.cpp` refuses the eight other classes. `mod-diablocraft/scripts/tests/classes/test_race_class_unlock.py` pins the table
against that gate.

# Map, WorldMapArea, Light, AreaTable, DungeonMap, DungeonMapChunk — the Sanctum of Torment (map 750)

Yogg-Saron's arena as an open map under a new id: a copy of Ulduar (map 603) with nothing native on it (research
`docs/research/ulduar-yogg-hub.md` sections 5 and 8; `diablocraft-ugfc`). `mod-diablocraft/scripts/generate/world/generate_hub_sanctum.py`
writes the six files and the server overlay `world_0030_sanctum_map.sql` in one run, from one sheet,
`mod-diablocraft/data/d3/world_sanctum_dbc.csv`: a row is a clone of `source_id` with the listed fields set, or a rename
when id and source are the same.

```text
python3 mod-diablocraft/scripts/generate/world/generate_hub_sanctum.py
python3 mod-diablocraft/scripts/tests/world/test_hub_sanctum.py
```

| File | Change | Why |
|---|---|---|
| `Map.dbc` | row 750 cloned from 603: directory `UlduarRaid`, instance type 0, name "Sanctum of Torment", loading screen 244 | the client reads the terrain by directory out of its own MPQs; type 0 is an open map; 244 is `InstanceUlduarRaid`, row 603's own (the brief's 142 is `InstanceDeadmines`) |
| `WorldMapArea.dbc` | row 750 cloned from 529 with map 750 | the world map (M); the internal name stays row 529's |
| `DungeonMap.dbc` | Ulduar's 5 floors (69-72, 98) cloned as 1000 + id with map 750 | the world map's floors: without them map 750 had no floor to draw (`diablocraft-bk308`) |
| `DungeonMapChunk.dbc` | Ulduar's 51 chunks cloned as 10000 + id with map 750, each pointing at the cloned floor | the client finds the floor you stand on by map and WMO group |
| `Light.dbc` | row 2750 cloned from 1862 with map 750 | Ulduar's default light; Light id 750 is already a stock row |
| `AreaTable.dbc` | area 4273 renamed "Sanctum of Torment" | WMOAreaTable has no map column, so the arena resolves to 4273 on any map; the real Ulduar shows the new name too |

Append-only like the writers above: it starts from the stock file (the server's extracted copy), keeps every stock row byte
for byte (the renamed row apart), refuses a new id that already holds a different row, and a rerun over its own output
changes nothing. Only the first light row of Ulduar is cloned (the brief's choice): the other 603 rows are zone-specific,
and a miss shows as the wrong sky, which is one of the live checks.

Once the open-world rift layer exists (below) the six files are the last layer's render: `generate_hub_sanctum.py` refuses
to run and `generate_open_rift_map.py` builds this layer first.

# Map, WorldMapArea, Light — the open-world rift map (map 751)

Kalimdor's terrain as a private party instance, the proof of concept of open-world rifts (`diablocraft-kw18`; research
`docs/research/open-world-rifts.md`). `mod-diablocraft/scripts/generate/rifts/generate_open_rift_map.py` builds a second layer over the
Sanctum's output from `mod-diablocraft/data/d3/world_open_rift_dbc.csv` and writes the server overlay
`world_0035_open_rift_map.sql` (`map_dbc` 751, `mapdifficulty_dbc` 7510, `instance_template` 751).

```text
python3 mod-diablocraft/scripts/generate/rifts/generate_open_rift_map.py
python3 mod-diablocraft/scripts/tests/rifts/test_open_rift_map.py
```

| File | Change | Why |
|---|---|---|
| `Map.dbc` | row 751 cloned from 1: directory `Kalimdor`, instance type 1, name "Kalimdor Rift", corpse map 1 at Un'Goro, four players | the client reads the continent's own terrain by directory; type 1 makes the core give each party its own copy |
| `WorldMapArea.dbc` | the 22 map-1 rows cloned with map 751 (ids 3000 + the original) | the world map (M); internal names stay the originals' |
| `Light.dbc` | the 127 map-1 rows cloned with map 751 (ids 5000 + the original) | the continent's own sky and fog |
| `WorldMapOverlay.dbc` | the 230 overlays of those 22 world maps cloned onto their clones (ids 3000 + the original, `MapAreaID` 3000 + the original's) | zone fog (`diablocraft-y0gjt`): the client lights an explored sub-area only through an overlay of the world map on screen; the server sets the bits and clears them for a new copy (`dc_open_rift.cpp`, `dc_zone_fog.h`) |

The server's map files are links of Kalimdor's 2,341 files under the id 751
(`python3 mod-diablocraft/scripts/link_map_clone.py --data <server data dir> --sheet mod-diablocraft/data/d3/world_open_rift_dbc.csv`,
dry run first, run by the PM; ids are three digits wide in the file names).

The server needs `map_dbc` (map 750) and `areatable_dbc` (the name `.gps` and the General channel print), and gets both
from the same run. It reads neither WorldMapArea nor Light for anything visible on map 750 (the core keys WorldMapArea by
area id for `.gps` and `.go zonexy`, and uses Light only as a map's default-light id for a script's light override), so
those two files are the client's alone and the server's own DBC files stay stock. The client files are coupled to the
migration (`applied_migrations.py`): once `world_0030` is applied, a changed sheet needs a new migration, not an edit.

## Map 752, the Eastern Kingdoms (`diablocraft-hyoic.6`)

The bounty acts' second copy (`docs/research/bounty-acts.md` 6), a third layer over map 751's: the generator's `LAYERS`
builds each sheet over the one before, writes one migration a layer and couples the client files to the last one. From
`mod-diablocraft/data/d3/world_open_rift_ek_dbc.csv`, overlay `world_0045_open_rift_ek_map.sql` (`map_dbc` 752,
`mapdifficulty_dbc` 7520, `instance_template` 752, parent 0).

| File | Change | Why |
|---|---|---|
| `Map.dbc` | row 752 cloned from 0: directory `Azeroth`, instance type 1, name "Eastern Kingdoms" (row 0's, ruling 2026-10-12: no new names), four players; the corpse fields stay row 0's (-1, no point yet) | as 751 |
| `WorldMapArea.dbc` | the 26 map-0 rows cloned with map 752 (ids 3000 + the original) | the world map (M) |
| `Light.dbc` | the 82 map-0 rows cloned with map 752 (ids 5000 + the original) | the continent's own sky and fog |

The server's map files: `python3 mod-diablocraft/scripts/link_map_clone.py --data <server data dir> --sheet
mod-diablocraft/data/d3/world_open_rift_ek_dbc.csv`, dry run first, run by the PM. `client-patch/build_map_bounds.py` is
rerun after this layer (MapBounds.lua gains the 752 rectangles).

## Map 753, Outland (`diablocraft-hyoic.9`)

The bounty acts' third copy, act 5, a fourth layer over 752's. From
`mod-diablocraft/data/d3/world_open_rift_outland_dbc.csv`, overlay `world_0046_open_rift_outland_map.sql` (`map_dbc` 753,
`mapdifficulty_dbc` 7530, `instance_template` 753, parent 530).

| File | Change | Why |
|---|---|---|
| `Map.dbc` | row 753 cloned from 530: directory `Expansion01`, instance type 1, name "Outland" (row 530's), four players; corpse map -1 where row 530 has 0 (a dungeon's corpse arrow would point at map 0), no point yet | as 752 |
| `WorldMapArea.dbc` | the 9 Outland rows of map 530 cloned with map 753 (ids 3000 + the original: 465-467, 473, 475, 477-479, 481); the 7 Quel'Thalas and Azuremyst rows of map 530 are left out, they are not Outland | the world map (M) |
| `Light.dbc` | the 176 map-530 rows cloned with map 753 (ids 5000 + the original) | Outland's own sky and fog |

Green lava: the server reads liquid type 2 on map 530 as green lava, a hardcoded id; core patch
`core-patches/0023-outland-copy-liquid.patch` gives 753 the same rule. The client has its own map-530 rule and may still
draw water on 753; that is a dev check. The server's map files: `link_map_clone.py --sheet
mod-diablocraft/data/d3/world_open_rift_outland_dbc.csv`, as 752, run by the PM; MapBounds.lua gains the 753 rectangles.

**Before `build.sh` in a worker worktree**: `client-patch/dbc/Spell.dbc` is gitignored and `worker_worktree.sh` copies it
once, when the worktree is made, so it goes stale as main regenerates it, and `build.sh` packs whatever copy is there.
Build into a scratch path first (`--output`), extract it and the committed `patch-4.MPQ` with `smpq -x`, and `diff -rq`:
only your task's files may differ (`diablocraft-ugfc` found a stale `Spell.dbc` that way).

# GameObjectDisplayInfo — Torment's own placeable world objects

What a gameobject looks like is its display row: a model path and a size box. Torment's own rows live above the stock
maximum 9624 (ours start at 9700), so a model that is in the client but has no display (the Azjol-Nerub stairs, `diablocraft-8jd5`)
becomes an object the designer can place, turn and scale. Two sheets, one row per asset in each, drive
`mod-diablocraft/scripts/generate/world/generate_world_objects.py`:

```text
python3 mod-diablocraft/scripts/generate/world/generate_world_objects.py
python3 mod-diablocraft/scripts/tests/world/test_world_objects.py
```

| Sheet | Row |
|---|---|
| `data/d3/world_object_displays.csv` | `display_id` (above 9624), `model_path`, `name`, the six size-box cells, `notes` |
| `data/d3/world_objects.csv` | `entry` (the 910090-910099 block), `display_id` (a row of the sheet above), `name`, `size`, `notes`: a type 5 (generic, decoration) template, nothing spawned |

**Adding the next asset is one command** (`diablocraft-jn9r`):

```text
python3 mod-diablocraft/scripts/add_world_object.py "<model path as Noggit shows it>" "<object name>" [--client-dir DIR] [--size 1]
python3 mod-diablocraft/scripts/tests/world/test_add_world_object.py
```

It looks the path up in the stock `GameObjectDisplayInfo` first (`.m2` or `.mdx`, either slash, any case) and then in our own
sheet, and **reuses a display it finds**: no display row, no client DBC change, no new `patch-4.MPQ` (the designer's
`World\Generic\PassiveDoodads\ParticleEmitters\AuraRed.m2` is stock display 264: one template, entry 910091). Otherwise it takes
the next free display id from 9700, reads the size box from the model's `.m2` header when `--client-dir` is a folder of
EXTRACTED files (not the client's MPQs) and writes zeros flagged PLACEHOLDER when it is not given, adds the template on the next
free entry of 910090-910099, checks the result with the generator on a temp copy (a refusal leaves both sheets untouched), and then
runs the generator. By hand it is one row in each sheet and `generate_world_objects.py`; a template's `display_id` may be a stock
id. After a NEW display row: `client-patch/build.sh` (build to a scratch
`--output` first and diff, see the Spell.dbc warning below), then bump `client_patch` in VERSION at the publish. The generator
writes `GameObjectDisplayInfo.dbc` (the stock file, every stock row byte for byte, plus ours), and the server overlay
migration (`gameobjectdisplayinfo_dbc` and `gameobject_template`; the core loads its binary DBC and then the table, as for
`map_dbc`). Once world_0036 is applied its file is frozen (`applied_migrations.py`): the next asset after that moves the generator's
`MIGRATION` to the next free `world_NNNN` name, and the new file re-renders every row (delete then insert, so a rerun is safe).

**Model path:** write it as the table stores it. All 3575 model rows of the stock table end `.mdx` (none `.m2`), and the 3.3.5
client reads an `.mdx` name as the `.m2` file beside it, so a row copies the stock form.

**Size box:** from the model's own bounds (header of the `.m2`). The VPS has no client MPQs, so a row can carry zeros as a
flagged placeholder; the server reads the box only for interaction distance (`GameObject::IsAtInteractDistance`), never for a
decoration, and stock rows 9491 and 9624 are zero too.

**Known limit, and what fixing it takes:** the server has no collision for the model, so monsters do not path over it and the
editor's floor snap ignores it. The core finds an object's collision in `vmaps/GameObjectModels`, a list keyed by model file
name (`LoadGameObjectModelList`, `GameObjectModel.cpp`), which `vmap4_extractor` builds from the client's own
`GameObjectDisplayInfo.dbc` and the models. Fixing it means running the vmap extractor and assembler over a client whose MPQ
chain holds `patch-4.MPQ` and the model, then putting the regenerated `vmaps/GameObjectModels` into each data folder (the PM,
as `link_map_clone.py` is). That needs the client's data on the VPS, which it does not have today. Walking up them is expected to work
anyway, because the client collides with the model it draws (test sheet check 2, not yet seen in game).


**`CreatureDisplayInfo.dbc`** (`diablocraft-ie3xd`): `python3 client-patch/dbc/build_creaturedisplayinfo.py` writes the stock table
(every row and the string block byte for byte, from the server's data dbc) plus Torment's own display rows from 33000 (the stock table
ends at 32754). Today one: Archon form's Algalon, the Archon rows of `mod-diablocraft/data/d3/wizard_archon_values.csv` (`display_id`'s
row at `form_display_id` with its display scale times `scale`). A size lives in the display row, never in a scale the server sends: the
client tweens an object-scale change, and loads a display at its own size. The server needs no copy. After a change: rerun it, then
`build.sh` to a scratch `--output` and diff as below.
