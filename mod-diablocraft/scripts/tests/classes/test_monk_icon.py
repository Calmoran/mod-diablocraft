"""diablocraft-3exia, im7mr.4: the create screen's Monk, Necromancer and Witch Doctor icons (the first two the designer's own art, the third a plain WD until he sends his).

    python3 mod-diablocraft/scripts/tests/classes/test_monk_icon.py

For each class build_icon.py makes (the Monk, the Necromancer, the Witch Doctor): the texture CharacterCreate.lua names for it
(CLASS_ICON_TEXTURE) is a file in client-patch/art that build.sh packs at that path; it is a 64x64 DXT5 BLP2;
build_icon.py rebuilds it byte for byte from the one source image beside it (so a new icon is a one-file swap); and it
decodes, over the create screen's dark backdrop, close to the source.
Not run here: the client's own decoding (no client); the preview PNG on the test sheet is for the designer's eye.
"""
import importlib.util
import re
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True                  # no __pycache__ beside the art source
ROOT = Path(__file__).resolve().parents[4]
ART = ROOT / "client-patch" / "art"
KIT = ART / "Interface" / "Glues" / "CharacterCreate" / "source"
spec = importlib.util.spec_from_file_location("build_icon", KIT / "build_icon.py")
build_icon = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_icon)             # also puts the vendored Pillow on sys.path
from PIL import Image, ImageChops, ImageStat  # noqa: E402


def on_backdrop(image):
    backdrop = Image.new("RGBA", image.size, (24, 20, 18, 255))
    backdrop.alpha_composite(image)
    return backdrop.convert("RGB")


def shipped(token):
    """The one file in client-patch/art the screen names for the class."""
    lua = (ART / "Interface" / "GlueXML" / "CharacterCreate.lua").read_text()
    table = lua.split("CLASS_ICON_TEXTURE = {", 1)[1].split("}", 1)[0]
    path = re.search(rf'\["{token.replace("_", "").upper()}"\]\s*=\s*"([^"]+)"', table).group(1).replace("\\\\", "/") + ".blp"
    return [p for p in ART.rglob("*") if p.relative_to(ART).as_posix().lower() == path.lower()]


class ClassIcons(unittest.TestCase):
    def test_the_classes(self):
        self.assertEqual(build_icon.CLASSES, ("monk", "necromancer", "witch_doctor"))

    def test_named_and_shipped(self):
        for token in build_icon.CLASSES:
            with self.subTest(token):
                matches = shipped(token)
                self.assertEqual(len(matches), 1, f"{token}: the texture the screen names is one file in client-patch/art")
                self.assertNotIn("source", matches[0].relative_to(ART).parts, "build.sh never packs source/")
                self.assertEqual(matches[0], build_icon.out_path(token), "the file build_icon.py writes")

    def test_a_64x64_dxt5_blp2(self):
        for token in build_icon.CLASSES:
            with self.subTest(token):
                head = build_icon.out_path(token).read_bytes()[:20]
                self.assertEqual(struct.unpack("<4sIBBBBII", head), (b"BLP2", 1, 2, 8, 7, 1, 64, 64))

    def test_rebuilt_from_the_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            for token in build_icon.CLASSES:
                with self.subTest(token):
                    out = Path(tmp) / f"{token}.blp"
                    build_icon.build(token, out)
                    self.assertEqual(out.read_bytes(), build_icon.out_path(token).read_bytes(),
                                     "build_icon.py output is committed")

    def test_decodes_to_the_source(self):
        for token in build_icon.CLASSES:
            with self.subTest(token):
                want = Image.open(build_icon.source_of(token)).convert("RGBA").resize((64, 64), Image.LANCZOS)
                got = Image.open(build_icon.out_path(token)).convert("RGBA")
                diff = ImageStat.Stat(ImageChops.difference(on_backdrop(got), on_backdrop(want))).mean
                self.assertLess(max(diff), 8, f"mean channel difference {diff}")


if __name__ == "__main__":
    unittest.main()
