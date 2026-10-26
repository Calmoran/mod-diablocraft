# client-extension/install — the dev install script

By-hand install of the client extension on the designer's dev client (brief C3). It writes **tswow's
loader patch** onto a stock 3.3.5.12340 `Wow.exe` so the client loads `WarcraftXL.dll`
(tswow's loader + `wxl-core`, D1 A). The player-facing delivery is the launcher's bead (C4);
this changes no launcher.

## What it writes

The exact bytes are tswow's, not ours — `reference/tswow/tswow-scripts/util/ClientPatches.ts:137-162`:

| file offset | what |
|---|---|
| `0x28E19C` | the 6-byte jump into the code cave (replaces the client's own `LoadLibraryA`) |
| `0x3738B8` | the cave: call `LoadLibraryA` on the name below, then jump back |
| `0x5E2A71` | the 20-byte DLL-name field, set to `WarcraftXL.dll` |

The name replaces tswow's `ClientExtensions.dll`; the two offsets apply to the designer's exe unchanged,
because it is byte-for-byte tswow's known clean build — its MD5 is tswow's `CLEAN_CLIENT_MD5`
(`reference/tswow/tswow-scripts/runtime/Client.ts:32`).

## Run it

```
python3 patch_wow.py /path/to/Wow.exe
```

It computes the exe's SHA256 and **refuses any exe whose hash is not on its known list**,
printing the hash it saw so the list can be extended. On a match it keeps the untouched exe
beside the patched one (`Wow.exe.orig` next to `Wow.exe`) and patches `Wow.exe` in place — the
same order tswow uses (`Client.ts:190` copies the exe to a `_clean` file first).

The known list is `KNOWN` at the top of `patch_wow.py`, keyed by SHA256 (the check); the MD5 is
kept beside it only to recognise the build by hand. The first entry is the designer's stock client:

- SHA256 `aa63a5750d60ef16746c686b3d5e26876d98953eab08b1c026cd0faf78e88cb8`
- MD5 `45892bdedd0ad70aed4ccd22d9fb5984` (== tswow `CLEAN_CLIENT_MD5`)

Its expected result is in `PATCHED`: the designer's exe patched by this script has SHA256
`ef091efc80718c7c9da4f06b3b6b3ddf6679dd7dcd5e890b6dfa31919580f828`. The script checks the patched
image against it before writing anything and refuses a different result.

To add another stock client, add its SHA256 (the script prints it) to `KNOWN` and re-run.

## The test

```
python3 test_patch_wow.py
```

It works on a **synthetic byte buffer**, never a real `Wow.exe`: it proves the offsets and the
exact bytes written, that the loader patch is internally consistent (the stage jump lands in the
cave, the cave jumps back to just after the stage), that an exe with any other hash is refused
(nothing written), that the CLI prints the hash it saw, and that the untouched copy is kept.

It is run by hand for now: `run_tests.py` discovers only `mod-diablocraft/scripts/test_*.py`, and
the client-extension CI workflow lives on C1a's branch (`diablocraft-z2k69.1`), so wiring this test
into CI belongs to a later bead.

Nothing here runs against a real `Wow.exe` on the Linux box; only the test's buffer does.
