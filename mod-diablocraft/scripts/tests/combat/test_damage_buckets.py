"""diablocraft-cy3o (damage buckets part 1): the seven bonuses of docs/research/damage-buckets.md 6a are multipliers of their own.

  * the production arithmetic (src/combat/dc_damage_buckets.h: Additive, AddFactor, Product, Total) is compiled and driven with
    the sheet's numbers (Ruthless, No Escape, Insanity, Arcane Attunement per enemy, Spark per enemy, Elemental Exposure per
    stack, a rolled pet-skill affix): the hit with the bonus is the hit without it times (1 + bonus), whatever the additive
    pool holds (Battle Rage and more). Mutants of the header fail the same driver;
  * source-text guards, function by function: each of the seven is built in its module's Multipliers/TargetFactor and no longer
    in the DamageBonus/TargetBonus that feed the pool; section 6a's "checked and the same as D3" list stays where it was;
    hit.legendary is the item and set powers' multiplier (diablocraft-ews9q). They prove where the code sits, not that it runs; the in-game steps are in
    docs/test-diablocraft-cy3o.md.
"""
import csv
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import wizard_source  # noqa: E402
import harness_env
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
import barbarian_source  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
SRC = MODULE / "src"
DATA = MODULE / "data/d3"
HEADER = SRC / "combat/dc_damage_buckets.h"
HARNESS = MODULE / "tests/damage_buckets/harness.cpp"
POOLS = [0, 15, 40, 190]          # percent: nothing, Battle Rage alone, a few buffs, a full rolled gear set


def sheet(name, **match):
    with open(DATA / name, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if all(r[k] == v for k, v in match.items())]
    assert len(rows) == 1, (name, match, rows)
    return float(rows[0]["value"])


# row -> the percent of one factor, from the sheet (never typed here)
ROWS = {
    "Ruthless": sheet("barbarian_passive_values.csv", skill="Ruthless", token="damage_bonus_pct"),
    "No Escape": sheet("barbarian_passive_values.csv", skill="No Escape", token="damage_bonus_pct"),
    "Insanity": sheet("barbarian_skill_values.csv", skill="Wrath of the Berserker", rune="Insanity", token="damage_bonus_pct"),
    "Arcane Attunement": 5 * sheet("wizard_skill_values.csv", skill="Wave of Force", rune="Arcane Attunement", token="damage_bonus_pct"),
    "Spark": sheet("wizard_skill_values.csv", skill="Arcane Orb", rune="Spark", token="max_count")
    * sheet("wizard_skill_values.csv", skill="Arcane Orb", rune="Spark", token="damage_bonus_pct"),
    "Elemental Exposure": sheet("wizard_passive_values.csv", skill="Elemental Exposure", token="max_stacks_count")
    * sheet("wizard_passive_values.csv", skill="Elemental Exposure", token="damage_taken_pct"),
    "Pet skill damage": 20.0,      # a rolled "+20% Hydra damage"; the roll is the designer's, any number holds
}


def build(header_text, name):
    compiler = shutil.which("c++") or shutil.which("g++")
    if not compiler:
        raise unittest.SkipTest("no C++ compiler")
    work = Path(tempfile.mkdtemp(prefix="dmgbuckets-%s-" % name))
    (work / "combat").mkdir()
    (work / "combat/dc_damage_buckets.h").write_text(header_text, encoding="utf-8")
    built = subprocess.run([compiler, "-std=c++17", "-I", str(work), str(HARNESS), "-o", str(work / "harness")],
                           capture_output=True, text=True)
    if built.returncode:
        raise AssertionError("harness did not compile:\n" + built.stderr[-3000:])
    return work


def totals(header_text, name, hits):
    work = build(header_text, name)
    try:
        (work / "cases.txt").write_text("".join("hit %r %d %s\n" % (pool, len(f), " ".join(map(repr, f))) for pool, f in hits))
        ran = harness_env.run([str(work / "harness"), str(work / "cases.txt")], capture_output=True, text=True)
        return [float(x) for x in ran.stdout.split()]
    finally:
        shutil.rmtree(work, ignore_errors=True)


