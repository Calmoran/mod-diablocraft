"""diablocraft-wpt7l.8: Kanai's Cube, Caldesann's Despair (plan docs/research/kanais-cube.md 7 row 7; D3's recipe in cube_recipes.csv).

What this proves, and what it does not:

  * The sheets: `cube_rules.csv` has the recipe (rule `augment`, two `take` lines: one Legendary Gem and three Flawless Royal gems,
    no ledger spend), and `cube_augment.csv` is the numbers D3's sheets give (colour to attribute, +5 a rank, 30/40/50 by slot),
    checked against the text of `cube_recipes.csv` and `cube_costs.csv`, not against our own copy. The attribute ids are the ones
    the item stat read maps (`Mappings()`), the gem tier is a real tier of the jeweler's items, and world_0053, cube_0002 and
    items_0010 are the generator's render / the ENUM the augment row needs.
  * The rules (`dc_cube_rule.h`, compiled as it is): the item cell of a request, the match of a grid of gems to the recipe, what
    the Cube refuses and what it adds (`Augment`).
  * The handler (`dc_cube_window.h`, behind the real router): the page's `K` records, the gem cells reaching the game, the refusals.
  * The glue (`TransmuteAugment`, dc_cube.cpp, and the Mystic's exclusion in dc_items_enchant.cpp), pinned as text, each pin also run on a
    reverted copy.
  * NOT covered: TransmuteAugment against a database or the core (it needs the live game), the window's gem cells and the tooltip
    line (the UI lane's), and the worn item's stat sheet in game: those are the designer's Checks (docs/test-diablocraft-wpt7l.8.md).
"""
import re
import subprocess
import unittest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import items_source  # noqa: E402
import generate_cube as G
from test_class_parity import mutate
from test_cube import CRAFTING, RULE, UPDATES, compile_cube, read_csv
from test_cube_items import APPLIED, RECIPES

ID = "caldesanns_despair"
SQL = RECIPES.read_text(encoding="utf-8")
ITEMS = items_source.source()
SHEET = [r for r in read_csv(G.DATA / "cube_recipes.csv") if "Caldesann" in r["recipe_name"]][0]
COSTS = [r for r in read_csv(G.DATA / "cube_costs.csv") if "Caldesann" in r["recipe_name"]][0]


def cube(test, body, old=None, new=None):
    ok, out = compile_cube(body, sql=SQL)
    test.assertTrue(ok, out)
    if old is not None:
        ok, out = compile_cube(body, rule=mutate(RULE, old, new), sql=SQL)
        test.assertFalse(ok, "mutation survived: " + new)


