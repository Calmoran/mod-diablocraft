"""diablocraft-wpt7l.6: Kanai's Cube, the Primal upgrade (Curiosity of Lorath Nahr; plan docs/research/kanais-cube.md 6.5 and 7 row 5).

What this proves, and what it does not:

  * The sheet (`cube_rules.csv`) has the recipe: rule `primal_upgrade`, one spend line of 100 Primordial Ashes, which is
    `cube_costs.csv`'s column for the recipe and `cube_recipes.csv`'s "100 Primordial Ashes" (two sources), and no make line.
    It sorts last, its page row is in `cube_pages.csv`, and world_0053 and cube_0001 are the generator's render of both.
  * The rule (`dc_cube_rule.h`, compiled as it is): the recipe takes a Legendary or Set item and nothing else, and consumes it.
  * The handler (`dc_cube_window.h`, behind the real router, the recipe parsed out of world_0053): the list shows it with its cost
    and no output, and a transmute reports the item removed.
  * The glue (`TransmuteItem` in dc_crafting.cpp), pinned as text, each pin also run on a reverted copy: not a crafted item,
    the same base rolled again at quality `primal`, for the upgrader's class or a class-only item's own, the maker marked on the
    staged item before the commit, and the item destroyed before the new one is staged.
  * NOT covered: TransmuteItem against a database or the core (it needs the live game), so the Primal's affixes at the top, the
    gems coming back and the "Made by" line in game are the designer's Checks (docs/test-diablocraft-wpt7l.6.md).
"""
import re
import unittest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_cube as G
from test_cube_items import RECIPES
from test_cube import CRAFTING, RULE, UPDATES, compile_cube, read_csv
from test_class_parity import mutate

ID = "curiosity_of_lorath_nahr"
ASHES = 102013
SQL = RECIPES.read_text(encoding="utf-8")


def cube(test, body, old=None, new=None):
    ok, out = compile_cube(body, sql=SQL)
    test.assertTrue(ok, out)
    if old is not None:
        ok, out = compile_cube(body, rule=mutate(RULE, old, new), sql=SQL)
        test.assertFalse(ok, "mutation survived: " + new)


class Generator(unittest.TestCase):
    def test_the_recipe_spends_a_hundred_ashes_and_makes_no_material(self):
        recipes = {rid: (sort, rule, name, lines) for rid, sort, rule, name, lines in G.recipes()}
        sort, rule, name, lines = recipes[ID]
        self.assertEqual((rule, name), ("primal_upgrade", "Curiosity of Lorath Nahr"))
        self.assertEqual(sort, 11)
        self.assertEqual([(kind, entry, amount) for _, kind, _, entry, amount in lines], [("spend", ASHES, 100)])

    def test_the_hundred_is_both_d3_sheets(self):
        name = "Curiosity of Lorath Nahr"
        cost = [r for r in read_csv(G.DATA / "cube_costs.csv") if r["recipe_name"].endswith(name)][0]
        self.assertEqual(cost["primordial_ashes"], "100")
        self.assertEqual(sum(int(cost[k]) for k in cost if k not in ("recipe_name", "other_inputs", "notes", "source_url")), 100)
        ashes = {int(r["item_entry"]): r["name"] for r in read_csv(G.DATA / "account_economy.csv")}[ASHES]
        text = [r for r in read_csv(G.DATA / "cube_recipes.csv") if name in r["recipe_name"]][0]
        self.assertTrue(text["inputs"].startswith(f"100 {ashes} +"))

    def test_the_recipe_and_the_page_are_there(self):
        # that world_0053 and the pages migration are the generator's render, with their mirrors, is test_cube_items and test_cube_grid's
        self.assertIn(f"('{ID}',11,'primal_upgrade','Curiosity of Lorath Nahr')", SQL)
        pages = G.pages()
        subtitle, item, note, quote, source = pages[ID]
        self.assertEqual((subtitle, item), ("Upgrade Legendary Item", "Legendary or Set Item"))
        self.assertEqual((quote, source), ("", ""))     # no D3 capture supplied: nothing invented
        page_sql = (UPDATES / G.PAGES).read_text(encoding="utf-8")
        self.assertIn(f"('{ID}','Upgrade Legendary Item'", page_sql)

    def test_refusals(self):
        broken = __import__("test_cube").Generator("test_refusals").broken
        mine = lambda r: [x for x in r if x["recipe_id"] == ID]
        self.assertIn("makes no material", broken("cube_rules.csv", lambda r: r.append(dict(mine(r)[0], line="2", kind="make", rarity="set"))))
        self.assertIn("rule", broken("cube_rules.csv", lambda r: [x.update(rule="primal") for x in mine(r)]))


