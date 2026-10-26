# Parked client files: never packed

`build.sh` packs only `dbc/` and `art/`. Files here are kept for reference and for their tests and are not in any
archive.

`GlueXML/CharacterCreate.lua` is the create-screen class lock of `diablocraft-race-class-unlock`. The 3.3.5 client
signature-checks `Interface\GlueXML` (and `Interface\FrameXML`) and answers an edited file with "Your login
interface files are corrupt. Please reinstall the game." (Nightly 52, 2026-10-02). It must not return to
`client-patch/art/` unless the client itself is patched to skip the check. `build.sh` and `manifest.py check_mpq` both
refuse such a file unless the release ships a build whose pin in `launcher/engine/src/allow.rs` PINNED carries the
glue-unlock flag: the rebuilt `WowClient64.exe`, built with the signature checks off (`build.sh --client-rebuild <dir>`). Without `--client-rebuild`, `build.sh` uses the artefact of the client-rebuild CI run `client-patch/glue_unlock_run` names (the run whose WowClient64.exe carries the flag; update that file with the pin), kept in `azerothcore-wotlk/build/_agent-scratch/client-rebuild-run<id>/` and fetched there with `gh run download` when missing.

Option C (the designer, q-1001-37) locks the classes with `CharBaseInfo.dbc` instead, so this file has no test and is
reference only for the parked option B (a client that skips the check).
