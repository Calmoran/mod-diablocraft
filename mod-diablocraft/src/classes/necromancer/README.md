# The Necromancer's code

The Necromancer rides the shared combat engine: a skill is a spell record plus the numbers of its sheet
(`data/d3/necromancer_skill_values.csv`), and the engine casts, costs, hits and ticks it. The code in this folder is what a
record and a number cannot say: when, where, on whom.

`dc_necromancer.h` declares the seams the engine calls (`BasePct`, `Connected`, `Cast`, `Ground`, `RegisterScripts`);
`dc_necromancer.cpp` is the dispatch and pays the Essence every primary generates. Each skill that needs code has a file of
its own; the files share `dc_necromancer_common.h` (the class helpers and the engine's headers) and
`dc_necromancer_effects.cpp` (the stun, the slow, the heal and the Essence payment).

| File | What it holds |
|------|---------------|
| `dc_necromancer` | the seams, and the Essence a primary generates per attack |
| `dc_necromancer_effects` | the stun and the slow put on an enemy, the Necromancer's heal, the Essence paid through the core's own energize |
| `dc_necromancer_corpses` | the kill hook that leaves a corpse for each Necromancer of the killer's party (the record is the shared `combat/dc_corpses`) |
| `dc_necromancer_buffs` | the timed, stacking sheet numbers: a stack for each enemy, the whole time restarted, the number off the sheet when it ends |
| `dc_necromancer_grim_scythe` | Blood Scythe's heal, Execution's decapitation, Frost Scythe's attack speed, Dual Scythes' push to the line faced (Cursed Scythe's curse waits for the Curses category) |
| `dc_necromancer_revive` | the cast that revives up to ten corpses near the point aimed at as minions in the look of the creature that died (the kind is `dc_necromancer_pets`); Oblation's cost in Life for each corpse, Personal Army's cut to the damage taken, Horrific Return's fear (Purgatory's corpse is the minion's kind) |
| `dc_necromancer_devour` | the cast that consumes every corpse within 60 yards for Essence (and Ruthless's minions); Cannibalize's heal, Voracious's cost cut, Satiated's maximum Life, Devouring Aura's toggled aura of 15 yards and a share of the pickup radius |
| `dc_necromancer_corpse_lance` | the corpse a lance flies from (near the target, else near the Necromancer), the cast check; Ricochet, Brittle Touch's chance to be crit, Blood Lance's additional lance and Life, Visceral Impact's stun, Shredding Splinters' stacking slow and weakness |
| `dc_necromancer_corpse_explosion` | the cast that explodes up to five corpses near the point aimed at (or near the Necromancer for Close Quarters), each striking the enemies around it; Shrapnel's cone, Final Embrace's pull and cost in Life, Bloody Mess's radius, Dead Cold's freeze (the corpses are the shared `combat/dc_corpses`) |
| `dc_necromancer_death_nova` | Tendril Nova's heal, Bone Nova's and Unstable Compound's own novas (their radius is not the skill's), Blood Nova's cost in Life, Blight's patch of slow and weakness |
| `dc_necromancer_skeletal_mage` | the cast that raises the mage (the mage's kind is `dc_necromancer_pets`): Life Support's Life, Singularity's Essence and bonus |
| `dc_necromancer_passives` | the passives that need code: Life from Death's roll (the globe waits for the health globes), Fueled by Death, Stand Alone, Bone Prison, Swift Harvesting (the attack speed seam), Commander of the Risen Dead; Extended Servitude (the pets ask for the minions' seconds), Rigor Mortis, Overwhelming Essence, Dark Reaping, Spreading Malediction (the multipliers seam), Eternal Torment (the curses ask for their seconds; the Essence cut is paid back like Commander's), Final Service (the reduce seam); Grisly Tribute (the shared `Minions::OnStruck`), Draw Life, Serration (the multipliers seam, which takes the enemy hit), Aberrant Animator, Blood for Blood (the stack waits for the health globes), Blood Is Power, Rathma's Shield (`SpendLife` asks whether Life may be lost) |
| `dc_necromancer_simulacrum` | the copies of the Necromancer (the minions' kind is `dc_necromancer_pets`) that repeat its Secondary skills; Life cost, Reservoir's Essence, Cursed Form's three curses (the curses' registry holds one curse per skill), Blood Debt's cheaper Life, Blood and Bone's second copy, Self Sacrifice's second chance |
| `dc_necromancer_siphon_blood` | the channel: a strike every tick with the Essence of each, the heal every second, Suppress's slow, Purity of Essence's larger gain at full Life, Drain Life's larger heal, Power Shift's growing hits (Blood Sucker's health globes wait for the globes) |
| `dc_necromancer_bone_spear` | Crystallization's slow and speed, Shatter's detonation on the first enemy, Blighted Marrow's bonus for the enemies passed, Blood Spear's cost in Life, Teeth's shorter reach (the spear is the engine's projectile) |
| `dc_necromancer_blood_rush` | the Life the rush costs (none for Hemostasis, doubled for Metabolism), Metabolism's two charges, Transfusion's heal for the enemies passed through, Potency's armor, Molting's corpse where the rush began (the movement is the engine's charge to the point) |
| `dc_necromancer_bone_spirit` | the charges Bone Spirit stores and the corpses that shorten their recharge; Possession's charm and Life cost, Panic Attack's fear, Unfinished Business' explosion, Astral Projection's bonus for the enemies on its way |
| `dc_necromancer_bone_armor` | the armor the cast makes (damage taken cut for each enemy hit), Limited Immunity's absorb and control immunity, Dislocation's stun, Thy Flesh Sustained's Life cost and regeneration, Harvest of Anguish's speed |
| `dc_necromancer_curses` | which curse of the Necromancer is on which enemy: one at a time, the newest replaces the old and the old one's skill lifts its effects |
| `dc_necromancer_decrepify` | the cast that curses the enemies around the place aimed at (slow, less damage dealt); Enfeeblement's decaying slow, Opportunist's speed and Borrowed Time's cooldown reduction for the enemies cursed, Wither, Dizzying Curse's stun |
| `dc_necromancer_frailty` | the cast that curses the enemies around the place aimed at (or everything around the Necromancer, for Aura of Frailty) and the check that kills the cursed under the threshold; Early Grave's Life cost, Harvest Essence's Essence, Volatile Death's explosion (the kill hook), Scent of Blood's minion bonus |
| `dc_necromancer_leech` | the cast that curses the enemies around the place aimed at (or the ground, for Cursed Ground), the heal when a cursed enemy is struck; Osmosis' regeneration, Transmittable's spread, Sanguine End's Life per Kill, Blood Flask's potion cooldown (the kill hook) |
| `dc_necromancer_land_of_the_dead` | the cast that opens the land (the shared corpses meet a request with corpses made on the spot for its seconds); Invigoration's free abilities, Frozen Lands' freeze, Plaguelands' plague, Land of Plenty's heal and Shallow Graves' extension on kills (the kill hook) |
| `dc_necromancer_army_of_the_dead` | the cast that raises the army after the power's delay: the skill's blasts, Blighted Grasp's hands, Frozen Army's line, Unconventional Warfare's random attacks, Death Valley's pull, Dead Storm's ticks and its Life cost |
| `dc_necromancer_command_golem` | the active: the Golem collapses into corpses (the skill, Flesh Golem), Bone Golem's tornado, Blood Golem's sacrifice and veins, Decay Golem's feeding, Ice Golem's freeze and crit mark (the Golem and its runes' blows are `dc_necromancer_pets`) |
| `dc_necromancer_command_skeletons` | the active: the order at a target (until it dies), Freezing Grasp's hold, Kill Command's explosion in place of an order (the skeleton and its runes' blows are `dc_necromancer_pets`) |
| `dc_necromancer_pets` | the five kinds of minion the Necromancer defines (the minions are the shared `combat/dc_minions`): the mage with its runes (a corpse at its end, an aura, an archer's blows), the skeletons, the golem, the revived and the Simulacrum, and the keepers of Command Skeletons and Command Golem |
| `dc_necromancer_bone_spikes` | Sudden Impact's stun, Path of Bones' line, Bone Pillars' strikes on the nearest enemy and two around it, Frost Spikes' slow, Blood Spikes' bleed and heal |

## Skills with no file of their own

A skill that is a spell shell and sheet numbers has no file: the engine runs it from its row.

- None yet: the skill beads add their files as they land.
