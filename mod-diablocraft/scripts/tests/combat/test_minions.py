"""The minions a class raises, the shared piece, and the Necromancer's on it (src/combat/dc_minions*.h/.cpp,
src/classes/necromancer/dc_necromancer_pets.*, data/d3/necromancer_summons.csv).

What this proves, and how:

  * **The rules that need no core type.** tests/minions/harness.cpp compiles the real dc_minions_math.h with the sheets'
    and tunables' own numbers: a full group sends its oldest away and never refuses; the keeper raises one at a time, only
    below the wanted number and only when its clock has run; a loss holds the next raise for the return time; a timed
    minion is over at its time and a permanent one never; a skeleton dies on its last hit; a commanded blow carries the
    bonus against the ordered target only; "over two attacks" is two equal shares; the copy has its share of the owner's
    Life. Planted differences in a scratch copy must each make it fail.
  * **The code reads what the sheets state.** Every token dc_necromancer_pets.cpp reads by name is a row of
    necromancer_skill_values.csv for the skill that owns it, with the researched number; every tunable it reads is a row of
    data/tunables/necromancer.csv with the D3 number, or the one named placeholder with none.
  * **The creatures.** necromancer_summons.csv names five summons from donors that exist in the core (no difficulty
    entries, a model), entries no other sheet owns; the migration is the generator's render of the sheet.
  * **The wiring.** The shared piece names no class; its blows are the owner's own Strike; the minions go with the owner
    on logout and floor change; the script is "dc_minion"; both halves are registered in Combat::RegisterScripts.

What it does not prove: anything on a running server, or how the client draws the minions.

    python mod-diablocraft/scripts/tests/combat/test_minions.py
"""

import csv
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
MATH = "src/combat/dc_minions_math.h"
HARNESS = MODULE / "tests/minions/harness.cpp"
SHARED = [MODULE / "src/combat/dc_minions.h", MODULE / "src/combat/dc_minions.cpp", MODULE / MATH]
PETS = MODULE / "src/classes/necromancer/dc_necromancer_pets.cpp"
CORE_SQL = REPO / "azerothcore-wotlk/data/sql/base/db_world"
UPDATES = MODULE / "data/sql/db-world/updates"
MIGRATION = UPDATES / "minions_0001_necromancer_summons.sql"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(skill, token, rune=""):
    rows = [r for r in read(D3 / "necromancer_skill_values.csv")
            if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (skill, rune, token, "")]
    assert len(rows) == 1, (skill, rune, token, len(rows))
    return float(rows[0]["value"])


def tunables():
    return {r["name"]: r for r in read(MODULE / "data/tunables/necromancer.csv")}


def tunable(name):
    return float(tunables()[name]["d3_value"])


