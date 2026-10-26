# client-extension/wowdecomp

Torment's source edits to the rebuilt client. wowdecomp itself is not in this repo: both workflows check out
the commit pinned in `PINNED.md` ("wowdecomp") and apply what is here on top. `reference/wowdecomp` stays an
untracked reading copy.

- `patches/`: the series every rebuilt client is built with. `.github/workflows/client-rebuild.yml` applies
  each `*.patch` in file-name order (`apply-patches.ps1`) before it builds, and fails when one does not apply at
  the pin. The artefact's `wowdecomp-commit.txt` lists the series it was built with.
- `probes/`: compile probes, never shipped (none now: K0's retype probe made its edits for real in `0010` and the K4 patch, and was removed). `.github/workflows/client-rebuild-probe.yml` compiles the pin with
  the series and again with the series plus every probe, and lists the diagnostics the probes add. A probe edits
  lines in place and moves none, so the two lists compare line for line.
- The series today: `0001` hits unsigned to the text (the -1 fix); `0002` the Lua globals `TormentKeyDown`,
  `TormentDamageTextRead` and `TormentWorldToScreen` (the Torment module's jobs, its key table and damage text queue
  carried as copies); `0003` class ids past the stock ten (the module's race/class and role patches); `0004` the
  engine's render hooks (`Engine/Source/Gx/RenderHooks.h`) and the unit outline on them, which also replaces
  wxl-modern-m2's one job, the model-batch draw event; `0005` the loot beam; `0006` the login version proof
  taken over the exe file on disk, so it holds under ASLR (`login-mark.md`). `0007` the nameplate class colours past the Druid: `s_classColors` grows to class id 14 (the Witch Doctor) with the class colour sheet's hex (`mod-diablocraft/data/class_colours.csv`), and a class id past it takes the hostile colour instead of the bytes after the table (`tests/test_nameplate_class_colours.py`). `0008` class powers: a player whose class has a
  row in `class_power_tokens.h` reports the row's token for that slot (`UnitPowerType`, the tooltip cost line, the
  not-enough-power text) and shows its true points (`UnitPower`, `UnitPowerMax` and costs divide by the row's storage scale, not the stock tenth),
  and a class power's slots, a second one included, move on the client at the slot's own
  regeneration fields, negative for decay (`docs/contracts/class-powers.md`, `tests/test_class_power_tokens.py`). `0009` the crash log's first line names the build (`BUILD WowClient64.exe timedatestamp=… sizeofimage=… pdb=… guid=… age=…`). `0010` Life in 64 bits (K3 of the client 64-bit numbers, `docs/contracts/life-64bit-wire.md`): `m_unitFieldHealth` and `m_unitFieldMaxhealth` read as 64 bits through `UnitWideField` (the stock low dword in place, the new high dword at the end of the unit block), the unit block grows to 150 dwords, the player's fields start two dwords later, and the Life change handlers, bars and Lua readers take the whole value (`tests/test_life_64bit_fields.py`). `0011` exact hits in 64 bits (K4, `docs/contracts/life-64bit-wire.md`): the two damage parsers (`SMSG_SPELLNONMELEEDAMAGELOG`, the damage ticks of `SMSG_PERIODICAURALOG`) read the 64-bit hit and overkill, and the floating number, the combat text, the portrait, the combat log and the addon's damage-text queue carry it whole (`tests/test_exact_hits_64bit.py`). `0012` the out-of-range party member's power through the class row's storage scale (`UnitPower`, `UnitPowerMax`; `docs/contracts/class-powers.md`, `tests/test_class_power_tokens.py`).
  The module ports keep their upstream
  licence headers and name the commit they come from.
- `version_seed.py`: the authserver's version seed for a client build, the value `build_info.winChecksumSeed`
  must hold for `StrictVersionCheck` to let it log in (the login mark: `login-mark.md`). It ports the client's own
  checksum walk (`ChecksumExecutables.cpp`, `Win64/OsVersionHash.cpp`) and runs it on the exe file. On the designer's stock
  12340 client it gives AzerothCore's stock seed (`test_version_seed.py`, `TORMENT_STOCK_CLIENT`).
- `seed-probe/`: the version-proof probe `client-rebuild.yml` builds and runs: the series' own
  `OsVersionHash.cpp` in a tiny ASLR exe, whose hashed bytes `check_proof.py` compares with `version_seed.py`'s
  walk over the exe file; the run fails when they differ (`version-proof-probe.txt` in the artefact).
- `build_id.py`: the build id and the private PDB store (ruling 2026-10-20, `diablocraft-fjy88`). The PDBs never ship to
  players; a crash log carries `WowClient64.exe+0x<offset>` and the names come from the PDB of that exact build, so each
  shipped build's PDBs are kept outside the repo, in `$TORMENT_PDB_STORE` or `~/.local/share/torment/client-pdb/`, one
  folder per build named `<TimeDateStamp>-<SizeOfImage>`, never replaced once stored. After a build ships (the exe is
  pinned in `launcher/engine/src/allow.rs`), on the box that publishes: download the run (`gh run download <run> -n
  client-rebuild -D <dir>`), then `python3 client-extension/wowdecomp/build_id.py add <dir> --run <run>`. To read a crash:
  `build_id.py find <WowClient_crash.log>` prints the stored PDB for the log's first line. `build_id.py shipped` fails
  while a pinned exe or decoder has no stored PDB: run it before a launcher publish. CI runs `check` on every build (the
  exe was linked with `/debug`, the PDB beside each image is that exact link) and writes `build-id.txt` into the artefact.
  Tests: `tests/test_build_id.py`, which compiles patch 0009's C++ on Linux and compares its line with this tool's.
- `apply-patches.ps1`: applies one folder's patches to a checkout, through the index, so the runner's CRLF
  checkout does not matter.
- `copy-generated.ps1`: copies the generated files the series includes into a checkout's `Torment/` folder (its
  include root): `mod-diablocraft/data/generated/class_power_tokens.h`, which the class resources generator writes.
  Both workflows run it after the patches; a change to the table rebuilds the exe.
- `.gitattributes`: patches are kept byte for byte (`-text`).

## Writing a patch

1. Clone the pin to a scratch folder: `git clone reference/wowdecomp <scratch>` and check `git rev-parse HEAD`
   is the pin. If the series is not empty, apply it first: `git -C <scratch> apply patches/*.patch` in order,
   then `git -C <scratch> commit -am series`.
2. Make the edit, then `git -C <scratch> diff > client-extension/wowdecomp/patches/NNNN-<what it does>.patch`.
   `NNNN` is the next free number; one patch per purpose, named for what it changes (no bead id or date).
3. `python3 client-extension/tests/test_wowdecomp_patches.py` checks that the series, then the probes, apply at
   the pin (it needs `reference/wowdecomp` at the pin; it skips without it).

A later patch is made on top of the earlier ones, so the series applies in order. Moving the pin means
re-making every patch on the new commit, in the same change as the new pin.
