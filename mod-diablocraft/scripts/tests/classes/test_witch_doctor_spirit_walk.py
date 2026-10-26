"""Spirit Walk and its five runes (src/classes/witch_doctor/dc_witch_doctor_spirit_walk.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/witch_doctor_spirit_walk/harness.cpp compiles the real
    dc_witch_doctor_spirit_walk.h with the sheets' own rune names and numbers: each rune name is its rune; a walk runs at the
    base speed and only Severance adds its percent on top; Honored Guest's and Healing Journey's share of a maximum is the
    percent of it and nothing for no maximum, no percent or a negative number; the cooldown is pushed back by the walk's
    seconds in milliseconds (Jaunt's longer walk delays longer). Eight mutations planted in a scratch copy (two runes share a
    name, every rune gets Severance's speed, the base speed is lost, a negative speed adds, the share is not divided by a
    hundred, a negative share pays, the delay is in seconds, a negative walk delays) must each make it fail.
  * **The code reads what the sheets state.** Every token dc_witch_doctor_spirit_walk.cpp reads by name is a row of
    witch_doctor_skill_values.csv for Spirit Walk, the generated value map says whose record holds it, and the numbers are
    the researched ones: a 2 second walk (Jaunt 3), Severance 100% movement speed, Umbral Shock 750% weapon damage within
    10 yards, Honored Guest 20% of maximum Mana, Healing Journey 15% of maximum Life. The one number the sheets do not carry,
    the base run speed, is a witchdoctor tunable row with the power file's value.
  * **The sheet is D3's.** The numbers are the ones the power file holds (Power/Witchdoctor_SpiritWalk.pow, read with
    scripts/decode_pow.py): duration 2 plus 1, run speed 0.5 and 1.0, damage 7.5 in 10 yards, 20% Mana, 15% Life, cooldown 10.
  * **The wiring.** The dispatch hands Spirit Walk's spells to its file; the walk absorbs every point of damage for its seconds
    (`Invulnerable`, the stock Power Word: Shield set past any hit, as the Monk's Serenity does: the client's Spell.dbc says that
    record 17 is one SCHOOL_ABSORB effect of every school); the walk's control immunity goes on and comes off
    under the rune's own key after the walk's time; Umbral Shock erupts at the place the body was left, once the walk is over,
    and only for its rune; the cooldown is pushed back on every rune; Spirit Walk is a self-targeted skill, so the engine's own
    hit loop never hits anything with the Umbral Shock number.

What it does not prove: anything on a running server, whether the walk's immunity and absorb stop each effect of the core, and
that an enemy loses sight of the Witch Doctor. The body left standing (the power file's 'Dummy Health') is test_witch_doctor_spirit_walk_body.py's.

    python mod-diablocraft/scripts/tests/classes/test_witch_doctor_spirit_walk.py
"""

import csv
import re
import struct
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
HEADER = "src/classes/witch_doctor/dc_witch_doctor_spirit_walk.h"
SOURCES = [HEADER, "tests/witch_doctor_spirit_walk/harness.cpp"]
CODE = MODULE / "src/classes/witch_doctor/dc_witch_doctor_spirit_walk.cpp"
DISPATCH = MODULE / "src/classes/witch_doctor/dc_witch_doctor.cpp"
SKILL = "Spirit Walk"
TUNABLE = "spirit_walk_run_speed_pct"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(rune, token, qualifier=""):
    rows = [r for r in read(D3 / "witch_doctor_skill_values.csv")
            if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, qualifier)]
    assert len(rows) == 1, (rune, token, qualifier, len(rows))
    return float(rows[0]["value"])


def tunable():
    rows = [r for r in read(MODULE / "data/tunables/witchdoctor.csv") if r["name"] == TUNABLE]
    assert len(rows) == 1
    return rows[0]


def runes():
    rows = sorted((r for r in read(D3 / "witch_doctor_runes.csv") if r["skill_name"] == SKILL), key=lambda r: r["rune_slot"])
    return [r["rune_name"] for r in rows]


