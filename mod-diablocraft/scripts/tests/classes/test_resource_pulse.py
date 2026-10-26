"""diablocraft-dupme (ruling 2026-10-14, P1): class resources on Rage or Runic Power move smoothly; class powers P2
(diablocraft-m7mj0): so does every resource the registry has the module pay (paid_by module), Wrath on Energy first.

What this proves, and how:

  * **The pulse's arithmetic.** tests/resource_pulse/harness.cpp compiles the real
    src/stats/dc_resource_pulse.h over the generated registry, no core, and runs the pulse loop
    dc_resource_pulse.cpp runs at combat.resource_pulse_ms (read from combat.csv): the decaying
    Rage row loses the core's 1 Fury a second out of combat at its own scale (ten units at ten a point)
    a unit at a time, nothing in combat or under an interrupt-regen aura, a realm rate's fraction
    carries; the slot's regeneration percent auras (the Empowered Shrine's) move the regeneration and
    the class's own Energy-rate record does not; each unit of a fill or drain lands on the pulse the
    rate's exact share says, neither late nor early (Step's tolerance); regeneration is the same in and
    out of combat; every Monk regen_per_second_resource (the sheets' numbers) paid as a one-second
    flow pays exactly its units over the second a pulse's share at a time; the module-paid Energy row
    rows (Arcane Power, Wrath) pay ten seconds of their sheet rate a unit at a time, in combat too, and
    stop at their maximum; the regeneration field is the rate (less Energy's native 10). Planted
    mutations (the remainder dropped, the rate per pulse wrong, out of combat skipped, the decay lost,
    the loss in slot units, the shrine's percent off, the own rate record on, Step's tolerance dropped
    or widened) must each make it fail.
  * **The core tick is masked.** Every live class with a module-paid resource has a
    generated record with SPELL_AURA_PREVENT_REGENERATE_POWER (294) and MiscValue power + 1 per such
    resource, in spell_shells.sql and in the newest combat migration; RegenerationMaskFor names it
    and no other class; the pulse keeps it on and pays the rate and writes the regeneration fields only
    while it is on; and the pinned
    core's Player::Regenerate still returns at that aura. Planted: the record's aura gone, the
    pulse not putting it on.
  * **The sources moved onto it.** The five Spirit regeneration sources (Exalted Soul and Chant of
    Resonance, Circular Breathing, Epiphany, Inner Storm, Air Ally) hand their seconds to
    Resources::Flow over the time they are for, and none pays regen_per_second_resource at once any
    more. Planted: Epiphany back on Generate.
  * **No class is named.** The pulse's two files read the slot off the registry; a class, a class
    resource or a class constant planted in them is seen.
  * **The Demon Hunter's two** (class powers P2, diablocraft-a52dy; live since diablocraft-vawmy.1). The registry carries
    its rows (the Hunter slot, wow class 3), and the same harness runs over it: Hatred on Energy at 5/s (field -5) and
    Discipline, the second, in Focus at 1/s (field 1) each fill a unit a pulse and stop at their pools, and both are
    pulsed. The stats code gives a second resource its maximum (its pool, in the max-power hook and the sheet's display)
    and its starting value at login. Planted: the pulse paying primaries only, each of the three second-slot lines gone.
  * **The tunable and the wiring.** combat.resource_pulse_ms is 100 ms in combat.csv and in the
    generated tunables migration; the pulse reads it; Stats::RegisterScripts registers the pulse.

What it does not prove: anything on a running server (docs/test-diablocraft-dupme.md).

    python mod-diablocraft/scripts/tests/classes/test_resource_pulse.py
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
import harness_env

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
SCRATCH = REPO / "azerothcore-wotlk" / "build" / "_agent-scratch" / "resource_pulse"
CORE_PLAYER = REPO / "azerothcore-wotlk" / "src" / "server" / "game" / "Entities" / "Player" / "Player.cpp"
sys.path.insert(0, str(MODULE / "scripts"))

import generate_class_resources as gcr  # noqa: E402
from class_names import sheet_stem  # noqa: E402

HEADER = "src/stats/dc_resource_pulse.h"
PULSE = "src/stats/dc_resource_pulse.cpp"
SOURCES = [HEADER, PULSE, "src/classes/dc_resource_data.h", "tests/resource_pulse/harness.cpp",
           "src/combat/dc_spell_shells.h", "data/generated/spell_shells.sql", "data/generated/spell_shells.csv"]
MONK = "src/classes/monk/"
# Each source, the call that now hands its Spirit over, and the stretch it is for.
FLOWS = {
    "dc_monk_passives.cpp": "Resources::Flow(player, Resources::Spirit, points * seconds, seconds * 1000);",
    "dc_monk_mantras.cpp": "Resources::Flow(owner, Resources::Spirit, spirit, std::uint32_t(Mantras::Millis(period)));",
    "dc_monk_epiphany.cpp": 'Resources::Flow(player, Resources::Spirit, Numbers::Num(spellId, "regen_per_second_resource"), 1000);',
    "dc_monk_sweeping_wind.cpp": 'Resources::Flow(player, Resources::Spirit, Numbers::Num(spellId, "regen_per_second_resource"), 1000);',
    "dc_monk_mystic_ally.cpp": "seconds * 1000);",
}
PREVENT_REGENERATE_POWER = 294


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def pulse_ms():
    rows = [r for r in read(MODULE / "data/tunables/combat.csv") if r["name"] == "resource_pulse_ms"]
    assert len(rows) == 1, rows
    return rows[0]["value"]


def decay_rows():
    """The timed decay's two combat.csv numbers: the rate a second, and the wait in seconds."""
    rows = {r["name"]: r for r in read(MODULE / "data/tunables/combat.csv")}
    return [rows["maelstrom_decay_per_second"]["value"], rows["maelstrom_decay_wait_seconds"]["value"]]