def scratch_tree(mutate=None):
    files = {MATH[len("src/"):]: (MODULE / MATH).read_text(encoding="utf-8")}
    if mutate:
        old, new = mutate
        if files[MATH[len("src/"):]].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {MATH}")
        files[MATH[len("src/"):]] = files[MATH[len("src/"):]].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [tunable("minion_mage_cap"), value("Command Skeletons", "max_count"),
               value("Command Skeletons", "interval_seconds"), tunable("minion_skeleton_hits"),
               value("Command Skeletons", "damage_pct"), value("Command Skeletons", "damage_bonus_pct"),
               value("Skeletal Mage", "damage_pct"), value("Skeletal Mage", "duration_seconds"),
               tunable("simulacrum_life_pct"), value("Command Skeletons", "attack_speed_pct", "Frenzy")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 30, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("a full group refuses", ("return {true, true};", "return {false, false};")),
            ("a stay-put kind follows", ("return !staysPut;", "return true;")),
            ("every kind stays put", ("return !staysPut;", "return false;")),
            ("a group one short sends one away", ("alive < cap)", "alive <= cap)")),
            ("a cap of 0 still counts", ("cap == 0 || alive < cap", "alive < cap")),
            ("the keeper raises over the number", ("alive < wanted && now >= nextAt", "alive <= wanted && now >= nextAt")),
            ("the keeper is early", ("now >= nextAt", "now + 1 >= nextAt")),
            ("the keeper is late", ("now >= nextAt", "now > nextAt")),
            ("the interval is lost", ("return now + intervalMs;", "return intervalMs;")),
            ("a loss brings the next one earlier", ("return std::max(nextAt, now + returnMs);", "return now + returnMs;")),
            ("a loss does not wait", ("return std::max(nextAt, now + returnMs);", "return nextAt;")),
            ("a minion goes a moment late", ("now >= bornAt + lifeMs", "now > bornAt + lifeMs")),
            ("a permanent minion ends", ("lifeMs > 0 && now >= bornAt + lifeMs", "now >= bornAt + lifeMs")),
            ("a skeleton dies a hit late", ("taken >= limit", "taken > limit")),
            ("a boost adds nothing", ("return boostPct > 0 ? damagePct * (1.0 + boostPct / 100.0) : damagePct;", "return damagePct;")),
            ("a boost is not a percent of the blow", ("damagePct * (1.0 + boostPct / 100.0)", "damagePct * (1.0 + boostPct)")),
            ("a negative boost cuts the blow", ("return boostPct > 0 ? damagePct", "return true ? damagePct")),
            ("the frenzy speeds every target", ("return commanded && speedPct > 0 ? attacksPerSecond * (1.0 + speedPct / 100.0) : attacksPerSecond;", "return speedPct > 0 ? attacksPerSecond * (1.0 + speedPct / 100.0) : attacksPerSecond;")),
            ("the frenzy is not a percent", ("attacksPerSecond * (1.0 + speedPct / 100.0)", "attacksPerSecond * (1.0 + speedPct)")),
            ("the frenzy slows on a negative number", ("commanded && speedPct > 0 ?", "commanded ?")),
            ("a skeleton with no limit dies", ("limit > 0 && taken >= limit", "taken >= limit")),
            ("every target takes the bonus", ("commanded && bonusPct > 0", "bonusPct > 0")),
            ("the bonus is not a percent", ("bonusPct / 100.0", "bonusPct")),
            ("a hit is the whole skill", ("return totalPct / std::max(1u, hits);", "return totalPct;")),
            ("no attacks divides by none", ("totalPct / std::max(1u, hits)", "totalPct / hits")),
            ("the copy can be dead", ("std::max(1.0, life)", "life")),
            ("the copy's share is a tenth", ("lifePct) / 100.0;", "lifePct) / 10.0;")),
            ("the kind's swing time is ignored", ("return swingMs > 0 ? swingMs : (", "return (")),
            ("every swing time is the owner's rate", ("return swingMs > 0 ? swingMs : (attacksPerSecond > 0 ? 1000.0 / attacksPerSecond : 0.0);", "return attacksPerSecond > 0 ? 1000.0 / attacksPerSecond : 0.0;")),
            ("a swing time of nothing waits for nothing", ("return swingMs > 0 ? swingMs :", "return swingMs >= 0 ? swingMs :")),
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
    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("Skeletal Mage", "damage_pct"), value("Skeletal Mage", "duration_seconds")], [400, 6])
        self.assertEqual([value("Command Skeletons", t) for t in ("damage_pct", "damage_bonus_pct", "interval_seconds", "max_count")],
                         [50, 50, 2, 7])
        self.assertEqual(value("Command Golem", "damage_pct"), 450)
        self.assertEqual(value("Revive", "duration_seconds"), 15)
        self.assertEqual(value("Simulacrum", "duration_seconds"), 15)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = PETS.read_text(encoding="utf-8")
        call = r'Numbers::(?:Num|Get|Own|Inherited)\((?:[^,()]|\([^()]*\))+, "([a-z_]+)"'
        tokens = set(re.findall(call, text))
        self.assertEqual(tokens, {"damage_pct", "duration_seconds", "damage_bonus_pct", "max_count", "interval_seconds",
                                  "attack_speed_pct", "max_stacks_count", "heal_pct"})
        mapped = {(r["skill"], r["rune"], r["token"], r["qualifier"])
                  for r in read(MODULE / "data/generated/spell_value_map.csv")}
        for skill, token in (("Skeletal Mage", "damage_pct"), ("Skeletal Mage", "duration_seconds"),
                             ("Command Skeletons", "damage_pct"), ("Command Skeletons", "damage_bonus_pct"),
                             ("Command Skeletons", "interval_seconds"), ("Command Skeletons", "max_count"),
                             ("Command Golem", "damage_pct"), ("Revive", "duration_seconds"),
                             ("Simulacrum", "duration_seconds")):
            with self.subTest(skill=skill, token=token):
                self.assertIn((skill, "", token, ""), mapped)

    def test_the_skills_the_code_names_are_skills_of_the_sheet(self):
        text = PETS.read_text(encoding="utf-8")
        named = set(re.findall(r'"((?:Skeletal Mage|Revive|Command Skeletons|Command Golem|Simulacrum))"', text))
        sheet = {r["skill"] for r in read(D3 / "necromancer_skill_values.csv")}
        self.assertEqual(named, {"Skeletal Mage", "Revive", "Command Skeletons", "Command Golem", "Simulacrum"})
        self.assertLessEqual(named, sheet)


