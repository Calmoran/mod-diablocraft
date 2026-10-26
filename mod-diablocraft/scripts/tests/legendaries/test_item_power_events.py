"""Legendary powers P3, events and procs (diablocraft-g0n7f): the rows an event fires and the rules that fire them.

  * data/legendary_powers.csv gains the event columns (`fire_on`, `fire_skills`, `chance_pct`, `icd_seconds`) and eight rows that use them:
    Band of Might, Echoing Fury, In-geom, Messerschmidt's Reaver, Obsidian Ring of the Zodiac, the Bastions of Will 2-piece (two rows) and
    The Burning Axe of Sankis. Every number is read from its source and compared: the Power files through decode_pow.py when the client data
    is on this machine (the numbers of 2026-10-11 otherwise), the committed legendary-pow-data.csv for Sankis, the planner's set text for
    Bastions of Will and the catalogue for Band of Might's skills;
  * the generator refuses a row it cannot stand behind (an unknown event, an effect or a `triggered` condition with no event, a cast with no
    skill, a chance outside 0-100, a negative internal cooldown, a reduction of 100 or more ...);
  * the production rules (src/combat/dc_item_power_math.h: Fire, the `triggered` condition, ReductionFactor, PlayerSum, HitKinds) are compiled
    and driven with the generated rows: the window of each buff to the millisecond, the internal cooldown, the chance with and without the
    proc coefficient, a failed roll that costs nothing, the skills of a cast, the owner (worn, stored roll, set count), two rows of one
    owner that fire apart;
  * mutants of those rules fail the same driver;
  * source-text guards that each event has its call site, each effect its executor and each stat its reader (they prove the call is there,
    not that it runs; the C++ is compile-checked by syntax_check.sh and the in-game steps are in docs/test-diablocraft-g0n7f.md).
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
import barbarian_source  # noqa: E402
import harness_env
import generate_legendary_powers as generator

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_events/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
MIGRATION = MODULE / "data/sql/db-world/updates" / GENERATED.name

BAND, ECHO, INGEOM = "P61_Unique_Ring_05", "P66_Unique_Mace_1H_001", "Unique_Sword_1H_113_x1"
REAVER, ZODIAC, SANKIS = "P66_Unique_Axe_2H_011", "Unique_Ring_023_p2", "Unique_Axe_1H_007_x1"
BASTIONS = "Bastions of Will"
ROW_WIDTH = 16


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def generated_rows():
    """Every row of the generated SQL, sixteen columns, in table order."""
    text = GENERATED.read_text(encoding="utf-8")
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16]))
            for m in re.finditer(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)", text)]


def event_rows():
    """The rows bead 4 owns; the `hit` event and its `apply_skill` effect are bead 5's (test_item_power_k4.py), The Gavel of Judgment's
    test_item_power_gavel.py's (diablocraft-2z25c), Stone Gauntlets' test_item_power_stone_gauntlets.py's (diablocraft-ghb4o), The Shame of Delsere's test_item_power_shame_of_delsere.py's (diablocraft-s5ydk), Girdle of Giants' test_item_power_girdle_of_giants.py's (diablocraft-5mn2l; a skill row with an event), Dark Mage's Shade's test_item_power_dark_mages_shade.py's (diablocraft-ohipa; the life_below event), Might of the Earth's
    test_item_power_might_of_the_earth_set.py's (diablocraft-tydva; the land event), Crystal Fist's test_item_power_crystal_fist.py's
    (diablocraft-9c2kv; a cast event), Bul-Kathos's Wedding Band's
    test_item_power_bul_kathos_wedding_band.py's (diablocraft-942kn; the tick event), Vigilance's
    test_item_power_vigilance.py's (diablocraft-115jg; a cast on taken), Ancestors' Grace's
    test_item_power_ancestors_grace.py's (diablocraft-omfd8; the fatal event), Fire Walkers'
    test_item_power_fire_walkers.py's (diablocraft-4na3e; the tick that drops the fire), Blood Brother's
    test_item_power_blood_brother.py's (diablocraft-jxvsn; the block event), Harrington Waistguard's
    test_item_power_harrington_waistguard.py's (diablocraft-ikpbp; the chest event), Krede's Flame's
    test_item_power_kredes_flame.py's (diablocraft-z1q6q; the taken_element event), Fleshrake's
    test_item_power_fleshrake.py's (diablocraft-k2yzl; a cast event)."""
    return [r for r in generated_rows() if r[12] and r[12] != "hit"
            and r[0] not in ("P4_Unique_Bracer_106", "Unique_Shield_011_x1", "Unique_Axe_1H_006_x1", "Unique_Staff_006_x1", "Unique_Ring_003_x1", "Unique_Belt_105_x1", "P61_Unique_Mighty_2H_001", "P66_Unique_Gloves_007", "P4_Unique_Belt_02", "P61_Unique_BarbBelt_EQ", "Unique_WizardHat_101_x1", "Unique_WizardHat_001_x1", "P61_Unique_Ring_03", "P61_Unique_Bracer_109", "Might of the Earth", "P610_Unique_Bracer_006", "Unique_SpiritStone_101_x1", "P41_Unique_Fist_008", "Unique_Ring_020_x1", "Unique_Polearm_001_x1", "P4_Unique_Shoulder_101", "P67_Unique_Fist_006", "Unique_Staff_101_x1", "Unique_Amulet_102_x1", "Unique_Boots_007_p2", "Unique_Sword_2H_103_x1", "P41_Unique_Fist_007")]