def monk_rates():
    out = []
    for name in ("monk_skill_values.csv", "monk_passive_values.csv"):
        out += [r["value"] for r in read(MODULE / "data/d3" / name) if r["token"] == "regen_per_second_resource"]
    assert out, "no Monk regeneration numbers"
    return out


def scratch_tree(name, mutations=()):
    tree = SCRATCH / name
    if tree.exists():
        shutil.rmtree(tree)
    for source in SOURCES + [MONK + f for f in FLOWS] + ["src/stats/dc_stats.cpp"]:
        target = tree / source
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(MODULE / source, target)
    for path, old, new in mutations:
        text = (tree / path).read_text(encoding="utf-8")
        if text.count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        (tree / path).write_text(text.replace(old, new), encoding="utf-8")
    return tree


def build_and_run(tree):
    compiler = shutil.which("g++") or shutil.which("clang++")
    if not compiler:
        raise unittest.SkipTest("no C++ compiler")
    binary = tree / "harness"
    subprocess.run([compiler, "-std=c++20", "-O1", "-o", str(binary), str(tree / "tests/resource_pulse/harness.cpp")],
                   check=True, capture_output=True, text=True)
    return harness_env.run([str(binary), pulse_ms(), *decay_rows()] + monk_rates(), capture_output=True, text=True)


def span(sql, spell_id):
    """(columns, start, end) of the spell_dbc row `spell_id` in a generated INSERT: sql[start:end] is its values."""
    header = re.search(r"INSERT INTO `spell_dbc` \(([^)]*)\) VALUES", sql)
    columns = [c.strip(" `") for c in header.group(1).split(",")]
    start = sql.index("(%d," % spell_id, header.end()) + 1
    quoted, i = False, start
    while quoted or sql[i] != ")":
        if sql[i] == "'" and quoted and sql[i + 1] == "'":
            i += 1
        elif sql[i] == "'":
            quoted = not quoted
        i += 1
    return columns, start, i


def record(sql, spell_id):
    """The spell_dbc row `spell_id` of a generated INSERT, as {column: text}."""
    columns, start, end = span(sql, spell_id)
    return dict(zip(columns, next(csv.reader([sql[start:end]], quotechar="'", skipinitialspace=True))))


def pulsed_classes():
    """The classes whose core tick the pulse masks: a class with a module-paid resource (paid_by module) and its id
    blocks. A class without a generate_spells.py CLASS_BLOCKS entry has no mask record and nothing for the pulse to pay."""
    import generate_spells
    out = {}
    for entry in gcr.registry():
        if entry["paid_by"] == "module" and sheet_stem(entry["d3_class"]) in generate_spells.CLASS_BLOCKS:
            out.setdefault(entry["class_id"], []).append(entry["power_id"])
    return out


