"""Hellfire Amulet (diablocraft-enuxm): a class passive rolled when the amulet is made and granted while it is worn.

What this proves, and what it does not:

  * The RULES are the production header src/items/dc_granted_passive_rule.h, compiled into tests/granted_passive/harness.cpp and
    driven with the sheets: data/d3/base_items.csv (the amulet is the one legendary base that rolls, though the ethereals list the
    same preset) and the generated class catalogue (every passive of every class is reachable from the roll: the full list,
    whatever the player chose, ruling 2026-10-12).
  * Each rule has a mutation that must turn the harness red.
  * The WIRING (StageRoll rolls it, Items::Apply caches it, Passives::Has searches it, the Mystic and the crafting window skip the
    row, the migration holds the kind) is read from the code with comments removed. It is not executed: that needs a game server
    and is the GM script in docs/test-diablocraft-enuxm.md.
"""
import csv
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import items_source  # noqa: E402
import crafting_source  # noqa: E402
import harness_env  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
ROOT = MODULE.parent
SRC = MODULE / "src"
HEADER = SRC / "items/dc_granted_passive_rule.h"
HARNESS = MODULE / "tests/granted_passive/harness.cpp"
SCRATCH = ROOT / "azerothcore-wotlk/build/_agent-scratch/granted_passive"
CATALOGUE = MODULE / "data/generated/class_catalogue.sql"
MIGRATION = MODULE / "data/sql/db-characters/updates/items_0009_affix_passive_kind.sql"
HELLFIRE = "x1_Amulet_norm_unique_25"


def code(path):
    """Source with comments removed, so prose cannot satisfy a wiring check."""
    return without_comments(Path(path).read_text(encoding="utf-8"))


def without_comments(text):
    lines = []
    for line in text.splitlines():
        if line.strip().startswith(("//", "*", "/*")):
            continue
        lines.append(line.split("//")[0])
    return "\n".join(lines)


def passives_by_class():
    """[(class_id, passive name)] in unlock order, from the generated dc_class_passive and its labels."""
    text = CATALOGUE.read_text(encoding="utf-8")
    rows = re.findall(r"^\((\d+), (\d+), (\d+)\)[,;]$", text[text.index("INSERT INTO `dc_class_passive` "):], re.M)
    labels = dict((int(i), n) for i, n in re.findall(
        r"^\((\d+), '((?:[^']|'')*)'\)[,;]$", text[text.index("INSERT INTO `dc_class_passive_label`"):], re.M))
    assert rows and labels
    return [(c, labels[int(s)].replace("''", "'")) for c, s, _ in sorted(rows, key=lambda r: (int(r[0]), int(r[2]), int(r[1])))
            if int(s) in labels]


def write_inputs():
    SCRATCH.mkdir(parents=True, exist_ok=True)
    with (MODULE / "data/d3/base_items.csv").open(encoding="utf-8", newline="") as stream:
        bases = list(csv.DictReader(stream, strict=True))
    (SCRATCH / "bases.tsv").write_text(
        "".join("%s\t%s\t%s\n" % (b["d3_id"], b["rarity"], b["preset_affixes"]) for b in bases), encoding="utf-8")
    (SCRATCH / "passives.tsv").write_text("".join("%s\t%s\n" % row for row in passives_by_class()), encoding="utf-8")


def build(include_dir, name, strict=True):
    compiler = shutil.which("c++") or shutil.which("g++")
    binary = SCRATCH / name
    flags = ["-Wall", "-Wextra", "-Werror"] if strict else []
    built = subprocess.run([compiler, "-std=c++17", "-O1", *flags, "-I", str(include_dir), str(HARNESS), "-o", str(binary)],
                           capture_output=True, text=True)
    if built.returncode:
        raise AssertionError("the harness did not compile:\n" + built.stderr[-6000:])
    return binary


def run(binary):
    return harness_env.run([str(binary), str(SCRATCH / "bases.tsv"), str(SCRATCH / "passives.tsv"), HELLFIRE],
                           capture_output=True, text=True)


# One mutation per rule; each must make the harness fail.
MUTATIONS = [
    ("rolls: an ethereal rolls too",
     'return rarity == "legendary" &&', "return"),
    ("rolls: every legendary rolls",
     ' && std::find(presets.begin(), presets.end(), Preset) != presets.end();', ";"),
    ("pick: the first passive is never chosen",
     "std::clamp(pick, 0.0, 1.0) * classPassives.size()", "std::clamp(pick, 0.0, 1.0) * (classPassives.size() - 1) + 1"),
    ("pick: the last passive is never chosen",
     "std::clamp(pick, 0.0, 1.0) * classPassives.size()", "std::clamp(pick, 0.0, 1.0) * (classPassives.size() - 1)"),
    ("pick: no clamp to the last, a pick of 1 runs off the list",
     "return classPassives[std::min(index, classPassives.size() - 1)];", "return classPassives[index];"),
    ("pick: an empty list picks something",
     "if (classPassives.empty())\n            return std::string();", "if (false)\n            return std::string();"),
    ("granted: any row grants",
     "if (row.kind == Kind)", "if (true)"),
    ("granted: nothing is read from the item",
     "return row.affixId;", "break;"),
    ("merge: a granted copy of a chosen passive is added again",
     "std::find(chosen.begin(), chosen.end(), name) == chosen.end()", "true"),
    ("merge: an empty name is added",
     "!name.empty() && ", ""),
    ("merge: the granted passives are dropped",
     "chosen.push_back(name);", ";"),
]


