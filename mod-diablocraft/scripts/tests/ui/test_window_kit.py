"""The windows on the shared Torment look build from the kit (diablocraft-5mxi; brief
docs/briefs/builds-on-brief.md item 5).

For each window below, (a) the file calls no SetBackdrop( of its own: its panels come from DCUI
(dc_aio_ui.lua); (b) its window frame is made by U.window(. The Mystic broke (a) before round 3
(diablocraft-2unu) by drawing its own tan panels. When R1 moves the next window (tier select, the
Skills window), that window joins WINDOWS as part of its move.

The code is read with its comments stripped, so a comment that names SetBackdrop does not count.
Run from anywhere: `python3 mod-diablocraft/scripts/tests/ui/test_window_kit.py`.
"""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
AIO = REPO / "mod-diablocraft/lua/aio"
WINDOWS = ("dc_blacksmith.lua", "dc_jeweler.lua", "dc_paragon.lua", "dc_crafting.lua")


def code(path):
    """The Lua source without comments: block comments, then line comments."""
    text = path.read_text(encoding="utf-8-sig")
    text = re.sub(r"--\[(=*)\[.*?\]\1\]", "", text, flags=re.S)
    return re.sub(r"--[^\n]*", "", text)


class WindowKit(unittest.TestCase):
    def test_no_backdrop_of_its_own(self):
        for name in WINDOWS:
            with self.subTest(name):
                self.assertFalse("SetBackdrop(" in code(AIO / name),
                                 name + " draws its own panels; take them from DCUI (dc_aio_ui.lua)")

    def test_window_frame_from_the_kit(self):
        for name in WINDOWS:
            with self.subTest(name):
                self.assertTrue(re.search(r"\bframe\s*=\s*U\.window\(", code(AIO / name)),
                                name + " does not make its window frame with U.window(")


if __name__ == "__main__":
    unittest.main()