def mask_problems(tree):
    """Why the core's tick would not be masked, [] when it is."""
    problems = []
    shells = (tree / "src/combat/dc_spell_shells.h").read_text(encoding="utf-8")
    body = shells.split("inline uint32_t RegenerationMaskFor(uint32_t classId)")
    if len(body) != 2:
        return ["no RegenerationMaskFor"]
    named = {int(c): int(s) for c, s in re.findall(r"if \(classId == (\d+)\)\s*return (\d+);", body[1].split("}")[0])}
    wanted = pulsed_classes()
    if set(named) != set(wanted):
        problems.append(f"RegenerationMaskFor names classes {sorted(named)}, the registry {sorted(wanted)}")
    sql = (tree / "data/generated/spell_shells.sql").read_text(encoding="utf-8")
    kinds = {int(r["spell_id"]): r["kind"] for r in read(tree / "data/generated/spell_shells.csv")}
    updates = sorted((MODULE / "data/sql/db-world/updates").glob("combat_*.sql"))
    newest = updates[-1].read_text(encoding="utf-8")
    for class_id, spell in named.items():
        if kinds.get(spell) != "regeneration_mask":
            problems.append(f"{spell} is not a regeneration_mask record")
        row = record(sql, spell)
        effects = sorted((int(row["EffectMiscValue_%d" % s]) - 1) for s in (1, 2, 3)
                         if int(row["EffectAura_%d" % s]) == PREVENT_REGENERATE_POWER and int(row["Effect_%d" % s]) == 6)
        if effects != sorted(wanted.get(class_id, [])):
            problems.append(f"{spell} prevents the core's regeneration of slots {effects}, wants {wanted.get(class_id)}")
        if record(newest, spell) != row:
            problems.append(f"{spell} differs in {updates[-1].name}, the migration the server applies")
    pulse = (tree / PULSE).read_text(encoding="utf-8")
    for needed in ("Combat::Shells::RegenerationMaskFor(classId)", "player->AddAura(mask, player);",
                   "                if (masked)\n                {\n                    Stats::Pulse::Rate const rate = RateOf(player, r, outOfCombatMs);\n"
                   "                    units = Stats::Pulse::Units(rate, elapsed);",
                   "player->SetStatFloatValue(UNIT_FIELD_POWER_REGEN_FLAT_MODIFIER + r.power, field);",
                   "player->SetStatFloatValue(UNIT_FIELD_POWER_REGEN_INTERRUPTED_FLAT_MODIFIER + r.power, field);"):
        if needed not in pulse:
            problems.append(f"the pulse lacks {needed}")
    return problems


# What the stats code does for a second resource (dc_stats.cpp): its row, its maximum in the sheet's display and in
# the max-power hook, and its starting value at login.
SECOND_SLOT = [
    "cls.second = Resources::Of(cls.classId, Resources::Data::Role::Second);",
    "Resources::SetMax(player, *cls.second,\n"
    "                                  Resources::Pool::Maximum(cls.second->pool, player->GetGUID().GetRawValue(), sheet[Stat::MaxSecond]));",
    "else if (cls.second && power == Resources::Slot(*cls.second))\n"
    "                            value = static_cast<float>(Resources::ToUnits(\n"
    "                                *cls.second, Resources::Pool::Maximum(cls.second->pool, player->GetGUID().GetRawValue(),\n"
    "                                                                      (*sheet)[Stat::MaxSecond])));",
    "for (Resources::Resource const* resource : {SheetOf(player).resource, SheetOf(player).second})",
]


def second_slot_problems(tree):
    text = (tree / "src/stats/dc_stats.cpp").read_text(encoding="utf-8")
    return [f"dc_stats.cpp lacks {line}" for line in SECOND_SLOT if line not in text]


def named_classes(tree):
    words = set()
    for entry in gcr.rows(include_planned=True):
        words |= {entry["d3_class"], entry["d3_name"]}
    for row in read(MODULE / "data/d3/class_map.csv"):
        words.add(row["wow_class"])
    found = []
    for path in (HEADER, PULSE):
        text = (tree / path).read_text(encoding="utf-8")
        found += [f"{path}: {w}" for w in sorted(words) if re.search(r"\b%s\b" % re.escape(w), text)]
        found += [f"{path}: {m}" for m in re.findall(r"CLASS_[A-Z_]+|Resources::(?:Fury|Spirit|ArcanePower)\b"
                                                     r"|classId == \d+", text)]
    return found


def source_problems(tree):
    problems = []
    for name, call in FLOWS.items():
        text = (tree / MONK / name).read_text(encoding="utf-8")
        if call not in text:
            problems.append(f"{name}: no {call}")
        for paid in re.findall(r"(?:Generate|Energize)\([^;]*regen_per_second_resource[^;]*;", text):
            problems.append(f"{name}: pays at once: {paid}")
    return problems


