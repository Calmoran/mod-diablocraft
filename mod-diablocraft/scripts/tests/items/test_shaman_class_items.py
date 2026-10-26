"""diablocraft-xnrvn.3: the Shaman's class items (the Ritual Mace and the Totem), proved from the sheets, the migrations and the
production code, never from a live server (nobody can log in here; the in-game steps are docs/test-diablocraft-xnrvn.3.md).

    python3 mod-diablocraft/scripts/tests/items/test_shaman_class_items.py

Seven points (the bead, brief shaman-build-2026-10-22 step 1 row 1b; the proof is h943x's, test_monk_class_items.py):
  1. the base rows: the Ritual Mace (one hand, 1.30 attacks a second, the Flail's damage), the Totem (off hand, the Source's
     added weapon damage) and the legendary Ritual Mace the start kit needs, at ids after the set caches, their stock looks
     (the item and display ids are the stock WoW rows, read from the stock Item.dbc) and what the migration and the client's
     Item.dbc say about them;
  2. who may wear what: the AllowableClass the migrations leave (items_0011, 0020, 0028, 0058 and the added-base migration
     replayed in order) gives the Shaman the draft's weapon types (1.7) and her two class items, and the class items to
     nobody else;
  3. what drops: the production header dc_roll_class.h, compiled, rolls the class items for the Shaman and for no other
     class, and rolls the Shaman no other class's item;
  4. the weapon proficiencies: each weapon type she may wield has a skill the stock Shaman has or a SkillRaceClassInfo row
     the generator adds, the Ritual Mace being a Mace;
  5. the affix pools: the production PoolFor, cut out of dc_items_data.cpp and compiled over the real sheets, adds a type's own
     lines to its slot's pool and to no other type's, and the migration is what the generator renders;
  6. the pieces the draft names that wait on a system the build has not made yet are not in the pools (no stand-in);
  7. the start profile: a Ritual Mace legendary and a Totem in the kit, a base to pick in every slot, the weapon skills her weapons need.
Not covered offline: the roller picking at run time, delivery, the client drawing the looks. Each check is a function of the data it
is given, so the mutation tests below hand it a broken copy.
"""
import csv
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[3]
ROOT = MODULE.parent
sys.path.insert(0, str(MODULE / "scripts"))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_class_item_pools as pools_gen  # noqa: E402
import generate_class_proficiencies as proficiencies  # noqa: E402
import generate_sql as g  # noqa: E402
import harness_env  # noqa: E402
import items_source  # noqa: E402
from dbc_store import Store, schema  # noqa: E402

D3 = MODULE / "data" / "d3"
UPDATES = MODULE / "data" / "sql" / "db-world" / "updates"
ADDED = UPDATES / g.ADDED_BASE_MIGRATION
SHAMAN_BIT = 1 << 6            # WoW class 7, class_map.csv wow_class_id
STOCK_DBC = ROOT / "azerothcore-wotlk" / "build" / "server" / "data" / "dbc"
CXX = shutil.which("c++") or shutil.which("g++")
BRACKETS = ("rare", "legendary", "ancient", "primal")
NEW = {"Shaman_RitualMace_001": 101176, "Shaman_Totem_001": 101177, "Shaman_Unique_RitualMace_001": 101178}
# The draft's 1.7 (shaman-grok-v1.4.md): one-handed axes, maces, swords, daggers and spears; two-handed staves, axes, maces and
# swords; shields; and the two class items. Everything else a Shaman wears is armor and jewelry, which names no class.
DRAFT_HANDS = {("onehand", t) for t in ("Axe", "Mace", "Sword", "Dagger", "Spear", "Ritual Mace")} | \
              {("twohand", t) for t in ("Staff", "Two-Handed Axe", "Two-Handed Mace", "Two-Handed Sword")} | \
              {("offhand", "Shield"), ("offhand", "Totem")}
CLASS_ITEMS = {"Ritual Mace", "Totem"}
OTHER_CLASSES = ("barbarian", "wizard", "monk", "crusader", "necromancer", "demonhunter", "witchdoctor")