def pow_numbers(power, item, fallback):
    """({SF label: value}, (item number low, high)) from the Power file and the item's attribute when the client data is on this machine; the same
    numbers as the files held on 2026-10-11 otherwise (`fallback`)."""
    import decode_pow
    if not decode_pow.available():
        return fallback
    labelled = {}
    if power:
        parsed = decode_pow.parse_power(decode_pow.extract("Power/%s.pow" % power))
        labelled = {label: float(parsed["sf"][n]) for n, label in enumerate(parsed["labels"]) if n in parsed["sf"]}
    attrs = decode_pow.items()[item]
    low, high = decode_pow.evaluate(next(f for i, sno, f in attrs if i == decode_pow.ATTR_ITEM_POWER_PASSIVE))
    return labelled, (round(low, 6), round(high, 6))


def catalogue_skills(name):
    row = next(r for r in read_csv("../docs/research/legendary-catalogue.csv") if r["item_or_set"] == name)
    return row["skills"]


def bastions_text():
    """The two 2-piece sentences of Bastions of Will as the planner words them: [(percent, seconds)] in order."""
    text = (REPO / "reference/d3planner/data_itemsets.js").read_text(encoding="utf-8")
    start = text.index("bastionsofwill: {")
    block = text[start:text.index("\n  },\n", start)]
    return re.findall(r"deal (\d+)%% increased damage for (\d+) seconds", block), re.findall(r'format: "([^"]+)"', block)


def sankis_numbers():
    """(chance %, duration, reduction %, internal cooldown) from the committed decode of the Power file (docs/research/legendary-pow-data.csv)."""
    row = next(r for r in read_csv("../docs/research/legendary-pow-data.csv") if r["item_or_set"] == "The Burning Axe of Sankis")
    sf = dict(re.findall(r"SF_(\d+) [^=]+= ([\d.]+)", row["script_formulas"]))
    return float(row["item_number"]) * 100, float(sf["0"]), float(sf["1"]) * 100, float(sf["3"])


def sheet_skills():
    """[(skill, primary, cost, generated)] of every class's skill sheet, the numbers as the sheets state them."""
    out = []
    for path in sorted((MODULE / "data/d3").glob("*_skills.csv")):
        for r in read_csv("data/d3/" + path.name):
            cost = r.get("fury_cost") if "fury_cost" in r else r.get("resource_cost")
            generated = r.get("fury_generation") if "fury_generation" in r else r.get("resource_generation")
            out.append((r["skill_name"], r["category"] == "Primary", float(cost or 0), float(generated or 0)))
    return out


