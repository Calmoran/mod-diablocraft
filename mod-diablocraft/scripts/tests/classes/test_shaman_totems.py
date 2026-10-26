"""The Shaman's totems on the native totem slots (src/classes/shaman/dc_shaman_totems.cpp, dc_shaman_totems_math.h).

What this proves, and how:

  * **The rules.** tests/shaman_totems/harness.cpp compiles the real dc_shaman_totems_math.h with the sheets' numbers: each native slot holds
    its own creature of data/d3/shaman_summons.csv and no other slot holds one, a totem lasts the skill's seconds and a totem with none is not
    placed, a pulse is due once an interval of the Searing Totem's record has passed with the rest of the clock kept, and the bolt goes to the
    nearest enemy. Planted differences in a scratch copy of the header must each make it fail.
  * **The creatures.** The four creature templates are the stock totem creatures of the core with the module's ScriptName and no loot, untargetable
    like the Hydra, in entries no other summon owns; the migration is the generator's render of the sheet.
  * **The records.** The four Totems skills keep the stock summon properties of their slot (fire 63, earth 81, water 82, air 83), the slot a rune
    places its totem in is its skill's, and the numbers the pulse reads (duration, interval, radius, damage) are rows of the sheet.
  * **The wiring.** The class dispatch calls the totems on a paid cast; the cast sets the slot's creature down at the Shaman's feet for the skill's
    duration with the skill's own summon properties, so the core keeps one totem a slot and puts the old one away; the creature ends with its owner
    (gone, dead, another map) and the owner's logout and change of floor take every totem away; the core's totem class is what the monsters and the
    rifts already leave out. Planted differences in the source must each be caught.

What it does not prove: the placing, the replacing, the pulses and the ending on a running server (docs/test-diablocraft-xnrvn.11.md).

    python mod-diablocraft/scripts/tests/classes/test_shaman_totems.py
"""

import csv
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_shaman_summons as summons  # noqa: E402
import harness_env  # noqa: E402
from test_item_power_cindercoat import SHELLS_SQL, manifest, records  # noqa: E402

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
CORE_SQL = REPO / "azerothcore-wotlk/data/sql/base/db_world"
HEADER = "src/classes/shaman/dc_shaman_totems_math.h"
HARNESS = MODULE / "tests/shaman_totems/harness.cpp"
FOLDER = MODULE / "src/classes/shaman"
# The four Totems skills, by slot, with the stock summon properties each one's record keeps (Searing Totem 63, Earthbind 81, Healing Stream 82,
# Windfury 83: the core's slots 1 to 4).
SKILLS = {"Searing Totem": 63, "Earthbind Totem": 81, "Healing Stream Totem": 82, "Tempest Totem": 83}
UNSELECTABLE = 33554432  # UNIT_FLAG_NOT_SELECTABLE


