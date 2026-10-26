"""Demon Hunter 2b: Hatred and Discipline, the two pools and who pays them.

What this proves, and how:

  * **The payment and the pools.** tests/demon_hunter_hatred/harness.cpp compiles the real dc_demon_hunter_hatred.h,
    dc_resources.h and the generated dc_resource_data.h over the registry harness's shim Player, and feeds it the sheet's own
    numbers (demon_hunter_skill_values.csv, read here): Hatred is in Energy and Discipline in Focus, one unit a point, 125 and
    30, regenerating 5 and 1 a second, nothing decays, both start full; Hungering Arrow and Serrated Arrow add their sheet
    values to Hatred and never touch Discipline; Impale's cost comes off Hatred only and Caltrops' off Discipline only; each
    pool stops at its own maximum and at 0; another class, a Demon Hunter not showing Hatred and a zero generation are not
    paid; Paragon pays Hatred +1 per two points and Discipline none. Six mutations planted in a scratch copy (the class guard,
    the displayed-power guard, the zero guard, Hatred stored ten units a point, Discipline moved to Energy, the Hatred pool)
    must each make it fail.
  * **The sheets agree.** The five primaries' generated_resource equals demon_hunter_skills.csv's resource_generation, no other
    skill states an unqualified one, every row has its place in the generated value table the engine reads, the resource
    sheets and the registry agree on 125 and 30, and the records pay a Discipline skill in Focus.
  * **The wiring.** Combat::Connected calls the Demon Hunter, and the class's name appears in src/ only in its folder and
    that one call.

What it does not prove: anything on a running server. The orb, the tooltips and a primary's hit need the skill beads and are
the test sheet's, live.

    python mod-diablocraft/scripts/tests/classes/test_demon_hunter_resources.py
"""

import csv
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
sys.path.insert(0, str(MODULE / "scripts"))

import generate_class_resources as gcr  # noqa: E402
import generate_spells  # noqa: E402

HATRED_HEADER = "src/classes/demon_hunter/dc_demon_hunter_hatred.h"
SOURCES = ["src/classes/dc_resources.h", "src/classes/dc_resource_carry.h", "src/classes/dc_resource_data.h", HATRED_HEADER,
           "tests/demon_hunter_hatred/harness.cpp"]


