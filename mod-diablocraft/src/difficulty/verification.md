# Difficulty verification

## Tier login correction — 2026-09-07

- Confirmed source path: CharacterHandler adds the player to the map before OnPlayerLogin; map entry invokes OnPlayerMapChanged, then login loads the saved/leader tier. Missing FindMap/ready was not the root of the reproduced failure.
- Installed Unit::SetPhaseMask's unchanged-ID return skips WorldObject::SetPhaseMask and the literal-phase hook; the default combined flag remains true for an unchanged Normal player and can remain true for a Normal creature. The same visibility comparison applies to hub services, objects and open-world monsters.
- Added difficulty-only ApplyPhase helper: unchanged ID goes through WorldObject's existing policy hook; changed ID uses Unit's normal path. Login/map-change and creature/object initialization share it.
- Source-extracted regression reproduces five overlapping Normal masks (1/3/5/7/9), then passes single-copy checks for all ten tiers, visibility refresh, creature/object initialization, Unit transition/veto behavior and stock instances. The designer's precise live count remains unverified.
- First harness configure failed with MSB6001 (duplicate Path/PATH environment keys); the Windows PowerShell 5.1-compatible test runner normalizes the child environment and the harness passes.
- Full Release worldserver build passed with 0 warnings/errors under Codex's build.lock and -m:1; lock removed; verified installed SHA256 DE4B8D537E0DA2A8989D917878691EFAC159F1BF30EE6CC2E0E76CFCC1A518EA.
- Previous executable retained in build/tier-login-backup-20260907-181817; old process shut down cleanly and drained all database queues; replacement launched with -c configs/worldserver.conf. No core source, client patch or migration was edited.
- Exact pending live checks: docs/test-tier-login.md; cold Normal and Torment VI login must each show one copy of every installed hub service/object before using the selector.

## Retired full-map approach

- Captured worldserver log: update time diff **18,891 ms**, zero players; mean **2,670 ms**, median **2 ms**, 95th percentile **14,138 ms**, 99th percentile **16,710 ms** (68 samples). MapUpdate.Threads=1. This run had a debugger attached, so it is not a controlled final benchmark.
- One player reported severe simulation lag while client network latency showed 3 ms. No numeric one-player server update-time sample was captured; do not substitute the network latency.
- Later diagnostic with MapUpdate.Threads=0: `.server info` at 1m08s uptime, zero players, last diff **2 ms**, mean **374 ms**, median **2 ms**, 95th **1,612 ms**, 99th **2,401 ms**, max **2,995 ms** (97 samples). Different threading/warmup means this is not an after-fix comparison.
- Crash capture detected heap corruption while loading a grid in `BIHWrap<GameObjectModel>::balance` through `DynamicMapTree::GetAreaAndLiquidData`. The detection stack does not establish the original memory-corruption site.
- At that stage, actual Normal Hogger: entry 448, level 11, baseline/max Life **666**, phase 1. Torment VI and two-player Life had not yet been verified (completed below). `.npc add` under GM mode used its aura phase (Normal); the three created Hoggers remain phase 1.

## Area-only replacement

