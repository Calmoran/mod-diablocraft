"""diablocraft-w9zv8: Broken Crown, "whenever a gem drops, a gem of the type socketed into your helmet also drops".

1. The rule, dc_broken_crown_rule.h compiled and driven with the dc_gem_item rows of the newest crafting migration (the
   same rows the server reads, never typed-in entries): for every helm colour and every dropped gem, the bonus is the helm's
   colour at the dropped gem's grade; no helm gem, a legendary gem (no row) and an unknown drop give nothing. Each rule runs
   again on a mutant that breaks it, and the harness must go red.
2. The wiring, pinned as text (not run: it needs a Player and a kill): the bonus follows the kill hook's gem roll for each
   member, reads only the head slot, checks the Crown's d3_id, and the Greater Rift Guardian's legendary gem is not given one.
"""
import re
import unittest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import loot_source  # noqa: E402
from test_class_parity import SRC, definition, mutate, run

MODULE = SRC.parent
RULE = (SRC / "loot/dc_broken_crown_rule.h").read_text(encoding="utf-8")
LOOT = loot_source.source()   # R4: the roll and hooks (dc_loot.cpp) and BrokenCrownGem (dc_loot_delivery.cpp)
MIGRATION = MODULE / "data/sql/db-world/updates/crafting_0007_crafting_tunables.sql"


def gems():
    text = MIGRATION.read_text(encoding="utf-8")
    rows = re.findall(r"INSERT INTO `dc_gem_item` VALUES \((\d+),'[^']*','([^']*)',\d+,'[^']*','([^']*)'\);", text)
    assert len(rows) == 50, len(rows)
    return [(int(entry), tier, colour) for entry, tier, colour in rows]


def harness(rule, body):
    table = ",\n".join('{%d, "%s", "%s"}' % (e, c, t) for e, t, c in gems())
    return ('#include <cassert>\n#include <cstdint>\n#include <string>\n#include <vector>\n' + rule
            + "\nusing namespace DC::Loot::BrokenCrown;\nint main() {\n    std::vector<Gem> g = {" + table
            + "};\n    auto by = [&](std::uint32_t e) -> Gem const& { for (auto& x : g) if (x.entry == e) return x; assert(false); };\n"
            + body + "\n    return 0;\n}\n")


def both(test, body, old, new):
    ok, out = run(harness(RULE, body))
    test.assertTrue(ok, out)
    ok, out = run(harness(mutate(RULE, old, new), body))
    test.assertFalse(ok, "mutation survived: " + new)


class Rule(unittest.TestCase):
    def test_the_bonus_is_the_helm_colour_at_the_drop_grade(self):
        both(self, r'''
    for (auto& h : g) for (auto& d : g) {
        std::uint32_t b = BonusGem(h.entry, d.entry, g);
        assert(b && by(b).colour == h.colour && by(b).tier == d.tier);
    }''', "gem.colour == colour && gem.tier == tier", "gem.colour == colour")

    def test_the_drop_grade_not_the_drop_colour(self):
        both(self, r'''
    for (auto& h : g) for (auto& d : g)
        if (h.colour != d.colour) assert(by(BonusGem(h.entry, d.entry, g)).colour == h.colour);''',
             "if (gem.entry == helmGem)\n                colour = gem.colour;", "if (gem.entry == dropped)\n                colour = gem.colour;")

    def test_nothing_without_an_ordinary_helm_gem_or_a_known_drop(self):
        # No mutant: nothing matches an empty colour or grade, so the answer is 0 by construction.
        ok, out = run(harness(RULE, r'''
    assert(BonusGem(0, g[0].entry, g) == 0);            // empty socket
    assert(BonusGem(910001, g[0].entry, g) == 0);       // not a dc_gem_item row: a legendary gem
    assert(BonusGem(g[0].entry, 910001, g) == 0);       // an unknown drop'''))
        self.assertTrue(ok, out)


class Wiring(unittest.TestCase):
    def test_every_member_gets_it_after_their_own_gem_roll(self):
        hook = definition(LOOT, "auto rollFor = [&](Player* member)")
        self.assertLess(hook.index("RollGemEntry(level, tier)"), hook.index("BrokenCrownGem(member, gem)"))
        self.assertEqual(LOOT.count("BrokenCrownGem("), 2)   # the definition and this one call

    def test_the_guardians_legendary_gem_gets_none(self):
        guardian = LOOT[LOOT.index("if (std::uint32_t const gem = DC::Rifts::Gr::PickGem"):]
        self.assertNotIn("BrokenCrownGem", guardian[:guardian.index("DeliverGemDrop")+200])

    def test_it_reads_the_head_slot_and_the_crowns_id(self):
        body = definition(LOOT, "std::uint32_t BrokenCrownGem(Player* player, std::uint32_t dropped)")
        self.assertIn("GetItemByPos(INVENTORY_SLOT_BAG_0, EQUIPMENT_SLOT_HEAD)", body)
        self.assertIn("helm->IsBroken()", body)
        self.assertIn("DC::Loot::BrokenCrown::BaseId", body)
        self.assertIn('affix.kind == "gem"', body)
        self.assertIn('"P2_Unique_Helm_001"', RULE)


if __name__ == "__main__":
    unittest.main()
