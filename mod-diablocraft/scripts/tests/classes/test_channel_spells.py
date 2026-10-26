"""The addon's channelled-skills list equals the server's channel data (diablocraft-vz49.1).

client-patch/addons/Torment/ChannelSpells.lua is the list the channel observer watches. The server
reads the same set as data: every spell with a channel_tick_frames_count row in
data/generated/spell_value_map.csv is a channel the module ticks (dc_combat_resolve.cpp WizardChannel,
Whirlwind's own shells). A new channel rune that reaches the sheet but not the list would never stop
on release; a spell on the list that is no channel would be stopped by a key let go. Archon's
Disintegration Wave (83276) is the one deliberate gap until the designer rules whether it holds.
"""
import csv
import re
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
LIST = REPO / "client-patch/addons/Torment/ChannelSpells.lua"
SHEET = MODULE / "data/generated/spell_value_map.csv"
TOC = REPO / "client-patch/addons/Torment/Torment.toc"
ARCHON_WAVE = 83276


def listed():
    return {int(i): n for i, n in re.findall(r'\[(\d+)\]\s*=\s*"([^"]+)"', LIST.read_text(encoding="utf-8"))}


def sheet():
    with SHEET.open(encoding="utf-8", newline="") as f:
        return {int(r["spell_id"]): r["skill"] for r in csv.DictReader(f) if r["token"] == "channel_tick_frames_count"}


class ChannelSpells(unittest.TestCase):
    def test_the_list_is_the_sheets_channels_but_archon(self):
        rows = sheet()
        self.assertIn(ARCHON_WAVE, rows, "the sheet still carries Archon's wave, so the gap below is real")
        self.assertGreater(len(rows), 20, "read the real sheet, not an empty one")
        self.assertEqual(sorted(set(rows) - {ARCHON_WAVE}), sorted(listed()))

    def test_each_rune_names_its_skill(self):
        # The sheet's skill column is the skill's name; a rune row reads "<skill> <rune>" or the bare skill.
        for spell, skill in listed().items():
            self.assertTrue(sheet()[spell].startswith(skill), (spell, skill, sheet()[spell]))

    def test_the_toc_loads_the_list_before_its_reader(self):
        files = [l.strip() for l in TOC.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
        self.assertIn("ChannelSpells.lua", files)
        self.assertIn("ChannelObserver.lua", files)
        self.assertLess(files.index("ChannelSpells.lua"), files.index("ChannelObserver.lua"))
        self.assertNotIn("Whirlwind.lua", files)


if __name__ == "__main__":
    unittest.main()