class Rules(unittest.TestCase):
    def test_it_takes_a_legendary_or_set_item_and_consumes_it(self):
        cube(self, r'''
    using namespace DC::Crafting::Cube;
    Recipe const& r = *Find(generated, "curiosity_of_lorath_nahr");
    assert(Takes(r, "legendary") && Takes(r, "set") && !Takes(r, "rare") && !Takes(r, "magic") && !Takes(r, "normal"));
    assert(Consumes(r));''',
             'recipe.rule == "primal_upgrade" ? rarity == "legendary" || rarity == "set"',
             'recipe.rule == "primal_upgrade" ? rarity == "legendary"')
        cube(self, r'''
    using namespace DC::Crafting::Cube;
    assert(!Takes(*Find(generated, "curiosity_of_lorath_nahr"), "rare"));''',
             'recipe.rule == "primal_upgrade" ? rarity == "legendary" || rarity == "set"',
             'recipe.rule == "primal_upgrade" ? rarity != "magic"')


class Handler(unittest.TestCase):
    def test_the_list_shows_its_cost_and_no_output(self):
        cube(self, r'''
    Rig rig; rig.game.funds.materials[102013] = "130"; rig.cube("list");
    assert(rig.has("C|curiosity_of_lorath_nahr|primal_upgrade|Curiosity of Lorath Nahr"));
    assert(rig.has("T|curiosity_of_lorath_nahr|102013|100|130|1"));
    for (auto const& s : rig.sent) assert(s.rfind("DCCUBE\tY|curiosity", 0) != 0);''')

    def test_a_transmute_reports_the_item_removed(self):
        cube(self, r'''
    Rig rig;
    rig.game.effect = [&] { rig.game.bags.erase(42); rig.game.bags[43] = Held{30002, 1, 255, 23}; rig.game.funds.materials[102013] = "0"; };
    rig.cube("transmute\t42\t102013_100");
    assert(rig.game.calls == std::vector<std::string>{"curiosity_of_lorath_nahr 42"});
    assert(rig.sent.front() == "DCCUBE\tR|transmute|1" && rig.sent.back() == "DCCUBE\tE|transmute");''')


class Wiring(unittest.TestCase):
    BODY = CRAFTING[CRAFTING.index("        void TransmuteItem("):CRAFTING.index("        void Transmute(Player* player")]

    @staticmethod
    def branch(body):
        start = body.index('recipe.rule == "primal_upgrade"')
        return body[start:body.index("            Amounts spend;")]

    def problems(self, body):
        found = []
        branch = self.branch(body)
        if 'Need(!instance.crafted && craftOnly != "yes", "The Cube takes no crafted item for this recipe.");' not in branch:
            found.append("a crafted item is not refused")
        if "pick = instance.baseItem;" not in branch:
            found.append("not the same base item")
        if 'rollClass = SlotVendor::RollClassFor(designated, "", playerClass);' not in branch:
            found.append("not rolled for the upgrader's class or the item's own")
        if 'quality = "primal";' not in branch:
            found.append("not rolled Primal")
        marked = 'if (recipe.rule == "primal_upgrade")\n                Items::MarkMade(player, staged->GetItem(), player, tx);'
        if marked not in body or not (body.index("Items::StageRoll(") < body.index(marked) < body.index("Save(player, tx);")):
            found.append("only the Primal upgrade marks its maker, on the staged item, before the commit")
        return found

    def test_the_glue_is_right(self):
        self.assertEqual(self.problems(self.BODY), [])

    def test_each_pin_fails_on_a_reverted_copy(self):
        for old, new in (('quality = "primal";', 'quality = "";'),
                         ("Items::MarkMade(player, staged->GetItem(), player, tx);", "(void)0;"),
                         ('if (recipe.rule == "primal_upgrade")\n                Items::MarkMade', "if (true)\n                Items::MarkMade"),
                         ("pick = instance.baseItem;\n                rollClass = SlotVendor::RollClassFor(designated, \"\", playerClass);\n                quality = \"primal\";",
                          "pick = 0;\n                rollClass = SlotVendor::RollClassFor(designated, \"\", playerClass);\n                quality = \"primal\";"),
                         ('Need(!instance.crafted && craftOnly != "yes", "The Cube takes no crafted item for this recipe.");\n                pick = instance.baseItem;\n                rollClass = SlotVendor::RollClassFor(designated, "", playerClass);\n                quality = "primal";',
                          'pick = instance.baseItem;\n                rollClass = SlotVendor::RollClassFor(designated, "", playerClass);\n                quality = "primal";')):
            self.assertIn(old, self.BODY)
            self.assertTrue(self.problems(self.BODY.replace(old, new)), old)


if __name__ == "__main__":
    unittest.main()
