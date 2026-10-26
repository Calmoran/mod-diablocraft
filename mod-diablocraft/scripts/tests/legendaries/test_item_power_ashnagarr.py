"""Ashnagarr's Blood Bracer (diablocraft-46s0p, legendary-rest bead 006): "Increases the potency of your shields by [75-100]%."

  * data/legendary_powers.csv gains one row: a `player` shield_potency_pct 75-100, rolled once per item (a Primal takes 100); the range
    is read from d3planner's item file and data.json, set against the sheet's words, the catalogue and the tooltip text the players see;
    the generator refuses the stat anywhere it cannot be read (zero, negative);
  * the production rule (dc_item_power_math.h PlayerFactor, Owned, Best, RollPowers) is compiled and driven with the generated row: no
    item worn is x1, the item at 75 / 100 is x1.75 / x2.00, a Primal rolls at the top, an item with no stored roll gives nothing;
  * source-text guards that every place a player's own shield sets its absorb amount (Molten Wildebeest's PutShield, the Wizard's Shield
    helper for its five shield records, the Wizard's Diamond Skin aura amount, Force Armor's cap on what it cuts, diablocraft-y3ldu) multiplies by the one reader ItemPowers::ShieldFactor and
    that no other file sets one around it (they prove the call is there, not that it runs; the C++ is compile-checked by syntax_check.sh
    and the in-game steps are in docs/test-diablocraft-46s0p.md);
  * mutants of each rule fail the same drivers.
"""
import re
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
import wizard_source  # noqa: E402
import harness_env  # noqa: E402
import test_item_power_events as events  # noqa: E402  (modules, so their test classes are not run twice)
import test_item_power_math as power_math  # noqa: E402
from test_item_power_math import GENERATED, MIGRATION, generator, planner, planner_json, read_csv, tooltip, all_rows  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
ASH = "P4_Unique_Bracer_004"
STAT = "shield_potency_pct"
GEM_CPP = SRC / "combat/dc_gem_powers.cpp"
WIZARD_CPP = wizard_source.CPP
POWERS_CPP = item_powers_source.CPP
SHAMAN_CPP = SRC / "classes/shaman/dc_shaman_elemental_shield.cpp"
POWERS_H = SRC / "combat/dc_item_powers.h"
FORMAT = "Increases the potency of your shields by %d%%."


def source():
    """(min, max) from the planner's item file, the same pair from data.json, the sheet words and the catalogue's."""
    text = planner("item_wrists.js", ASH)
    found = re.search(r'format: "Increases the potency of your shields by %d%%.", min: (\d+), max: (\d+)\}', text)
    assert found, text
    json_custom = planner_json(ASH)["required"]["custom"]
    assert json_custom["format"] == FORMAT, json_custom
    assert (float(json_custom["min"]), float(json_custom["max"])) == (float(found[1]), float(found[2])), json_custom
    catalogue = next(r for r in read_csv("../docs/research/legendary-catalogue.csv") if r["d3_id"] == ASH)
    assert "Increases the potency of your shields by [%s-%s]%%." % (found[1], found[2]) == catalogue["power_text"], catalogue["power_text"]
    return float(found[1]), float(found[2])


def row_problems(rows, n):
    """What is wrong with the item's generated rows against the source's range: the sentences a mutant must trigger."""
    blank = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
    want = {(ASH, 0, "player", "", STAT, n[0], n[1], *blank)}
    return [] if set(rows) == want and len(rows) == 1 else ["rows %r are not %r" % (sorted(rows), sorted(want))]


