"""Legendary powers P0-P2 (diablocraft-w6ged, diablocraft-ews9q, diablocraft-r2jz4): the item power table, the set counter, the (skill, stat) modifiers and the conditions.

  * data/legendary_powers.csv is the table: its rows are the d3planner numbers of the two Wastes K0 items (Sun Keeper's
    required edmg 15-30, The Furnace's custom 40-50, read from reference/d3planner/item_*.js) and the Wastes 2-piece's
    two Rend numbers (500% damage per second, 15 seconds), read out of the set's own text in data/d3/barbarian_sets.csv;
    the generated SQL and the committed migration are what the generator renders from it;
  * the generator refuses a row it cannot stand behind (an owner that is not in the pool, a stat the slot's pool does
    not hold, a level that is not 2/3/4/6, a duplicate, no source);
  * the production rules (src/combat/dc_item_power_math.h: CountSets, BonusActive, ItemStats, RollRange, SkillFactor,
    SkillSetTo, BleedTick) are compiled
    and driven with the generated rows and the real Wastes set from base_items.csv: the count of 0..6 pieces, two
    copies of a piece as one, two sets apart, a bonus that switches at its level and only with a row, the roll range
    the table gives in place of the slot pool's (the pool's real range from affix_pools.csv), the Rend multiplier that
    switches on at 2 pieces, the sources that multiply, a duration that is set and never shortens, and a longer bleed
    that pays more ticks of the same size (its total grows with its length);
  * the per-item roll (diablocraft-ddnqh): an item-owned row of any kind but `stat` with a range rolls once, inside its range, a Primal at the
    top, a fixed row, a stat row and a set bonus roll nothing; the read (WornRolls) gives one number per worn item, the stored roll for a
    ranged row, the table's for a fixed one, none for an item rolled before it had a stored roll;
  * mutants of the rules fail the same driver;
  * source-text guards that Items::Apply refreshes the count, the roller reads the table and the scripts are
    registered (they prove the call is there, not that it runs; the C++ is compile-checked by syntax_check.sh and the
    in-game steps are in docs/test-diablocraft-w6ged.md).
"""
import csv
import math
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
HARNESS = MODULE / "tests/item_power_counter/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
SUN_KEEPER, FURNACE = "Unique_Mace_1H_011_x1", "Unique_Mace_2H_103_x1"
SQUIRT = "P66_Unique_Amulet_010"
REAL_MANTLE = "P4_Unique_Shoulder_103"
SQUIRT_POWER = "P66_ItemPassive_Unique_Ring_931"
WASTES = "Wrath of the Wastes"
# fixture owners for the per-item roll (the real table has no item-owned skill row yet)
MANTLE, SECOND, FIXED, FRACTION, BOTH = "Fixture_Mantle", "Fixture_Second", "Fixture_Fixed", "Fixture_Fraction", "Fixture_Both"


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


# The owners of the rows bead 5 (diablocraft-j86ni) added: the Wastes 6-piece, Mortick's Brace, Ambo's Pride, Lamentation. They are
# test_item_power_k4.py's, with the rules they use; this file's drivers see only the rows of beads 1 to 3.
K4_OWNERS = {(WASTES, 6), ("P2_Unique_Bracer_003", 0), ("P67_Unique_Mighty_1H_012", 0), ("P67_Unique_BarbBelt_005", 0)}
# Legendary build 2 bead 2's rows are test_item_power_math.py's (diablocraft-li0ie), Cindercoat's test_item_power_cindercoat.py's (diablocraft-5cqu3).
K0K2_OWNERS = {("P41_Unique_Gloves_014", 0), ("P61_Unique_Bracer_105", 0), ("P72_Unique_Mighty_1H_102", 0), ("P4_Unique_Chest_012", 0),
               ("Unique_Boots_008_x1", 0), ("Unique_Chest_006_x1", 0), ("P61_Unique_Mighty_2H_001", 0), ("P67_Unique_Shoulder_102", 0),
               ("P66_Unique_Gloves_007", 0), ("P4_Unique_Orb_001", 0), ("P4_Unique_Bracer_004", 0)}   # and Ashnagarr's Blood Bracer's test_item_power_ashnagarr.py's (46s0p), The Gavel of Judgment's test_item_power_gavel.py's (2z25c), Stone Gauntlets' test_item_power_stone_gauntlets.py's (ghb4o), Primordial Soul's test_item_power_primordial_soul.py's (tt86k)

