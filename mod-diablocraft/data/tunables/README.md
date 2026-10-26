The designer's numbers, one file per category (sixteen of them since 2026-09-19, when the Architect added `combat` for class-agnostic player combat numbers): the values that are ours rather than D3's, so each one has a row he can set instead of a literal in the code.
`data/d3/` stays D3's published reference data; a number D3 published belongs there, not here, and only reaches a row below as `d3_value` when the same row also needs the designer's override.
`scripts/generate_tunables.py` turns these files into `dc_tunables`, which the server reads through `DC::Tunables::Get` and the AIO Lua reads with `WorldDBQuery`; `.dc tunables reload` re-reads it without a restart.

Columns: `name,d3_value,value,unit,notes`.

- `name` — lower_snake_case, unique inside the file; the category is the file name, so no prefix.
- `d3_value` — what D3 published, blank when D3 published nothing. When it is filled, the `notes` column says where it came from.
- `value` — the designer's number, blank when he has not chosen one. It seeds `tuned_value` in the table.
- `unit` — yards, seconds, milliseconds, percent, count, multiplier, degrees, flag, damage, yards per second, degrees per second, gold, level, pixels.
- `notes` — the audit row or decision this came from. Required; it is what tells the designer what he is setting.

A negative number is allowed in either value column, and is not a deviation from the affix sheet: an offset can legitimately point the other way, and `dc_tunables.d3_value` / `tuned_value` are signed `DOUBLE` (Architect, 2026-09-19). Only a non-finite value is refused.

A row with both values blank is a parameter nobody has chosen a number for. `DC::Tunables::Get` returns 0 for it and logs once, so the code that reads it must be written for a value that is not there yet, exactly as the affix tunables are.

**The CSV wins on every apply** (ruling 2026-09-19). Regeneration is an upsert and never a drop, and it writes the sheet's numbers over whatever is in the table: `d3_value`, `unit`, `notes` and `tuned_value` all come from the CSV. A `value` left blank clears the row back to `d3_value`, which is how a number is un-tuned.

`.dc tunables set` is therefore a scratch override for the session you are testing in, and the command says so when you use it. It survives `.dc tunables reload`; it does not survive the next apply of `tunables_0001.sql`. To keep a number, put it in the CSV.

The loop this is built for:

1. edit the row in `data/tunables/<category>.csv` on a dev branch;
2. `python mod-diablocraft/scripts/generate_tunables.py`;
3. apply the current migration (`data/tunables/current_migration.txt` names it; once dev has applied it, the next run of the generator writes the next free number and records it there) to the dev world;
4. `.dc tunables reload` and play it — no restart, no rebuild;
5. keep it or change the number and go round again;
6. merge the CSV and the regenerated SQL together, and live picks it up on its next apply.

Same rule, same wording, for `elite_affix_parameters.csv` and `.dc affix set`.

## Files with their own table

Ten sheets in this folder are not category files and `generate_tunables.py`
walks past them by name. Each is the designer's numbers rather than D3's, which is why
the Architect moved the FILE here out of `data/d3/` on 2026-09-19 — but each
already had its own generator and its own runtime table before phase 2, so the
numbers themselves did NOT move into `dc_tunables`. Set them with the command
in the last column, not with `.dc tunables set`.
`class_resources.csv` is the exception to that history: it was written here new
(diablocraft-resource-registry, 2026-09-22) as the Torment half of the class
resource registry, beside the D3 half in `data/d3/class_resources.csv`.

| file | runtime table | generator | how the designer changes it |
|---|---|---|---|
| `ability_tunables.csv` | `dc_ability_tuning` | `generate_spells.py` | edit the CSV, rerun the generator, apply the SQL |
| `elite_affix_parameters.csv` | `dc_affix_tunables` | `generate_affix_tunables.py` | `.dc affix set <affix> <parameter> <value>`, or the CSV and a rerun |
| `loot_tuning.csv` | `dc_loot_tuning` | `generate_paragon.py`, `generate_rift_affixes.py`, `generate_jeweler.py`, `generate_crafting.py`, `generate_spells.py` | edit the CSV, rerun the generators, apply the SQL |
| `block.csv` | `dc_block_tuning` | `generate_block.py` | edit the CSV, rerun the generator, apply the SQL |
| `monster_targeting.csv` | `dc_monster_targeting` | `generate_monster_targeting.py` | edit the CSV, rerun the generator, apply the SQL |
| `rift_survey.csv` | none: the inputs of the offline survey of the rift dungeons (`value` blank = not set); the report's densities, cluster sizes, elite chance, solo share and entry clearance are the spawn sheets' (below) | `generate_rift_survey.py --survey` | edit the CSV, rerun `--survey`; the survey's sheets (`data/d3/rift_*.csv`) are the source after it |
| `monster_sets.csv`, `cluster_recipes.csv`, `monster_spawn.csv`, `area_defaults.csv` | `dc_monster_set` (+ `_member`, `_family`), `dc_cluster_recipe`, `dc_monster_spawn`, `dc_area_default`: the spawn sheets (monster-spawning.md §5), read by the spawner (S2, `src/rifts/dc_rift_spawner.cpp`, once per floor, read at startup). The knobs and orbs of the same plan are rows of `rifts.csv` (`elite_chance_pct`, `elite_packs_min/_max`, `elite_champion_pct`, `solo_share_pct`, `patrol_share_pct`, `cluster_radius_small_yards`, `entry_clear_yards`, `floor_body_cap`, `open_zone_*`, `gr_orb_*_count/_points`, `nr_orb_*`) | `generate_spawn_sheets.py` | edit the CSV, rerun the generator, apply the SQL. A set's `source` is `d3` for a seed and `alex` once edited; blank value rows in `rifts.csv` are placeholders the designer sets |
| `bags.csv` | the generated container templates | `generate_bags.py` | edit the CSV, rerun the generator, add the next numbered delta |
| `primary_mechanics.csv` | `dc_primary_data.h` (compiled, not a table) | `generate_spells.py` | edit the CSV, rerun the generator, rebuild |
| `ground_loot_parameters.csv` | the generated ground-loot rows | `generate_ground_loot.py` | edit the CSV, rerun the generator, apply the SQL |
| `class_resources.csv` | `dc_resource_data.h` (compiled, not a table) | `generate_class_resources.py` | edit the CSV, rerun the generator and `generate_spells.py`, rebuild |
| `monster_abilities.csv` | `dc_family_ability` | `generate_monster_models.py` | edit the CSV, rerun the generator, apply the SQL. A cell names its source: `game_data` and `roster` are published numbers, `donor` is the borrowed WoW spell's own cast time, range or recovery (`wow_spell` is that spell), `tunable` is a blank cell whose number is the blank PLACEHOLDER row `ability_<monster>_<ability>_<cell>` of `monsters.csv` (set it there; `.dc tunables set` moves it at run time), `n/a` has nothing to time. Its damage is `monsters.csv` `ability_damage_<kind>`, which `.dc tunables set` also moves at run time |

Folding all ten into `dc_tunables`, so there is one table and one `set` command,
is a later task. Nothing about how they behave today changed when they moved.