class Tunables(unittest.TestCase):
    NUMBERS = {
        "minion_mage_cap": "10",
        "minion_revive_cap": "10",
        "minion_skeleton_hits": "20",
        "minion_golem_return_seconds": "10",
        "simulacrum_life_pct": "100",
    }
    # Revive's damage (the Revived Monster Damage Scalar) came from the power file, diablocraft-im7mr.18: tested with Revive
    DECODED = {"revive_damage_pct": "100"}
    # What the pets file once held as constants (diablocraft-jal8h): the tooltip's two attacks, and the keeper's look at the bar
    KEPT = {"minion_mage_attacks": "2", "minion_keeper_poll_seconds": "1"}

    def test_the_rows_hold_the_researched_numbers_and_none_of_alexs(self):
        rows = tunables()
        for name, number in self.NUMBERS.items():
            with self.subTest(name):
                self.assertIn(name, rows)
                self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (number, ""))
                if number:
                    self.assertNotIn("PLACEHOLDER", rows[name]["notes"])
                    self.assertIn("docs/research/necromancer/README.md", rows[name]["notes"])
                else:
                    self.assertTrue(rows[name]["notes"].startswith("PLACEHOLDER for the designer"))
        for name, number in self.DECODED.items():
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (number, ""))
            self.assertNotIn("PLACEHOLDER", rows[name]["notes"])

    def test_the_code_reads_exactly_these(self):
        text = PETS.read_text(encoding="utf-8")
        # the mage's runes (diablocraft-im7mr.13) and Revive's (diablocraft-im7mr.18) read more rows, tested with their skills
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)),
                         set(self.NUMBERS) | set(self.DECODED) | set(self.KEPT) |
                         {"contamination_radius_yards", "skeleton_archer_range_yards", "revive_life_pct",
                          "simulacrum_spawn_yards", "simulacrum_mirrors"})

    def test_the_constants_the_pets_file_held_are_rows_with_todays_values(self):
        rows = tunables()
        for name, number in self.KEPT.items():
            with self.subTest(name):
                self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (number, ""))
                self.assertNotIn("PLACEHOLDER", rows[name]["notes"])
        text = re.sub(r"\s+", " ", PETS.read_text(encoding="utf-8"))
        for gone in ("MageAttacks", "PollMs"):
            self.assertNotIn(gone, text)
        self.assertIn('kind.hitsPerSwing = unsigned(Tune("minion_mage_attacks"));', text)
        self.assertIn('std::uint32_t const pollMs = Millis(Tune("minion_keeper_poll_seconds"));', text)
        self.assertIn("(found->second += diff) < pollMs", text)

    def test_the_mages_attacks_are_the_tooltips_number(self):
        tooltip = [r["full_tooltip_text"] for r in read(D3 / "necromancer_skills.csv") if r["skill_name"] == "Skeletal Mage"][0]
        said = re.search(r"over (\w+) attacks", tooltip)
        self.assertIsNotNone(said, tooltip)
        self.assertEqual(float(tunables()["minion_mage_attacks"]["d3_value"]), {"two": 2, "three": 3}[said.group(1)])

    def test_the_cores_timer_net_is_a_combat_row_the_shared_piece_reads(self):
        rows = {r["name"]: r for r in read(MODULE / "data/tunables/combat.csv")}
        row = rows["minion_timer_net_seconds"]
        self.assertEqual((row["d3_value"], row["value"], row["unit"]), ("1", "", "seconds"))
        self.assertIn("not D3", row["notes"])
        text = re.sub(r"\s+", " ", (MODULE / "src/combat/dc_minions.cpp").read_text(encoding="utf-8"))
        self.assertNotIn("NetMs", text)
        self.assertIn('Millis(DC::Tunables::Get("combat", "minion_timer_net_seconds"))', text)
        self.assertIn("kind.lifeMs + net", text)