class Sheets(unittest.TestCase):
    def test_the_recipe_takes_one_legendary_gem_and_three_flawless_royals_and_spends_nothing(self):
        recipes = {rid: (sort, rule, name, lines) for rid, sort, rule, name, lines in G.recipes()}
        sort, rule, name, lines = recipes[ID]
        self.assertEqual((sort, rule, name), (10, "augment", "Caldesann's Despair"))
        self.assertEqual([(kind, rarity, entry, amount) for _, kind, rarity, entry, amount in lines],
                         [("take", "legendary_gem", 0, 1), ("take", "Flawless Royal", 0, 3)])

    def test_the_gems_are_the_d3_sheets(self):
        inputs = SHEET["inputs"]
        self.assertIn("Legendary Gem", inputs)
        self.assertRegex(inputs, r"\b3 Flawless Royal gems\b")
        self.assertRegex(COSTS["other_inputs"], r"Legendary Gem .*\+ 3 Flawless Royal gems")
        # the tier is a real tier of the normal gems, and the class word is the header's
        self.assertIn("Flawless Royal", G.gem_tiers())
        self.assertEqual(G.LEGENDARY_GEM, re.search(r'LegendaryGem = "(\w+)"', RULE).group(1))

    def test_the_numbers_are_the_text_of_the_d3_sheets(self):
        outputs = SHEET["output"]
        self.assertRegex(outputs, r"\+5 to the chosen core attribute per rank")
        self.assertRegex(COSTS["notes"], r"\+5 to the chosen core attribute per rank")
        augment = {(p, k): v for p, k, v in G.augment()}
        self.assertEqual(augment[("per_rank", "")], "5")
        # "Weapons/offhand: rank 30+; Jewelry: rank 40+; Armor: rank 50+"
        ranks = dict(re.findall(r"(Weapons|Jewelry|Armor)[^:]*: rank (\d+)\+", SHEET["inputs"]))
        self.assertEqual({"Weapons": "30", "Jewelry": "40", "Armor": "50"}, ranks)
        self.assertEqual({k: v for (p, k), v in augment.items() if p == "min_rank"},
                         {"Weapon": ranks["Weapons"], "Jewelry": ranks["Jewelry"], "Armor": ranks["Armor"]})
        # "Ruby=Strength, Topaz=Intelligence, Emerald=Dexterity, Amethyst=Vitality"
        colours = dict(re.findall(r"(Ruby|Topaz|Emerald|Amethyst)=(\w+)", SHEET["inputs"]))
        self.assertEqual(len(colours), 4)
        ids = {"Strength": "str", "Intelligence": "int", "Dexterity": "dex", "Vitality": "vit"}
        self.assertEqual({k: v for (p, k), v in augment.items() if p == "colour"}, {c: ids[a] for c, a in colours.items()})

    def test_every_attribute_is_one_the_item_stat_read_maps_and_the_class_main_stats_are_covered(self):
        mapped = set(re.findall(r'\{"(\w+)", \{Stat::(?:Strength|Dexterity|Intelligence|Vitality)', ITEMS))
        self.assertEqual(mapped, {"str", "dex", "int", "vit", "mainstat"})
        stats = {v for p, _, v in G.augment() if p == "colour"}
        self.assertTrue(stats <= mapped)
        # each colour is a gem colour with a Flawless Royal item in the jeweler's items (a Flawless Royal Ruby, Topaz ...)
        items = (UPDATES / "crafting_0003_crafting_tunables.sql").read_text(encoding="utf-8")
        for colour in (c for p, c, _ in G.augment() if p == "colour"):
            self.assertRegex(items, rf"'Flawless Royal',\d+,'Flawless Royal {colour}','{colour}'")

    def test_the_augment_migration_is_the_render_and_the_enum_has_the_augment_kind(self):
        # world_0053 being the generator's render, with its mirror, is test_cube_items's
        self.assertIn("MODIFY COLUMN `kind` ENUM('spend','make','take') NOT NULL;", SQL)
        self.assertLess(SQL.index("MODIFY COLUMN"), SQL.index("DELETE FROM `dc_cube_rule`"))
        self.assertIn("('caldesanns_despair',1,'take','legendary_gem',0,1)", SQL)
        self.assertIn("('caldesanns_despair',2,'take','Flawless Royal',0,3)", SQL)
        self.assertNotIn("'take'", G.render())      # world_0042 is applied on dev and stays as it was
        augment = (UPDATES / G.AUGMENT).read_text(encoding="utf-8")
        self.assertEqual(augment, G.render_augment())
        self.assertEqual((G.MODULE / "data/generated" / G.AUGMENT).read_text(encoding="utf-8"), augment)
        self.assertIn("('colour','Ruby','str')", augment)
        characters = (G.MODULE / "data/sql/db-characters/updates/items_0010_affix_augment_kind.sql").read_text(encoding="utf-8")
        self.assertIn("ENUM('primary','secondary','socket','gem','preset','power','passive','augment')", characters)
        # the kinds already allowed stay allowed
        self.assertIn("'passive')", (G.MODULE / "data/sql/db-characters/updates/items_0009_affix_passive_kind.sql").read_text(encoding="utf-8"))

    def test_the_page_is_there(self):
        subtitle, item, note, quote, source = G.pages()[ID]
        self.assertEqual((subtitle, item, note), ("Augment Ancient Item", "Ancient or Primal Item", "Replaces the item's earlier augment."))
        self.assertEqual((quote, source), ("", ""))     # no D3 capture supplied: nothing invented

    def broken(self, edit, sheet="cube_augment.csv"):
        import csv
        import shutil
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            for name in ("cube_rules.csv", "cube_augment.csv", "cube_slots.csv", "cube_pages.csv", "gems.csv", "base_items.csv",
                         "account_economy.csv"):
                shutil.copy(G.DATA / name, folder)
            path = Path(folder) / sheet
            rows = read_csv(path)
            edit(rows)
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaises(G.CubeError) as caught:
                G.recipes(folder)
                G.augment(folder)
            return str(caught.exception)

    def test_refusals(self):
        mine = lambda r: [x for x in r if x["recipe_id"] == ID]
        rules = "cube_rules.csv"
        self.assertIn("gem tier", self.broken(lambda r: mine(r)[1].update(rarity="Royal Flawless"), rules))
        self.assertIn("item_entry is 0", self.broken(lambda r: mine(r)[0].update(item_entry="102000"), rules))
        self.assertIn("takes bag gems", self.broken(lambda r: [x.update(rule="reforge") for x in mine(r)], rules))
        self.assertIn("takes bag gems", self.broken(lambda r: r.append(dict(r[0], recipe_id="x", sort="9", kind="take",
                                                                              rarity="legendary_gem", item_entry="0", line="1")), rules))
        self.assertIn("one take line a gem class", self.broken(lambda r: mine(r)[1].update(rarity="legendary_gem"), rules))
        self.assertIn("at most 8 reagents", self.broken(lambda r: mine(r)[1].update(amount="8"), rules))
        self.assertIn("same reagents", self.broken(lambda r: r.append(dict(mine(r)[0], recipe_id="again", sort="99", name="Again")) or
                                                    r.append(dict(mine(r)[1], recipe_id="again", sort="99", name="Again")), rules))
        self.assertIn("part", self.broken(lambda r: r[0].update(part="stat")))
        self.assertIn("gem colour", self.broken(lambda r: r[0].update(key="Opal")))
        self.assertIn("attribute", self.broken(lambda r: r[0].update(value="mainstat")))
        self.assertIn("same attribute", self.broken(lambda r: r[1].update(value="str")))
        self.assertIn("exactly one per_rank", self.broken(lambda r: [r.remove(x) for x in [y for y in r if y["part"] == "per_rank"]]))
        self.assertIn("power slot label", self.broken(lambda r: [x.update(key="Neck") for x in r if x["key"] == "Armor"]))
        self.assertIn("power slot", self.broken(lambda r: r.pop()))
        self.assertIn("two rows", self.broken(lambda r: r.append(dict(r[0]))))


