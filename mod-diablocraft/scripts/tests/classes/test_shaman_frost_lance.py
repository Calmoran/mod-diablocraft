"""Shaman Frost Lance and its five runes (src/classes/shaman/dc_shaman_frost_lance.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/shaman_frost_lance/harness.cpp compiles the real dc_shaman_frost_lance.h with the
    sheets' and tunables' own names and numbers: each rune name is its rune; the shards', burn's and arc's damage leaves the
    lance's own hit the skill's; Icefury stacks to its most and each stack adds its percent for its seconds; the shards' cone
    opens behind the first enemy, as long and as wide as its tunables; a freeze waits for its cooldown; only Frostfire Bolt burns
    and only a chilled enemy. Mutations planted in a scratch copy must each make it fail.
  * **The records.** Shattering Lance and Glacial Boulder stop on the first enemy where the skill and the other runes pierce:
    two `single_enemy` rows of skill_targeting.csv, rendered into the newest combat migration, the generated spell shells and
    the client Spell.dbc.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of shaman_skill_values.csv for Frost Lance (or
    the rune that states it); the four numbers the draft does not give are rows of data/tunables/combat.csv, rendered into the
    tunables migration current_migration.txt names.
  * **The wiring.** The class dispatch answers the seams; every rune keeps the chill and reads the enemy's chill before it gives
    its own; each rune's code is what the draft says.

What it does not prove: anything on a running server. The lance, the shards, the burn, the freeze, the arc and the stacks are
docs/test-diablocraft-xnrvn.15.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_shaman_frost_lance.py
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
HEADERS = ["src/classes/shaman/dc_shaman_frost_lance.h", "src/combat/dc_damage_buckets.h"]
HEADER = HEADERS[0]
HARNESS = MODULE / "tests/shaman_frost_lance/harness.cpp"
CODE = MODULE / "src/classes/shaman/dc_shaman_frost_lance.cpp"
SKILL = "Frost Lance"
RUNES = ["Icefury", "Shattering Lance", "Frostfire Bolt", "Glacial Boulder", "Thunderhail"]
TUNABLES = {
    "frost_lance_burn_tick_seconds": "0.5",
    "frost_lance_shatter_cone_yards": "15",
    "frost_lance_shatter_cone_degrees": "60",
    "frost_lance_arc_radius_yards": "15",
}


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


def tunable(name):
    return float({r["name"]: r for r in read(MODULE / "data/tunables/combat.csv")}[name]["value"])


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
    numbers = RUNES + [value("Icefury", "max_stacks_count"), value("Icefury", "damage_bonus_pct"), value("Icefury", "duration_seconds"),
                       tunable("frost_lance_shatter_cone_yards"), tunable("frost_lance_shatter_cone_degrees"),
                       value("Glacial Boulder", "internal_cooldown_seconds"), ",".join(waiting_runes())]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 12, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", ('if (name == "Frostfire Bolt")\n            return Rune::FrostfireBolt;', 'if (name == "Frostfire Bolt")\n            return Rune::Icefury;')),
            ("Icefury's hit is left to the loader", ("rune == Rune::Thunderhail ||\n               rune == Rune::Icefury;", "rune == Rune::Thunderhail;")),
            ("Thunderhail hits for its arc", ("rune == Rune::Thunderhail ||\n               rune == Rune::Icefury;", "rune == Rune::Icefury;")),
            ("Glacial Boulder hits for the skill's", ("rune == Rune::Thunderhail ||\n               rune == Rune::Icefury;", "rune == Rune::Thunderhail ||\n               rune == Rune::Icefury || rune == Rune::GlacialBoulder;")),
            ("Icefury never stops stacking", ("return std::min(stacks + gained, maxStacks);", "return stacks + gained;")),
            ("Icefury stacks nothing", ("return std::min(stacks + gained, maxStacks);", "return std::min(stacks, maxStacks);")),
            ("a stack adds once", ("return perStackPct > 0 ? double(stacks) * perStackPct : 0.0;", "return perStackPct > 0 && stacks ? perStackPct : 0.0;")),
            ("the stacks hold a millisecond long", ("return nowMs < untilMs;", "return nowMs <= untilMs;")),
            ("the cone is a half circle", ("return cosine >= std::cos(degrees * 0.5 * 3.14159265358979323846 / 180.0);", "return cosine >= 0;")),
            ("the cone reaches too far", ("distance > length", "distance > length * 2")),
            ("the cone includes the front", ("return cosine >= std::cos(", "return std::fabs(cosine) >= std::cos(")),
            ("the cone is twice as wide", ("degrees * 0.5 * 3.14159265358979323846", "degrees * 1.0 * 3.14159265358979323846")),
            ("a freeze never waits", ("return lastMs == 0 || nowMs >= lastMs + std::uint64_t(cooldownSeconds * 1000.0);", "return true;")),
            ("a freeze waits a millisecond too long", ("nowMs >= lastMs + std::uint64_t", "nowMs > lastMs + std::uint64_t")),
            ("every rune burns", ("return rune == Rune::FrostfireBolt && chilled;", "return chilled;")),
            ("Frostfire Bolt burns any enemy", ("return rune == Rune::FrostfireBolt && chilled;", "return rune == Rune::FrostfireBolt;")),
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
    def test_the_records_the_loader_would_give_no_hit_are_icefury_and_frostfire_bolt(self):
        self.assertEqual(waiting_runes(), ["Icefury", "Frostfire Bolt"])

    def test_the_five_runes(self):
        self.assertEqual(runes(), RUNES)

    def test_every_token_the_code_reads_is_a_row_of_the_sheet(self):
        code = CODE.read_text(encoding="utf-8")
        reads = set(re.findall(r'Numbers::Num\((?:spellId|BaseId\(\)|id), "([a-z_]+)"', code))
        self.assertGreaterEqual(len(reads), 10, reads)
        held = {r["token"] for r in read(D3 / "shaman_skill_values.csv") if r["skill"] == SKILL}
        for token in reads:
            self.assertIn(token, held, token)

    def test_the_numbers_are_the_drafts(self):
        self.assertEqual([value("", "damage_pct"), value("", "generated_resource"), value("", "chill_pct"), value("", "chill_duration_seconds"),
                          value("Icefury", "max_stacks_count"), value("Icefury", "damage_bonus_pct"), value("Icefury", "duration_seconds"),
                          value("Shattering Lance", "projectile_count"), value("Shattering Lance", "damage_pct"), value("Frostfire Bolt", "damage_pct"),
                          value("Frostfire Bolt", "dot_duration_seconds"), value("Glacial Boulder", "damage_pct"),
                          value("Glacial Boulder", "freeze_duration_seconds"), value("Glacial Boulder", "internal_cooldown_seconds"),
                          value("Thunderhail", "target_count"), value("Thunderhail", "damage_pct")],
                         [250, 12, 30, 2, 5, 6, 6, 6, 180, 200, 3, 300, 1, 6, 1, 80])

    def test_the_tunables_are_rows_of_the_combat_sheet_and_of_the_migration(self):
        rows = {r["name"]: r for r in read(MODULE / "data/tunables/combat.csv")}
        name = (MODULE / "data/tunables/current_migration.txt").read_text(encoding="utf-8").strip()
        migration = (MODULE / "data/sql/db-world/updates" / name).read_text(encoding="utf-8")
        self.assertEqual(migration, (MODULE / "data/generated" / name).read_text(encoding="utf-8"))
        for tunable_name, number in TUNABLES.items():
            with self.subTest(tunable_name):
                self.assertEqual(rows[tunable_name]["value"], number)
                self.assertTrue(rows[tunable_name]["notes"].strip())
                self.assertIn(f"('combat', '{tunable_name}', NULL, {float(number)},", migration)

    def test_the_code_reads_only_tunables_the_sheet_has(self):
        used = set(re.findall(r'Tune\("([a-z_]+)"\)', CODE.read_text(encoding="utf-8")))
        self.assertEqual(used, set(TUNABLES))

    def test_two_runes_stop_on_the_first_enemy(self):
        rows = {r["skill"]: r for r in read(D3 / "skill_targeting.csv")}
        self.assertEqual((rows[SKILL]["target_type"], rows[SKILL]["range_yards"], rows[SKILL]["width_yards"]), ("line_pierce", "30", "3"))
        for rune in ("Shattering Lance", "Glacial Boulder"):
            row = rows[f"{SKILL} - {rune}"]
            self.assertEqual((row["target_type"], row["range_yards"]), ("single_enemy", "30"), rune)
        for rune in ("Icefury", "Frostfire Bolt", "Thunderhail"):
            self.assertNotIn(f"{SKILL} - {rune}", rows, rune)

    def test_the_newest_combat_migration_and_the_shells_give_the_records_their_shape(self):
        shells = {r["name"]: r["spell_id"] for r in read(MODULE / "data/generated/spell_shells.csv")}
        sql = (MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8")
        migration = (MODULE / "data/sql/db-world/updates/combat_0134_shaman_frost_lance_stops_piercing.sql").read_text(encoding="utf-8")
        for rune in ("Shattering Lance", "Glacial Boulder"):
            line = f"VALUES ({shells[f'{SKILL} - {rune}']},'single_enemy','NUMERIC',30.0,0.0,0.0);"
            self.assertEqual(sql.count(line), 1, rune)
            self.assertIn(line, migration, rune)
        for rune in ("", " - Icefury", " - Frostfire Bolt", " - Thunderhail"):
            line = f"VALUES ({shells[SKILL + rune]},'line_pierce','NUMERIC',30.0,0.0,3.0);"
            self.assertEqual(sql.count(line), 1, rune)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/shaman/dc_shaman.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertIn("ElementalLash::Landed(player, target, spellId); FrostLance::Landed(player, target, spellId);", self.dispatch)
        self.assertIn("FlameShock::Multipliers(player, target, spellId, out); FrostLance::Multipliers(player, spellId, out);", self.dispatch)
        self.assertIn("if (auto elementalLash = ElementalLash::BasePct(spellId)) return elementalLash; if (auto frostLance = FrostLance::BasePct(spellId)) return frostLance;", self.dispatch)

    def test_the_lances_own_hit_is_the_skills_where_the_rune_states_another_damage(self):
        base = self.code[self.code.index("std::optional<double> BasePct("):self.code.index("void Landed(")]
        self.assertIn("if (!Is(spellId) || !HitIsSkills(RuneAt(spellId))) return std::nullopt;", base)
        self.assertIn('return Numbers::Num(BaseId(), "damage_pct");', base)

    def test_every_rune_keeps_the_chill_and_reads_the_chill_before_giving_its_own(self):
        landed = self.code[self.code.index("void Landed("):self.code.index("switch (rune)")]
        self.assertLess(landed.index("Chilled(player, target)"), landed.index("Chill(player, target,"))
        self.assertIn('Chill(player, target, Numbers::Num(spellId, "chill_pct"), Numbers::Num(spellId, "chill_duration_seconds"));', landed)
        self.assertIn("if (striking || !player || !target || !Is(spellId)) return;", landed)

    def test_each_rune_runs_its_own_code(self):
        self.assertIn("case Rune::ShatteringLance: Shatter(player, target, spellId); break;", self.code)
        self.assertIn("case Rune::GlacialBoulder: FreezeOnce(player, target, spellId); break;", self.code)
        self.assertIn("case Rune::Thunderhail: Arc(player, target, spellId); break;", self.code)

    def test_icefury_stacks_on_a_chilled_enemy_and_raises_cold_hits(self):
        self.assertIn("case Rune::Icefury: if (chilled) GainStack(player); break;", self.code)
        stack = self.code[self.code.index("void GainStack("):self.code.index("void Shatter(")]
        self.assertIn('Stacked(held, 1, unsigned(Numbers::Num(id, "max_stacks_count")))', stack)
        self.assertIn("Holds(now, fury.until) ? fury.stacks : 0", stack)
        self.assertIn('fury.until = now + std::uint64_t(Numbers::Num(id, "duration_seconds") * 1000.0);', stack)
        multipliers = self.code[self.code.index("void Multipliers("):]
        self.assertIn("info->GetSchoolMask() != SPELL_SCHOOL_MASK_FROST", multipliers)
        self.assertIn('IcefuryBonus(stacks, Numbers::Num(IcefuryId(), "damage_bonus_pct"))', multipliers)
        self.assertIn('AddFactor(out, "Icefury", bonus);', multipliers)

    def test_shattering_lance_sends_its_shards_behind_the_first_enemy(self):
        shatter = self.code[self.code.index("void Shatter("):self.code.index("void Arc(")]
        self.assertIn('Tune("frost_lance_shatter_cone_yards")', shatter)
        self.assertIn('Tune("frost_lance_shatter_cone_degrees")', shatter)
        self.assertIn("enemy == first || !BehindInCone(player->GetPositionX(), player->GetPositionY(), first->GetPositionX(), first->GetPositionY(), enemy->GetPositionX(), enemy->GetPositionY(), length, degrees)", shatter)
        self.assertIn('auto const shards = std::size_t(Numbers::Num(spellId, "projectile_count"));', shatter)
        self.assertIn("if (behind.size() > shards) behind.resize(shards);", shatter)
        self.assertIn('Strikes(player, enemy, spellId, Numbers::Num(spellId, "damage_pct"));', shatter)

    def test_frostfire_bolt_burns_a_chilled_enemy(self):
        fire = self.code[self.code.index("case Rune::FrostfireBolt:"):self.code.index("case Rune::GlacialBoulder:")]
        self.assertIn("if (Burns(rune, chilled))", fire)
        self.assertIn('Burning::Burn(player, target, spellId, Numbers::Num(spellId, "damage_pct"), seconds, Tune("frost_lance_burn_tick_seconds"));', fire)

    def test_glacial_boulder_freezes_once_per_cooldown(self):
        freeze = self.code[self.code.index("void FreezeOnce("):self.code.index("bool Is(")]
        self.assertIn('Numbers::Num(spellId, "internal_cooldown_seconds")', freeze)
        self.assertIn("if (!Freezes(now, last, Numbers::Num(spellId, \"internal_cooldown_seconds\"))) return; last = now;", freeze)
        self.assertIn('Shaman::Freeze(player, target, Numbers::Num(spellId, "freeze_duration_seconds"));', freeze)

    def test_thunderhail_arcs_from_each_enemy_to_the_nearest_other(self):
        arc = self.code[self.code.index("void Arc("):self.code.index("void FreezeOnce(")]
        self.assertIn('Tune("frost_lance_arc_radius_yards")', arc)
        self.assertIn("near.erase(std::remove(near.begin(), near.end(), from), near.end());", arc)
        self.assertIn("return from->GetExactDist(a) < from->GetExactDist(b);", arc)
        self.assertIn('Numbers::Num(spellId, "target_count")', arc)
        self.assertIn('Strikes(player, enemy, spellId, Numbers::Num(spellId, "damage_pct"));', arc)


if __name__ == "__main__":
    unittest.main()
