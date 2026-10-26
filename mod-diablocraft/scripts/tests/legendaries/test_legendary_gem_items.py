"""diablocraft-i1y1 (Legendary gems part 9): the 21 gems as items.

  * legendary_gem_items.csv names exactly the 21 gems that have numbers, with unique entries in the
    reserved range that no other migration or sheet uses, and slots that are real base-item slots;
    Gem of Ease takes weapons and no other gem does (ruling 2);
  * the generated SQL is the generator's output for the sheet, one template per gem, none stacking;
  * the production rules (src/items/dc_legendary_gem_item.h) are compiled and driven with the sheet's
    own slots against every base-item slot, and with socketed sets for Unique Equipped; mutants fail;
  * Unique Equipped refuses (the designer, card q-1006-04, diablocraft-ozl9): the production rule that finds a copy
    already worn is compiled and driven with worn sets, the item or socket that is about to leave, and the
    same gem twice; its mutants fail; the two socket paths and the equip veto are guarded as source text;
  * every legendary gem sells for 16 gold, a tunable (economy.csv legendary_gem_sell_gold), and buys for none;
  * structural guards that every C++ reader of a gem row knows the legendary rank (these read source
    text and prove only that the call is there, not that it runs; the C++ is compile-checked by
    syntax_check.sh and the in-game steps are in docs/test-legendary-gem-items.md).
"""
import csv
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import items_source  # noqa: E402
import crafting_source  # noqa: E402
import generate_legendary_gem_items as gen
import harness_env

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
HEADER = MODULE / "src/items/dc_legendary_gem_item.h"
HARNESS = MODULE / "tests/legendary_gem_items/harness.cpp"


