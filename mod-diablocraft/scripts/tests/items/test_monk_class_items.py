"""diablocraft-h943x: the Monk's class items, proved from the sheets and the applied migrations.

    python3 mod-diablocraft/scripts/tests/items/test_monk_class_items.py

Four points (brief monk-class-items-2026-10-13), each read from what the generators and migrations emit, never from a
live server (nobody can log in here; the in-game steps are docs/test-diablocraft-h943x.md):
  1. who may wear the Monk's items: the AllowableClass the applied migrations leave (items_0011, 0020, 0028 replayed in
     order), the weapon and head inventory types, and the proficiency / dual-wield spells the start kit teaches;
  2. what a Monk's drops roll: the drop pool rules of src/items/dc_roll_class.h (pinned in the header, mirrored here) give
     a Monk its class-only items and a Barbarian none of them, as the Barbarian's Mighty Weapons and Belts;
  3. Kadala, the slot vendors, the Blacksmith and the Mystic carry rows a Monk reaches;
  4. every base row, every Monk legendary and every Monk set piece of the catalogue has its item id.
The roller, the database and delivery are not run here (test_class_roll_rules.py compiles the header, and the checks of the
sheet do the rest). Each check is a function of the data it is given, so the mutation tests below hand it a broken copy.
"""
import csv
import re
import unittest
from collections import Counter
from pathlib import Path

MODULE = Path(__file__).resolve().parents[3]
ROOT = MODULE.parent
D3 = MODULE / "data" / "d3"
UPDATES = MODULE / "data" / "sql" / "db-world" / "updates"
MONK_BIT = 1 << 11            # WoW class 12 (the Monk), class_map.csv wow_class_id
WEAPON_SKILL = {10: 136, 13: 473}  # ItemSubClassToSkill: ITEM_SUBCLASS_WEAPON_STAFF, ITEM_SUBCLASS_WEAPON_FIST
CATALOGUE = ROOT / "docs" / "research" / "legendary-catalogue.csv"


