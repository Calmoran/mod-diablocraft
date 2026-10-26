"""diablocraft-class-roll-rules - class-aware loot and Mystic rolls, executed.

What this suite proves, and what it does not:

  * The **rules** are the production header `src/items/dc_roll_class.h`,
    compiled into `scripts/tests/loot/roll_class_tests.cpp` and driven with what
    the generators emit: the class map, the droppable bases, the skill-affix rows
    of the skill-affix classes migration (items_0012, then items_0029 for the Monk, items_0049 for the Necromancer and the Crusader, items_0052 for the Demon Hunter, items_0055 for the Witch Doctor, items_0062 for the Shaman) and the `loot/smart_loot_off_class_pct` tunable. Never a literal.
  * Every rule has a **mutation** that must turn the harness red.
  * The **wiring** - that dc_loot.cpp, the dc_items*.cpp files and dc_identify.cpp call
    those functions and carry the roll class through - is checked by reading the
    code with comments removed. It is not executed: that needs a Player and is
    the GM script in docs/test-class-roll-rules.md.
  * The **skill-affix migration** is replayed in SQLite on top of items_0004's
    rows. The characters migration (loot_0007) uses information_schema and
    PREPARE, so it is checked as text only; it has not been run against MySQL.
"""
import csv
import pathlib
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import items_source  # noqa: E402
from class_names import item_key  # noqa: E402
import harness_env
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import applied_migrations
import generate_skill_affixes as affixes

MODULE = pathlib.Path(__file__).resolve().parents[3]
ROOT = MODULE.parent
SRC = MODULE / "src"
HEADER = SRC / "items" / "dc_roll_class.h"
HARNESS = MODULE / "scripts" / "tests/loot" / "roll_class_tests.cpp"
GENERATED = MODULE / "data" / "generated"
WORLD = MODULE / "data" / "sql" / "db-world" / "updates"
CHARACTERS = MODULE / "data" / "sql" / "db-characters" / "updates"
CLASSES_SQL = WORLD / affixes.CLASSES_MIGRATION
ROLL_CLASS_SQL = CHARACTERS / "loot_0007_roll_class.sql"
SCRATCH = harness_env.private_scratch(ROOT / "azerothcore-wotlk" / "build" / "_agent-scratch" / "class_roll_rules")


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


def skill_rows(path):
    """(group, index, affix, class_id) from a dc_skill_affix REPLACE."""
    return [(g, int(i), a, int(c)) for g, i, a, c in
            re.findall(r"^\('([^']*)',(\d+),'([^']*)',(\d+),", path.read_text(encoding="utf-8"), re.M)]


def code(path):
    """Source with comments removed, so prose cannot satisfy a wiring check."""
    return code_text(path.read_text(encoding="utf-8"))


def code_text(text):
    lines = []
    for line in text.splitlines():
        if line.strip().startswith("//") or line.strip().startswith("*") or line.strip().startswith("/*"):
            continue
        lines.append(line.split("//")[0])
    return "\n".join(lines)


def off_class_pct():
    match = re.search(r"\('loot', 'smart_loot_off_class_pct', ([0-9.]+|NULL), ([0-9.]+|NULL),",
                      (GENERATED / "tunables_0003.sql").read_text(encoding="utf-8"))
    d3_value, tuned = match.groups()
    return tuned if tuned != "NULL" else d3_value


PLANNER_SETS = ROOT / "reference" / "d3planner" / "data_itemsets.js"


def planner_set_classes():
    """{set name: class key or ''} from the D3Planner set data (`class:` on the newer sets,
    `tclass:` on the older ones, none on a classless set such as Cain's Destiny). This is the
    source the drop class is taken from, read here independently of every generated column."""
    sets, current = {}, None
    for line in PLANNER_SETS.read_text(encoding="utf-8").splitlines():
        if re.match(r"^  \w+: \{$", line):
            current = None
            continue
        match = re.match(r'^    name: "(.*)",$', line)
        if match:
            current = match.group(1).replace("\\u2019", "'").replace("\u2019", "'")
            sets[current] = ""
            continue
        match = re.match(r'^    t?class: "(\w+)",$', line)
        if match and current is not None:
            sets[current] = match.group(1)
    return sets