def sheet(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def bases():
    return sheet(D3 / "base_items.csv")


def ids():
    return {row["d3_id"]: int(row["item_entry"]) for row in sheet(D3 / "base_item_ids.csv")}


def masks():
    """entry -> AllowableClass after the migrations that set it, in the order the core applies them."""
    out = {}
    for name in ("items_0011_item_allowable_class.sql", "items_0020_set_wear_class.sql",
                 "items_0028_item_allowable_class_added.sql", g.ADDED_WEAR_MIGRATION, g.ADDED_BASE_MIGRATION):
        for mask, entries in re.findall(r"SET `AllowableClass`=(-?\d+) WHERE `entry` IN \(([^)]*)\)",
                                        (UPDATES / name).read_text(encoding="utf-8")):
            out.update({int(entry): int(mask) for entry in entries.split(",")})
    return out


def wearable(mask, bit=SHAMAN_BIT):
    return mask < 0 or bool(mask & bit)


def in_pool(base):
    return base["pool_version"] == "yes" and base["craft_only"] != "yes" and base["rarity"] != "ethereal"


# --- 1. the rows --------------------------------------------------------------------------------------------------------
class Rows(unittest.TestCase):
    def test_the_three_new_base_rows(self):
        rows = {r["d3_id"]: r for r in bases() if r["d3_id"] in NEW}
        self.assertEqual(set(rows), set(NEW))
        mace, totem, legendary = (rows[k] for k in ("Shaman_RitualMace_001", "Shaman_Totem_001", "Shaman_Unique_RitualMace_001"))
        flail = next(r for r in bases() if r["d3_id"] == "Flail_1H_201")
        for row, name, slot, type_, rarity in ((mace, "Ritual Mace", "onehand", "Ritual Mace", ""),
                                               (totem, "Totem", "offhand", "Totem", ""),
                                               (legendary, "Earthcaller's Gavel", "onehand", "Ritual Mace", "legendary")):
            self.assertEqual((row["d3_name"], row["slot"], row["type"], row["rarity"]), (name, slot, type_, rarity), row)
            # Shaman-only in both lists: the drop rule and the wear rule both name her.
            self.assertEqual((row["usable_by"], row["designated_class"], row["pool_version"], row["craft_only"]),
                             ("shaman", "shaman", "yes", "no"), row)
        # The brief: 1.30 attacks a second, "like the Flail" (its damage range; the Flail swings 1.4).
        for row in (mace, legendary):
            self.assertEqual((row["weapon_aps"], row["weapon_min"], row["weapon_max"]), ("1.3", flail["weapon_min"], flail["weapon_max"]))
        # The Totem is a Source's shape: no base range of its own (added weapon damage is the pool's required line).
        self.assertEqual((totem["weapon_min"], totem["weapon_max"], totem["weapon_aps"]), ("", "", ""))

    def test_the_entries_are_the_published_identities_and_follow_the_set_caches(self):
        found = ids()
        self.assertEqual({d3: found[d3] for d3 in NEW}, NEW)
        caches = {int(r["entry"]) for r in sheet(D3 / "set_caches.csv")}
        shipped = g.shipped_entries(D3 / "base_items.csv")
        self.assertEqual(len(shipped), 1114)
        self.assertEqual(set(found.values()) - shipped, set(NEW.values()))
        self.assertEqual(caches & set(found.values()), set(), "an entry is a cache or a base item, never both")
        self.assertGreater(min(NEW.values()), max(caches))
        # The migration inserts exactly these three into dc_base_item and into item_template.
        text = ADDED.read_text(encoding="utf-8")
        base_part = text.split("INSERT INTO `dc_base_item`", 1)[1].split(";\n", 1)[0]
        self.assertEqual(sorted(int(e) for e in re.findall(r"^\((\d+), ", base_part, re.M)), sorted(NEW.values()))
        self.assertEqual(g.added_entries(D3 / "base_items.csv"), set(NEW.values()))

    def stock_item(self, entry):
        path = STOCK_DBC / "Item.dbc"
        if not path.is_file():
            self.skipTest("the stock Item.dbc is not on this machine")
        store = Store(path.read_bytes(), schema(ROOT, "item_dbc"))
        return store.decode(entry)

    def test_the_looks_are_the_stock_items_rows(self):
        displays = {(r["slot"], r["type"]): r for r in sheet(D3 / "item_display.csv")}
        for key, want_class, want_sub in ((("onehand", "Ritual Mace"), 2, 4), (("offhand", "Totem"), 4, 0)):
            row = displays[key]
            stock = self.stock_item(int(row["wow_item_id"]))
            self.assertEqual((stock["DisplayInfoID"], stock["InventoryType"], stock["ClassID"], stock["SubclassID"]),
                             (int(row["wow_display_id"]), int(row["inventory_type"]), want_class, want_sub), key)

    def test_the_templates_and_the_client_rows_say_the_same(self):
        text = ADDED.read_text(encoding="utf-8")
        part = text.split("INSERT INTO `item_template`", 1)[1].split(";\n", 1)[0]
        rows = {int(m[0]): m for m in re.findall(
            r"^\((\d+), (\d+), (\d+), '((?:[^']|'')*)', (\d+), (\d+), (\d+), (\d+), (\d+), (\d+), (\d+), (\d+), (\d+)\)", part, re.M)}
        displays = {(r["slot"], r["type"]): int(r["wow_display_id"]) for r in sheet(D3 / "item_display.csv")}
        # entry, class, subclass, name, display, quality, inventory, ilvl, reqlevel, min, max, dmgtype, delay
        mace, totem, legendary = rows[101176], rows[101177], rows[101178]
        self.assertEqual((mace[1], mace[2], mace[4], mace[5], mace[6], mace[9], mace[10], mace[12]),
                         ("2", "4", str(displays[("onehand", "Ritual Mace")]), "1", "13", "192", "355", "769"))
        self.assertEqual((totem[1], totem[2], totem[4], totem[5], totem[6], totem[12]),
                         ("4", "0", str(displays[("offhand", "Totem")]), "1", "23", "0"))
        self.assertEqual((legendary[5], legendary[6], legendary[12]), ("5", "13", "769"))
        # The client resolves the bag icon and the equip slot from its own Item.dbc: a row per entry, the template's.
        client = Store((ROOT / "client-patch" / "dbc" / "Item.dbc").read_bytes(), schema(ROOT, "item_dbc"))
        for entry, row in rows.items():
            record = client.decode(entry)
            self.assertEqual((record["ClassID"], record["SubclassID"], record["DisplayInfoID"], record["InventoryType"]),
                             (int(row[1]), int(row[2]), int(row[4]), int(row[6])), entry)
        self.assertEqual({e: client.decode(e)["SheatheType"] for e in rows}, {101176: 3, 101177: 7, 101178: 3})

    def test_the_weapon_class_and_the_subclass(self):
        classes = {r["weapon_type"]: r["weapon_class"] for r in sheet(D3 / "weapon_classes.csv")}
        self.assertEqual(classes["Ritual Mace"], "damage1HNormal")        # the Flail's, the draft's "like the Flail"
        self.assertEqual(g.WEAPON_SUBCLASS["Ritual Mace"], g.WEAPON_SUBCLASS["Mace"])
        self.assertIn("'Ritual Mace'", (UPDATES / "items_0059_weapon_class.sql").read_text(encoding="utf-8"))
        self.assertEqual(g.check_weapon_classes(MODULE), len({r["type"] for r in bases() if r["slot"] in ("onehand", "twohand")}))


# --- 2. who may wear what -----------------------------------------------------------------------------------------------
def wear_problems(rows, entry_of, mask_of):
    """The Shaman's wear rule against the draft's 1.7, as a list of problems."""
    problems = []
    seen = {}
    for base in rows:
        key = (base["slot"], base["type"])
        # A set piece is locked to its set's class (items_0020), so it says nothing about the type.
        if base["slot"] not in ("onehand", "twohand", "offhand") or base["designated_class"] not in ("", "shaman") \
                or base["rarity"] == "set":
            continue
        mask = mask_of.get(entry_of[base["d3_id"]], -1)
        seen.setdefault(key, set()).add(wearable(mask))
    for key, answers in seen.items():
        if answers != {key in DRAFT_HANDS}:
            problems.append((key, answers))
    for key in DRAFT_HANDS - set(seen):
        problems.append((key, "no base"))
    for base in rows:
        if base["type"] in CLASS_ITEMS:
            mask = mask_of.get(entry_of[base["d3_id"]], -1)
            if mask != SHAMAN_BIT:
                problems.append((base["d3_id"], mask))
    return problems


class Wear(unittest.TestCase):
    def test_the_shaman_wears_the_drafts_weapons_and_no_others(self):
        self.assertEqual(wear_problems(bases(), ids(), masks()), [])

    def test_only_the_shamans_bit_was_added_to_the_masks_of_the_shipped_bases(self):
        before = {}
        for name in ("items_0011_item_allowable_class.sql", "items_0020_set_wear_class.sql",
                     "items_0028_item_allowable_class_added.sql", "items_0053_item_allowable_class_added.sql"):
            for mask, entries in re.findall(r"SET `AllowableClass`=(-?\d+) WHERE `entry` IN \(([^)]*)\)",
                                            (UPDATES / name).read_text(encoding="utf-8")):
                before.update({int(e): int(mask) for e in entries.split(",")})
        after = masks()
        entry_of = ids()
        for base in bases():
            entry = entry_of[base["d3_id"]]
            if entry not in before or base["rarity"] == "set":      # a set piece is locked to its set's class
                continue
            listed = "shaman" in base["usable_by"].split(";") and base["designated_class"] in ("", "shaman")
            if before[entry] == after[entry]:
                self.assertFalse(listed and before[entry] >= 0, base["d3_id"])
            else:
                self.assertEqual(after[entry] - before[entry], SHAMAN_BIT, base["d3_id"])
                self.assertTrue(listed, base["d3_id"])

    def test_the_usable_by_migration_is_the_sheet_against_0002(self):
        applied = g.base_item_rows((UPDATES / "0002_dc_base_item.sql").read_text(encoding="utf-8"))
        changed = {}
        entry_of = ids()
        for base in bases():
            entry = entry_of[base["d3_id"]]
            if entry in applied and applied[entry][g.BASE_ITEM_USABLE_BY_INDEX] != base["usable_by"]:
                changed[entry] = base["usable_by"]
        self.assertEqual(len(changed), 159)
        migration = (UPDATES / g.BASE_USABLE_BY_MIGRATION).read_text(encoding="utf-8")
        carried = {int(e) for _, found in re.findall(r"SET `usable_by`='([^']*)' WHERE `entry` IN \(([^)]*)\)", migration)
                   for e in found.split(",")}
        self.assertEqual(carried, set(changed))
        for entry, value in changed.items():
            self.assertTrue(value.endswith(";shaman") and value.count("shaman") == 1, (entry, value))
        # every one of them is a type of the draft's list
        types = {(b["slot"], b["type"]) for b in bases() if entry_of[b["d3_id"]] in changed}
        self.assertEqual(types, DRAFT_HANDS - {("onehand", "Ritual Mace"), ("offhand", "Totem")})


# --- 3. what drops ------------------------------------------------------------------------------------------------------
def eligibility(classes, header_dir=MODULE / "src" / "items"):
    """{(usable_by, designated): [classes that may roll it]} out of the production header, compiled."""
    if not CXX:
        raise unittest.SkipTest("no C++ compiler")
    pairs = sorted({(b["usable_by"], b["designated_class"]) for b in bases()})
    lit = lambda text: '"' + text + '"'
    code = ('#include "dc_roll_class.h"\n#include <iostream>\nint main()\n{\n    using namespace DC::RollClass;\n'
            + "".join(f'    for (char const* roll : {{{", ".join(lit(c) for c in classes)}}})\n'
                      f'        if (Eligible({lit(u)}, {lit(d)}, roll))\n'
                      f'            std::cout << {lit(u + "|" + d)} << " " << roll << "\\n";\n' for u, d in pairs)
            + "    return 0;\n}\n")
    with tempfile.TemporaryDirectory(prefix="dc-shaman-drops-") as folder:
        cpp, binary = Path(folder) / "t.cpp", Path(folder) / "t"
        cpp.write_text(code, encoding="utf-8")
        built = subprocess.run([CXX, "-std=c++17", "-I", str(header_dir), "-o", str(binary), str(cpp)],
                               capture_output=True, text=True)
        assert built.returncode == 0, built.stderr[-2000:]
        ran = harness_env.run([str(binary)], capture_output=True, text=True)
    out = {}
    for line in ran.stdout.splitlines():
        key, roll = line.rsplit(" ", 1)
        out.setdefault(tuple(key.split("|")), []).append(roll)
    return out


class Drops(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.answers = eligibility(("shaman",) + OTHER_CLASSES)

    def rollers(self, base):
        return set(self.answers.get((base["usable_by"], base["designated_class"]), []))

    def test_the_class_items_roll_for_the_shaman_alone(self):
        for base in bases():
            if base["type"] in CLASS_ITEMS:
                self.assertEqual(self.rollers(base), {"shaman"}, base["d3_id"])
                self.assertTrue(in_pool(base), base["d3_id"])

    def test_the_shaman_rolls_the_drafts_types_and_no_other_classs_item(self):
        for base in bases():
            if not in_pool(base) or base["type"] in CLASS_ITEMS:
                continue
            rolls = "shaman" in self.rollers(base)
            if base["designated_class"] not in ("", "shaman"):
                self.assertFalse(rolls, base["d3_id"])          # another class's own item
            elif base["slot"] in ("onehand", "twohand", "offhand"):
                self.assertEqual(rolls, (base["slot"], base["type"]) in DRAFT_HANDS, base["d3_id"])
            else:
                self.assertTrue(rolls, base["d3_id"])           # armor and jewelry name no class

    def test_every_hand_slot_has_a_shaman_legendary_for_kadala_and_the_vendors(self):
        have = {(b["slot"], b["type"]) for b in bases()
                if b["rarity"] == "legendary" and in_pool(b) and "shaman" in self.rollers(b)}
        self.assertIn(("onehand", "Ritual Mace"), have)
        # The Totem has no legendary yet: the Shaman's legendaries are step 3 of her build (paused).
        self.assertNotIn(("offhand", "Totem"), have)
        self.assertTrue({("onehand", "Sword"), ("twohand", "Staff"), ("offhand", "Shield")} <= have)


# --- 4. the weapon proficiencies ----------------------------------------------------------------------------------------
class Proficiencies(unittest.TestCase):
    def test_every_weapon_she_may_wield_has_a_skill(self):
        needed = proficiencies.weapon_skills(MODULE, "shaman")
        # Ritual Mace is a Mace (skill 54); Spear takes the Swords proficiency (generate_sql.WEAPON_SUBCLASS).
        self.assertEqual(sorted(needed), [43, 44, 54, 55, 136, 160, 172, 173])
        self.assertIn("Ritual Mace", needed[54])
        records, _, _ = proficiencies.render(MODULE)
        added = sorted(r["SkillID"] for r in records if r["ClassMask"] == SHAMAN_BIT)
        # The stock Shaman has axes, maces, staves and daggers; swords and two-handed swords are the rows added.
        self.assertEqual(added, [43, 55])
        text = (UPDATES / proficiencies.MIGRATION).read_text(encoding="utf-8")
        for record in records:
            if record["ClassMask"] == SHAMAN_BIT:
                self.assertIn(f"({record['ID']},{record['SkillID']},0,{SHAMAN_BIT},", text)


# --- 5. the affix pools -------------------------------------------------------------------------------------------------
def pool_program(mutate=None):
    """The production PoolFor, compiled over the real pool sheets; prints each type's lines per bracket."""
    source = items_source.read("dc_items_data.cpp")
    function = items_source.block("std::vector<PoolEntry> PoolFor(BaseItem const& base, std::string const& bracket)", source)
    if mutate:
        old, new = mutate
        assert function.count(old) == 1, old
        function = function.replace(old, new)
    header = (MODULE / "src" / "items" / "dc_items.h").read_text(encoding="utf-8")
    entry = items_source.block("struct PoolEntry\n", header)
    rows = sheet(D3 / "affix_pools.csv") + sheet(D3 / "class_item_pools.csv")
    literal = lambda r: '{"%s", "%s", "%s"}' % (r["slot"], r["item_level_bracket"], r["affix_id"])
    types = sorted({(b["slot"], b["type"]) for b in bases() if b["slot"] in ("onehand", "twohand", "offhand")})
    return ("#include <cstdint>\n#include <iostream>\n#include <string>\n#include <unordered_map>\n#include <vector>\nnamespace DC::Items\n{\n"
            + entry + items_source.struct("BaseItem")
            + "std::unordered_map<std::string, std::unordered_map<std::string, std::vector<PoolEntry>>> pools;\n"
            + function
            + "}\nusing namespace DC::Items;\nint main()\n{\n"
            + "    struct Row { char const *slot, *bracket, *id; };\n    Row const rows[] = {"
            + ", ".join(literal(r) for r in rows) + "};\n"
            + "    for (Row const& r : rows)\n    {\n        PoolEntry e; e.affixId = r.id; e.bracket = r.bracket;\n"
              "        pools[r.slot][r.bracket].push_back(e);\n    }\n"
            + "    struct Type { char const *slot, *type; };\n    Type const types[] = {"
            + ", ".join('{"%s", "%s"}' % t for t in types) + "};\n"
            + '    for (Type const& t : types)\n        for (char const* bracket : {"rare", "legendary", "ancient", "primal"})\n'
              "        {\n            BaseItem base; base.slot = t.slot; base.type = t.type;\n"
              '            std::cout << t.slot << "|" << t.type << "|" << bracket << "|";\n'
              '            for (PoolEntry const& e : PoolFor(base, bracket))\n                std::cout << e.affixId << ",";\n'
              '            std::cout << "\\n";\n        }\n    return 0;\n}\n')


def pool_run(mutate=None):
    if not CXX:
        raise unittest.SkipTest("no C++ compiler")
    with tempfile.TemporaryDirectory(prefix="dc-shaman-pools-") as folder:
        cpp, binary = Path(folder) / "t.cpp", Path(folder) / "t"
        cpp.write_text(pool_program(mutate), encoding="utf-8")
        built = subprocess.run([CXX, "-std=c++17", "-o", str(binary), str(cpp)], capture_output=True, text=True)
        assert built.returncode == 0, built.stderr[-3000:]
        ran = harness_env.run([str(binary)], capture_output=True, text=True)
    out = {}
    for line in ran.stdout.splitlines():
        slot, type_, bracket, ids_ = line.split("|")
        out[(slot, type_, bracket)] = [i for i in ids_.split(",") if i]
    return out


def pool_problems(out):
    problems = []
    rows = sheet(D3 / "class_item_pools.csv")
    own = {}
    for r in rows:
        slot, type_ = r["slot"].split(":")
        own.setdefault((slot, type_, r["item_level_bracket"]), []).append(r["affix_id"])
    generic = {}
    for r in sheet(D3 / "affix_pools.csv"):
        generic.setdefault((r["slot"], r["item_level_bracket"]), []).append(r["affix_id"])
    for (slot, type_, bracket), got in out.items():
        want = generic.get((slot, bracket), []) + own.get((slot, type_, bracket), [])
        if got != want:
            problems.append(((slot, type_, bracket), sorted(set(got) ^ set(want))))
    return problems


class Pools(unittest.TestCase):
    def test_a_type_rolls_its_slots_pool_and_its_own_lines_and_no_other_types(self):
        out = pool_run()
        self.assertEqual(pool_problems(out), [])
        self.assertEqual(len(out), len({(b["slot"], b["type"]) for b in bases() if b["slot"] in ("onehand", "twohand", "offhand")}) * 4)
        for bracket in BRACKETS:
            mace = out[("onehand", "Ritual Mace", bracket)]
            totem = out[("offhand", "Totem", bracket)]
            self.assertTrue({"dmgphy", "dmgfir", "dmgcol", "dmglit", "maelstromgen"} <= set(mace))
            self.assertTrue({"maxmaelstrom", "cdr", "rcr", "area", "primarymaelstrom"} <= set(totem))
            self.assertNotIn("maxmaelstrom", mace)
            self.assertNotIn("primarymaelstrom", mace)
            self.assertNotIn("maelstromgen", totem)
            for key, got in out.items():
                if key[2] == bracket and key[1] != "Ritual Mace":
                    self.assertFalse({"dmgphy", "dmgfir", "dmgcol", "dmglit"} & set(got), key)
                if key[2] == bracket and key[1] != "Totem":
                    self.assertNotIn("maxmaelstrom", got, key)
                    self.assertNotIn("primarymaelstrom", got, key)
                if key[2] == bracket and key[1] != "Ritual Mace":
                    self.assertNotIn("maelstromgen", got, key)
        # a Sword and a Shield roll their slot's pool unchanged
        for bracket in BRACKETS:
            self.assertEqual(out[("onehand", "Sword", bracket)], out[("onehand", "Mace", bracket)])
            self.assertEqual(out[("offhand", "Shield", bracket)], out[("offhand", "Source", bracket)])

    def test_the_draft_numbers_and_the_cross_source_rows(self):
        rows = sheet(D3 / "class_item_pools.csv")
        for r in rows:
            if r["affix_id"] == "maxmaelstrom":
                self.assertEqual((r["slot"], r["value_min"], r["value_max"], r["is_percent"]), ("offhand:Totem", "10", "20", "0"))
        # The draft (5.1, 5.2): "Primary skills generate +1-3 Maelstrom (Totem only)" and "Maelstrom generation +5-10% (Ritual Mace
        # only)", on the two stats Shaman 2b appended to the sheet (xnrvn.9).
        lines = {r["affix_id"]: r for r in rows if r["affix_id"] in ("primarymaelstrom", "maelstromgen")}
        self.assertEqual(len([r for r in rows if r["affix_id"] in lines]), 8)
        for r in rows:
            if r["affix_id"] == "primarymaelstrom":
                self.assertEqual((r["slot"], r["value_min"], r["value_max"], r["is_percent"], r["kind"]),
                                 ("offhand:Totem", "1", "3", "0", "primary"), r)
            if r["affix_id"] == "maelstromgen":
                self.assertEqual((r["slot"], r["value_min"], r["value_max"], r["is_percent"], r["kind"]),
                                 ("onehand:Ritual Mace", "5", "10", "1", "primary"), r)
        one = {(r["affix_id"], r["item_level_bracket"]): r for r in sheet(D3 / "affix_pools.csv") if r["slot"] == "onehand"}
        for r in rows:
            if r["affix_id"] in ("cdr", "rcr", "area"):
                peer = one[(r["affix_id"], r["item_level_bracket"])]
                self.assertEqual((r["value_min"], r["value_max"], r["is_percent"], r["affix_name"]),
                                 (peer["value_min"], peer["value_max"], peer["is_percent"], peer["affix_name"]), r)
        metadata = {r["affix_id"]: r["affix_name"] for r in sheet(D3 / "affix_metadata.csv")}
        elemental = {r["item_level_bracket"]: (r["value_min"], r["value_max"])
                     for r in sheet(D3 / "affix_pools.csv") if r["slot"] == "neck" and r["affix_id"] == "elemental"}
        for r in rows:
            if r["affix_id"].startswith("dmg"):
                self.assertEqual(r["affix_name"], metadata[r["affix_id"]], r)
                self.assertEqual((r["value_min"], r["value_max"]), elemental[r["item_level_bracket"]], r)
        # every line the sheet lists reaches the character sheet through Mappings()
        mapping = items_source.mappings()
        elemental = items_source.table("ElementalAffixes")
        for r in rows:
            where = elemental if r["affix_id"].startswith("dmg") else mapping
            self.assertIn('{"%s",' % r["affix_id"], where, r["affix_id"])
        self.assertIn('{"maxmaelstrom", {Stat::MaxFury, Bucket::Flat, Element::Physical, "maelstrom"}}', mapping)
        self.assertIn('{"primarymaelstrom", {Stat::PrimaryMaelstrom}}', mapping)
        self.assertIn('{"maelstromgen", {Stat::MaelstromGeneration}}', mapping)
        resources = {r["resource_key"] for r in sheet(D3 / "class_resources.csv") if r["d3_class"] == "Shaman"}
        self.assertEqual(resources, {"maelstrom"})

    def test_the_migration_is_what_the_generator_renders(self):
        # items_0061 shipped without the two Maelstrom lines (merged, so frozen); they ride in their own migration.
        for name, text in ((pools_gen.MIGRATION, pools_gen.render(MODULE)),
                           (pools_gen.MAELSTROM_MIGRATION, pools_gen.render_maelstrom(MODULE))):
            self.assertEqual((UPDATES / name).read_text(encoding="utf-8"), text, name)
            self.assertEqual((MODULE / "data" / "generated" / name).read_text(encoding="utf-8"), text, name)
        self.assertNotIn("primarymaelstrom", pools_gen.render(MODULE))
        self.assertNotIn("maelstromgen", pools_gen.render(MODULE))
        later = pools_gen.render_maelstrom(MODULE)
        self.assertEqual(later.count("('offhand:Totem','primarymaelstrom'"), 4)
        self.assertEqual(later.count("('onehand:Ritual Mace','maelstromgen'"), 4)
        self.assertNotIn("maxmaelstrom", later)   # 0061's lines are not written twice
        self.assertIn("AND affix_id IN ('maelstromgen','primarymaelstrom')", later)
        slots = {r["slot"] for r in sheet(D3 / "class_item_pools.csv")}
        self.assertEqual(slots, {"onehand:Ritual Mace", "offhand:Totem"})

    def test_the_lines_that_wait_on_a_system_are_not_in_the_pools(self):
        # The draft lists "Increases [Shaman skill] Damage" (needs the skill records, 2a): no stat or effect exists for
        # it, so no row does either (AGENTS.md "No stand-ins"). The two Maelstrom lines have their stats since 2b.
        ids_ = {r["affix_id"] for r in sheet(D3 / "class_item_pools.csv")}
        self.assertEqual(ids_, {"dmgphy", "dmgfir", "dmgcol", "dmglit", "maxmaelstrom", "cdr", "rcr", "area",
                                "primarymaelstrom", "maelstromgen"})

    def test_the_totem_takes_the_sources_required_damage_line(self):
        source = items_source.source()
        self.assertIn('base.type == "Phylactery" || base.type == "Totem"', source)

    def test_mutants_are_caught(self):
        for old, new in (('base.slot + ":" + base.type', 'base.slot + ":Totem"'),       # every type gets the Totem's lines
                         ('base.slot + ":" + base.type', 'base.slot')):                   # no type gets its own
            with self.subTest(mutation=new):
                self.assertNotEqual(pool_problems(pool_run((old, new))), [], new)


# --- 7. the start profile ------------------------------------------------------------------------------------------------
class Profile(unittest.TestCase):
    """The Shaman's kit: a Ritual Mace legendary and a Totem, the rest the Barbarian's pattern (class_starts.csv)."""

    def profile(self):
        return g.class_start_rows(D3 / "class_starts.csv")[7]

    def test_the_kit_is_a_ritual_mace_legendary_a_totem_and_the_patterned_rest(self):
        kit = {row["slot"]: row for row in self.profile()["kit"]}
        self.assertEqual(self.profile()["class_key"], "shaman")
        self.assertEqual(set(kit), {"mainhand", "offhand", "head", "neck", "shoulders", "torso", "waist", "legs", "feet", "wrists",
                                    "hands", "finger"})
        self.assertEqual((kit["mainhand"]["rarity"], kit["mainhand"]["base_type"], kit["mainhand"]["base_slot"],
                          kit["mainhand"]["designated_class"]), ("legendary", "Ritual Mace", "onehand", "shaman"))
        self.assertEqual((kit["offhand"]["rarity"], kit["offhand"]["base_type"], kit["offhand"]["base_slot"],
                          kit["offhand"]["designated_class"]), ("rare", "Totem", "offhand", "shaman"))
        # the other ten slots are the Necromancer's rows (the same pattern, no filters)
        other = {row["slot"]: row for row in g.class_start_rows(D3 / "class_starts.csv")[13]["kit"]}
        for slot in kit:
            if slot not in ("mainhand", "offhand"):
                self.assertEqual({k: kit[slot][k] for k in ("rarity", "count", "base_type")},
                                 {k: other[slot][k] for k in ("rarity", "count", "base_type")}, slot)

    def test_every_kit_slot_has_a_base_to_pick_and_the_class_slots_pick_hers(self):
        profile = self.profile()
        for kit in profile["kit"]:
            pool = g.starter_candidates(profile, kit, bases())
            self.assertTrue(pool, kit["slot"])
            if kit["slot"] in ("mainhand", "offhand"):
                self.assertEqual({b["d3_id"] for b in pool},
                                 {"Shaman_Unique_RitualMace_001"} if kit["slot"] == "mainhand" else {"Shaman_Totem_001"})

    def test_the_weapon_skills_are_the_ones_her_weapons_need(self):
        profile = self.profile()
        need = set(proficiencies.weapon_skills(MODULE, "shaman"))
        self.assertEqual({row["skill_id"] for row in profile["skills"]}, need)
        # each skill's proficiency spell is the one every other class's profile uses for it
        spells = {}
        for key, other in g.class_start_rows(D3 / "class_starts.csv").items():
            if key != 7:
                for row in other["skills"]:
                    spells.setdefault(row["skill_id"], set()).add(row["spell_id"])
        for row in profile["skills"]:
            self.assertEqual(spells[row["skill_id"]], {row["spell_id"]}, row)

    def test_the_migration_and_the_legacy_companion_name_her(self):
        sql = (UPDATES / g.CLASS_START_MIGRATION).read_text(encoding="utf-8")
        self.assertIn("INSERT INTO dc_class_start VALUES (7,'shaman','Shaman');", sql)
        self.assertEqual(sql.count("INSERT INTO dc_class_starter_kit VALUES (7,"), 12)
        self.assertEqual(sql.count("INSERT INTO dc_class_start_skill VALUES (7,"), 8)
        legacy = (ROOT / "mod-diablocraft" / "data" / "sql" / "db-characters" / "updates" / g.CLASS_START_LEGACY_MIGRATION).read_text(encoding="utf-8")
        self.assertIn("WHERE class IN (7);", legacy)

    def test_a_kit_with_no_base_is_refused(self):
        # AGENTS.md "No stand-ins": the generator refuses a kit slot whose type has no base. Without the Totem the Shaman's
        # offhand pool is empty.
        without = [b for b in bases() if b["type"] != "Totem"]
        profile = self.profile()
        offhand = next(k for k in profile["kit"] if k["slot"] == "offhand")
        self.assertEqual(g.starter_candidates(profile, offhand, without), [])


# --- the mutation tests of the wear and drop checks ---------------------------------------------------------------------
class Mutants(unittest.TestCase):
    def test_a_wrong_mask_is_caught(self):
        entry_of, mask_of = ids(), masks()
        rows = bases()
        mace = entry_of["Shaman_RitualMace_001"]
        for mutated in ({**mask_of, mace: SHAMAN_BIT | 1},                      # a Barbarian could wield the class mace
                        {**mask_of, mace: 0},                                    # nobody could
                        {**mask_of, entry_of["Polearm_302"]: -1}):                 # a Shaman could wield a polearm
            self.assertNotEqual(wear_problems(rows, entry_of, mutated), [])

    def test_a_header_that_ignores_both_class_lists_leaks_the_class_items(self):
        header = (MODULE / "src" / "items" / "dc_roll_class.h").read_text(encoding="utf-8")
        old = ("return !rollClass.empty() && (usableBy.empty() || Lists(usableBy, rollClass)) &&\n"
               "               (designated.empty() || designated == rollClass);")
        self.assertEqual(header.count(old), 1)
        with tempfile.TemporaryDirectory(prefix="dc-shaman-mutant-") as folder:
            (Path(folder) / "dc_roll_class.h").write_text(header.replace(old, "return !rollClass.empty();"), encoding="utf-8")
            answers = eligibility(("shaman",) + OTHER_CLASSES, Path(folder))
        self.assertGreater(len(answers[("shaman", "shaman")]), 1)       # the Barbarian etc. could roll the Ritual Mace


if __name__ == "__main__":
    unittest.main()