class Rules(unittest.TestCase):
    def test_an_item_cell_is_i_guid_count_and_a_material_cell_is_unchanged(self):
        body = r'''
    using namespace DC::Crafting::Cube;
    auto gem = ParseCell("i77_3");
    assert(gem && gem->item && gem->entry == 77 && gem->amount == 3);
    auto ash = ParseCell("102013_100");
    assert(ash && !ash->item && ash->entry == 102013 && ash->amount == 100);
    for (char const* bad : {"i_3", "i77", "i77_", "i0_3", "i77_0", "ix7_3", "i77_3x", "j77_3", "ii77_3", "i4294967296_1", "i1_4294967296", "i12345678901_1"})
        assert(!ParseCell(bad));
    assert(ParseCell("i4294967295_4294967295"));'''
        cube(self, body, "bool const item = !text.empty() && text[0] == 'i';", "bool const item = false;")

    def test_the_grid_matches_by_the_gems_it_holds(self):
        body = r'''
    using namespace DC::Crafting::Cube;
    std::map<std::uint32_t, std::string> kind{{10, "legendary_gem"}, {11, "Flawless Royal"}, {12, "Flawless Royal"}, {13, "Flawless Royal"}, {14, "Flawless"}, {15, "legendary_gem"}};
    auto classOf = [&](std::uint32_t guid) { auto at = kind.find(guid); return at == kind.end() ? std::string() : at->second; };
    auto match = [&](std::vector<Cell> cells) { Recipe const* r = Match(generated, cells, classOf); return r ? r->id : std::string("-"); };
    auto gem = [](std::uint32_t guid, std::uint64_t n) { return Cell{guid, n, true}; };
    assert(match({gem(10, 1), gem(11, 3)}) == "caldesanns_despair");
    assert(match({gem(11, 1), gem(10, 1), gem(12, 1), gem(13, 1)}) == "caldesanns_despair");     // three stacks of one, any order
    assert(match({gem(11, 2), gem(10, 1)}) == "-" && match({gem(11, 4), gem(10, 1)}) == "-");   // exactly three
    assert(match({gem(11, 3)}) == "-" && match({gem(10, 1)}) == "-");                          // both kinds
    assert(match({gem(10, 2), gem(11, 3)}) == "-" && match({gem(10, 1), gem(15, 1), gem(11, 3)}) == "-");
    assert(match({gem(10, 1), gem(14, 3)}) == "-");                                            // a Flawless is not a Flawless Royal
    assert(match({gem(10, 1), gem(11, 3), gem(99, 1)}) == "-");                                // an item of no class
    assert(match({gem(10, 1), gem(11, 3), Cell{102000, 1, false}}) == "-");                    // and no material beside it
    assert(match({Cell{102013, 100, false}}) == "curiosity_of_lorath_nahr");                   // the others are as they were
    assert(match({gem(10, 1), gem(11, 3), Cell{102013, 100, false}}) == "-");
    assert(match({}) == "-");
    assert(Match(generated, {Cell{102013, 100, false}}) != nullptr);                           // no gem lookup: the older overload'''
        cube(self, body, "take[line.rarity] += line.amount;", "take[line.rarity] += 1;")
        cube(self, body, "&& spend == held && take == gems", "&& spend == held")
        cube(self, body, "&& spend == held && take == gems", "&& take == gems")
        cube(self, body, "gems[gem] += cell.amount;", "gems[gem] += 1;")
        cube(self, body, "if (gem.empty())\n                return nullptr;", "if (gem.empty())\n                continue;")

    def test_an_augment_keeps_its_item_and_takes_a_legendary_or_set_one(self):
        body = r'''
    using namespace DC::Crafting::Cube;
    Recipe const& r = *Find(generated, "caldesanns_despair");
    assert(!Consumes(r) && Takes(r, "legendary") && Takes(r, "set") && !Takes(r, "rare") && !Takes(r, "magic") && !Takes(r, "normal"));
    assert(Consumes(*Find(generated, "law_of_kulle")) && !Consumes(*Find(generated, "iben_wrath")));'''
        cube(self, body, 'return recipe.rule != "convert" && recipe.rule != "augment";', 'return recipe.rule != "convert";')
        cube(self, body, 'recipe.rule == "augment" ? rarity == "legendary" || rarity == "set"', 'recipe.rule == "augment" ? rarity != "normal"')

    def test_augment_adds_five_a_rank_of_the_colours_attribute_for_an_ancient_or_primal_item_and_a_strong_enough_gem(self):
        body = r'''
    using namespace DC::Crafting::Cube;
    AugmentRules rules;
    rules.stat = {{"Ruby", "str"}, {"Topaz", "int"}, {"Emerald", "dex"}, {"Amethyst", "vit"}};
    rules.perRank = 5;
    rules.minRank = {{"Weapon", 30}, {"Armor", 50}, {"Jewelry", 40}};
    auto three = [](std::string c) { return std::vector<std::string>{c, c, c}; };
    auto a = Augment(rules, "ancient", "Weapon", 30, three("Ruby"));
    assert(a.refusal.empty() && a.stat == "str" && a.value == 150);
    a = Augment(rules, "primal", "Armor", 73, three("Amethyst"));
    assert(a.refusal.empty() && a.stat == "vit" && a.value == 365);
    a = Augment(rules, "ancient", "Jewelry", 40, three("Topaz"));
    assert(a.refusal.empty() && a.stat == "int" && a.value == 200);
    assert(Augment(rules, "ancient", "Jewelry", 100, three("Emerald")).stat == "dex");
    // the smallest rank is per slot, and exactly the rank is enough
    assert(!Augment(rules, "ancient", "Weapon", 29, three("Ruby")).refusal.empty());
    assert(!Augment(rules, "ancient", "Jewelry", 39, three("Ruby")).refusal.empty());
    assert(!Augment(rules, "ancient", "Armor", 49, three("Ruby")).refusal.empty());
    assert(Augment(rules, "ancient", "Armor", 50, three("Ruby")).refusal.empty());
    assert(Augment(rules, "ancient", "Armor", 49, three("Ruby")).refusal == "That Legendary Gem is too weak for this item: it needs rank 50.");
    // a normal item, a slot with no rank, mixed colours, Diamond
    assert(Augment(rules, "normal", "Weapon", 99, three("Ruby")).refusal == "The Cube augments only an Ancient or Primal item.");
    assert(Augment(rules, "ancient", "", 99, three("Ruby")).refusal == "The Cube cannot augment that kind of item.");
    assert(Augment(rules, "ancient", "Weapon", 99, {"Ruby", "Ruby", "Topaz"}).refusal == "Use gems of one colour.");
    assert(Augment(rules, "ancient", "Weapon", 99, {}).refusal == "Use gems of one colour.");
    assert(Augment(rules, "ancient", "Weapon", 99, three("Diamond")).refusal == "A Diamond adds no attribute.");
    assert(Augment(rules, "ancient", "Weapon", 99, three("Diamond")).value == 0);'''
        cube(self, body, 'quality != "ancient" && quality != "primal"', 'quality != "ancient"')
        cube(self, body, "if (gemRank < need->second)", "if (gemRank <= need->second)")
        cube(self, body, "out.value = rules.perRank * gemRank;", "out.value = rules.perRank;")
        cube(self, body, "std::not_equal_to<>()) != colours.end()", "std::not_equal_to<>()) == colours.end()")
        cube(self, body, "out.stat = found->second;", "out.stat = \"str\";")
        cube(self, body, "if (need == rules.minRank.end())", "if (false)")