def read(name):
    with (D3 / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(skill, rune, token):
    rows = [r for r in read("demon_hunter_skill_values.csv")
            if r["skill"] == skill and r["rune"] == rune and r["token"] == token and not r["qualifier"]]
    assert len(rows) == 1, (skill, rune, token, len(rows))
    return rows[0]["value"]


def scratch_tree(mutate=None):
    """The headers one build stages ({path under src/: text}); the mutation edits one of them."""
    files = {source[len("src/"):]: (MODULE / source).read_text(encoding="utf-8") for source in SOURCES if source.startswith("src/")}
    if mutate:
        path, old, new = mutate
        key = path[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([MODULE / "tests/demon_hunter_hatred/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree,
                                 includes=[MODULE / "tests/resource_registry/shim"])
    numbers = [value("Hungering Arrow", "", "generated_resource"),
               value("Hungering Arrow", "Serrated Arrow", "generated_resource"),
               value("Impale", "", "cost_resource"),
               value("Caltrops", "", "cost_resource")]
    return harness_env.run([str(binary)] + numbers, capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_payment_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 32, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        data = "src/classes/dc_resource_data.h"
        mutations = [
            ("a Monk is paid Hatred", (HATRED_HEADER, "classId != Resources::Hatred.classId ||", "")),
            ("a Demon Hunter not showing Hatred is paid",
             (HATRED_HEADER, "||\n            !Resources::Displayed(player, Resources::Hatred)", "")),
            ("a zero generation is paid", (HATRED_HEADER, "points <= 0 ||", "")),
            ("Hatred stored ten units a point",
             (data, '"Hatred", Role::Primary, 3, "Energy", 1.0,', '"Hatred", Role::Primary, 3, "Energy", 10.0,')),
            ("Discipline in Energy",
             (data, '"Discipline", Role::Second, 2, "Focus",', '"Discipline", Role::Second, 3, "Energy",')),
            ("Hatred pool 100", (data, '"Energy", 1.0, 125.0,', '"Energy", 1.0, 100.0,')),
        ]
        for label, mutation in mutations:
            with self.subTest(label):
                try:
                    tree = scratch_tree(mutation)
                except AssertionError as error:
                    self.fail(str(error))
                out = build_and_run(tree)
                self.assertNotEqual(out.returncode, 0, f"{label} was not caught: {out.stdout[-500:]}")


class Sheets(unittest.TestCase):
    def test_the_five_primaries_generate_and_nothing_else_unqualified(self):
        skills = {r["skill_name"]: r for r in read("demon_hunter_skills.csv")}
        unqualified = [r for r in read("demon_hunter_skill_values.csv")
                       if not r["rune"] and not r["qualifier"] and r["token"] == "generated_resource"]
        self.assertEqual(sorted(r["skill"] for r in unqualified),
                         sorted(name for name, row in skills.items() if row["category"] == "Primary"))
        self.assertEqual(len(unqualified), 5)
        for row in unqualified:
            self.assertEqual(float(skills[row["skill"]]["resource_generation"]), float(row["value"]), row["skill"])
            self.assertEqual(skills[row["skill"]]["resource"], "hatred", row["skill"])

    def test_every_generating_row_is_in_the_value_table_the_engine_reads(self):
        header = (MODULE / "src/combat/dc_spell_values.h").read_text(encoding="utf-8")
        ids = {}
        with (MODULE / "data/generated/spell_shells.csv").open(encoding="utf-8", newline="") as stream:
            for row in csv.reader(stream):
                if row and row[0].isdigit():
                    ids[row[1]] = int(row[0])
        checked = 0
        for row in read("demon_hunter_skill_values.csv"):
            if row["token"] != "generated_resource" or row["qualifier"]:
                continue
            name = f"{row['skill']} - {row['rune']}" if row["rune"] else row["skill"]
            spell = ids[name]
            self.assertRegex(header, r'\{%d, "generated_resource", "", Source::BasePoints, %d, \d+, Origin::Own, %d\}'
                             % (spell, spell, spell), name)
            checked += 1
        self.assertEqual(checked, 10)

    def test_the_resource_sheets_and_the_registry_agree(self):
        resource = {r["metric"]: r for r in read("demon_hunter_resource.csv")}
        self.assertEqual(float(resource["Maximum Hatred (base)"]["value"]), 125)
        self.assertEqual(float(resource["Maximum Discipline (base)"]["value"]), 30)
        entries = {e["key"]: e for e in gcr.registry() if e["d3_class"] == "Demon Hunter"}
        self.assertEqual({k: (e["role"], e["power"], e["scale"], e["pool"], e["regen"], e["decay"], e["paragon"], e["starts_full"],
                              e["paid_by"]) for k, e in entries.items()},
                         {"hatred": ("primary", "Energy", 1, 125.0, 5.0, "none", 0.5, True, "module"),
                          "discipline": ("second", "Focus", 1, 30.0, 1.0, "none", 0.0, True, "module")})
        for row in read("demon_hunter_base_stats.csv"):
            self.assertEqual((float(row["resource_max"]), float(row["discipline_max"])), (125, 30), row["level"])

    def test_the_records_pay_hatred_in_energy_and_discipline_in_focus(self):
        self.assertEqual(generate_spells.power_of("Demon Hunter"), (3, 1, "energy_points"))
        skills = {r["skill_name"]: r for r in read("demon_hunter_skills.csv")}
        self.assertEqual({skills[n]["resource"] for n in ("Caltrops", "Smoke Screen", "Shadow Power", "Vault", "Marked for Death")},
                         {"discipline"})
        self.assertEqual(float(value("Caltrops", "", "cost_resource")), 6)
        self.assertEqual(float(value("Impale", "", "cost_resource")), 20)


class Wiring(unittest.TestCase):
    def test_connected_calls_the_demon_hunter(self):
        text = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat" / "dc_combat_internal.h",
                                                               *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])
        body = text.split("void Connected(Player* player, std::uint32_t spellId, unsigned enemies)")[1].split("}")[0]
        self.assertIn("DemonHunter::Connected(player, spellId);", body)

    def test_the_demon_hunter_is_named_only_in_its_folder(self):
        found = set()
        for path in (MODULE / "src").rglob("*.*"):
            rel = path.relative_to(MODULE).as_posix()
            if path.suffix in (".cpp", ".h") and not rel.startswith("src/classes/demon_hunter/") \
                    and re.search(r"\bDemonHunter\b", path.read_text(encoding="utf-8", errors="replace")):
                found.add(rel)
        self.assertEqual(found, {"src/combat/dc_combat.cpp", "src/combat/dc_combat_hooks.cpp", "src/combat/dc_combat_resolve.cpp"})

    def test_the_connected_pay_reads_the_sheet_number_and_the_item_factor(self):
        text = (MODULE / "src/classes/demon_hunter/dc_demon_hunter.cpp").read_text(encoding="utf-8")
        self.assertIn('Numbers::Get(spellId, "generated_resource")', text)
        self.assertIn('"resource_generation_pct"', text)
        self.assertIn("Classes::ClassIdOf(player)", text)


if __name__ == "__main__":
    unittest.main()