- Full-map retirement removed ownership for **1,105,605 creature copies**, **514,917 game-object copies**, **6,804 pools**, and **36 spawn groups**, with associated rows. Ownership tables now contain zero rows. GM test spawn GUIDs 6406286–6406288 remain.
- `dc_world_areas`: one row, map **1**, area **876**, `all`, `open`; AreaTable.dbc confirms GM Island. CSV row count equals SQL row count.
- Generator tests and retirement fixture pass. The fixture verifies preserving unowned/GM placements, deleting owned relationships, fresh-install execution and rerun safety.
- Approved spawn hook exists as patch 0004, listed in core-patches/README.md, in separate commit **6ab2b31**. The accidental inclusion in the concurrent combat commit was split without changing the final tree; the old history remains at `refs/backup/before-spawn-hook-split`.
- Release build passes with zero warnings/errors. `scripts/build.ps1` uses the root `build.lock`, waits for a recent owner, refreshes lock age while running, and releases its own lock in finally. Builds use `-- -m:1 /p:CL_MPCount=1` to avoid memory pressure alongside MySQL/server processes.
- Initial filtered startup exposed Wintergrasp's null portal dereference: `Object::SetUInt32Value -> BattlefieldWG::SetupBattlefield -> BattlefieldMgr::InitBattlefield`. Existing `Wintergrasp.Enable=2` skips all processing; zero only disables the battle. No Wintergrasp core patch was made.
- PvE settings are recorded in docs/install-dev.md. Built-in `disables` contains 7 outdoor-PvP IDs and 13 battleground/arena IDs, including their aggregate queues. Continent boats are disabled; game-event/pool loaders check failed creations. Unconditional Deeprun Tram grid loading remains, with its closed-area objects rejected.
- Filtered startup completed in **7 seconds**, initially about **0.9 GiB** working set. Startup denied 9 creatures, 50 game objects and 6 static transports. These are startup counts, not a complete gameplay test of every object type.
- `dc areas test`: **PASS** for six kinds across open/closed/instance policy and four real creation vetoes. `dc areas scan 1 876`: **19 sources** (4 creatures, 15 objects). The scanner casts FLOAT coordinates to DOUBLE in SQL to preserve their stored precision; a generator check caught and prevented using the earlier rounded snapshot.
- Generated/applied **171 copies**: 4 creatures and 15 objects in each phase 2-10, with original sources supplying phase 1. All copy coordinates, maps and phases match ownership/source records (zero mismatches). The unowned GM-created phase-10 Hogger remains untouched.
- Generator integration tests pass for stable reruns, links, removed-source cleanup, unowned preservation, GUID collisions, Life ceiling, closed/pool/cross-area/stale rejection and rollback. A live rerun reproduced SHA1 **58306CE6A419E98D89CB965468CF9D54E2A1663C** with unchanged GUIDs. One intermediate metadata read returned empty for an existing table; the run stopped without rewriting output, direct inspection confirmed the table, and the next complete run passed.
- After-copy idle sample, no debugger, MapUpdate.Threads=1, uptime **2m11s**, zero connected/in-world players: update diff **2 ms**, mean **1 ms**, median **2 ms**, p95 **2 ms**, p99/max **3 ms** (500 updates), working set approximately **869 MiB**. Repeated console commands flushed the captured output; they represent the same sample window, not independent trials.
- After-copy one-player sample, Diablocraft on GM Island at Normal with GM mode on, second client at login, uptime **5m37s**: update diff **2 ms**, mean **1 ms**, median **2 ms**, p95 **2 ms**, p99/max **3 ms** (500 updates), working set approximately **879 MiB**. MapUpdate.Threads=1; no debugger. The previous sample including recent login reported 3 ms last diff with the same 1 ms mean.
- In-game `.dc tier` verified Normal spawn **6406288**, level 11, phase **1**, baseline/Life **666**, damage multiplier **1**, one player. Its owned Torment VI copy **6406325** is at the identical source position but phase **10**, baseline **666**, Life **57,209**, damage multiplier **25.4**, one player. Matching positions are intentional; these are distinct GUIDs and phases.
- The designer confirmed Tiermate inherited tier 10 when joining Diablocraft's party, and the member's attempt to choose tier 1 was refused.
- The first `/dctier` test failed because the active WoW client had no AIO_Client addon installed. An initial approved copy used the earlier Heimdall client path; the designer installed it in the actual repository client, `WoW Client/Interface/AddOns`. After restarting, the designer's screenshot confirms the Difficulty menu on Tiermate displays all ten tiers with the correct multipliers and Torment VI selected. The designer subsequently confirmed menu selection, party following and combat refusal worked. The log records successful choices of tiers 4, 10 and 9; the final fight was on Torment V, rather than the requested Torment VI. No server code change was required for the addon installation issue.
- Both Diablocraft and Tiermate subsequently logged in at level 70 with saved tier 10 / phase 10, confirmed in the server log.
- Two-player engagement verified on Torment V: Hogger spawn **6406324**, baseline **666**, Life **53,636**, damage multiplier **17.52**, players **2**. On leaving combat, the same spawn returned to solo Life **35,757**. These equal floor(666 * 53.69 * 1.5) and floor(666 * 53.69), respectively; rounding occurs after the full multiplier product. Spawns 6406306 and 6406315 showed the same transition. Two-player Torment VI Life was not measured; the earlier solo Torment VI test is recorded above.
- A numeric pre-change one-player sample is unavailable; the old 3 ms report was network latency, not server update time. The old full-map idle diagnostic had a debugger attached and different world content, so the comparison is observational rather than controlled.

Final party-test log excerpts:

```text
[DC tiers] Diablocraft selected tier=10 phase=10
[DC tiers] Diablocraft selected tier=9 phase=9
[DC tier creature] entry=448 spawn=6406324 level=11 phase=9 baseLife=666 Life=53636 damageMultiplier=17.52 players=2
[DC tier creature] entry=448 spawn=6406324 level=11 phase=9 baseLife=666 Life=35757 damageMultiplier=17.52 players=1
```