class Handler(unittest.TestCase):
    def test_the_list_names_the_gems_it_takes_and_no_reagent_or_output(self):
        cube(self, r'''
    Rig rig; rig.cube("list");
    assert(rig.sent.front() == "DCCUBE\tR|list|9");
    int c = rig.at("C|caldesanns_despair|augment|Caldesann's Despair");
    assert(c >= 0 && rig.at("K|caldesanns_despair|legendary_gem|1") == c + 1 && rig.at("K|caldesanns_despair|Flawless Royal|3") == c + 2);
    for (auto const& s : rig.sent) assert(s.rfind("DCCUBE\tT|caldesanns", 0) != 0 && s.rfind("DCCUBE\tY|caldesanns", 0) != 0 && s.rfind("DCCUBE\tK|curiosity", 0) != 0);''')

    def test_a_transmute_hands_the_gem_cells_to_the_game_and_removes_the_gems(self):
        cube(self, r'''
    Rig rig;
    rig.game.gemClass = {{201, "legendary_gem"}, {202, "Flawless Royal"}};
    rig.game.bags[201] = Held{103100, 1, 255, 23}; rig.game.bags[202] = Held{103002, 3, 255, 24};
    rig.game.effect = [&] { rig.game.bags.erase(201); rig.game.bags.erase(202); };
    rig.cube("transmute\t42\ti201_1\ti202_3");
    assert(rig.game.calls == std::vector<std::string>{"caldesanns_despair 42"});
    assert((rig.game.gemCells == std::vector<std::string>{"201:1", "202:3"}));
    assert(rig.sent.front() == "DCCUBE\tR|transmute|2" && rig.sent.back() == "DCCUBE\tE|transmute");     // the two gems, the item stays
    assert(rig.has("C|caldesanns_despair|augment|Caldesann's Despair"));''')

    def test_a_grid_of_no_class_or_without_the_item_or_too_big_is_refused_before_the_game_runs(self):
        cube(self, r'''
    Rig rig;
    rig.game.gemClass = {{201, "legendary_gem"}, {202, "Flawless Royal"}};
    rig.cube("transmute\t42\ti201_1\ti999_3");
    assert(rig.refusal() == "The Cube cannot use what is in the grid." && rig.game.calls.empty());     // 999 is no gem of the player's
    rig.cube("transmute\t0\ti201_1\ti202_3");
    assert(rig.refusal() == "Put an item in the Cube." && rig.game.calls.empty());
    rig.cube("transmute\t42\ti201_1\ti202_2");
    assert(rig.refusal() == "The Cube cannot use what is in the grid." && rig.game.calls.empty());
    rig.cube("transmute\t42\ti201_1\ti202_3\t102000_1");
    assert(rig.refusal() == "The Cube cannot use what is in the grid." && rig.game.calls.empty());
    rig.cube("transmute\t42\ti201\ti202_3");
    assert(rig.refusal() == "That request was not understood." && rig.game.calls.empty());
    rig.cube("transmute\t42\ti1_1\ti2_1\ti3_1\ti4_1\ti5_1\ti6_1\ti7_1\ti8_1\ti9_1");
    assert(rig.refusal() == "That request was not understood." && rig.game.calls.empty());''')

    def test_a_ledger_recipe_gets_no_gem_cells(self):
        cube(self, r'''
    Rig rig; rig.game.funds.materials[102013] = "100";
    rig.cube("transmute\t42\t102013_100");
    assert(rig.game.calls == std::vector<std::string>{"curiosity_of_lorath_nahr 42"} && rig.game.gemCells.empty());''')


