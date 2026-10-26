#!/usr/bin/env python3
"""Legendary preset codes that rolled and showed but did nothing worn now reach the stat sheet (dc_items_data.cpp Mappings()).

What runs, per code, on the item's own top roll from item_preset_ranges.csv:
  * Mappings(), Applies() and Signed() cut out of dc_items_data.cpp, with Apply's own gate line and value line, compiled
    against the real dc_common.cpp (Calculate, Validate, the sheet save) and the generated class resource registry
    (dc_resource_data.h, read through dc_resources.h's Of()); the worn line's contribution goes through Calculate and
    the sheet is read back:
      basearmor (Thundergod's Vigor) adds to Armor, as stats_full.js:559 does;
      firetaken (Andariel's Visage) multiplies Fire damage taken by 1 + X/100 (stats_full.js:611) and nothing else's;
      maxfury (Girdle of Giants) and maxap (The Swami) add to the resource maximum of the class whose resource is Fury or Arcane
      Power and of no other; maxdisc (Izzuccob, Unique_HandXBow_005_x1) adds to the Demon Hunter's second maximum
      (Stat::MaxSecond, the Discipline pool) and never to the first slot's (Hatred), and to no other class's;
      maxmana (Split Tusk) does nothing on any built class;
      apoc (The Swami), lifefury (Fury of the Vanished Peak), spiritregen (Holy Beacon) and manaregen (Gazing Demise) reach the sheet
      only on the class whose resource the line names, and there Combat's reader (stats/dc_stat_readers.h, compiled in:
      CritResource, LifeForFurySpent, RegenPerSecond) pays the line's own number; manaregen's row lands on the stat
      RegenStatOf reads for "mana";
      damage_beasts (Pig Sticker), damage_demons (Sever), damage_undead (Corrupted Ashbringer) and damage_humans
      (Pig Sticker) reach every class, and MonsterTypeFactor multiplies that kind by 1 + X/100 and no other kind.
    The class a resource line belongs to comes from data_stats.js's own `class:` and class_map.csv, not from the code.
  * single-rule mutants of the gate, the sign and the rows.
Open, named below: maxmana and manaregen wait on the Witch Doctor.
Not covered: the server's equip hook around Apply, the tooltip (unchanged), the hit itself and the callers of the readers
(Combat's tests/stat_readers harness drives those).
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import items_source  # noqa: E402
import csv
import harness_env
import re
import shutil
import subprocess
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[3]
SRC = MODULE / "src"
COMMON = SRC / "common/dc_common.cpp"
RESOURCES = SRC / "classes/dc_resources.h"
NUMERIC_STUB = MODULE / "tests/element_reduction/harness.cpp"
D3 = MODULE / "data/d3"
STATS_JS = MODULE.parent / "reference/d3planner/data_stats.js"
STATS_FULL = MODULE.parent / "reference/d3planner/stats_full.js"
CXX = shutil.which("g++") or shutil.which("c++")

# code -> the item whose preset carries it (item_preset_ranges.csv d3_id)
ITEMS_FOR = {"maxfury": "P61_Unique_BarbBelt_EQ", "basearmor": "Unique_BarbBelt_003_x1", "firetaken": "Unique_Helm_003_p2", "maxap": "P3_Unique_WizardHat_003",
             "maxmana": "Unique_VoodooMask_006_x1", "maxdisc": "Unique_HandXBow_005_x1",
             "apoc": "P3_Unique_WizardHat_003", "lifefury": "P61_Unique_Mighty_2H_006", "spiritregen": "Unique_Amulet_013_x1",
             "manaregen": "P68_Unique_Mojo_003", "damage_beasts": "Unique_Dagger_007_x1",
             "damage_demons": "Unique_Sword_1H_007_x1", "damage_undead": "Unique_Sword_2H_104_x1",
             "damage_humans": "Unique_Dagger_007_x1"}
# The lines Combat's readers read (stats/dc_stat_readers.h), with the monster kind of each damage-to-type line.
READ = ("apoc", "lifefury", "spiritregen", "manaregen")
KIND = {"damage_beasts": "Beast", "damage_demons": "Demon", "damage_undead": "Undead", "damage_humans": "Human"}
EVERY_CLASS = -1


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def top_roll(code):
    rows = [r for r in read(D3 / "item_preset_ranges.csv")
            if r["d3_id"] == ITEMS_FOR[code] and r["affix_id"] == code and r["item_level_bracket"] == "legendary"]
    assert len(rows) == 1, (code, rows)
    return float(rows[0]["value_max"])


def owning_class(code):
    """class_map.csv class_id of the class data_stats.js gives the code, 0 for one Torment has not built, EVERY_CLASS
    for a line data_stats.js gives no class."""
    line = next(l for l in STATS_JS.read_text(encoding="utf-8").splitlines() if l.strip().startswith(code + ": {"))
    found = re.search(r'class: "(\w+)"', line)
    if not found:
        return EVERY_CLASS
    built = {r["d3_class"].replace(" ", "").lower(): int(r["class_id"]) for r in read(D3 / "class_map.csv")}
    return built.get(found.group(1), 0)


def cut(text, start, end):
    return text[text.index(start):text.index(end)]


def program(items, resources):
    stub = NUMERIC_STUB.read_text(encoding="utf-8")
    numeric = cut(stub, "namespace DC::NumericData\n", "} // namespace DC::NumericData") + "}\n"
    of = cut(resources, "    inline Resource const* Of(", "    // The resources the module's class code names.")
    head = items_source.lists(items)
    body = items_source.stat_map(items)
    # A source without the class gate (nightly before it) has no Applies(): it compiles without it and
    # fails at the per-code checks below, not here.
    gate_start = "// False for a class resource's stat on a class without that resource"
    if gate_start in items:
        body += cut(items, gate_start, "// Per player, the contributions")
    gate = re.search(r"\n(        auto mapping = mappings\.find\(statId\);\n        if \(mapping == mappings\.end\(\).*\n"
                     r"            continue;\n)", items)
    # Apply's own value line (the Cube's and the set levels' read row.max and row.min)
    value = [line for line in re.findall(r"\n            (contribution\.value = [^;\n]*;)\n", items) if "row." not in line]
    assert gate and len(value) == 1, "Apply's gate or value line moved"
    return ('#include "dc_common.h"\n#include "dc_numeric_data.h"\n#include "dc_resource_data.h"\n'
            '#include "dc_stat_readers.h"\n'
            "#include <cmath>\n#include <cstdio>\n#include <cstdlib>\n#include <map>\n#include <string>\n"
            "#include <string_view>\n#include <unordered_map>\n#include <vector>\n"
            "class Player {};\n" + numeric +
            "namespace DC::Classes\n{\nstd::uint32_t worn = 0;\n"
            "std::uint32_t ClassIdOf(Player const*) { return worn; }\n}\n"
            "namespace DC::Resources\n{\nusing Resource = Data::Row;\n" + of + "}\n"
            "namespace DC::Items\n{\n" + head + body +
            "// One worn line through Apply: its gate, then the contribution it adds.\n"
            "std::vector<Contribution> Worn(Player const* player, std::string const& statId, double value)\n{\n"
            "    auto const& mappings = Mappings();\n"
            "    std::vector<Contribution> added;\n"
            "    for (int once = 0; once < 1; ++once)\n    {\n"
            + gate.group(1) +
            "        Contribution contribution;\n"
            "        contribution.stat = mapping->second.stat;\n"
            "        contribution.bucket = mapping->second.bucket;\n"
            "        contribution.element = mapping->second.element;\n"
            "        contribution.id = 77;\n"
            "            " + value[0] + "\n"
            "        added.push_back(contribution);\n"
            "    }\n    return added;\n}\n}\n"
            "using namespace DC;\n"
            "int failures = 0;\n"
            "void Check(bool ok, char const* what) { if (!ok) { std::printf(\"FAIL: %s\\n\", what); ++failures; } }\n"
            "bool Near(double a, double b) { return std::fabs(a - b) < 1e-9; }\n"
            "namespace Readers = DC::Stats::Readers;\nusing Readers::MonsterKind;\n"
            "MonsterKind KindNamed(std::string const& name)\n{\n"
            "    return name == \"Beast\" ? MonsterKind::Beast : name == \"Demon\" ? MonsterKind::Demon\n"
            "         : name == \"Undead\" ? MonsterKind::Undead : name == \"Human\" ? MonsterKind::Human : MonsterKind::Other;\n}\n"
            "// What Combat's reader pays for the line on this sheet: Arcane Power on one crit of coefficient 1, Life for 10\n"
            "// Fury spent, the resource's points a second.\n"
            "double Reader(std::string const& code, StatSheet const& sheet)\n{\n"
            "    double carry = 0;\n"
            "    if (code == \"apoc\") return Readers::CritResource(sheet, 1.0, carry) + carry;\n"
            "    if (code == \"lifefury\") return Readers::LifeForFurySpent(sheet, 10);\n"
            "    if (code == \"spiritregen\") return Readers::RegenPerSecond(sheet, \"spirit\");\n"
            "    if (code == \"manaregen\") return Readers::RegenPerSecond(sheet, \"mana\");\n"
            "    std::abort();\n}\n"
            "double Paid(std::string const& code, double value) { return code == \"lifefury\" ? 10 * value : value; }\n"
            "int main(int argc, char** argv)\n{\n"
            "    if (argc != 5) return 2;\n"
            "    std::string const code = argv[1];\n"
            "    double const value = std::atof(argv[2]);\n"
            "    int const owner = std::atoi(argv[3]);\n"
            "    MonsterKind const kind = KindNamed(argv[4]);\n"
            "    Player player;\n"
            "    BaseStats base;\n"
            "    base.level = 70; base.strength = 100; base.vitality = 100; base.baseArmor = 100;\n"
            "    base.baseLife = 1000; base.lifePerVitality = 10; base.maxFury = 100;\n"
            "    std::vector<Contribution> gear{{Source::Items, Stat::AllResistance, 1, 300}};\n"
            "    StatSheet const bare = Calculate(base, gear);\n"
            "    std::vector<std::uint32_t> classes;\n"
            "    for (auto const& row : Resources::Data::Rows) classes.push_back(row.classId);\n"
            "    for (std::uint32_t cls : classes)\n    {\n"
            "        Classes::worn = cls;\n"
            "        std::vector<Contribution> worn = gear;\n"
            "        for (Contribution const& c : Items::Worn(&player, code, value)) worn.push_back(c);\n"
            "        StatSheet const sheet = Calculate(base, worn);\n"
            "        unsigned const fire = Index(Element::Fire), cold = Index(Element::Cold);\n"
            "        if (code == \"basearmor\")\n"
            "            Check(Near(sheet[Stat::Armor], bare[Stat::Armor] + value), \"basearmor adds to Armor\");\n"
            "        else if (code == \"firetaken\")\n        {\n"
            "            Check(Near(sheet.damageTaken[fire], bare.damageTaken[fire] * (1 + value / 100)), \"Fire taken x 1 + X/100\");\n"
            "            Check(Near(sheet.damageTaken[cold], bare.damageTaken[cold]), \"Cold taken unchanged\");\n"
            "            Check(Near(sheet.elementReduction[fire], -value), \"the Fire reduction reads -X\");\n"
            "            Check(Near(DeserializeSheet(Serialize(sheet)).elementReduction[fire], -value), \"the sheet save keeps it\");\n"
            "        }\n"
            "        else if (kind != MonsterKind::Other)\n        {\n"
            "            Check(worn.size() == gear.size() + 1, \"every class wears the damage-to-type line\");\n"
            "            for (MonsterKind other : {MonsterKind::Other, MonsterKind::Beast, MonsterKind::Demon, MonsterKind::Undead,\n"
            "                                      MonsterKind::Human})\n"
            "                Check(Near(Readers::MonsterTypeFactor(sheet, other), other == kind ? 1 + value / 100 : 1.0),\n"
            "                      \"its own kind takes 1 + X/100 and every other kind 1\");\n"
            "        }\n"
            "        else if (code.rfind(\"max\", 0) != 0)\n        {\n"
            "            if (owner == static_cast<int>(cls))\n"
            "                Check(Near(Reader(code, sheet), Paid(code, value)), \"the owning class's reader pays the line\");\n"
            "            else\n"
            "                Check(Near(Reader(code, sheet), Reader(code, bare)) && worn.size() == gear.size(),\n"
            "                      \"another class's reader pays nothing and the line adds nothing\");\n"
            "        }\n"
            "        else if (code == \"maxdisc\")\n        {\n"
            "            // Discipline is the Demon Hunter's second resource: the line raises the second slot's maximum, never Hatred's.\n"
            "            Check(Near(sheet[Stat::MaxFury], bare[Stat::MaxFury]), \"Maximum Discipline leaves the first slot's maximum alone\");\n"
            "            if (owner == static_cast<int>(cls))\n"
            "                Check(Near(sheet[Stat::MaxSecond], bare[Stat::MaxSecond] + value), \"the owning class's second maximum rises\");\n"
            "            else\n"
            "                Check(Near(sheet[Stat::MaxSecond], bare[Stat::MaxSecond]) && worn.size() == gear.size(),\n"
            "                      \"another class's second maximum is untouched and the line adds nothing\");\n"
            "        }\n"
            "        else if (owner == static_cast<int>(cls))\n"
            "            Check(Near(sheet[Stat::MaxFury], bare[Stat::MaxFury] + value), \"the owning class's maximum rises\");\n"
            "        else\n"
            "            Check(Near(sheet[Stat::MaxFury], bare[Stat::MaxFury]) && worn.size() == gear.size(),\n"
            "                  \"another class's maximum is untouched and the line adds nothing\");\n"
            "    }\n"
            "    // A regeneration line lands on the stat the pulse's reader reads for the resource its row names.\n"
            "    if (code == \"spiritregen\" || code == \"manaregen\")\n    {\n"
            "        auto const row = Items::Mappings().find(code);\n"
            "        Check(row != Items::Mappings().end() && row->second.resource &&\n"
            "              Readers::RegenStatOf(row->second.resource) == row->second.stat, \"the row is the reader's stat\");\n"
            "    }\n"
            "    return failures;\n}\n")


def build(items, resources, folder):
    if not CXX:
        raise unittest.SkipTest("no C++ compiler")
    cpp, binary = Path(folder) / "t.cpp", Path(folder) / "t"
    cpp.write_text(program(items, resources), encoding="utf-8")
    built = subprocess.run([CXX, "-std=c++17", "-O1", "-UNDEBUG", "-I", str(SRC / "common"), "-I", str(SRC / "classes"), "-I", str(SRC / "stats"),
                            "-o", str(binary), str(cpp), str(COMMON)], capture_output=True, text=True)
    if built.returncode:
        return None, built.stderr[-3000:]
    return binary, ""


def run(binary, code):
    done = harness_env.run([str(binary), code, repr(top_roll(code)), str(owning_class(code)), KIND.get(code, "Other")],
                           capture_output=True, text=True)
    return done.returncode, done.stdout


class Reference(unittest.TestCase):
    def test_the_reference_names_each_stat(self):
        stats = STATS_JS.read_text(encoding="utf-8")
        for code, attribute in (("basearmor", r'name: "Base Armor", base: true'),
                                ("firetaken", r'id: "Amplify_Damage_Type_Percent#Fire"'),
                                ("maxfury", r'class: "barbarian".*id: "Resource_Max_Bonus#Fury"'),
                                ("maxap", r'class: "wizard".*id: "Resource_Max_Bonus#Arcanum"'),
                                ("maxmana", r'class: "witchdoctor".*id: "Resource_Max_Bonus#Mana"'),
                                ("maxdisc", r'class: "demonhunter".*id: "Resource_Max_Bonus#Discipline"'),
                                ("apoc", r'class: "wizard".*id: "Resource_On_Crit#Arcanum"'),
                                ("lifefury", r'class: "barbarian".*id: "Spending_Resource_Heals_Percent#Fury"'),
                                ("spiritregen", r'class: "monk".*id: "Resource_Regen_Per_Second#Spirit"'),
                                ("manaregen", r'class: "witchdoctor".*id: "Resource_Regen_Per_Second#Mana"'),
                                ("damage_beasts", r'id: "Damage_Percent_Bonus_Vs_Monster_Type#Beast", percent: true'),
                                ("damage_demons", r'id: "Damage_Percent_Bonus_Vs_Monster_Type#Demon", percent: true'),
                                ("damage_undead", r'id: "Damage_Percent_Bonus_Vs_Monster_Type#Undead", percent: true'),
                                ("damage_humans", r'id: "Damage_Percent_Bonus_Vs_Monster_Type#Human", percent: true')):
            with self.subTest(code=code):
                self.assertRegex(stats, code + r": \{.*" + attribute)
        full = STATS_FULL.read_text(encoding="utf-8")
        self.assertIn("this.armor += (this.basearmor || 0);", full)
        self.assertIn("(1 + 0.01 * (this.firetaken || 0))", full)

    def test_the_registry_keys_the_gate_names(self):
        keys = {r["resource_key"]: r["d3_class"] for r in read(D3 / "class_resources.csv")}
        self.assertEqual(keys.get("fury"), "Barbarian")
        self.assertEqual(keys.get("arcane_power"), "Wizard")
        self.assertEqual(keys.get("mana"), "Witch Doctor")
        self.assertEqual(keys.get("discipline"), "Demon Hunter")
        self.assertEqual(keys.get("spirit"), "Monk")


class Worn(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix="dc-preset-stats-")
        cls.items = items_source.source()
        cls.resources = RESOURCES.read_text(encoding="utf-8")
        cls.binary, cls.error = build(cls.items, cls.resources, cls.folder.name)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def worn(self, code):
        self.assertIsNotNone(self.binary, self.error)
        code_, out = run(self.binary, code)
        self.assertEqual(code_, 0, out)

    def test_basearmor(self):
        self.worn("basearmor")

    def test_firetaken(self):
        self.worn("firetaken")

    def test_maxap(self):
        self.assertEqual(owning_class("maxap"), 2)
        self.worn("maxap")

    def test_maxfury_only_on_the_barbarian(self):
        self.assertEqual(owning_class("maxfury"), 1)
        self.worn("maxfury")

    def test_maxmana_only_on_the_witch_doctor(self):
        self.assertEqual(owning_class("maxmana"), 7)
        self.worn("maxmana")

    def test_maxdisc_only_on_the_demon_hunter(self):
        self.assertEqual(owning_class("maxdisc"), 6)
        self.worn("maxdisc")

    def test_apoc_only_on_the_wizard(self):
        self.assertEqual(owning_class("apoc"), 2)
        self.worn("apoc")

    def test_lifefury_only_on_the_barbarian(self):
        self.assertEqual(owning_class("lifefury"), 1)
        self.worn("lifefury")

    def test_spiritregen_only_on_the_monk(self):
        self.assertEqual(owning_class("spiritregen"), 3)
        self.worn("spiritregen")

    def test_manaregen_only_on_the_witch_doctor(self):
        self.assertEqual(owning_class("manaregen"), 7)
        self.worn("manaregen")

    def test_damage_beasts(self):
        self.worn("damage_beasts")

    def test_damage_demons(self):
        self.worn("damage_demons")

    def test_damage_undead(self):
        self.worn("damage_undead")

    def test_damage_humans(self):
        self.worn("damage_humans")

    def test_the_damage_lines_are_every_class(self):
        for code in KIND:
            with self.subTest(code=code):
                self.assertEqual(owning_class(code), EVERY_CLASS)

    def test_mutants_are_caught(self):
        gate = "if (mapping == mappings.end() || !Applies(mapping->second, player))"
        mutants = [
            (gate, "if (mapping == mappings.end())", "maxap"),
            ("contribution.value = Signed(mapping->second, value);", "contribution.value = value;", "firetaken"),
            ("double Signed(StatMapping const& mapping, double value) { return mapping.negate ? -value : value; }",
             "double Signed(StatMapping const& mapping, double value) { return value; }", "firetaken"),
            ('{"basearmor", {Stat::Armor}},', '{"basearmor", {Stat::Thorns}},', "basearmor"),
            ('Element::Fire, nullptr, true}}', 'Element::Cold, nullptr, true}}', "firetaken"),
            ('{"maxap", {Stat::MaxFury, Bucket::Flat, Element::Physical, "arcane_power"}}',
             '{"maxap", {Stat::MaxFury, Bucket::Flat, Element::Physical, "fury"}}', "maxap"),
            ('{"maxfury", {Stat::MaxFury, Bucket::Flat, Element::Physical, "fury"}}',
             '{"maxfury", {Stat::MaxFury, Bucket::Flat, Element::Physical, nullptr}}', "maxfury"),
            ('{"maxmana", {Stat::MaxFury, Bucket::Flat, Element::Physical, "mana"}}',
             '{"maxmana", {Stat::MaxFury, Bucket::Flat, Element::Physical, "spirit"}}', "maxmana"),
            ('Element::Physical, "discipline"}}', 'Element::Physical, nullptr}}', "maxdisc"),
            ('{"maxdisc", {Stat::MaxSecond,', '{"maxdisc", {Stat::MaxFury,', "maxdisc"),
            ("std::string_view(row->key) == mapping.resource", "true", "maxap"),
            ('{"apoc", {Stat::ResourceOnCrit, Bucket::Flat, Element::Physical, "arcane_power"}}',
             '{"apoc", {Stat::ResourceOnCrit, Bucket::Flat, Element::Physical, nullptr}}', "apoc"),
            ('{"apoc", {Stat::ResourceOnCrit,', '{"apoc", {Stat::ManaRegen,', "apoc"),
            ('{"lifefury", {Stat::LifePerFury, Bucket::Flat, Element::Physical, "fury"}}',
             '{"lifefury", {Stat::LifePerHit, Bucket::Flat, Element::Physical, "fury"}}', "lifefury"),
            ('Stat::LifePerFury, Bucket::Flat, Element::Physical, "fury"}}',
             'Stat::LifePerFury, Bucket::Flat, Element::Physical, nullptr}}', "lifefury"),
            ('{"spiritregen", {Stat::SpiritRegen,', '{"spiritregen", {Stat::ManaRegen,', "spiritregen"),
            ('Stat::SpiritRegen, Bucket::Flat, Element::Physical, "spirit"}}',
             'Stat::SpiritRegen, Bucket::Flat, Element::Physical, "fury"}}', "spiritregen"),
            ('{"manaregen", {Stat::ManaRegen,', '{"manaregen", {Stat::SpiritRegen,', "manaregen"),
            ('Stat::ManaRegen, Bucket::Flat, Element::Physical, "mana"}}',
             'Stat::ManaRegen, Bucket::Flat, Element::Physical, nullptr}}', "manaregen"),
            ('{"damage_beasts", {Stat::DamageVsBeast}}', '{"damage_beasts", {Stat::DamageVsDemon}}', "damage_beasts"),
            ('{"damage_demons", {Stat::DamageVsDemon}}', '{"damage_demons", {Stat::DamageVsUndead}}', "damage_demons"),
            ('{"damage_undead", {Stat::DamageVsUndead}}', '{"damage_undead", {Stat::DamageVsBeast}}', "damage_undead"),
            ('{"damage_humans", {Stat::DamageVsHuman}}', '{"damage_humans", {Stat::DamageVsHuman, Bucket::Percent}}',
             "damage_humans"),
            ('{"damage_humans", {Stat::DamageVsHuman}}',
             '{"damage_humans", {Stat::DamageVsHuman, Bucket::Flat, Element::Physical, "fury"}}', "damage_humans"),
        ]
        for old, new, code in mutants:
            with self.subTest(mutation=old):
                self.assertEqual(self.items.count(old), 1, old)
                with tempfile.TemporaryDirectory(prefix="dc-preset-stats-mutant-") as folder:
                    binary, error = build(self.items.replace(old, new), self.resources, folder)
                    if binary is None:
                        continue  # a mutant that no longer compiles is caught
                    returned, _ = run(binary, code)
                    self.assertNotEqual(returned, 0, f"survived: {new!r}")


if __name__ == "__main__":
    unittest.main()
