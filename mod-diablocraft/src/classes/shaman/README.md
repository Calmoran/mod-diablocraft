# The Shaman's code

The Shaman rides the shared combat engine: a skill is a spell record plus the numbers of its sheet
(`data/d3/shaman_skill_values.csv`), and the engine casts, costs, hits and ticks it. The code in this folder is what a record
and a number cannot say: when, where, on whom. Contract: `docs/contracts/shaman-class.md`.

`dc_shaman.h` declares the seams the engine calls; `dc_shaman.cpp` is the dispatch (each skill's file answers for its own
records) and the 250 ms upkeep that keeps the Overcharge and Attunement buffs on the bar. Files share `dc_shaman_common.h`
(the class helpers and the engine's headers) and `dc_shaman_effects` (the stun, freeze, slow and heal).

| File | What it holds |
|------|---------------|
| `dc_shaman` | the seams (`Connected`, `Casting`, `Multipliers`, `Gain`, and the Defensive block: `BasePct`, `Aim`, `Cast`, `MissChance`, `Reduce`, `Damaged`, `Landed`) and the upkeep |
| `dc_shaman_maelstrom` | what a skill that states `Generate: N Maelstrom` pays, and the split of a gain between the bar and Overcharge |
| `dc_shaman_overcharge` | the stacks banked from overflow, the next Secondary spending them for damage, the buff on the bar |
| `dc_shaman_attunement` | the element the last Secondary or Primal cast set, its bonus, the buff on the bar |
| `dc_shaman_effects` | the stun, the freeze and the slow put on an enemy (stock auras), the Shaman's heal, the elite test |
| `dc_shaman_thunderstorm` | the knockback, the slow, Gale Force's stun, Frost Storm's freeze, Sandstorm's blind (a miss chance for ordinary enemies, only the slow for elites and bosses), Eye of the Storm's storm around the Shaman and Volcanic Gale's ring of fire |
| `dc_shaman_elemental_shield` | the shield the Shaman wears (charges, seconds, one at a time, a new cast replaces it), the hit it lowers when mitigated and pays for when it lands (a charge, even for a hit other absorbs took whole, then the strike back at most once an interval; a broken Stoneskin puts on a core absorb), Lightning Shield's Maelstrom and the charges Primary hits add, Water Shield's heal, Maelstrom and chill, Flame Shield's burn and fiery answer, Stoneskin's Armor, the six buffs that show it. Totemic Ward only wears the plain shield until the Totems exist |
| `dc_shaman_ghost_wolf` | the form (the stock Ghost Wolf aura with the sheet's speed and seconds), the immunity to slows and roots while it stands, the end a cast of any other skill gives it; Spirit Walk's longer form and stripped control effects, Wind Rush's charges in place of the cooldown, Thunderous Paws' trail of lightning patches, Spectral Recovery's heal and Blazing Spirit's explosion at the end |
| `dc_shaman_purge` | the empowered states a Purge takes off the enemies it is aimed at before the hit lands (asked of the elite affixes), the Maelstrom each removal pays, Wind Shear's interrupt and stun, Greater Purge's weakened elite, Cleanse Spirit's cleansed Shaman, Consuming Purge's burn; Earthen Purge's cone is its targeting row |
| `dc_shaman_spirit_link` | the link a cast makes (the enemy aimed at and the nearest to it, up to the sheet's count in its radius, for its seconds), the link's own damage each tick, the share of every hit the Shaman deals to one linked enemy that the others take (one proc-free fixed copy, never shared again; elites and bosses take half), Searing Link's burn, Frozen Link's chill and freeze, Thunder Link's larger share, Spirit Harvest's Maelstrom and longer link |
| `dc_shaman_elemental_weapon` | the imbue (the rune of the skill on the bar, always on), its activation for the sheet's seconds on a cast, the damage factors and Maelstrom it gives, Flametongue's burn, Frostbrand's chill and freeze, Windfury's strike again, Rockbiter's Armor, Maelstrom Weapon's free Secondary cast and richer Primaries, the sheet numbers an imbue puts on the character and the buffs that show it |
| `dc_shaman_spirit_wolves` | the wave of wolves that runs down the lane (the aimed line, or Spirit Pack's fan across its cone) at the speed the tunable gives, each wolf's hit on every enemy its lane touches as the wave reaches it, Lightning Wolves' arcs, Fiery Wolves' burning trail of ground patches, Frost Wolves' freeze, Spirit of the Pack's Maelstrom per enemy up to its cap |

Each `.h` named with a skill or mechanic holds the rules that need no core type, so the harness in `tests/shaman_*` compiles the
production code.