# The legendary-rest beads' rows (one bead a legendary, ruling 2026-10-12) are each their own test file's: Might of the Earth 6-piece is Immortal King's Call 6-piece's test_item_power_immortal_kings_call.py's (diablocraft-14cp4), The Shame of Delsere's test_item_power_shame_of_delsere.py's (diablocraft-s5ydk), Immortal King's Call 2- and 4-piece's test_item_power_immortal_kings_call_set.py's (diablocraft-xf9oy), Tzo Krin's Gaze's test_item_power_tzo_krins_gaze.py's (diablocraft-08i4q), Gesture of Orpheus's test_item_power_gesture_of_orpheus.py's (diablocraft-1i52b), The Flow of Eternity's test_item_power_flow_of_eternity.py's (diablocraft-fyi93), Asheara's Vestments 2-piece's test_item_power_ashearas_vestments.py's (diablocraft-wn9q7).
# test_item_power_might_of_the_earth.py's (diablocraft-aa9tm), Oathkeeper's test_item_power_oathkeeper.py's (diablocraft-kaz5u), Starfire's test_item_power_starfire.py's (diablocraft-mcrtc), Tasker and Theo's test_item_power_tasker_and_theo.py's (diablocraft-1cv9k), The Three Hundredth Spear's test_item_power_three_hundredth_spear.py's (diablocraft-6dzud), Skull Grasp's test_item_power_skull_grasp.py's (diablocraft-zub4g), Depth Diggers' test_item_power_depth_diggers.py's (diablocraft-vijvi), Hunter's Wrath's test_item_power_hunters_wrath.py's (diablocraft-q3ezz), Dishonored Legacy's test_item_power_dishonored_legacy.py's (diablocraft-a2rln), Immortal King's Call 6-piece's test_item_power_immortal_kings_call.py's (diablocraft-14cp4), The Shame of Delsere's test_item_power_shame_of_delsere.py's (diablocraft-s5ydk), The Undisputed Champion's test_item_power_undisputed_champion.py's (diablocraft-szycu), Vengeful Wind's test_item_power_vengeful_wind.py's (diablocraft-8iwwg), the stat-only set levels test_item_power_stat_set_levels.py's (diablocraft-a13xy), Velvet Camaral's test_item_power_velvet_camaral.py's (diablocraft-9l8ka), Fazula's Improbable Chain's test_item_power_fazulas_improbable_chain.py's (diablocraft-0la7a), Serpent's Sparker's test_item_power_serpents_sparker.py's (diablocraft-1zocv), Myken's Ball of Hate's test_item_power_mykens_ball_of_hate.py's (diablocraft-3j0cg), Rabid Strike's test_item_power_rabid_strike.py's (diablocraft-6d1jb), Fjord Cutter's test_item_power_fjord_cutter.py's (diablocraft-5i88h), Standoff's test_item_power_standoff.py's (diablocraft-r2lly), Bracers of Destruction's test_item_power_bracers_of_destruction.py's (diablocraft-wme53), Blackthorne's Battlegear 4-piece's test_item_power_blackthornes_battlegear.py's (diablocraft-vix14), Skular's Salvation's test_item_power_skulars_salvation.py's (diablocraft-cnc98), Vile Ward's test_item_power_vile_ward.py's (diablocraft-s8lut), Blood Brother's test_item_power_blood_brother.py's (diablocraft-jxvsn), Scarbringer's test_item_power_scarbringer.py's (diablocraft-c9mth), Lion's Claw's test_item_power_lions_claw.py's (diablocraft-xureo), Monkey King's Garb's test_item_power_monkey_kings_garb.py's (diablocraft-w7wes), Countess Julia's Cameo's test_item_power_countess_julias_cameo.py's (diablocraft-sjdct), Hack's test_item_power_hack.py's (diablocraft-fhpm9), Harrington Waistguard's test_item_power_harrington_waistguard.py's (diablocraft-ikpbp), Maloth's Focus's test_item_power_maloths_focus.py's (diablocraft-kxdwe), The Butcher's Sickle's test_item_power_butchers_sickle.py's (diablocraft-v052u), Gloves of Worship's test_item_power_gloves_of_worship.py's (diablocraft-4y1jn), Aether Walker's test_item_power_aether_walker.py's (diablocraft-iv3xg), Ranslor's Folly's test_item_power_ranslors_folly.py's (diablocraft-5kkgd). The Tormentor's test_item_power_the_tormentor.py's (diablocraft-a3ycm), Vambraces of Sescheron's test_item_power_vambraces_of_sescheron.py's (diablocraft-uovwz), Wall of Man's test_item_power_wall_of_man.py's (diablocraft-44hz9), Fleshrake's test_item_power_fleshrake.py's (diablocraft-k2yzl).
REST_OWNERS = {('P610_Unique_Bracer_006', 0), ("Immortal King's Call", 6), ('Unique_Pants_006_p1', 0), ('P69_Unique_Belt_005', 0), ('P4_Unique_Belt_06', 0), ('P610_Unique_Staff_102', 0), ('Unique_Orb_102_x1', 0), ('P67_fistWeapon_norm_unique_02', 0), ('P68_Unique_Mighty_2H_004', 0), ('P61_Unique_Fist_009_x1', 0), ("Born's Command", 3), ('P61_Unique_Fist_013_x1', 0), ('Unique_Dagger_103_x1', 0), ('Unique_Orb_103_x1', 0), ('P73_Unique_Spear_001', 0), ("Aughild's Authority", 3), ('Unique_Axe_1H_103_x1', 0), ('P4_Unique_Belt_05', 0), ('Unique_SpiritStone_007_x1', 0), ("Sage's Journey", 3), ('Unique_Helm_103_x1', 0), ('Unique_Shoulder_001_x1', 0), ('Unique_Shoulder_003_p1', 0), ('Unique_Belt_105_x1', 0), ("Cain's Destiny", 2), ('P4_Unique_Belt_07', 0), ("Blackthorne's Battlegear", 3), ('Unique_Polearm_001_x1', 0), ("Asheara's Vestments", 2), ('P61_Unique_Ring_03', 0), ('Unique_WizardHat_101_x1', 0), ('Unique_SpiritStone_102_x1', 0), ('P61_Unique_Bracer_108_x1', 0), ('P61_Unique_CombatStaff_2H_003_x1', 0), ("Monkey King's Garb", 2), ("Captain Crimson's Trimmings", 2), ('Unique_Pants_101_x1', 0), ('P61_Unique_Belt_03', 0), ('P71_Unique_Bracer_108', 0), ('P61_Unique_Ring_02', 0), ('Unique_Staff_007_x1', 0), ('Unique_Chest_101_x1', 0), ('P71_Unique_Fist_003', 0), ("Monkey King's Garb", 4), ('Unique_Orb_004_x1', 0), ("Born's Command", 2), ('P74_Unique_WizardHat_104', 0), ('P68_Unique_Wand_102', 0), ("Aughild's Authority", 2), ('Unique_WizardHat_001_x1', 0), ('P2_Unique_Wand_002', 0), ('Unique_SpiritStone_103_x1', 0), ('Unique_Gloves_103_x1', 0), ("Monkey King's Garb", 6), ('Unique_Ring_103_x1', 0), ('Unique_Shield_011_x1', 0), ('P73_Unique_Spear_002', 0), ('P61_Unique_Boots_01', 0), ('P67_Unique_Bracer_100', 0), ("Sage's Journey", 2), ('P61_Unique_Staff_009', 0), ('P1_Wand_norm_unique_01', 0), ('P4_Unique_Bracer_106', 0), ('Might of the Earth', 2), ('Unique_Staff_006_x1', 0), ('P61_Unique_Orb_004', 0), ('P42_Unique_Wand_003_x1', 0), ("Blackthorne's Battlegear", 2), ('P68_Unique_BarbBelt_006', 0), ("Immortal King's Call", 2), ('P61_Unique_Sword_1H_112_x1', 0), ('P4_Unique_Belt_02', 0), ('Unique_Boots_009_x1', 0), ('Unique_Gloves_003_x1', 0), ('Unique_Ring_020_x1', 0), ("Demon's Hide", 3), ('P61_Unique_Polearm_01', 0), ('Unique_Axe_1H_006_x1', 0), ("Blackthorne's Battlegear", 4), ("Asheara's Vestments", 3), ('Unique_WizardHat_004_x1', 0), ('Unique_Bracer_102_x1', 0), ('P67_Unique_Mighty_1H_006', 0), ('P61_Unique_Mighty_2H_006', 0), ('Unique_Amulet_107_x1', 0), ('P4_Unique_Boots_001', 0), ('P4_Unique_Chest_018', 0), ('Unique_Sword_2H_103_x1', 0), ('P41_Unique_Fist_007', 0), ('Unique_Amulet_103_x1', 0), ('P4_Unique_Mighty_1H_104', 0), ('Unique_Polearm_101_x1', 0), ('P71_Unique_Boots_010', 0), ('P73_Unique_Bracer_101', 0), ('Unique_BarbBelt_002_x1', 0), ('Unique_CombatStaff_2H_102_x1', 0), ('P1_fistWeapon_norm_unique_01', 0), ('Unique_Boots_102_x1', 0), ('P4_Unique_Mighty_1H_005', 0), ('Unique_Ring_106_x1', 0), ('P4_Unique_Shoulder_101', 0), ('P74_Unique_Helm_006', 0), ('Krelm’s Buff Bulwark', 2), ('Might of the Earth', 4), ('P4_Unique_Bracer_105', 0), ('P41_Unique_CombatStaff_2H_005', 0), ('Unique_WizardHat_102_x1', 0), ('Unique_Mighty_1H_103_x1', 0), ("Immortal King's Call", 4), ('P67_Unique_Fist_006', 0), ('Unique_Belt_106_x1', 0), ('Hallowed Protectors', 2), ('Might of the Earth', 6)}



def generated_rows():
    """The rows beads 1 to 3 own, in their twelve columns: the rows an event fires (bead 4) are test_item_power_events.py's, bead 5's test_item_power_k4.py's, the potions' test_potion_powers.py's."""
    text = GENERATED.read_text(encoding="utf-8")
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]))
            for m in re.finditer(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),(\d+),'([^']*)','[^']*',[\d.]+,[\d.]+\)", text)
            if not m[13] and m[3] != "potion" and (m[1], int(m[2])) not in K4_OWNERS | K0K2_OWNERS | REST_OWNERS]


