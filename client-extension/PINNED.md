# client-extension / wxl-core — pinned source

## What this is

`wxl-core/` is a plain copy (not a submodule, not a renamed `.git`) of the WarcraftXL
core, vendored so our CI can build it and our own extension can sit on it.

- **Upstream:** https://github.com/WarcraftXL/wxl-core.git
- **Commit:** `748d77b4700d919a8470264577ddee4f3835fac6`
  (2026-10-12 revision of `v1.1`; upstream HEAD merge `Merge pull request #32 from
  Morfium-G/fix/imgui-input-follow-device-recreation`).
- **Copied:** every tracked file as-is, byte-for-byte, minus the upstream's own
  CI: `wxl-core/.github/` (the project's `release.yml`) and the nested
  `deps/minhook/.github/` and `deps/flatbuffers/.github/` were removed so no
  third-party workflow runs in this repo. `wxl-core/.gitattributes`
  (`* text=auto eol=crlf`) is kept, so git stores LF and checks the tree out CRLF,
  as upstream does.
- `client-extension/wxl-core/` is unchanged from upstream beyond those deletions; our
  own code lives in the extension module beside it (a later task), never mixed in here.
- **The launcher installs:** `WarcraftXL.dll` beside `Wow.exe`, and our own module's
  `Extensions\Torment\Torment.dll` (built from `client-extension/torment/`), both from the CI artefact.
  The launcher refuses any DLL whose SHA256 it does not know, so each CI artefact's hash is what it
  is told (C4).

## Dependency security read (2026-10-12, before this tree builds)

Scope: every dependency that could fetch, run, or phone home at configure, build, or
load. Read: `CMakeLists.txt`, `build.ps1`, and each tree under `deps/`. Findings —
what each one is allowed to do — with the file that proves it.

### Build-time (configure)

- **`CMakeLists.txt`** does **no** fetching: no `FetchContent`, `ExternalProject`,
  `file(DOWNLOAD)`, or `execute_process`. Its only external include is
  `add_subdirectory(deps/minhook)` (`CMakeLists.txt:94`), a local source tree.
  `cmake_minimum_required(VERSION 3.20)`, Win32-only (the `CMAKE_SIZEOF_VOID_P EQUAL 4`
  block; a 64-bit configure builds nothing, `CMakeLists.txt:196-198`). Nothing downloads.
- **`build.ps1`** runs only local tooling: `cmake` configure/build and, with
  `-AutoPatch`, the locally built `wxl-patcher.exe`. No download, no network, no
  package restore. It refuses to run without a `-ClientPath` (cached in the CMake
  cache); that path is only used to copy built artefacts into a client.
- **`deps/minhook/CMakeLists.txt`** builds the vendored sources in place; no fetch,
  no `execute_process`.

### `deps/minhook` — linked into `WarcraftXL.dll`

Inline-detour engine (v1.3.3). Compiled into the DLL via `add_subdirectory`. No I/O,
no network, no process spawn. Its only dynamic resolution is the hook-API itself:
`GetModuleHandleW`/`GetProcAddress` to find a hook target inside the current process
(`src/hook.c:891-895`). Nothing external is contacted.

### `deps/imgui` — linked into `WarcraftXL.dll`

Dear ImGui v1.91.9b, core + DX9/Win32 backends (listed explicitly in
`CMakeLists.txt:78-83`; the demo window is not vendored). Relevant calls, all ordinary
Win32 and none of them automatic:

- `imgui_impl_win32.cpp` dynamically loads `xinput1_*.dll`, `user32.dll`, `shcore.dll`
  and resolves functions out of them (`:196-200`, `:821`, `:860-893`) — system input/
  DPI helpers, no network.
- `imgui.cpp:15178` can call `ShellExecuteW(NULL, L"open", path, ...)` — but only from
  `Platform_OpenInShellFn`, reached when a caller asks ImGui to open a path/URL; it
  runs nothing by itself.
- `imgui.cpp:2311-2328` uses `fopen`/`_wfopen` for ImGui's own optional file logging;
  off unless a caller turns it on.
- No socket, no `WinInet`, no `CreateProcess`, no registry access.

### `deps/flatbuffers` — **not built**

Only headers (`include/flatbuffers/**`, header-only for our use) plus
`src/util.cpp`. **Nothing references `flatbuffers` and no target compiles it**
(`CMakeLists.txt` lists no flatbuffers source, and no `src/` file includes it) — it is
dead weight in this copy, carried for parity with upstream. `src/util.cpp` itself has
no network, process-spawn, or dynamic-load calls.

### `deps/stormlib` — **not built**, and note the one network-capable dep

`CMakeLists.txt` never references `stormlib` and no `src/` file includes it: it is not
compiled into any target here. Upstream's own `deps/README` marks it for the retired
64-bit host, which no longer exists (`CMakeLists.txt:3`, "there is no 64-bit asset host
any more"). Flagged anyway because it is the only dependency with network code:
`src/FileStream.cpp:691-717` uses WinINet (`InternetOpen`/`HttpSendRequest`) to read an
MPQ over HTTP when the archive path is a URL. It is inert in this build (not compiled,
no caller); if it is ever linked, that HTTP path exists.

### Runtime behaviour of the vendored core (for the record)

- `WarcraftXL.dll` reads its own optional `WarcraftXL.cfg` (cwd, then `..\`) and the
  environment for knobs (`src/common/Config.cpp:36-73`); it writes its own log under
  `Logs\` (`src/runtime/Main.cpp`). It loads extension DLLs from a local
  `Extensions\<name>\<name>.dll` folder (`src/runtime/Extensions.cpp`). It reads the
  host client's own files at runtime. No telemetry, no upload, no phone-home anywhere
  in the tree.

## Build we run

`windows-latest`, MSVC, Win32. The CI job (`.github/workflows/client-extension.yml`)
first builds and runs our unit test (`client-extension/tests`, the key table), then
copies our module (`client-extension/torment`) to `wxl-core/extensions/Torment`,
configures `client-extension/wxl-core` with `-A Win32`, builds the `WarcraftXL` and
`Torment` targets only, checks their exports, then uploads both as the `client-extension`
artefact. It passes no `-DCLIENT_PATH`, so the build copies nothing into a client. See that
workflow for the exact commands.

# client-extension / wxl-unit-outline — pinned source

## What this is

`wxl-unit-outline/` is a plain copy of WarcraftXL's unit outline module (C5, brief
`azerothcore-wotlk/build/_agent-scratch/wxl-modules-2026-10-12/brief.md`). The CI job copies it to
`wxl-core/extensions/wxl-unit-outline`; the core's extension loop builds it as
`wxl-unit-outline.dll`, staged into `Extensions\wxl-unit-outline\`.

- **Upstream:** https://github.com/WarcraftXL/wxl-unit-outline.git, branch `v1.1`
- **Commit:** `4e8123ec5d0e89cf1641eaeb27c487d72e29405d` (2026-08-06, "v1.1").
  Not `main` (`29e5e29`, 2026-07-16): that is an in-core script written for the core from before
  2026-07-18 (`events/`, `game/gx/`, no `WXL_Query`/`WXL_Load`) and does not build on 748d77b.
- **Copied:** every tracked file as-is (`git archive` of that commit), with the one patch below.
- **The launcher installs:** `Extensions\wxl-unit-outline\wxl-unit-outline.dll`, from the CI artefact.
  The launcher refuses any DLL whose SHA256 it does not know, so each CI artefact's hash is what it
  is told (C4).

## Torment patch

- `src/Outline.cpp`, `Outline::RebuildTargets`: the line `AddTarget(world::TargetGuid(), player);`
  is replaced by a comment, so only the unit under the cursor is outlined, as D3 outlines on hover
  (PM ruling on `diablocraft-z2k69.6`, 2026-10-12). Upstream also outlines the current target.

## It needs wxl-modern-m2

The outline traces each silhouette from `OnM2BatchDraw`, and nothing in the pinned core fires that
event: the core leaves the `DrawIndexedPrimitive` slot to the M2 module
(`wxl-core/src/client/CWorldScene/Render.cpp:31-38`), and the one module that fires it is
WarcraftXL/wxl-modern-m2 (`src/render/M2Draw.cpp`), pinned below (ruling 2026-10-12, z2k69.9). Without
that DLL this one loads, logs `outline active on mouseover and target` (upstream's text) and draws
nothing.

## Security read (2026-10-12, before this tree builds)

Three source files and an HLSL header; no build glue of its own (the core's extension loop builds
it; no `shared.cmake`). No file, network, process, registry, `LoadLibrary` or hook calls, and no
`offsets/` include: it reads units through `wxl::game::world` / `wxl::game::unit`, subscribes to
`OnEndScene`, `OnM2BatchDraw` and `OnDeviceLost`, and compiles its three pixel shaders through the
core's `gx::CompilePixelShader`. It needs no `d3d9.dll` from wxl: that proxy only forwards
`Direct3DCreate9(Ex)` and loads `WarcraftXL.dll` (`wxl-core/src/engine/gpu/Proxy.cpp`), which
tswow's loader already does.

# client-extension / wxl-loot-beam — pinned source

## What this is

`wxl-loot-beam/` is the client half of manatactical's loot beam module (C6, the same brief). The CI
job copies it to `wxl-core/extensions/wxl-loot-beam`; the core's extension loop builds it as
`wxl-loot-beam.dll`, staged into `Extensions\wxl-loot-beam\` with Torment's `wxl-loot-beam.ini`
beside it (the module reads the `.ini` from its own folder, `src/Module.cpp`).

- **Upstream:** https://github.com/manatactical/wxl-loot-beam.git, branch `main`
- **Commit:** `fd75b76bf0661f2a3950bd83b835c31258f151c2` (2026-10-04; `wxl.json` says 1.2.0, abi 1.1;
  the repo's only tag is `1.0.0`).
- **Copied:** `src/`, `wxl-loot-beam.ini`, `wxl.json`, `LICENSE`, `README.md`, `.gitattributes`,
  `.gitignore`, as-is (`git archive` of that commit), with the patches below. **Left out:**
  `server/mod-loot-beam/` (the AzerothCore half; C7 starts from it inside `mod-diablocraft`),
  `module.cmake` (meant to keep `server/*.cpp` out of the client DLL, but no core branch reads a
  `module.cmake` since upstream core 95f7d56, 2026-07-18; our loop would compile the server file into
  the DLL and fail), `store/` and `screenshot.jpg` (store listing art).
- **The launcher installs:** `Extensions\wxl-loot-beam\wxl-loot-beam.dll` from the CI artefact, and
  `Extensions\wxl-loot-beam\wxl-loot-beam.ini` beside it (not a DLL; the module reads it from there).
  The launcher refuses any DLL whose SHA256 it does not know, so each CI artefact's hash is what it
  is told (C4).

## Torment patches

The designer's rules (decisions.md 2026-09-29 corpse loot answer 5, 2026-10-10 Primal): a beam only over a
corpse holding your own legendary, set or Primal Ancient drop, in orange, green or red, one beam, the
highest tier wins, gone when looted. The tier is the server's per-viewer value
(`docs/contracts/loot-beam-tier.md`).

- `src/LootBeam.cpp` `kTierDefs`: the tiers at server values 7 and 8 are renamed `Set` and `Primal`
  (upstream `Artifact` and `Heirloom`): their `.ini` keys and panel labels.
- `src/LootBeam.cpp` `ScanUnits`: the tier is read from the server's field before a corpse is
  tracked; a corpse with no tier gets no beacon (upstream beams every lootable corpse, in `Color`
  while its loot is unknown). The tier is set from the field every frame, so it follows the server
  down as well as up (upstream only ever raised it).
- `src/LootBeam.cpp` `OnUpdate`: no `ScanLoot()`. Upstream also raised a beacon to the best quality
  the open loot window shows (`GetLootSlotInfo`); that is not a Torment tier source.
- `src/Module.cpp` `WXL_Load`: no `UiAddPanel` call, so wxl's overlay (F9) has no Loot Beam panel
  (PM ruling on `diablocraft-z2k69.7`, 2026-10-12: D3 has no beam settings). Upstream lets any player
  change and save every setting there.
- `wxl-loot-beam.ini`: Torment's, and the sheet the designer edits for the beam's look (PM ruling, same
  bead: no tunables row, no generator). `ConfigVersion=9` (so the module's first-load migration leaves the
  file alone), tiers Currency to Epic off, Legendary `#FF8000` and Set `#1EFF00` (the addon's own
  orange and green, `mod-diablocraft/lua/aio/dc_grid.lua` `COLOUR_CODE`), Primal `#FF1A1A` (the stock
  client's `RED_FONT_COLOR`, 1.0/0.1/0.1). Height, width, pulse, fade and sparkles are upstream's
  values until the designer sets Torment's.

`OnM2BatchDraw` (fired by wxl-modern-m2, below) only feeds the mask that hides the beam behind your
own character (`LootBeam.cpp` `OnM2Batch`); without that DLL the beam still draws, through your
character when the character stands in front of it.

## Security read (2026-10-12, before this tree builds)

`src/` only (the server half is not vendored). No network, process, registry or hook calls, and no
`offsets/` include; the raw addresses it reads (the unit descriptor block, the open-loot GUID) are
named in `UnitFields.hpp` and `LootFields.hpp` and read under SEH guards. File access: its own
`wxl-loot-beam.ini` beside the DLL, read live (`GetPrivateProfile*`, polled by file time) and written
by the version migration (the panel's Save, which also wrote it, is patched out) (`WritePrivateProfileStringA`). It resolves
`D3DCompile` with `LoadLibraryA("d3dcompiler_47.dll")` by name, the same way the core's own
`src/game/Gx.cpp:34-35` does. It sends nothing to the server. It needs no `d3d9.dll` from wxl (its
README asks for one; that proxy only loads `WarcraftXL.dll`, which tswow's loader already does).

Upstream's overlay panel (wxl's overlay, F9, `wxl-core/src/engine/ui/ImGuiHost.cpp:73`) is not
registered (the patch above); the `.ini` is still read live, so a hand edit applies within a second.

# client-extension / wxl-modern-m2 — pinned source

## What this is

`wxl-modern-m2/` is WarcraftXL's M2 module (z2k69.9; ruling 2026-10-12, C5 question 1 answer (a)). It
is the module our core leaves the model draw to: it owns the `DrawIndexedPrimitive` slot and fires
`OnM2BatchDraw`, which the unit outline needs to draw and the loot beam's self-mask uses. It also
reads newer-format (MD21) models; Torment ships none, so that half is inert here. The CI job copies it
to `wxl-core/extensions/wxl-modern-m2`; its `shared.cmake` adds the core's
`src/engine/assets/shared/models/m2/*.cpp` to it, as the core's extension loop expects.

- **Upstream:** https://github.com/WarcraftXL/wxl-modern-m2.git, branch `main`
- **Commit:** `feba6b3a89622d0ed01d80e67cd4588a49a9a061` (2026-09-29; `wxl.json` 1.0.0, abi 1.1).
  Its own CI builds it against wxl-core `v1.1`, the branch our 748d77b is the tip of.
- **Copied:** every tracked file as-is (`git archive` of that commit) except `.github/` (upstream's
  release workflow, removed as for wxl-core) and `store/` (listing art). No Torment patch.
- **The launcher installs:** `Extensions\wxl-modern-m2\wxl-modern-m2.dll`, from the CI artefact.
  The launcher refuses any DLL whose SHA256 it does not know, so each CI artefact's hash is what it
  is told (C4).
- Fit to 748d77b, by name: every core header it includes, all 17 hook points in its `wxl.json`, every
  client offset it names, and the `wxl.m2arena` interface (published by the core,
  `src/client/CM2Shared/Memory.cpp:286`) are in the pinned core. `wxl.fdid` comes from wxl-db2, which
  we do not ship; it is only asked for to resolve newer-format texture ids and is null-checked.

## Security read (2026-10-12, before this tree builds)

Every source and build file (`src/**`, `shared.cmake`, `wxl.json`), plus the core's shared m2
sources it compiles in, read in full (the model-transform
files by a subagent under this worker, the OS-facing ones by the worker).

- No network, process, registry, thread, library-load or memory-protection call, no code-byte
  patching, nothing written to disk, nothing sent anywhere, no user or machine data collected.
- Memory: large model buffers (1 MB and up by default) come from the core's arena or
  `VirtualAlloc(PAGE_READWRITE)` (`src/load/Memory.cpp:71`), never executable, falling back to the
  client's own allocator; smaller buffers it owns are `malloc`ed and kept for the process.
- Files: reads only its optional `Extensions\wxl-modern-m2\wxl-modern-m2.cfg` and the environment
  (through the core's `common/ExtensionConfig.hpp`, read-only), and tests one sentinel file's
  existence. Its `Storage.FileOpen` hook (`src/load/LodModelVariant.cpp`) only renames a request
  carrying a `$LODnn` marker, which nothing in our client makes; every other open passes untouched,
  through the client's own storage.
- Device: one vtable pointer swap, `DrawIndexedPrimitive` (`src/render/M2Draw.cpp:300-305`), through
  the core's `wxl::mem::SwapPointer`, re-applied on the core's world-render cadence. It publishes
  `wxl.m2draw` for other extensions; we ship none that use it.
- Hooks (17, `wxl.json`): every detour calls the client's original, except `M2.Init` for an MD21
  container (its own reader, never a stock model) and `M2.BuildBatchMaterial`, which returns null for
  a shader id with bit 0x8000 and index above 3 (a known client crash). Shadow and doodad draws may be
  split into several native calls; a fault inside the shadow original is swallowed and that batch is
  not drawn.
- Shaders: `src/render/shaders/*.h` are real D3D9 bytecode (ps_3_0, vs_3_0) matching their `.hlsl`,
  used only for batches tagged in `Skin::Rebuild`, which runs for MD21 models alone. They are created
  once per session; after a device recreate a tagged batch would bind the old device's shaders. Inert
  here, since we ship no MD21 model; named in case one ever ships.

## What it changes on stock models (the designer's check, docs/test-diablocraft-z2k69.9.md)

1. Bone split at skin finalize: a submesh with more than 75 bones gets its skin arrays rebuilt and
   batches duplicated (`src/compat/ModernM2.cpp:82-90`, `BoneBudget.cpp`); under `character\` and
   `item\objectcomponents\` a section's `level` reads as high index bits.
2. The draw start index of a skin section whose `level` is nonzero is rewritten to
   `(level << 16) | indexStart` (`src/render/M2Draw.cpp` `ExpandM2StartIndex`).
3. Shadow pass: over-budget draws split, the zero-base-vertex path forced when the stream gives a
   nonzero base, and a section with `boneInfluences == 0` lifted to 1, which picks another shadow
   program (`src/render/BonePalette.cpp`, `ShadowSpace.cpp:97-99`). Upstream marks the split "not yet
   fully verified".
4. Doodad batches split into chunks when bones times run length exceed 75.
5. Particle emitters with blend mode above 6 draw with blend state 12 (screen-add), alpha test off
   (`src/compat/EmitterBlend.cpp:75-81`).
6. Ribbons with three or more textures draw in one combined pass (`Ribbons.cpp:30` with
   `M2Draw.cpp` `DrawRibbonMultiTexture`).
7. Fault fallbacks: a hit-test fault is no hit, a bad opaque-sort key is cleared (pointer order on a
   fault), effect pointers that fault on read are nulled at skin finalize.

Knobs: nothing on this list can be switched off without a rebuild (`kEnabled` is a compile-time
`true`, `src/ExtensionApi.hpp:40`). The one runtime gate is the large-buffer allocator:
`WXL_M2_VIRTUAL_ALLOC=0` in the `.cfg`, or a file `WarcraftXL_m2_virtual_alloc.disable` beside
`Wow.exe`. Without this DLL the client draws exactly as before and the outline draws nothing.

# wowdecomp — the client rebuild spike (E1), built from its pin, not vendored

## What this is

`.github/workflows/client-rebuild.yml` builds the 64-bit `WowClient` target of wowdecomp, a C++
reconstruction of the 3.3.5a client (Wow.exe build 12340), on the Actions runner. Brief:
`azerothcore-wotlk/build/_agent-scratch/client-rebuild-2026-10-15/brief.md`, step E1. Nothing of it is
in this repo: the job checks out the pinned commit, and `reference/wowdecomp` stays an untracked copy.
Nothing ships from this build; the artefact is for the designer's E2 run on his PC.
Torment's edits are patches applied on the pin before the build (`client-extension/wowdecomp/`, its
README); moving the pin means re-making them on the new commit.

- **Upstream:** https://github.com/SatyPardus/wowdecomp.git, branch `main`
- **Commit:** `5d0aafad2cf1df980fb7a7198db6bf5f2a37b3dc` (2026-10-15, "Add special thanks"; the
  repo's only commit when cloned). The workflow's `WOWDECOMP_COMMIT` must name it; its first step
  refuses to run when this file does not. If upstream rewrites history and the commit disappears, the
  checkout fails; it never builds another commit.
- **Build:** `windows-latest` with no `-G`, so cmake takes the image's Visual Studio 18 2026 (upstream
  documents 2022, but `windows-2025` is now the 2026 image too and has no 2022; run 38914396961 green),
  `-A x64`, `WOWDECOMP_DISABLE_SIGNATURE_CHECKS=ON` (MPQ signing data, `.toc.sig` and the
  GlueXML/FrameXML/AddOn MD5 checks; it leaves the patch, survey and Scan.dll RSA gates below as they are), `WOWCLIENT_CRASH_LOG=ON`, `RelWithDebInfo` with `/OPT:REF /OPT:ICF`.
- **Artefact `client-rebuild`:** `WowClient64.exe`, `XvidDecoder.dll` (the x64 movie decoder the exe
  imports; it replaces the 32-bit DivxDecoder.dll), both PDBs (the crash logger names functions and lines
  from them), both import tables, `build-id.txt` (the BUILD line of each image, the first line the crash log writes), `wowdecomp-commit.txt`, `SHA256SUMS.txt` (every file, by its path in the
  artefact), and `Extensions\wxl-loot-beam\wxl-loot-beam.ini` (the loot beam of patch 0005 reads it there). Artefact
  `client-rebuild-build-log`: the configure and build output.

## Security read (2026-10-16, before it builds)

Read by this lane's worker and two subagents under it: every CMakeLists.txt, `Tools/WowClient`,
`Tools/XvidDecoder`, the two prebuilt libraries, and every network, process, library-load and registry
call site in the x64 build (found by API name, each hit and its callers read). The full reads, with every
site: `azerothcore-wotlk/build/_agent-scratch/client-rebuild-2026-10-15/build-read.md` and
`network-read.md`. Line numbers are at the pin.

### The build

- No fetching: no `file(DOWNLOAD)`, `FetchContent`, `ExternalProject`, outside `include()` or
  `find_package` in any of the 49 CMakeLists. The only `execute_process` (lib.exe making a DivxDecoder
  import library) and the NASM custom commands are Win32-only (`ThirdParty/CMakeLists.txt:140-170`,
  `Engine/Source/SoundEngine/CMakeLists.txt:55-102`).
- Writes outside the build folder: `WowClient64.exe` and `XvidDecoder.dll` go to the checkout's own
  `bin/Win` (`Tools/WowClient/CMakeLists.txt`, `Tools/XvidDecoder/CMakeLists.txt`). No post-build step.
- Each library globs both `Win32/` and `Win64/`; every file in them is fenced by `WOWDECOMP_ARCH_32` or
  `_64`, so only `Win64/` code is in this build. FMOD Ex, ogg/vorbis and FLAC are built from source in the
  tree.

### Prebuilt libraries linked in

- `ThirdParty/nvapi/amd64/nvapi64.lib`, sha256 `901e479e548d41c30688c7481f0c6353c0be7fdee978796d27d87c32e19ce172`,
  into the exe (Gx). NVIDIA's open-source NVAPI stub (`nvapi/README.md`, `nvapi.h:28`): loads
  `nvapi64.dll` from System32. Its `nvSecureLoadLibrary.obj` also carries `nvCreateProcess*` and
  `nvShellExecute*` helpers; nothing in the tree calls them, and `/OPT:REF` drops unreferenced ones (the
  artefact's import table shows the result). The game calls only `NvAPI_Initialize`, `NvAPI_Stereo_*`
  and `NvAPI_GetErrorMessage` (`Engine/Source/Gx/CGxDeviceD3d/CGxDeviceD3d.cpp:2555-2617`).
- `ThirdParty/xvidcore/lib/x64/libxvidcore.lib`, sha256 `be95947a0d7b3bb6f362bfd5d361ce220c30489b20bc8604c4e3383b286de368`,
  into `XvidDecoder.dll`. Xvid 1.3.7 (`include/xvid.h:60`), built with MSVC 14.34; its object paths
  match a ShiftMediaProject build (an inference from the paths; the tree names no source). Imports: CRT,
  `GetSystemInfo`, `Sleep`, and stdio file calls in the encoder plugins and a debug dump the decoder shim
  never calls. No network, process, registry or library-load import.
- `Tools/XvidDecoder/XvidDecoder.cpp`: a shim from the old DivxDecoder API to `xvid_decore`; no file,
  registry, process, network or library-load call.

### The crash logger (`Tools/WowClient/crash_log.cpp`)

Opens a console window on every start and writes `WowClient_crash.log` beside the exe (deleted and
recreated each start, `:133-146`); a first-chance vectored handler logs faults with a 24-frame stack, so it
also logs faults the client handles itself. Uploads nothing; no network, registry or process call. Its
symbol lookup honours `_NT_SYMBOL_PATH` if the machine sets one.

### Network: what the client connects to

Stays on the realmlist server and the addresses it hands out:

- Login (grunt) to the `realmList` cvar from `realmlist.wtf` (`WoW/Source/WowServices/Win64/WowConnection.cpp:672-735`);
  with no realmlist set, the built-in default is `us.logon.worldofwarcraft.com:3724`
  (`ClientServices_CVar.cpp:59`).
- The world server from the realm list (`ClientServices.cpp:1198`, `NetClient.cpp:351`); a redirect is
  checked against the session key (`NetClient.cpp:836-871`).
- Patch and survey transfer and the hardware survey ride the login connection, only when the server asks;
  a pushed patch or Survey.dll runs only if Blizzard's RSA key signs it (`PatchDownloadGlue.cpp:345-353`,
  `SurveyDownloadGlue.cpp:173-186`), which no private server can.
- Voice chat (UDP) is off by default (`EnableVoiceChat` 0); on, it sends only to the server's roster
  addresses (`Player_C.cpp:14647-14692`).
- Warden on x64 is a stub that discards `SMSG_WARDEN_DATA` and runs no module
  (`Game/GameClient/Win64/WardenClient.cpp`).

**Leaves the realmlist without the server or the player asking: the brief's rule fails as built.**
These are the stock client's own calls (the code is a reconstruction of it), with the URLs taken from
GlueStrings; Torment's own `client-patch/art/Interface/GlueXML/GlueStrings.lua` carries Blizzard's:

- At the login screen, an HTTP GET of `SERVER_ALERT_URL`, `http://launcher.worldofwarcraft.com/alert`
  (`WoW/Source/Glue/CGlueMgr.cpp:771-777` through `Engine/Source/Os/Win64/OsURLDownload.cpp`; GlueStrings.lua:789).
- At startup, a GET of `LATEST_AGREEMENTS_URL`, `http://launcher.worldofwarcraft.com/legal/agreements.mpq`
  (`CGlueMgr.cpp:534-541,1080`; GlueStrings.lua:487).
- If the login GlueXML calls `ScanDLLStart`: GETs of `us.scan.worldofwarcraft.com/update/Launcher.txt` and
  `Scan.dll` (`ScanDLLGlue.cpp:254-305`; GlueStrings.lua:773,775); Scan.dll loads only if Blizzard-signed
  (`CheckExecutableSignature.cpp:41-42,135-160`). Not checked: whether the GlueXML our client loads calls it.
- If the login server sets bit 0x1 of the login flags: GETs to `support.worldofwarcraft.com` carrying the
  account name and a hash derived from the session key (`CGlueMgr.cpp:1805`, `CAccountMsgHeaders.cpp:149,195`,
  `CAccountMsgBody.cpp:50`; GlueStrings.lua:51-55). Not checked: whether AzerothCore's authserver sets it.

On a player's action or a special file only:

- The in-game Help frame's knowledge base, to hardcoded Blizzard support hosts (`KnowledgeBase.cpp:501-523`),
  reachable from any Lua.
- `LaunchURL` / `LaunchAddOnURL` hand any string to `ShellExecuteA("open")` with no scheme check
  (`Engine/Source/Os/Win64/System.cpp:454-525`), from glue Lua; with signature checks off, glue Lua is
  whatever the MPQs carry.
- An account name with `@` takes the Battle.net login, which loads `Battle.net.dll` by bare name from the
  DLL search path with no signature check (`ClientServices.cpp:836-848`, `Battlenet/Tumor/CreepTendril.cpp:38-50`);
  its host comes from that DLL.
- A `WoW.mfil` manifest beside the exe turns on trial streaming and its tracker,
  `http://us.tracker.worldofwarcraft.com:3724/announce` (`Tracker.cpp:73,311-370`); no Torment client has one.
- A fatal error starts `WowError.exe` from the game folder (`Client.cpp:2000-2008`; on by default through
  the registry value it writes, `Client.cpp:1817-1827`); `QuitGameAndRunLauncher()` starts `Launcher.exe`
  (`CGlueMgr.cpp:291-293`). The client opens no socket for either; what they send is theirs.

Compiled in and unreachable: FMOD's profiler listen socket and net streaming, the `OsTcp` layer, the
connection's accept path, Lua's `os.execute`/`io.popen`/`package.loadlib` (the one Lua state opens base,
string, table, math and bit only, `FrameScript.cpp:1136-1158`).

### Registry and files outside the game folder

Writes under `HKCU\Software\Blizzard Entertainment\World of Warcraft` (`SendErrorLogs`, `MoveLogFile`,
four hardware indices; `Client.cpp:431,1819`, `ConsoleDetect.cpp:154-157`) and tries
`HKLM\...\InstallPath` (fails without admin; `Client.cpp:842-844`). Outside the game folder it writes only
an empty `%TEMP%\TempHTMLFile<n>.html` while finding the browser for a URL, deleted at once.

### Not covered

The 2,723 source files were searched by API name, not read line by line. Not read: `Battle.net.dll`,
`WowError.exe`, `Launcher.exe`; which GlueXML the client loads from the base MPQs; what AzerothCore's
authserver sends in the login flags; the Win32 build and the `Wow` target; the xvidcore objects beyond
symbols and strings. The exe's real import table is in the artefact, from the first green run.