def scratch_tree(mutate=None):
    files = {source[len("src/"):]: (MODULE / source).read_text(encoding="utf-8")
             for source in SOURCES if source.startswith("src/")}
    if mutate:
        path, old, new = mutate
        key = path[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([MODULE / "tests/witch_doctor_spirit_walk/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [float(tunable()["d3_value"]), value("Severance", "movement_speed_pct"), value("Honored Guest", "gain_pct"),
               value("Healing Journey", "heal_pct"), value("", "duration_seconds"), value("Jaunt", "duration_seconds")]
    return harness_env.run([str(binary)] + runes() + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 16, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        speed = "return std::max(0.0, basePct) + (rune == Rune::Severance ? std::max(0.0, severancePct) : 0.0);"
        share = "return maximum > 0 && pct > 0 ? maximum * pct / 100.0 : 0.0;"
        delay = "return std::uint64_t(std::max(0.0, walkSeconds) * 1000.0 + 0.5);"
        mutations = [
            ("two runes share a name", (HEADER, "return Rune::HealingJourney;", "return Rune::HonoredGuest;")),
            ("every rune gets Severance's speed", (HEADER, speed, speed.replace("rune == Rune::Severance", "true"))),
            ("the base speed is lost", (HEADER, speed, speed.replace("std::max(0.0, basePct) + ", ""))),
            ("a negative speed adds", (HEADER, speed, speed.replace("std::max(0.0, severancePct)", "severancePct"))),
            ("the share is not divided by a hundred", (HEADER, share, share.replace(" / 100.0", ""))),
            ("a negative share pays", (HEADER, share, share.replace("maximum > 0 && pct > 0", "maximum > 0"))),
            ("the delay is in seconds", (HEADER, delay, delay.replace(" * 1000.0 + 0.5", ""))),
            ("a negative walk delays", (HEADER, delay, delay.replace("std::max(0.0, walkSeconds)", "(walkSeconds < 0 ? -walkSeconds : walkSeconds)"))),
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
        self.assertEqual(runes(), ["Severance", "Jaunt", "Umbral Shock", "Honored Guest", "Healing Journey"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual((value("", "cooldown_seconds"), value("", "duration_seconds")), (10, 2))
        self.assertEqual(value("Severance", "movement_speed_pct"), 100)
        self.assertEqual(value("Jaunt", "duration_seconds"), 3)
        self.assertEqual((value("Umbral Shock", "damage_pct"), value("Umbral Shock", "radius_yards")), (750, 10))
        self.assertEqual(value("Honored Guest", "gain_pct"), 20)
        self.assertEqual(value("Healing Journey", "heal_pct"), 15)

    def test_the_numbers_are_the_power_files(self):
        out = subprocess.run([sys.executable, str(MODULE / "scripts/decode_pow.py"), "power", "Witchdoctor_SpiritWalk"],
                             capture_output=True, text=True)
        if out.returncode:
            raise unittest.SkipTest("no D3 power files on this machine")
        sf = {}
        for line in out.stdout.splitlines():
            found = re.match(r"\s*SF_(\d+) '([^']*)' = (.*)$", line)
            if found:
                sf[int(found.group(1))] = found.group(3).strip()
        self.assertEqual(float(sf[12]), value("", "duration_seconds"))                        # Base: Duration
        modifier = float(re.search(r"\?\s*([\d.]+)", sf[5]).group(1))                         # B: Duration Modifier, 'Rune_B ?1 : 0'
        self.assertEqual(float(sf[12]) + modifier, value("Jaunt", "duration_seconds"))
        self.assertEqual(float(sf[7]), value("", "cooldown_seconds"))                         # Base: Cooldown
        self.assertEqual(float(sf[16]) * 100, float(tunable()["d3_value"]))                   # Run Speed Increase
        self.assertEqual(float(sf[1]) * 100, value("Severance", "movement_speed_pct"))        # A: Movement speed
        self.assertEqual(float(sf[6]) * 100, value("Umbral Shock", "damage_pct"))             # C: Damage
        self.assertEqual(float(sf[8]), value("Umbral Shock", "radius_yards"))                 # C: Damage Radius
        self.assertEqual(float(sf[9]), value("Honored Guest", "gain_pct"))                    # D: the share of Mana
        self.assertEqual(float(sf[10]) * 100, value("Healing Journey", "heal_pct"))           # E: Health Gain

    def test_the_tunable_is_one_row_and_is_rendered(self):
        row = tunable()
        self.assertEqual((row["d3_value"], row["value"], row["unit"]), ("50", "", "percent"))
        self.assertIn(f"('witchdoctor', '{TUNABLE}', 50.0,", (MODULE / "data/generated" / (MODULE / "data/tunables/current_migration.txt").read_text().strip()).read_text(encoding="utf-8"))

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        call = r'Numbers::(?:Num|Get|Own|Inherited)\((?:[^,()]|\([^()]*\))+, "([a-z_]+)"'
        tokens = set(re.findall(call, text))
        sheet_tokens = {r["token"] for r in read(D3 / "witch_doctor_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"duration_seconds", "radius_yards", "damage_pct", "movement_speed_pct", "gain_pct", "heal_pct"})
        self.assertEqual(set(re.findall(r'Tune\("([a-z_]+)"\)', text)), {TUNABLE, "spirit_walk_body_life_pct"})   # the body's Life is its own test's
        mapped = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune in [""] + runes():
            with self.subTest(rune=rune):
                self.assertIn((rune, "duration_seconds", ""), mapped)       # the walk's time reaches every record
        for rune, token in (("Severance", "movement_speed_pct"), ("Umbral Shock", "damage_pct"),
                            ("Umbral Shock", "radius_yards"), ("Honored Guest", "gain_pct"), ("Healing Journey", "heal_pct")):
            with self.subTest(rune=rune, token=token):
                self.assertIn((rune, token, ""), mapped)


class Wiring(unittest.TestCase):
    def test_the_walk_absorbs_all_damage_for_its_seconds(self):
        text = " ".join(CODE.read_text(encoding="utf-8").split())
        self.assertIn("Invulnerable(player, seconds);", text)
        effects = " ".join((MODULE / "src/classes/witch_doctor/dc_witch_doctor_effects.cpp").read_text(encoding="utf-8").split())
        self.assertIn("constexpr std::uint32_t ShieldHold = 17;", effects)
        self.assertIn("shield->SetMaxDuration(int32(seconds * 1000)); shield->SetDuration(int32(seconds * 1000));", effects)
        self.assertIn("effect->ChangeAmount(std::numeric_limits<std::int32_t>::max());", effects)
        self.assertIn("if (!player || !player->IsAlive() || seconds <= 0) return;", effects)

    def test_the_dispatch_hands_spirit_walk_to_its_file(self):
        text = DISPATCH.read_text(encoding="utf-8")
        self.assertIn("SpiritWalk::Cast(player, spellId);", text)
        self.assertIn('#include "dc_witch_doctor_spirit_walk.h"', text)

    def test_the_immunity_goes_on_and_off_under_the_runes_key_after_the_walk(self):
        text = " ".join(CODE.read_text(encoding="utf-8").split())
        self.assertIn("ControlImmunity::Set(player, spellId, true);", text)
        self.assertIn("AddEventAtOffset([player, spellId] { ControlImmunity::Set(player, spellId, false); }, ms);", text)
        self.assertIn("auto const ms = std::chrono::milliseconds(CooldownDelayMs(seconds));", text)

    def test_umbral_shock_erupts_where_the_body_was_left_once_the_walk_is_over(self):
        text = " ".join(CODE.read_text(encoding="utf-8").split())
        self.assertRegex(text, r"case Rune::UmbralShock: player->m_Events\.AddEventAtOffset\(\[player, spellId, body = player->GetPosition\(\)\]"
                               r" \{ Erupt\(player, spellId, body\); \}, ms\); break;")
        self.assertIn('Enemies(player, spellId, body, Numbers::Num(spellId, "radius_yards"))', text)
        self.assertIn('Strike(player, enemy, spellId, Numbers::Own(spellId, "damage_pct"));', text)

    def test_the_cooldown_is_pushed_back_on_every_rune(self):
        text = " ".join(CODE.read_text(encoding="utf-8").split())
        self.assertIn("for (auto const& ability : Shells::Abilities) if (Skill == ability.skill && "
                      "player->GetSpellCooldownDelay(ability.id)) player->ModifySpellCooldown(ability.id, "
                      "int32(CooldownDelayMs(seconds)));", text)

    def test_the_skill_is_self_targeted_so_the_engine_hits_nobody_with_the_eruptions_number(self):
        rows = [r for r in read(D3 / "skill_targeting.csv") if r["skill"] == SKILL]
        self.assertEqual([r["target_type"] for r in rows], ["self"])
        engine = (MODULE / "src/combat/dc_combat_internal.h").read_text(encoding="utf-8")
        self.assertIn('return type == "self" || type == "self_allies" || type == "self_summon";', engine)


class StockRecords(unittest.TestCase):
    def test_power_word_shield_is_one_absorb_of_every_school(self):
        dbc = REPO / "azerothcore-wotlk/build/server/data/dbc/Spell.dbc"
        schema = REPO / "azerothcore-wotlk/data/sql/base/db_world/spell_dbc.sql"
        if not dbc.is_file() or not schema.is_file():
            raise unittest.SkipTest("no client Spell.dbc")
        columns, inside = [], False
        for line in schema.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("CREATE TABLE `spell_dbc`"):
                inside = True
            elif inside and line.startswith(")"):
                break
            elif inside and line.strip().startswith("`"):
                columns.append(line.strip().split("`")[1])
        data = dbc.read_bytes()
        _magic, count, fields, size, _strings = struct.unpack("<4sIIII", data[:20])
        for i in range(count):
            row = struct.unpack_from("<%dI" % fields, data, 20 + i * size)
            if row[0] == 17:
                record = dict(zip(columns, row))
                break
        else:
            self.fail("no spell 17")
        self.assertEqual((6, 0, 0), (record["Effect_1"], record["Effect_2"], record["Effect_3"]))   # SPELL_EFFECT_APPLY_AURA only
        self.assertEqual(69, record["EffectAura_1"])                                                # SPELL_AURA_SCHOOL_ABSORB
        self.assertEqual(127, record["EffectMiscValue_1"])                                          # every school


if __name__ == "__main__":
    unittest.main()