def planner_block(js, item_id):
    text = (REPO / "reference/d3planner" / js).read_text(encoding="utf-8")
    start = text.index('id: "%s"' % item_id)
    return text[start:text.index("},\n\n", start)]


def pool_range(slot, stat):
    row = next(r for r in read_csv("data/d3/affix_pools.csv")
               if r["slot"] == slot and r["affix_id"] == stat and r["item_level_bracket"] == "legendary")
    return float(row["value_min"]), float(row["value_max"])


def wastes_two_piece_text():
    """The Wastes 2-piece bonus as the set sheet words it, the same on all six pieces."""
    texts = {r["bonus_2pc"] for r in read_csv("data/d3/barbarian_sets.csv") if r["set_name"] == WASTES}
    assert len(texts) == 1, texts
    return texts.pop()


def squirt_numbers():
    """(damage per stack %, damage taken per stack %, max stacks, hit reset seconds) from Squirt's Power file when the client data is
    on this machine (decode_pow.py); the same four numbers as the file held on 2026-10-11 otherwise."""
    import decode_pow
    if not decode_pow.available():
        return 10.0, 5.0, 10, 2.0
    sf = decode_pow.parse_power(decode_pow.extract("Power/%s.pow" % SQUIRT_POWER))["sf"]
    labels = decode_pow.parse_power(decode_pow.extract("Power/%s.pow" % SQUIRT_POWER))["labels"]
    assert labels[:4] == ["Damage Amount", "Toughness Amount", "Max Stacks", "Hit Reset"], labels
    return float(sf[0]) * 100, float(sf[1]) * 100, int(float(sf[2])), float(sf[3])


def mantle_numbers():
    """(roll min %, roll max %, damage reduction %) from Mantle of Channeling's files when the client data is on this machine; the
    same numbers as the files held on 2026-10-11 otherwise."""
    import decode_pow
    if not decode_pow.available():
        return 20.0, 25.0, 25.0
    attrs = decode_pow.items()["P4_Unique_Shoulder_103"]
    power = decode_pow.parse_power(decode_pow.extract("Power/P4_ItemPassive_Unique_Ring_039.pow"))
    assert power["labels"][:1] == ["Damage Reduction"], power["labels"]
    low, high = decode_pow.evaluate(next(f for i, sno, f in attrs if i == decode_pow.ATTR_ITEM_POWER_PASSIVE))
    return round(low * 100, 6), round(high * 100, 6), round(float(power["sf"][0]) * 100, 6)


def wastes_four_piece_text():
    texts = {r["bonus_4pc"] for r in read_csv("data/d3/barbarian_sets.csv") if r["set_name"] == WASTES}
    assert len(texts) == 1, texts
    return texts.pop()


def wastes_pieces():
    return [r["d3_name"] for r in read_csv("data/d3/base_items.csv")
            if r["set_name"] == WASTES and r["pool_version"] == "yes"]


