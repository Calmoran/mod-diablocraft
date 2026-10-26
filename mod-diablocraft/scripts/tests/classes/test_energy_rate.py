"""Energy regenerating at a set rate: the energy_rate passive (Wrath 2.5/s, Hatred 5/s).

What this proves, and how:

  * **The record.** generate_spells.py renders one hidden passive for a class whose primary resource is
    on Energy at another rate than the slot's native 10/s: SPELL_AURA_MOD_POWER_REGEN_PERCENT (110) on
    MiscValue 3 (Energy), amount the registry's energy_rate_pct (-75 for 2.5/s), exact (no die side),
    on the caster, effects 2 and 3 empty. The live classes on Energy are the Wizard (at the native
    10/s, so no record) and the Crusader (Wrath, 2.5/s, its record in its own helper block, written before
    its skill records exist); the test also rehearses a full render in a scratch copy of the generated
    folder with the Wizard's registry row at -75 and -50, and reads the rows out of the rendered
    spell_shells.sql and spell_shells.csv. The same render writes EnergyRateFor, which names the
    class and the record. The committed files are held to the live registry: a record per class that
    needs one, none for a class that does not.
  * **The rate the core pays.** The pinned core's Player::UpdateEnergyRegen and Player::Regenerate are
    read as text, the formula they spell is run over the rendered record (the 10/s start, the percent
    aura of MiscValue 3 as AddPct on 1.0, the flat modifier and the 10 added back, the integer part
    and the carried fraction) and a character with the passive gains 2.5 Energy a second (25 over
    ten seconds), the Hatred rate 50, a record on the wrong power or without the percent gains 100.
  * **The module keeps it on.** dc_stats.cpp's PublishRegeneration asks EnergyRateFor and adds the
    aura. Planted changes (the record's aura, power or amount, the generator's aura constant, the
    module's lookup or add) must each be seen.

What it does not prove: a running core. The arithmetic is the core's formula written out here, read
against the pinned source text, not the core compiled; the designer's dev check with the Crusader (Wrath
2.5/s, docs/test-diablocraft-55e0k.md) proves the rate in game.

    python mod-diablocraft/scripts/tests/classes/test_energy_rate.py
"""

import contextlib
import csv
import io
import re
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
SCRATCH = REPO / "azerothcore-wotlk" / "build" / "_agent-scratch" / "energy_rate"
CORE = REPO / "azerothcore-wotlk" / "src" / "server"
STAT_SYSTEM = CORE / "game" / "Entities" / "Unit" / "StatSystem.cpp"
PLAYER = CORE / "game" / "Entities" / "Player" / "Player.cpp"
UNIT = CORE / "game" / "Entities" / "Unit" / "Unit.cpp"
SHARED = CORE / "shared" / "SharedDefines.h"
STATS = MODULE / "src" / "stats" / "dc_stats.cpp"

import generate_spells as gs  # noqa: E402

AURA_PERCENT, POWER_ENERGY, WIZARD_CLASS_ID, CRUSADER_CLASS_ID, DEMON_HUNTER_CLASS_ID = 110, 3, 2, 4, 6


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def sql_record(sql, spell_id):
    """The spell_dbc row `spell_id` of a generated INSERT, as {column: text}."""
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
    return dict(zip(columns, next(csv.reader([sql[start:i]], quotechar="'", skipinitialspace=True))))


