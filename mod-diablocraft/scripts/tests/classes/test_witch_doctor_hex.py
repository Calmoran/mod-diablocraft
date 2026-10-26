"""Hex and its five runes (src/classes/witch_doctor/dc_witch_doctor_hex_math.h and dc_witch_doctor_hex.cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/witch_doctor_hex/harness.cpp compiles the real dc_witch_doctor_hex_math.h with the
    sheets' own rune names and numbers: each rune name is its rune; every rune but the Angry Chicken has the Shaman and the
    skill and every rune but the Toad and the chicken hex the group; a cast is one chain of cycles, the first at once, that
    runs the cycles the Shaman's time holds and no more, and a chain ends with its own Shaman; the group ends at its radius; Hedge Magic heals the sheet's number at the sheet's level and its share of it below; the
    Toad's poison is the whole percent over whole ticks; the Angry Chicken explodes once, on the next press or when its time is over;
    Unstable Form remembers a hexed enemy until its hex ends, once, and forgets those that ran out. Twenty mutations planted in a
    scratch copy must each make it fail.
  * **The code reads what the sheets state.** Every token dc_witch_doctor_hex.cpp reads by name is a row of
    witch_doctor_skill_values.csv for Hex, the generated value map says whose record holds it, and every tunable it reads is a
    row of witchdoctor.csv rendered into the migration.
  * **The sheet is D3's.** The numbers are the ones Power/Witchdoctor_Hex.pow holds (decode_pow.py): a 12 second Shaman, a 4 second
    hex, radius 12 and search radius 30, the Angry Chicken's 2 seconds, 50% speed, 1350% and 12 yards, Unstable Form's 500% and 8 yards,
    Hedge Magic's 6% of the Healing table (the sheet's 32185 at level 70) and 40 yards, the Toad's 5 seconds, 15% and swallow, Jinx's
    15%, the cooldown 15. The four numbers the sources left open are the Architect's rulings (a cycle every 4 seconds, a 50% slow,
    the next press or the 2 seconds' end, once a second), tunables of the sheet.
  * **The Shaman is a creature.** witch_doctor_hex_summons.csv names it (entry 900174), the generator's output is the migration
    (minions_0004), and the pets' own migration is as it was.
  * **The stock auras are what the helpers say.** The client's Spell.dbc: "Polymorph: Chicken" (228) is a transform into the chicken, a
    silence and a cut of the damage done with no interrupt flag; "Pacify" (10730) is one MOD_PACIFY; "Chicken" (3245) is one TRANSFORM
    into the same chicken; "Dazed" (50259) is one MOD_DECREASE_SPEED.
  * **The wiring.** The engine asks the class after a ground cast, before the core's check (the second press) and at startup; the
    dispatch hands each to Hex's file; the Shaman is one minion of its own group; the cycle hexes the group round the nearest enemy.

What it does not prove: anything on a running server, how the Shaman looks (the donor is the Imp the Fetish uses), and that the core
lets a chicken be hexed (elites that refuse control).

    python mod-diablocraft/scripts/tests/classes/test_witch_doctor_hex.py
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
HEADER = "src/classes/witch_doctor/dc_witch_doctor_hex_math.h"
SOURCES = [HEADER, "tests/witch_doctor_hex/harness.cpp"]
CODE = MODULE / "src/classes/witch_doctor/dc_witch_doctor_hex.cpp"
EFFECTS = MODULE / "src/classes/witch_doctor/dc_witch_doctor_effects.cpp"
DISPATCH = MODULE / "src/classes/witch_doctor/dc_witch_doctor.cpp"
RESOLVE = MODULE / "src/combat/dc_combat_resolve.cpp"
COMBAT = MODULE / "src/combat/dc_combat.cpp"
SKILL = "Hex"
RUNES = ["Toad of Hugeness", "Angry Chicken", "Unstable Form", "Hedge Magic", "Jinx"]
CHICKEN_FORM, PACIFY, POLYMORPH_CHICKEN, DAZED = 3245, 10730, 228, 50259


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(rune, token):
    rows = [r for r in read(D3 / "witch_doctor_skill_values.csv") if (r["skill"], r["rune"], r["token"]) == (SKILL, rune, token)]
    assert len(rows) == 1, (rune, token, len(rows))
    return float(rows[0]["value"])


def tunable(name):
    rows = [r for r in read(MODULE / "data/tunables/witchdoctor.csv") if r["name"] == name]
    assert len(rows) == 1, name
    return rows[0]


def number(name):
    row = tunable(name)
    return float(row["value"] or row["d3_value"])


def healing(level):
    return float([r for r in read(D3 / "healing_table.csv") if int(r["level"]) == level][0]["value"])


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
    binary = harness_env.build([MODULE / "tests/witch_doctor_hex/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("", "duration_seconds"), number("hex_cycle_seconds"), number("hex_group_radius_yards"),
               value("Hedge Magic", "heal_life"), healing(60), healing(70), value("Toad of Hugeness", "damage_pct"),
               value("Toad of Hugeness", "dot_duration_seconds"), number("hex_toad_tick_seconds"),
               value("Angry Chicken", "duration_seconds")]
    return harness_env.run([str(binary)] + RUNES + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 30, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", 'return Rune::Jinx;\n        return Rune::None;', 'return Rune::HedgeMagic;\n        return Rune::None;'),
            ("the chicken has the Shaman", "return rune != Rune::AngryChicken;", "return true;"),
            ("the toad hexes", "return RaisesShaman(rune) && rune != Rune::ToadOfHugeness;", "return RaisesShaman(rune);"),
            ("a cycle is dropped", "return next < lifeMs ?", "return next + cycleMs < lifeMs ?"),
            ("a cycle runs as the Shaman goes", "return next < lifeMs ?", "return next <= lifeMs ?"),
            ("the chain never ends", "return next < lifeMs ?", "return true ?"),
            ("a zero cycle repeats", "if (cycleMs == 0)\n            return std::nullopt;\n        std::uint64_t const next", "std::uint64_t const next"),
            ("a chain runs on in the next Shaman", "return chainShaman != 0 && chainShaman == standingShaman;", "return standingShaman != 0;"),
            ("a chain of no Shaman stands", "return chainShaman != 0 && chainShaman == standingShaman;", "return chainShaman == standingShaman;"),
            ("the group runs past its radius", "return radius > 0 && distance <= radius;", "return radius > 0 && distance <= radius + 1;"),
            ("the heal ignores the level", "sheetHeal * tableAtLevel / tableAtSheetLevel", "sheetHeal"),
            ("a tick too few", "std::floor(seconds / tickSeconds + 1e-9)", "std::floor(seconds / tickSeconds - 1)"),
            ("a tick pays the whole percent", "return ticks && totalPct > 0 ? totalPct / ticks : 0.0;", "return ticks && totalPct > 0 ? totalPct : 0.0;"),
            ("the chicken explodes on a press twice", "            live = false;\n            return true;\n        }\n\n        // The look",
             "            return true;\n        }\n\n        // The look"),
            ("a press at the end moment explodes", "if (!live || now >= until)", "if (!live || now > until)"),
            ("the time's end is early", "if (!live || now < until)", "if (!live || now < until - 1)"),
            ("an enemy that dies as its hex ends explodes", "found->second > now", "found->second >= now"),
            ("a second hex does not renew", "end = std::max(end, now + ms);", "end = end ? end : now + ms;"),
            ("the list is never pruned", "it = it->second <= now ? until.erase(it) : std::next(it);", "++it;"),
            ("a chicken of no time is live", "live = ms > 0;", "live = true;"),
        ]
        for label, old, new in mutations:
            with self.subTest(label):
                try:
                    tree = scratch_tree((HEADER, old, new))
                except AssertionError as error:
                    self.fail(str(error))
                out = build_and_run(tree)
                self.assertNotEqual(out.returncode, 0, f"{label} was not caught: {out.stdout[-500:]}")


class Sheets(unittest.TestCase):
    def test_the_runes(self):
        rows = sorted((r for r in read(D3 / "witch_doctor_runes.csv") if r["skill_name"] == SKILL), key=lambda r: r["rune_slot"])
        self.assertEqual([r["rune_name"] for r in rows], RUNES)

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual((value("", "cooldown_seconds"), value("", "duration_seconds")), (15, 12))
        self.assertEqual([value("Toad of Hugeness", t) for t in ("damage_pct", "dot_duration_seconds", "damage_taken_pct")], [750, 5, 15])
        self.assertEqual([value("Angry Chicken", t) for t in ("duration_seconds", "damage_pct", "radius_yards")], [2, 1350, 12])
        self.assertEqual([value("Unstable Form", t) for t in ("damage_pct", "radius_yards")], [500, 8])
        self.assertEqual(value("Hedge Magic", "heal_life"), 32185)
        self.assertEqual(value("Jinx", "damage_taken_pct"), 15)

    def test_the_numbers_are_the_power_file(self):
        out = subprocess.run([sys.executable, str(MODULE / "scripts/decode_pow.py"), "power", "Witchdoctor_Hex"], capture_output=True, text=True)
        if out.returncode:
            raise unittest.SkipTest("no D3 power files on this machine")
        sf = {}
        for line in out.stdout.splitlines():
            m = re.match(r"\s*SF_(\d+) '([^']*)' = (.*)$", line)
            if m:
                sf[int(m.group(1))] = m.group(3).strip()
        self.assertEqual(float(sf[0]), value("", "duration_seconds"))                              # Fetish Duration
        self.assertEqual(float(sf[7]), number("hex_duration_seconds"))                             # Hex Duration
        self.assertEqual(float(sf[8]), number("hex_target_search_yards"))                          # Hex Target Search Radius
        self.assertEqual(float(sf[19]), number("hex_group_radius_yards"))                          # Hex Radius
        self.assertEqual(float(sf[17]), value("", "cooldown_seconds"))                             # Base: Cooldown
        self.assertEqual(float(sf[5]), value("Angry Chicken", "duration_seconds"))                 # B: Self Hex Duration
        self.assertEqual(float(sf[6]) * 100, number("hex_angry_chicken_speed_pct"))                # B: Movement Speed Increase
        self.assertEqual(float(sf[9]), value("Angry Chicken", "radius_yards"))                     # B: AOE Radius
        self.assertEqual(float(sf[13]) * 100, value("Angry Chicken", "damage_pct"))                # B: Damage Salar
        self.assertEqual(float(sf[10]), value("Unstable Form", "radius_yards"))                    # C: Explode Area
        self.assertEqual(float(sf[11]) * 100, value("Unstable Form", "damage_pct"))                # C: Explode Damage
        self.assertEqual(float(re.search(r"\?\s*([\d.]+)", sf[12]).group(1)) * 100, value("Jinx", "damage_taken_pct"))   # E: Damage Modifier
        self.assertEqual(float(sf[16]), number("hex_hedge_magic_yards"))                           # D: Heal search radius
        self.assertEqual(round(0.06 * healing(70)), value("Hedge Magic", "heal_life"))             # D: Heal Amount = 6% of the Healing table
        self.assertIn("0.06", sf[15])
        self.assertEqual(float(sf[20]), value("Toad of Hugeness", "dot_duration_seconds"))         # A: DoT Duration
        self.assertEqual(float(sf[21]) * 100, value("Toad of Hugeness", "damage_taken_pct"))       # A: Big Toad Damage Amplification
        self.assertEqual(float(sf[23]), number("hex_toad_swallow_seconds"))                        # A: Big Toad Swallow Duration

    def test_the_four_open_numbers_are_the_architects_rulings(self):
        self.assertEqual((tunable("hex_cycle_seconds")["d3_value"], tunable("hex_cycle_seconds")["value"]), ("", "4"))
        self.assertEqual((tunable("hex_toad_slow_pct")["d3_value"], tunable("hex_toad_slow_pct")["value"]), ("", "50"))
        self.assertEqual((tunable("hex_hedge_magic_interval_seconds")["d3_value"], tunable("hex_hedge_magic_interval_seconds")["value"]), ("", "1"))
        for name in ("hex_cycle_seconds", "hex_toad_slow_pct", "hex_hedge_magic_interval_seconds"):
            self.assertNotIn("placeholder", tunable(name)["notes"].lower())

    def test_every_tunable_the_code_reads_is_a_rendered_row(self):
        text = CODE.read_text(encoding="utf-8")
        names = set(re.findall(r'Tune\("([a-z_]+)"\)', text))
        self.assertTrue({"hex_cycle_seconds", "hex_duration_seconds", "hex_target_search_yards", "hex_group_radius_yards",
                         "hex_toad_slow_pct", "hex_toad_swallow_seconds", "hex_toad_tick_seconds",
                         "hex_angry_chicken_speed_pct", "hex_hedge_magic_interval_seconds", "hex_hedge_magic_yards",
                         "fetish_life_pct"} <= names)
        migration = (MODULE / "data/generated" / (MODULE / "data/tunables/current_migration.txt").read_text().strip()).read_text(encoding="utf-8")
        for name in sorted(names):
            with self.subTest(name=name):
                self.assertIn(f"('witchdoctor', '{name}',", migration)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        call = r'Numbers::(?:Num|Get|Own|Inherited)\((?:[^,()]|\([^()]*\))+, "([a-z_]+)"'
        tokens = set(re.findall(call, text))
        sheet_tokens = {r["token"] for r in read(D3 / "witch_doctor_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"duration_seconds", "dot_duration_seconds", "damage_pct", "damage_taken_pct", "heal_life", "radius_yards"})
        mapped = {(r["rune"], r["token"]) for r in read(MODULE / "data/generated/spell_value_map.csv") if r["skill"] == SKILL}
        for rune in [""] + RUNES:
            self.assertIn((rune, "duration_seconds"), mapped)       # the Shaman's seconds reach every record


class Creature(unittest.TestCase):
    def test_the_shaman_is_one_row_and_one_migration(self):
        rows = read(D3 / "witch_doctor_hex_summons.csv")
        self.assertEqual([(r["summon"], r["skill"], r["entry"], r["donor_creature"], r["script"]) for r in rows],
                         [("Fetish Shaman", "Hex", "900174", "416", "dc_minion")])
        self.assertIn("constexpr std::uint32_t ShamanEntry = 900174;", CODE.read_text(encoding="utf-8"))
        sys.path.insert(0, str(MODULE / "scripts/generate/classes"))
        import generate_witch_doctor_summons as gen
        sql = (MODULE / "data/sql/db-world/updates/minions_0004_witch_doctor_hex_summons.sql").read_text(encoding="utf-8")
        self.assertEqual(sql, gen.render(MODULE, gen.HEX_SHEET))
        self.assertIn("SET entry=900174,", sql)
        self.assertIn("lootid=0,pickpocketloot=0,skinloot=0", sql)

    def test_the_pets_migration_is_as_it_was(self):
        sql = (MODULE / "data/sql/db-world/updates/minions_0003_witch_doctor_summons.sql").read_text(encoding="utf-8")
        self.assertNotIn("900174", sql)
        self.assertEqual(sql.count("ScriptName='dc_minion'"), 4)


def one_chain_problems(source):
    """What is wrong with how dc_witch_doctor_hex.cpp schedules the Shaman's cycles and heals: a cast starts exactly one chain of
    cycles (and not a loop of them, each of which would go on by itself), each cycle asks NextCycle for the next, and every
    chain finds its Shaman only through ShamanOf, which ends it when the Shaman standing is not the one the cast raised."""
    text = " ".join(source.split())
    problems = []
    cast = text[text.index("void Cast(Player* player"):text.index("bool Press(Player* player")]
    if " for (" in cast or "while (" in cast:
        problems.append("Cast loops: every pass starts a chain of its own")
    if cast.count("Cycle(player, spellId, rune, chain, 0)") != 1:
        problems.append("Cast does not start exactly one chain of cycles at 0")
    if "std::uint64_t const chain = shaman->GetGUID().GetRawValue();" not in cast:
        problems.append("the chain is not the guid of the Shaman the cast raised")
    if "HealAllies(player, spellId, chain)" not in cast:
        problems.append("Hedge Magic's heals are not tied to the cast's Shaman")
    cycle = text[text.index("void Cycle(Player* owner"):text.index("void Explode(")]
    if "NextCycle(elapsedMs, cycleMs," not in cycle or cycle.count("Cycle(owner, spellId, rune, chain, *next)") != 1:
        problems.append("a cycle does not ask NextCycle for exactly one next cycle")
    if "Creature* shaman = ShamanOf(owner, chain);" not in cycle:
        problems.append("a cycle finds its Shaman without its chain")
    heal = text[text.index("void HealAllies(Player* owner"):text.index("void Cycle(Player* owner")]
    if "Creature* shaman = ShamanOf(owner, chain);" not in heal or "HealAllies(owner, spellId, chain)" not in heal:
        problems.append("Hedge Magic's heal finds its Shaman without its chain")
    if text.count("Minions::Standing(") != 1 or "ChainStands(chain, standing.front()->GetGUID().GetRawValue())" not in text:
        problems.append("a Shaman is found other than through ShamanOf and ChainStands")
    return problems


class Wiring(unittest.TestCase):
    def test_a_cast_is_one_chain_of_cycles_tied_to_its_shaman(self):
        self.assertEqual(one_chain_problems(CODE.read_text(encoding="utf-8")), [])

    def test_a_planted_second_chain_or_loose_chain_is_caught(self):
        source = CODE.read_text(encoding="utf-8")
        mutations = [
            ("Cast queues every cycle up front again",
             "        player->m_Events.AddEventAtOffset([player, spellId, rune, chain] { Cycle(player, spellId, rune, chain, 0); },\n                                          Ms(0));",
             "        for (unsigned i = 0; i < 3; ++i)\n            player->m_Events.AddEventAtOffset([player, spellId, rune, chain] { Cycle(player, spellId, rune, chain, 0); },\n                                              Ms(i * 4.0));"),
            ("Cast starts a second chain",
             "        if (rune == Rune::HedgeMagic)\n            HealAllies(player, spellId, chain);",
             "        player->m_Events.AddEventAtOffset([player, spellId, rune, chain] { Cycle(player, spellId, rune, chain, 0); },\n                                          Ms(1));\n        if (rune == Rune::HedgeMagic)\n            HealAllies(player, spellId, chain);"),
            ("a cycle starts two next cycles",
             "                    std::chrono::milliseconds(cycleMs));\n",
             "                    std::chrono::milliseconds(cycleMs));\n            if (auto const again = NextCycle(elapsedMs, cycleMs, 0))\n                owner->m_Events.AddEventAtOffset([owner, spellId, rune, chain, again] { Cycle(owner, spellId, rune, chain, *next); }, std::chrono::milliseconds(cycleMs));\n"),
            ("a cycle finds any Shaman", "        {\n            Creature* shaman = ShamanOf(owner, chain);\n            if (!shaman || !owner->IsInWorld() || !owner->IsAlive())",
             "        {\n            Creature* shaman = ShamanOf(owner, ShamanAny);\n            if (!shaman || !owner->IsInWorld() || !owner->IsAlive())"),
            ("Hedge Magic heals on any Shaman", "void HealAllies(Player* owner, std::uint32_t spellId, std::uint64_t chain)\n        {\n            Creature* shaman = ShamanOf(owner, chain);",
             "void HealAllies(Player* owner, std::uint32_t spellId, std::uint64_t chain)\n        {\n            Creature* shaman = Minions::Standing(owner, ShamanGroup).front();"),
            ("the chain is not the Shaman's", "std::uint64_t const chain = shaman->GetGUID().GetRawValue();", "std::uint64_t const chain = player->GetGUID().GetRawValue();"),
            ("a cycle runs on without the cap", "NextCycle(elapsedMs, cycleMs, std::uint64_t(Ms(Numbers::Num(spellId, \"duration_seconds\")).count()))", "std::optional<std::uint64_t>(elapsedMs + cycleMs)"),
        ]
        for label, old, new in mutations:
            with self.subTest(label):
                flat = source
                if flat.count(old) != 1:
                    self.fail(f"mutation target for {label!r} not found exactly once")
                self.assertNotEqual(one_chain_problems(flat.replace(old, new)), [], f"{label} was not caught")

    def test_the_engine_asks_the_class_after_a_ground_cast_before_the_check_and_at_startup(self):
        resolve = RESOLVE.read_text(encoding="utf-8")
        self.assertIn("DemonHunter::Ground(player, shell.spellId, center);\n            WitchDoctor::Ground(player, shell.spellId, center);", resolve)
        combat = COMBAT.read_text(encoding="utf-8")
        self.assertIn("DemonHunter::RegisterScripts();\n        WitchDoctor::RegisterScripts();", combat)
        flat = " ".join(combat.split())
        monk = "if (!spell->IsTriggered() && Monk::Toggle(player, spell->GetSpellInfo()->Id)) { result = SPELL_FAILED_DONT_REPORT; return; }"
        self.assertIn(monk + " " + monk.replace("Monk::Toggle", "WitchDoctor::Toggle"), flat)

    def test_the_dispatch_hands_each_call_to_hex(self):
        text = " ".join(DISPATCH.read_text(encoding="utf-8").split())
        self.assertIn("Hex::Cast(player, spellId, center);", text)
        self.assertIn("return Hex::Press(player, spellId);", text)
        self.assertIn("Hex::Register();", text)

    def test_the_shaman_is_one_minion_of_its_own_group_and_hexes_the_group_round_the_nearest_enemy(self):
        text = " ".join(CODE.read_text(encoding="utf-8").split())
        self.assertIn("kind.cap = 1;", text)
        self.assertIn('Minions::Define("fetish_shaman", Shaman);', text)
        self.assertIn("Minions::Dismiss(player, ShamanGroup); Creature* shaman = Minions::Raise(player, \"fetish_shaman\", center); if (!shaman) return;", text)
        self.assertIn("if (!centre || shaman->GetExactDist(enemy) < shaman->GetExactDist(centre)) centre = enemy;", text)
        self.assertIn("if (HexEnemy(owner, enemy, seconds))", text)

    def test_each_rune_does_its_own_thing(self):
        text = " ".join(CODE.read_text(encoding="utf-8").split())
        self.assertIn('if (rune == Rune::Jinx) EnemyEffects::Taken(enemy, spellId, Numbers::Num(spellId, "damage_taken_pct"), seconds);', text)
        self.assertIn("if (rune == Rune::UnstableForm)", text)
        self.assertIn("RuneAt(state.spellId) == Rune::UnstableForm", text)
        self.assertIn("if (rune == Rune::HedgeMagic) HealAllies(player, spellId, chain);", text)
        self.assertIn('Slow(owner, enemy, Tune("hex_toad_slow_pct"), dot);', text)
        self.assertIn("Abilities::Pull(enemy, point);", text)
        self.assertIn('Strike(owner, enemy, spellId, Numbers::Own(spellId, "damage_pct"));', text)
        self.assertIn("if (!RaisesShaman(rune)) {", text)


class StockRecords(unittest.TestCase):
    def record(self, spell_id):
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
            if row[0] == spell_id:
                return dict(zip(columns, row))
        self.fail(f"no spell {spell_id}")

    def test_polymorph_chicken_is_a_transform_a_silence_and_a_cut_with_no_interrupt(self):
        record = self.record(POLYMORPH_CHICKEN)
        self.assertEqual([record["EffectAura_1"], record["EffectAura_2"], record["EffectAura_3"]], [56, 27, 79])   # TRANSFORM, SILENCE, DAMAGE_DONE
        self.assertEqual(record["EffectMiscValue_1"], 620)                                                          # the chicken
        self.assertEqual(record["AuraInterruptFlags"], 0)                                                           # damage does not end it

    def test_pacify_is_one_pacify_with_no_interrupt(self):
        record = self.record(PACIFY)
        self.assertEqual((6, 0, 0), (record["Effect_1"], record["Effect_2"], record["Effect_3"]))
        self.assertEqual(25, record["EffectAura_1"])                                                                # SPELL_AURA_MOD_PACIFY
        self.assertEqual(0, record["AuraInterruptFlags"])

    def test_chicken_is_one_transform_into_the_same_chicken(self):
        record = self.record(CHICKEN_FORM)
        self.assertEqual((6, 0, 0), (record["Effect_1"], record["Effect_2"], record["Effect_3"]))
        self.assertEqual((56, 620), (record["EffectAura_1"], record["EffectMiscValue_1"]))

    def test_dazed_is_one_slow(self):
        record = self.record(DAZED)
        self.assertEqual((6, 0, 0), (record["Effect_1"], record["Effect_2"], record["Effect_3"]))
        self.assertEqual(33, record["EffectAura_1"])                                                                # SPELL_AURA_MOD_DECREASE_SPEED

    def test_the_effects_file_names_the_records_it_applies(self):
        text = EFFECTS.read_text(encoding="utf-8")
        for const, spell in (("HexHold", POLYMORPH_CHICKEN), ("PacifyHold", PACIFY), ("ChickenForm", CHICKEN_FORM), ("SlowHold", DAZED)):
            self.assertIn(f"constexpr std::uint32_t {const} = {spell};", text)


if __name__ == "__main__":
    unittest.main()