class Table(unittest.TestCase):
    def test_rows_are_d3planners_numbers(self):
        sun = re.search(r"required: \{\s*edmg: \{min: (\d+), max: (\d+)\}", planner_block("item_onehand.js", SUN_KEEPER))
        furnace = re.search(r'custom: \{id: "leg_thefurnace".*?min: (\d+), max: (\d+)\}', planner_block("item_twohand.js", FURNACE))
        self.assertTrue(sun and furnace)
        rend = re.search(r"damage per second of Rend by (\d+)% and its duration to (\d+) seconds", wastes_two_piece_text())
        self.assertTrue(rend)
        four = re.search(r"During (\w+) and for (\d+) seconds after, you gain (\d+)% damage reduction and your applied (\w+)s deal triple damage",
                         wastes_four_piece_text())
        self.assertTrue(four)
        window, reduction, tripled = "channel_or_after", -float(four[3]), (3 - 1) * 100.0  # triple is a multiplier of 1 + 200/100
        dealt, taken, most, reset = squirt_numbers()
        roll = mantle_numbers()
        mantle_skills = "Whirlwind;Arcane Torrent;Disintegrate;Ray of Frost"
        want = {(SUN_KEEPER, 0, "stat", "", "edmg", float(sun[1]), float(sun[2]), "", 0.0, "", 0.0, 0),
                (FURNACE, 0, "stat", "", "edmg", float(furnace[1]), float(furnace[2]), "", 0.0, "", 0.0, 0),
                (WASTES, 2, "skill", "Rend", "damage_increase_pct", float(rend[1]), float(rend[1]), "", 0.0, "", 0.0, 0),
                (WASTES, 2, "skill", "Rend", "dot_duration_seconds", float(rend[2]), float(rend[2]), "", 0.0, "", 0.0, 0),
                (WASTES, 4, "skill", four[4], "damage_increase_pct", tripled, tripled, window, float(four[2]), four[1], 0.0, 0),
                (WASTES, 4, "player", "", "damage_taken_pct", reduction, reduction, window, float(four[2]), four[1], 0.0, 0),
                # Squirt's Necklace: the Power file's per stack numbers, one stack a second (decisions.md 2026-10-10)
                (SQUIRT, 0, "player", "", "damage_dealt_pct", dealt, dealt, "quiet_stacks", reset, "", 1.0, most),
                (SQUIRT, 0, "player", "", "damage_taken_pct", taken, taken, "quiet_stacks", reset, "", 1.0, most),
                # Mantle of Channeling: the item's own rolled number and the Power file's fixed reduction, while a listed skill is held 1 s
                (REAL_MANTLE, 0, "player", "", "damage_dealt_pct", roll[0], roll[1], "channel_held", 1.0, mantle_skills, 0.0, 0),
                (REAL_MANTLE, 0, "player", "", "damage_taken_pct", -roll[2], -roll[2], "channel_held", 1.0, mantle_skills, 0.0, 0),
                # Lornelle's Sunstone: the item's own per-1%-of-Life-missing number (d3planner item_finger.js, leg_lornellessunstone)
                ("P6_Unique_Ring_04", 0, "player", "", "damage_reduction_pct", 0.75, 0.95, "life_missing", 0.0, "", 0.0, 0),
                # Irontoe Mudsputters (movement speed per 1% of Life missing), Justice Lantern (a share of the Block Chance), Krysbin's Sentence (against impaired enemies): the items' own numbers
                ("Unique_Boots_104_x1", 0, "player", "", "movement_speed_pct", 0.25, 0.3, "life_missing", 0.0, "", 0.0, 0),
                ("P4_Unique_Ring_03", 0, "player", "", "damage_reduction_of_block_pct", 45.0, 55.0, "", 0.0, "", 0.0, 0),
                ("P6_Unique_Ring_03", 0, "player", "", "damage_vs_impaired_pct", 75.0, 100.0, "", 0.0, "", 0.0, 0)}
        self.assertEqual(want, set(generated_rows()))
        self.assertEqual((500.0, 15.0), (float(rend[1]), float(rend[2])))
        self.assertEqual((-50.0, 3.0, 200.0), (reduction, float(four[2]), tripled))
        self.assertEqual(("Whirlwind", "Rend"), (four[1], four[4]))
        self.assertEqual((15.0, 30.0), (float(sun[1]), float(sun[2])))
        self.assertEqual((40.0, 50.0), (float(furnace[1]), float(furnace[2])))

    def test_the_items_pools_hold_the_stat(self):
        # the roller skips a preset its slot's pool does not hold, so the row would be dropped silently
        self.assertEqual((5.0, 8.0), pool_range("onehand", "edmg"))
        self.assertEqual((9.0, 10.0), pool_range("twohand", "edmg"))

    def test_generator_refuses_a_row_it_cannot_stand_behind(self):
        good = {"owner": SUN_KEEPER, "pieces": "", "kind": "stat", "skill": "", "stat": "edmg", "value_min": "15",
                "value_max": "30", "cond": "", "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
                "icd_seconds": "", "source": "x", "note": ""}
        skill = dict(good, owner=WASTES, pieces="2", kind="skill", skill="Rend", stat="damage_increase_pct", value_min="500",
                     value_max="500")
        window = dict(skill, cond="channel_or_after", cond_arg="3", cond_skills="Whirlwind")
        stacks = dict(good, owner=SUN_KEEPER, pieces="", kind="player", skill="", stat="damage_dealt_pct", value_min="10",
                      value_max="10", cond="quiet_stacks", cond_arg="2", stack_seconds="1", stack_max="10")
        player = dict(good, owner=WASTES, pieces="4", kind="player", skill="", stat="damage_taken_pct", value_min="-50",
                      value_max="-50")
        bad = {
            "owner not in the pool": dict(good, owner="Unique_Nothing_x1"),
            "set level 5": dict(good, owner=WASTES, pieces="5"),
            "set not a set": dict(good, owner="No Such Set", pieces="2"),
            "kind unknown": dict(good, kind="proc"),
            "stat not in the slot's pool": dict(good, stat="notastat"),
            "min above max": dict(good, value_min="31"),
            "no source": dict(good, source=""),
            "a skill named on a stat row": dict(good, skill="Rend"),
            "a skill row with no skill": dict(skill, skill=""),
            "a skill that does not exist": dict(skill, skill="Not A Skill"),
            "a skill stat nothing reads": dict(skill, stat="edmg"),
            "a duration on a skill with no bleed": dict(skill, skill="Frenzy", stat="dot_duration_seconds", value_min="15", value_max="15"),
            "a set bonus that rolls": dict(skill, value_max="600"),
            "a condition nothing reads": dict(window, cond="at_night"),
            "a condition on a rolled stat": dict(good, cond="channel_or_after", cond_arg="3", cond_skills="Whirlwind"),
            "a condition with no seconds": dict(window, cond_arg=""),
            "a condition with no skills": dict(window, cond_skills=""),
            "a condition on a skill that does not exist": dict(window, cond_skills="Whirlwind;Not A Skill"),
            "seconds with no condition": dict(skill, cond_arg="3"),
            "skills with no condition": dict(skill, cond_skills="Whirlwind"),
            "a player stat nothing reads": dict(player, stat="edmg"),
            "a player row that names a skill": dict(player, skill="Rend"),
            "stacks on a window": dict(window, stack_seconds="1", stack_max="10"),
            "stacks that never build": dict(stacks, stack_seconds=""),
            "no stack limit": dict(stacks, stack_max=""),
            "a fractional stack limit": dict(stacks, stack_max="2.5"),
            "stacks with skills": dict(stacks, cond_skills="Whirlwind"),
            "stacks with no reset seconds": dict(stacks, cond_arg=""),
            "stack numbers with no condition": dict(player, stack_seconds="1", stack_max="10"),
            "a player number of zero": dict(player, value_min="0", value_max="0"),
            "a player reduction of 100 or more": dict(player, value_min="-100", value_max="-100"),
            "a player number that rolls": dict(player, value_max="-40"),
            "a player number across zero": dict(player, value_min="-5", value_max="5"),
        }
        for name, row in bad.items():
            with self.subTest(name), self.assertRaises(ValueError):
                self.rows_of([row])
        with self.subTest("listed twice"), self.assertRaises(ValueError):
            self.rows_of([good, good])
        self.assertEqual([(SUN_KEEPER, 0, "stat", "", "edmg", 15.0, 30.0, "", 0.0, "", 0.0, 0)], self.rows_of([good]))
        # a set level's stat is one fixed number (N-SETSTAT, diablocraft-wn9q7: the sheet reads it, so it does not roll)
        self.assertEqual([(WASTES, 2, "stat", "", "edmg", 15.0, 15.0, "", 0.0, "", 0.0, 0)],
                         self.rows_of([dict(good, owner=WASTES, pieces="2", value_max="15")]))
        with self.subTest("a set level's stat that rolls"), self.assertRaises(ValueError):
            self.rows_of([dict(good, owner=WASTES, pieces="2")])
        self.assertEqual([(WASTES, 2, "skill", "Rend", "damage_increase_pct", 500.0, 500.0, "", 0.0, "", 0.0, 0)], self.rows_of([skill]))
        # an item-owned skill row may be a range (it rolls once per item); a set bonus may not
        item_skill = dict(skill, owner=SUN_KEEPER, pieces="", value_min="20", value_max="25")
        self.assertEqual([(SUN_KEEPER, 0, "skill", "Rend", "damage_increase_pct", 20.0, 25.0, "", 0.0, "", 0.0, 0)], self.rows_of([item_skill]))
        self.assertEqual([(SUN_KEEPER, 0, "skill", "Rend", "damage_increase_pct", 20.0, 20.0, "", 0.0, "", 0.0, 0)],
                         self.rows_of([dict(item_skill, value_max="20")]))
        # a Bottomless potion owns its power like an item and its range rolls once per potion (diablocraft-1z5ye); the potion
        # slot has no affix pool, so a potion never owns a stat row
        potion = dict(player, owner="HealthPotionLegendary_01", pieces="", stat="damage_dealt_pct", value_min="10", value_max="20")
        self.assertEqual([("HealthPotionLegendary_01", 0, "player", "", "damage_dealt_pct", 10.0, 20.0, "", 0.0, "", 0.0, 0)],
                         self.rows_of([potion]))
        with self.subTest("a potion-owned stat row"), self.assertRaises(ValueError):
            self.rows_of([dict(good, owner="HealthPotionLegendary_01")])
        for name, row in {"an item-owned skill row of an owner not in the pool": dict(item_skill, owner="Unique_Nothing_x1"),
                          "an item-owned skill row of a skill that is not one": dict(item_skill, skill="Not A Skill"),
                          "an item-owned skill row with a stat nothing reads": dict(item_skill, stat="edmg")}.items():
            with self.subTest(name), self.assertRaises(ValueError):
                self.rows_of([row])
        self.assertEqual([(WASTES, 2, "skill", "Rend", "dot_duration_seconds", 15.0, 15.0, "", 0.0, "", 0.0, 0)],
                         self.rows_of([dict(skill, stat="dot_duration_seconds", value_min="15", value_max="15")]))
        self.assertEqual([(WASTES, 2, "skill", "Rend", "damage_increase_pct", 500.0, 500.0, "channel_or_after", 3.0, "Whirlwind", 0.0, 0)],
                         self.rows_of([window]))
        self.assertEqual([(WASTES, 4, "player", "", "damage_taken_pct", -50.0, -50.0, "", 0.0, "", 0.0, 0)], self.rows_of([player]))
        # a positive player number is a damage increase (a later row); the same owner may carry one row per condition
        self.assertEqual(1, len(self.rows_of([dict(player, value_min="50", value_max="50")])))
        self.assertEqual(2, len(self.rows_of([skill, window])))
        # an item-owned fixed power is a row, with or without stacks
        self.assertEqual([(SUN_KEEPER, 0, "player", "", "damage_dealt_pct", 10.0, 10.0, "quiet_stacks", 2.0, "", 1.0, 10)], self.rows_of([stacks]))
        self.assertEqual(1, len(self.rows_of([dict(skill, owner=SUN_KEEPER, pieces="")])))

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
            return [row[:12] for row in generator.rows(module) if row[2] != "potion"]  # the potions' own rows (87qlt)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itempower-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self):
        """[(command line, expected output line)]: the expectations come from the sheets and the set's own list."""
        pieces = wastes_pieces()
        self.assertEqual(6, len(pieces))
        rows = [("row", *map(str, r)) for r in generated_rows()]
        # a fixture sheet for the set bonus rules, which the real table has no rows for yet: the Wastes 2- and 6-piece only
        fixture = [("row", WASTES, "6", "stat", "", "edmg", "1", "2"),
                   ("row", "Other Set", "4", "stat", "", "edmg", "1", "2"),
                   # a set row whose owner reads like an item's d3_id: never an item's preset
                   ("row", "Unique_Boots_Set_01_p2", "2", "stat", "", "str", "1", "2"),
                   # rows for the skill rules the real table has too few of: a second source on Rend, a longer duration, another skill
                   ("row", "Other Set", "2", "skill", "Rend", "damage_increase_pct", "100", "100"),
                   ("row", "Other Set", "4", "skill", "Rend", "dot_duration_seconds", "20", "20"),
                   ("row", "Third Set", "3", "skill", "Whirlwind", "damage_increase_pct", "25", "25")]
        # item-owned rows of other kinds than `stat` (the real table has none yet): a range, a second one on the same skill and stat,
        # a fixed one, a fractional range, and a stat row beside them
        item_rows = [("row", MANTLE, "0", "skill", "Rend", "damage_increase_pct", "20", "25"),
                     ("row", SECOND, "0", "skill", "Rend", "damage_increase_pct", "10", "12"),
                     ("row", FIXED, "0", "skill", "Rend", "dot_duration_seconds", "15", "15"),
                     ("row", FRACTION, "0", "skill", "Whirlwind", "damage_increase_pct", "1.5", "2.5"),
                     ("row", BOTH, "0", "stat", "", "edmg", "15", "30"),
                     ("row", BOTH, "0", "skill", "Rend", "damage_increase_pct", "30", "40"),
                     # a set row that is a range (the generator refuses one): still never an item's roll
                     ("row", "Ranged Set", "2", "skill", "Rend", "damage_increase_pct", "10", "20")]
        out = [("\t".join(r), None) for r in rows + fixture + item_rows]
        rend = re.search(r"damage per second of Rend by (\d+)% and its duration to (\d+) seconds", wastes_two_piece_text())
        wastes_factor, wastes_seconds = 1 + int(rend[1]) / 100, int(rend[2])
        for n in range(7):
            worn = pieces[:n]
            line = "\t".join(["count", str(n)] + [x for p in worn for x in (WASTES, p)])
            out.append((line, "%s=%d;" % (WASTES, n) if n else ""))
        two_copies = ["count", "3"] + [x for p in (pieces[0], pieces[0], pieces[1]) for x in (WASTES, p)]
        out.append(("\t".join(two_copies), "%s=2;" % WASTES))
        apart = ["count", "3", WASTES, pieces[0], "Other Set", pieces[1], WASTES, pieces[2]]
        out.append(("\t".join(apart), "Other Set=1;%s=2;" % WASTES))
        out.append(("\t".join(["count", "1", "", "Plain Ring"]), ""))
        for worn in range(0, 8):
            for level in (2, 3, 4, 6):
                on = worn >= level and level in (2, 4, 6)
                out.append(("active\t%s\t%d\t%d" % (WASTES, level, worn), "1" if on else "0"))
        out += self.skill_cases(wastes_factor, wastes_seconds)
        out += self.power_cases()
        out.append(("active\tOther Set\t4\t4", "1"))
        out.append(("active\tOther Set\t4\t3", "0"))
        out.append(("active\tOther Set\t3\t6", "0"))
        out.append(("active\tOther Set\t2\t6", "1"))
        low, high = pool_range("onehand", "edmg"), pool_range("twohand", "edmg")
        out += [("range\t%s\tedmg\t%g\t%g" % (SUN_KEEPER, *low), "15 30"),
                ("range\t%s\tedmg\t%g\t%g" % (FURNACE, *high), "40 50"),
                ("range\t%s\tstr\t%g\t%g" % (SUN_KEEPER, 100, 200), "100 200"),
                ("range\tUnique_Mace_1H_001_x1\tedmg\t5\t8", "5 8"),
                ("range\tUnique_Boots_Set_01_p2\tstr\t3\t4", "3 4"),
                ("stats\t%s" % SUN_KEEPER, "1"), ("stats\t%s" % FURNACE, "1"),
                ("stats\tUnique_Boots_Set_01_p2", "0"), ("stats\tnone", "0")]
        return out

    @staticmethod
    def power_cases():
        """The per-item roll and the read. Expectations are worked out from the range and the rules in the contract, not from the code."""
        key = "power:Rend:damage_increase_pct"
        cases = []
        for tenth in range(0, 11):  # a draw anywhere in the range lands inside it, on a whole number for a whole range
            unit = tenth / 10
            cases.append(("powers\t%s\t0\t%r" % (MANTLE, unit), "%s=%d[20-25];" % (key, math.floor(20 + unit * 5 + 0.5))))
        # a Primal stores the top of the range whatever the draw
        for unit in (0, 0.5, 1):
            cases.append(("powers\t%s\t1\t%r" % (MANTLE, unit), "%s=25[20-25];" % key))
        cases += [("powers\t%s\t0\t0.5" % FRACTION, "power:Whirlwind:damage_increase_pct=2[1.5-2.5];"),
                  ("powers\t%s\t1\t0" % FRACTION, "power:Whirlwind:damage_increase_pct=2.5[1.5-2.5];"),
                  # an item with a stat row and a skill row stores only the skill row: the stat row is an ordinary preset
                  ("powers\t%s\t0\t1" % BOTH, "%s=40[30-40];" % key),
                  # nothing to store: a fixed row, a stat row alone, a set bonus, an item the table does not know
                  ("powers\t%s\t0\t0.5" % FIXED, ""), ("powers\t%s\t1\t0.5" % FIXED, ""),
                  ("powers\t%s\t0\t0.5" % SUN_KEEPER, ""), ("powers\t%s\t1\t0.5" % SUN_KEEPER, ""),
                  ("powers\t%s\t0\t0.5" % WASTES, ""), ("powers\tRanged Set\t0\t0.5", ""), ("powers\tnone\t0\t0.5", "")]
        # an item that dropped before its power's row existed has no stored row: it gets the missing ones, a Primal at the top, and an
        # item that has its row gets nothing new (a roll is once)
        cases += [("powers\t%s\t0\t0.5\tpower:Rend:other" % MANTLE, "%s=23[20-25];" % key),
                  ("powers\t%s\t1\t0\tpower:Rend:other" % MANTLE, "%s=25[20-25];" % key),
                  ("powers\t%s\t0\t0.5\t%s" % (MANTLE, key), ""), ("powers\t%s\t1\t0.5\t%s" % (MANTLE, key), ""),
                  ("powers\t%s\t1\t0.5\t%s" % (BOTH, key), ""),
                  ("powers\t%s\t0\t0.5\tpower:Whirlwind:damage_increase_pct" % BOTH, "%s=35[30-40];" % key)]
        # the read: one number per worn item with the row, the stored roll for a range and the table's for a fixed row
        cases += [("worn\tRend\tdamage_increase_pct\t1\t%s\t1\t%s\t22" % (MANTLE, key), "22;"),
                  ("worn\tRend\tdamage_increase_pct\t1\t%s\t1\t%s\t25" % (MANTLE, key), "25;"),
                  # an item rolled before the roll was stored has no value, so no power
                  ("worn\tRend\tdamage_increase_pct\t1\t%s\t0" % MANTLE, ""),
                  ("worn\tRend\tdamage_increase_pct\t1\t%s\t1\tpower:Rend:other\t22" % MANTLE, ""),
                  ("worn\tRend\tdot_duration_seconds\t1\t%s\t0" % FIXED, "15;"),
                  ("worn\tRend\tdamage_increase_pct\t2\t%s\t1\t%s\t22\t%s\t1\t%s\t11" % (MANTLE, key, SECOND, key), "22;11;"),
                  # two worn copies of one item give two numbers, each its own
                  ("worn\tRend\tdamage_increase_pct\t2\t%s\t1\t%s\t21\t%s\t1\t%s\t24" % (MANTLE, key, MANTLE, key), "21;24;"),
                  ("worn\tRend\tdamage_increase_pct\t2\t%s\t1\t%s\t22\t%s\t0" % (MANTLE, key, SECOND), "22;"),
                  # another skill, another stat, a stat-kind row and an item the table does not know read nothing
                  ("worn\tWhirlwind\tdamage_increase_pct\t1\t%s\t1\t%s\t22" % (MANTLE, key), ""),
                  ("worn\tRend\tdot_duration_seconds\t1\t%s\t1\t%s\t22" % (MANTLE, key), ""),
                  ("worn\t\tedmg\t1\t%s\t1\tedmg\t20" % SUN_KEEPER, ""),
                  ("worn\tRend\tdamage_increase_pct\t1\tnone\t0", ""),
                  ("worn\tRend\tdamage_increase_pct\t0", "")]
        return cases

    @staticmethod
    def skill_cases(wastes_factor, wastes_seconds):
        """The skill rules, with the expectations worked out from the set's own text and the rules of the game, not from the code."""
        def counts(**worn):
            return ["%d" % len(worn)] + [x for set_name, n in worn.items() for x in (set_name.replace("_", " "), str(n))]
        cases = []
        for worn in range(0, 7):  # the 500% is on at the 2-piece and stays on above it
            cases.append(("\t".join(["factor", "Rend", "damage_increase_pct", *counts(**{"Wrath_of_the_Wastes": worn})]),
                          "%g" % (wastes_factor if worn >= 2 else 1)))
            cases.append(("\t".join(["setto", "Rend", "dot_duration_seconds", "5", *counts(**{"Wrath_of_the_Wastes": worn})]),
                          "%g" % (wastes_seconds if worn >= 2 else 5)))
        # two sources on one skill each multiply (the second is 1 + 100/100); a skill or stat apart gets nothing
        cases += [("\t".join(["factor", "Rend", "damage_increase_pct", *counts(**{"Wrath_of_the_Wastes": 2, "Other_Set": 2})]),
                   "%g" % (wastes_factor * 2)),
                  ("\t".join(["factor", "Rend", "damage_increase_pct", *counts(**{"Wrath_of_the_Wastes": 6, "Other_Set": 1})]),
                   "%g" % wastes_factor),
                  ("\t".join(["factor", "Whirlwind", "damage_increase_pct", *counts(**{"Wrath_of_the_Wastes": 6})]), "1"),
                  ("\t".join(["factor", "Whirlwind", "damage_increase_pct", *counts(**{"Third_Set": 3, "Wrath_of_the_Wastes": 6})]), "1.25"),
                  ("\t".join(["factor", "Rend", "damage_increase_pct", "0"]), "1"),
                  # a duration that is set takes the highest source and never shortens the skill's own
                  ("\t".join(["setto", "Rend", "dot_duration_seconds", "5", *counts(**{"Wrath_of_the_Wastes": 2, "Other_Set": 4})]), "20"),
                  ("\t".join(["setto", "Rend", "dot_duration_seconds", "30", *counts(**{"Wrath_of_the_Wastes": 2})]), "30")]
        # a bleed of total T over 5 ticks, lasting N ticks, pays N/5 times T in all, in ticks of T/5 (rounded within one)
        for total, base, ticks in ((1000, 5, 5), (1003, 5, 15), (7, 5, 15), (123456.5, 5, 15), (1003, 5, 3)):
            sum_, lowest, highest = math.floor(total * ticks / base), math.floor(total / base), math.ceil(total / base)
            cases.append(("bleed\t%r\t%d\t%d" % (total, base, ticks), "%g %g %g" % (sum_, lowest, highest)))
        return cases

    def drive(self, header_text, name):
        cases = self.cases()
        work, binary = self.build(header_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            got = run.stdout.split("\n")[:-1]
            want = [w for _, w in cases if w is not None]
            return got, want
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_every_rule_agrees_with_the_sheets(self):
        got, want = self.drive(MATH.read_text(encoding="utf-8"), "real")
        self.assertGreater(len(want), 50)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        mutants = {
            "duplicates_count": real.replace("names[piece.set].insert(piece.name);",
                                             "names[piece.set].insert(piece.name + std::to_string(names[piece.set].size()));"),
            "level_needs_one_more": real.replace("if (worn < pieces || !pieces)", "if (worn <= pieces || !pieces)"),
            "level_needs_none_less": real.replace("if (worn < pieces || !pieces)", "if (worn + 1 < pieces || !pieces)"),
            "bonus_needs_no_row_for_its_level": real.replace("row.owner == set && row.pieces == pieces", "row.owner == set"),
            "bonus_needs_no_row": real.replace("        for (Row const& row : rows)\n            if (row.owner == set && row.pieces == pieces)\n                return true;\n        return false;",
                                               "        return true;"),
            "set_row_is_an_item_preset": real.replace("row.owner == d3Id && !row.pieces && row.kind", "row.owner == d3Id && row.kind"),
            "range_ignores_the_stat": real.replace("if (row.stat == stat)", "if (true)"),
            "range_keeps_the_pool_max": real.replace("                max = row.max;\n", ""),
            "range_keeps_the_pool_min": real.replace("                min = row.min;\n", ""),
            "unset_piece_counts": real.replace("if (!piece.set.empty())", "if (true)"),
            "sources_add_not_multiply": real.replace("factor *= 1.0 + pct / 100.0;", "factor += pct / 100.0;"),
            "source_needs_one_more_piece": real.replace("worn->second < row.pieces", "worn->second <= row.pieces"),
            "any_skill": real.replace("NamesSkill(row.skill, skill) && ", ""),
            "any_stat": real.replace(" && row.stat == stat && Owned", " && Owned"),
            "duration_may_shorten": real.replace("if (value > base)", "if (true)"),
            "bleed_ticks_of_the_new_length": real.replace("total * tick / baseTicks", "total * tick / (baseTicks + 1)"),
            "power_primal_rolls": real.replace("atTop ? Best(row) : roll(row.min, row.max)", "roll(row.min, row.max)"),
            "power_primal_stores_min": real.replace("atTop ? Best(row) : roll(row.min, row.max)", "atTop ? row.min : roll(row.min, row.max)"),
            "power_fixed_row_stored": real.replace("return !row.pieces && row.kind != \"stat\" && row.min < row.max;",
                                                   "return !row.pieces && row.kind != \"stat\" && row.min <= row.max;"),
            "power_stat_row_stored": real.replace("return !row.pieces && row.kind != \"stat\" && row.min < row.max;",
                                                  "return !row.pieces && row.min < row.max;"),
            "power_set_row_stored": real.replace("return !row.pieces && row.kind != \"stat\" && row.min < row.max;",
                                                 "return row.kind != \"stat\" && row.min < row.max;"),
            "power_rolled_again": real.replace("std::none_of(have.begin(), have.end(), [&](Stored const& s) { return s.key == RollKey(row); })", "true"),
            "power_held_by_any_key": real.replace("return s.key == RollKey(row); })", "return !s.key.empty(); })"),
            "power_of_another_item": real.replace("if (row.owner == d3Id && Rolls(row) &&", "if (Rolls(row) &&"),
            "power_key_ignores_skill": real.replace('"power:" + FirstSkill(row.skill) + ":" + row.stat', '"power::" + row.stat'),
            "read_ignores_the_skill": real.replace("NamesSkill(value.skill, skill) && ", ""),
            "read_ignores_the_stat": real.replace(" && value.stat == stat", ""),
            "read_fixed_row_dropped": real.replace("                out.push_back({row.skill, row.stat, row.min, d3Id, true});\n                continue;\n", "                continue;\n"),
            "read_unrolled_item_reads_min": real.replace("            if (found != stored.end())\n                out.push_back({row.skill, row.stat, found->value, d3Id});",
                                                         "            out.push_back({row.skill, row.stat, found == stored.end() ? row.min : found->value, d3Id});"),
            "read_takes_any_stored_key": real.replace("return s.key == RollKey(row);", "return true;"),
            "read_stat_rows": real.replace("if (row.owner != d3Id || row.pieces || row.kind == \"stat\")", "if (row.owner != d3Id || row.pieces)"),
            "bleed_total_not_grown": real.replace("std::floor(total * (tick - 1) / baseTicks)", "std::floor(total * (tick - 1) / baseTicks) - 1"),
        }
        for name, mutant in mutants.items():
            self.assertTrue(real != mutant, "the %s mutation no longer applies" % name)
            got, want = self.drive(mutant, name)
            self.assertNotEqual(want, got, "mutant %s passed" % name)


class Conditions(unittest.TestCase):
    """P2 (diablocraft-r2jz4): the Wastes 4-piece reads "while Whirlwind channels and for 3 seconds after". The expectations are worked
    out from the set's own text (50% damage reduction, triple), not from the code; the situation is set by hand."""

    def cases(self):
        four = re.search(r"During (\w+) and for (\d+) seconds after, you gain (\d+)% damage reduction", wastes_four_piece_text())
        skill, after, reduction = four[1], int(four[2]) * 1000, int(four[3]) / 100.0
        rend2 = 1 + 5.0  # the 2-piece, always on from 2 pieces
        pieces = wastes_pieces()
        self.assertEqual(6, len(pieces))
        out = [("\t".join(("row", *map(str, r))), None) for r in generated_rows()]

        def at(now, spans, worn, sets=None):
            """Lines that set the situation, then ask Rend's damage factor and the player's damage-taken factor."""
            lines = ["clear", "now\t%d" % now] + ["span\t%s\t%d\t%d\t%d" % span for span in spans]
            counts = "1\t%s\t%d" % (WASTES, worn)
            return lines, "factor\tRend\tdamage_increase_pct\t" + counts, "player\tdamage_taken_pct\t" + counts

        def ask(now, spans, worn, rend, taken):
            lines, factor, player = at(now, spans, worn)
            out.extend((line, None) for line in lines)
            out.append((factor, "%g" % rend))
            out.append((player, "%g" % taken))

        t = 100000
        on = (1 - reduction)
        # channelling now: both on from the 4th piece, neither below it
        for worn in range(0, 7):
            four_on = worn >= 4
            ask(t, [(skill, t - 5000, 0, 1)], worn, (rend2 if worn >= 2 else 1) * (3 if four_on else 1), on if four_on else 1)
        # not channelling: ended within the window holds, after it does not, never channelled does not
        ask(t, [(skill, t - 9000, t - 1, 0)], 6, rend2 * 3, on)
        ask(t, [(skill, t - 9000, t - after + 1, 0)], 6, rend2 * 3, on)
        ask(t, [(skill, t - 9000, t - after - 1, 0)], 6, rend2, 1)
        ask(t, [(skill, t - 9000, t - after - 60000, 0)], 6, rend2, 1)
        ask(t, [], 6, rend2, 1)
        # another skill channelling does not count; the clock may have wrapped since the channel ended
        ask(t, [("Frenzy", t - 5000, 0, 1)], 6, rend2, 1)
        ask(100, [(skill, 4294960000, 4294967000, 0)], 6, rend2 * 3, on)   # 396 ms after, across the wrap
        ask(100000, [(skill, 4294960000, 4294967000, 0)], 6, rend2, 1)
        # the set's other bonuses are not touched by the window: a longer Rend bleed has no condition
        out.append(("\t".join(["setto", "Rend", "dot_duration_seconds", "5", "1", WASTES, "6"]), "15"))
        out += self.squirt_cases()
        out += self.mantle_cases()
        return out

    def mantle_cases(self):
        """Mantle of Channeling: +[20-25]% damage dealt (the item's own stored roll) and 25% less damage taken while one of its skills has been
        channelled for a second. The expectations come from the item text and the Power file's 0.25."""
        out = []
        t = 500000
        listed = ("Whirlwind", "Arcane Torrent", "Disintegrate", "Ray of Frost")

        def ask(spans, roll, dealt, taken, worn=True, now=None):
            lines = ["clear", "now\t%d" % (t if now is None else now)]
            if worn:
                lines.append("wears\t%s\t%d" % (REAL_MANTLE, t - 100000))
            if roll is not None:
                lines.append("value\t%s\t\tdamage_dealt_pct\t%g" % (REAL_MANTLE, roll))
                lines.append("value\t%s\t\tdamage_taken_pct\t-25" % REAL_MANTLE)
            lines += ["span\t%s\t%d\t%d\t%d" % span for span in spans]
            out.extend((line, None) for line in lines)
            out.append(("player\tdamage_dealt_pct\t0", "%g" % dealt))
            out.append(("player\tdamage_taken_pct\t0", "%g" % taken))

        for skill in listed:                                        # every listed skill, held for a second or more
            ask([(skill, t - 1000, 0, 1)], 23, 1.23, 0.75)
            ask([(skill, t - 60000, 0, 1)], 20, 1.2, 0.75)
            ask([(skill, t - 60000, 0, 1)], 25, 1.25, 0.75)         # the roll is the item's: the top of the range
        ask([("Whirlwind", t - 999, 0, 1)], 23, 1, 1)                 # not yet a second
        ask([("Whirlwind", t - 5000, t - 1, 0)], 23, 1, 1)           # stopped: no "for 3 seconds after" here
        ask([("Frenzy", t - 5000, 0, 1)], 23, 1, 1)                  # not one of its skills
        ask([], 23, 1, 1)                                            # channelling nothing
        ask([("Whirlwind", t - 5000, 0, 1)], 23, 1, 1, worn=False)   # not worn
        ask([("Whirlwind", t - 5000, 0, 1)], 22.5, 1.225, 0.75)      # a whole range value is not assumed
        ask([("Whirlwind", t - 5000, 0, 1)], None, 1, 0.75)          # no stored roll: no value, no power for the ranged row (the server backfills one on first read)
        ask([("Disintegrate", 4294960000, 0, 1)], 23, 1.23, 0.75, now=2000)   # the clock wrapped while it channelled
        ask([("Ray of Frost", 4294966000, 0, 1)], 23, 1.23, 0.75, now=100)    # wrapped, held 1.396 s: on
        return out

    def squirt_cases(self):
        """Squirt's Necklace, from the Power file's numbers and the designer's ruling (decisions.md 2026-10-10): a stack a second, +10% damage dealt
        and +5% damage taken each, at most 10; a hit removes every stack and none build for 2 s."""
        dealt, taken, most, reset = squirt_numbers()
        out = []

        def ask(label, now, worn, hurt, stacks):
            lines = ["clear", "now\t%d" % now]
            if worn is not None:
                lines.append("wears\t%s\t%d" % (SQUIRT, worn))
            if hurt is not None:
                lines.append("hurt\t%d" % hurt)
            out.extend((line, None) for line in lines)
            out.append(("player\tdamage_dealt_pct\t0", "%g" % (1 + dealt * stacks / 100)))
            out.append(("player\tdamage_taken_pct\t0", "%g" % (1 + taken * stacks / 100)))

        t = 1000000
        for seconds in (0, 0.5, 1, 1.5, 2, 5, 9.9, 10, 10.1, 11, 60):   # worn and never hit: a stack a second, the tenth is the last
            ask("quiet", t + int(seconds * 1000), t, None, min(int(seconds), most))
        ask("not worn", t, None, None, 0)
        ask("a hit now", t + 7000, t, t + 7000, 0)
        ask("2 s after a hit", t + 9000, t, t + 7000, 0)             # the pause is over, no stack yet
        ask("2.5 s after a hit", t + 9500, t, t + 7000, 0)
        ask("3 s after a hit", t + 10000, t, t + 7000, 1)            # the first stack, a second after the pause
        ask("8 s after a hit", t + 15000, t, t + 7000, 6)
        ask("12 s after a hit", t + 19000, t, t + 7000, 10)          # capped
        ask("worn 1 s after a hit", t + 4000, t + 1000, t, 2)        # hit at t, worn at t+1 s: the pause ends t+2 s, now t+4 s: 2 s of building
        ask("worn long after a hit", t + 53000, t + 50000, t, 3)     # the old hit does not give a later equip a head start
        ask("clock wrapped", 5000, 4294960000, 4294965000, 5)
        # an item's fixed power with no condition (no real row yet): on while the item is worn and only then
        out.append(("row\tFixture_Item\t0\tplayer\t\tdamage_taken_pct\t-10\t-10", None))
        out += [("clear", None), ("now\t5", None), ("player\tdamage_taken_pct\t0", "1"),
                ("wears\tFixture_Item\t1", None), ("player\tdamage_taken_pct\t0", "0.9"),
                ("wears\tSomeone_Else\t1", None), ("clear", None), ("wears\tSomeone_Else\t1", None), ("player\tdamage_taken_pct\t0", "1")]       # now 5000 after the wrap, hit 7296 ms ago, pause over 5296 ms ago
        return out

    def run_with(self, header_text, name):
        cases = self.cases()
        work, binary = Rules.build(header_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_window_switches_the_4_piece_on_and_off(self):
        want, got = self.run_with(MATH.read_text(encoding="utf-8"), "cond-real")
        self.assertGreater(len(want), 20)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        mutants = {
            "condition_ignored": real.replace("if (row.cond.empty())\n            return true;", "return true;"),
            "unknown_condition_holds": real.replace("        return false;\n    }\n\n    // A worn set piece", "        return true;\n    }\n\n    // A worn set piece"),
            "running_does_not_count": real.replace("span->second.running || (", "(", 1),
            "window_open_ended": real.replace("(situation.now - span->second.end) <= static_cast<std::uint32_t>(row.arg * 1000.0)", "true"),
            "window_in_the_wrong_unit": real.replace("row.arg * 1000.0", "row.arg"),
            "any_skill": real.replace("situation.channels.find(skill)", "situation.channels.begin()"),
            "stacks_not_capped": real.replace("return built < row.stackMax ? built : row.stackMax;", "return built;"),
            "a_hit_does_not_pause": real.replace("if (static_cast<std::int32_t>(resume - start) > 0)", "if (false)"),
            "pause_ignored_for_a_late_equip": real.replace("if (static_cast<std::int32_t>(resume - start) > 0)", "if (true)"),
            "stack_a_tenth_second": real.replace("elapsed / (row.stackSeconds * 1000.0)", "elapsed / (row.stackSeconds * 100.0)"),
            "stacks_before_the_pause_ends": real.replace("situation.lastHurt + static_cast<std::uint32_t>(row.arg * 1000.0)", "situation.lastHurt"),
            "item_row_without_the_item": real.replace("else if (!situation.wornSince.count(row.owner))\n            return false;", ""),
            "held_for_no_time": real.replace("(situation.now - span->second.start) >= static_cast<std::uint32_t>(row.arg * 1000.0)", "true"),
            "held_needs_more": real.replace("(situation.now - span->second.start) >= static_cast", "(situation.now - span->second.start) > static_cast"),
            "held_when_stopped": real.replace("span != situation.channels.end() && span->second.running &&\n                    (situation.now - span->second.start)", "span != situation.channels.end() &&\n                    (situation.now - span->second.start)"),
            "ranged_row_reads_the_table": real.replace("number = found->value;", "number = row.min;"),
            "ranged_row_without_a_roll_reads_the_table": real.replace("if (item == situation.itemValues.end())\n                return false;", "if (item == situation.itemValues.end())\n                return true;"),
            "stacks_not_per_stack": real.replace("number * Counted(row, situation)", "number"),
            "player_ignores_condition": real.replace("Owned(row, counts, situation, number) &&\n                Holds(row, situation))", "Owned(row, counts, situation, number))"),
            "damage_reduction_adds": real.replace("for (double pct : ActiveValues(rows, counts, \"player\", \"\", stat, situation))\n            factor *= 1.0 + pct / 100.0;",
                                                   "for (double pct : ActiveValues(rows, counts, \"player\", \"\", stat, situation))\n            factor *= 1.0 - pct / 100.0;"),
        }
        for name, mutant in mutants.items():
            self.assertTrue(real != mutant, "the %s mutation no longer applies" % name)
            want, got = self.run_with(mutant, name)
            self.assertNotEqual(want, got, "mutant %s passed" % name)


if __name__ == "__main__":
    unittest.main()