class Harness(unittest.TestCase):
    def test_the_pulse_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree("clean"))
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        self.assertGreaterEqual(int(out.stdout.split("cases=")[1].split()[0]), 40, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("the remainder dropped", (HEADER, "        fraction = total - whole;\n", "        fraction = 0;\n")),
            ("the rate per pulse wrong", (HEADER, "1000.0;", "100.0;")),
            ("out of combat skipped", (HEADER, "        Rate rate;\n", "        Rate rate;\n        if (!in.inCombat)\n"
                                                                     "            return rate;\n")),
            ("the timed decay without its wait", (HEADER, "in.outOfCombatMs >= in.timedWaitMs", "true")),
            ("the timed decay forever waiting", (HEADER, "in.outOfCombatMs >= in.timedWaitMs", "in.outOfCombatMs > 1e12")),
            ("the timed decay in combat", (HEADER, "if (in.row->decay == Resources::Data::Decay::Timed && !in.inCombat && !in.interrupted &&",
                                           "if (in.row->decay == Resources::Data::Decay::Timed && !in.interrupted &&")),
            ("the clock never restarting", (HEADER, "return inCombat ? 0.0 : previousMs + elapsedMs;", "return previousMs + elapsedMs;")),
            ("the timed rate in slot units", (HEADER, "rate.lossPerSecond = in.timedPerSecond * in.row->scale;",
                                              "rate.lossPerSecond = in.timedPerSecond * 10.0;")),
            ("the realm's loss rate on the timed rate", (HEADER, "rate.lossPerSecond = in.timedPerSecond * in.row->scale;",
                                                          "rate.lossPerSecond = in.timedPerSecond * in.row->scale * in.realmLossRate;")),
            ("the decay lost", (HEADER, "rate.lossPerSecond = StockLossPerSecond(in.row->power) * in.row->scale * in.realmLossRate;",
                                "rate.lossPerSecond = 0;")),
            ("the loss in slot units, not points", (HEADER, "StockLossPerSecond(in.row->power) * in.row->scale *",
                                                    "StockLossPerSecond(in.row->power) * 10.0 *")),
            ("the shrine's percent left off the regeneration", (HEADER, "rate.regenPerSecond * rate.regenMultiplier",
                                                                 "rate.regenPerSecond")),
            ("the class's own rate record on the regeneration", (HEADER, "rate.regenMultiplier = in.regenAuraMultiplier;",
                                                                  "rate.regenMultiplier = in.auraMultiplier;")),
            # The PM's pin (review gqklk): the whole-unit tolerance in Step decides on which pulse a unit lands.
            ("Step's tolerance dropped: a unit a pulse late", (HEADER, "std::fabs(total) + 1e-9", "std::fabs(total)")),
            ("Step's tolerance widened: a unit a pulse early", (HEADER, "std::fabs(total) + 1e-9", "std::fabs(total) + 1e-3")),
            ("the pulse back to the two slots", (HEADER, "        return r.modulePaid;",
                                                 "        return r.power == Rage || r.power == RunicPower;")),
            ("Energy's field without the native 10", (HEADER, "power == Energy ? unitsPerSecond - 10.0 : unitsPerSecond",
                                                      "unitsPerSecond")),
        ]
        for label, mutation in mutations:
            with self.subTest(label):
                out = build_and_run(scratch_tree("mutant", [mutation]))
                self.assertNotEqual(out.returncode, 0, f"{label} was not caught: {out.stdout[-500:]}")