def write_inputs():
    SCRATCH.mkdir(parents=True, exist_ok=True)
    classes = sql_rows(GENERATED / "class_catalogue.sql", "dc_class_map")
    (SCRATCH / "classes.tsv").write_text(
        "".join("%s\t%s\n" % (row["class_id"], row["class_key"]) for row in classes), encoding="utf-8")
    # Exactly the rows the loot loader reads (dc_loot.cpp LootWorld).
    planner = planner_set_classes()
    # What the loader joins: the generated dc_set_class, by set_name.
    set_classes = {row["set_name"]: row["class_key"] for row in sql_rows(GENERATED / "set_class.sql", "dc_set_class")} \
        if (GENERATED / "set_class.sql").exists() else {}

    def truth(row):
        """The class D3Planner gives the set a piece belongs to; '' for a classless set or a non-set."""
        if row["rarity"] != "set":
            return ""
        name = row["set_name"].replace("\u2019", "'")
        if name not in planner:
            raise AssertionError("set %r is not in D3Planner's data_itemsets.js" % name)
        return planner[name]

    # Every row: the harness applies the production InDropPool, the filter the loader applies.
    bases = sql_rows(GENERATED / "base_items.sql", "dc_base_item")
    (SCRATCH / "bases.tsv").write_text(
        "".join("%s\t%s\t%s\t%s\t%s\t%s\t%s\n" % (
            row["usable_by"], row["designated_class"], set_classes.get(row["set_name"], ""), row["rarity"], truth(row),
            row["pool_version"], row["craft_only"]) for row in bases), encoding="utf-8")
    (SCRATCH / "skills.tsv").write_text(
        "".join("%s\t%s\t%d\n" % (g, a, c) for g, _i, a, c in skill_rows(CLASSES_SQL)), encoding="utf-8")
    return classes, bases


def build(include_dir, name, strict=True):
    """strict for the real header; a mutant may leave a parameter unused."""
    compiler = shutil.which("c++") or shutil.which("g++")
    binary = SCRATCH / name
    flags = ["-Wall", "-Wextra", "-Werror"] if strict else []
    built = subprocess.run([compiler, "-std=c++17", "-O1", *flags, "-I", str(include_dir),
                            str(HARNESS), "-o", str(binary)], capture_output=True, text=True)
    if built.returncode:
        raise AssertionError("the harness did not compile:\n" + built.stderr[-6000:])
    return binary


def run(binary):
    return harness_env.run([str(binary), str(SCRATCH / "classes.tsv"), str(SCRATCH / "bases.tsv"),
                           str(SCRATCH / "skills.tsv"), off_class_pct()], capture_output=True, text=True)


# One mutation per rule; each must make the harness fail.
MUTATIONS = [
    ("rule 1: the split ignores the tunable",
     "roll * 100.0 >= offClassPct", "roll * 100.0 >= offClassPct * 2"),
    ("rule 1: the looter's own class joins the off-class pool",
     "!key.empty() && key != looter &&", "!key.empty() &&"),
    ("rule 2: class-only items never drop off-class",
     "(designated.empty() || designated == rollClass)", "designated.empty()"),
    ("rule 2: any class's class-only items drop for any roll class",
     "(designated.empty() || designated == rollClass)", "true"),
    ("rule 2: a class set's pieces drop for every class",
     "return designated.empty() ? setClass : designated;", "return designated;"),
    ("ethereal: an Ethereal may drop",
     'return poolVersion == "yes" && craftOnly != "yes" && rarity != "ethereal";',
     'return poolVersion == "yes" && craftOnly != "yes";'),
    ("ethereal: a crafted set may drop",
     'return poolVersion == "yes" && craftOnly != "yes" && rarity != "ethereal";',
     'return poolVersion == "yes" && rarity != "ethereal";'),
    ("ethereal: a superseded pool version may drop",
     'return poolVersion == "yes" && craftOnly != "yes" && rarity != "ethereal";',
     'return craftOnly != "yes" && rarity != "ethereal";'),
    ("rule 3: a class-only item takes the roll class",
     "return designated.empty() ? rollClass : designated;", "return rollClass;"),
    ("rule 3: skill choices are not filtered by class",
     "if (classId && choice.classId == classId)", "if (classId)"),
    ("rule 4: a shell rolls for the owner rather than its stored class",
     "return stored.empty() ? ownerClass : stored;", "return ownerClass.empty() ? stored : ownerClass;"),
    ("rule 5: the Mystic re-rolls a class-only item for the re-roller",
     "return AffixClass(designated, rerollerClass);", "return rerollerClass;"),
    ("rule 5: the Mystic keeps an ordinary item's old class",
     "return AffixClass(designated, rerollerClass);", "return designated;"),
]


