"""Shaman Elemental Lash and its five runes (src/classes/shaman/dc_shaman_elemental_lash.h and .cpp, dc_shaman_free_lava_burst.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/shaman_elemental_lash/harness.cpp compiles the real dc_shaman_elemental_lash.h with the
    sheets' own rune names and numbers: each rune name is its rune; only Searing Lash states its hit beside a burn; a Lava Surge comes
    up below its chance; Stonewhip adds Maelstrom for its crowd and more, nothing for fewer, and pushes back no elite. Mutations
    planted in a scratch copy must each make it fail.
  * **The records.** Thunder Lash's cone reaches 30 yards where the skill and the other runes keep 20: a `cone_enemies` row of
    skill_targeting.csv, rendered into the newest combat migration and the generated spell shells.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of shaman_skill_values.csv for Elemental Lash (or the
    rune that states it); the burn's tick is a row of data/tunables/combat.csv, rendered into the tunables migration
    current_migration.txt names.
  * **The wiring.** The class dispatch answers the seams; the Maelstrom file passes the enemies a cast hit on to the Lash; the engine
    passes the count; Searing Lash's hit is read from its "hit" row, its burn is a periodic strike and Burning; Lava Surge gives the
    free Lava Burst; Stonewhip spares elites; Frost Lash chills.

What it does not prove: anything on a running server. The cone, the burn, the push, the chill and the Maelstrom are
docs/test-diablocraft-xnrvn.14.md's, live. Nothing spends the free Lava Burst yet: Lava Burst is its own bead.

    python mod-diablocraft/scripts/tests/classes/test_shaman_elemental_lash.py
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
HEADERS = ["src/classes/shaman/dc_shaman_elemental_lash.h"]
HEADER = HEADERS[0]
HARNESS = MODULE / "tests/shaman_elemental_lash/harness.cpp"
CODE = MODULE / "src/classes/shaman/dc_shaman_elemental_lash.cpp"
SKILL = "Elemental Lash"
RUNES = ["Searing Lash", "Lava Surge", "Stonewhip", "Frost Lash", "Thunder Lash"]
TUNABLE = ("elemental_lash_burn_tick_seconds", "0.5")


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(rune, token, qualifier=""):
    rows = [r for r in read(D3 / "shaman_skill_values.csv") if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, qualifier)]
    assert len(rows) == 1, (rune, token, qualifier, len(rows))
    return float(rows[0]["value"])


def waiting_runes():
    """The runes whose record the loader would give no hit (dc_combat_internal.h DamageWaits): the record or its skill states a duration."""
    waits = {"dot_duration_seconds", "duration_seconds", "duration_minutes"}
    rows = [r for r in read(D3 / "shaman_skill_values.csv") if r["skill"] == SKILL]
    states = lambda rune: any(r["rune"] == rune and (r["token"] in waits or (r["token"], r["qualifier"]) == ("damage_pct", "ramp")) for r in rows)
    return [rune for rune in [""] + RUNES if states("") or states(rune)]


def runes():
    rows = sorted((r for r in read(D3 / "shaman_runes.csv") if r["skill_name"] == SKILL), key=lambda r: r["rune_slot"])
    return [r["rune_name"] for r in rows]


def scratch_tree(mutate=None):
    files = {path[len("src/"):]: (MODULE / path).read_text(encoding="utf-8") for path in HEADERS}
    if mutate:
        old, new = mutate
        key = HEADER[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {HEADER}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    numbers = RUNES + [value("Lava Surge", "proc_chance_pct"), value("Stonewhip", "gain_resource"), value("Stonewhip", "nearby_enemy_count"), ",".join(waiting_runes())]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 7, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", ('if (name == "Stonewhip")\n            return Rune::Stonewhip;', 'if (name == "Stonewhip")\n            return Rune::FrostLash;')),
            ("every rune states its hit apart", ("return rune == Rune::SearingLash;", "return rune != Rune::None;")),
            ("Searing Lash reads the skill's hit", ("return rune == Rune::SearingLash;", "return false;")),
            ("a Lava Surge always comes up", ("return chancePct > 0 && roll * 100.0 < chancePct;", "return chancePct > 0;")),
            ("a Lava Surge comes up at the chance", ("roll * 100.0 < chancePct", "roll * 100.0 <= chancePct")),
            ("Stonewhip needs one enemy more", ("double(enemies) >= needed", "double(enemies) > needed")),
            ("Stonewhip needs one enemy less", ("double(enemies) >= needed", "double(enemies) + 1 >= needed")),
            ("Stonewhip adds for a crowd of any size", ("return needed > 0 && gain > 0 && double(enemies) >= needed ? gain : 0.0;", "return gain > 0 ? gain : 0.0;")),
            ("Stonewhip pushes an elite", ("return !elite;", "return true;")),
            ("Stonewhip pushes nothing", ("return !elite;", "return false;")),
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
    def test_the_record_the_loader_would_give_no_hit_is_searing_lash(self):
        self.assertEqual(waiting_runes(), ["Searing Lash"])

    def test_the_five_runes(self):
        self.assertEqual(runes(), RUNES)

    def test_every_token_the_code_reads_is_a_row_of_the_sheet(self):
        code = CODE.read_text(encoding="utf-8")
        reads = set(re.findall(r'Numbers::Num\(spellId, "([a-z_]+)"', code))
        self.assertGreaterEqual(len(reads), 7, reads)
        held = {r["token"] for r in read(D3 / "shaman_skill_values.csv") if r["skill"] == SKILL}
        for token in reads:
            self.assertIn(token, held, token)

    def test_the_numbers_are_the_drafts(self):
        self.assertEqual([value("", "damage_pct"), value("", "generated_resource"), value("", "radius_yards"), value("", "cone_angle_degrees"),
                          value("Searing Lash", "damage_pct", "hit"), value("Searing Lash", "damage_pct", "dot"),
                          value("Searing Lash", "dot_duration_seconds"), value("Lava Surge", "proc_chance_pct"), value("Stonewhip", "damage_pct"),
                          value("Stonewhip", "knockback_yards"), value("Stonewhip", "gain_resource"), value("Stonewhip", "nearby_enemy_count"),
                          value("Frost Lash", "damage_pct"), value("Frost Lash", "chill_pct"), value("Frost Lash", "chill_duration_seconds"),
                          value("Thunder Lash", "damage_pct"), value("Thunder Lash", "radius_yards", "new"), value("Thunder Lash", "radius_yards", "base")],
                         [230, 10, 20, 60, 220, 240, 4, 6, 270, 6, 3, 3, 240, 40, 3, 220, 30, 20])

    def test_the_tunable_is_a_row_of_the_combat_sheet_and_of_the_migration(self):
        name, number = TUNABLE
        rows = {r["name"]: r for r in read(MODULE / "data/tunables/combat.csv")}
        migration_name = (MODULE / "data/tunables/current_migration.txt").read_text(encoding="utf-8").strip()
        migration = (MODULE / "data/sql/db-world/updates" / migration_name).read_text(encoding="utf-8")
        self.assertEqual(migration, (MODULE / "data/generated" / migration_name).read_text(encoding="utf-8"))
        self.assertEqual(rows[name]["value"], number)
        self.assertTrue(rows[name]["notes"].strip())
        self.assertIn(f"('combat', '{name}', NULL, {float(number)},", migration)
        self.assertEqual(set(re.findall(r'Tunables::Get\("combat", "([a-z_]+)"\)', CODE.read_text(encoding="utf-8"))), {name})

    def test_thunder_lashs_cone_reaches_further(self):
        rows = {r["skill"]: r for r in read(D3 / "skill_targeting.csv")}
        self.assertEqual((rows[SKILL]["target_type"], rows[SKILL]["range_yards"]), ("cone_enemies", "20"))
        thunder = rows[f"{SKILL} - Thunder Lash"]
        self.assertEqual((thunder["target_type"], thunder["range_yards"]), ("cone_enemies", "30"))
        self.assertEqual(float(thunder["range_yards"]), value("Thunder Lash", "radius_yards", "new"))
        for rune in RUNES:
            if rune != "Thunder Lash":
                self.assertNotIn(f"{SKILL} - {rune}", rows, rune)

    def test_the_newest_combat_migration_gives_the_cone_its_reach(self):
        shells = {r["name"]: r["spell_id"] for r in read(MODULE / "data/generated/spell_shells.csv")}
        thunder, base = shells[f"{SKILL} - Thunder Lash"], shells[SKILL]
        sql = (MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8")
        self.assertEqual(sql.count(f"VALUES ({thunder},'cone_enemies','NUMERIC',30.0,30.0,0.0);"), 1)
        self.assertEqual(sql.count(f"VALUES ({base},'cone_enemies','NUMERIC',20.0,20.0,0.0);"), 1)
        migration = MODULE / "data/sql/db-world/updates/combat_0133_shaman_elemental_lash_thunder_lash_reach.sql"
        self.assertIn(f"VALUES ({thunder},'cone_enemies','NUMERIC',30.0,30.0,0.0);", migration.read_text(encoding="utf-8"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/shaman/dc_shaman.cpp").read_text(encoding="utf-8"))
        self.maelstrom = re.sub(r"\s+", " ", (MODULE / "src/classes/shaman/dc_shaman_maelstrom.cpp").read_text(encoding="utf-8"))
        self.resolve = re.sub(r"\s+", " ", (MODULE / "src/combat/dc_combat_resolve.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertIn("FlameShock::Landed(player, target, spellId); ElementalLash::Landed(player, target, spellId);", self.dispatch)
        self.assertIn("if (auto flameShock = FlameShock::BasePct(spellId)) return flameShock; if (auto elementalLash = ElementalLash::BasePct(spellId)) return elementalLash;", self.dispatch)

    def test_the_cast_passes_the_enemies_it_hit_to_the_lash(self):
        self.assertIn("void Connected(Player* player, std::uint32_t spellId, unsigned enemies)", self.maelstrom)
        self.assertIn("Gain(player, spellId, points); ElementalLash::Connected(player, spellId, enemies);", self.maelstrom)
        self.assertEqual(self.resolve.count("Shaman::Connected(player, spellId, enemies);"), 1)

    def test_searing_lash_reads_its_hit_and_burns(self):
        base = self.code[self.code.index("std::optional<double> BasePct("):self.code.index("void Landed(")]
        self.assertIn("if (!Is(spellId) || !HitIsTagged(RuneAt(spellId))) return std::nullopt;", base)
        self.assertIn('return Numbers::Num(spellId, "damage_pct", "hit");', base)
        searing = self.code[self.code.index("case Rune::SearingLash:"):self.code.index("case Rune::LavaSurge:")]
        self.assertIn('Burning::Burn(player, target, spellId, Numbers::Num(spellId, "damage_pct", "dot"), seconds, Tunables::Get("combat", "elemental_lash_burn_tick_seconds"));', searing)
        self.assertIn('double const seconds = Numbers::Num(spellId, "dot_duration_seconds");', searing)

    def test_lava_surge_makes_the_next_lava_burst_free(self):
        surge = self.code[self.code.index("case Rune::LavaSurge:"):self.code.index("case Rune::Stonewhip:")]
        self.assertIn('if (Procs(frand(0.0f, 1.0f), Numbers::Num(spellId, "proc_chance_pct"))) FreeLavaBurst::Grant(player);', surge)

    def test_stonewhip_pushes_and_adds_for_a_crowd(self):
        whip = self.code[self.code.index("case Rune::Stonewhip:"):self.code.index("case Rune::FrostLash:")]
        self.assertIn('if (Pushes(IsElite(target))) Abilities::Knockback(player, target, Numbers::Num(spellId, "knockback_yards"));', whip)
        connected = self.code[self.code.index("void Connected("):]
        self.assertIn("RuneAt(spellId) != Rune::Stonewhip", connected)
        self.assertIn('CrowdGain(enemies, Numbers::Num(spellId, "nearby_enemy_count"), Numbers::Num(spellId, "gain_resource"))', connected)

    def test_frost_lash_chills(self):
        frost = self.code[self.code.index("case Rune::FrostLash:"):self.code.index("default:")]
        self.assertIn('Chill(player, target, Numbers::Num(spellId, "chill_pct"), Numbers::Num(spellId, "chill_duration_seconds"));', frost)

    def test_the_free_lava_burst_is_a_state_per_shaman(self):
        state = re.sub(r"\s+", " ", (MODULE / "src/classes/shaman/dc_shaman_free_lava_burst.cpp").read_text(encoding="utf-8"))
        self.assertIn("pending.insert(player->GetGUID().GetRawValue());", state)
        self.assertIn("pending.erase(player->GetGUID().GetRawValue());", state)
        self.assertIn("return pending.count(player->GetGUID().GetRawValue()) != 0;", state)


if __name__ == "__main__":
    unittest.main()
