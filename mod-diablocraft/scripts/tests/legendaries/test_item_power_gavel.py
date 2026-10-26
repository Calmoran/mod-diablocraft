"""The Gavel of Judgment (diablocraft-2z25c, legendary build 2 bead 3): Hammer of the Ancients deals +[600-800]% and returns 25 Fury
if it hits 3 or fewer enemies.

  * data/legendary_powers.csv gains its two rows: a `skill` damage_increase_pct [600-800] and an `effect` resource_refund 25, fired on
    `hit_spender` for Hammer of the Ancients under the new condition `enemies_hit_at_most` 3; the numbers and words are read from
    d3planner's item file and set against the tooltip; the generator refuses the condition anywhere it cannot be counted;
  * the production rules (dc_item_power_math.h Fire with the cast's enemy count, SkillFactor) are compiled and driven with the generated
    rows through the events and power_math harnesses, and their mutants fail the same drivers;
  * source-text guards that the cast path counts the enemies it hit and hands the count through Combat::Connected and
    ItemPowers::Attack to Fire, and that the refund is the class's own primary resource (they prove the calls are there, not that they
    run; the C++ is compile-checked by syntax_check.sh and the in-game steps are in docs/test-diablocraft-2z25c.md).
  * diablocraft-aassb: HotA's records (Speed 35) resolve in dc_ability_targets::Impact, not ResolveCast; the path is read from the
    generated records and every Connected there must carry a count, and the production Struck (the count Impact passes) is compiled and
    driven, with its mutants.
"""
import csv
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
import harness_env  # noqa: E402
import test_item_power_events as events  # noqa: E402  (modules, so their test classes are not run twice)
import test_item_power_math as power_math  # noqa: E402
import test_spectral_blade_runes as spectral  # noqa: E402  (the generated records' reader)
from test_item_power_math import generator, planner, read_csv, tooltip, all_rows  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
GAVEL, BRACERS = "P61_Unique_Mighty_2H_001", "P61_Unique_Bracer_105"
HOTA = "Hammer of the Ancients"
SPELL_ATTR1_CHANNELLED = 0x4 | 0x40   # IS_CHANNELLED, IS_SELF_CHANNELLED: SpellInfo::IsChanneled


def source():
    text = planner("item_twohand.js", GAVEL)
    found = re.search(r'format: "The damage of Hammer of the Ancients is increased by %d%% and it returns (\d+) Fury if it hits (\d+) or '
                      r'fewer enemies.", min: (\d+), max: (\d+)\}', text)
    assert found, text
    return {"refund": float(found[1]), "most": float(found[2]), "damage": (float(found[3]), float(found[4]))}