def sheet(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def masks():
    """entry -> AllowableClass after items_0011, items_0020 and items_0028, in the order the core applies them."""
    out = {}
    for name in ("items_0011_item_allowable_class.sql", "items_0020_set_wear_class.sql",
                 "items_0028_item_allowable_class_added.sql"):
        for mask, entries in re.findall(r"SET `AllowableClass`=(-?\d+) WHERE `entry` IN \(([^)]*)\)",
                                        (UPDATES / name).read_text(encoding="utf-8")):
            out.update({int(entry): int(mask) for entry in entries.split(",")})
    return out


def eligible(base, set_class, roll):
    """dc_roll_class.h DropEligible: usable_by names the class (or none), and the item's drop class is nobody's or its."""
    drop = base["designated_class"] or set_class.get(base["set_name"], "")
    return (not base["usable_by"] or roll in base["usable_by"].split(";")) and (not drop or drop == roll)


def in_pool(base):
    return base["pool_version"] == "yes" and base["craft_only"] != "yes" and base["rarity"] != "ethereal"


# --- the checks: each returns a list of problems ---------------------------------------------------------------------
def wear_problems(bases, ids, mask):
    problems = []
    for base in bases:
        entry, designated = ids[base["d3_id"]], base["designated_class"]
        got = mask.get(entry, -1)
        if designated == "monk" and got != MONK_BIT:
            problems.append(f"{base['d3_id']}: a Monk-only base wears as {got}, not {MONK_BIT}")
        if designated and designated != "monk" and got not in (0, -1) and got & MONK_BIT:
            problems.append(f"{base['d3_id']}: another class's base can be worn by a Monk ({got})")
    return problems


def pool_problems(bases, set_class):
    problems = []
    own, kinds = {}, {}
    for roll in ("barbarian", "monk"):
        pool = [b for b in bases if in_pool(b) and eligible(b, set_class, roll)]
        kinds[roll] = Counter(b["type"] for b in pool)
        own[roll] = Counter(b["type"] for b in pool if (b["designated_class"] or set_class.get(b["set_name"], "")) == roll)
        foreign = [b["d3_id"] for b in pool if (b["designated_class"] or set_class.get(b["set_name"], "")) not in ("", roll)]
        if foreign:
            problems.append(f"{roll} rolls another class's class-only items: {foreign[:3]}")
    for kind in ("Fist Weapon", "Daibo", "Spirit Stone"):
        if not own["monk"][kind]:
            problems.append(f"a Monk's drops hold no {kind}")
        if kinds["barbarian"][kind]:
            problems.append(f"a Barbarian's drops hold {kind}")
    for kind in ("Mighty Weapon", "Two-Handed Mighty Weapon", "Mighty Belt"):
        if kinds["monk"][kind] or not own["barbarian"][kind]:
            problems.append(f"{kind} must drop for the Barbarian and never for a Monk")
    return problems


def vendor_problems(bases, set_class, entries, vendors):
    """Every Kadala entry and slot vendor a Monk can use has a Monk-eligible legendary or set to hand out."""
    problems = []
    for slot, types in [(e["slot"], [t for t in e["base_types"].split(";") if t]) for e in entries] + \
                       [(v["slot"], []) for v in vendors]:
        if slot == "offhand":
            continue                       # D3's Monk has no off-hand type; the Source, Quiver, Mojo and Phylactery are others'
        pool = [b for b in bases if in_pool(b) and b["rarity"] in ("legendary", "set") and b["slot"] == slot
                and (not types or b["type"] in types) and eligible(b, set_class, "monk")]
        if not pool:
            problems.append(f"nothing a Monk can wear is offered for slot {slot} {types}")
    return problems


class WearAndProficiency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bases = sheet(D3 / "base_items.csv")
        cls.ids = {r["d3_id"]: int(r["item_entry"]) for r in sheet(D3 / "base_item_ids.csv")}
        cls.mask = masks()

    def test_a_monk_only_base_is_worn_by_a_monk_and_nobody_else(self):
        self.assertEqual(wear_problems(self.bases, self.ids, self.mask), [])
        for kind in ("FistWeapon_1H_206", "CombatStaff_2H_302", "SpiritStone_206"):
            self.assertEqual(self.mask[self.ids[kind]], MONK_BIT, kind)
        self.assertEqual(self.mask[self.ids["BarbBelt_206"]] & MONK_BIT, 0)       # the Barbarian's Mighty Belt

    def test_the_three_class_bases_carry_the_inventory_types_the_monks_proficiencies_allow(self):
        template = (UPDATES / "0002_dc_item_template.sql").read_text(encoding="utf-8")
        row = lambda entry: re.search(rf"^\({entry}, (\d+), (\d+), '[^']*', \d+, \d+, (\d+),", template, re.M).groups()
        fist, daibo, stone = (tuple(map(int, row(self.ids[k]))) for k in
                              ("FistWeapon_1H_206", "CombatStaff_2H_302", "SpiritStone_206"))
        self.assertEqual(fist, (2, 13, 13))     # a weapon, fist, one-handed
        self.assertEqual(daibo, (2, 10, 17))    # a weapon, staff, two-handed
        self.assertEqual(stone[0], 4)           # armor; items_0009 moves the class's armor to Miscellaneous, which needs no skill
        starts = [r for r in sheet(D3 / "class_starts.csv") if r["class_id"] == "12" and r["row_type"] == "skill"]
        taught = {int(r["spell_id"]) for r in starts}
        skills = {int(r["skill_id"]) for r in starts}
        for subclass, skill in WEAPON_SKILL.items():
            self.assertIn(skill, skills, f"the Monk is taught no skill {skill} for weapon subclass {subclass}")
        self.assertIn(15590, taught)            # Fist Weapons
        self.assertIn(227, taught)              # Staves
        self.assertIn((674, 118), {(int(r["spell_id"]), int(r["skill_id"])) for r in starts})   # Dual Wield: a fist in each hand
        proficiencies = {r["skill_id"] for r in sheet(MODULE / "data" / "class_proficiency_ids.csv") if r["class_key"] == "monk"}
        self.assertLessEqual({"473", "136"}, proficiencies)

    def test_the_wear_check_catches_a_wrong_mask(self):
        broken = dict(self.mask)
        broken[self.ids["SpiritStone_206"]] = 1                                   # a Barbarian's mask
        self.assertTrue(wear_problems(self.bases, self.ids, broken))
        broken[self.ids["SpiritStone_206"]] = MONK_BIT | 1                        # a Monk and a Barbarian
        self.assertTrue(wear_problems(self.bases, self.ids, broken))
        broken = dict(self.mask)
        broken[self.ids["BarbBelt_206"]] = MONK_BIT | 1                           # a Monk wears a Mighty Belt
        self.assertTrue(wear_problems(self.bases, self.ids, broken))


class Drops(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bases = sheet(D3 / "base_items.csv")
        cls.set_class = {r["set_name"]: r["class_key"] for r in sheet(D3 / "set_classes.csv")}

    def test_a_monk_rolls_its_class_items_and_a_barbarian_never_sees_them(self):
        self.assertEqual(pool_problems(self.bases, self.set_class), [])

    def test_the_header_still_says_what_this_mirrors(self):
        header = (MODULE / "src" / "items" / "dc_roll_class.h").read_text(encoding="utf-8")
        self.assertIn("return !rollClass.empty() && (usableBy.empty() || Lists(usableBy, rollClass)) &&\n"
                      "               (designated.empty() || designated == rollClass);", header)
        self.assertIn("return designated.empty() ? setClass : designated;", header)
        self.assertIn('return poolVersion == "yes" && craftOnly != "yes" && rarity != "ethereal";', header)

    def test_the_pool_check_catches_a_leak_and_a_missing_class_item(self):
        leaked = [dict(b, usable_by="", designated_class="") if b["d3_id"] == "SpiritStone_206" else b for b in self.bases]
        self.assertTrue(pool_problems(leaked, self.set_class))                    # nobody's Spirit Stone drops for a Barbarian
        crippled = [dict(b, pool_version="no") if b["type"] == "Daibo" else b for b in self.bases]
        self.assertTrue(pool_problems(crippled, self.set_class))                  # no Daibo left for a Monk


class Vendors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bases = sheet(D3 / "base_items.csv")
        cls.set_class = {r["set_name"]: r["class_key"] for r in sheet(D3 / "set_classes.csv")}
        cls.entries = sheet(D3 / "kadala_entries.csv")
        cls.vendors = sheet(D3 / "slot_vendors.csv")

    def test_kadala_and_the_slot_vendors_hand_a_monk_something_in_every_slot_it_wears(self):
        self.assertEqual(vendor_problems(self.bases, self.set_class, self.entries, self.vendors), [])
        by_slot = {e["slot"]: e for e in self.entries}
        self.assertIn("head", by_slot)                    # the Mystery Helm covers the Spirit Stone: no base_types filter
        self.assertEqual(by_slot["head"]["base_types"], "")
        self.assertEqual((by_slot["onehand"]["base_types"], by_slot["twohand"]["base_types"]), ("", ""))   # Fist Weapon, Daibo

    def test_the_vendor_check_catches_an_empty_slot(self):
        no_fists = [dict(b, pool_version="no") if b["slot"] == "onehand" else b for b in self.bases]
        self.assertTrue(vendor_problems(no_fists, self.set_class, self.entries, self.vendors))

    def test_the_blacksmith_crafts_the_spirit_stone_and_the_daibo(self):
        catalog = {r["recipe"]: r for r in sheet(D3 / "blacksmith_catalog.csv")}
        ids = {r["d3_id"]: r["item_entry"] for r in sheet(D3 / "base_item_ids.csv")}
        for recipe, base in (("T12_Armor_SpiritStone", "SpiritStone_206"), ("T12_Weapon_CombatStaff", "CombatStaff_2H_302")):
            self.assertEqual(catalog[recipe]["output_d3_id"], base)
            self.assertEqual(catalog[recipe]["output_entry"], ids[base])
            self.assertEqual(catalog[recipe]["enabled"], "1")
        # The sheet's recipes are D3's own: it lists no plain Mighty Weapon (1H) or Fist Weapon recipe either.
        self.assertNotIn("T12_Weapon_Fist", catalog)

    def test_the_mystic_has_the_monks_skill_choices_and_the_weapon_classes(self):
        rows = re.findall(r"\('(skill_\w+)',\d+,'[^']+',(\d+),", (UPDATES / "items_0029_skill_affix_classes.sql").read_text(encoding="utf-8"))
        monk_id = next(r["class_id"] for r in sheet(D3 / "class_map.csv") if r["d3_class"] == "Monk")
        per_class = Counter((group, cls) for group, cls in rows)
        for group in ("skill_head", "skill_torso", "skill_legs"):
            self.assertGreater(per_class[(group, monk_id)], 0, f"the Mystic has no Monk choice in {group}")
        weapon = (UPDATES / "items_0019_weapon_class.sql").read_text(encoding="utf-8")
        for kind in ("'Fist Weapon', 'damage1HNormal'", "'Daibo', 'damage2H'"):
            self.assertIn(kind, weapon)


class Ids(unittest.TestCase):
    def test_every_base_row_every_monk_legendary_and_every_monk_set_piece_has_its_id(self):
        bases, ids = sheet(D3 / "base_items.csv"), {r["d3_id"]: r["item_entry"] for r in sheet(D3 / "base_item_ids.csv")}
        self.assertEqual([b["d3_id"] for b in bases if b["d3_id"] not in ids], [])
        self.assertEqual(len(set(ids.values())), len(ids), "an item id is used twice")
        catalogue = [r for r in sheet(CATALOGUE) if r["class"] == "monk"]
        self.assertEqual(len(catalogue), 59)
        items = [r for r in catalogue if not r["pieces"]]
        self.assertEqual(len(items), 43)
        self.assertEqual([r["d3_id"] for r in items if r["d3_id"] not in ids], [])
        by_id = {b["d3_id"]: b for b in bases}
        self.assertEqual({by_id[r["d3_id"]]["designated_class"] for r in items}, {"monk"})
        # the other 16 rows are set bonuses (2, 4, 6 pieces); the pieces they need are base rows of the set
        set_class = {r["set_name"]: r["class_key"] for r in sheet(D3 / "set_classes.csv")}
        needed = {}
        for r in catalogue:
            if r["pieces"]:
                needed[r["item_or_set"]] = max(needed.get(r["item_or_set"], 0), int(r["pieces"]))
        self.assertEqual(len(needed), 6)
        for name, count in needed.items():
            self.assertEqual(set_class[name], "monk", name)
            pieces = [b for b in bases if b["set_name"] == name]
            self.assertGreaterEqual(len(pieces), count, f"{name} has {len(pieces)} base pieces for a {count}-piece bonus")

    def test_the_id_check_catches_a_missing_id(self):
        bases, ids = sheet(D3 / "base_items.csv"), {r["d3_id"]: r["item_entry"] for r in sheet(D3 / "base_item_ids.csv")}
        ids.pop("SpiritStone_206")
        self.assertEqual([b["d3_id"] for b in bases if b["d3_id"] not in ids], ["SpiritStone_206"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
