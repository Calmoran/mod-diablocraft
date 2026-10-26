# Addons shipped to players

| Folder | Whose | Notes |
|---|---|---|
| `Torment/` | ours | The screens with no stock WoW equivalent. |
| `ElvUI_Torment/` | ours | ElvUI companion addon; skeleton now carries the padded D3 bottom-bar art and its LibSharedMedia registration. Replaces `Roth_UI` + `Bartender4` when the build lands. |
| `Roth_UI/` | third party, MODIFIED by the designer | Galaxy's oUF layout with Diablo flavour, 3.3.5a-test.8. Carries its own `LICENSE.txt`; keep it. Its `rActionBarStyler` REUSES the stock ActionButtons and hides `MainMenuBar`, so anything of ours that touches the action bar shares frames with it. |
| `Bartender4/` | third party | the designer uses it to hide the bag bar and move the micro-menu. |
| `ElvUI/` | third party | Not in this repo or on Torment's download host. The launcher installs ElvUI-WotLK 6.09 unmodified, straight from its GitHub (decisions.md 2026-09-24, `docs/proposals/launcher.md` §2). |


Tracked here from 2026-09-17 because the designer's modified copies existed only on his
Windows client: decisions.md 2026-09-17 "The live client runs a MODIFIED RothUI plus
Bartender4". The uploads they came from are in `reference/addons/live/` with his `WTF`
settings; `reference/addons/rothui/` is the untouched upstream package for comparison.

Players get one archive containing all three folders, not three downloads. Nothing is
merged into `Torment/`: these keep their own identity, licences and update path.