class Table(unittest.TestCase):
    def test_the_rows_are_the_sources(self):
        n = source()
        self.assertEqual((25, 3, (600, 800)), (n["refund"], n["most"], n["damage"]))
        blank = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
        self.assertEqual({(GAVEL, 0, "skill", HOTA, "damage_increase_pct", *n["damage"], *blank),
                          (GAVEL, 0, "effect", "", "resource_refund", n["refund"], n["refund"], "enemies_hit_at_most", n["most"], "", 0.0, 0,
                           "hit_spender", HOTA, 100.0, 0.0)},
                         {r for r in all_rows() if r[0] == GAVEL})
        self.assertIn("%g–%g%%" % n["damage"], tooltip(GAVEL))
        pool = next(r for r in read_csv("data/d3/base_items.csv") if r["d3_id"] == GAVEL)
        self.assertEqual(("The Gavel of Judgment", "yes", "barbarian"), (pool["d3_name"], pool["pool_version"], pool["designated_class"]))
        # the refund is a spender's: Hammer of the Ancients states a cost, so a cast that hit fires hit_spender (ItemPower::HitKinds)
        cost = [r for r in read_csv("data/d3/barbarian_skill_values.csv") if r["skill"] == HOTA and not r["rune"] and r["token"] == "cost_resource"]
        self.assertEqual(1, len(cost))
        self.assertGreater(float(cost[0]["value"]), 0)

    def test_the_generator_refuses_a_count_it_cannot_read(self):
        base = {"owner": GAVEL, "pieces": "", "kind": "effect", "skill": "", "stat": "resource_refund", "value_min": "25", "value_max": "25",
                "cond": "enemies_hit_at_most", "cond_arg": "3", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "hit_spender",
                "fire_skills": HOTA, "chance_pct": "", "icd_seconds": "", "source": "x", "note": ""}
        bad = {
            "on a skill row": dict(base, kind="skill", skill=HOTA, stat="damage_increase_pct", value_min="600", value_max="800"),
            "fired per enemy (hit)": dict(base, fire_on="hit"),
            "fired on a cast (no hits yet)": dict(base, fire_on="cast"),
            "fired on a kill": dict(base, fire_on="kill", fire_skills=""),
            "a part of an enemy": dict(base, cond_arg="2.5"),
            "no count": dict(base, cond_arg=""),
            "with skills of its own": dict(base, cond_skills=HOTA),
            "another condition on an effect": dict(base, cond="triggered"),
            "a skill that does not exist": dict(base, fire_skills="Not A Skill"),
            "skills on an event that names none": dict(base, cond="", cond_arg="", fire_on="taken"),
        }
        for name, row in bad.items():
            with self.subTest(name), self.assertRaises(ValueError):
                power_math.Table.rows_of([row])
        self.assertEqual(1, len(power_math.Table.rows_of([base])))
        self.assertEqual(1, len(power_math.Table.rows_of([dict(base, cond="", cond_arg="")])))   # a refund on every cast that hit is a row too
        self.assertIn("resource_refund", generator.EFFECT_STATS)


class Rules(unittest.TestCase):
    def cases(self):
        T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
        n = source()
        out = [(T("row", *r), None) for r in all_rows()]
        clear = [(T("clear"), None), (T("now", 100000), None)]
        fire = lambda skill: T("fire", "hit_spender", skill, 1, 50, 0)  # noqa: E731
        refund = "resource_refund=%g;" % n["refund"]
        for enemies in (0, 1, 2, 3, 4, 10):
            out += clear + [(T("wears", GAVEL, 0), None), (T("enemies", enemies), None),
                            (fire(HOTA), refund if 1 <= enemies <= n["most"] else ""),
                            (fire("Whirlwind"), ""),                                         # another spender's cast
                            (T("fire", "hit_generator", HOTA, 1, 50, 0), "")]                 # the row is the spender's
        out += clear + [(T("enemies", 2), None), (fire(HOTA), "")]                            # not worn
        out += clear + [(T("wears", GAVEL, 0), None), (T("enemies", 2), None), (fire(HOTA), refund), (fire(HOTA), refund)]   # every cast
        return out

    def drive(self, header_text, name):
        cases = self.cases()
        work, binary = events.Rules.build(header_text, "gavel-" + name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def damage_cases(self):
        T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
        n = source()
        out = [(T("row", *r), None) for r in all_rows()]
        for roll in (*n["damage"], 700):
            out += [(T("clear"), None), (T("wears", GAVEL), None), (T("value", GAVEL, HOTA, "damage_increase_pct", roll), None),
                    (T("factor", HOTA, "damage_increase_pct"), "%g" % (1 + roll / 100)), (T("factor", "Whirlwind", "damage_increase_pct"), "1")]
        out += [(T("clear"), None), (T("wears", GAVEL), None), (T("wears", BRACERS), None), (T("value", GAVEL, HOTA, "damage_increase_pct", 700), None),
                (T("value", BRACERS, HOTA, "damage_increase_pct", 400), None), (T("factor", HOTA, "damage_increase_pct"), "%g" % (8 * 5))]
        out += [(T("roll", GAVEL, 1), "power:%s:damage_increase_pct=%g;" % (HOTA, n["damage"][1]))]   # a Primal: the top; the refund is fixed
        return out

    def test_the_rules_agree_with_the_source(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), "real")
        self.assertGreater(len(want), 20)
        self.assertEqual(want, got)
        cases = self.damage_cases()
        work, binary = power_math.Rules.build(MATH.read_text(encoding="utf-8"), "gavel-damage")
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            self.assertEqual([w for _, w in cases if w is not None], run.stdout.split("\n")[:-1])
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        check = 'if (row.cond == "enemies_hit_at_most" && !(situation.enemiesHit >= 1 && situation.enemiesHit <= row.arg))'
        mutants = {
            "three_is_too_many": real.replace(check, check.replace("<= row.arg", "< row.arg")),
            "a_miss_counts": real.replace(check, check.replace("situation.enemiesHit >= 1 && ", "")),
            "any_count": real.replace(check, 'if (row.cond == "enemies_hit_at_most" && false)'),
        }
        for name, mutant in mutants.items():
            self.assertTrue(real != mutant, "the %s mutation no longer applies" % name)
            want, got = self.drive(mutant, name)
            self.assertNotEqual(want, got, "mutant %s passed" % name)


class Hooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.powers = item_powers_source.CPP.read_text(encoding="utf-8")
        cls.combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])

    def test_the_cast_path_counts_its_enemies_through_to_fire(self):
        cast = self.combat[self.combat.index("void ResolveCast(Player* player, Shell const& shell,"):]
        cast = cast[:cast.index("// --- the Wizard's channels")]
        # each enemy the hammer itself hit, once; the shell may be the Monk's punched copy, the count is what reaches Fire
        self.assertRegex(cast, r"connected \+= ResolveHit\(player, target, [^;]*\binfo\) \? 1 : 0;")
        self.assertIn("Connected(player, shell.spellId, connected);", cast)
        connected = self.combat[self.combat.index("void Connected(Player* player, std::uint32_t spellId, unsigned enemies)"):]
        self.assertIn("ItemPowers::Attack(player, spellId, enemies);", connected[:connected.index("\n    }\n")])
        attack = self.powers[self.powers.index("void Attack(Player* player, std::uint32_t spellId, unsigned enemies)"):self.powers.index("void Taken(")]
        self.assertIn('Fire(player, "hit_spender", name, scale, nullptr, enemies);', attack)
        self.assertIn('Fire(player, "hit_generator", name, scale, nullptr, enemies);', attack)
        fire = self.powers[self.powers.index("void Fire(Player* player, char const* event"):self.powers.index("constexpr std::uint32_t ImmuneKey")]
        self.assertIn("situation.enemiesHit = enemies;", fire)
        self.assertLess(fire.index("situation.enemiesHit = enemies;"), fire.index("fired = ItemPower::Fire("))

    def test_hotas_records_reach_a_counted_connected(self):
        # diablocraft-aassb: dc_ability_targets resolves a record with Speed > 0 that is not channelled in Impact, one AfterHit per
        # target, never in ResolveCast. HotA's records have Speed 35, so the count must come through Impact, or the refund never fires.
        with (MODULE / "data/generated/spell_shells.csv").open(encoding="utf-8") as stream:
            hota = [int(row["spell_id"]) for row in csv.DictReader(stream)
                    if row["name"].split(" - ")[0] == HOTA and row["kind"] in ("active", "rune")]
        self.assertEqual(len(hota), 6)
        records = spectral.generated_rows()
        projectile = {i for i in hota if float(records[i]["Speed"]) > 0 and not int(records[i]["AttributesEx"]) & SPELL_ATTR1_CHANNELLED}
        script = self.combat[self.combat.index("class dc_ability_targets"):]
        self.assertIn("return GetSpellInfo()->Speed > 0 && !GetSpellInfo()->IsChanneled();",
                      script[script.index("bool Projectile()"):script.index("SpellCastResult Check()")], "the path rule read above")
        impact = script[script.index("void Impact()"):script.index("void Register() override")]
        if projectile:
            # Every Connected the hammer's impacts reach carries a count, and the cone's count is the enemies it hits.
            calls = re.findall(r"Connected\(([^;]*)\);", impact)
            self.assertTrue(calls)
            for call in calls:
                self.assertEqual(len(call.split(",")), 3, "Connected(%s) passes no enemy count" % call)
            self.assertIn("unsigned const struck = connected ? 0 : Struck(player);", impact)
            self.assertIn("Connected(player, shell.spellId, struck);", impact)
            struck = script[script.index("unsigned Struck(Player* player)"):script.index("void Impact()")]
            self.assertIn("for (ObjectGuid const& guid : native)", struck)
            self.assertIn("ValidTarget(player, ObjectAccessor::GetUnit(*player, guid), GetSpellInfo(), shell.targeting.Friendly())", struck)
        self.assertEqual(projectile, set(hota), "HotA's records are all one path; the guard above follows the one they take")

    STRUCK_HARNESS = r"""
#include <cstdio>
#include <vector>
struct ObjectGuid { int id; };
struct Unit { bool valid; };
struct Player { std::vector<Unit> world; };
struct SpellInfo {};
namespace ObjectAccessor { Unit* GetUnit(Player& p, ObjectGuid const& g) { return g.id < 0 ? nullptr : &p.world[g.id]; } }
bool seenFriendly = false;
bool ValidTarget(Player*, Unit* u, SpellInfo const*, bool friendly) { seenFriendly |= friendly; return u && u->valid; }
struct Targeting { bool Friendly() const { return false; } };
struct Shell { Targeting targeting; };
struct Script {
    std::vector<ObjectGuid> native; Shell shell; SpellInfo info;
    SpellInfo const* GetSpellInfo() const { return &info; }
@STRUCK@
};
int main()
{
    Player p{{{true}, {true}, {false}, {true}, {true}}};   // 2 is dead or out of sight
    Script s;
    std::printf("%u", s.Struck(&p));                       // no list: the one target it hit
    s.native = {{0}, {1}, {3}};
    std::printf(" %u", s.Struck(&p));
    s.native = {{0}, {1}, {2}, {-1}};                      // one listed enemy no longer valid, one gone from the map
    std::printf(" %u", s.Struck(&p));
    s.native = {{0}, {1}, {3}, {4}};
    std::printf(" %u %d\n", s.Struck(&p), seenFriendly);
}
"""

    def struck(self, combat):
        body = combat[combat.index("            unsigned Struck(Player* player)"):combat.index("            void Impact()")]
        compiler = shutil.which("c++") or shutil.which("g++")
        if not compiler:
            raise unittest.SkipTest("no C++ compiler")
        power_math.SCRATCH.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="gavel-struck-", dir=str(power_math.SCRATCH)))
        try:
            (work / "struck.cpp").write_text(self.STRUCK_HARNESS.replace("@STRUCK@", body), encoding="utf-8")
            built = subprocess.run([compiler, "-std=c++17", str(work / "struck.cpp"), "-o", str(work / "struck")],
                                   capture_output=True, text=True)
            self.assertEqual(0, built.returncode, built.stderr[-3000:])
            run = harness_env.run([str(work / "struck")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return run.stdout.strip()
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_impact_count_is_the_enemies_the_hammer_hits(self):
        # Production Struck, compiled: 1 with no launch list, else the listed enemies still valid (3, 2, 4: 4 is over the Gavel's 3).
        self.assertEqual("1 3 2 4 0", self.struck(self.combat))

    def test_the_impact_count_mutants_fail(self):
        body = self.combat[self.combat.index("            unsigned Struck(Player* player)"):self.combat.index("            void Impact()")]
        mutants = {"the whole list": ("count += ValidTarget(", "count += 1 || ValidTarget("),
                   "no list counts none": ("                    return 1;", "                    return 0;"),
                   "the count dropped": ("return count;", "return 1;")}
        for name, (old, new) in mutants.items():
            with self.subTest(name):
                self.assertIn(old, body)
                self.assertNotEqual("1 3 2 4 0", self.struck(self.combat.replace(body, body.replace(old, new))))

    # diablocraft-dtumj: the hit kills its target before anything after it runs (ResolveHit -> DealSpellDamage), so the count must
    # not drop the enemy the connecting hit kills. Production Struck and the end of production Impact, compiled, with a ResolveHit
    # that kills what it hits.
    IMPACT_HARNESS = r"""
#include <cstdio>
#include <set>
#include <vector>
struct ObjectGuid { int id; long GetRawValue() const { return id; } };
struct Unit { bool valid; int id; ObjectGuid GetGUID() const { return {id}; } };
struct Player { std::vector<Unit> world; };
struct SpellInfo {};
namespace ObjectAccessor { Unit* GetUnit(Player& p, ObjectGuid const& g) { return g.id < 0 ? nullptr : &p.world[g.id]; } }
bool ValidTarget(Player*, Unit* u, SpellInfo const*, bool) { return u && u->valid; }
struct Targeting { bool Friendly() const { return false; } };
struct Shell { Targeting targeting; unsigned spellId = 7; };
std::vector<unsigned> counts;
void Connected(Player*, unsigned, unsigned count) { counts.push_back(count); }
bool ResolveHit(Player*, Unit* target, Shell const&, SpellInfo const*) { target->valid = false; return true; }   // a killing blow
namespace Necromancer { bool Impact(Player*, Unit*, unsigned, unsigned) { return false; } }   // the class's seam: it leaves the hit to the engine
namespace DemonHunter { bool Impact(Player*, Unit*, Unit*, std::vector<ObjectGuid> const&, unsigned) { return false; } }   // the same
struct Script {
    std::vector<ObjectGuid> native; Shell shell; SpellInfo info; std::set<long> impacted; bool connected = false;
    SpellInfo const* GetSpellInfo() const { return &info; }
    Unit* GetExplTargetUnit() const { return nullptr; }
@STRUCK@
    void Land(Player* player, Unit* target)
    {
@TAIL@
};
Player Fresh() { return Player{{{true, 0}, {true, 1}, {true, 2}, {true, 3}, {true, 4}}}; }
int main()
{
    { Player p = Fresh(); Script s; s.native = {{0}}; s.Land(&p, &p.world[0]); }                         // its only target dies: 1
    { Player p = Fresh(); Script s; s.native = {{0}, {1}, {3}, {4}}; s.Land(&p, &p.world[0]); }          // 4 listed, the first dies: 4
    { Player p = Fresh(); Script s; s.native = {{0}, {1}, {3}}; s.Land(&p, &p.world[0]); s.Land(&p, &p.world[1]); }   // once a cast: 3
    for (unsigned c : counts) std::printf("%u ", c);
    std::printf("\n");
}
"""

    def impact(self, combat):
        struck = combat[combat.index("            unsigned Struck(Player* player)"):combat.index("            void Impact()")]
        impact = combat[combat.index("            void Impact()"):]
        impact = impact[:impact.index("            void Register() override")]
        tail = impact[impact.index("                if (!impacted.insert(target->GetGUID().GetRawValue()).second)"):]
        compiler = shutil.which("c++") or shutil.which("g++")
        if not compiler:
            raise unittest.SkipTest("no C++ compiler")
        power_math.SCRATCH.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="gavel-impact-", dir=str(power_math.SCRATCH)))
        try:
            (work / "impact.cpp").write_text(self.IMPACT_HARNESS.replace("@STRUCK@", struck).replace("@TAIL@", tail), encoding="utf-8")
            built = subprocess.run([compiler, "-std=c++17", str(work / "impact.cpp"), "-o", str(work / "impact")],
                                   capture_output=True, text=True)
            self.assertEqual(0, built.returncode, built.stderr[-3000:])
            run = harness_env.run([str(work / "impact")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return run.stdout.strip()
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_enemy_the_first_hit_kills_still_counts(self):
        self.assertEqual("1 4 3", self.impact(self.combat))

    def test_the_kill_count_mutant_fails(self):
        # the count taken after the hit, as at 679cffdc: the killed target drops out (0 and 3)
        old = "Connected(player, shell.spellId, struck);"
        self.assertEqual(1, self.combat.count(old))
        self.assertNotEqual("1 4 3", self.impact(self.combat.replace(old, "Connected(player, shell.spellId, Struck(player));")))

    def test_the_refund_is_the_classs_primary_resource(self):
        fire = self.powers[self.powers.index("void Fire(Player* player, char const* event"):self.powers.index("constexpr std::uint32_t ImmuneKey")]
        self.assertIn('else if (one.stat == "resource_refund")\n                {\n                    if (Resources::Resource const* resource = '
                      'Resources::Of(Classes::ClassIdOf(player)))\n                        Resources::Add(player, *resource, one.value);\n                }', fire)


if __name__ == "__main__":
    unittest.main()