def check(header_text, name):
    hits = [(pool, [pct]) for pct in ROWS.values() for pool in POOLS]
    hits += [(pool, list(ROWS.values())) for pool in POOLS]
    bare = [(pool, []) for pool in POOLS]
    # and the pool itself is still additive: 15% and 0% in the pool differ by exactly 1.15
    got = totals(header_text, name, hits + bare + [(15, []), (0, [])])
    base = dict(zip(POOLS, got[len(hits):len(hits) + len(POOLS)]))
    for (pool, factors), total in zip(hits, got):
        want = base[pool]
        for pct in factors:
            want *= 1 + pct / 100
        if abs(total - want) > 1e-6 * want:
            raise AssertionError("pool %s factors %s: %r != %r" % (pool, factors, total, want))
    if abs(got[-2] / got[-1] - 1.15) > 1e-9:
        raise AssertionError("the additive pool is no longer 1 + sum")


class Arithmetic(unittest.TestCase):
    def test_hit_with_the_bonus_is_the_hit_without_times_one_plus_bonus(self):
        check(HEADER.read_text(encoding="utf-8"), "prod")

    def test_mutants_fail(self):
        text = HEADER.read_text(encoding="utf-8")
        mutants = {
            "product-is-a-sum": text.replace("product *= factor.second;", "product += factor.second - 1.0;"),
            "bonus-joins-the-pool": text.replace("out.emplace_back(name, 1.0 + pct / 100.0);", "out.emplace_back(name, 1.0);"),
            "total-drops-standalone": text.replace("legendary * standalone * crit", "legendary * crit"),
        }
        for label, mutant in mutants.items():
            self.assertNotEqual(text, mutant, label)
            with self.assertRaises(AssertionError, msg=label):
                check(mutant, label)


def body(path, signature):
    """The text of the function whose definition line contains `signature`, braces matched."""
    text = path.read_text(encoding="utf-8")
    start = text.index(signature)
    open_at = text.index("{", start)
    depth = 0
    for i in range(open_at, len(text)):
        depth += text[i] == "{"
        depth -= text[i] == "}"
        if depth == 0:
            return text[start:i + 1]
    raise AssertionError(signature)


PASSIVES = SRC / "classes/barbarian/dc_barbarian_passives.cpp"
ABILITIES = barbarian_source.CPP
WIZARD = wizard_source.CPP
COMBAT = SRC / "combat/dc_combat.cpp"