class Rules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (shutil.which("c++") or shutil.which("g++")):
            raise unittest.SkipTest("no C++ compiler")
        cls.classes, cls.bases = write_inputs()
        cls.binary = build(HEADER.parent, "roll_class_tests")

    def test_the_production_header_passes_on_the_generated_data(self):
        result = run(self.binary)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("class roll rules OK", result.stdout)
        print("\n" + result.stdout)

    def test_the_split_is_measured_for_both_classes(self):
        out = run(self.binary).stdout
        keys = [row["class_key"] for row in self.classes]
        self.assertGreaterEqual(len(keys), 2)
        for key in keys:
            self.assertRegex(out, r"rule1 looter=%s own=8[45]\.\d\d%%" % key)

    def test_the_tunable_is_the_generated_fifteen_percent(self):
        self.assertEqual(float(off_class_pct()), 15.0)

    def test_every_mutation_fails(self):
        for label, old, new in MUTATIONS:
            with self.subTest(mutation=label):
                source = HEADER.read_text(encoding="utf-8")
                self.assertEqual(source.count(old), 1, "mutation target moved: " + old)
                folder = SCRATCH / ("mutant_%d" % MUTATIONS.index((label, old, new)))
                folder.mkdir(parents=True, exist_ok=True)
                (folder / "dc_roll_class.h").write_text(source.replace(old, new), encoding="utf-8")
                result = run(build(folder, "mutant", strict=False))
                self.assertNotEqual(result.returncode, 0, label + " was not caught:\n" + result.stdout)