class Rehearsal(unittest.TestCase):
    def test_the_demon_hunters_two_on_the_pulse(self):
        rows = [e for e in gcr.registry() if e["d3_class"] == "Demon Hunter"]
        self.assertEqual(sorted((e["key"], e["power"], e["role"], e["paid_by"], e["regen"]) for e in rows),
                         [("discipline", "Focus", "second", "module", 1.0), ("hatred", "Energy", "primary", "module", 5.0)])
        out = build_and_run(scratch_tree("clean"))
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        regenerating = sum(1 for e in gcr.registry() if e["paid_by"] == "module" and e["regen"] > 0)
        seconds = sum(1 for e in gcr.registry() if e["role"] == "second")
        self.assertEqual(seconds, 1)
        self.assertIn(f" regenerating={regenerating} second={seconds}", out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_pulse_paying_primaries_only_is_caught(self):
        out = build_and_run(scratch_tree("mutant", [(HEADER, "        return r.modulePaid;",
                                                     "        return r.modulePaid && r.role == Resources::Data::Role::Primary;")]))
        self.assertNotEqual(out.returncode, 0, out.stdout[-500:])

    def test_the_stats_code_serves_the_second_slot(self):
        self.assertEqual(second_slot_problems(scratch_tree("clean")), [])

    def test_a_second_slot_line_gone_is_caught(self):
        for line in SECOND_SLOT[1:]:
            with self.subTest(line):
                tree = scratch_tree("mutant", [("src/stats/dc_stats.cpp", line, "")])
                self.assertNotEqual(second_slot_problems(tree), [])


class Mask(unittest.TestCase):
    def test_the_core_tick_is_masked(self):
        self.assertEqual(mask_problems(scratch_tree("clean")), [])
        self.assertTrue(pulsed_classes(), "no live class on Rage or Runic Power")

    def test_an_unmasked_tick_is_caught(self):
        spell = min(int(r["spell_id"]) for r in read(MODULE / "data/generated/spell_shells.csv")
                    if r["kind"] == "regeneration_mask")
        sql = (MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8")
        columns, start, end = span(sql, spell)
        fields = sql[start:end].split(",", columns.index("EffectAura_1") + 1)
        self.assertEqual(fields[columns.index("EffectAura_1")], str(PREVENT_REGENERATE_POWER))
        fields[columns.index("EffectAura_1")] = "0"
        for label, mutation in [
            ("the pulse does not put the mask on", (PULSE, "player->AddAura(mask, player);", "")),
            ("the pulse writes no regeneration field",
             (PULSE, "player->SetStatFloatValue(UNIT_FIELD_POWER_REGEN_FLAT_MODIFIER + r.power, field);", "")),
            ("the record does not prevent the core's tick",
             ("data/generated/spell_shells.sql", "(" + sql[start:end] + ")", "(" + ",".join(fields) + ")")),
        ]:
            with self.subTest(label):
                self.assertNotEqual(mask_problems(scratch_tree("mutant", [mutation])), [], label)

    def test_the_core_returns_at_the_aura(self):
        text = CORE_PLAYER.read_text(encoding="utf-8")
        body = text.split("void Player::Regenerate(Powers power)")[1].split("\nvoid Player::")[0]
        self.assertRegex(body, r"if \(HasAuraTypeWithMiscvalue\(SPELL_AURA_PREVENT_REGENERATE_POWER, power \+ 1\)\)\s*return;")


class Sources(unittest.TestCase):
    def test_every_source_flows(self):
        self.assertEqual(source_problems(scratch_tree("clean")), [])

    def test_a_source_paying_at_once_is_caught(self):
        tree = scratch_tree("mutant", [(MONK + "dc_monk_epiphany.cpp", FLOWS["dc_monk_epiphany.cpp"],
                                        'Generate(player, 3, spellId, Numbers::Num(spellId, "regen_per_second_resource"));')])
        self.assertNotEqual(source_problems(tree), [])


class NoClassNamed(unittest.TestCase):
    def test_the_pulse_names_no_class(self):
        self.assertEqual(named_classes(scratch_tree("clean")), [])

    def test_a_named_class_is_caught(self):
        for label, planted in [("a resource constant", "(void)Resources::Spirit;"), ("a class id", "if (classId == 3)"),
                               ("a class name", "// the Barbarian")]:
            with self.subTest(label):
                tree = scratch_tree("mutant", [(PULSE, "        bool const masked = Masked(player, classId);\n",
                                                "        bool const masked = Masked(player, classId);\n        "
                                                + planted + "\n")])
                self.assertNotEqual(named_classes(tree), [], label)


class Wiring(unittest.TestCase):
    def test_the_tunable(self):
        rows = [r for r in read(MODULE / "data/tunables/combat.csv") if r["name"] == "resource_pulse_ms"]
        self.assertEqual([(r["value"], r["unit"]) for r in rows], [("100", "milliseconds")])
        self.assertIn('Tunables::Get("combat", "resource_pulse_ms")', (MODULE / PULSE).read_text(encoding="utf-8"))
        generated = (MODULE / "data/generated").glob("tunables_*.sql")
        self.assertTrue(any("'resource_pulse_ms'" in p.read_text(encoding="utf-8") for p in generated))

    def test_the_pulse_is_registered(self):
        text = (MODULE / "src/stats/dc_stats.cpp").read_text(encoding="utf-8")
        body = text.split("    void RegisterScripts()")[1].split("}")[0]
        self.assertIn("RegisterResourcePulseScripts();", body)


if __name__ == "__main__":
    unittest.main()
