# The Wizard's code

The Wizard rides the shared combat engine: a skill is a spell record plus the numbers of its sheet
(`data/d3/wizard_skill_values.csv`), and the engine casts, costs, hits and ticks it. The code in this folder
is what a record and a number cannot say: when, where, on whom.

`dc_wizard.cpp` is the dispatch (`Begin`, `Cast`, `Delayed`, `Landed`, `Incoming` and the registration order).
`dc_wizard.h` declares what the engine calls; each function is defined in the file of the skill or family it
belongs to. `dc_wizard_internal.h` and `dc_wizard_helpers.cpp` hold what the files share: the state kept per
player and its lock, the sheet and catalogue lookups, and the controls (freeze, stun, slow, chill, shield).

| File | What it holds |
|------|---------------|
| `dc_wizard_arcane_orb` | Scorch's wall of fire |
| `dc_wizard_arcane_torrent` | Arcane Mines' tick, and the channel's share of its own time |
| `dc_wizard_archon` | Archon form: the bar, the transformation, the abilities' term and element |
| `dc_wizard_armors` | Energy, Ice and Storm Armor: what they answer to a hit, Force Armor, Chilling Aura, the ticks |
| `dc_wizard_black_hole` | the pull, Blazar, the Spellsteal and Absolute Zero stacks |
| `dc_wizard_energy_twister` | the twister's wander forward (its path in `dc_twister_math.h`), Storm Chaser's charges |
| `dc_wizard_explosive_blast` | the fuse and Chain Reaction |
| `dc_wizard_familiar` | the companion, its attack on a cast, Ancient Guardian |
| `dc_wizard_frost_nova` | the freeze and its marks, Frozen Mist, Shatter |
| `dc_wizard_hydra` | the totem's mind |
| `dc_wizard_magic_missile` | Conflagrate's burn |
| `dc_wizard_magic_weapon` | Conduit, Deflection, Ignite |
| `dc_wizard_meteor` | the fall, Meteor Shower, Star Pact |
| `dc_wizard_mirror_image` | the Images, and the copy of a killed one |
| `dc_wizard_next_spell_bonus` | Arcane Attunement and Spark: the bonus the next Arcane or Lightning spell takes |
| `dc_wizard_slow_time` | the bubble, the bubble that follows the Wizard, its aura script |
| `dc_wizard_spectral_blade` | Barrier Blades, Flame Blades, Ice Blades |
| `dc_wizard_teleport` | the landing's facing, Reversal, Wormhole, Safe Passage, Calamity |
| `dc_wizard_passives` | the passives that need code: Arcane Dynamo, Illusionist, Unstable Anomaly, Galvanizing Ward, Evocation, Dominance, Elemental Exposure |
| `dc_wizard_formula` | the terms the Wizard adds to the damage formula |
| `dc_wizard_buffs` | the buffs the Wizard wears and their contributions to the sheet |
| `dc_wizard_auras` | the aura script of the buff records |
| `dc_wizard_upkeep` | the timers, the refresh, the kill hook, logout and map change, the tuning read at startup |

## Skills with no file of their own

A skill that is a spell shell and sheet numbers has no file: the engine runs it from its row.

- Shock Pulse, Electrocute: no code.
- Ray of Frost, Disintegrate: the engine's channel pays and ticks them from the sheet; Arcane Torrent has the file above only for Arcane Mines.
- Blizzard: Frozen Solid's one freeze is a few lines of `Cast` in `dc_wizard.cpp`; the ground damage runs on the engine's persistent area aura.
- Diamond Skin: Sleek Shell's speed is a line of `dc_wizard_buffs.cpp` and Diamond Shards' blast a line of `dc_wizard_auras.cpp`.
- Wave of Force: Debilitating Force is a line of `Landed` in `dc_wizard.cpp`; Arcane Attunement is in `dc_wizard_next_spell_bonus`.