def render(percent):
    """A full spell render into a scratch copy of the outputs with the Wizard's primary resource at
    `percent` (None: the real registry); returns (spell_shells.sql, spell_shells.csv rows, dc_spell_shells.h)."""
    work = SCRATCH / ("render_none" if percent is None else "render_%d" % -percent)
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(MODULE / "src", work / "module" / "src")   # the render also writes class headers under src/
    shutil.copytree(MODULE / "data" / "sql", work / "module" / "data" / "sql")   # the potion migration is checked here
    shutil.copytree(MODULE / "data" / "generated", work / "generated")
    for name in ("Spell.dbc", "SpellCategory.dbc", "SpellDescriptionVariables.dbc"):
        shutil.copy(REPO / "client-patch" / "dbc" / name, work / name)
    saved = (gs.MODULE_ROOT, gs.GENERATED, gs.CLIENT_DBC, gs.CLIENT_CATEGORY_DBC, gs.CLIENT_VARIABLES_DBC,
             [dict(e) for e in gs.RESOURCES])
    try:
        gs.MODULE_ROOT, gs.GENERATED = work / "module", work / "generated"
        gs.CLIENT_DBC, gs.CLIENT_CATEGORY_DBC = work / "Spell.dbc", work / "SpellCategory.dbc"
        gs.CLIENT_VARIABLES_DBC = work / "SpellDescriptionVariables.dbc"
        if percent is not None:
            for entry in gs.RESOURCES:
                if entry["d3_class"] == "Wizard":
                    entry["energy_rate_pct"] = percent
        with contextlib.redirect_stdout(io.StringIO()):   # the generator's progress report
            gs.main()
            gs.generate_ability_data()
    finally:
        (gs.MODULE_ROOT, gs.GENERATED, gs.CLIENT_DBC, gs.CLIENT_CATEGORY_DBC, gs.CLIENT_VARIABLES_DBC) = saved[:5]
        gs.RESOURCES[:] = saved[5]
    return ((work / "generated" / "spell_shells.sql").read_text(encoding="utf-8"),
            read_csv(work / "generated" / "spell_shells.csv"),
            (work / "module" / "src" / "combat" / "dc_spell_shells.h").read_text(encoding="utf-8"))


def energy_after(seconds, record, step_ms=100):
    """Energy a character with energy 0 gains in `seconds`, by the pinned core's arithmetic.

    Player::UpdateEnergyRegen: 10/s, times the product over the player's SPELL_AURA_MOD_POWER_REGEN_PERCENT
    effects of MiscValue 3 of (1 + amount/100) (Unit::GetTotalAuraMultiplier, AddPct), the flat modifier is
    that rate minus 10; Player::Regenerate adds (flat modifier + 10) / 1000 per elapsed ms, then the carried
    fraction, pays the integer part and carries the rest. The record's aura effects are read by their type,
    their MiscValue and their amount, exactly the three things the core's predicate and AddPct read."""
    rate = 10.0
    for slot in "123":
        if record["Effect_" + slot] == "6" and int(record["EffectAura_" + slot]) == AURA_PERCENT \
                and int(record["EffectMiscValue_" + slot]) == POWER_ENERGY:
            rate += rate * int(record["EffectBasePoints_" + slot]) / 100.0
    flat = rate - 10.0
    energy, fraction = 0, 0.0
    for _ in range(int(seconds * 1000 / step_ms)):
        addvalue = (flat + 10.0) * 0.001 * step_ms + fraction
        energy += int(addvalue)
        fraction = addvalue - int(addvalue)
    return energy + fraction


class CoreFormula(unittest.TestCase):
    def test_the_core_still_spells_the_formula_the_model_runs(self):
        text = STAT_SYSTEM.read_text(encoding="utf-8")
        body = text.split("void Player::UpdateEnergyRegen()")[1].split("\n}\n")[0]
        for needle in ("float regenPerSecond = 10.f;",
                       "regenPerSecond *= GetTotalAuraMultiplierByMiscValue(SPELL_AURA_MOD_POWER_REGEN_PERCENT, POWER_ENERGY);",
                       "UNIT_FIELD_POWER_REGEN_FLAT_MODIFIER + AsUnderlyingType(POWER_ENERGY), regenPerSecond - 10.f"):
            self.assertIn(needle, body)
        regenerate = PLAYER.read_text(encoding="utf-8").split("case POWER_ENERGY:")[1].split("break;")[0]
        self.assertIn("addvalue += (GetFloatValue(UNIT_FIELD_POWER_REGEN_FLAT_MODIFIER + AsUnderlyingType(POWER_ENERGY)) + 10.f);",
                      regenerate)
        self.assertIn("addvalue *= 0.001f;", regenerate)
        self.assertIn("addvalue *= m_regenTimer;", regenerate)
        multiplier = UNIT.read_text(encoding="utf-8").split("float Unit::GetTotalAuraMultiplier(AuraType auraType, std::function")[1]
        self.assertIn("AddPct(multiplier, aurEff->GetAmount());", multiplier.split("\n}\n")[0])
        self.assertRegex(SHARED.read_text(encoding="utf-8"), r"POWER_ENERGY\s*=\s*3,")

    def test_the_model_pays_native_ten_a_second_without_the_passive(self):
        self.assertAlmostEqual(energy_after(5, {"Effect_1": "0", "Effect_2": "0", "Effect_3": "0"}), 50.0, places=6)


