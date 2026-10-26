# The login mark: only the rebuilt client logs in

Torment refuses every client but its own rebuilt 64-bit one at login: the authserver's `StrictVersionCheck` on,
and `build_info`'s Windows seed for build 12340 set to the rebuilt exe's own version proof. The one client change
is patch 0006, which takes that proof over the exe file on disk so it holds under ASLR (below; the designer's ruling
2026-10-16, card q-1016-22, option B "Source patch, keep ASLR"). A stock or loader-patched `Wow.exe` then fails with the stock "version invalid" answer, and the launcher's
own text tells the player to start the game from the launcher (Settings, Game folder).

Server config is the PM's to apply; this file gives the values and the steps. The authserver and `acore_auth` are
shared by dev and live (the `dev-realm` skill), and the authserver is the designer's to stop and start (`docs/handoffs/pm.md`).

## How the check works

- At login the client sends SHA1(A, checksum). The checksum is an HMAC-SHA1 keyed by the authserver's fixed
  16-byte challenge over the client's own image, `DivxDecoder.dll` as loaded and `unicows.dll` read from the
  game folder (wowdecomp `ChecksumExecutables.cpp`). With patch 0006 the client's own image is its exe file laid
  out as the loader maps it, not the loaded copy.
- With `StrictVersionCheck` on, the authserver computes SHA1(A, seed) from `build_info.winChecksumSeed` and refuses a
  mismatch with `WOW_FAIL_VERSION_INVALID` (`AuthSession::VerifyVersion`). An all-zero seed lets every client in.
- `build_info` is read once, when the authserver starts (`RealmList::Initialize`): a seed change needs an
  authserver restart.
- The 64-bit client loads `XvidDecoder.dll`, never a module named `DivxDecoder.dll`, so its proof covers its exe
  and `unicows.dll` only.

## The seed of a build

`version_seed.py` computes it from the client-rebuild artefact, with the stock `unicows.dll` of a 3.3.5a folder
(sha256 `22f23cc65698741184ec34f46e6f69717644e0b5aabf5d5bd015101f2d72e56e`; no Blizzard file is in the repo):

```
gh run download <client-rebuild run> -n client-rebuild -D <dir>
sha256sum <stock folder>/unicows.dll        # must be 22f23cc6...e56e
python3 client-extension/wowdecomp/version_seed.py --exe <dir>/WowClient64.exe --unicows <stock folder>/unicows.dll
```

Check the run's `version-proof-probe.txt` first: it says the patched checksum code, run on an ASLR-moved exe,
hashed exactly the walk over that exe's file (`check_proof.py`; the run fails otherwise).

### The pinned build's seed

client-rebuild run 39975784168 (nightly cba2f4cb6, patches 0001-0009), the build `allow.rs` pins (launcher 0.1.14):
WowClient64.exe sha256 `a66e1e86...abb4`, with the stock `unicows.dll`, gives

    F8C53EFE6B5FAC6605259DCA4F5AC4220929B6F0

Its `version-proof-probe.txt`: the probe loaded at `0x7ff702310000` (moved from the preferred `0x140000000`; the loader writes the new base into the
in-memory header), and both runs hashed exactly the file walk (40960 bytes). The earlier pins' seeds: run 38972807183
(launcher 0.1.12, exe `e3ca3ce0...c179752`) `7059FC6801E5496B00A9215623E15133B5A8594B`; run 39709396181 (0.1.13, exe
`e3b83840...f0103`) was not recorded here and its artefact is not kept in the shared scratch folder.

The tool is checked against Blizzard's own computation: the designer's stock 12340 client (Wow.exe sha256
`aa63a575...8cb8`, with its DivxDecoder.dll and unicows.dll) gives `CDCBBD5188315E6B4D19449D492DBCFAF156A347`,
the seed AzerothCore ships for 12340 (`test_version_seed.py` with `TORMENT_STOCK_CLIENT`).

### Why the proof is taken over the file (patch 0006)

client-rebuild run 38957889090 (its image-base probe, two runs on windows-latest):
`loaded_at=0x7ff7ca210000 header_image_base=0x7ff7ca210000 file_image_base=0x140000000`. Windows writes the
load address into an ASLR-moved exe's in-memory ImageBase, so the client's walk over its loaded image sees no
move, puts nothing back, and hashes the relocated bytes and the moved base. The proof then followed the load
address, which ASLR picks again for each boot, and no `build_info` seed could hold. The stock 32-bit Wow.exe never
moves (no ASLR, base 0x400000), which is why the stock seed holds.

Patch 0006 (`Engine/Source/Os/Win64/OsVersionHash.cpp`) hashes the program itself from its file: it reads the
exe named by `GetModuleFileNameW`, lays the headers and each section's data out at their RVAs, and runs the same
walk with nothing to put back. That is the image the exe has at its file base, on every boot, and the walk
`version_seed.py` runs on the file. WowClient64.exe keeps ASLR (DllCharacteristics 0x8160). `DivxDecoder.dll`
and other named modules are still hashed as loaded, as stock.

## Steps (dev first; live when live returns)

The launcher release that delivers this build and the seed change go out together (K6): from the restart, every
client but the pinned WowClient64.exe is refused, on both realms, since the authserver is shared.

1. Note the current row, to put it back: `SELECT build, winChecksumSeed FROM acore_auth.build_info WHERE build = 12340;`
   (stock: `CDCBBD5188315E6B4D19449D492DBCFAF156A347`).
2. Set the seed of the build the launcher ships (today `F8C53EFE6B5FAC6605259DCA4F5AC4220929B6F0`, above):
   `UPDATE acore_auth.build_info SET winChecksumSeed = '<seed>' WHERE build = 12340;`
3. In `authserver.conf`: `StrictVersionCheck = 1` (the code default is 0).
4. Restart the authserver (the designer's).
5. Check: the rebuilt client logs in; a stock `Wow.exe` gets "version invalid". The authserver log shows nothing for
   a refused version; the client's answer is the check.

Undo: put back the old seed (step 1), `StrictVersionCheck = 0`, restart the authserver.

## Every later client build

MSVC builds are not reproducible, so every client-rebuild run gives another exe and another seed. A new
WowClient64.exe reaches players as a launcher release with its pin (`launcher/engine/src/allow.rs` PINNED), and
its seed goes into `build_info` at the same moment, with an authserver restart: the row holds one Windows seed, so
the old exe is refused from then on and the launcher's update brings the new one.

## What it does not cover

- A game folder without `unicows.dll`, or with another one, sends another proof and is refused. Every stock 3.3.5a
  folder seen has it (three 3.3.5a folders on the designer's PC, all `22f23cc6...e56e`).
- Warden is unchanged (the rebuilt client never answers Warden; `docs/research/client-rebuild.md` §3).
- The macOS seed and other builds' rows are untouched.