class Table(unittest.TestCase):
    def test_rows_are_their_sources_numbers(self):
        band_sf, band_item = pow_numbers("P4_ItemPassive_Unique_Ring_049", BAND, ({"Duration": 8.0}, (0.6, 0.8)))
        echo_sf, _ = pow_numbers("P66_ItemPassive_Unique_Ring_927", ECHO, ({"Max Stack": 5.0, "Buff Duration": 4.0, "Attack Speed Bonus": 0.15}, (1.0, 1.0)))
        ingeom_sf, ingeom_item = pow_numbers("ItemPassive_Unique_Ring_919_x1", INGEOM, ({"Duration": 15.0}, (8.0, 10.0)))
        _, reaver_item = pow_numbers(None, REAVER, ({}, (1.0, 1.0)))
        _, zodiac_item = pow_numbers(None, ZODIAC, ({}, (1.0, 1.0)))
        chance, sankis_seconds, sankis_reduction, sankis_icd = sankis_numbers()
        bastions, sentences = bastions_text()
        self.assertEqual(2, len(bastions), sentences)
        self.assertIn("resource-generating attack or primary skill", sentences[0])
        self.assertIn("resource-spending attack", sentences[1])
        # Echoing Fury's buff is Frenzy's own: the file's stacks, seconds and attack speed are the skill sheet's numbers
        frenzy = {r["token"]: float(r["value"]) for r in read_csv("data/d3/barbarian_skill_values.csv") if r["skill"] == "Frenzy" and not r["rune"] and r["token"] in
                  ("max_stacks_count", "duration_seconds", "attack_speed_pct")}
        self.assertEqual((echo_sf["Max Stack"], echo_sf["Buff Duration"], echo_sf["Attack Speed Bonus"] * 100),
                         (frenzy["max_stacks_count"], frenzy["duration_seconds"], frenzy["attack_speed_pct"]))
        # the catalogue's words agree with the numbers
        text = {r["item_or_set"]: r["power_text"] for r in read_csv("../docs/research/legendary-catalogue.csv") if r["pieces"] in ("", "2")}
        self.assertIn("[%g-%g]%% reduced damage for %g seconds" % (band_item[0] * 100, band_item[1] * 100, band_sf["Duration"]), text["Band of Might"])
        self.assertIn("reduced by [%g-%g] seconds for %g seconds" % (ingeom_item[0], ingeom_item[1], ingeom_sf["Duration"]), text["In-geom"])
        want = {
            (BAND, 0, "player", "", "damage_reduction_pct", band_item[0] * 100, band_item[1] * 100, "triggered", band_sf["Duration"], "", 0.0, 0,
             "cast", catalogue_skills("Band of Might"), 100.0, 0.0),
            (ECHO, 0, "effect", "", "frenzy_stacks", echo_sf["Max Stack"], echo_sf["Max Stack"], "", 0.0, "", 0.0, 0, "kill", "", 100.0, 0.0),
            (INGEOM, 0, "player", "", "cooldown_reduction_seconds", ingeom_item[0], ingeom_item[1], "triggered", ingeom_sf["Duration"], "", 0.0, 0,
             "kill_elite", "", 100.0, 0.0),
            (REAVER, 0, "effect", "", "cooldown_cut_seconds", reaver_item[0], reaver_item[1], "", 0.0, "", 0.0, 0, "kill", "", 100.0, 0.0),
            (ZODIAC, 0, "effect", "", "cooldown_cut_seconds", zodiac_item[0], zodiac_item[1], "", 0.0, "", 0.0, 0, "hit_spender", "", 100.0, 0.0),
            (BASTIONS, 2, "player", "", "damage_dealt_pct", float(bastions[0][0]), float(bastions[0][0]), "triggered", float(bastions[0][1]), "", 0.0, 0,
             "hit_generator", "", 100.0, 0.0),
            (BASTIONS, 2, "player", "", "damage_dealt_pct", float(bastions[1][0]), float(bastions[1][0]), "triggered", float(bastions[1][1]), "", 0.0, 0,
             "hit_spender", "", 100.0, 0.0),
            (SANKIS, 0, "player", "", "damage_reduction_pct", sankis_reduction, sankis_reduction, "triggered", sankis_seconds, "", 0.0, 0, "taken", "",
             chance, sankis_icd),
        }
        self.assertEqual(want, set(event_rows()))
        self.assertEqual(8, len(event_rows()))
        self.assertEqual("Furious Charge;Ground Stomp;Leap", catalogue_skills("Band of Might"))

    def test_every_event_row_has_its_owner_in_the_pool_and_a_source(self):
        sheet = {r["owner"] + "|" + r["pieces"] + "|" + r["stat"] + "|" + r["fire_on"]: r for r in read_csv("data/legendary_powers.csv")}
        for owner, pieces, _, _, stat, *_rest, fire_on, _skills, _chance, _icd in event_rows():
            row = sheet["%s|%s|%s|%s" % (owner, pieces or "", stat, fire_on)]
            self.assertTrue(row["source"].strip() and row["note"].strip(), owner)

    def test_generator_refuses_a_row_it_cannot_stand_behind(self):
        good = {"owner": BAND, "pieces": "", "kind": "player", "skill": "", "stat": "damage_reduction_pct", "value_min": "60", "value_max": "80",
                "cond": "triggered", "cond_arg": "8", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "cast",
                "fire_skills": "Leap", "chance_pct": "", "icd_seconds": "", "source": "x", "note": ""}
        effect = dict(good, owner=REAVER, kind="effect", stat="cooldown_cut_seconds", value_min="1", value_max="1", cond="", cond_arg="",
                      fire_on="kill", fire_skills="")
        bad = {
            "an event nothing fires": dict(good, fire_on="at_night"),
            "an effect with no event": dict(effect, fire_on=""),
            "a triggered condition with no event": dict(good, fire_on="", fire_skills=""),
            "an event on a rolled stat row": dict(good, kind="stat", stat="edmg", cond="", cond_arg="", fire_on="kill", fire_skills=""),
            "an event that starts nothing": dict(good, cond="", cond_arg=""),
            "a cast with no skill": dict(good, fire_skills=""),
            "a cast of a skill that does not exist": dict(good, fire_skills="Leap;Not A Skill"),
            "skills on a kill": dict(effect, fire_skills="Leap"),
            "a chance of zero": dict(effect, chance_pct="0"),
            "a chance above 100": dict(effect, chance_pct="101"),
            "a negative internal cooldown": dict(effect, icd_seconds="-1"),
            "a chance with no event": dict(good, kind="player", fire_on="", fire_skills="", cond="", cond_arg="", chance_pct="8"),
            "an internal cooldown with no event": dict(good, fire_on="", fire_skills="", cond="", cond_arg="", icd_seconds="4"),
            "an effect stat nothing does": dict(effect, stat="edmg"),
            "an effect that names a skill": dict(effect, skill="Rend"),
            "an effect with a condition": dict(effect, cond="triggered", cond_arg="3"),
            "a triggered condition with skills": dict(good, cond_skills="Leap"),
            "a triggered condition with no seconds": dict(good, cond_arg=""),
            "a reduction of 100": dict(good, value_min="100", value_max="100"),
            "a negative reduction": dict(good, value_min="-5", value_max="-5"),
            "a negative cooldown reduction": dict(good, stat="cooldown_reduction_seconds", value_min="-1", value_max="-1"),
            "a set bonus that rolls an effect": dict(effect, owner=BASTIONS, pieces="2", value_max="2"),
        }
        for name, row in bad.items():
            with self.subTest(name), self.assertRaises(ValueError):
                self.rows_of([row])
        with self.subTest("listed twice"), self.assertRaises(ValueError):
            self.rows_of([good, good])
        self.assertEqual([(BAND, 0, "player", "", "damage_reduction_pct", 60.0, 80.0, "triggered", 8.0, "", 0.0, 0, "cast", "Leap", 100.0, 0.0)],
                         self.rows_of([good]))
        self.assertEqual([(REAVER, 0, "effect", "", "cooldown_cut_seconds", 1.0, 1.0, "", 0.0, "", 0.0, 0, "kill", "", 8.0, 4.0)],
                         self.rows_of([dict(effect, chance_pct="8", icd_seconds="4")]))
        # the same owner and stat may carry one row per event (Bastions of Will's two buffs)
        self.assertEqual(2, len(self.rows_of([dict(good, fire_on="hit_spender", fire_skills=""), dict(good, fire_on="hit_generator", fire_skills="")])))

    @staticmethod
    def rows_of(sheet_rows):
        with tempfile.TemporaryDirectory(dir=str(SCRATCH)) as folder:
            module = Path(folder)
            (module / "data/d3").mkdir(parents=True)
            for name in ("base_items.csv", "affix_pools.csv", "legendary_potions.csv", *sorted(p.name for p in (MODULE / "data/d3").glob("*_skills.csv")),
                         *sorted(p.name for p in (MODULE / "data/d3").glob("*_skill_values.csv"))):
                shutil.copy(MODULE / "data/d3" / name, module / "data/d3" / name)
            with (module / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(sheet_rows[0]))
                writer.writeheader()
                writer.writerows(sheet_rows)
            return [row for row in generator.rows(module) if row[2] != "potion"]  # the potions' own rows (87qlt)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemevents-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    @staticmethod
    def sets(**worn):
        return ["%d" % len(worn)] + [x for name, n in worn.items() for x in (name.replace("_", " "), str(n))]

    def cases(self):
        """[(command line, expected output line or None)]: the expectations are worked out from the rules in the contract and the sources' numbers."""
        T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
        out = [(T("row", *r), None) for r in generated_rows()]
        assert all(len(c[0].split("\t")) == ROW_WIDTH + 1 for c in out), "row width"
        none = self.sets()
        fire = lambda event, skill, scale, draw, *sets: (T("fire", event, skill, scale, draw, *(sets or none)))  # noqa: E731
        reduction = lambda *sets: T("reduction", *(sets or none))  # noqa: E731
        taken = lambda p: "%g" % (1 - p / 100)  # noqa: E731

        # Band of Might: a cast of one of its three skills starts 8 s of reduction at the item's stored roll
        out += [(T("clear"), None), (T("now", 1000), None), (T("wears", BAND, 0), None), (T("value", BAND, "", "damage_reduction_pct", 70), None),
                (reduction(), "1"),
                (fire("cast", "Leap", 1, 0), ""), (reduction(), taken(70)),
                (T("now", 9000), None), (reduction(), taken(70)),          # 8000 ms later: still on
                (T("now", 9001), None), (reduction(), "1"),                # and 1 ms more: over
                (T("now", 20000), None), (fire("cast", "Whirlwind", 1, 0), ""), (reduction(), "1"),   # not one of its skills
                (fire("kill_elite", "Leap", 1, 0), ""), (reduction(), "1"),                            # not its event
                (fire("cast", "Furious Charge", 1, 0), ""), (reduction(), taken(70)),
                (T("now", 28000), None), (fire("cast", "Ground Stomp", 1, 0), ""),                      # a recast renews the 8 s
                (T("now", 35999), None), (reduction(), taken(70)), (T("now", 36001), None), (reduction(), "1")]
        out += [(T("clear"), None), (T("now", 1000), None), (T("wears", BAND, 0), None), (T("value", BAND, "", "damage_reduction_pct", 80), None),
                (fire("cast", "Leap", 1, 0), ""), (reduction(), taken(80))]                             # a Primal's top
        out += [(T("clear"), None), (T("now", 1000), None), (fire("cast", "Leap", 1, 0), ""), (reduction(), "1")]   # not worn
        out += [(T("clear"), None), (T("now", 1000), None), (T("wears", BAND, 0), None),                       # worn with no stored roll: no power
                (fire("cast", "Leap", 1, 0), ""), (reduction(), "1")]

        # Echoing Fury, Messerschmidt's Reaver, the Obsidian Ring: effects, certain, on their own events only
        out += [(T("clear"), None), (T("now", 10), None), (T("wears", ECHO, 0), None),
                (fire("kill", "", 1, 99), "frenzy_stacks=5;"), (fire("kill", "", 0, 99), "frenzy_stacks=5;"),   # a certain effect needs no coefficient
                (fire("kill_elite", "", 1, 0), ""), (fire("hit_spender", "Whirlwind", 1, 0), ""), (fire("cast", "Leap", 1, 0), "")]
        out += [(T("clear"), None), (T("now", 10), None), (fire("kill", "", 1, 0), "")]                        # not worn: nothing
        out += [(T("clear"), None), (T("now", 10), None), (T("wears", REAVER, 0), None),
                (fire("kill", "", 1, 99), "cooldown_cut_seconds=1;"), (fire("hit_spender", "Whirlwind", 1, 0), "")]
        out += [(T("clear"), None), (T("now", 10), None), (T("wears", ZODIAC, 0), None),
                (fire("hit_spender", "Whirlwind", 0.13, 99), "cooldown_cut_seconds=1;"),
                (fire("hit_spender", "Whirlwind", 0, 99), "cooldown_cut_seconds=1;"),       # a hit that states no coefficient still counts: no chance is rolled
                (fire("hit_generator", "Frenzy", 1, 0), ""), (fire("kill", "", 1, 0), "")]
        out += [(T("clear"), None), (T("now", 10), None), (T("wears", ECHO, 0), None), (T("wears", REAVER, 0), None),       # two items, one kill, both fire in table order
                (fire("kill", "", 1, 0), "frenzy_stacks=5;cooldown_cut_seconds=1;")]

        # In-geom: an elite kill starts 15 s of N seconds off the cooldowns; a plain kill does not
        out += [(T("clear"), None), (T("now", 2000), None), (T("wears", INGEOM, 0), None), (T("value", INGEOM, "", "cooldown_reduction_seconds", 9), None),
                (T("sum", "cooldown_reduction_seconds", *none), "0"),
                (fire("kill", "", 1, 0), ""), (T("sum", "cooldown_reduction_seconds", *none), "0"),
                (fire("kill_elite", "", 1, 0), ""), (T("sum", "cooldown_reduction_seconds", *none), "9"),
                (T("now", 17000), None), (T("sum", "cooldown_reduction_seconds", *none), "9"),
                (T("now", 17001), None), (T("sum", "cooldown_reduction_seconds", *none), "0")]

        # Bastions of Will: two separate buffs of a set bonus, on at 2 pieces, each 1 + 50/100 for 5 s
        two = self.sets(Bastions_of_Will=2)
        dealt = lambda *sets: T("player", "damage_dealt_pct", *(sets or none))  # noqa: E731
        out += [(T("clear"), None), (T("now", 100), None),
                (fire("hit_generator", "Frenzy", 1, 0, *two), ""), (dealt(*two), "1.5"),
                (T("now", 5100), None), (dealt(*two), "1.5"), (T("now", 5101), None), (dealt(*two), "1"),
                (T("now", 6000), None), (fire("hit_spender", "Whirlwind", 1, 0, *two), ""), (dealt(*two), "1.5"),    # the other buff, alone
                (T("now", 6100), None), (fire("hit_generator", "Frenzy", 1, 0, *two), ""), (dealt(*two), "2.25"),    # both: two multipliers
                (T("now", 11000), None), (dealt(*two), "2.25"),                                                      # the spender's 5 s end here, inclusive
                (T("now", 11001), None), (dealt(*two), "1.5"),                                                       # the generator buff, renewed at 6100, runs on
                (T("now", 11101), None), (dealt(*two), "1")]
        out += [(T("clear"), None), (T("now", 100), None), (fire("hit_generator", "Frenzy", 1, 0, *self.sets(Bastions_of_Will=1)), ""),
                (dealt(*self.sets(Bastions_of_Will=1)), "1"), (dealt(*two), "1")]                                    # one piece: nothing fires, nothing is on
        out += [(T("clear"), None), (T("now", 100), None), (fire("hit_generator", "Frenzy", 1, 0, *self.sets(Bastions_of_Will=6)), ""),
                (dealt(*self.sets(Bastions_of_Will=6)), "1.5"), (dealt(*self.sets(Bastions_of_Will=1)), "1")]      # a buff that fired is not on without the bonus

        # The Burning Axe of Sankis: 8% a hit taken (a monster's hit has coefficient 1), 35% less damage for 4 s, no new chance for 4 s
        out += [(T("clear"), None), (T("now", 1000), None), (T("wears", SANKIS, 0), None),
                (fire("taken", "", 1, 8.0), ""), (reduction(), "1"),                       # the roll fell at 8.0: not under 8
                (fire("taken", "", 1, 7.99), ""), (reduction(), taken(35))]
        out += [(T("clear"), None), (T("now", 1000), None), (T("wears", SANKIS, 0), None),
                (fire("taken", "", 0.5, 4.0), ""), (reduction(), "1"),                      # the chance is scaled by the coefficient: 8% x 0.5 = 4%
                (fire("taken", "", 0.5, 3.99), ""), (reduction(), taken(35))]
        out += [(T("clear"), None), (T("now", 1000), None), (T("wears", SANKIS, 0), None),
                (fire("taken", "", 0, 0), ""), (reduction(), "1")]                          # a coefficient of 0 never procs
        out += [(T("clear"), None), (T("now", 1000), None), (T("wears", SANKIS, 0), None),  # a roll that fails costs nothing: no buff, no cooldown
                (fire("taken", "", 1, 50), ""), (reduction(), "1"), (T("now", 1001), None), (fire("taken", "", 1, 0), ""), (reduction(), taken(35))]
        out += [(T("clear"), None), (T("now", 1000), None), (T("wears", SANKIS, 0), None),
                (fire("taken", "", 1, 0), ""), (T("now", 4999), None), (reduction(), taken(35)),
                (fire("taken", "", 1, 0), ""),                                              # 3999 ms after the last: the internal cooldown holds it back
                (T("now", 5000), None), (reduction(), taken(35)),                           # the buff's 4 s are inclusive
                (T("now", 5001), None), (reduction(), "1"),                                 # and the blocked fire did not renew it
                (fire("taken", "", 1, 0), ""), (reduction(), taken(35)),                    # 4001 ms after: free again
                (T("now", 9001), None), (reduction(), taken(35)), (T("now", 9002), None), (reduction(), "1")]
        out += [(T("clear"), None), (T("now", 1000), None), (T("wears", SANKIS, 0), None), (fire("taken", "", 1, 0), ""),
                (T("now", 5000), None), (fire("taken", "", 1, 0), ""), (T("now", 9000), None), (reduction(), taken(35))]   # exactly 4000 ms: free
        out += [(T("clear"), None), (T("now", 1000), None), (fire("taken", "", 1, 0), ""), (reduction(), "1")]                 # not worn
        # Sankis's buff (diablocraft-pl8fc): shown when its window opens, for its row's seconds; never for a failed roll or a fire the internal
        # cooldown held back, nor for a row of another event
        opened = lambda event: T("opened", event)  # noqa: E731
        window = "%s/damage_reduction_pct/%d;" % (SANKIS, sankis_numbers()[1])
        out += [(T("clear"), None), (T("now", 1000), None), (T("wears", SANKIS, 0), None),
                (fire("taken", "", 1, 50), ""), (opened("taken"), ""),
                (fire("taken", "", 1, 0), ""), (opened("taken"), window), (opened("cast"), ""),
                (T("now", 1001), None), (opened("taken"), ""),                              # a moment later the window is open, not opening
                (T("now", 4999), None), (fire("taken", "", 1, 0), ""), (opened("taken"), ""),   # held back by the internal cooldown
                (T("now", 5000), None), (fire("taken", "", 1, 0), ""), (opened("taken"), window)]
        out += [(T("clear"), None), (T("now", 100), None), (T("wears", BAND, 0), None), (T("value", BAND, "", "damage_reduction_pct", 70), None),
                (fire("cast", "Leap", 1, 0), ""), (opened("cast"), "%s/damage_reduction_pct/8;" % BAND)]   # Band of Might opens one too: it has no buff record (yet)
        out += [(T("clear"), None), (T("now", 100), None), (T("wears", ECHO, 0), None), (T("wears", ZODIAC, 0), None),
                (fire("kill", "", 1, 0), "frenzy_stacks=5;"), (opened("kill"), ""),                   # an effect that fired is no window
                (fire("hit_spender", "Whirlwind", 1, 0), "cooldown_cut_seconds=1;"), (opened("hit_spender"), "")]

        # a worn clock that wraps: the window and the cooldown are differences
        out += [(T("clear"), None), (T("now", 4294966000), None), (T("wears", BAND, 0), None), (T("value", BAND, "", "damage_reduction_pct", 70), None),
                (fire("cast", "Leap", 1, 0), ""), (T("now", 6000), None), (reduction(), taken(70)), (T("now", 7000), None), (reduction(), "1")]

        # what a hit is to the hit events, from every skill of every sheet
        out += [(T("hitkind", 1 if primary else 0, "%g" % cost, "%g" % generated), "%d %d" % (1 if primary or generated > 0 else 0, 1 if cost > 0 else 0))
                for _, primary, cost, generated in sheet_skills()]
        sheet = {name: (primary, cost, generated) for name, primary, cost, generated in sheet_skills()}
        self.assertEqual((False, 10.0, 0.0), sheet["Whirlwind"])
        self.assertEqual((True, 0.0, 4.0), sheet["Frenzy"])
        self.assertEqual((False, 0.0, 15.0), sheet["Leap"])
        self.assertEqual((False, 0.0, 0.0), sheet["Ignore Pain"])
        out += [(T("hitkind", 0, 10, 0), "0 1"), (T("hitkind", 1, 0, 4), "1 0"), (T("hitkind", 0, 0, 15), "1 0"), (T("hitkind", 0, 0, 0), "0 0"),
                (T("hitkind", 1, 0, 0), "1 0")]
        return out

    def drive(self, header_text, name):
        cases = self.cases()
        work, binary = self.build(header_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_every_rule_agrees_with_the_sources(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), "real")
        self.assertGreater(len(want), 80)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        window = "return last != situation.fired.end() && (situation.now - last->second) <= static_cast<std::uint32_t>(row.arg * 1000.0);"
        chance = "if (row.chancePct < 100 && !(row.chancePct * scale > 0 && roll(row.chancePct * scale)))\n                continue;"
        mutants = {
            "icd_ignored": real.replace("(situation.now - last->second) < static_cast<std::uint32_t>(icd * 1000.0)", "false"),
            "icd_a_millisecond_short": real.replace("(situation.now - last->second) < static_cast<std::uint32_t>(icd * 1000.0)",
                                                    "(situation.now - last->second) <= static_cast<std::uint32_t>(icd * 1000.0)"),
            "chance_ignored": real.replace("row.chancePct < 100 &&", "false &&"),
            "chance_not_scaled": real.replace("roll(row.chancePct * scale)", "roll(row.chancePct)"),
            "a_failed_roll_starts_the_cooldown": real.replace(
                chance, "bool const fell = !(row.chancePct < 100) || (row.chancePct * scale > 0 && roll(row.chancePct * scale));\n"
                        "            situation.fired[key] = situation.now;\n            if (!fell)\n                continue;"),
            "skill_filter_dropped": real.replace("!row.fireSkills.empty() && std::find", "false && std::find"),
            "event_ignored": real.replace("row.fireOn != fireOn || !Owned", "!Owned"),
            "owner_ignored": real.replace("row.fireOn != fireOn || !Owned(row, counts, situation, number)", "row.fireOn != fireOn"),
            "fire_not_recorded": real.replace("situation.fired[key] = situation.now;", ""),
            "effect_not_returned": real.replace('if (row.kind == "effect")\n                out.push_back', "if (false)\n                out.push_back"),
            "window_open_ended": real.replace(window, "return last != situation.fired.end();"),
            "window_exclusive": real.replace(window, window.replace("<=", "<")),
            "window_in_the_wrong_unit": real.replace(window, window.replace("row.arg * 1000.0", "row.arg")),
            "two_rows_share_a_clock": real.replace("+ '|' + row.fireOn;", ";"),
            "reduction_adds": real.replace("factor *= 1.0 - pct / 100.0;", "factor *= 1.0 + pct / 100.0;"),
            "stored_roll_ignored": real.replace("number = found->value;", "number = row.min;"),
            "primary_is_not_a_generator": real.replace("primary || generated > 0", "generated > 0"),
            "a_free_skill_is_a_spender": real.replace("cost > 0}", "cost >= 0}"),
            "opened_any_time": real.replace("at != situation.fired.end() && at->second == situation.now", "at != situation.fired.end()"),
            "opened_any_event": real.replace('if (row.fireOn == fireOn && row.cond == "triggered")', 'if (row.cond == "triggered")'),
            "opened_any_row": real.replace('if (row.fireOn == fireOn && row.cond == "triggered")', "if (row.fireOn == fireOn)"),
        }
        for name, mutant in mutants.items():
            self.assertTrue(real != mutant, "the %s mutation no longer applies" % name)
            want, got = self.drive(mutant, name)
            self.assertNotEqual(want, got, "mutant %s passed" % name)


if __name__ == "__main__":
    unittest.main()
