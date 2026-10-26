# client-extension

Torment's client extension: tswow's loader patch on a stock 3.3.5a (12340) `Wow.exe` loads WarcraftXL's
`wxl-core` DLL, and our Torment module runs on it (ruling 2026-10-12, D1 A). The lane's rules:
`docs/handoffs/client-extension.md`. The research: `docs/research/client-extension.md`.

- `wxl-core/`: WarcraftXL's core, vendored (`PINNED.md`).
- `torment/`: our module, `Torment.dll`, loaded by wxl-core from `Extensions\Torment\` beside `Wow.exe`. It keeps
  the key state behind the Lua global `TormentKeyDown` (`docs/contracts/client-key-state.md`), and writes tswow's
  three class patches into the client's code at load (`torment/ClassPatches.hpp`; Monk 1c,
  `docs/contracts/monk-class.md`). It hands the engine's own floating damage numbers and words to the addon
  through `TormentDamageTextRead` and `TormentWorldToScreen` (`torment/DamageText.hpp`,
  `torment/DamageTextSites.hpp`; `docs/contracts/damage-text.md`).
- `wxl-unit-outline/`: WarcraftXL's unit outline module, vendored with one Torment patch (`PINNED.md`).
- `wxl-loot-beam/`: the loot beam's client half, vendored with Torment's patches and `.ini` (`PINNED.md`); the
  server sends each player their own tier (`docs/contracts/loot-beam-tier.md`).
- `wxl-modern-m2/`: WarcraftXL's M2 module, vendored as-is (`PINNED.md`): it fires the model-draw event the
  outline needs.
- The three `wxl-*` modules are no longer built by `client-extension.yml`: the rebuilt client carries their jobs as
  source (`wowdecomp/patches` 0004, 0005). Their folders stay as the source the patches were ported from, and
  `wxl-loot-beam.ini` ships with the rebuilt client.
- `wowdecomp/`: Torment's source edits to the rebuilt client, kept as patches on the wowdecomp pin, and the
  compile probes (`wowdecomp/README.md`).
- `tests/`: the module's unit tests (the key table, the damage text queue), built and run by the CI job, and
  `test_class_patches.py` (the class patch sites against tswow, wxl-core and the core's Warden checks) and
  `test_damage_text_sites.py` (the damage text sites against reference/wowdecomp and the Warden checks), run by hand, and
  `test_wowdecomp_patches.py` (the wowdecomp patches and probes apply at the pin), run by hand.

Nothing here builds or runs on the Linux box; `.github/workflows/client-extension.yml` builds it on
`windows-latest`.
