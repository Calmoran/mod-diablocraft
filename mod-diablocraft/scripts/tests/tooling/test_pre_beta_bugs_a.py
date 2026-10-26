"""diablocraft-pre-beta-bugs-a: GitHub #61, #49, #47 and #56, executed.

Each check reads what the generators emitted or compiles the real function cut
out of the module source; none of them restates a number by hand.

  #61  Every class's gear-and-paragon cost and cooldown aura is a SPELLMOD in
       that class's own family whose mask covers every one of its skills, so
       it reaches each priced and timed record the class casts. Both classes
       are checked, and the pre-fix shape (the Barbarian's family-20 record
       alone) must fail the same check for the Wizard.
  #49  Nothing in the module hands the core an epoch time as a cooldown.
  #47  PrimaryStat, ClassKey, StatAffix and ResolveMainStats are compiled and
       fed the generated class and base-item tables: every designated class
       resolves from the sheet, a Dexterity class rolls Dexterity, and a class
       with no row resolves to nothing rather than Strength.
  #56  RollValue is compiled and rolled over every row of the new affix pool
       migration: the glove crit row reaches 8.5 and 9.5, every roll sits on
       its row's grid, and every value_step equals the step d3planner's
       slots.js gives that row.
"""
import csv
import hashlib
import importlib.util
import io
import re
import shutil
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import items_source  # noqa: E402
import harness_env
from class_names import sheet_stem  # noqa: E402
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
MODULE = REPO_ROOT / "mod-diablocraft"
SCRIPTS = MODULE / "scripts"
D3 = MODULE / "data" / "d3"
GENERATED = MODULE / "data" / "generated"
UPDATES = MODULE / "data" / "sql" / "db-world" / "updates"
CORE = REPO_ROOT / "azerothcore-wotlk"
SLOTS_JS = REPO_ROOT / "reference" / "d3planner" / "slots.js"
SCRATCH = CORE / "build" / "_agent-scratch" / "pre_beta_bugs_a"
ITEMS = items_source.source()
ITEMS_H = (MODULE / "src" / "items" / "dc_items.h").read_text(encoding="utf-8")
POOL_MIGRATION = UPDATES / "items_0008_affix_pool_step.sql"

sys.path.insert(0, str(SCRIPTS))
from test_cost_math import generated_records  # noqa: E402

