# Diablocraft

Diablo III's systems rebuilt on a World of Warcraft 3.3.5a (build 12340) server: AzerothCore plus one
module, a set of small core patches and a client patch. Greater Rifts, Torment difficulties, D3 loot and
legendaries, Kadala, artisans and the Cube, paragon, followers, and the D3 classes (Barbarian, Crusader,
Demon Hunter, Monk, Necromancer, Witch Doctor, Wizard) with their skills, runes and passives, with a
Shaman in progress.

**The project has ended and is released as-is for the private server community.** It was never
finished: some systems are complete, others are partly built, and nothing here is supported. Take what
is useful.

## What is here

| Path | What it is |
|---|---|
| `mod-diablocraft/` | The AzerothCore module: C++ (`src/`), server Lua for ALE + AIO (`lua/aio/`), config (`conf/`), data |
| `mod-diablocraft/data/` | `d3/` D3 numbers, `tunables/` tuning sheets, `generated/` and `sql/` the SQL built from them |
| `mod-diablocraft/scripts/` | Generators (`generate/`), Python tests (`tests/`), build and test helpers |
| `core-patches/` | Numbered patches to AzerothCore, applied in order; `README.md` says what each one does |
| `client-patch/` | The client side: addons, art, DBC sources, `build.sh` and the built `patch-4.MPQ` |
| `client-extension/` | The client DLL module (`torment/`, on top of the vendored WarcraftXL core `wxl-core/`) and patches for a rebuilt client (`wowdecomp/patches/`, for SatyPardus/wowdecomp, which is not included) |
| `reference/d3planner/` | d3planner's item and stat data, which the generators read |

Internally the code still uses the name `Torment` in places (the client addon folder, the DLL module,
config keys). Torment is also the D3 difficulty name used throughout the data.

## Building the server, in outline

1. Clone AzerothCore and check out the commit in `core-commit.txt` into `azerothcore-wotlk/` at the
   repo root.
2. Apply `core-patches/*.patch` in numeric order (`git -C azerothcore-wotlk apply <patch>`).
3. Put the modules in `modules-commit.txt` into `azerothcore-wotlk/modules/` at the listed commits
   (mod-ale, mod-autobalance, mod-transmog; mod-heimdall is optional), and link
   `mod-diablocraft/` in as `azerothcore-wotlk/modules/mod-diablocraft`.
4. Configure and build AzerothCore as usual with `-DSCRIPTS=minimal-static -DMODULES=static`
   (`mod-diablocraft/scripts/build.sh` is the script the project used).
5. Copy `mod-diablocraft/conf/mod_diablocraft.conf.dist` next to the worldserver config. The SQL
   under `mod-diablocraft/data/sql/` is applied by AzerothCore's own DB updater.
6. Server Lua: install AIO (`mod-diablocraft/scripts/build_live_aio.sh` builds the pinned AIO server
   half with patch 0020) and put `mod-diablocraft/lua/aio/` under the worldserver's `lua_scripts/`.

To change data, edit the CSVs and rerun
`python3 mod-diablocraft/scripts/generate/tooling/generate_sql.py`; never edit generated SQL by hand.

## The client

- `client-patch/patch-4.MPQ` goes in the client's `Data/` folder. Rebuild it with
  `client-patch/build.sh` (needs `smpq`). `client-patch/dbc/README.md` explains the DBCs.
- The addons in `client-patch/addons/` go in `Interface/AddOns/`.
- Edited `GlueXML` and `FrameXML` files only load on a client whose interface signature check is
  removed; see the notes in `client-patch/build.sh`.
- The client extension builds on Windows; see `client-extension/README.md`.

## Tests

The Python tests run directly (`python3 mod-diablocraft/scripts/tests/<system>/test_x.py`) or through
`mod-diablocraft/scripts/run_tests.py`. Many expect a built core and extracted DBCs under
`azerothcore-wotlk/build/`.

## Licence

GNU Affero General Public License v3.0, see `LICENSE`. Third-party code keeps its own licence:
`client-extension/wxl-core/` (WarcraftXL and its dependencies), `client-patch/addons/Bartender4/`, and
`reference/d3planner/`. Diablo and World of Warcraft are trademarks of Blizzard Entertainment; this
project is not affiliated with or endorsed by Blizzard.