class Table(unittest.TestCase):
    def test_the_row_is_the_sources_range(self):
        n = source()
        self.assertEqual((75, 100), n)
        self.assertEqual([], row_problems([r for r in all_rows() if r[0] == ASH], n))
        self.assertIn("%g–%g%%" % n, tooltip(ASH))     # the text the Lua tooltip puts the stored roll into (rolledPower)
        self.assertEqual("Increases the potency of your shields by %g–%g%%." % n, tooltip(ASH))
        pool = next(r for r in read_csv("data/d3/base_items.csv") if r["d3_id"] == ASH)
        self.assertEqual(("Ashnagarr's Blood Bracer", "wrists", "yes", ""), (pool["d3_name"], pool["slot"], pool["pool_version"], pool["designated_class"]))
        # the row mutants: a range off the source, another stat or kind
        for name, row in {"min off": (ASH, 0, "player", "", STAT, 70.0, 100.0, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0),
                          "max off": (ASH, 0, "player", "", STAT, 75.0, 110.0, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0),
                          "another stat": (ASH, 0, "player", "", "damage_dealt_pct", 75.0, 100.0, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0),
                          "another kind": (ASH, 0, "skill", "", STAT, 75.0, 100.0, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0),
                          "fixed at the top": (ASH, 0, "player", "", STAT, 100.0, 100.0, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)}.items():
            self.assertTrue(row_problems([row], n), name)
        self.assertTrue(row_problems([], n))

    def test_the_tooltip_lists_the_item_as_built(self):
        # dc_tooltip.lua marks a power built when dc_legendary_power has a pieces-0 row of the item (test_item_power_tooltip.py drives the Lua)
        self.assertTrue([r for r in all_rows() if r[0] == ASH and r[1] == 0])
        lua = (MODULE / "lua/aio/dc_tooltip.lua").read_text(encoding="utf-8")
        self.assertIn("JOIN dc_legendary_power p ON p.owner=b.d3_id AND p.pieces=0", lua)

    def test_the_sql_row_and_the_stat_are_in_the_generators_vocabulary(self):
        self.assertIn("('%s',0,'player','','%s',75,100,'',0,'',0,0,'','',100,0)" % (ASH, STAT), MIGRATION.read_text(encoding="utf-8"))
        self.assertIn(STAT, generator.PLAYER_STATS)
        self.assertIn(STAT, generator.POSITIVE_PLAYER_STATS)

    def test_the_generator_refuses_a_potency_it_cannot_read(self):
        base = {"owner": ASH, "pieces": "", "kind": "player", "skill": "", "stat": STAT, "value_min": "75", "value_max": "100", "cond": "",
                "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
                "icd_seconds": "", "source": "x", "note": ""}
        bad = {"zero": dict(base, value_min="0", value_max="0"), "negative": dict(base, value_min="-100", value_max="-75"),
               "a range across zero": dict(base, value_min="-5", value_max="100"), "min above max": dict(base, value_min="100", value_max="75"),
               "no source": dict(base, source="")}
        for name, row in bad.items():
            with self.subTest(name), self.assertRaises(ValueError):
                power_math.Table.rows_of([row])
        self.assertEqual(1, len(power_math.Table.rows_of([base])))


T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731


