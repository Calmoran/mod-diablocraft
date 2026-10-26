"""diablocraft-4usi7 (Monk 2.1): Spirit.

What this proves, and how:

  * **The payment.** tests/monk_spirit/harness.cpp compiles the real dc_monk_spirit.h,
    dc_resources.h and the generated dc_resource_data.h over the registry harness's shim Player,
    and feeds it the sheet's own numbers (monk_skill_values.csv, read here): a Monk shows 0/250,
    Fists of Thunder adds its value stored at one Runic Power unit a point (class powers P2), Quickening its own,
    Lashing Tail Kick's cost comes off, the pool stops at 250 and at 0, another class (the
    Barbarian, whose primaries are paid on Rage elsewhere; the Wizard) and a Monk not showing
    Spirit are not paid, and Paragon pays +1 Spirit a point. Four mutations planted in a scratch
    copy (the class guard, the displayed-power guard, the storage scale, the zero guard) must each
    make it fail.
  * **The sheets agree.** The primaries' generated_resource and the spenders' cost_resource in
    monk_skill_values.csv equal monk_skills.csv's resource_generation / resource_cost columns;
    monk_resource.csv and class_resources.csv agree on 250, no regeneration, no decay;
    class_resources.csv's Monk row is the registry's (Runic Power, one unit, Paragon +1).
  * **The records will be paid in the right units.** generate_spells.power_of("Monk") is
    (Runic Power, 1, runic_power_points): a ManaCost of 50 on a record is Lashing Tail Kick's 50.
  * **Decay and regeneration are the core's absence.** The pinned core's Player.cpp regenerates and
    decays Runic Power only for a Death Knight (Player::RegenerateAll); a mutation of that guard in
    a scratch copy is seen. Nothing in src/ calls Regenerate or writes a Runic Power timer.
  * **The wiring.** Combat::Connected calls Monk::Connected, and the Monk's name appears in src/
    only in src/classes/monk/, the registry, the Spirit constant and that one call.

What it does not prove: anything on a running server. The orb, the tooltips, the minute standing
still and the Fists of Thunder hit need the Monk's records (2.2) and are docs/test-diablocraft-
4usi7.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_monk_spirit.py
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
CORE_PLAYER = REPO / "azerothcore-wotlk" / "src" / "server" / "game" / "Entities" / "Player" / "Player.cpp"
sys.path.insert(0, str(MODULE / "scripts"))

import generate_class_resources as gcr  # noqa: E402
import generate_spells  # noqa: E402

SOURCES = ["src/classes/dc_resources.h", "src/classes/dc_resource_carry.h", "src/classes/dc_resource_data.h", "src/classes/monk/dc_monk_spirit.h",
           "tests/monk_spirit/harness.cpp"]


def read(name):
    with (D3 / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(skill, rune, token):
    rows = [r for r in read("monk_skill_values.csv")
            if r["skill"] == skill and r["rune"] == rune and r["token"] == token]
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
    binary = harness_env.build([MODULE / "tests/monk_spirit/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree,
                                 includes=[MODULE / "tests/resource_registry/shim"])
    numbers = [value("Fists of Thunder", "", "generated_resource"),
               value("Fists of Thunder", "Quickening", "generated_resource"),
               value("Deadly Reach", "", "generated_resource"),
               value("Lashing Tail Kick", "", "cost_resource"),
               next(r["value"] for r in read("followers_skill_numbers.csv") if (r["skill_id"], r["token"]) == ("inspire", "spirit_generated_pct"))]
    return harness_env.run([str(binary)] + numbers, capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_payment_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 20, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("a Barbarian is paid Spirit",
             ("src/classes/monk/dc_monk_spirit.h", "classId != Resources::Spirit.classId ||", "")),
            ("a Monk not showing Spirit is paid",
             ("src/classes/monk/dc_monk_spirit.h", "||\n            !Resources::Displayed(player, Resources::Spirit)", "")),
            ("Spirit stored ten units a point",
             ("src/classes/dc_resource_data.h", '"Spirit", Role::Primary, 6, "Runic Power", 1.0,',
              '"Spirit", Role::Primary, 6, "Runic Power", 10.0,')),
            ("a loss is scaled by what is generated",
             ("src/classes/dc_resources.h", "double const factor = points > 0 && source && player ? source(player, r) : 1.0;",
              "double const factor = source && player ? source(player, r) : 1.0;")),
            ("a cost given back is scaled",
             ("src/classes/dc_resources.h", "generated ? Generated(player, r, points) : points", "Generated(player, r, points)")),
            ("a gain is not scaled", ("src/classes/dc_resources.h", "generated ? Generated(player, r, points) : points", "points")),
            ("a source that answers nothing wipes the gain", ("src/classes/dc_resources.h", "return factor > 0 ? points * factor : points;", "return points * factor;")),
            ("Spirit's refund flag is dropped", ("src/classes/monk/dc_monk_spirit.h", "points, generated);", "points);")),
            ("a zero generation is paid",
             ("src/classes/monk/dc_monk_spirit.h", "points <= 0 ||", "")),
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
    def test_skill_columns_equal_the_value_rows(self):
        skills = {r["skill_name"]: r for r in read("monk_skills.csv")}
        checked = 0
        for row in read("monk_skill_values.csv"):
            if row["rune"] or row["token"] not in ("generated_resource", "cost_resource"):
                continue
            column = "resource_generation" if row["token"] == "generated_resource" else "resource_cost"
            self.assertEqual(float(skills[row["skill"]][column]), float(row["value"]), row["skill"])
            checked += 1
        # four primaries generate, eight skills spend (Dashing Strike spends charges, the rest are free or spend per second)
        self.assertEqual(checked, 4 + sum(1 for r in read("monk_skill_values.csv")
                                         if not r["rune"] and r["token"] == "cost_resource"))
        self.assertEqual(sum(1 for r in read("monk_skill_values.csv")
                             if not r["rune"] and r["token"] == "generated_resource"), 4)

    def test_pool_regen_and_decay_agree_across_the_sheets(self):
        resource = {r["metric"]: r for r in read("monk_resource.csv")}
        self.assertEqual(float(resource["Maximum Spirit (base)"]["value"]), 250)
        self.assertEqual(resource["Decay out of combat"]["value"], "0")
        self.assertTrue(resource["Passive regeneration (base)"]["value"].startswith("0"))
        entry = next(e for e in gcr.registry() if e["d3_class"] == "Monk")
        self.assertEqual((entry["pool"], entry["regen"], entry["decay"], entry["power"], entry["scale"],
                          entry["paragon"], entry["live"]),
                         (250.0, 0.0, "none", "Runic Power", 1, 1.0, True))
        for row in read("monk_base_stats.csv"):
            self.assertEqual(float(row["resource_max"]), 250, row["level"])

    def test_the_records_pay_in_runic_power_points(self):
        self.assertEqual(generate_spells.power_of("Monk"), (6, 1, "runic_power_points"))
        self.assertEqual(float(value("Lashing Tail Kick", "", "cost_resource")), 50)


class Core(unittest.TestCase):
    def test_only_a_death_knight_regenerates_or_decays_runic_power(self):
        text = CORE_PLAYER.read_text(encoding="utf-8")
        guard = re.compile(r"if \(IsClass\(CLASS_DEATH_KNIGHT, CLASS_CONTEXT_ABILITY\)\)\s*Regenerate\(POWER_RUNIC_POWER\);")
        self.assertEqual(len(guard.findall(text)), 1)
        self.assertEqual(len(re.findall(r"Regenerate\(POWER_RUNIC_POWER\)", text)), 1)
        # the planted difference: with the guard gone the same pattern no longer matches
        self.assertIsNone(guard.search(text.replace("IsClass(CLASS_DEATH_KNIGHT, CLASS_CONTEXT_ABILITY))\n            Regenerate",
                                                    "true)\n            Regenerate")))

    def test_the_module_does_not_regenerate_runic_power(self):
        for path in (MODULE / "src").rglob("*.*"):
            if path.suffix in (".cpp", ".h"):
                self.assertNotIn("Regenerate(POWER_RUNIC_POWER", path.read_text(encoding="utf-8", errors="replace"), path)


if __name__ == "__main__":
    unittest.main()