class Wiring(unittest.TestCase):
    """The production paths call the tested functions; comments removed first."""

    loot = code(SRC / "loot" / "dc_loot.cpp") + "\n" + code(SRC / "loot" / "dc_loot_delivery.cpp")   # R4: split
    ground = code(SRC / "loot" / "dc_ground_loot.cpp")
    items = code_text(items_source.source())
    identify = code(SRC / "items" / "dc_identify.cpp")

    def test_rule1_the_drop_picks_a_roll_class_from_the_tunable(self):
        self.assertIn('DC::Tunables::Get("loot", "smart_loot_off_class_pct")', self.loot)
        self.assertIn("DC::RollClass::Pick(d3, playable, offClassPct, Roll(), Roll())", self.loot)
        self.assertNotIn("0.85", self.loot)
        self.assertNotIn("OtherClassItem", self.loot)

    def test_rule1_every_ordinary_drop_goes_through_the_class_pick(self):
        body = self.loot[self.loot.index("Result RollLoot("):]
        body = body[:body.index("\n}\n")]
        self.assertIn("DC::RollClass::Pick(d3, playable, offClassPct, Roll(), Roll())", body)
        self.assertIn("PickBaseItem(rarity, monsterLevel, rollClass, tier)", body)

    def test_the_first_kill_legendary_is_always_the_looters_class(self):
        """The explicit exception (the designer, decisions.md 2026-09-23, superseding
        PM return R3): the act-boss first-kill legendary is 100% the player's
        own class, never 85/15."""
        first = self.loot[self.loot.index("void FirstBossKill("):]
        first = first[:first.index("\n}\n")]
        self.assertIn("std::string const rollClass = D3Class(player);", first)
        self.assertIn("PickBaseItem(Rarity::Legendary, monsterLevel, rollClass, bossTier)", first)
        self.assertNotIn("RollClass::Pick", first)
        self.assertNotIn("offClassPct", first)
        for call in ("DeliverItem(player, base, monsterLevel, Name(Source::Boss), bossTier, rollClass, quality)",
                     "Buffer(player, base, monsterLevel, Name(Source::Boss), bossTier, rollClass, quality)",
                     "deathSource->GetPosition(),rollClass,quality)"):
            self.assertIn(call, first)

    def test_rule2_the_base_is_picked_for_the_roll_class(self):
        self.assertIn("DC::RollClass::DropEligible(item.usable, item.designation, item.setClass, rollClass)", self.loot)
        self.assertNotIn("DC::RollClass::Eligible(", self.loot)
        self.assertIn("PickBaseItem(rarity, monsterLevel, rollClass, tier)", self.loot)

    def test_rule2_the_loader_reads_the_sets_class_for_the_drop_only(self):
        self.assertIn("COALESCE(sc.class_key,'')", self.loot)
        self.assertIn("LEFT JOIN dc_set_class sc ON sc.set_name=b.set_name", self.loot)
        self.assertIn("item.setClass = fields[6].Get<std::string>();", self.loot)
        # diablocraft-set-wear-class (ruling 2026-10-03, q-1003-28: "Lock each piece to its set's
        # class"): the wear rule reads the same sheet. AllowableClass is generated from usable_by,
        # designated_class AND the set's class, through data/d3/set_classes.csv.
        generator = (MODULE / "scripts" / "generate/tooling/generate_sql.py").read_text(encoding="utf-8")
        start = generator.index("def render_set_wear_class")
        rule = generator[start:generator.index("\ndef ", start + 10)]
        self.assertIn("set_classes.csv", rule)
        self.assertIn('row["set_name"]', rule)
        # items_0011 is frozen: its render must not read the set class.
        frozen = generator[generator.index("def render_allowable_class"):generator.index("def render_set_wear_class")]
        self.assertNotIn("set_class", frozen)

    def test_ethereals_are_kept_out_of_the_one_pool_every_source_draws_from(self):
        """diablocraft-ethereal-no-drop. Every source that hands out a base item gets it from
        PickBaseItem, which reads only `generics` and `uniques`, and those are filled in exactly
        one place, behind DC::RollClass::InDropPool. Sources checked (comments removed):
          kills, chests and the rift guardian: RollLoot -> PickBaseItem (dc_loot.cpp),
          the act-boss first-kill legendary: FirstBossKill -> PickBaseItem (dc_loot.cpp),
          the rift guardian's reward: dc_monster_ai.cpp -> DC::Loot::RollLoot (no pick of its own)."""
        self.assertIn("DC::RollClass::InDropPool(rarity, fields[7].Get<std::string>(), fields[8].Get<std::string>(),", self.loot)
        # No query in the loot module may reach dc_base_item rows around that filter: one pool query, and one named existence check
        # (Broken Crown: does the worn helm's base row carry the Crown's id; it returns no row to hand out).
        self.assertEqual(self.loot.count('FROM dc_base_item b "'), 1)
        check = "SELECT 1 FROM dc_base_item WHERE entry={} AND d3_id='{}'"
        self.assertEqual(self.loot.count("FROM dc_base_item"), 2)
        self.assertEqual(self.loot.count(check), 1)
        crown = self.loot[self.loot.index("BrokenCrownGem(Player* player"):]
        crown = crown[:crown.index("\n}\n")]
        self.assertIn('if (!WorldDatabase.Query("' + check + '"', crown)   # only asked whether the row exists, never read for a pick
        self.assertNotIn("dc_base_item", self.ground)
        # Pools: only the loader assigns them, and only from what it filtered.
        self.assertEqual(self.loot.count("generics = std::move("), 1)
        self.assertEqual(self.loot.count("uniques = std::move("), 1)
        self.assertEqual(self.loot.count("PickBaseItem("), 6)   # the definition, the first-kill pick, the roll and its own-class retry, and the gamble's legendary and rare picks (diablocraft-aeo7)
        rift = code(SRC / "monsters" / "dc_monster_ai.cpp")
        self.assertIn("DC::Loot::RollLoot(", rift)
        self.assertNotIn("dc_base_item", rift)
        # Nothing else in the module picks a base from the item sheet by rarity for a reward.
        for name in ("dc_ground_loot.cpp", "dc_corpse_loot.cpp"):
            self.assertNotIn("FROM dc_base_item", code(SRC / "loot" / name))

    def test_rule3_the_roller_uses_one_class_for_main_stat_and_skills(self):
        self.assertIn("DC::RollClass::AffixClass(base.designatedClass,", self.items)
        self.assertIn("SkillChoices(skillGroups, groupId, affixClass)", self.items)
        self.assertIn("PrimaryStat(base, affixClass, mainStats)", self.items)
        self.assertNotIn("PrimaryStatOf", self.items)

    def test_rule4_the_roll_class_travels_with_every_delivery(self):
        for call in ("DeliverItem(player, base, monsterLevel, Name(source), tier, rollClass, quality)",
                     "Buffer(player, base, monsterLevel, Name(source), tier, rollClass, quality)",
                     "DeliverShell(player, base, monsterLevel, shellRarity, shellEntry, Name(source), tier, rollClass, quality)",
                     'DC::Items::StageRoll(player, base, monsterLevel, "", PlayerEconomy::BeginTransaction(), rollClass, quality)',
                     '"rolled",1,dropPosition,rollClass,quality)',
                     "DeliverItem(player,base,level,source.c_str(),tier ? tier : 1,rollClass,DC::Quality::Clean(f[13].Get<std::string>()))"):
            self.assertIn(call, self.loot)
        self.assertEqual(self.loot.count("tier,owner_guid,roll_class,quality_tier)"), 1, "the staged shell INSERT")
        self.assertEqual(self.loot.count("tier, owner_guid, roll_class, quality_tier)"), 1, "the direct shell INSERT")
        self.assertIn("drop_source, tier, roll_class, quality_tier)", self.loot)
        self.assertIn("in_rift,drop_count,roll_class", self.loot)
        self.assertIn("expires_at,roll_class,quality_tier)", self.ground)

    def test_rule4_identify_rolls_the_stored_class(self):
        self.assertIn("DC::RollClass::ShellClass(row->rollClass, ownerClass)", self.identify)
        self.assertIn("row->rarity, transaction, rollClass,", self.identify)  # + row->qualityTier (diablocraft-t3t8)
        self.assertNotIn("getClass", self.identify.replace("(*owner)[0]", ""))
        self.assertIn("owner_guid, roll_class", self.items)

    def test_rule5_the_mystic_uses_the_mystic_class(self):
        # diablocraft-xw2m moved the class into MysticInputs (ctx.mysticClass) and MysticCtx::Expand;
        # EnchantOptions reaches both through Enchant::NewChoices. Whitespace is dropped so a reformat
        # cannot turn it red.
        def body(text, head):
            text = text[text.index(head):]
            return re.sub(r"\s+", "", text[:text.index("\n}\n")] if "\n}\n" in text else text)
        inputs = body(self.items, "bool MysticInputs(")
        self.assertIn("in.ctx.mysticClass=DC::RollClass::MysticClass(base->second.designatedClass,"
                      "player?ClassKeyOfLocked(player->getClass()):std::string());", inputs)
        expand = re.sub(r"\s+", "", self.items[self.items.index("struct MysticCtx"):self.items.index("struct MysticInput\n")])
        self.assertIn("PrimaryStat(*base,mysticClass,classMainStats)", expand)
        self.assertIn("SkillChoices(skillGroups,c.id,mysticClass)", expand)
        options = body(self.items, "std::vector<Affix> EnchantOptions(")
        self.assertIn("MysticInputs(player,instance,in)", options)
        self.assertIn("Enchant::NewChoices(in.pool,*target,in.rows,in.ctx)", options)

    def test_no_class_is_named_in_the_rule_code(self):
        for path in (HEADER, SRC / "loot" / "dc_loot.cpp", SRC / "loot" / "dc_loot_delivery.cpp", SRC / "items" / "dc_identify.cpp"):
            body = code(path).lower()
            for name in ("barbarian", "wizard", "monk", "crusader", "necromancer", "witchdoctor",
                         "demonhunter", "class_warrior", "class_mage"):
                self.assertNotIn(name, body, "%s names %s" % (path.name, name))