class Rules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (shutil.which("c++") or shutil.which("g++")):
            raise unittest.SkipTest("no C++ compiler")
        write_inputs()
        cls.binary = build(HEADER.parent, "granted_passive_tests")

    def test_the_production_header_passes_on_the_sheets(self):
        result = run(self.binary)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertRegex(result.stdout, r"granted passive OK \(\d+ classes, \d+ bases list the preset, 1 roll\)")

    def test_every_class_with_a_catalogue_has_passives_to_roll_from(self):
        classes = {c for c, _ in passives_by_class()}
        self.assertGreaterEqual(len(classes), 2)

    def test_every_mutation_fails(self):
        for index, (label, old, new) in enumerate(MUTATIONS):
            with self.subTest(mutation=label):
                source = HEADER.read_text(encoding="utf-8")
                self.assertEqual(source.count(old), 1, "mutation target moved: " + old)
                folder = SCRATCH / ("mutant_%d" % index)
                folder.mkdir(parents=True, exist_ok=True)
                (folder / HEADER.name).write_text(source.replace(old, new), encoding="utf-8")
                result = run(build(folder, "mutant", strict=False))
                self.assertNotEqual(result.returncode, 0, label + " was not caught:\n" + result.stdout)


def body(source, anchor):
    start = source.find(anchor)
    assert start >= 0, "anchor missing (renamed or moved; update this test): " + anchor
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        depth += {"{": 1, "}": -1}.get(source[index], 0)
        if depth == 0:
            return source[start:index + 1]
    raise AssertionError("unbalanced braces after " + anchor)


class Wiring(unittest.TestCase):
    items = without_comments(items_source.source())
    passives = code(SRC / "combat/dc_passives.cpp")
    crafting = without_comments(crafting_source.source())
    header = code(HEADER)

    def test_the_roll_picks_from_the_roll_classs_full_list_for_every_path(self):
        roll = body(self.items, "std::unique_ptr<StagedRoll> StageRoll(")
        # The list is the roll class's (affixClass: the drop's roll class, else the player's), never the player's chosen passives.
        self.assertIn("classIds.find(affixClass)", roll)
        self.assertIn("DC::GrantedPassive::Rolls(base.presets, base.rarity)", roll)
        self.assertIn("DC::GrantedPassive::Pick(passiveChoices,", roll)
        self.assertIn("DC::GrantedPassive::Kind", roll)
        self.assertNotIn("Classes::Passives", roll)
        self.assertNotIn("Passives::Has", roll)

    def test_the_passive_list_is_every_passive_of_the_class(self):
        load = self.items[self.items.index("loadedPassives;"):]
        load = load[:load.index("classPassiveNames = std::move")]
        self.assertIn("FROM dc_class_passive p", load)
        self.assertNotIn("dc_character_passives", load)
        self.assertNotIn("WHERE", load)

    def test_has_searches_the_chosen_and_the_granted(self):
        has = body(self.passives, "bool Has(Player* p, char const* name)")
        self.assertIn("Items::WithGrantedPassives(p, Classes::Passives(p))", has)

    def test_apply_grants_only_while_worn_and_unbroken_and_tells_has(self):
        apply = body(self.items, "void Apply(Player* player, Item* item, bool equipping)")
        # A broken item is already `equipping = false` at the top of Apply.
        self.assertIn("if (equipping && item->IsBroken())", apply)
        self.assertIn("equipping ? DC::GrantedPassive::Granted(instance->affixes)", apply)
        self.assertIn("DC::Combat::Passives::Invalidate(player)", apply)
        # Invalidate takes Passives' own lock: it is called after the items lock is released.
        self.assertLess(apply.index("grantedPassive[playerGuid]"), apply.index("if (differs)"))
        self.assertIn("grantedPassive.erase(player->GetGUID().GetRawValue())", self.items)

    def test_the_stat_loop_the_mystic_and_the_window_skip_the_row(self):
        apply = body(self.items, "void Apply(Player* player, Item* item, bool equipping)")
        self.assertIn("affix.kind == DC::GrantedPassive::Kind) continue;", apply)
        # the Mystic's choice list skips the Cube's augment row too (diablocraft-wpt7l.8)
        self.assertIn('a.kind == "power" || a.kind == "augment" || a.kind == DC::GrantedPassive::Kind', self.items)
        self.assertIn('a.kind != "passive"', self.crafting)

    def test_the_migration_holds_the_kind_the_code_writes(self):
        kind = re.search(r'Kind = "(\w+)"', self.header)[1]
        enum = re.search(r"ENUM\(([^)]*)\)", MIGRATION.read_text(encoding="utf-8"))[1].split(",")
        self.assertIn("'%s'" % kind, enum)
        # items_0007's kinds stay: the new ENUM only adds.
        for old in ("primary", "secondary", "socket", "gem", "preset", "power"):
            self.assertIn("'%s'" % old, enum)


if __name__ == "__main__":
    unittest.main()
