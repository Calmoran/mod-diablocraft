"""The source-text guards of monk spirit: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_monk_spirit.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_monk_spirit import MODULE  # noqa: E402


class Wiring(unittest.TestCase):
    def test_connected_calls_the_monk(self):
        text = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat" / "dc_combat_internal.h", *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])
        body = text.split("void Connected(Player* player, std::uint32_t spellId, unsigned enemies)")[1].split("}")[0]
        self.assertIn("Monk::Connected(player, spellId);", body)

    def test_the_monk_is_named_only_in_its_folder(self):
        # dc_spell_shells.h and dc_spell_values.h are generated from the sheets: the Monk's records name it (diablocraft-3mk78)
        allowed = {"src/classes/dc_resource_data.h", "src/classes/dc_resources.h", "src/combat/dc_combat.cpp",
                   "src/combat/dc_combat_resolve.cpp", "src/combat/dc_combat_hooks.cpp",
                   "src/common/dc_world.cpp", "src/combat/dc_spell_shells.h", "src/combat/dc_spell_values.h"}
        found = set()
        for path in (MODULE / "src").rglob("*.*"):
            rel = path.relative_to(MODULE).as_posix()
            if path.suffix in (".cpp", ".h") and not rel.startswith("src/classes/monk/") \
                    and "Monk" in path.read_text(encoding="utf-8", errors="replace"):
                found.add(rel)
        self.assertEqual(found - allowed, set(), "the Monk named outside its folder")


if __name__ == "__main__":
    unittest.main()
