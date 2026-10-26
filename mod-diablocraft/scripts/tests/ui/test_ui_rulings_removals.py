"""The removals of the 2026-10-03 UI rulings (diablocraft-ui-rulings; brief items 2, 3a, 3b).

R2: the Mystic has no "Repair all" button of its own; repair lives at the Blacksmith.
R3a: dc_crafting.lua holds no old Blacksmith screen (gate, Recipes/Quote/Balance handlers,
     Salvage/Craft tabs), so a failed dc_blacksmith load cannot bring it back.
R3b: the 09-15 client shell (Torment/Blacksmith.lua/.xml, /dcblacksmith) is gone, with its
     TOC lines, and nothing left in the addon or the AIO files names any piece of it.

Each check reads the code with its comments stripped, so a comment that records the history
does not count as a caller. The runtime side (a Blacksmith gossip with dc_blacksmith missing
draws nothing) is pinned in test_crafting.lua.
Run from anywhere: `python3 mod-diablocraft/scripts/tests/ui/test_ui_rulings_removals.py`.
"""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
AIO = REPO / "mod-diablocraft/lua/aio"
ADDON = REPO / "client-patch/addons/Torment"
CRAFTING = AIO / "dc_crafting.lua"


def code(path):
    """The Lua source without comments: block comments, then line comments."""
    text = path.read_text(encoding="utf-8-sig")
    text = re.sub(r"--\[(=*)\[.*?\]\1\]", "", text, flags=re.S)
    return re.sub(r"--[^\n]*", "", text)


def lua_files():
    return sorted(AIO.glob("*.lua")) + sorted(ADDON.glob("*.lua"))


class MysticRepair(unittest.TestCase):
    def test_no_repair_button(self):
        self.assertNotIn('"Repair all"', code(CRAFTING), "the Mystic still draws its own Repair all")

    def test_window_sends_no_repair(self):
        source = code(CRAFTING)
        self.assertIsNone(re.search(r'send\(\s*"repair"', source), "the Mystic window still sends repair")
        self.assertIsNone(re.search(r'Mystic\.Send\(\s*"repair"', source), "the reborn window still sends repair")

    def test_window_puts_only_the_contracts_verbs_on_the_wire(self):
        # diablocraft-0atm: the window is wired to docs/contracts/mystic-enchant-messages.md. Its one
        # send point carries place, preview, roll and pick - the old offer/choose/quote verbs and the
        # DCMYSTIC wire are gone - and the only literal message left is the Transmogrify tab's.
        source = code(CRAFTING)
        self.assertEqual(re.findall(r'SendAddonMessage\(\s*"([A-Z]+)"\s*,\s*"([a-z-]+)"', source),
                         [("DCARTISAN", "transmog")], "the only literal send is the Transmogrify tab's")
        self.assertEqual(sorted(re.findall(r"^\s*(\w+) = \{\{1, ", source, re.M)),
                         ["pick", "place", "preview", "roll"], "the four verbs of the contract")
        for gone in ("offer", "choose", "quote"):
            self.assertIsNone(re.search(r'\(\s*"' + gone + r'"', source),
                              "the retired verb " + gone + " is still called")
        self.assertNotIn("DCMYSTIC", source, "the retired quote wire is still handled")


class OldBlacksmithScreen(unittest.TestCase):
    def test_no_old_handlers(self):
        source = code(CRAFTING)
        for name in ("Recipes", "Quote", "Balance"):
            self.assertIsNone(re.search(r"function\s+handlers\." + name + r"\b", source),
                              "dc_crafting.lua still answers " + name)
        self.assertNotIn("DCCraftingResponses", source, "the old stage-1 response store is still kept")

    def test_no_old_gate_or_recipe_reads(self):
        source = code(CRAFTING)
        self.assertIsNone(re.search(r"local\s+function\s+blacksmith\b", source), "the old Blacksmith gate is still there")
        self.assertNotIn("recipeData", source, "the old recipe list is still built")
        self.assertNotIn("dc_blacksmith_recipe", source, "the old recipe table is still read")
        self.assertNotIn("maxCraftCount", source, "the old Show still carries a craft count")

    def test_no_old_tabs_or_actions(self):
        source = code(CRAFTING)
        for tab in ('"Salvage"', '"Craft"'):
            self.assertNotIn(tab, source, "the old Blacksmith tab " + tab + " is still drawn")
        for verb in ("craft", "salvage", "bulk"):
            self.assertIsNone(re.search(r'send\(\s*"' + verb + '"', source), "the window still sends " + verb)

    def test_blacksmith_gossip_reaches_only_the_new_window(self):
        # The context string still routes the Blacksmith's gossip, but only to dc_blacksmith.
        self.assertIn("DCBlacksmithServer.Show(player)", code(CRAFTING))


class ClientShell(unittest.TestCase):
    def test_files_gone(self):
        for name in ("Blacksmith.lua", "Blacksmith.xml"):
            self.assertFalse((ADDON / name).exists(), name + " is still in the addon")

    def test_toc_lines_gone(self):
        toc = (ADDON / "Torment.toc").read_text(encoding="utf-8-sig").splitlines()
        loaded = [line.strip() for line in toc if line.strip() and not line.lstrip().startswith("#")]
        for name in ("Blacksmith.lua", "Blacksmith.xml"):
            self.assertNotIn(name, loaded, "Torment.toc still loads " + name)
        self.assertNotIn("Bs_OnLoad", "\n".join(toc), "a TOC comment still describes the shell")

    def test_nothing_names_the_shell(self):
        shell = re.compile(r"/dcblacksmith|DIABLOCRAFTBLACKSMITH|DiablocraftBlacksmith[A-Z]\w*|\bD(?:C|iablocraft)\.Bs[A-Z_]\w*")
        hits = []
        for path in lua_files():
            for match in shell.finditer(code(path)):
                hits.append("%s: %s" % (path.relative_to(REPO), match.group(0)))
        for path in sorted(ADDON.glob("*.xml")):
            for match in shell.finditer(path.read_text(encoding="utf-8-sig")):
                hits.append("%s: %s" % (path.relative_to(REPO), match.group(0)))
        self.assertEqual(hits, [], "a removed shell piece is still named")


if __name__ == "__main__":
    unittest.main(verbosity=2)