class Creatures(unittest.TestCase):
    def sheet(self):
        return read(D3 / "necromancer_summons.csv")

    def test_five_summons_from_real_donors(self):
        rows = self.sheet()
        self.assertEqual([r["summon"] for r in rows],
                         ["Skeletal Mage", "Skeletal Warrior", "Flesh Golem", "Revived Minion", "Simulacrum"])
        self.assertEqual({r["script"] for r in rows}, {"dc_minion"})
        code = PETS.read_text(encoding="utf-8")
        for name, row in zip(("MageEntry", "SkeletonEntry", "GolemEntry", "RevivedEntry", "SimulacrumEntry"), rows):
            self.assertRegex(code, rf"{name} = {row['entry']}\b")
        templates = (CORE_SQL / "creature_template.sql").read_text(encoding="utf-8")
        models = (CORE_SQL / "creature_template_model.sql").read_text(encoding="utf-8")
        for r in rows:
            with self.subTest(r["summon"]):
                row = re.search(rf"^\({r['donor_creature']},(\d+),(\d+),(\d+),", templates, re.M)
                self.assertIsNotNone(row)
                self.assertEqual(row.groups(), ("0", "0", "0"))  # difficulty_entry_1..3: the clone would claim them
                self.assertRegex(models, rf"(?m)^\({r['donor_creature']},0,\d+,")
                self.assertTrue(r["why"])

    def test_no_entry_is_another_summons(self):
        mine = {int(r["entry"]) for r in self.sheet()}
        others = ({int(r["entry"]) for n in ("wizard", "monk", "crusader") for r in read(D3 / f"{n}_summons.csv")} |
                  {int(r["entry"]) for r in read(MODULE / "data/legendary_summons.csv")} | set(range(900100, 900103)))
        self.assertEqual(len(mine), 5)
        self.assertFalse(mine & others)
        self.assertIn("'data/d3/necromancer_summons.csv'",
                      (MODULE / "scripts/generate/legendaries/generate_legendary_summons.py").read_text(encoding="utf-8"))

    def test_the_migration_is_the_generators_render_of_the_sheet(self):
        sys.path.insert(0, str(MODULE / "scripts"))
        import generate_necromancer_summons
        sql = MIGRATION.read_text(encoding="utf-8")
        self.assertEqual(sql, generate_necromancer_summons.render())
        self.assertEqual(sql.count("ScriptName='dc_minion'"), 5)
        for r in self.sheet():
            with self.subTest(r["summon"]):
                self.assertIn(f"SET entry={r['entry']},name='{r['summon']}',subname='',npcflag=0,unit_flags=0,", sql)
                self.assertIn(f"INSERT INTO creature_template_model SELECT {r['entry']},Idx,", sql)

    def test_the_generator_refuses_a_taken_entry_and_a_stranger_script(self):
        sys.path.insert(0, str(MODULE / "scripts"))
        import generate_necromancer_summons
        for field, new in (("entry", "900110"), ("script", "dc_other")):
            with self.subTest(field), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "data/d3").mkdir(parents=True)
                for name in ("wizard_summons.csv", "monk_summons.csv", "crusader_summons.csv"):
                    shutil.copy(D3 / name, root / "data/d3" / name)
                shutil.copy(MODULE / "data/legendary_summons.csv", root / "data/legendary_summons.csv")
                rows = self.sheet()
                rows[0][field] = new
                with (root / "data/d3/necromancer_summons.csv").open("w", encoding="utf-8", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                    writer.writeheader()
                    writer.writerows(rows)
                with self.assertRaises(ValueError):
                    generate_necromancer_summons.rows(root)


class Wiring(unittest.TestCase):
    def test_the_shared_piece_names_no_class(self):
        for path in SHARED:
            text = path.read_text(encoding="utf-8")
            for class_name in ("Necromancer", "Wizard", "Monk", "Crusader", "Barbarian", "Demon Hunter", "Witch Doctor"):
                with self.subTest(file=path.name, name=class_name):
                    self.assertNotIn(class_name, text)

    def test_a_minions_blow_is_the_owners_own_and_goes_with_the_owner(self):
        text = re.sub(r"\s+", " ", (MODULE / "src/combat/dc_minions.cpp").read_text(encoding="utf-8"))
        self.assertIn("Combat::Strike(player, target, kind.record, share)", text)
        self.assertIn('CreatureScript("dc_minion")', text)
        self.assertIn("PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_MAP_CHANGED", text)
        self.assertRegex(text, r"void OnPlayerLogout\(Player\* player\) override \{ ?DismissAll\(player\);")
        self.assertRegex(text, r"void OnPlayerMapChanged\(Player\* player\) override \{ ?DismissAll\(player\);")
        self.assertIn("Expired(Now(), bornAt, kind.lifeMs)", text)
        self.assertIn("Admit(Alive(owner, kind.group), kind.cap)", text)
        self.assertIn("KeeperDue(now, state.nextAt[kind.group], alive, wanted)", text)
        self.assertIn("Combat::AttacksPerSecond(player) * Combat::ItemPowers::PetSpeedFactor(player)", text)

    def test_a_kind_may_fix_its_own_swing_time_and_the_oldest_may_be_sent_away(self):
        text = re.sub(r"\s+", " ", (MODULE / "src/combat/dc_minions.cpp").read_text(encoding="utf-8"))
        self.assertIn("double const wait = SwingMs(aps, kind.swingMs) / (1.0 + std::max(0.0, haste.attackPct) / 100.0); if (wait <= 0 || clock < wait || !InReach(target)) return;", text)
        # the oldest by birth, forgotten at once (its keeper is not held), then sent away; where it stood is the answer
        self.assertIn("if (e.group == group && e.bornAt < bornAt) { bornAt = e.bornAt; oldest = e.guid; }", text)
        self.assertIn("Position const where = creature->GetPosition(); Forget(owner->GetGUID().GetRawValue(), oldest); creature->DespawnOrUnsummon(); return where;", text)
        self.assertIn("if (!creature) return std::nullopt;", text)
        header = (MODULE / "src/combat/dc_minions.h").read_text(encoding="utf-8")
        self.assertIn("double swingMs = 0;", header)
        self.assertIn("std::optional<Position> DismissOldest(Player* owner, std::string_view group);", header)

    def test_both_halves_are_registered(self):
        text = re.sub(r"\s+", " ", (MODULE / "src/combat/dc_combat.cpp").read_text(encoding="utf-8"))
        self.assertIn("Minions::RegisterScripts(); Necromancer::Pets::RegisterScripts();", text)
        internal = (MODULE / "src/combat/dc_combat_internal.h").read_text(encoding="utf-8")
        self.assertIn('#include "../classes/necromancer/dc_necromancer_pets.h"', internal)
        self.assertIn('#include "dc_minions.h"', internal)

    def test_the_kinds_the_class_defines_are_the_ones_the_calls_raise(self):
        text = PETS.read_text(encoding="utf-8")
        defined = set(re.findall(r'Minions::Define\("([a-z_]+)"', text))
        raised = set(re.findall(r'Minions::(?:Raise|Keep)\(\s*(?:owner|player), "([a-z_]+)"', text))
        self.assertEqual(defined, {"skeletal_mage", "command_skeleton", "command_golem", "revived_minion", "simulacrum",
                                   "simulacrum_bone"})
        self.assertEqual(raised, defined)


if __name__ == "__main__":
    unittest.main()
