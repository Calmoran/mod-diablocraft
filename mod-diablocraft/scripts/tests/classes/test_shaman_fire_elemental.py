"""Shaman Fire Elemental and its five runes (src/classes/shaman/dc_shaman_fire_elemental.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/shaman_fire_elemental/harness.cpp compiles the real dc_shaman_fire_elemental.h with the
    sheets' and tunables' own names and numbers: each rune name is its rune; Primal Fire Elemental lasts longer and every other rune the
    skill's seconds (Magma Elemental's own second is the knock down's); **a tick of the aura and an echo deal above 0** and the ticks
    add up to the sheet's damage per second; a chained echo is its share of the echo; Water Elemental heals its percent of the maximum
    Life per second and chills through the next tick; only a Secondary cast is echoed, and only while the elemental stands. Mutations
    planted in a scratch copy must each make it fail.
  * **Every damage it deals passes its own percent.** Every record states a duration, so the loader gives the cast's own hit none
    (DamageWaits) and the elemental's aura, echo and crash are strikes with their percent; the test pins that the skill claims no hit
    and that each strike passes its percent.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of shaman_skill_values.csv for Fire Elemental (or the
    rune that states it); the two numbers the draft does not give are rows of data/tunables/combat.csv, rendered into the tunables
    migration current_migration.txt names.
  * **The wiring.** The class dispatch answers the cast seam; one elemental per Shaman at a time (a new cast takes a new stamp); the
    elemental is skill damage and no creature.

What it does not prove: anything on a running server. The aura, the echo, the crash and each rune's effect are
docs/test-diablocraft-xnrvn.34.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_shaman_fire_elemental.py
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
HEADERS = ["src/classes/shaman/dc_shaman_fire_elemental.h", "src/combat/dc_periodic_strike.h"]
HEADER = HEADERS[0]
HARNESS = MODULE / "tests/shaman_fire_elemental/harness.cpp"
CODE = MODULE / "src/classes/shaman/dc_shaman_fire_elemental.cpp"
SKILL = "Fire Elemental"
RUNES = ["Primal Fire Elemental", "Meteor Call", "Storm Elemental", "Water Elemental", "Magma Elemental"]
TUNABLES = {"fire_elemental_tick_seconds": "1", "fire_elemental_chain_radius_yards": "15"}


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(rune, token, qualifier=""):
    rows = [r for r in read(D3 / "shaman_skill_values.csv") if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, qualifier)]
    assert len(rows) == 1, (rune, token, qualifier, len(rows))
    return float(rows[0]["value"])


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
    numbers = RUNES + [value("Primal Fire Elemental", "duration_seconds"), value("", "duration_seconds"), value("Magma Elemental", "duration_seconds"),
                       value("", "damage_pct", "aura"), value("", "damage_pct", "echo"), value("Storm Elemental", "damage_share_pct"),
                       value("Water Elemental", "life_regen_pct"), tunable("fire_elemental_tick_seconds")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 10, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", ('if (name == "Storm Elemental")\n            return Rune::StormElemental;', 'if (name == "Storm Elemental")\n            return Rune::WaterElemental;')),
            ("Primal Fire Elemental lasts the skill's seconds", ("return rune == Rune::PrimalFireElemental ? ownSeconds : baseSeconds;", "return baseSeconds;")),
            ("every rune lasts its own seconds", ("return rune == Rune::PrimalFireElemental ? ownSeconds : baseSeconds;", "return ownSeconds ? ownSeconds : baseSeconds;")),
            ("a tick deals nothing", ("return perSecondPct > 0 && tickSeconds > 0 ? perSecondPct * tickSeconds : 0.0;", "return 0.0;")),
            ("a tick deals the whole second's damage", ("return perSecondPct > 0 && tickSeconds > 0 ? perSecondPct * tickSeconds : 0.0;", "return perSecondPct > 0 && tickSeconds > 0 ? perSecondPct : 0.0;")),
            ("a chained echo is the whole echo", ("return echoPct > 0 && sharePct > 0 ? echoPct * sharePct / 100.0 : 0.0;", "return echoPct;")),
            ("a chained echo deals nothing", ("return echoPct > 0 && sharePct > 0 ? echoPct * sharePct / 100.0 : 0.0;", "return 0.0;")),
            ("Water Elemental heals once a tick whatever the tick", ("return maxLife > 0 && pct > 0 && tickSeconds > 0 ? maxLife * pct / 100.0 * tickSeconds : 0.0;", "return maxLife > 0 && pct > 0 && tickSeconds > 0 ? maxLife * pct / 100.0 : 0.0;")),
            ("the chill ends before the next tick", ("return tickSeconds > 0 ? tickSeconds * 2.0 : 0.0;", "return tickSeconds > 0 ? tickSeconds * 0.5 : 0.0;")),
            ("a Primary cast is echoed", ('return up && category == "Secondary";', "return up;")),
            ("a Secondary cast is echoed with no elemental up", ('return up && category == "Secondary";', 'return category == "Secondary";')),
            ("it stands a millisecond long", ("return nowMs < untilMs;", "return nowMs <= untilMs;")),
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
    def test_the_five_runes(self):
        self.assertEqual(runes(), RUNES)

    def test_every_record_states_a_duration_so_the_casts_own_hit_is_none(self):
        rows = [r for r in read(D3 / "shaman_skill_values.csv") if r["skill"] == SKILL]
        self.assertTrue(any(r["rune"] == "" and r["token"] == "duration_seconds" for r in rows))
        # and the base states no plain damage: only the aura's and the echo's
        self.assertEqual({r["qualifier"] for r in rows if r["rune"] == "" and r["token"] == "damage_pct"}, {"aura", "echo"})

    def test_every_token_the_code_reads_is_a_row_of_the_sheet(self):
        code = CODE.read_text(encoding="utf-8")
        reads = set(re.findall(r'Numbers::Num\((?:spellId|BaseId\(\)), "([a-z_]+)"', code))
        self.assertGreaterEqual(len(reads), 8, reads)
        held = {r["token"] for r in read(D3 / "shaman_skill_values.csv") if r["skill"] == SKILL}
        for token in reads:
            self.assertIn(token, held, token)

    def test_the_numbers_are_the_drafts(self):
        self.assertEqual([value("", "cooldown_seconds"), value("", "radius_yards"), value("", "damage_pct", "aura"), value("", "damage_pct", "echo"),
                          value("", "duration_seconds"), value("Primal Fire Elemental", "duration_seconds"), value("Meteor Call", "damage_pct"),
                          value("Storm Elemental", "target_count"), value("Storm Elemental", "damage_share_pct"), value("Storm Elemental", "attack_speed_pct"),
                          value("Water Elemental", "chill_pct"), value("Water Elemental", "life_regen_pct"), value("Magma Elemental", "radius_yards"),
                          value("Magma Elemental", "duration_seconds")],
                         [90, 12, 400, 1200, 15, 22, 2400, 4, 60, 10, 40, 1, 8, 1])

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


class Creature(unittest.TestCase):
    """The look: an untargetable creature with a stock Fire Elemental model that follows the Shaman, in minions_0007."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(MODULE / "scripts/generate/classes"))
        import generate_shaman_elemental_summons as generator
        cls.generator = generator
        cls.rows = {r["summon"]: r for r in generator.rows(MODULE)}  # also checks the entries are not taken

    def test_the_sheet_row_is_the_stock_greater_fire_elemental_for_the_skill(self):
        row = self.rows["Fire Elemental"]
        self.assertEqual((row["skill"], row["rune"], row["entry"], row["donor_creature"], row["script"]), (SKILL, "", "900190", "15438", "dc_minion"))

    def test_the_code_raises_the_sheets_entry(self):
        self.assertIn(f"constexpr std::uint32_t Entry = {self.rows['Fire Elemental']['entry']};", CODE.read_text(encoding="utf-8"))

    def test_the_migration_is_the_generators_render_and_the_creature_cannot_be_selected(self):
        migration = (MODULE / "data/sql/db-world/updates/minions_0007_shaman_elemental_summons.sql").read_text(encoding="utf-8")
        self.assertEqual(migration, self.generator.render(MODULE))
        self.assertIn("unit_flags=33554432,unit_flags2=0,", migration)
        self.assertIn("ScriptName='dc_minion'", migration)
        self.assertIn("WHERE entry=15438;", migration)
        self.assertIn("faction=35", migration)
        self.assertIn("lootid=0", migration)

    def test_the_minions_migration_follows_the_totems(self):
        # minions_0006 is the totems' (World's); this one numbers above it.
        self.assertEqual("minions_0007_shaman_elemental_summons.sql", self.generator.MIGRATION)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/shaman/dc_shaman.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_cast_seam(self):
        self.assertIn("Bloodlust::Cast(player, spellId, targets); FireElemental::Cast(player, spellId, targets);", self.dispatch)

    def test_the_skill_claims_no_hit_and_every_strike_passes_its_percent(self):
        self.assertNotIn("BasePct", self.code)
        self.assertIn("Combat::Strike(player, enemy, spellId, pct, true);", self.code)
        self.assertIn('double const pct = AuraPerTick(Numbers::Num(spellId, "damage_pct", "aura"), tick);', self.code)
        self.assertIn('Combat::Strike(player, enemy, spellId, Numbers::Num(spellId, "damage_pct"));', self.code)
        self.assertIn('double const pct = Numbers::Num(spellId, "damage_pct", "echo");', self.code)
        self.assertIn("if (!ticks) return;", self.code)

    def test_the_creature_is_raised_with_the_elemental_and_sent_away_with_it(self):
        start = self.code[self.code.index("void Start("):self.code.index("} // namespace bool Is(")]
        self.assertIn("Minions::Dismiss(player, Group); Minions::Raise(player, Group, player->GetPosition());", start)
        end = self.code[self.code.index("void End("):self.code.index("void Chain(")]
        self.assertIn("PutSpeed(player, 0); Minions::Dismiss(player, Group);", end)
        define = self.code[self.code.index("void RegisterScripts()"):]
        self.assertIn("Minions::Define(Group,", define)
        self.assertIn("kind.entry = Entry;", define)
        self.assertIn("kind.cap = 1;", define)
        # it deals nothing itself: no damage is set on the kind
        self.assertNotIn("damagePct", define)
        self.assertNotIn("auraPct", define)
        self.assertIn("Bloodlust::RegisterScripts(); FireElemental::RegisterScripts();", self.dispatch)

    def test_one_elemental_at_a_time_and_its_damage_is_the_shamans_not_a_pets(self):
        start = self.code[self.code.index("void Start("):self.code.index("} // namespace bool Is(")]
        self.assertIn("Standing& elemental = standing[key]; stamp = elemental.stamp = ++stamps;", start)
        tick = self.code[self.code.index("void Tick("):self.code.index("void Crash(")]
        self.assertIn("found == standing.end() || found->second.stamp != stamp", tick)
        self.assertIn("!player->IsInWorld() || !player->IsAlive() || player->GetMap() != elemental.map", tick)
        for forbidden in ("SummonCreature", "TempSummon", "ScriptedAI", "damagePct"):
            self.assertNotIn(forbidden, self.code)

    def test_the_attack_speed_ends_with_the_elemental(self):
        end = self.code[self.code.index("void End("):self.code.index("void Chain(")]
        self.assertIn("standing.erase(found); } PutSpeed(player, 0);", end)

    def test_the_lifetime_and_the_summon(self):
        start = self.code[self.code.index("void Start("):]
        self.assertIn('Lifetime(rune, Numbers::Num(spellId, "duration_seconds"), Numbers::Num(BaseId(), "duration_seconds"))', start)
        self.assertIn("if (rune == Rune::MeteorCall) Crash(player, spellId);", start)
        self.assertIn('PutSpeed(player, rune == Rune::StormElemental ? Numbers::Num(spellId, "attack_speed_pct") : 0.0);', start)

    def test_the_aura_burns_what_is_in_reach_and_the_water_elemental_chills_and_heals(self):
        tick = self.code[self.code.index("void Tick("):self.code.index("void Crash(")]
        self.assertIn('Combat::Enemies(player, spellId, player->GetPosition(), Numbers::Num(spellId, "radius_yards"))', tick)
        self.assertIn('if (elemental.rune == Rune::WaterElemental && enemy->IsAlive()) Chill(player, enemy, Numbers::Num(spellId, "chill_pct"), ChillSeconds(intervalMs / 1000.0));', tick)
        self.assertIn('if (elemental.rune == Rune::WaterElemental) Heal(player, spellId, HealPerTick(double(player->GetMaxHealth()), Numbers::Num(spellId, "life_regen_pct"), intervalMs / 1000.0));', tick)

    def test_the_echo_of_each_secondary_cast(self):
        cast = self.code[self.code.index("void Cast("):]
        self.assertIn("if (!Echoes(Classes::CategoryOf(spellId), up) || targets.empty()) return;", cast)
        echo = self.code[self.code.index("void Echo("):self.code.index("void Tick(")]
        self.assertIn('Combat::Enemies(player, spellId, target->GetPosition(), Numbers::Num(spellId, "radius_yards"))', echo)
        self.assertIn('Stun(player, enemy, Numbers::Num(spellId, "duration_seconds"));', echo)
        self.assertIn("Combat::Strike(player, target, spellId, pct); Chain(player, target, spellId, pct);", echo)
        chain = self.code[self.code.index("void Chain("):self.code.index("void Echo(")]
        self.assertIn('Tune("fire_elemental_chain_radius_yards")', chain)
        self.assertIn('Combat::Strike(player, enemy, spellId, ChainedPct(echoPct, Numbers::Num(spellId, "damage_share_pct")));', chain)


if __name__ == "__main__":
    unittest.main()