class Record(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wrath = render(-75)
        cls.hatred = render(-50)
        cls.real = render(None)

    def rows(self, rendered, d3_class="Wizard"):
        return [r for r in rendered[1] if r["kind"] == "energy_rate" and r["name"] == gs.ENERGY_RATE % d3_class]

    def test_the_record_is_the_percent_aura_on_energy(self):
        sql, manifest, _header = self.wrath
        rows = self.rows(self.wrath)
        self.assertEqual(sorted(r["name"] for r in manifest if r["kind"] == "energy_rate"),
                         ["Crusader - energy rate", "Demon Hunter - energy rate", "Wizard - energy rate"])
        record = sql_record(sql, int(rows[0]["spell_id"]))
        first, last = gs.CLASS_BLOCKS["wizard"].helpers
        self.assertTrue(first <= int(rows[0]["spell_id"]) <= last)
        self.assertEqual((record["Effect_1"], record["EffectAura_1"], record["EffectMiscValue_1"], record["EffectMiscValueB_1"],
                          record["EffectBasePoints_1"], record["EffectDieSides_1"], record["ImplicitTargetA_1"]),
                         ("6", "110", "3", "0", "-75", "0", "1"))
        for slot in "23":
            self.assertEqual((record["Effect_" + slot], record["EffectAura_" + slot], record["EffectBasePoints_" + slot]),
                             ("0", "0", "0"))
        self.assertEqual(record["Name_Lang_enUS"], "Wizard - energy rate")

    def test_the_lookup_names_the_class_and_the_record(self):
        _sql, _manifest, header = self.wrath
        spell = int(self.rows(self.wrath)[0]["spell_id"])
        body = header.split("inline uint32_t EnergyRateFor(uint32_t classId)")[1].split("\n}\n")[0]
        self.assertIn("if (classId == %d)\n        return %d;" % (WIZARD_CLASS_ID, spell), body)

    def test_a_class_at_the_native_rate_has_no_record(self):
        self.assertEqual(self.rows(self.real), [])
        body = self.real[2].split("inline uint32_t EnergyRateFor(uint32_t classId)")[1].split("\n}\n")[0]
        self.assertNotIn("classId == %d" % WIZARD_CLASS_ID, body)

    def test_the_crusader_has_its_record_in_its_helper_block(self):
        sql, _manifest, header = self.real
        rows = self.rows(self.real, "Crusader")
        self.assertEqual(len(rows), 1)
        spell = int(rows[0]["spell_id"])
        first, last = gs.CLASS_BLOCKS["crusader"].helpers
        self.assertTrue(first <= spell <= last, spell)
        record = sql_record(sql, spell)
        self.assertEqual((record["EffectAura_1"], record["EffectMiscValue_1"], record["EffectBasePoints_1"]), ("110", "3", "-75"))
        body = header.split("inline uint32_t EnergyRateFor(uint32_t classId)")[1].split("\n}\n")[0]
        self.assertIn("if (classId == %d)\n        return %d;" % (CRUSADER_CLASS_ID, spell), body)
        self.assertAlmostEqual(energy_after(10, record), 25.0, places=4)
        # since 2a (diablocraft-qulab) the records block holds the skill records, and none of them is the rate record
        records = gs.CLASS_BLOCKS["crusader"].records
        self.assertEqual([r for r in self.real[1] if records[0] <= int(r["spell_id"]) <= records[1]
                          and r["kind"] == "energy_rate"], [])

    def test_the_demon_hunter_has_its_record_in_its_helper_block_at_the_hatred_rate(self):
        sql, _manifest, header = self.real
        rows = self.rows(self.real, "Demon Hunter")
        self.assertEqual(len(rows), 1)
        spell = int(rows[0]["spell_id"])
        first, last = gs.CLASS_BLOCKS["demon_hunter"].helpers
        self.assertTrue(first <= spell <= last, spell)
        record = sql_record(sql, spell)
        self.assertEqual((record["EffectAura_1"], record["EffectMiscValue_1"], record["EffectBasePoints_1"]), ("110", "3", "-50"))
        body = header.split("inline uint32_t EnergyRateFor(uint32_t classId)")[1].split("\n}\n")[0]
        self.assertIn("if (classId == %d)\n        return %d;" % (DEMON_HUNTER_CLASS_ID, spell), body)
        self.assertAlmostEqual(energy_after(10, record), 50.0, places=4)   # Hatred 5 a second, half Energy's native 10

    def test_the_committed_files_follow_the_registry(self):
        needs = {e["d3_class"] for e in gs.RESOURCES if e["role"] == "primary" and e["energy_rate_pct"] is not None}
        committed = [r["name"] for r in read_csv(MODULE / "data/generated/spell_shells.csv") if r["kind"] == "energy_rate"]
        self.assertEqual(sorted(committed), sorted(gs.ENERGY_RATE % c for c in needs))
        header = (MODULE / "src/combat/dc_spell_shells.h").read_text(encoding="utf-8")
        body = header.split("inline uint32_t EnergyRateFor(uint32_t classId)")[1].split("\n}\n")[0]
        self.assertEqual(body.count("classId =="), len(needs))

    def test_a_character_with_the_passive_gains_the_d3_rate(self):
        # Wrath: 2.5/s, 25 in ten seconds; Hatred: 5/s; the unrelated class record at the wrong power gains the native 10/s.
        for label, rendered, per_second in (("Wrath", self.wrath, 2.5), ("Hatred", self.hatred, 5.0)):
            with self.subTest(label):
                row = self.rows(rendered)[0]
                self.assertAlmostEqual(energy_after(10, sql_record(rendered[0], int(row["spell_id"]))), per_second * 10, places=4)
        record = dict(sql_record(self.wrath[0], int(self.rows(self.wrath)[0]["spell_id"])))
        record["EffectMiscValue_1"] = "0"
        self.assertAlmostEqual(energy_after(10, record), 100.0, places=4)

    def test_a_changed_record_is_seen(self):
        record = sql_record(self.wrath[0], int(self.rows(self.wrath)[0]["spell_id"]))
        # Each planted change to the rendered record must move the rate off 2.5/s.
        for label, field, value in (("the wrong aura", "EffectAura_1", "85"), ("the wrong power", "EffectMiscValue_1", "0"),
                                    ("another amount", "EffectBasePoints_1", "-70"), ("no effect", "Effect_1", "0")):
            with self.subTest(label):
                self.assertNotAlmostEqual(energy_after(10, dict(record, **{field: value})), 25.0, places=2)

    def test_a_changed_generator_is_seen(self):
        # The writer's aura constant planted wrong in the generator reaches the rendered record and the rate.
        gs.SPELL_AURA_MOD_POWER_REGEN_PERCENT = 85
        try:
            sql, manifest, _header = render(-75)
        finally:
            gs.SPELL_AURA_MOD_POWER_REGEN_PERCENT = AURA_PERCENT
        row = [r for r in manifest if r["kind"] == "energy_rate"][0]
        self.assertNotAlmostEqual(energy_after(10, sql_record(sql, int(row["spell_id"]))), 25.0, places=2)


def module_problems(text):
    body = text.split("void PublishRegeneration(Player* player, ClassSheet const& cls)")[1].split("\n        }\n")[0]
    return [needle for needle in ("Combat::Shells::ResourceRegenerationFor(cls.classId)",
                                  "Combat::Shells::EnergyRateFor(cls.classId)",
                                  "if (spell && !player->HasAura(spell))", "player->AddAura(spell, player);")
            if needle not in body]


class Module(unittest.TestCase):
    def test_the_module_adds_both_regeneration_passives(self):
        self.assertEqual(module_problems(STATS.read_text(encoding="utf-8")), [])

    def test_a_module_that_stops_adding_it_is_seen(self):
        text = STATS.read_text(encoding="utf-8")
        for old, new in (("Combat::Shells::EnergyRateFor(cls.classId)", "0u"),
                         ("player->AddAura(spell, player);", ";")):
            with self.subTest(old):
                self.assertEqual(text.count(old), 1)
                self.assertTrue(module_problems(text.replace(old, new)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