class Placement(unittest.TestCase):
    def assertIn_(self, needles, text, where):
        for needle in needles:
            self.assertIn(needle, text, "%s should hold %s" % (where, needle))

    def assertNotIn_(self, needles, text, where):
        for needle in needles:
            self.assertNotIn(needle, text, "%s must not hold %s" % (where, needle))

    def test_barbarian_passives(self):
        pool = body(PASSIVES, "double DamageBonus(Player* p)")
        self.assertNotIn_(['"Ruthless"', '"No Escape"'], pool, "Passives::DamageBonus")
        self.assertIn_(['"Weapons Master"', '"Berserker Rage"', "BrawlerOn"], pool, "Passives::DamageBonus")  # 6a: same as D3
        factors = body(PASSIVES, "void Multipliers(")
        self.assertIn_(['AddFactor(out, "Ruthless"', 'AddFactor(out, "No Escape"'], factors, "Passives::Multipliers")

    def test_barbarian_abilities(self):
        pool = body(ABILITIES, "double DamageBonus(Player* p)") + body(ABILITIES, "void OnDamageBonus(Player* p, double& result)")
        self.assertNotIn_(["Insanity"], pool, "Abilities::DamageBonus")
        self.assertIn_(['"Battle Rage"', "Marauder's Rage"], pool, "Abilities::DamageBonus")
        self.assertIn_(['AddFactor(out, "Insanity"'], body(ABILITIES, "void Multipliers(") + body(ABILITIES, "void OnMultipliers("),
                       "Abilities::Multipliers")

    def test_wizard(self):
        pool = body(WIZARD, "double DamageBonus(Player* player, Unit* /*target*/")
        self.assertNotIn_(["attunement", "spark"], pool, "Wizard::DamageBonus")
        self.assertIn_(['"Magic Weapon"', '"Sparkflint"', '"Glass Cannon"', '"Unwavering Will"', "spellsteal"], pool,
                       "Wizard::DamageBonus")  # 6a: same as D3
        taken = body(WIZARD, "double TargetBonus(")
        self.assertNotIn_(["Elemental Exposure"], taken, "Wizard::TargetBonus")
        self.assertIn_(['"Lightning Storm"', '"Time Warp"', "boneChill", "schoolTaken", '"Cold Blooded"'], taken,
                       "Wizard::TargetBonus")
        multi = body(WIZARD, "void Multipliers(")
        self.assertIn_(['AddFactor(out, "Arcane Attunement", state.attunement)', 'AddFactor(out, "Spark", state.spark)'], multi,
                       "Wizard::Multipliers")
        self.assertIn_(['"Elemental Exposure"', "max_stacks_count"], body(WIZARD, "double TargetFactor("), "Wizard::TargetFactor")
        self.assertIn_(["absoluteZero", "SpectralBlade::FlameBladesBonus(player, bonus)"], body(WIZARD, "double ElementalBonus("),
                       "Wizard::ElementalBonus")
        self.assertIn_(['"Flame Blades"', '"damage_bonus_pct"', '"max_bonus_pct"'], body(WIZARD, "void FlameBladesBonus("),
                       "SpectralBlade::FlameBladesBonus")
        self.assertIn_(['"Power Hungry"', '"Audacity"', '"Arcane Dynamo"', '"Archon"'], body(WIZARD, "double Standalone("),
                       "Wizard::Standalone")

    def test_the_hit(self):
        hit = body(COMBAT, "bool ComputeHit(")
        # The factors are appended, so a Hit computed into twice (the Rend bleed's snapshot, on every REAPPLY) must start
        # empty: the clear comes before the first append, or Insanity/Ruthless compound on each recast (sns4).
        self.assertIn("hit.factors.clear();", hit)
        self.assertLess(hit.index("hit.factors.clear();"), hit.index("AddFactor(hit.factors"))
        self.assertLess(hit.index("hit.factors.clear();"), hit.index("Multipliers(player"))
        self.assertIn_(["Passives::Multipliers(player, target, shell.skill, hit.factors)",
                        "Abilities::Multipliers(player, hit.factors)", "Wizard::Multipliers(player, shell.spellId, hit.factors)",
                        "Wizard::TargetFactor(player, target, hit.factors)", "Product(hit.factors)", 'hit.legendary = ItemPowers::SkillFactor(player, petName, "damage_increase_pct") * ItemPowers::DealtFactor(player) * CopyFactor();',
                        'AddFactor(hit.factors, "Pet skill damage"'], hit, "ComputeHit")
        pool = hit[hit.index("hit.additive = Additive("):hit.index("hit.elemental")]
        self.assertNotIn_(["Multipliers", "Insanity", "Ruthless"], pool, "the additive pool of ComputeHit")
        self.assertIn("Passives::DamageBonus(player)", pool)
        self.assertIn("IsPetSkill(shell.skill.c_str()) ? 0", pool)      # a pet skill's own affix is not in the pool
        self.assertIn("Wizard::TargetFactor(player, target) / hit.targetFactor", body(COMBAT, "double VictimAdjustedTotal("))
        self.assertIn_(["for (auto const& [name, factor] : factors)"], body(COMBAT, "std::string Hit::Describe()"), "Describe")

    def test_the_sheet_multiplies_insanity(self):
        self.assertIn("DC::Combat::DamageFactor(player)", (SRC / "stats/dc_stats.cpp").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