class Rules(unittest.TestCase):
    def events_cases(self):
        """[(command line, expected output line or None)] for the events harness (PlayerFactor over the generated rows)."""
        n = source()
        out = [(T("row", *r), None) for r in all_rows()]
        g = lambda x: "%g" % x  # noqa: E731
        clear = [(T("clear"), None)]
        # no item: unchanged; the item put on but no stored roll yet: no value, no power
        out += clear + [(T("player", STAT, 0), "1")]
        out += clear + [(T("wears", ASH, 0), None), (T("player", STAT, 0), "1")]
        for roll in (n[0], 80, 87.5, n[1]):
            out += clear + [(T("wears", ASH, 0), None), (T("value", ASH, "", STAT, roll), None), (T("player", STAT, 0), g(1 + roll / 100))]
            out += [(T("player", "damage_dealt_pct", 0), "1"), (T("player", "damage_reduction_pct", 0), "1")]   # no other stat moves
        out += [(T("clear"), None), (T("wears", ASH, 0), None), (T("value", ASH, "", STAT, 75), None), (T("player", STAT, 0), "1.75")]
        out += [(T("clear"), None), (T("wears", ASH, 0), None), (T("value", ASH, "", STAT, 100), None), (T("player", STAT, 0), "2")]
        out += clear + [(T("value", ASH, "", STAT, 100), None), (T("player", STAT, 0), "1")]    # a roll stored but the item not worn
        return out

    def roll_cases(self):
        n = source()
        out = [(T("row", *r), None) for r in all_rows()]
        out += [(T("roll", ASH, 1), "power::%s=%g;" % (STAT, n[1])),            # a Primal Ancient: the top
                (T("roll", ASH, 0), "power::%s=%g;" % (STAT, sum(n) / 2))]      # an ordinary drop: a draw inside the range (the harness draws the middle)
        return out

    def drive(self, build, header_text, cases, name):
        work, binary = build(header_text, "ashnagarr-" + name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def both(self, header_text, name):
        a = self.drive(events.Rules.build, header_text, self.events_cases(), name + "-factor")
        b = self.drive(power_math.Rules.build, header_text, self.roll_cases(), name + "-roll")
        return a, b

    def test_the_rules_agree_with_the_source(self):
        (want, got), (roll_want, roll_got) = self.both(MATH.read_text(encoding="utf-8"), "real")
        self.assertGreater(len(want), 10)
        self.assertEqual(want, got)
        self.assertEqual(2, len(roll_want))
        self.assertEqual(roll_want, roll_got)

    def test_the_scaled_amount_is_the_amount_times_the_factor(self):
        # the places multiply their amount by the factor the rules return: an absorb of 1000 is 1750 at the item's 75 and 2000 at its 100
        n = source()
        cases = [(T("row", *r), None) for r in all_rows()]
        for roll in n:
            cases += [(T("clear"), None), (T("wears", ASH, 0), None), (T("value", ASH, "", STAT, roll), None), (T("player", STAT, 0), "")]
        _, got = self.drive(events.Rules.build, MATH.read_text(encoding="utf-8"), cases, "amount")
        self.assertEqual([1750, 2000], [round(1000 * float(x)) for x in got])

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        factor = "factor *= 1.0 + pct / 100.0;"
        best = 'return row.stat == "resource_threshold_pct" || row.stat == "damage_generation_cut_pct" ? row.min : row.max;'
        rolled = "if (!row.pieces && Rolls(row))"
        counted = "out.push_back(number * Counted(row, situation));"
        for source_text in (factor, best, rolled, counted):
            self.assertIn(source_text, real)
        # PlayerFactor is the first function that holds the factor line twice (SkillFactor holds the other copy): mutate only PlayerFactor's
        start = real.index("inline double PlayerFactor(")
        end = real.index("}", real.index("return factor;", start))
        player = real[start:end]
        mutants = {
            "factor_is_not_one_plus_n": real[:start] + player.replace(factor, "factor *= pct / 100.0;") + real[end:],
            "factor_adds_n_to_one_twice": real[:start] + player.replace(factor, "factor *= 1.0 + 2 * pct / 100.0;") + real[end:],
            "primal_takes_the_bottom": real.replace(best, "return row.min;"),
            "no_stored_roll_still_powers": real.replace(rolled, "if (false)"),
        }
        for name, mutant in mutants.items():
            self.assertNotEqual(real, mutant, "the %s mutation no longer applies" % name)
            (want, got), (roll_want, roll_got) = self.both(mutant, name)
            self.assertTrue(want != got or roll_want != roll_got, "mutant %s passed" % name)


def shield_problems(gem, wizard, powers, header, other_files, shaman):
    """What is wrong with the places a player's shield amount is set: the guards a mutant of the source must trigger."""
    bad = []
    read = 'return PlayerFactor(player, "%s");' % STAT
    if "double ShieldFactor(Player const*);" not in header:
        bad.append("the header does not declare ShieldFactor")
    if "double ShieldFactor(Player const* player)\n    {\n        " + read not in powers:
        bad.append("ShieldFactor does not read " + STAT)
    # Molten Wildebeest's shield: the one place a gem sets an absorb amount
    put = gem[gem.index("void PutShield(Player* player, double amount)"):gem.index("// A damage taken (a monster's hit")]
    if "effect->ChangeAmount(int32(std::min(amount * ItemPowers::ShieldFactor(player), double(INT32_MAX))));" not in put:
        bad.append("PutShield does not scale its amount")
    if put.count("ChangeAmount(") != 1:
        bad.append("PutShield sets an amount more than once")
    # the Wizard's shield helper: Spectral Blade - Barrier Blades, Magic Weapon - Deflection, Unstable Anomaly, Galvanizing Ward, Dominance
    helper = wizard[wizard.index("void Shield(Player* player, char const* helper, double lifePct, double seconds)"):wizard.index("// The freeze mark alone")]
    if "effect->ChangeAmount(int32(player->GetMaxHealth() * lifePct / 100 * ItemPowers::ShieldFactor(player)));" not in helper:
        bad.append("the Wizard's Shield helper does not scale its amount")
    if helper.count("ChangeAmount(") != 1:
        bad.append("the Wizard's Shield helper sets an amount more than once")
    # Diamond Skin: the absorb aura's amount is worked out when it is applied
    case = wizard[wizard.index("case SPELL_AURA_SCHOOL_ABSORB:"):wizard.index("case SPELL_AURA_MOD_MELEE_DAMAGE_TAKEN_PCT:")]
    if ('amount = owner ? int32(owner->GetMaxHealth() * Num(id, "absorb_capacity_life_pct") / 100 *\n'
            '                                               ItemPowers::ShieldFactor(owner->ToPlayer()))\n                                       : 0;') not in case:
        bad.append("Diamond Skin's absorb amount does not scale")
    # Force Armor (Energy Armor rune, diablocraft-y3ldu): the cap on what it cuts is that rune's absorb amount (wizard_runes.csv max_absorb_pct),
    # so it is scaled like the others, and it is the cap, not the threshold or the hit, that is scaled
    force = wizard[wizard.index("// Force Armor: a hit over the threshold"):wizard.index("damage -= uint32(std::max(0.0, cut));")]
    if 'maxLife * Num(id, "max_absorb_pct") / 100 * ItemPowers::ShieldFactor(victim));' not in force:
        bad.append("Force Armor's cap does not scale")
    if force.count("ItemPowers::ShieldFactor(") != 1 or wizard.count('"max_absorb_pct"') != 1:
        bad.append("Force Armor's cap is scaled other than once, or max_absorb_pct is read elsewhere")
    # no other amount is set around the helper: the five shield records are made only through Shield(), every absorb percent is read
    # by it or by the aura case, and each of the five identities is shielded exactly once
    calls = re.findall(r'\bShield\((?:player|victim), "([^"]+)"', wizard)
    idents = re.search(r"constexpr char const\* ShieldBuffs\[\] = \{(.*?)\};", wizard, re.S)[1]
    if sorted(calls) != sorted(re.findall(r'"([^"]+)"', idents)):
        bad.append("a shield record is made around the helper, or one is not made through it: %r" % calls)
    if wizard.count('"absorb_capacity_life_pct"') != len(calls) + 1:
        bad.append("an absorb percent is read outside Shield() and the aura case")
    if wizard.count("ItemPowers::ShieldFactor(") != 3:
        bad.append("the Wizard file does not call the one reader three times (Shield, Diamond Skin, Force Armor)")
    if gem.count("ItemPowers::ShieldFactor(") != 1:
        bad.append("the gem file does not call the one reader once")
    # the Shaman's Stoneskin: the pool a broken shield leaves is its percent of the maximum Life, times the shield potency
    if "double const amount = player->GetMaxHealth() * share * ItemPowers::ShieldFactor(player);" not in shaman or shaman.count("ItemPowers::ShieldFactor(") != 1:
        bad.append("Stoneskin's absorb pool does not scale, or the Shaman file calls the one reader other than once")
    # no other file sets an absorb amount: every .cpp that names the absorb aura, its percent or the Wildebeest shield is a place above
    for name, text in other_files.items():
        if re.search(r"SPELL_AURA_SCHOOL_ABSORB|absorb_capacity_life_pct|GemPower::Wildebeest|SetAmount\(|\bAbsorb\w*Amount", text):
            bad.append("%s names an absorb: a place this test does not know" % name)
    return bad


class Places(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gem = GEM_CPP.read_text(encoding="utf-8")
        cls.wizard = WIZARD_CPP.read_text(encoding="utf-8")
        cls.powers = POWERS_CPP.read_text(encoding="utf-8")
        cls.header = POWERS_H.read_text(encoding="utf-8")
        cls.shaman = SHAMAN_CPP.read_text(encoding="utf-8")
        cls.others = {str(p.relative_to(MODULE)): p.read_text(encoding="utf-8") for p in sorted(SRC.rglob("*.cpp"))
                      if p not in (GEM_CPP, SHAMAN_CPP) and p not in wizard_source.files()}

    def problems(self, **swap):
        return shield_problems(swap.get("gem", self.gem), swap.get("wizard", self.wizard), swap.get("powers", self.powers),
                               swap.get("header", self.header), swap.get("others", self.others), swap.get("shaman", self.shaman))

    def test_every_shield_place_calls_the_one_reader(self):
        self.assertEqual([], self.problems())

    def test_the_reader_is_the_player_factor_of_the_tables_stat(self):
        self.assertIn('double ShieldFactor(Player const* player)\n    {\n        return PlayerFactor(player, "%s");' % STAT, self.powers)
        # nothing hardcoded: the 75 and the 100 are the table's, not the code's
        for text in (self.gem, self.wizard):
            self.assertNotRegex(text, r"ShieldFactor\([^)]*\)\s*[*+]\s*(75|100|1\.75|2)\b")
        factor = self.powers[self.powers.index("double ShieldFactor(Player const* player)"):]
        factor = factor[:factor.index("}") + 1]
        self.assertNotRegex(factor, r"\b(75|100|1\.75)\b")

    def test_the_mutants_fail_the_same_guards(self):
        reader = "ItemPowers::ShieldFactor(player)"
        mutants = {
            "the gem shield skips the factor": dict(gem=self.gem.replace("amount * " + reader, "amount")),
            "the Wizard helper skips the factor": dict(wizard=self.wizard.replace("lifePct / 100 * " + reader, "lifePct / 100")),
            "Diamond Skin skips the factor": dict(wizard=self.wizard.replace(" / 100 *\n                                               ItemPowers::ShieldFactor(owner->ToPlayer()))", " / 100)")),
            "Force Armor's cap skips the factor": dict(wizard=self.wizard.replace(' / 100 * ItemPowers::ShieldFactor(victim));', ' / 100);')),
            "Force Armor scales the threshold, not the cap": dict(wizard=self.wizard.replace(
                ' / 100 * ItemPowers::ShieldFactor(victim));', ' / 100);').replace(
                'damage > maxLife * Num(id, "damage_threshold_pct") / 100)', 'damage > maxLife * Num(id, "damage_threshold_pct") / 100 * ItemPowers::ShieldFactor(victim))')),
            "the reader reads another stat": dict(powers=self.powers.replace('PlayerFactor(player, "%s")' % STAT, 'PlayerFactor(player, "damage_dealt_pct")')),
            "the reader is not declared": dict(header=self.header.replace("double ShieldFactor(Player const*);", "")),
            "a sixth shield around the helper": dict(wizard=self.wizard.replace(
                'Shield(player, "Dominance - shield", Num(id, "absorb_capacity_life_pct") * stacks,',
                'Shield(player, "Dominance - shield", Num(id, "absorb_capacity_life_pct") * stacks,', 1)
                + '\n// Shield(player, "Another - shield", 1, 1);\nShield(player, "Another - shield", Num(id, "absorb_capacity_life_pct"), 1);'),
            "Stoneskin skips the factor": dict(shaman=self.shaman.replace("player->GetMaxHealth() * share * ItemPowers::ShieldFactor(player);", "player->GetMaxHealth() * share;")),
            "a new file sets an absorb of its own": dict(others=dict(self.others, **{"src/combat/dc_new.cpp": "AuraEffect* e; e->SetAmount(5); // SPELL_AURA_SCHOOL_ABSORB"})),
        }
        for name, swap in mutants.items():
            text = swap.get("gem") or swap.get("wizard") or swap.get("powers") or swap.get("header") or swap.get("others") or swap.get("shaman")
            reference = {"gem": self.gem, "wizard": self.wizard, "powers": self.powers, "header": self.header, "others": self.others, "shaman": self.shaman}[next(iter(swap))]
            self.assertNotEqual(reference, text, "the %s mutation no longer applies" % name)
            self.assertTrue(self.problems(**swap), "mutant survived: " + name)


if __name__ == "__main__":
    unittest.main()