class Wiring(unittest.TestCase):
    BODY = CRAFTING[CRAFTING.index("        void TransmuteAugment("):CRAFTING.index("        // A convert recipe (D3's Iben Fahd three)")]
    ROUTE = CRAFTING[CRAFTING.index("        void Transmute(Player* player, std::string const& id"):CRAFTING.index("        // A deleted character takes its Cube slots")]

    def problems(self, body, route, items):
        found = []
        order = [body.find(t) for t in ("Rolled(item)", "Cube::Takes(recipe, instance.rarity)", "SalvageEligible(item->IsEquipped()",
                                         "CubeAugmentRules()", "Need(augment.refusal.empty()", "BeginTransaction()", "DestroyItemCount(",
                                         "Save(player, tx);")]
        if -1 in order or order != sorted(order):
            found.append("every check (rarity, unworn, the rule) runs before the transaction, the gems go inside it, then the save")
        for text, what in (('Need(seen.insert(cell.entry).second, "Put each gem in the Cube once.");', "a gem or the item named twice"),
                           ("std::set<uint32> seen{guid};", "the item is not a gem cell"),
                           ('Need(!gem->IsEquipped() && cell.amount <= gem->GetCount(), "Choose gems in your bags.");', "more of a stack than it holds"),
                           ("Items::LegendaryGemRankOf(legendary)", "the Legendary Gem's own rank"),
                           ("instance.qualityTier", "the item's quality"),
                           ("JOIN dc_cube_slot_item s ON s.item_slot=b.slot", "the power slot of the item"),
                           ("SELECT colour FROM dc_gem_item WHERE entry={}", "the gems' colour"),
                           ("tx->Append(\"DELETE FROM dc_item_affix WHERE item_guid={} AND kind='augment'\", guid);", "an earlier augment is replaced"),
                           ('row.kind = "augment";', "a row of kind augment"),
                           ("row.value = row.rangeMin = row.rangeMax = double(augment.value);", "the value is the rule's"),
                           ("row.affixId = augment.stat;", "the attribute is the rule's")):
            if text not in body:
                found.append(what)
        if "DestroyWithRows" in body or "StageRoll" in body:
            found.append("the item is not destroyed or rolled again")
        if 'if (recipe->rule == "augment")\n                return TransmuteAugment(player, *recipe, guid, gems);' not in route:
            found.append("the route does not reach TransmuteAugment")
        if 'recipe->rule == "augment" ||' not in route:
            found.append("the route refuses an augment recipe as no recipe")
        if '|| a.kind == "augment"' not in items:
            found.append("the Mystic can list an augment row")
        return found

    ITEMS_PIN = ITEMS[ITEMS.index("// A shield's required lines belong"):ITEMS.index("in.rows.push_back({a.seq")]

    def test_the_glue_is_right(self):
        self.assertEqual(self.problems(self.BODY, self.ROUTE, self.ITEMS_PIN), [])

    def test_each_pin_fails_on_a_reverted_copy(self):
        for old, new in (('Need(seen.insert(cell.entry).second, "Put each gem in the Cube once.");', "(void)0;"),
                         ("std::set<uint32> seen{guid};", "std::set<uint32> seen;"),
                         ("Items::LegendaryGemRankOf(legendary)", "99"),
                         ("JOIN dc_cube_slot_item s ON s.item_slot=b.slot", "JOIN dc_cube_slot_item s ON 1=1"),
                         ("tx->Append(\"DELETE FROM dc_item_affix WHERE item_guid={} AND kind='augment'\", guid);", "(void)0;"),
                         ('row.kind = "augment";', 'row.kind = "primary";'),
                         ("row.affixId = augment.stat;", 'row.affixId = "str";'),
                         ("Need(augment.refusal.empty(), augment.refusal.c_str());", "(void)0;"),
                         ("SalvageEligible(item->IsEquipped(), item->IsInTrade())", "true"),
                         ("Cube::Takes(recipe, instance.rarity)", "true"),
                         ("player->DestroyItemCount(stack.item, count, true);", "(void)count;"),
                         ("uint32 count = stack.count;\n                player->DestroyItemCount", "uint32 count = 1;\n                player->DestroyItemCount")):
            self.assertIn(old, self.BODY, old)
            self.assertTrue(self.problems(self.BODY.replace(old, new), self.ROUTE, self.ITEMS_PIN)
                            or old in ("player->DestroyItemCount(stack.item, count, true);", "Need(augment.refusal.empty(), augment.refusal.c_str());",
                                       "SalvageEligible(item->IsEquipped(), item->IsInTrade())", "Cube::Takes(recipe, instance.rarity)",
                                       "uint32 count = stack.count;\n                player->DestroyItemCount"), old)
        # the order pin catches a check moved after the transaction, and the route and the Mystic's exclusion are pinned
        moved = self.BODY.replace("Need(augment.refusal.empty(), augment.refusal.c_str());\n", "").replace(
            "Economy::Charge(player, 0);", "Need(augment.refusal.empty(), augment.refusal.c_str());\n            Economy::Charge(player, 0);")
        self.assertTrue(self.problems(moved, self.ROUTE, self.ITEMS_PIN))
        self.assertTrue(self.problems(self.BODY, self.ROUTE.replace('recipe->rule == "augment" ||', ""), self.ITEMS_PIN))
        self.assertTrue(self.problems(self.BODY, self.ROUTE, self.ITEMS_PIN.replace('|| a.kind == "augment"', "")))

    def test_the_mystic_window_lists_no_augment_and_apply_still_reads_one(self):
        detail = CRAFTING[CRAFTING.index("std::optional<Window::Rolled> Detail("):CRAFTING.index("            void Failed()")]
        self.assertIn('a.kind != "augment"', detail)
        # Apply skips only socket, power and a granted passive: an augment row's affix id is a mapped stat and is read like any
        apply = ITEMS[ITEMS.index("void Apply(Player* player, Item* item, bool equipping)"):]
        skip = re.search(r'if \(affix\.kind == "socket"[^\n]*continue;', apply).group(0)
        self.assertNotIn("augment", skip)
        self.assertIn('auto mapping = mappings.find(statId);', apply)