class SkillAffixMigration(unittest.TestCase):
    def test_every_playable_class_has_its_own_groups_from_d3planner(self):
        import json
        groups = json.loads((ROOT / "reference/d3planner/data.json").read_text(encoding="utf-8"))["statGroups"]
        rows = skill_rows(CLASSES_SQL)
        keys = {c: k for c, k in affixes.playable_classes()}
        self.assertGreaterEqual(len(keys), 2)
        # A class D3Planner has no groups for takes its groups from its own sheet by D3's slot rule
        # (test_skill_affix_groups.py checks that rule); the Shaman is the one such class so far.
        derived = {key for key in keys.values() if "skill_%s_head" % key not in groups}
        self.assertEqual(derived, {"shaman"})
        for class_id, key in keys.items():
            for slot in affixes.SLOTS:
                if key in derived:
                    want = [affix for affix, _skill in affixes.derived_groups(key, slot)]
                else:
                    want = groups["skill_%s_%s" % (key, slot)]
                got = [a for g, _i, a, c in rows if g == "skill_" + slot and c == class_id]
                self.assertEqual(got, want, "%s %s" % (key, slot))

    def test_the_applied_barbarian_rows_keep_their_group_and_index(self):
        applied = re.findall(r"\('(skill_\w+)','(\d+)','(skill_\w+)'",
                             (WORLD / "items_0004_skill_affixes.sql").read_text(encoding="utf-8"))
        rows = {(g, i, a) for g, i, a, _c in skill_rows(CLASSES_SQL)}
        self.assertEqual(len(applied), 15)
        for group, index, affix in applied:
            self.assertIn((group, int(index), affix), rows)

    def test_reordering_classes_would_move_an_applied_row(self):
        """The mutation for the stable key: Barbarian second shifts its indices."""
        original = affixes.playable_classes
        affixes.playable_classes = lambda: list(reversed(original()))
        try:
            moved = {(g, i, a) for g, i, a, *_ in affixes.definitions()}
        finally:
            affixes.playable_classes = original
        applied = {(g, int(i), a) for g, i, a in re.findall(
            r"\('(skill_\w+)','(\d+)','(skill_\w+)'",
            (WORLD / "items_0004_skill_affixes.sql").read_text(encoding="utf-8"))}
        self.assertFalse(applied <= moved)

    def test_the_migration_replays_over_the_applied_rows(self):
        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE dc_skill_affix (group_id TEXT NOT NULL, choice_index INT NOT NULL, "
                   "affix_id TEXT NOT NULL PRIMARY KEY, class_id INT NOT NULL DEFAULT 0, "
                   "skill_id INT NOT NULL DEFAULT 0, skill_name TEXT NOT NULL, affix_name TEXT NOT NULL, "
                   "UNIQUE (group_id, choice_index))")
        applied = (WORLD / "items_0004_skill_affixes.sql").read_text(encoding="utf-8")
        db.execute(applied[applied.index("REPLACE INTO"):applied.rindex(";")])
        body = CLASSES_SQL.read_text(encoding="utf-8")
        replace = body[body.index("REPLACE INTO"):]
        db.execute(replace[:replace.index(";\n")])
        for _ in range(2):  # a rerun is a no-op
            db.execute(replace[:replace.index(";\n")])
        self.assertEqual(db.execute("SELECT COUNT(*) FROM dc_skill_affix").fetchone()[0], len(skill_rows(CLASSES_SQL)))
        self.assertEqual(db.execute("SELECT COUNT(*) FROM dc_skill_affix WHERE skill_id=0").fetchone()[0], 0)

    def test_regenerating_writes_nothing_new(self):
        paths = [CLASSES_SQL, WORLD / "items_0005_skill_affix_ids.sql",
                 CHARACTERS / "items_0005_resolve_skill_affixes.sql", GENERATED / "skill_affix_classes.sql"]
        before = [path.read_bytes() for path in paths]
        affixes.main()
        self.assertEqual([path.read_bytes() for path in paths], before)
        self.assertEqual((GENERATED / "skill_affix_classes.sql").read_bytes(), CLASSES_SQL.read_bytes())

    def test_no_literal_carries_a_semicolon(self):
        for path in (CLASSES_SQL, ROLL_CLASS_SQL):
            for literal in re.findall(r"'((?:[^']|'')*)'", path.read_text(encoding="utf-8")):
                self.assertNotIn(";", literal, "%s: %s" % (path.name, literal))


