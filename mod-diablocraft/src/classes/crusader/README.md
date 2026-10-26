# The Crusader's code

The Crusader rides the shared combat engine: a skill is a spell record plus the numbers of its sheet
(`data/d3/crusader_skill_values.csv`), and the engine casts, costs, hits and ticks it. The code in this folder is what a
record and a number cannot say: when, where, on whom.

`dc_crusader.h` declares the seams the engine calls (`BasePct`, `CanCast`, `Connected`, `Approach`, `Cast`, `Ground`, `Landed`, `Multipliers`, `CritBonus`, `Blocked`);
`dc_crusader.cpp` is the dispatch and pays the Wrath a primary generates. Each skill that needs code has a file of its
own; the files share `dc_crusader_common.h` (the class helpers and the engine's headers) and `dc_crusader_buffs.h/.cpp`
(a timed, stacking number on the sheet).

| File | What it holds |
|------|---------------|
| `dc_crusader` | the seams, and the Wrath every primary generates per attack |
| `dc_crusader_buffs` | Hardened Senses' Block Chance and the other timed sheet numbers: stacks, the restarted time, the end |
| `dc_crusader_slash` | Zeal's and Guard's stacks, Electrify's stun, Crush's critical chance, Carve's larger area |
| `dc_crusader_smite` | the chains to the nearest enemies, Shared Fate's ties and stuns, Shackle's Immobilize, Shatter's explosions, Reaping's regeneration |
| `dc_crusader_justice` | the hammer's hit (Hammer of Pursuit's own number), Sword of Justice's speed, Crack's smaller hammers, Burst's explosion and stun, Holy Bolt's heal |
| `dc_crusader_nearest` | the rule that picks the nearest enemies inside a radius, shared by Smite's chains and Crack's hammers |
| `dc_crusader_shield_bash` | the charge, the cone of enemies around the one aimed at, Shattered Shield's fragments, Shield Cross's arms, One on One's stun and knockback |
| `dc_crusader_block_share` | "plus a share of your shield Block Chance as damage": the hit's multiplier and the percentage the Crusader's own strikes carry (Shield Bash, Blessed Shield) |
| `dc_crusader_sweep_attack` | the half circle in front, Gathering Sweep's pull, Blazing Sweep's fire, Holy Shock's Life, Trip Attack's stun, Inspiring Sweep's Armor |
| `dc_crusader_dot` | a burn: ticks of damage over a number of seconds on an enemy, one running per Crusader, enemy and spell |
| `dc_crusader_blessed_hammer` | the hammer's one pass, Burning Wrath's fire pools, Limitless's larger ring, Brute Force's slow and explosion |
| `dc_crusader_blessed_shield` | the ricochet (or Piercing Shield's pierce), Staggering Shield's stuns, Combust's explosions, Divine Aegis's stacks, Shattering Throw's fragments |
| `dc_crusader_fist_of_the_heavens` | the bolts that leave the explosion, Heaven's Tempest's storm, Reverberation's slow, Fissure's burn and arcs, Divine Well's zaps, Retribution's fist |
| `dc_crusader_shield_glare` | the blind over the whole arc, Divine Verdict's extra damage, Uncertainty's roll to charm (the charm itself is the shared `combat/dc_charm_effect`), Emblazoned Shield's explosions, Zealous Glare's Wrath, Subdue's slow |
| `dc_crusader_iron_skin` | the skin's damage reduction and time, Charged Up's stun and Flash's speed when hit, Explosive Skin's blast at the end, Reflective Skin's Thorns |
| `dc_crusader_consecration` | the ground's heal each second, Bed of Nails' Thorns, Shattered Ground's fire, Fearful's fear, Aegis Purgatory's edge |
| `dc_crusader_judgment` | the Immobilize on the enemies around the spot, Penitence's heal, Mass Verdict's pull, Resolved's crit chance on the judged, Debilitate's weakening |
| `dc_crusader_provoke` | the taunt (or Flee Fool's fear) on the enemies around, the Wrath for each, Cleanse's Life on Hit, Too Scared to Run's slow and weaker attacks, Charged Up's Lightning on every hit, Hit Me's Block Chance |
| `dc_crusader_steed_charge` | the war horse and its speed, the ride's ticks: Spiked Barding's Thorns, Rejuvenation's Life, Nightmare's fire pools, Draw and Quarter's bound and dragged enemies |
| `dc_crusader_condemn` | the explosion that builds and goes off, Reciprocate's counted damage, Vacuum's pulses, Eternal Retaliation's cooldown cut, Unleashed's instant blast |
| `dc_crusader_phalanx` | the avatars of the order (their creature script, crusader_summons.csv): the charge to the point and Shield Charge's bash, Stampede's stuns, the Bowmen's shots, the place the Shield Bearers hold, the Bodyguard's blows, and the cost and cooldown of the three gated runes |
| `dc_crusader_falling_sword` | what each rune leaves where the Crusader lands (the cast path is a leap to a ground point, struck on landing): Superheated's burning ground, Part the Clouds' storm that strikes and stuns, Rise Brothers' avatars (Phalanx's fighters), Flurry's swords and incapacitate; Rapid Descent's cut, and the cooldown that starts only once the effects are over |
| `dc_crusader_akarats_champion` | the transformation: its time, the damage it adds to every hit, the Wrath it pays each second, Fire Starter's burn, Rally's cut to the other cooldowns, Prophet's Armor and one saved life (the `Fatal` seam), Hasteful's attack speed |
| `dc_crusader_heavens_fury` | the ray as a ground zone of ticks, Ascendancy's wider one, Blessed Ground's burning ground, Split Fury's ring of beams, Thou Shalt Not Pass's held place, Fires of Heaven's beam through the Crusader |
| `dc_crusader_bombardment` | the barrage: spheres that leave and fall one after another on enemies near the aimed point, Barrels of Spikes' Thorns, Annihilate's critical chance, Mine Field's mines, Impactful Bombardment's one large ball, Targeted's first enemy |
| `dc_crusader_hold` | a place held shut: an enemy seen on one side of its edge and found on the other is put back (Thou Shalt Not Pass) |
| `dc_crusader_zone` | a ground zone: ticks of damage on the enemies standing in a place |
| `dc_crusader_punish` | the shield it needs, Hardened Senses, and the answer each rune gives to a block |
| `dc_crusader_laws` | the state every Law shares (only one Law in force, its window, Answered Prayer's extension), and the mechanism that pulses a Law's aura to the Crusader and its group and holds the numbers it gives |
| `dc_crusader_laws_of_valor` | Laws of Valor's pulse (the passive or the empowered Attack Speed), Invincible's Life on Hit, Critical's Critical Hit Damage, Frozen in Terror's stun, Unstoppable Force's cost cut, Answered Prayer's kills |
| `dc_crusader_laws_of_justice` | Laws of Justice's resistance pulse, Immovable Object's Armor, Faith's Armor's shields, Bravery's immunity, Decaying Strength's weakened attackers, and Protect the Innocent's share of an ally's damage dealt to the Crusader |
| `dc_crusader_laws_of_hope` | Laws of Hope's heal each pulse, the shield, Wings of Angels' speed, Eternal Hope's Life, Hopeful Cry's and Promise of Faith's damage reductions, Faith's Reward's heal for Wrath spent |
| `dc_crusader_passives` | the passives that need code: Heavenly Strength's damage cost and its grip (the answer to core patch 0031's Titan's Grip hook; the shield comes off when the passive is unpicked), the sheet rows (Fervor, Vigilant, Righteousness, Divine Fortress, Hold Your Ground) kept by an update script, Righteousness' extra Wrath, Insurmountable's Wrath on a block, Fanaticism's attack speed, Indestructible's save, Holy Cause's and Lord Commander's damage and Holy Cause's heal, Wrathful's heal for Wrath spent, Lord Commander's cooldown cut, Hold Your Ground's end of dodging, Long Arm of the Law's longer Laws, Iron Maiden's and Finery's sheet rows, Renewal's heal on a block, Blunt's and Towering Shield's damage, Towering Shield's cooldown cut |

## Skills with no file of their own

A skill that is a spell shell and sheet numbers has no file: the engine runs it from its row.

- None yet: the Primary beads add their files as they land.