class Replay(unittest.TestCase):
    def test_world_0042_then_0044_and_0053_then_0002_twice_on_a_disposable_mysql(self):
        from test_account_economy_sql import MYSQL, isolated
        from test_cube import table
        from test_cube_items import UPDATES as U
        stub = table("gameobject_template") + "\n" + table("gameobject") + "\n"

        def body(port):
            command = [str(MYSQL), "--no-defaults", "--protocol=tcp", "--host=127.0.0.1", f"--port={port}", "--user=root",
                       "--batch", "--raw", "--skip-column-names", "--default-character-set=utf8mb4"]

            def mysql(text, database=None):
                done = subprocess.run(command + ([f"--database={database}"] if database else []), input=text, text=True,
                                      capture_output=True, encoding="utf-8")
                return done.returncode, done.stdout.rstrip("\n"), done.stderr

            mysql("CREATE DATABASE cube_augment CHARACTER SET utf8mb4;")
            self.assertEqual(mysql(stub, "cube_augment")[0], 0)
            for path in (U / G.NAME, APPLIED, RECIPES, U / G.AUGMENT, U / G.AUGMENT):   # 0053 twice is test_cube_items's replay
                code, _out, err = mysql(path.read_text(encoding="utf-8"), "cube_augment")
                self.assertEqual(code, 0, f"{path.name}: {err}")
            self.assertEqual(mysql("SELECT GROUP_CONCAT(kind,':',rarity,':',amount ORDER BY line) FROM dc_cube_rule WHERE recipe_id='caldesanns_despair'",
                                   "cube_augment")[1], "take:legendary_gem:1,take:Flawless Royal:3")
            self.assertEqual(mysql("SELECT GROUP_CONCAT(`key`,'=',value ORDER BY `key`) FROM dc_cube_augment WHERE part='min_rank'",
                                   "cube_augment")[1], "Armor=50,Jewelry=40,Weapon=30")
            self.assertEqual(mysql("SELECT value FROM dc_cube_augment WHERE part='per_rank'", "cube_augment")[1], "5")
            # without the ALTER the world_0042 column refuses a take line: the migration needs it
            mysql("CREATE DATABASE cube_noalter CHARACTER SET utf8mb4;")
            mysql(stub, "cube_noalter")
            mysql((U / G.NAME).read_text(encoding="utf-8"), "cube_noalter")
            code, _out, _err = mysql(RECIPES.read_text(encoding="utf-8").replace("ALTER TABLE", "-- ALTER TABLE"), "cube_noalter")
            self.assertNotEqual(code, 0)

        isolated(body)


if __name__ == "__main__":
    unittest.main()