def read(name):
    with (D3 / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(skill, token):
    rows = [r for r in read("shaman_skill_values.csv") if (r["skill"], r["rune"], r["token"]) == (skill, "", token)]
    assert len(rows) == 1, (skill, token, len(rows))
    return float(rows[0]["value"])


def scratch_tree(mutate=None):
    key = HEADER[len("src/"):]
    files = {key: (MODULE / HEADER).read_text(encoding="utf-8")}
    if mutate:
        old, new = mutate
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {HEADER}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    entries = [r["entry"] for r in read("shaman_summons.csv")]
    numbers = entries + [value("Searing Totem", "interval_seconds"), value("Searing Totem", "duration_seconds")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Rules(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 16, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("fire and earth hold each other's creature", ("case FireSlot:\n                return 900180;", "case FireSlot:\n                return 900181;")),
            ("the air slot holds none", ("case AirSlot:\n                return 900183;", "case AirSlot:\n                return 0;")),
            ("a fifth slot holds a creature", ("default:\n                return 0;", "default:\n                return 900183;")),
            ("a totem with no seconds is placed", ("return seconds > 0 ? std::uint32_t(std::llround(seconds * 1000.0)) : 0;", "return std::uint32_t(std::llround(seconds * 1000.0)) + 1;")),
            ("seconds are hundredths", ("std::llround(seconds * 1000.0)", "std::llround(seconds * 100.0)")),
            ("a pulse is due a millisecond early", ("while (clockMs >= period)", "while (clockMs + 1 >= period)")),
            ("a pulse is due a millisecond late", ("while (clockMs >= period)", "while (clockMs > period)")),
            ("the rest of the clock is lost", ("clockMs -= period;\n            ++due;", "clockMs = 0;\n            ++due;")),
            ("a totem with no interval keeps its clock", ("if (!period)\n        {\n            clockMs = 0;\n            return 0;\n        }", "if (!period)\n            return 0;")),
            ("the bolt goes to the farthest", ("distances[i] < distances[best]", "distances[i] > distances[best]")),
            ("the bolt goes to the last of equals", ("distances[i] < distances[best]", "distances[i] <= distances[best]")),
        ]
        for label, mutation in mutations:
            with self.subTest(label):
                try:
                    tree = scratch_tree(mutation)
                except AssertionError as error:
                    self.fail(str(error))
                out = build_and_run(tree)
                self.assertNotEqual(out.returncode, 0, f"{label} was not caught: {out.stdout[-500:]}")


class Creatures(unittest.TestCase):
    def test_four_totems_with_entries_no_other_sheet_owns(self):
        rows = read("shaman_summons.csv")
        self.assertEqual(["Fire Totem", "Earth Totem", "Water Totem", "Air Totem"], [r["summon"] for r in rows])
        self.assertEqual([900180, 900181, 900182, 900183], [int(r["entry"]) for r in rows])
        self.assertEqual({"dc_shaman_totem"}, {r["script"] for r in rows})
        taken = set()
        for name in summons.OTHER_SHEETS:
            taken |= {int(r["entry"]) for r in read_module(name)}
        self.assertEqual(set(), taken & {int(r["entry"]) for r in rows})
        self.assertEqual(4, len(summons.rows()))

    def test_the_header_and_the_sheet_agree_on_the_creature_of_each_slot(self):
        header = (MODULE / HEADER).read_text(encoding="utf-8")
        for slot, row in zip(("FireSlot", "EarthSlot", "WaterSlot", "AirSlot"), read("shaman_summons.csv")):
            self.assertRegex(header, r"case %s:\s*return %s;" % (slot, row["entry"]))

    def test_the_donors_are_the_stock_totems_with_a_model(self):
        templates = (CORE_SQL / "creature_template.sql").read_text(encoding="utf-8", errors="replace")
        models = (CORE_SQL / "creature_template_model.sql").read_text(encoding="utf-8", errors="replace")
        for row, name in zip(read("shaman_summons.csv"), ("Searing Totem", "Earthbind Totem", "Healing Stream Totem", "Windfury Totem")):
            donor = int(row["donor_creature"])
            self.assertTrue(re.search(r"\(%d,0,0,0,0,0,'%s'" % (donor, name), templates), donor)
            self.assertTrue(re.search(r"\(%d,\d+,\d+,[\d.]+,\d+,\d+\)" % donor, models), donor)

    def test_the_migration_is_the_generators_render_and_leaves_the_totems_untargetable(self):
        migration = (MODULE / "data/sql/db-world/updates" / summons.MIGRATION).read_text(encoding="utf-8")
        self.assertEqual(summons.render(), migration)
        self.assertEqual(4, migration.count("INSERT INTO creature_template SELECT"))
        self.assertEqual(4, migration.count("unit_flags=%d," % UNSELECTABLE))
        self.assertEqual(4, migration.count("ScriptName='dc_shaman_totem'"))
        self.assertEqual(4, migration.count("lootid=0"))


def read_module(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class Records(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = records()
        cls.manifest = manifest()
        cls.base = {r["name"]: int(sid) for sid, r in cls.manifest.items() if r["kind"] == "active" and r["name"] in SKILLS}

    def test_each_totems_skill_keeps_the_stock_summon_properties_of_its_slot(self):
        self.assertEqual(set(SKILLS), set(self.base))
        for skill, properties in SKILLS.items():
            with self.subTest(skill):
                self.assertEqual(properties, int(self.records[self.base[skill]]["EffectMiscValueB_1"]))

    def test_the_slot_order_is_fire_earth_water_air(self):
        self.assertEqual(list(SKILLS.values()), sorted(SKILLS.values()))
        self.assertEqual(["Searing Totem", "Earthbind Totem", "Healing Stream Totem", "Tempest Totem"], list(SKILLS))
        elements = {s: self.manifest[self.base[s]]["element"] for s in SKILLS}
        self.assertEqual("fire", elements["Searing Totem"])
        self.assertEqual("physical", elements["Earthbind Totem"])

    def test_the_numbers_the_pulse_reads_are_rows_of_the_sheet(self):
        for skill in SKILLS:
            self.assertGreater(value(skill, "duration_seconds"), 0, skill)
        for token in ("interval_seconds", "radius_yards", "damage_pct"):
            self.assertGreater(value("Searing Totem", token), 0, token)

    def test_every_totems_rune_is_a_record_of_the_totems_category(self):
        rows = read("shaman_skills.csv")
        self.assertEqual(set(SKILLS), {r["skill_name"] for r in rows if r["category"] == "Totems"})


FILES = {name: (FOLDER / name).read_text(encoding="utf-8") for name in ("dc_shaman_totems.cpp", "dc_shaman.cpp", "dc_shaman_common.h")}


def failures(cpp, dispatch, common):
    flat = re.sub(r"\s+", " ", re.sub(r"//[^\n]*", "", cpp)).replace("( ", "(").replace(" )", ")")
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    cast = flat[flat.find("void Cast("):flat.find("void Away(")]
    need("only a Shaman's cast of the Totems category places a totem",
         'if (!IsShaman(player) || Classes::CategoryOf(spellId) != "Totems") return;' in cast)
    need("the slot is the skill's own record's, not the rune's", "GetSpellInfo(BaseId(cast->skill))" in cast and "Effects[EFFECT_0].MiscValueB" in cast)
    need("the creature is the slot's and the seconds the skill's",
         "EntryOfSlot(properties->Slot)" in cast and 'DurationMs(Numbers::Num(spellId, "duration_seconds"))' in cast)
    need("nothing is placed without a creature or a duration", "if (!entry || !duration) return;" in cast)
    need("the totem is set down at the Shaman's feet with the slot's properties, owned by the Shaman and made by the cast",
         "player->GetMap()->SummonCreature(entry, player->GetPosition(), properties, duration, player, spellId);" in cast)
    away = flat[flat.find("void Away("):flat.find("void RegisterScripts()")]
    need("every native slot is walked", "for (unsigned slot = FireSlot; slot <= AirSlot; ++slot)" in away)
    need("a totem standing in the slot is put away", "totem->ToTempSummon()->UnSummon();" in away and "player->m_SummonSlot[slot]" in away)
    ai = flat[flat.find("class TotemAI"):flat.find("class TotemScript")]
    need("the totem ends when its owner is gone, dead or on another map",
         "if (!player || !player->IsAlive() || !player->IsInMap(me)) { if (TempSummon* summon = me->ToTempSummon()) summon->UnSummon(); return; }" in ai)
    need("the totem is made by the cast's spell", "source = me->GetUInt32Value(UNIT_CREATED_BY_SPELL);" in ai)
    need("a standing totem is updated with its own state", "if (source) Update(player, me, source, state, diff);" in ai)
    update = flat[flat.find("void Update("):flat.find("class TotemAI")]
    need("the update goes to the file of the skill the record belongs to",
         'if (std::string_view(row->skill) == "Searing Totem") Searing::Update(player, totem, source, state, diff);' in update)
    totem = flat[flat.find("Creature* Totem("):flat.find("std::uint32_t Standing(")]
    need("the totem of a slot is the slot's creature, alive", "GetCreature(player->m_SummonSlot[slot]); return totem && totem->IsAlive() ? totem : nullptr;" in totem)
    standing = flat[flat.find("std::uint32_t Standing("):flat.find("void Away(")]
    need("a standing totem's cast is the record it was made by", "Creature* totem = Totem(player, slot); return totem ? totem->GetUInt32Value(UNIT_CREATED_BY_SPELL) : 0;" in standing)
    owner = flat[flat.find("class Owner"):flat.find("void Cast(")]
    need("logout and a change of floor take the totems away",
         "PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_MAP_CHANGED" in owner and owner.count("Away(player);") == 2)
    need("both scripts are registered, the creature under the sheet's name", "new TotemScript(); new Owner();" in flat and 'CreatureScript("dc_shaman_totem")' in flat)
    d = re.sub(r"\s+", " ", dispatch)
    casting = d[d.find("void Casting("):d.find("void Multipliers(")]
    need("the class dispatch places the totem on a paid cast, after the Attunement's",
         "Totems::Cast(player, spellId);" in casting and "Attunement::Cast(player, spellId);" in casting
         and casting.index("Attunement::Cast(player, spellId);") < casting.index("Totems::Cast(player, spellId);"))
    need("the dispatch registers the totems", "new UpkeepScript(); Totems::RegisterScripts(); }" in d)
    return wrong


class Wiring(unittest.TestCase):
    def test_the_totems_are_placed_pulse_and_end_as_designed(self):
        self.assertEqual([], failures(FILES["dc_shaman_totems.cpp"], FILES["dc_shaman.cpp"], FILES["dc_shaman_common.h"]))

    def test_the_source_guards_fail_their_mutants(self):
        cpp, dispatch, common = FILES["dc_shaman_totems.cpp"], FILES["dc_shaman.cpp"], FILES["dc_shaman_common.h"]
        mutants = [
            ("cpp", "a_rune_takes_its_donors_slot", "GetSpellInfo(BaseId(cast->skill))", "GetSpellInfo(spellId)"),
            ("cpp", "any_class_places", "if (!IsShaman(player) || ", "if ("),
            ("cpp", "any_skill_places", 'Classes::CategoryOf(spellId) != "Totems"', 'Classes::CategoryOf(spellId) != ""'),
            ("cpp", "no_properties_so_no_slot", "properties, duration, player, spellId);", "nullptr, duration, player, spellId);"),
            ("cpp", "placed_at_range", "SummonCreature(entry, player->GetPosition(),", "SummonCreature(entry, player->GetClosePoint(),"),
            ("cpp", "an_owner_on_another_map_keeps_it", "|| !player->IsInMap(me)", ""),
            ("cpp", "a_dead_owner_keeps_it", "|| !player->IsAlive()", ""),
            ("cpp", "the_skill_is_not_updated", "Searing::Update(player, totem, source, state, diff);", ""),
            ("cpp", "a_dead_totem_stands", "return totem && totem->IsAlive() ? totem : nullptr;", "return totem ? totem : nullptr;"),
            ("cpp", "a_change_of_floor_keeps_them", "PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_MAP_CHANGED", "PLAYERHOOK_ON_LOGOUT"),
            ("cpp", "logout_keeps_them", "void OnPlayerLogout(Player* player) override\n            {\n                Away(player);", "void OnPlayerLogout(Player* player) override\n            {\n                (void)player;"),
            ("cpp", "only_fire_goes", "slot <= AirSlot", "slot <= FireSlot"),
            ("cpp", "not_registered", "new TotemScript();", ""),
            ("dispatch", "not_dispatched", "Totems::Cast(player, spellId);", ""),
            ("dispatch", "not_registered_by_the_class", "Totems::RegisterScripts();", ""),
        ]
        for which, name, old, new in mutants:
            with self.subTest(name):
                parts = {"cpp": cpp, "dispatch": dispatch}
                self.assertEqual(1, parts[which].count(old), name + " does not apply")
                parts[which] = parts[which].replace(old, new, 1)
                self.assertNotEqual([], failures(parts["cpp"], parts["dispatch"], common), name + " survived")

    def test_the_core_totems_are_what_the_monsters_and_rifts_leave_out(self):
        for path, count in (("src/monsters/dc_monster_ai.cpp", 2), ("src/rifts/dc_rift_scripts.cpp", 2)):
            text = (MODULE / path).read_text(encoding="utf-8")
            self.assertGreaterEqual(text.count("IsTotem()"), count, path)

    def test_the_shaman_dispatch_includes_the_totems(self):
        self.assertIn('#include "dc_shaman_totems.h"', FILES["dc_shaman.cpp"])
        self.assertIn("inline std::uint32_t BaseId(std::string_view skill)", FILES["dc_shaman_common.h"])


if __name__ == "__main__":
    unittest.main()