def read(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def base_slots():
    return sorted({r["slot"] for r in read(MODULE / "data/d3/base_items.csv")})


class Data(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = gen.items()

    def test_exactly_the_21_gems(self):
        numbers = {r["gem_id"] for r in read(MODULE / "data/d3/legendary_gems.csv") if r["gem_id"]}
        self.assertEqual(21, len(self.rows))
        self.assertEqual(numbers, {r[0] for r in self.rows})

    def test_entries_are_unique_and_collide_with_nothing(self):
        entries = [r[2] for r in self.rows]
        self.assertEqual(len(entries), len(set(entries)))
        self.assertTrue(all(gen.ENTRY_FIRST <= e <= gen.ENTRY_LAST for e in entries))
        mine = {"legendary_gems_0002_items.sql", "legendary_gems_0005_gem_icons.sql"}  # the second gives these gems their icons
        pattern = re.compile(r"\b1031\d\d\b")
        for folder in ("data/sql/db-world/updates", "data/generated"):
            for path in (MODULE / folder).glob("*.sql"):
                if path.name in mine:
                    continue
                self.assertIsNone(pattern.search(path.read_text(encoding="utf-8")), path.name)
        for sheet in (MODULE / "data/gem_items.csv", MODULE / "data/d3/gems.csv"):
            self.assertIsNone(pattern.search(sheet.read_text(encoding="utf-8")), sheet.name)

    def test_gem_of_ease_takes_weapons_and_every_other_gem_jewelry(self):
        real = set(base_slots())
        for gem_id, name, entry, slots in self.rows:
            self.assertTrue(set(slots.split("|")) <= real, name)
            want = "onehand|twohand" if name == "Gem of Ease" else "neck|finger"
            self.assertEqual(want, slots, name)

    def test_generated_sql_is_the_generators_output_for_the_sheet(self):
        self.assertEqual(gen.world_sql(self.rows),
                         (MODULE / "data/generated/legendary_gems_0002_items.sql").read_text(encoding="utf-8"))
        self.assertEqual(gen.characters_sql(),
                         (MODULE / "data/generated/legendary_gems_0001_rank.sql").read_text(encoding="utf-8"))
        for generated, migration in (("legendary_gems_0002_items.sql", "db-world"),
                                     ("legendary_gems_0001_rank.sql", "db-characters")):
            self.assertEqual((MODULE / "data/generated" / generated).read_text(encoding="utf-8"),
                             (MODULE / "data/sql" / migration / "updates" / generated).read_text(encoding="utf-8"))

    def test_one_non_stacking_template_per_gem(self):
        sql = gen.world_sql(self.rows)
        self.assertEqual(21, sql.count("REPLACE INTO item_template"))
        self.assertEqual(21, sql.count("stackable=1,"))
        for _, name, entry, _ in self.rows:
            self.assertIn("SET entry=%d,name=%s," % (entry, gen.quote(name)), sql)

    def test_every_legendary_gem_sells_for_the_tunable_and_buys_for_nothing(self):
        economy = {r["name"]: r for r in read(MODULE / "data/tunables/economy.csv")}
        row = economy["legendary_gem_sell_gold"]
        self.assertEqual(("", "16", "gold"), (row["d3_value"], row["value"], row["unit"]))   # the designer's, not 0
        self.assertIn("q-1006-04", row["notes"])
        sql = gen.world_sql(self.rows)
        self.assertEqual(21, sql.count("BuyPrice=0,SellPrice=16,"))
        self.assertEqual(21, sql.count("SellPrice="))
        self.assertEqual(0, int(economy["gem_vendor_gold"]["value"]))   # the normal gems and the vendor stay as they were
        self.assertIn("'economy', 'legendary_gem_sell_gold', NULL, 16.0,",
                      (MODULE / "data/generated/tunables_0008.sql").read_text(encoding="utf-8"))

    def test_the_rank_is_a_field_of_its_own(self):
        sql = gen.characters_sql()
        self.assertIn("legendary_rank", sql)
        self.assertIn("dc_legendary_gem_rank", sql)
        self.assertNotIn("gem_rank INT UNSIGNED NULL", sql.replace("legendary_rank", ""))

    def test_a_bad_sheet_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp)
            shutil.copytree(MODULE / "data/d3", module / "data/d3")
            for mutate in (lambda t: t.replace("103101", "103100"),        # duplicate entry
                           lambda t: t.replace("103101", "104101"),        # outside the range
                           lambda t: t.replace("neck|finger", "necklace", 1),   # not a base slot
                           lambda t: t.split("\n", 2)[0] + "\n" + t.split("\n", 2)[2]):   # a gem dropped
                (module / "data").mkdir(exist_ok=True)
                (module / "data/legendary_gem_items.csv").write_text(
                    mutate((MODULE / "data/legendary_gem_items.csv").read_text()), encoding="utf-8")
                with self.assertRaises(ValueError):
                    gen.items(module)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files={HEADER.name: header_text})
        work = Path(tempfile.mkdtemp(prefix="dc_lgi_" + name))
        return work, binary

    CASES = [  # (worn gems, the ones that count)
        ([], "-"),
        ([("Unique_Gem_001_x1", 5)], "Unique_Gem_001_x1:5"),
        ([("Unique_Gem_001_x1", 5), ("Unique_Gem_001_x1", 9)], "Unique_Gem_001_x1:9"),
        ([("Unique_Gem_001_x1", 9), ("Unique_Gem_001_x1", 5)], "Unique_Gem_001_x1:9"),
        ([("Unique_Gem_004_x1", 0), ("Unique_Gem_001_x1", 7), ("Unique_Gem_004_x1", 0)],
         "Unique_Gem_001_x1:7,Unique_Gem_004_x1:0"),
    ]

    # (worn rows (gem, item, seq), the gem asked about, items about to leave, the row it replaces, the answer)
    G1, G2 = "Unique_Gem_001_x1", "Unique_Gem_002_x1"
    WORN = [
        ([], G1, [], (0, 0), "-"),                                           # nothing worn
        ([(G1, 10, 0)], G1, [], (0, 0), "10"),                               # the same gem is worn: refused, and in which item
        ([(G1, 10, 0)], G2, [], (0, 0), "-"),                                # another gem is fine
        ([(G1, 10, 0), (G2, 11, 0)], G2, [], (0, 0), "11"),
        ([(G1, 10, 0)], G1, [10], (0, 0), "-"),                              # the item holding it is about to leave
        ([(G1, 10, 0)], G1, [11], (0, 0), "10"),                             # another item leaves
        ([(G1, 10, 0)], G1, [], (10, 0), "-"),                               # a swap replaces that very socket
        ([(G1, 10, 0)], G1, [], (10, 1), "10"),                              # another socket of the item
        ([(G1, 10, 0)], G1, [], (11, 0), "10"),                              # the same seq on another item
        ([(G1, 10, 0), (G1, 10, 1)], G1, [], (10, 0), "10"),                 # the item holds it twice, one stays
        ([(G1, 10, 0), (G1, 11, 0)], G1, [10], (0, 0), "11"),                # an old duplicate: the one that stays is named
        ([(G1, 10, 0), (G1, 11, 0)], G1, [10, 11], (0, 0), "-"),
        ([(G1, 10, 0), (G1, 10, 1)], G1, [], (0, 0), "10"),
    ]

    def drive(self, header_text, name):
        work, binary = self.build(header_text, name)
        lines, want = [], []
        for gem_id, _, _, slots in gen.items():
            for base in base_slots():
                lines.append("slot %s %s" % (slots, base))
                want.append("1" if base in slots.split("|") else "0")
        lines += ["slot neck|finger fin", "slot neck|finger neck|finger", "slot onehand|twohand hand"]
        want += ["0", "0", "0"]
        for worn, ask, leaving, replaced, conflict in self.WORN:
            lines.append("worn %d %s %s %d %s %d %d" % (
                len(worn), " ".join("%s %d %d" % w for w in worn), ask, len(leaving),
                " ".join(str(i) for i in leaving), replaced[0], replaced[1]))
            want.append(conflict)
        for worn, counted in self.CASES:
            lines.append("counted %d %s" % (len(worn), " ".join("%s %d" % g for g in worn)))
            want.append(counted)
        (work / "cases.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
        shutil.rmtree(work, ignore_errors=True)
        return run.stdout.split("\n")[:-1], want

    def test_slot_and_unique_equipped_rules_for_every_gem_and_slot(self):
        got, want = self.drive(HEADER.read_text(encoding="utf-8"), "real")
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = HEADER.read_text(encoding="utf-8")
        mutants = {
            "no_delimiters": real.replace('padded.find("|" + baseSlot + "|")', "padded.find(baseSlot)"),
            "lowest_rank": real.replace("gem.rank > found->rank", "gem.rank < found->rank"),
            "no_dedupe": real.replace("if (found == counted.end())", "if (true)"),
            "ignores_leaving_items": real.replace("std::find(leaving.begin(), leaving.end(), gem.item) != leaving.end()", "false"),
            "ignores_replaced_row": real.replace("replaced && replaced->first == gem.item && replaced->second == gem.seq", "false"),
            "replaces_whole_item": real.replace("replaced->first == gem.item && replaced->second == gem.seq", "replaced->first == gem.item"),
            "any_gem": real.replace("gem.gemId != gemId", "false"),
            "first_leaving_ends_search": real.replace("                continue;\n            if (replaced", "                return nullptr;\n            if (replaced"),
        }
        for name, mutant in mutants.items():
            self.assertNotEqual(real, mutant, "the %s mutation no longer applies" % name)
            got, want = self.drive(mutant, name)
            self.assertNotEqual(want, got, "mutant %s passed" % name)


class Readers(unittest.TestCase):
    """Source-text guards: the call is there. They do not run the C++."""

    @classmethod
    def setUpClass(cls):
        cls.items = items_source.source()
        cls.crafting = crafting_source.source()
        cls.stash = (MODULE / "src/items/dc_stash.cpp").read_text(encoding="utf-8")

    def test_both_socket_paths_write_the_legendary_rank_and_check_the_slot(self):
        for text in (self.items, self.crafting):
            self.assertIn("AppendGemRow(", text)
            self.assertIn("LegendaryGemFits(", text)
            self.assertIn("LegendaryGemRankOf(", text)
        self.assertNotIn("gem_entry,gem_rank) VALUES", self.items)
        self.assertNotIn("gem_entry,gem_rank) VALUES", self.crafting)

    def test_every_socket_path_and_the_equip_veto_ask_unique_equipped_first(self):
        # insert in the field, insert and swap at the Jeweler: refused before anything is taken or written
        field = self.items[self.items.index("void SocketInField("):self.items.index("class ItemCommand")]
        self.assertIn("WornLegendaryGem(", field)
        self.assertLess(field.index("WornLegendaryGem("), field.index("RemoveContributions(player, item)"))
        jeweler = self.crafting[self.crafting.index("void Socket(Player* player, uint32 guid, uint32 seq"):
                                self.crafting.index("void Combine(")]
        self.assertIn("Items::WornLegendaryGem(", jeweler)
        insert = jeweler.index("auto* gem = Owned(player, gemGuid)")   # the branch that puts a gem in (a swap too)
        call = jeweler.index("Items::WornLegendaryGem(")
        self.assertLess(insert, call)
        self.assertLess(call, jeweler.index("Items::RemoveContributions(player, item)", insert))
        self.assertLess(call, jeweler.index("Economy::Charge(", insert))   # before any gold is taken for a swap
        self.assertIn("child->seq", jeweler[jeweler.index("Items::WornLegendaryGem("):][:400])      # a swap's own socket leaves
        # equip of an item that already holds one: the veto, and not at login (a saved worn set is kept)
        hook = self.items[self.items.index("bool OnPlayerCanEquipItem("):self.items.index("void OnPlayerCustomScalingStatValueBefore")]
        self.assertIn("UniqueEquippedAllows(", hook)
        self.assertIn("notLoading", hook)
        self.assertIn("Unique Equipped", self.items)

    def test_remove_swap_and_salvage_return_the_gem_with_its_rank(self):
        c = self.crafting
        # four callers: salvage, the Jeweler's remove and swap (both in Socket), the Cube's item rules
        self.assertEqual(4, c.count("GrantGem(player,"))
        self.assertEqual(1, c[c.index("void Salvage("):c.index("void Craft(")].count("GrantGem(player,"))
        self.assertEqual(2, c[c.index("void Socket(Player* player, uint32 guid, uint32 seq"):c.index("void Combine(")].count("GrantGem(player,"))
        self.assertEqual(1, c[c.index("void TransmuteItem("):].count("GrantGem(player,"))
        self.assertIn("legendaryGems.push_back(a)", self.crafting)

    def test_the_rank_row_leaves_with_the_item(self):
        self.assertIn("DELETE FROM dc_legendary_gem_rank WHERE item_guid", self.items)
        self.assertIn('"dc_legendary_gem_rank"', self.stash)

    def test_load_reads_the_new_column(self):
        self.assertIn("legendary_rank FROM dc_item_affix", self.items)


if __name__ == "__main__":
    unittest.main()