SPELL_EFFECT_APPLY_AURA = "6"
SPELL_AURA_ADD_PCT_MODIFIER = "108"
SPELLMOD_COOLDOWN, SPELLMOD_COST = "11", "14"


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def load_generator():
    spec = importlib.util.spec_from_file_location("generate_spells", SCRIPTS / "generate/classes/generate_spells.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def definition(marker, source):
    """One definition, braces balanced, exactly as the module has it."""
    assert source.count(marker) == 1, "%r is not unique" % marker
    start = source.index(marker)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    if source[end:end + 1] == ";":
        end += 1
    return source[start:end]


def sql_rows(path, table):
    """[{column: value}] for every row a generated INSERT into `table` carries."""
    text = path.read_text(encoding="utf-8")
    rows = []
    for columns, body in re.findall(r"INSERT INTO `%s` \(([^)]*)\) VALUES\n(.*?);\n" % table, text, re.S):
        names = [name.strip(" `") for name in columns.split(",")]
        for line in body.split("\n"):
            line = line.rstrip(",")
            cells = next(csv.reader([line[1:-1]], quotechar="'", skipinitialspace=True))
            rows.append(dict(zip(names, cells)))
    return rows


def compile_harness(name, source):
    compiler = shutil.which("c++") or shutil.which("g++")
    if not compiler:
        raise unittest.SkipTest("no C++ compiler")
    SCRATCH.mkdir(parents=True, exist_ok=True)
    (SCRATCH / (name + ".cpp")).write_text(source, encoding="utf-8")
    binary = SCRATCH / name
    built = subprocess.run([compiler, "-std=c++17", "-O1", "-UNDEBUG", str(SCRATCH / (name + ".cpp")),
                            "-o", str(binary)], capture_output=True, text=True)
    if built.returncode:
        raise AssertionError("%s did not compile:\n%s" % (name, built.stderr[-6000:]))
    return binary


# --- #61 ---------------------------------------------------------------------

def is_affected(family, mask, record):
    """SpellInfo::IsAffected at the pin, for a modifier record's family and
    EffectSpellClassMaskA and a target record's own family and mask word one
    (the only word our records use). test_the_core_still_matches_by_family
    holds the core to this."""
    if not family:
        return True
    if family != int(record["SpellClassSet"]):
        return False
    return not mask or bool(mask & int(record["SpellClassMask_1"]))


class GearModifiersEveryClass(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gen = load_generator()
        cls.records = generated_records()
        cls.manifest = {int(row["spell_id"]): row for row in read_csv(GENERATED / "spell_shells.csv")}
        header = (MODULE / "src" / "combat" / "dc_spell_shells.h").read_text(encoding="utf-8")
        table = header.split("inline constexpr GearModifier GearModifiers[] = {")[1].split("};")[0]
        cls.gear = {int(m[0]): tuple(int(v) for v in m[1:])
                    for m in re.findall(r"\{(\d+), (\d+), (\d+), (\d+), (\d+)\}", table)}
        # The classes with generated records: blocks and skill sheets, as the generator's own count.
        cls.classes = [row for row in read_csv(D3 / "class_map.csv")
                       if sheet_stem(row["d3_class"]) in cls.gen.CLASS_BLOCKS
                       and (D3 / ("%s_skills.csv" % sheet_stem(row["d3_class"]))).is_file()]

    def skills_of(self, stem):
        """The class's own active and rune records: what a gear reduction is for."""
        first, last = self.gen.CLASS_BLOCKS[stem].records
        return [identifier for identifier, row in self.manifest.items()
                if first <= identifier <= last and row["kind"] in ("active", "rune", "archon")]

    def unreached(self, stem, modifier_ids):
        """(id, what) for each priced or timed record of the class none of the
        given modifiers reaches. Empty is the acceptance."""
        missing = []
        for identifier in self.skills_of(stem):
            record = self.records[identifier]
            timed = int(record["RecoveryTime"]) or int(record["CategoryRecoveryTime"])
            for need, wanted in (("cost", int(record["ManaCost"]) > 0), ("cooldown", timed > 0)):
                if not wanted:
                    continue
                reached = False
                for modifier in modifier_ids:
                    aura = self.records[modifier]
                    op = SPELLMOD_COST if need == "cost" else SPELLMOD_COOLDOWN
                    if aura["EffectMiscValue_1"] == op and is_affected(
                            int(aura["SpellClassSet"]), int(aura["EffectSpellClassMaskA_1"]), record):
                        reached = True
                if not reached:
                    missing.append((identifier, need))
        return missing

    def test_every_generated_class_has_a_gear_row(self):
        self.assertEqual(sorted(self.gear), sorted(int(row["class_id"]) for row in self.classes))
        self.assertGreaterEqual(len(self.gear), 2, "both classes, not one")

    def test_the_barbarian_keeps_its_records_and_probes(self):
        # 82403/82406 and the probes 81005/81010 are what the module used
        # before #61; the Barbarian's behaviour does not move.
        self.assertEqual(self.gear[1], (82403, 81005, 82406, 81010))
        for identifier in (82403, 82406):
            self.assertEqual(self.records[identifier]["SpellClassSet"], "20")

    def test_each_record_is_its_classes_hidden_percentage_modifier(self):
        for row in self.classes:
            stem = sheet_stem(row["d3_class"])
            cost, cost_probe, cooldown, cooldown_probe = self.gear[int(row["class_id"])]
            family = self.gen.CLASS_BLOCKS[stem].family
            every = 0
            for identifier in self.skills_of(stem):
                every |= int(self.records[identifier]["SpellClassMask_1"])
            for identifier, op in ((cost, SPELLMOD_COST), (cooldown, SPELLMOD_COOLDOWN)):
                with self.subTest(cls=stem, record=identifier):
                    record = self.records[identifier]
                    self.assertEqual(record["Effect_1"], SPELL_EFFECT_APPLY_AURA)
                    self.assertEqual(record["EffectAura_1"], SPELL_AURA_ADD_PCT_MODIFIER)
                    self.assertEqual(record["EffectMiscValue_1"], op)
                    self.assertEqual(record["EffectBasePoints_1"], "0", "the gear amount is cast in")
                    self.assertEqual(record["EffectDieSides_1"], "0")
                    self.assertEqual(int(record["SpellClassSet"]), family, "not the class's family")
                    self.assertEqual(int(record["EffectSpellClassMaskA_1"]), every,
                                     "the mask is not every one of the class's skills")
            for probe, field in ((cost_probe, "ManaCost"), (cooldown_probe, "RecoveryTime")):
                with self.subTest(cls=stem, probe=probe):
                    self.assertIn(probe, self.skills_of(stem), "the probe is not the class's own record")
                    self.assertGreater(int(self.records[probe][field]), 0)

    def test_every_priced_and_timed_record_of_both_classes_is_reached(self):
        for row in self.classes:
            stem = sheet_stem(row["d3_class"])
            cost, cost_probe, cooldown, cooldown_probe = self.gear[int(row["class_id"])]
            with self.subTest(cls=stem):
                self.assertEqual(self.unreached(stem, (cost, cooldown)), [])
                # and the probes the sheet is measured on are reached too
                self.assertTrue(is_affected(int(self.records[cost]["SpellClassSet"]),
                                            int(self.records[cost]["EffectSpellClassMaskA_1"]),
                                            self.records[cost_probe]))
                self.assertTrue(is_affected(int(self.records[cooldown]["SpellClassSet"]),
                                            int(self.records[cooldown]["EffectSpellClassMaskA_1"]),
                                            self.records[cooldown_probe]))
        self.assertGreater(len(self.skills_of("wizard")), 0)

    def test_the_pre_fix_shape_fails_for_the_wizard(self):
        """#61 itself: the Barbarian's family-20 pair reaches no Wizard record."""
        missing = self.unreached("wizard", (82403, 82406))
        priced = [identifier for identifier, need in missing if need == "cost"]
        timed = [identifier for identifier, need in missing if need == "cooldown"]
        self.assertTrue(priced and timed, "the check cannot see the bug it is for")

    def test_the_core_still_matches_by_family(self):
        source = (CORE / "src" / "server" / "game" / "Spells" / "SpellInfo.cpp").read_text(encoding="utf-8")
        body = definition("bool SpellInfo::IsAffected(uint32 familyName, flag96 const& familyFlags) const", source)
        compact = re.sub(r"\s+", " ", body)
        for clause in ("if (!familyName) return true;",
                       "if (familyName != SpellFamilyName) return false;",
                       "if (familyFlags && !(familyFlags & SpellFamilyFlags)) return false;"):
            self.assertIn(clause, compact)

    def test_the_module_looks_the_pair_up_by_class(self):
        passives = (MODULE / "src" / "combat" / "dc_passives.cpp").read_text(encoding="utf-8")
        refresh = definition("void RefreshModifiers(Player* p)", passives)
        self.assertIn("Shells::GearModifierFor(Classes::ClassIdOf(p))", refresh)
        self.assertIn("gear->costProbe", refresh)
        self.assertIn("gear->cooldownProbe", refresh)
        self.assertNotIn("gear and paragon", refresh, "a class-specific owner name is back")
        generator = (SCRIPTS / "generate/classes/generate_spells.py").read_text(encoding="utf-8")
        generic = generator.split("# --- every other class: the generic pass")[1].split(
            "current[\"stem\"] = \"barbarian\"")[0]
        self.assertIn("GEAR_COST_MODIFIER", generic, "the generic class pass builds no gear records")
        self.assertIn("block.family", generic)


# --- #49 ---------------------------------------------------------------------

class CooldownsAreRelativeMilliseconds(unittest.TestCase):
    def test_no_module_cooldown_is_an_epoch_time(self):
        calls = []
        for path in sorted((MODULE / "src").rglob("*.cpp")):
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(r"AddSpellCooldown\(", text):
                depth, end = 1, match.end()
                while depth:
                    depth += (text[end] == "(") - (text[end] == ")")
                    end += 1
                calls.append((path.name, text[match.end():end - 1]))
        self.assertGreaterEqual(len(calls), 2)
        for name, arguments in calls:
            with self.subTest(file=name, call=arguments):
                self.assertNotIn("time(", arguments, "an epoch time is not a duration")

    def test_nerves_of_steel_passes_its_sheet_seconds_as_milliseconds(self):
        passives = (MODULE / "src" / "classes" / "barbarian" / "dc_barbarian_passives.cpp").read_text(encoding="utf-8")
        fatal = definition("void Fatal(Player* p, uint32& damage)", passives)
        self.assertIn('Numbers::Num(r->id, "internal_cooldown_seconds") * 1000', re.sub(r"\s+", " ", fatal))
        row = next(r for r in read_csv(D3 / "barbarian_passive_values.csv")
                   if r["skill"] == "Nerves of Steel" and r["token"] == "internal_cooldown_seconds")
        self.assertEqual(float(row["value"]), 60.0, "the sheet's internal cooldown moved")

    def test_the_core_still_takes_a_relative_duration(self):
        source = (CORE / "src" / "server" / "game" / "Entities" / "Player" / "Player.cpp").read_text(encoding="utf-8")
        body = definition("void Player::_AddSpellCooldown(", source)
        self.assertIn("sc.end = GameTime::GetGameTimeMS().count() + end_time;", body)


# --- #47 ---------------------------------------------------------------------

MAIN_STAT_HARNESS = r"""
#include <cctype>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <set>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>
static int logged = 0;
#define LOG_ERROR(...) (++logged)
%(extract)s
int main(int argc, char** argv)
{
    // argv[1]: class<TAB>primary_stat rows; argv[2]: entry<TAB>designated_class
    // rows; argv[3]: the class to drop from the sheet, or "-".
    std::unordered_map<std::string, std::string> mainStats;
    std::ifstream classes(argv[1]);
    std::string line;
    std::string const dropped = argv[3];
    while (std::getline(classes, line))
    {
        auto tab = line.find('\t');
        std::string const name = line.substr(0, tab), stat = line.substr(tab + 1);
        if (name != dropped && !StatAffix(stat).empty())
            mainStats[ClassKey(name)] = StatAffix(stat);
    }
    std::unordered_map<std::uint32_t, BaseItem> items;
    std::ifstream bases(argv[2]);
    while (std::getline(bases, line))
    {
        auto tab = line.find('\t');
        BaseItem base;
        base.entry = std::stoul(line.substr(0, tab));
        base.designatedClass = line.substr(tab + 1);
        items.emplace(base.entry, base);
    }
    auto unknown = ResolveMainStats(items, mainStats);
    std::unordered_map<std::string, std::set<std::string>> byClass;
    unsigned designated = 0, rolled = 0;
    for (auto const& [entry, base] : items)
    {
        if (base.designatedClass.empty())
            continue;
        ++designated;
        // diablocraft-class-roll-rules: whatever class the roll names, a
        // designated item keeps its own class's main stat.
        std::string const stat = PrimaryStat(base, "no-such-roll-class", mainStats);
        if (!stat.empty())
            ++rolled;
        byClass[base.designatedClass].insert(stat.empty() ? "-" : stat);
    }
    std::cout << "designated=" << designated << " rolled=" << rolled << " unknown=" << unknown.size()
              << " logged=" << logged << "\n";
    for (auto const& [cls, stats] : byClass)
        for (auto const& stat : stats)
            std::cout << "class " << cls << " " << stat << "\n";
    // An undesignated item takes the main stat of the class it rolls for.
    BaseItem plain;
    for (char const* stat : {"Strength", "Intelligence", "Dexterity", ""})
    {
        std::unordered_map<std::string, std::string> rollClass;
        if (*stat)
            rollClass["roll"] = StatAffix(stat);
        int const before = logged;
        std::cout << "player " << (*stat ? stat : "none") << " " << PrimaryStat(plain, "roll", rollClass)
                  << " logged=" << (logged - before) << "\n";
    }
    return 0;
}
"""


class MainStatFromTheSheet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        extract = "\n\n".join([
            definition("struct BaseItem\n{", items_source.header()),
            definition("std::string ClassKey(std::string const& d3Class)", ITEMS),
            definition("std::string StatAffix(std::string const& stat)", ITEMS),
            definition("std::set<std::string> ResolveMainStats(", ITEMS),
            definition("std::string PrimaryStat(BaseItem const& base, std::string const& affixClass,", ITEMS),
        ])
        cls.binary = compile_harness("main_stat_harness", MAIN_STAT_HARNESS % {"extract": extract})
        # What the server loads: the generated tables, not the sheets.
        cls.sheet = sql_rows(GENERATED / "class_primary_stats.sql", "dc_class_primary_stats")
        bases = sql_rows(GENERATED / "base_items.sql", "dc_base_item")
        (SCRATCH / "classes.tsv").write_text(
            "".join("%s\t%s\n" % (row["class"], row["primary_stat"]) for row in cls.sheet), encoding="utf-8")
        (SCRATCH / "bases.tsv").write_text(
            "".join("%s\t%s\n" % (row["entry"], row["designated_class"]) for row in bases), encoding="utf-8")
        cls.designated = sum(1 for row in bases if row["designated_class"])

    def run_with(self, dropped="-"):
        run = harness_env.run([str(self.binary), str(SCRATCH / "classes.tsv"), str(SCRATCH / "bases.tsv"), dropped],
                             capture_output=True, text=True, check=True)
        return run.stdout

    def test_every_designated_class_resolves_from_the_sheet(self):
        out = self.run_with()
        self.assertIn("designated=%d rolled=%d unknown=0 logged=0" % (self.designated, self.designated), out)
        wanted = {"Strength": "str", "Dexterity": "dex", "Intelligence": "int"}
        for row in self.sheet:
            key = row["class"].lower().replace(" ", "")
            if "class %s " % key in out:
                self.assertIn("class %s %s\n" % (key, wanted[row["primary_stat"]]), out)
        # the two Dexterity classes the old fallback turned into Strength
        self.assertIn("class monk dex\n", out)
        self.assertIn("class demonhunter dex\n", out)

    def test_a_class_with_no_row_rolls_nothing_and_is_logged(self):
        out = self.run_with("Monk")
        self.assertIn("unknown=1", out)
        self.assertIn("class monk -\n", out)
        self.assertNotIn("class monk str", out, "a missing row became a silent Strength")
        self.assertRegex(out, r"logged=[1-9]")

    def test_an_undesignated_item_takes_the_players_class(self):
        out = self.run_with()
        self.assertIn("player Strength str logged=0", out)
        self.assertIn("player Intelligence int logged=0", out)
        self.assertIn("player Dexterity dex logged=0", out)
        self.assertIn("player none  logged=1", out, "no class row must log and roll nothing")

    def test_every_playable_class_main_stat_has_an_affix(self):
        stats = {row["primary_stat"] for row in read_csv(D3 / "class_map.csv")}
        self.assertLessEqual(stats, {"Strength", "Dexterity", "Intelligence"})

    def test_no_class_is_named_in_the_items_code(self):
        body = definition("std::string PrimaryStat(BaseItem const& base, std::string const& affixClass,", ITEMS)
        for name in ("CLASS_", "wizard", "barbarian", "monk", "demonhunter", "\"str\""):
            self.assertNotIn(name, body)
        self.assertNotIn("CLASS_MAGE", ITEMS)
        self.assertNotIn("CLASS_WARLOCK", ITEMS)


# --- #56 ---------------------------------------------------------------------

ROLL_HARNESS = r"""
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <random>
#include <set>
#include <sstream>
#include <string>
std::mt19937_64& Engine() { static std::mt19937_64 engine{20260923}; return engine; }
%(extract)s
int main(int argc, char** argv)
{
    // argv[1]: line<TAB>min<TAB>max<TAB>step rows; argv[2]: rolls per row;
    // argv[3]: "nostep" drops every step (the pre-fix roller's view).
    std::ifstream rows(argv[1]);
    int const rolls = std::stoi(argv[2]);
    bool const noStep = argc > 3 && std::string(argv[3]) == "nostep";
    std::string line;
    while (std::getline(rows, line))
    {
        std::istringstream in(line);
        std::string id;
        PoolEntry entry;
        in >> id >> entry.min >> entry.max >> entry.step;
        if (noStep)
            entry.step = 0;
        std::set<double> seen;
        double low = 1e300, high = -1e300;
        for (int i = 0; i < rolls; ++i)
        {
            double const value = RollValue(entry);
            seen.insert(value);
            low = std::min(low, value);
            high = std::max(high, value);
        }
        std::cout << id << " " << low << " " << high << " " << seen.size();
        for (double value : seen)
            std::cout << " " << value;
        std::cout << "\n";
    }
    return 0;
}
"""


def slots_steps():
    """{(slot, affix_id, bracket): (step or None, slots.js line of the limit)}
    from d3planner's slots.js: the slot's affix names a statLimits key, and
    the bracket's entry for that key may carry a step. Rare and ancient take
    legendary's keys they lack and primal is ancient (the IIFE at the end of
    statLimits)."""
    lines = SLOTS_JS.read_text(encoding="utf-8").splitlines()
    limits, slots = {}, {}
    section = block = None
    for number, line in enumerate(lines, 1):
        if line.startswith("DiabloCalc.statLimits"):
            section = "limits"
            continue
        if line.startswith("DiabloCalc.itemSlots") or line.startswith("DiabloCalc.metaSlots"):
            section = "slots"
            continue
        if line.startswith("DiabloCalc.") or line.startswith("(function"):
            section = None
            continue
        head = re.match(r"^  (\w+): \{", line)
        if head:
            block = head[1]
            continue
        if section == "limits":
            m = re.match(r"^\s+(\w+): \{(.*)\},", line)
            if m:
                limits.setdefault(block, {})[m[1]] = (dict(re.findall(r"(\w+): ([^,}]+)", m[2])), number)
        elif section == "slots":
            m = re.match(r'^\s{6}(\w+): "(\w+)",', line)
            if m:
                slots.setdefault(block, {}).setdefault(m[1], m[2])
    for bracket in ("ancient", "rare"):
        for key, value in limits["legendary"].items():
            limits[bracket].setdefault(key, value)
    limits["primal"] = dict(limits["ancient"])
    out = {}
    for slot, affixes in slots.items():
        for affix, key in affixes.items():
            for bracket in ("rare", "legendary", "ancient", "primal"):
                fields, number = limits[bracket].get(key, ({}, None))
                out[(slot, affix, bracket)] = (fields.get("step"), number, fields)
    return out


def newest_pool_migration():
    """The newest migration that recreates dc_affix_pool whole.

    Each pool migration is a generated DROP + CREATE + INSERT of the whole
    table, so the highest-numbered one is what the server loads last and the
    generator's output must equal it."""
    recreates = "DROP TABLE IF EXISTS `dc_affix_pool`"
    hits = [path for path in sorted(UPDATES.glob("items_*.sql"))
            if recreates in path.read_text(encoding="utf-8")]
    assert hits, "no migration recreates dc_affix_pool"
    return hits[-1]


class RollsOnTheSourcedStep(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        extract = "\n\n".join([definition("struct PoolEntry\n{", ITEMS_H),
                               definition("double RollValue(PoolEntry const& entry)", ITEMS)])
        cls.binary = compile_harness("roll_harness", ROLL_HARNESS % {"extract": extract})
        # What the server loads: the new migration's rows.
        cls.rows = sql_rows(POOL_MIGRATION, "dc_affix_pool")
        path = SCRATCH / "pool.tsv"
        path.write_text("".join("%d\t%s\t%s\t%s\n" % (index, row["value_min"], row["value_max"],
                                                       "0" if row["value_step"] == "NULL" else row["value_step"])
                                for index, row in enumerate(cls.rows)), encoding="utf-8")
        cls.results = cls.roll(path, 20000)
        cls.before = cls.roll(path, 20000, "nostep")

    @classmethod
    def roll(cls, path, count, mode=""):
        run = harness_env.run([str(cls.binary), str(path), str(count)] + ([mode] if mode else []),
                             capture_output=True, text=True, check=True)
        out = {}
        for line in run.stdout.splitlines():
            cells = line.split()
            out[int(cells[0])] = (float(cells[1]), float(cells[2]), [float(v) for v in cells[4:]])
        return out

    def index(self, slot, affix, bracket):
        return next(i for i, row in enumerate(self.rows)
                    if (row["slot"], row["affix_id"], row["item_level_bracket"]) == (slot, affix, bracket))

    def test_glove_crit_reaches_the_half_percents(self):
        values = self.results[self.index("hands", "chc", "rare")][2]
        self.assertEqual(values, [8.0, 8.5, 9.0, 9.5, 10.0])

    def test_the_pre_fix_roller_cannot(self):
        values = self.before[self.index("hands", "chc", "rare")][2]
        self.assertNotIn(8.5, values)
        self.assertNotIn(9.5, values)

    def test_every_roll_is_in_range_and_on_its_grid(self):
        stepped = 0
        for index, row in enumerate(self.rows):
            low, high, values = self.results[index]
            lo, hi = float(row["value_min"]), float(row["value_max"])
            with self.subTest(row=(row["slot"], row["affix_id"], row["item_level_bracket"])):
                self.assertGreaterEqual(low, lo)
                self.assertLessEqual(high, hi)
                if row["value_step"] == "NULL":
                    # no step in the source: today's behaviour, unchanged
                    self.assertEqual(values, self.before[index][2])
                    continue
                stepped += 1
                step = float(row["value_step"])
                count = round((hi - lo) / step)
                self.assertAlmostEqual((hi - lo) / step, count, places=9, msg="the step does not divide the range")
                grid = [round(lo + k * step, 6) for k in range(count + 1)]
                self.assertEqual([round(v, 6) for v in values], grid, "not every step is reachable")
        self.assertEqual(stepped, 68)

    def test_every_step_is_the_one_slots_js_gives(self):
        source = slots_steps()
        sheet = read_csv(D3 / "affix_pools.csv")
        found = not_found = 0
        for row in sheet:
            key = (row["slot"], row["affix_id"], row["item_level_bracket"])
            step, _line, fields = source.get(key, (None, None, {}))
            with self.subTest(row=key):
                if step is None:
                    self.assertEqual(row["value_step"], "", "a step with no source")
                    not_found += 1
                    continue
                found += 1
                self.assertEqual(float(row["value_step"]), float(step))
                self.assertEqual(float(row["value_min"]), float(fields["min"]))
                self.assertEqual(float(row["value_max"]), float(fields["max"]))
        # 68 rows carry a step from slots.js; the other 1032 have none. The 112 weapon rows G1
        # added (diablocraft-weapon-elemental-build) are exactly the difference: d3planner's
        # onehand/twohand affix maps list damage/weaponias/edmg, never wpnphy..wpnhol, so the
        # weapon damage rows name no statLimits key and get no step. Their roll is the weapon's
        # own two-part damage bracket (slots.js damage1HNormal/damage1HFast/damage2H), which is
        # why value_step is empty for them; the check above still holds them to that empty step.
        # The 4 offhand wpnphy rows (slots.js damageOffhand, a required line with no step) make 1036,
        # and the 4 offhand ias rows (slots.js iasQuiver, the same) 1040.
        self.assertEqual((found, not_found), (68, 1040))

    def test_the_applied_pool_migration_is_frozen_and_the_step_is_new(self):
        frozen = (UPDATES / "0002_dc_affix_pool.sql").read_text(encoding="utf-8")
        self.assertNotIn("value_step", frozen)
        # items_0008 was the first pool migration to carry value_step and is applied, so it stays
        # byte-frozen: sha256 of its committed content at 42775b42. The generator now emits a NEW
        # migration for a changed pool (items_0016, the weapon brackets); a rerun must never
        # rewrite the applied one.
        self.assertEqual(hashlib.sha256(POOL_MIGRATION.read_bytes()).hexdigest(),
                         "489fe7af95956ccb9b56cc53139f36f925ac45d20943bdeeb81374b3672b1a4f")
        self.assertIn("`value_step`", POOL_MIGRATION.read_text(encoding="utf-8"))
        # The generated mirror is the newest pool migration, whichever number that is.
        self.assertEqual(newest_pool_migration().read_bytes(),
                         (GENERATED / "affix_pools.sql").read_bytes())
        # The server reads the step out of the pool; G1 added the weapon columns
        # (value_min2, value_max2, weapon_class) to the same SELECT, so match the column
        # before FROM rather than the whole list.
        self.assertRegex(ITEMS, r"value_step\b[^)]*FROM dc_affix_pool")


if __name__ == "__main__":
    unittest.main(verbosity=2)