class CharactersMigration(unittest.TestCase):
    def test_both_tables_gain_roll_class_idempotently(self):
        body = ROLL_CLASS_SQL.read_text(encoding="utf-8")
        for table in ("dc_item_unidentified", "dc_loot_buffer"):
            self.assertIn("table_name='%s' AND column_name='roll_class'" % table, body)
            self.assertIn("ALTER TABLE %s ADD COLUMN `roll_class` VARCHAR(64) NOT NULL DEFAULT ''''" % table, body)
        self.assertEqual(body.count("IF(@dc_exists=0,"), 2)
        self.assertNotIn("INSERT", body.upper().replace("-- NO DATA ROW", ""))

    def test_the_migrations_meet_the_applied_contract(self):
        """#86: an applied migration is frozen, it is not required to stay
        unapplied. The old assertion checked the manifest for absence and broke
        the day loot_0007 was deployed (2026-09-23). Present, and - once the
        manifest records a hash - still hashing to that hash, is the contract."""
        applied = applied_migrations.load_manifest(MODULE)
        for name, path in (("loot_0007_roll_class.sql", ROLL_CLASS_SQL),
                           (affixes.CLASSES_MIGRATION, CLASSES_SQL)):
            with self.subTest(migration=name):
                self.assertTrue(path.is_file(), "%s is missing" % name)
                key = applied_migrations.manifest_key(MODULE, path)
                if key in applied:
                    self.assertEqual(
                        applied_migrations.sha1(path.read_bytes()), applied[key],
                        "%s has changed since it was applied; ship the change as a new "
                        "migration, the applied file is frozen" % name)


D3 = MODULE / "data" / "d3"


def set_wear_masks(d3_dir):
    """{entry: AllowableClass} as the database ends up: items_0011 (applied, frozen) first, then the
    set-wear migration and the added-classes migration the generator renders from `d3_dir`'s sheets. Entries in neither stay absent."""
    import generate_sql
    body = (WORLD / "items_0011_item_allowable_class.sql").read_text(encoding="utf-8")
    masks = {}
    for mask, entries in re.findall(r"SET `AllowableClass`=(-?\d+) WHERE `entry` IN \(([^)]*)\)", body):
        for entry in entries.split(","):
            masks[int(entry)] = int(mask)
    # The set-wear delta is what the generator emits against the applied items_0011.
    delta, _changed = generate_sql.render_set_wear_class(d3_dir / "base_items.csv", WORLD / "items_0011_item_allowable_class.sql")
    for mask, entries in re.findall(r"SET `AllowableClass`=(-?\d+) WHERE `entry` IN \(([^)]*)\)", delta):
        for entry in entries.split(","):
            masks[int(entry)] = int(mask)
    # The classes added since (the Monk) are one more delta, rendered against the masks so far.
    SCRATCH.mkdir(parents=True, exist_ok=True)
    so_far = SCRATCH / "wear_so_far.sql"
    so_far.write_text("".join("UPDATE `item_template` SET `AllowableClass`=%d WHERE `entry` IN (%d);\n" % (mask, entry)
                              for entry, mask in masks.items()), encoding="utf-8")
    added, _changed = generate_sql.render_added_wear_class(d3_dir / "base_items.csv", [so_far])
    for mask, entries in re.findall(r"SET `AllowableClass`=(-?\d+) WHERE `entry` IN \(([^)]*)\)", added):
        for entry in entries.split(","):
            masks[int(entry)] = int(mask)
    return masks


