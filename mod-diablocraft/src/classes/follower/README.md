# Follower skills

The skills the three followers cast and the passives they give their player (contract `docs/contracts/followers.md`, "Skills").
Not a class: a follower reads its own gear's main stat and the player's level (the sheet `data/d3/followers_skill_numbers.csv`).

| File | What it holds |
|---|---|
| `dc_follower_skills` | the sheet's numbers and the tiers (`dc_follower_skill`, `dc_follower_skill_value`), the picks a character keeps for each follower and the `.dc follower skill` and `.dc follower skills` commands, the cooldowns, the stock holds the skills put on enemies (stun, slow, taunt), a follower's hit and heal, the shield, the look the companion's AI asks for and the fatal-blow seam |
| `dc_follower_templar` | the Templar's eight: Heal, Intervene, Loyalty, Intimidate, Charge, Onslaught, Inspire, Guardian |
| `dc_follower_scoundrel` | the Scoundrel's eight: Crippling Shot, Powered Shot, Hysteria, Anatomy, Piercing Shot, Multishot, Vanish, Night's Veil |
| `dc_follower_enchantress` | the Enchantress' eight: Charm, Temporal Pulse, Amplification, Prophetic Harmony, Powered Shield, Erosion, Focused Mind, Fate's Lapse |
| `dc_follower_skill_rules.h` | the pure rules (the main stat's share, a tier open, a skill on, a cooldown, a heal, a hit, a fatal blow), compiled by `tests/follower_skills` |
| `dc_follower_internal.h` | what the files share |
