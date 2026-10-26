# Approved early spawn veto

Implements 03 section 3 and 08 section 2 at d3d984c. The designer approved patch 0004; the patch is written and applied. Build and runtime verification are in progress.

## Existing hooks

`AllCreatureScript::OnCreatureAddWorld` and `AllGameObjectScript::OnGameObjectAddWorld` run after initialization and cannot veto creation. The level-selection and phase-mask hooks also cannot veto it. A grid-only check misses scripted summons, event/pool loads, moving transports and passengers. Vehicles use creature creation; static transports override game-object creation, and moving transports have a separate creator.

## Approved patch

`core-patches/0004-world-spawn-filter-hook.patch`

One-line reason: Allow modules to veto world-object creation before models, AI, vehicle accessories and passenger scripts initialize.

Add a default-allow GlobalScript hook carrying object kind, entry/spawn ID, map ID, phase and resolved world coordinates. Any false result prevents creation; the core has no Diablocraft table names, area IDs or policy. Existing successful creation is unchanged when no module vetoes.

Expected files in the single patch:

- `src/server/game/Scripting/ScriptMgr.h`
- `src/server/game/Scripting/ScriptDefines/GlobalScript.h`
- `src/server/game/Scripting/ScriptDefines/GlobalScript.cpp`
- `src/server/game/Entities/Creature/Creature.h` and `.cpp`
- `src/server/game/Entities/GameObject/GameObject.h` and `.cpp`
- `src/server/game/Entities/Transport/Transport.cpp`
- `src/server/game/Maps/TransportMgr.cpp`
- `src/server/game/Entities/Pet/Pet.cpp`

Call before creature prototype/vehicle initialization and before game-object model/script initialization. Cover `StaticTransport::Create`, moving transport creation before `CreateMoTrans`, and transport map arrivals before loading the destination grid/passengers. Pet loading/taming checks use the owner/source's actual position before initialization. Existing failure returns perform cleanup; do not create and then despawn rejected objects.

Transport passengers need their offsets transformed to world coordinates before validation. Forward an optional world-position context through creature/game-object DB creation for those callers, preserving default arguments for existing callers. Never interpret a passenger's transport-local offset as a world area.

## Module implementation

Load and validate `dc_world_areas` before spawn systems initialize. An unlisted/closed open-world area is denied; missing/invalid rules fail closed with a startup error. Instance maps keep their existing behavior. The initial row is map 1, area 876, scope `all`, status `open`. Resolve areas from terrain at the actual position; database areaId=0 is not an authorization to spawn. Do not calculate rules per hit or alter visibility after spawning.

Replace full-map generation with a generator keyed by an explicitly open map/area. Keep baseline phase 1 and create phases 2-10 only for sources resolved inside that area. Record ownership by map/area/source/tier so reopening/rerunning cannot multiply existing copies. Preserve supported placement links within the area; report any unsupported cross-boundary links rather than silently cloning outside it. The three GM Island test Hoggers currently have database areaId=0, so resolved terrain area matters for this step.

## Verification plan

Check permitted and forbidden creature, game-object, vehicle, static/moving transport and scripted-summon paths; no spawned object/model/AI in a closed area. Verify instance behavior is unchanged and GM Island copies are confined to its area. Then repeat Normal/Torment VI Hogger Life and first-engagement party tests, tier/party persistence, and the AIO validation checks.

Capture idle and one-player GM Island `.server info` samples with the same map-thread setting and a stated warmup interval. Keep server tick time distinct from client network latency.