def set_rows():
    """[(row, wanted_class_key)] for every set piece; the key is D3Planner's, read independently."""
    planner = planner_set_classes()
    with (D3 / "base_items.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = [row for row in csv.DictReader(stream, strict=True) if row["rarity"] == "set"]
    return [(row, planner[row["set_name"].replace("’", "'")]) for row in rows]


def class_bits(d3_dir=D3):
    with (d3_dir / "class_map.csv").open(encoding="utf-8-sig", newline="") as stream:
        return {item_key(row["d3_class"]): 1 << (int(row["wow_class_id"]) - 1)
                for row in csv.DictReader(stream, strict=True)}


def entries_of(d3_dir=D3):
    with (d3_dir / "base_item_ids.csv").open(encoding="utf-8-sig", newline="") as stream:
        return {row["d3_id"]: int(row["item_entry"]) for row in csv.DictReader(stream, strict=True)}


def check_set_pieces_locked(test, masks, d3_dir=D3):
    """Every piece of a classed set is wearable by exactly that class and no other playable one;
    a classless set keeps the base rule (what items_0011 gave it). Returns the classes it saw."""
    bits, entries, seen = class_bits(d3_dir), entries_of(d3_dir), set()
    import generate_sql
    for row, wanted in set_rows():
        entry, mask = entries[row["d3_id"]], masks[entries[row["d3_id"]]]
        if not wanted:
            # The base rule over every playable class (the added-classes delta gives the Monk its bit).
            test.assertEqual(mask, generate_sql.base_wear_mask(row, bits), "%s: a classless set keeps the base rule" % row["d3_name"])
            continue
        seen.add(wanted)
        playable = bits.get(wanted, 0)
        for key, bit in bits.items():
            test.assertEqual(bool(mask & bit), bit == playable and key == wanted,
                             "%s (%s set %s): class %s %s wear it" % (
                                 row["d3_name"], wanted, row["set_name"], key, "may" if mask & bit else "may not"))
        if not playable:
            test.assertEqual(mask, 0, "%s: its class is not playable yet, so nobody wears it" % row["d3_name"])
    return seen


class SetWear(unittest.TestCase):
    """diablocraft-set-wear-class (ruling 2026-10-03, q-1003-28: "Lock each piece to its set's class").
    Every piece of a class set, the plain slots too, is worn only by that set's class. The class is
    the drop fix's key (set_classes.csv -> dc_set_class), never a list in code. The oracle is
    D3Planner's own set data, read independently of every generated column."""

    def test_a_barbarian_is_refused_a_wizard_set_helm_and_wears_a_barbarian_one(self):
        masks, entries, bits = set_wear_masks(D3), entries_of(), class_bits()
        helms = {}
        for row, wanted in set_rows():
            if row["slot"] == "head" and wanted in ("wizard", "barbarian"):
                helms.setdefault(wanted, []).append(masks[entries[row["d3_id"]]])
        self.assertTrue(helms.get("wizard") and helms.get("barbarian"))
        for mask in helms["wizard"]:
            self.assertEqual(mask & bits["barbarian"], 0)
            self.assertNotEqual(mask & bits["wizard"], 0)
        for mask in helms["barbarian"]:
            self.assertNotEqual(mask & bits["barbarian"], 0)
            self.assertEqual(mask & bits["wizard"], 0)

    def test_every_set_piece_wears_by_its_sets_class_only(self):
        seen = check_set_pieces_locked(self, set_wear_masks(D3))
        self.assertEqual(seen, {"barbarian", "crusader", "demonhunter", "monk", "necromancer", "witchdoctor", "wizard"})

    def test_the_generator_reads_the_sheet_not_a_list(self):
        generator = (MODULE / "scripts" / "generate/tooling/generate_sql.py").read_text(encoding="utf-8")
        start = generator.index("def render_set_wear_class")
        body = generator[start:generator.index("\ndef ", start + 10)]
        self.assertIn("set_classes.csv", body)
        for name in ("Wizard", "Barbarian", "wizard", "barbarian", "Tal Rasha", "Zunimassa"):
            self.assertNotIn(name, body)

    def _copy_sheets(self, name):
        target = SCRATCH / name
        shutil.rmtree(target, ignore_errors=True)
        target.mkdir(parents=True)
        for sheet in ("base_items.csv", "base_item_ids.csv", "class_map.csv", "set_classes.csv"):
            shutil.copy(D3 / sheet, target / sheet)
        # The frozen wear renders cover the base items 0002 shipped, found two folders above the sheet.
        applied = SCRATCH / "sql" / "db-world" / "updates"
        applied.mkdir(parents=True, exist_ok=True)
        shutil.copy(WORLD / "0002_dc_base_item.sql", applied / "0002_dc_base_item.sql")
        return target

    def test_mutant_the_lock_dropped_is_caught(self):
        target = self._copy_sheets("set_wear_no_lock")
        with (target / "set_classes.csv").open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        with (target / "set_classes.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["set_name", "class_key", "source"])
            writer.writeheader()
            for row in rows:
                writer.writerow({**row, "class_key": ""})
        with self.assertRaises(AssertionError):
            check_set_pieces_locked(self, set_wear_masks(target), target)

    def test_mutant_the_wrong_class_key_is_caught(self):
        target = self._copy_sheets("set_wear_wrong_key")
        with (target / "set_classes.csv").open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        keys = ["barbarian", "crusader", "demonhunter", "monk", "necromancer", "witchdoctor", "wizard"]
        with (target / "set_classes.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["set_name", "class_key", "source"])
            writer.writeheader()
            for row in rows:
                key = row["class_key"]
                writer.writerow({**row, "class_key": keys[(keys.index(key) + 1) % 7] if key else ""})
        with self.assertRaises(AssertionError):
            check_set_pieces_locked(self, set_wear_masks(target), target)

    def test_the_start_kit_follows_the_same_rule(self):
        world = code(SRC / "common" / "dc_world.cpp")
        self.assertIn("LEFT JOIN dc_set_class", world)
        self.assertIn("setClass", world)

    def test_the_migration_writes_only_allowable_class_on_set_entries(self):
        import generate_sql
        delta, changed = generate_sql.render_set_wear_class(D3 / "base_items.csv", WORLD / "items_0011_item_allowable_class.sql")
        self.assertGreater(changed, 0)
        sets = {entries_of()[row["d3_id"]] for row, _ in set_rows()}
        statements = [line for line in delta.splitlines() if line and not line.startswith("--")]
        self.assertTrue(statements)
        for line in statements:
            self.assertRegex(line, r"^UPDATE `item_template` SET `AllowableClass`=-?\d+ WHERE `entry` IN \([0-9,]+\);$")
            self.assertLessEqual({int(e) for e in re.search(r"\(([0-9,]+)\)", line).group(1).split(",")}, sets)


class WearNotLoot(unittest.TestCase):
    """Rule 2's other half: a class-only item can drop off-class, and the class
    parity mask (items_0011, already applied) is what stops the wrong class
    wearing it. Every single-class base's mask names exactly its class."""

    def test_class_only_bases_wear_masks_exclude_the_other_class(self):
        mask_of = {}
        # items_0011, then items_0028 (the Monk's masks), the newest added-classes delta and the base items added
        # since 0002 (the Shaman's, which carry their own mask), as test_slot_vendors.applied_wear reads them.
        import generate_sql
        for name in ("items_0011_item_allowable_class.sql", "items_0028_item_allowable_class_added.sql",
                     generate_sql.ADDED_WEAR_MIGRATION, generate_sql.ADDED_BASE_MIGRATION):
            body = (WORLD / name).read_text(encoding="utf-8")
            for mask, entries in re.findall(r"SET `AllowableClass`=(-?\d+) WHERE `entry` IN \(([^)]*)\)", body):
                for entry in entries.split(","):
                    mask_of[entry.strip()] = int(mask)
        classes = sql_rows(GENERATED / "class_catalogue.sql", "dc_class_map")
        bits = {row["class_key"]: 1 << (int(row["wow_class_id"]) - 1) for row in classes}
        rows = sql_rows(GENERATED / "base_items.sql", "dc_base_item")
        checked = 0
        for row in rows:
            key = row["designated_class"]
            if key in bits and row["usable_by"] == key:
                self.assertEqual(mask_of[row["entry"]], bits[key], row["d3_id"])
                checked += 1
        self.assertGreater(checked, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
