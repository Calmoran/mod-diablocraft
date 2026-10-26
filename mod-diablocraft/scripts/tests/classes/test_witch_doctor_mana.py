"""Witch Doctor 2b: Mana on the class-powers rule, who pays it and who spends it.

What this proves, and how:

  * **The payment and the pool.** tests/witch_doctor_mana/harness.cpp compiles the real dc_witch_doctor_mana.h, dc_resources.h and
    the generated dc_resource_data.h over the registry harness's shim Player and feeds it the sheets' own numbers (read here):
    Mana is in the Mana slot, one unit a point, 750, regenerating 50 a second by the module's pulse, no decay, full at login;
    each of the four on-hit runes (Spined Dart, Blazing Spiders, Toad Affinity, The Spirit Is Willing) adds its sheet value for
    each enemy hit and moves no other power; the pool stops at 750 and a spend (Haunt, Piranhas) at 0; another class, a Witch
    Doctor not showing Mana, a zero gain and no hit are not paid; Paragon pays +4 a point, 200 at 50 points. Six mutations
    planted in a scratch copy (the class guard, the displayed-power guard, the zero-hit guard, Mana stored ten units a point,
    Mana on the Rage slot, the pool) must each make it fail.
  * **One source of regeneration.** A row the module pays gets no core regeneration aura: the registry says so for every such
    row, the Witch Doctor has no "resource regeneration" record (it would be read by the pulse as a second source and its -100
    percent would multiply the sheet's and the gear's regeneration by zero), and the mask record that keeps the core's tick off
    the slot is still there. A core-paid Mana row would still get the aura (a planted sheet change shows it).
  * **The sheets agree.** The four Primaries are free and the eight spenders cost their sheet number in Mana (PowerType 0); the
    on-hit skills in the code are exactly the skills whose rune text says "hit"; the resource sheet, the registry and the base
    stats agree on 750 and 50; Paragon's Mana row is +4 for 50 points; the addon's name list, the stock blue and the orb's
    Mana fill exist for the class.
  * **The wiring.** Combat::Connected calls the Witch Doctor, and the class's name appears in src/ only in its folder and that
    one call.

What it does not prove: anything on a running server. The orb's look, the tooltips and a rune's hit need the skill beads and are
the test sheet's, live.

    python mod-diablocraft/scripts/tests/classes/test_witch_doctor_mana.py
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
sys.path.insert(0, str(MODULE / "scripts"))

import generate_class_resources as gcr  # noqa: E402

MANA_HEADER = "src/classes/witch_doctor/dc_witch_doctor_mana.h"
SOURCES = ["src/classes/dc_resources.h", "src/classes/dc_resource_carry.h", "src/classes/dc_resource_data.h", MANA_HEADER,
           "tests/witch_doctor_mana/harness.cpp"]
PRIMARIES = ("Poison Dart", "Corpse Spiders", "Plague of Toads", "Firebomb")
SPENDERS = ("Grasp of the Dead", "Firebats", "Haunt", "Locust Swarm", "Zombie Charger", "Spirit Barrage", "Acid Cloud",
            "Piranhas")
# The channels the module pays (generate_spells.py CHANNEL_DRAIN_SKILLS): the record carries no cost.
MODULE_PAID = {"Firebats"}
ON_HIT = {"Poison Dart": "Spined Dart", "Corpse Spiders": "Blazing Spiders", "Plague of Toads": "Toad Affinity",
          "Spirit Barrage": "The Spirit Is Willing"}
MANA_SLOT = 0
CLASS_ID = 7


def read(name):
    with (D3 / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(skill, rune, token):
    rows = [r for r in read("witch_doctor_skill_values.csv")
            if r["skill"] == skill and r["rune"] == rune and r["token"] == token and not r["qualifier"]]
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
    binary = harness_env.build([MODULE / "tests/witch_doctor_mana/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree,
                               includes=[MODULE / "tests/resource_registry/shim"])
    numbers = [value(skill, rune, "gain_resource") for skill, rune in ON_HIT.items()]
    numbers += [value("Haunt", "", "cost_resource"), value("Piranhas", "", "cost_resource")]
    return harness_env.run([str(binary)] + numbers, capture_output=True, text=True)


def manifest():
    with (MODULE / "data/generated/spell_shells.csv").open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class Harness(unittest.TestCase):
    def test_the_payment_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 40, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        data = "src/classes/dc_resource_data.h"
        mutations = [
            ("a Monk is paid Mana", (MANA_HEADER, "classId != Resources::Mana.classId ||", "")),
            ("a Witch Doctor not showing Mana is paid",
             (MANA_HEADER, "||\n            !Resources::Displayed(player, Resources::Mana)", "")),
            ("a hit-less call is paid", (MANA_HEADER, "hits == 0 ||", "")),
            ("Mana stored ten units a point",
             (data, '"Mana", Role::Primary, 0, "Mana", 1.0,', '"Mana", Role::Primary, 0, "Mana", 10.0,')),
            ("Mana in the Rage slot",
             (data, '"Mana", Role::Primary, 0, "Mana", 1.0,', '"Mana", Role::Primary, 1, "Rage", 1.0,')),
            ("Mana pool 700", (data, '"Mana", 1.0, 750.0,', '"Mana", 1.0, 700.0,')),
        ]
        for label, mutation in mutations:
            with self.subTest(label):
                try:
                    tree = scratch_tree(mutation)
                except AssertionError as error:
                    self.fail(str(error))
                out = build_and_run(tree)
                self.assertNotEqual(out.returncode, 0, f"{label} was not caught: {out.stdout[-500:]}")


class OneSource(unittest.TestCase):
    def test_no_module_paid_row_gets_a_core_regeneration_aura(self):
        paid = [e for e in gcr.registry() if e["paid_by"] == "module"]
        self.assertTrue(any(e["key"] == "mana" for e in paid))
        for entry in paid:
            self.assertEqual(entry["aura_regen"], 0.0, entry["key"])

    def test_a_core_paid_mana_row_still_gets_it(self):
        original = gcr.read

        def read(path):
            rows = original(path)
            if path.name == "class_resources.csv" and path.parent.name == "tunables":
                rows = [dict(r) for r in rows]
                for row in rows:
                    if row["resource_key"] == "mana":
                        row["paid_by"] = "core"
            return rows
        gcr.read = read
        try:
            mana = next(e for e in gcr.registry() if e["key"] == "mana")
        finally:
            gcr.read = original
        self.assertEqual(mana["aura_regen"], 50.0)

    def test_the_witch_doctor_has_the_mask_and_no_regeneration_record(self):
        names = {row["name"] for row in manifest()}
        self.assertNotIn("Witch Doctor - resource regeneration", names)
        self.assertIn("Witch Doctor - resource pulse - core regeneration mask", names)
        header = (MODULE / "src/combat/dc_spell_shells.h").read_text(encoding="utf-8")
        regeneration = header.split("inline uint32_t ResourceRegenerationFor(uint32_t classId)")[1].split("\n}\n")[0]
        self.assertNotIn(f"classId == {CLASS_ID}", regeneration)
        mask = header.split("inline uint32_t RegenerationMaskFor(uint32_t classId)")[1].split("\n}\n")[0]
        self.assertIn(f"classId == {CLASS_ID}", mask)


class Sheets(unittest.TestCase):
    def test_the_primaries_are_free_and_the_spenders_cost_their_sheet_number_in_mana(self):
        skills = {r["skill_name"]: r for r in read("witch_doctor_skills.csv")}
        for name in PRIMARIES:
            self.assertEqual(skills[name]["category"], "Primary", name)
            self.assertEqual(skills[name]["resource_cost"], "", name)
        self.assertEqual({n for n, r in skills.items() if r["resource_cost"]}, set(SPENDERS))
        records = {}
        text = (MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8")
        for insert in text.split("INSERT INTO `spell_dbc`")[1:]:
            header, _, body = insert.partition("VALUES")
            columns = re.findall(r"`(\w+)`", header)
            for line in body.splitlines():
                match = re.match(r"^\((86\d{3}),(.*)\)[,;]$", line)
                if match:
                    from test_class_records import split_values
                    records[int(match.group(1))] = dict(zip(columns, split_values(match.group(1) + "," + match.group(2))))
        ids = {row["name"]: int(row["spell_id"]) for row in manifest()}
        for name in PRIMARIES:
            self.assertEqual(records[ids[name]]["ManaCost"], "0", name)
        for name in SPENDERS:
            record = records[ids[name]]
            if name in MODULE_PAID:
                self.assertEqual(float(record["ManaCost"]), 0, name)
                continue
            self.assertEqual((record["PowerType"], float(record["ManaCost"])), ("0", float(value(name, "", "cost_resource"))), name)

    def test_the_on_hit_skills_are_the_ones_whose_rune_says_hit(self):
        gain = {(r["skill"], r["rune"]) for r in read("witch_doctor_skill_values.csv") if r["token"] == "gain_resource"}
        text = {(r["skill_name"], r["rune_name"]): r["full_rune_text"] for r in read("witch_doctor_runes.csv")}
        hitting = {skill for skill, rune in gain if re.search(r"\bhits?\b", text[(skill, rune)])}
        self.assertEqual(hitting, set(ON_HIT))
        self.assertEqual({(s, r) for s, r in gain if s in ON_HIT}, set(ON_HIT.items()))
        code = (MODULE / "src/classes/witch_doctor/dc_witch_doctor.cpp").read_text(encoding="utf-8")
        listed = re.search(r"PaysPerHit = \{(.*?)\};", code, re.S).group(1)
        self.assertEqual(set(re.findall(r'"([^"]+)"', listed)), set(ON_HIT))

    def test_every_on_hit_row_is_in_the_value_table_the_engine_reads(self):
        header = (MODULE / "src/combat/dc_spell_values.h").read_text(encoding="utf-8")
        ids = {row["name"]: int(row["spell_id"]) for row in manifest()}
        for skill, rune in ON_HIT.items():
            spell = ids[f"{skill} - {rune}"]
            self.assertRegex(header, r'\{%d, "gain_resource", "", Source::BasePoints, %d, \d+, Origin::Own, %d\}'
                             % (spell, spell, spell), skill)

    def test_the_resource_sheets_and_the_registry_agree(self):
        resource = {r["metric"]: r for r in read("witch_doctor_resource.csv")}
        self.assertEqual(float(resource["Maximum Mana (base)"]["value"]), 750)
        self.assertEqual(float(resource["Passive regeneration (base)"]["regen_per_second"]), 50)
        entry = next(e for e in gcr.registry() if e["d3_class"] == "Witch Doctor")
        self.assertEqual((entry["key"], entry["role"], entry["power"], entry["scale"], entry["pool"], entry["regen"],
                          entry["decay"], entry["paragon"], entry["starts_full"], entry["paid_by"], entry["token"]),
                         ("mana", "primary", "Mana", 1, 750.0, 50.0, "none", 4.0, True, "module", "MANA"))
        for row in read("witch_doctor_base_stats.csv"):
            self.assertEqual(float(row["resource_max"]), 750, row["level"])

    def test_paragon_has_a_mana_row_of_four_for_fifty_points(self):
        rows = [r for r in read("paragon.csv") if "mana" in r["resource_keys"].split(";")]
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["points_per_rank"], rows[0]["effect_per_point"], rows[0]["max_rank"]), ("1", "+4", "50"))

    def test_the_addon_and_the_orb_know_the_class(self):
        names = (REPO / "client-patch/addons/Torment/ResourceNames.lua").read_text(encoding="utf-8")
        self.assertRegex(names, r'WITCHDOCTOR = \{\s*MANA = \{ name = "Mana", colour = "0000FF", power = 0, role = "primary", key = "mana"')
        # The generated stock row's blue is the registry's colour (class_resources.csv display_colour).
        entry = next(e for e in gcr.registry() if e["d3_class"] == "Witch Doctor")
        self.assertEqual(entry["colour"].upper().lstrip("#"), "0000FF")
        for half in (1, 2):
            self.assertTrue((REPO / f"client-patch/addons/ElvUI_Torment/media/orb_fill_mana_{half}.blp").is_file(), half)
            self.assertTrue((REPO / f"client-patch/art/ui/elvui/orb_fill_mana_{half}.png").is_file(), half)


class Wiring(unittest.TestCase):
    def test_connected_calls_the_witch_doctor(self):
        text = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat" / "dc_combat_internal.h",
                                                               *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])
        body = text.split("void Connected(Player* player, std::uint32_t spellId, unsigned enemies)")[1].split("}")[0]
        self.assertIn("WitchDoctor::Connected(player, spellId, enemies);", body)

    def test_the_witch_doctor_is_named_only_in_its_folder(self):
        found = set()
        for path in (MODULE / "src").rglob("*.*"):
            rel = path.relative_to(MODULE).as_posix()
            if path.suffix in (".cpp", ".h") and not rel.startswith("src/classes/witch_doctor/") \
                    and re.search(r"\bWitchDoctor\b", path.read_text(encoding="utf-8", errors="replace")):
                found.add(rel)
        self.assertEqual(found, {"src/combat/dc_combat.cpp", "src/combat/dc_combat_resolve.cpp"})   # the seams: the Connected and Landed calls, the pets' RegisterScripts

    def test_the_pay_reads_the_sheet_number_and_the_class(self):
        text = (MODULE / "src/classes/witch_doctor/dc_witch_doctor.cpp").read_text(encoding="utf-8")
        self.assertIn('Numbers::Get(spellId, "gain_resource")', text)
        self.assertIn("Classes::ClassIdOf(player)", text)


if __name__ == "__main__":
    unittest.main()
