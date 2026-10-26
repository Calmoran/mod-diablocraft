"""diablocraft-resource-registry: the class resource registry.

What this proves, and how:

  * **Behaviour did not move.** tests/resource_registry/harness.cpp compiles
    the HEAD expressions the registry replaced (copied verbatim) beside the
    real dc_resources.h, dc_resource_data.h and dc_cost_math.h, on a shim
    Player that copies the core's SetPower/SetMaxPower/ModifyPower arithmetic
    and logs every write. Fury gain (the three clamped-SetPower sites,
    ChangeFury and Ancients' ModifyPower), spend (spend-all runes, Seismic
    Slam's extra), max (Recompute and the max-power hook), Berserker's
    threshold and .dc fury; Arcane Power gain (energize), max, the channel
    preflight and a full channel run with its carried fraction, Star Pact,
    Prism's reduction; and the cost read for every slot: end state and write
    sequence must match case for case.
  * **The harness can fail.** Mutations planted in scratch copies of the
    helper and the generated header (a scale, a clamp, the write path) must
    each make it report a difference.
  * **The generator refuses what the registry cannot carry.** A primary slot
    that disagrees with class_map.csv, a pool that disagrees with the base
    sheet, a regen that disagrees with wizard_resource.csv, stock decay on a
    slot without it, decay switched off on Rage, regeneration on a slot the
    aura does not drive, and a scale other than one or ten. Two classes may share a slot at their own scales
    (class powers P2: the Monk's Spirit ten a point, the Necromancer's Essence one, on Runic Power).
  * **The addon's name list is the registry.** ResourceNames.lua is the
    current render, loads in Lua 5.1, and every class token and slot token
    finds its D3 name and colour; planted changes in a scratch copy (a name,
    a class token, a slot token, a dropped row) each fail the lookup.
  * **Every D3 resource has its row (rollout A item 2).** The six planned
    rows carry the researched pool, regen, slot and scale; a planned class
    compiles into nothing.
  * **Energy at another rate is carried, not refused.** A planned class
    that joins class_map.csv on Energy at a rate other than 10/s gets
    energy_rate_pct, the percent that takes the native 10/s to the D3 rate
    (Wrath -75, Hatred -50), and goes live; a rate that is not a whole
    percent of the native one is refused; generator copies with the
    formula or the refusal changed are caught. The record that carries it
    is test_energy_rate.py's.
  * **Paragon Maximum Resource is per resource (item 5).** paragon.csv's
    resource_keys give Mana 4, Fury/Spirit/Essence 1, Wrath/Arcane
    Power/Hatred 0.5, Discipline 0; the harness proves 0.5 pays +1 per two
    points up to the cap, and a rounding mutation is caught.
  * **The records read the registry.** generate_spells.py's per-class power
    and regeneration come from it and give today's values; the generated
    header is current.

What it does not prove: anything live. Regeneration and decay are the core's
own paths (the Wizard's regeneration aura record is byte-identical after
regeneration; Fury's decay is stock Rage loss), so the harness has no module
code to compare for them. docs/test-resource-registry.md is the in-game check.

    python mod-diablocraft/scripts/tests/classes/test_resource_registry.py
"""

import shutil
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
SCRATCH = REPO / "azerothcore-wotlk" / "build" / "_agent-scratch" / "resource_registry"
sys.path.insert(0, str(MODULE / "scripts"))

import generate_class_resources as gcr  # noqa: E402
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
import barbarian_source  # noqa: E402

# Files the harness compiles, copied (never linked) into a scratch tree with
# the same layout so a mutation cannot touch the real ones.
SOURCES = ["src/classes/dc_resources.h", "src/classes/dc_resource_carry.h", "src/classes/dc_resource_data.h",
           "src/combat/dc_cost_math.h"]


def build_and_run(tree):
    binary = harness_env.build([MODULE / "tests/resource_registry/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree,
                               includes=[MODULE / "tests/resource_registry/shim"])
    return harness_env.run([str(binary)], capture_output=True, text=True)


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


class Harness(unittest.TestCase):
    def test_before_and_after_agree_case_for_case(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreater(cases, 400000, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("a Fury point stored as ten Rage units",
             ("src/classes/dc_resource_data.h", '"Fury", Role::Primary, 1, "Rage", 1.0,',
              '"Fury", Role::Primary, 1, "Rage", 10.0,')),
            # The core's SetPower caps at the maximum itself, so only the
            # floor of the clamp is observable: below zero wraps to uint32.
            ("the clamp lets a spend fall below zero",
             ("src/classes/dc_resources.h", "std::clamp(wanted, 0, cap)", "std::clamp(wanted, -1, cap)")),
            ("Ancients' Fury written through SetPower instead of ModifyPower",
             ("src/classes/dc_resources.h", "ModifyUnits(player, r, WholeUnits(player, r, points));",
              "Add(player, r, points);")),
            ("a change rounded instead of carried",
             ("src/classes/dc_resource_carry.h", "owed = std::max(0.0, total - whole);", "owed = 0;")),
            ("the carry kept at the maximum",
             ("src/classes/dc_resources.h", "            owed = 0;\n        return", "        return")),
            ("one carry for gains and losses",
             ("src/classes/dc_resources.h", "double& owed = units > 0 ? carry.gain : carry.loss;",
              "double& owed = carry.gain;")),
            ("a cost's dropped part not carried",
             ("src/classes/dc_resources.h", "return dropped > 0 ? -WholeUnits(player, r, -ToPoints(r, dropped)) : 0;",
              "return 0;")),
            ("a cost's float noise not read away",
             ("src/classes/dc_resource_carry.h", "std::round(exact * 10000.0) / 10000.0", "exact")),
            ("a forgotten player keeps its carry",
             ("src/classes/dc_resources.h", "            it = it->first.first == player ? store.owed.erase(it) : std::next(it);",
              "            it = std::next(it);")),
            ("Arcane Power's slot changed without its code",
             ("src/classes/dc_resource_data.h", '"Arcane Power", Role::Primary, 3, "Energy", 1.0,',
              '"Arcane Power", Role::Primary, 0, "Energy", 1.0,')),
            ("a class with no Mana resource keeps its Mana maximum",
             ("src/classes/dc_resources.h", "        if (slot != POWER_MANA)\n            return false;\n",
              "")),
            ("a half paragon point rounded up instead of paid per pair",
             ("src/classes/dc_resources.h", "return static_cast<double>(points * halves / 2);",
              "return static_cast<double>((points * halves + 1) / 2);")),
            ("the maximum written without rounding",
             ("src/classes/dc_resources.h",
              "player->SetMaxPower(Slot(r), static_cast<int32>(std::llround(ToUnits(r, points))));",
              "player->SetMaxPower(Slot(r), static_cast<int32>(ToUnits(r, points)));")),
        ]
        for label, mutation in mutations:
            with self.subTest(label):
                out = build_and_run(scratch_tree(mutation))
                self.assertNotEqual(out.returncode, 0, f"{label} was not caught: {out.stdout[-500:]}")


class Generator(unittest.TestCase):
    def patched(self, sheet, change):
        """registry() with one sheet's rows altered by change(rows)."""
        original = gcr.read

        def read(path):
            rows = original(path)
            if path.name == sheet[1] and path.parent.name == sheet[0]:
                rows = [dict(r) for r in rows]
                change(rows)
            return rows
        gcr.read = read
        try:
            return gcr.registry()
        finally:
            gcr.read = original

    def refused(self, sheet, change, words):
        with self.assertRaises(SystemExit) as caught:
            self.patched(sheet, change)
        self.assertIn(words, str(caught.exception))

    @staticmethod
    def row(rows, d3_class):
        return next(r for r in rows if r["d3_class"] == d3_class)

    def test_the_rows_are_today_s_behaviour(self):
        entries = {e["key"]: e for e in gcr.registry()}
        self.assertEqual(set(entries), {"fury", "arcane_power", "spirit", "wrath", "essence", "hatred", "discipline", "mana", "maelstrom"})
        fury, ap = entries["fury"], entries["arcane_power"]
        self.assertEqual((fury["power"], fury["scale"], fury["pool"], fury["regen"], fury["decay"],
                          fury["paragon"]), ("Rage", 1, 100.0, 0.0, "stock", 1.0))
        self.assertEqual((ap["power"], ap["scale"], ap["pool"], ap["regen"], ap["decay"], ap["paragon"]),
                         ("Energy", 1, 100.0, 10.0, "none", 0.5))
        self.assertEqual(ap["aura_regen"], 0.0)
        # Class powers P2: every power one slot unit a point (the x10 convention retired); the Wizard's Arcane Power
        # paid by the module's pulse, so every live row is.
        self.assertEqual({e["key"]: (e["scale"], e["paid_by"]) for e in entries.values()},
                         {k: (1, "module") for k in entries})
        # The Monk (diablocraft-1cuvw): Spirit on the Runic Power slot, no decay, no regeneration.
        spirit = entries["spirit"]
        self.assertEqual((spirit["power"], spirit["scale"], spirit["pool"], spirit["regen"], spirit["decay"],
                          spirit["paragon"], spirit["needs"]), ("Runic Power", 1, 250.0, 0.0, "none", 1.0, []))
        # The Crusader: Wrath on the Energy slot, one unit a point, 2.5 a second (x0.25 of Energy's native 10, the
        # energy_rate record's -75), no decay.
        wrath = entries["wrath"]
        self.assertEqual((wrath["d3_class"], wrath["class_id"], wrath["power"], wrath["scale"], wrath["pool"], wrath["regen"],
                          wrath["decay"], wrath["paragon"], wrath["needs"], wrath["energy_rate_pct"]),
                         ("Crusader", 4, "Energy", 1, 100.0, 2.5, "none", 0.5, [], -75))
        # The Necromancer (diablocraft-im7mr.1): Essence on the same slot, pool 200; class powers P2 stores it one
        # unit a point beside the Monk's ten, so a full bar is 200 slot units.
        essence = entries["essence"]
        self.assertEqual((essence["power"], essence["scale"], essence["pool"], essence["regen"], essence["decay"],
                          essence["paragon"], essence["needs"], essence["class_id"]),
                         ("Runic Power", 1, 200.0, 0.0, "none", 1.0, [], 5))
        self.assertEqual(essence["pool"] * essence["scale"], 200)
        # The Demon Hunter (diablocraft-vawmy.1): Hatred on Energy at 5 a second (x0.5 of Energy's native 10, the energy_rate
        # record's -50), pool 125; Discipline its second power in the Focus slot, pool 30, 1 a second, none from Paragon.
        hatred, discipline = entries["hatred"], entries["discipline"]
        self.assertEqual((hatred["d3_class"], hatred["class_id"], hatred["role"], hatred["power"], hatred["scale"], hatred["pool"],
                          hatred["regen"], hatred["decay"], hatred["paragon"], hatred["needs"], hatred["energy_rate_pct"]),
                         ("Demon Hunter", 6, "primary", "Energy", 1, 125.0, 5.0, "none", 0.5, [], -50))
        self.assertEqual((discipline["d3_class"], discipline["class_id"], discipline["role"], discipline["power"], discipline["scale"],
                          discipline["pool"], discipline["regen"], discipline["decay"], discipline["paragon"], discipline["needs"],
                          discipline["energy_rate_pct"]),
                         ("Demon Hunter", 6, "second", "Focus", 1, 30.0, 1.0, "none", 0.0, [], None))
        # The Witch Doctor (diablocraft-vxrcu.1): real Mana, 750 at every level, 50 a second paid by the pulse (a fine step
        # at a time, the core's Mana tick masked), 4 a Paragon point, none of D3's decay.
        mana = entries["mana"]
        self.assertEqual((mana["d3_class"], mana["class_id"], mana["role"], mana["power"], mana["scale"], mana["pool"], mana["regen"],
                          mana["decay"], mana["paragon"], mana["needs"], mana["energy_rate_pct"], mana["paid_by"]),
                         ("Witch Doctor", 7, "primary", "Mana", 1, 750.0, 50.0, "none", 4.0, [], None, "module"))
        # The Shaman (diablocraft-xnrvn.2, 2b): Maelstrom on the Barbarian's Rage slot, 100 at every level, no regeneration of its own,
        # the draft's timed out-of-combat loss, paid by the pulse; Paragon's Maximum Resource row is the Fury model's, 1 a point.
        maelstrom = entries["maelstrom"]
        self.assertEqual((maelstrom["d3_class"], maelstrom["class_id"], maelstrom["role"], maelstrom["power"], maelstrom["scale"],
                          maelstrom["pool"], maelstrom["regen"], maelstrom["decay"], maelstrom["paragon"], maelstrom["needs"],
                          maelstrom["energy_rate_pct"], maelstrom["paid_by"], maelstrom["token"]),
                         ("Shaman", 8, "primary", "Rage", 1, 100.0, 0.0, "timed", 1.0, [], None, "module", "MAELSTROM"))

    def test_who_enters_the_world_full(self):
        # diablocraft-zr3sp (the designer's card q-1014-21): Spirit starts full as Arcane Power does; Fury stays empty as D3 has it.
        entries = {e["key"]: e for e in gcr.registry()}
        self.assertEqual({key: e["starts_full"] for key, e in entries.items()},
                         {"fury": False, "arcane_power": True, "spirit": True, "wrath": False, "essence": False,
                          "hatred": True, "discipline": True, "mana": True, "maelstrom": False})
        header = (MODULE / "src/classes/dc_resource_data.h").read_text(encoding="utf-8")
        self.assertIn('"Fury", Role::Primary, 1, "Rage", 1.0, 100.0, 0.0, Decay::Stock, 0xFF0000, 1.0, false, "FURY", true}', header)
        self.assertIn('"Spirit", Role::Primary, 6, "Runic Power", 1.0, 250.0, 0.0, Decay::None, 0x00D1FF, 1.0, true, "SPIRIT", true}', header)
        # Essence starts empty (PM on diablocraft-im7mr.1, the brief's done line), until G2 finds D3's starting value.
        self.assertIn('"Essence", Role::Primary, 6, "Runic Power", 1.0, 200.0, 0.0, Decay::None, 0x2EA78F, 1.0, false, "ESSENCE", true}', header)
        # Hatred and Discipline start full (the Demon Hunter build brief's done line: 125 of 125 and 30 of 30).
        self.assertIn('"Hatred", Role::Primary, 3, "Energy", 1.0, 125.0, 5.0, Decay::None, 0x853215, 0.5, true, "HATRED", true}', header)
        self.assertIn('"Discipline", Role::Second, 2, "Focus", 1.0, 30.0, 1.0, Decay::None, 0x6161A4, 0.0, true, "DISCIPLINE", true}', header)
        # Mana starts full (the Witch Doctor build brief's done line: 750 of 750; D3 gives no starting value, G2 question 2).
        self.assertIn('"Mana", Role::Primary, 0, "Mana", 1.0, 750.0, 50.0, Decay::None, 0x0000FF, 4.0, true, "MANA", true}', header)
        # Maelstrom starts empty (the Shaman build brief: starts at 0, the Fury model).
        self.assertIn('"Maelstrom", Role::Primary, 1, "Rage", 1.0, 100.0, 0.0, Decay::Timed, 0x558FF2, 1.0, false, "MAELSTROM", true}', header)

    def test_a_bad_starts_full_is_refused(self):
        self.refused(("tunables", "class_resources.csv"),
                     lambda rows: self.row(rows, "Monk").update(starts_full="yes"), "starts_full 'yes' is not 0 or 1")
        self.refused(("tunables", "class_resources.csv"),
                     lambda rows: self.row(rows, "Monk").update(starts_full=""), "needs starts_full 0 or 1")

    def test_a_planned_class_may_leave_it_undecided(self):
        # No class is planned any more (the Witch Doctor, the last, went live with diablocraft-vxrcu.1): plant one by taking the Witch Doctor
        # out of class_map.csv and leaving its two decisions blank, as its row was before.
        original = gcr.read

        def read(path):
            rows = [dict(r) for r in original(path)]
            if path.name == "class_map.csv":
                rows = [r for r in rows if r["d3_class"] != "Witch Doctor"]
            if path.name == "class_resources.csv" and path.parent.name == "tunables":
                for r in rows:
                    if r["d3_class"] == "Witch Doctor":
                        r.update(starts_full="", paid_by="")
            return rows
        gcr.read = read
        try:
            planned = {(e["d3_class"], e["key"]): e for e in gcr.rows(include_planned=True) if not e["live"]}
            live = {e["key"] for e in gcr.rows()}
        finally:
            gcr.read = original
        self.assertEqual(set(planned), {("Witch Doctor", "mana")})
        self.assertFalse(planned[("Witch Doctor", "mana")]["starts_full"])
        self.assertNotIn("mana", live)

    def test_the_header_is_current(self):
        self.assertEqual((MODULE / "src/classes/dc_resource_data.h").read_text(encoding="utf-8"),
                         gcr.render(gcr.registry()))

    def test_a_slot_that_disagrees_with_class_map_is_refused(self):
        self.refused(("tunables", "class_resources.csv"),
                     lambda rows: self.row(rows, "Barbarian").update(wow_power="Runic Power"), "class_map.csv")

    def test_a_pool_that_disagrees_with_the_base_sheet_is_refused(self):
        self.refused(("d3", "class_resources.csv"),
                     lambda rows: self.row(rows, "Barbarian").update(pool="125"), "barbarian_base_stats.csv")

    def test_a_second_pool_that_disagrees_with_the_base_sheet_is_refused(self):
        # The Demon Hunter's Discipline is checked against the sheet's discipline_max, as Hatred is against resource_max.
        def change(rows):
            next(r for r in rows if r["resource_key"] == "discipline").update(pool="40")
        self.refused(("d3", "class_resources.csv"), change, "demon_hunter_base_stats.csv")

    def test_a_second_regen_that_disagrees_with_the_resource_sheet_is_refused(self):
        # Every resource of the class is held to the sheet's regen_per_second column, in order: Hatred 5, Discipline 1.
        def change(rows):
            next(r for r in rows if r["metric"].startswith("Passive regeneration, Discipline")).update(regen_per_second="2")
        self.refused(("d3", "demon_hunter_resource.csv"), change, "demon_hunter_resource.csv")

    def test_a_regen_that_disagrees_with_the_resource_sheet_is_refused(self):
        # The resource sheet moves (a registry regen other than Energy's
        # native 10 is refused earlier, as an unbuilt mechanism).
        def change(rows):
            for row in rows:
                if (row.get("regen_per_second") or "").strip():
                    row["regen_per_second"] = "12"
        self.refused(("d3", "wizard_resource.csv"), change, "wizard_resource.csv")

    def test_decay_switched_off_on_rage_is_refused(self):
        def change(rows):
            self.row(rows, "Barbarian").update(decay="none")
        self.refused(("tunables", "class_resources.csv"), change, "decay 'none' needs a resource D3 does not decay")

    def test_stock_decay_on_a_slot_without_it_is_refused(self):
        self.refused(("tunables", "class_resources.csv"),
                     lambda rows: self.row(rows, "Wizard").update(decay="stock"), "decay 'stock'")

    def test_regeneration_no_stock_path_pays_is_refused(self):
        # A row the module does not pay regenerates only on a slot the core refills (the Mana aura, Energy's native
        # gain); a planned class's Mana planted on Happiness (the Witch Doctor out of class_map.csv), with no payer, is refused.
        original = gcr.read

        def read(path):
            rows = [dict(r) for r in original(path)]
            if path.name == "class_map.csv":
                rows = [r for r in rows if r["d3_class"] != "Witch Doctor"]
            if path.name == "class_resources.csv" and path.parent.name == "tunables":
                for r in rows:
                    if r["d3_class"] == "Witch Doctor":
                        r.update(wow_power="Happiness", token="MANA_HAPPINESS", paid_by="core")
            return rows
        gcr.read = read
        try:
            with self.assertRaises(SystemExit) as caught:
                gcr.registry()
        finally:
            gcr.read = original
        self.assertIn("no stock path refills Happiness", str(caught.exception))

    def test_the_module_pays_regeneration_on_any_slot(self):
        # Discipline regenerates 1/s in Focus, which the core never refills for a player: the pulse pays it.
        entry = next(e for e in gcr.rows(include_planned=True) if e["key"] == "discipline")
        self.assertEqual((entry["power"], entry["paid_by"], entry["regen"]), ("Focus", "module", 1.0))
        self.assertIn("Focus", gcr.MODULE_ONLY_SLOTS)

    def test_two_classes_on_one_slot_keep_their_own_scales(self):
        """Class powers P2: the Monk's Spirit and the Necromancer's Essence share Runic Power, both one a point now; the
        header reads each class's cost at its own scale and a class with no row there at one."""
        header = (MODULE / "src/classes/dc_resource_data.h").read_text(encoding="utf-8")
        self.assertIn("constexpr double ScaleOf(uint32_t classId, uint32_t power)", header)
        self.assertNotIn("ScaleOfSlot", header)
        entries = {e["key"]: e for e in gcr.registry()}
        self.assertEqual((entries["spirit"]["power"], entries["spirit"]["scale"]), ("Runic Power", 1))
        self.assertEqual((entries["essence"]["power"], entries["essence"]["scale"]), ("Runic Power", 1))

    def test_a_scale_other_than_one_or_ten_is_refused(self):
        def change(rows):
            rows.append({"d3_class": "Barbarian", "resource_key": "test", "wow_power": "Mana",
                         "token": "TEST", "paid_by": "module", "storage_scale": "5", "decay": "none", "display_colour": "#000000",
                         "starts_full": "0", "notes": "x"})
        original = gcr.read

        def read(path):
            rows = [dict(r) for r in original(path)]
            if path.name == "class_resources.csv" and path.parent.name == "tunables":
                change(rows)
            if path.name == "class_resources.csv" and path.parent.name == "d3":
                rows.append({"d3_class": "Barbarian", "resource_key": "test", "d3_name": "Test",
                             "role": "second", "pool": "1", "regen_per_second": "0",
                             "decays_out_of_combat": "0", "source": "x", "notes": "x"})
            return rows
        gcr.read = read
        try:
            with self.assertRaises(SystemExit) as caught:
                gcr.registry()
        finally:
            gcr.read = original
        self.assertIn("is not 1 or 10", str(caught.exception))

    def test_the_spell_generator_reads_the_registry(self):
        import generate_spells
        self.assertEqual(generate_spells.power_of("Barbarian"), (1, 1, "rage_points"))
        self.assertEqual(generate_spells.power_of("Monk"), (6, 1, "runic_power_points"))
        self.assertEqual(generate_spells.power_of("Wizard"), (3, 1, "energy_points"))
        self.assertIsNone(generate_spells.primary_regeneration("Barbarian"))
        # Energy's native 10/s is Arcane Power's: no regeneration aura.
        self.assertIsNone(generate_spells.primary_regeneration("Wizard"))
        self.assertEqual(generate_spells.POWER_FURY, 1)


NAMES_PROBE = """
dofile(arg[1])
local out = {}
for token, slots in pairs(Diablocraft.ResourceNames) do
    for slot, e in pairs(slots) do
        out[#out + 1] = table.concat({token, slot, e.name, e.colour, tostring(e.power), e.role, e.key, e.token}, "|")
    end
end
table.sort(out)
print(table.concat(out, "\\n"))
"""


def lua_lookup(path):
    lua = shutil.which("lua5.1") or shutil.which("lua")
    if not lua:
        raise unittest.SkipTest("no Lua interpreter")
    probe = SCRATCH / "names_probe.lua"
    probe.parent.mkdir(parents=True, exist_ok=True)
    probe.write_text(NAMES_PROBE, encoding="utf-8")
    out = subprocess.run([lua, str(probe), str(path)], capture_output=True, text=True)
    if out.returncode != 0:
        return None
    return {tuple(line.split("|")) for line in out.stdout.splitlines() if line}


class Names(unittest.TestCase):
    LUA = gcr.NAMES_LUA
    # What the addon must find today, typed from the sheets rather than read
    # back through the generator.
    EXPECTED = {("WARRIOR", "RAGE", "Fury", "FF0000", "1", "primary", "fury", "FURY"),
                ("MAGE", "ENERGY", "Arcane Power", "FFFF00", "3", "primary", "arcane_power", "ARCANE_POWER"),
                ("MONK", "RUNIC_POWER", "Spirit", "00D1FF", "6", "primary", "spirit", "SPIRIT"),
                ("PALADIN", "ENERGY", "Wrath", "E8ECD9", "3", "primary", "wrath", "WRATH"),
                ("NECROMANCER", "RUNIC_POWER", "Essence", "2EA78F", "6", "primary", "essence", "ESSENCE"),
                ("HUNTER", "ENERGY", "Hatred", "853215", "3", "primary", "hatred", "HATRED"),
                ("HUNTER", "FOCUS", "Discipline", "6161A4", "2", "second", "discipline", "DISCIPLINE"),
                ("WITCHDOCTOR", "MANA", "Mana", "0000FF", "0", "primary", "mana", "MANA"),
                ("SHAMAN", "RAGE", "Maelstrom", "558FF2", "1", "primary", "maelstrom", "MAELSTROM")}

    def test_the_list_is_current(self):
        self.assertEqual(self.LUA.read_text(encoding="utf-8"), gcr.render_names(gcr.registry()))

    def test_every_class_and_slot_finds_its_name(self):
        self.assertEqual(lua_lookup(self.LUA), self.EXPECTED)

    def test_class_tokens_are_the_client_s(self):
        self.assertEqual(gcr.class_token("Death Knight"), "DEATHKNIGHT")
        self.assertEqual(gcr.class_token("Warrior"), "WARRIOR")
        with self.assertRaises(SystemExit):
            gcr.class_token("Monk 2")

    def test_a_planted_difference_is_caught(self):
        text = self.LUA.read_text(encoding="utf-8")
        mutations = [
            ("a renamed resource", 'name = "Arcane Power", colour = "FFFF00", power = 3, role', 'name = "Mana", colour = "FFFF00", power = 3, role'),
            ("a D3 class name as the token", "    MAGE = {", "    WIZARD = {"),
            ("the slot's WoW name as the token", "    WARRIOR = {\n        RAGE = {", "    WARRIOR = {\n        Rage = {"),
            ("a wrong colour", 'name = "Fury", colour = "FF0000", power = 1, role', 'name = "Fury", colour = "FF0001", power = 1, role'),
            ("a wrong token", 'token = "SPIRIT" }', 'token = "RUNIC_POWER" }'),
            ("Arcane Power left on the Mana token", "    MAGE = {\n        ENERGY = {", "    MAGE = {\n        MANA = {"),
            ("a dropped row", text[text.index("    WARRIOR = {"):text.index("    MAGE = {")], ""),
        ]
        for label, old, new in mutations:
            with self.subTest(label):
                self.assertEqual(text.count(old), 1, label)
                mutant = SCRATCH / "ResourceNames_mutant.lua"
                mutant.write_text(text.replace(old, new), encoding="utf-8")
                self.assertNotEqual(lua_lookup(mutant), self.EXPECTED, f"{label} was not caught")


PLANNED = {
    # key: (class, slot, scale, pool, regen, decay, paragon, needs, energy_rate_pct)
}


def mutated_generator(old, new):
    """A scratch copy of generate_class_resources.py with one planted change,
    imported as its own module (the real file is never touched)."""
    import importlib.util
    text = (MODULE / "scripts/generate/classes/generate_class_resources.py").read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise AssertionError(f"mutation target {old!r} not found exactly once")
    path = SCRATCH / "generate_class_resources_mutant.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.replace(old, new), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("gcr_mutant", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.MODULE, module.DATA, module.TUNABLES = gcr.MODULE, gcr.DATA, gcr.TUNABLES
    return module


def with_live_class(module, d3_class, class_id):
    """module.rows() with d3_class added to class_map.csv (and its primary
    slot as wow_power_type), as adding the class would."""
    original = module.read
    slot = next(r["wow_power"] for r in original(module.TUNABLES / "class_resources.csv")
                if r["d3_class"] == d3_class and next(
                    d["role"] for d in original(module.DATA / "class_resources.csv")
                    if d["d3_class"] == d3_class and d["resource_key"] == r["resource_key"]) == "primary")

    def read(path):
        rows = [dict(r) for r in original(path)]
        if path.name == "class_map.csv":
            rows.append({"d3_class": d3_class, "wow_class": d3_class, "wow_power_type": slot,
                         "primary_stat": "Dexterity", "class_id": str(class_id), "wow_class_id": "12"})
        if path.name == "class_resources.csv" and path.parent.name == "tunables":
            for r in rows:   # adding the class decides whether it starts full and who pays it (live rows need both)
                if r["d3_class"] == d3_class and not r["starts_full"]:
                    r["starts_full"] = "0"
                if r["d3_class"] == d3_class and not r["paid_by"]:
                    r["paid_by"] = "module" if r["wow_power"] in gcr.MODULE_ONLY_SLOTS else "core"
        return rows
    module.read = read
    try:
        return module.rows()
    finally:
        module.read = original


class Planned(unittest.TestCase):
    def test_every_d3_resource_has_its_row(self):
        planned = {e["key"]: e for e in gcr.rows(include_planned=True) if not e["live"]}
        self.assertEqual(set(planned), set(PLANNED))
        for key, want in PLANNED.items():
            e = planned[key]
            self.assertEqual((e["d3_class"], e["power"], e["scale"], e["pool"], e["regen"], e["decay"],
                              e["paragon"], e["needs"], e["energy_rate_pct"]), want, key)
            self.assertIsNone(e["class_id"])

    def test_planned_rows_compile_into_nothing(self):
        header = (MODULE / "src/classes/dc_resource_data.h").read_text(encoding="utf-8")
        names = gcr.NAMES_LUA.read_text(encoding="utf-8")
        for key, want in PLANNED.items():
            self.assertNotIn(f'"{key}"', header)
            self.assertNotIn(f'"{want[0]}"', names)

    def test_energy_at_another_rate_goes_live_with_its_percent(self):
        # The percent Player::UpdateEnergyRegen multiplies the native 10/s by: 5/s is x0.5 (-50). The Crusader's
        # 2.5/s (-75) and the Demon Hunter's 5/s are live and pinned in Generator.
        for d3_class, key, percent in (("Crusader", "wrath", -75), ("Demon Hunter", "hatred", -50)):
            with self.subTest(d3_class):
                live = [e for e in gcr.registry() if e["key"] == key]
                self.assertEqual([(e["power"], e["needs"], e["energy_rate_pct"]) for e in live],
                                 [("Energy", [], percent)])
        self.assertEqual(gcr.MECHANISMS, {})

    def test_energy_at_the_native_rate_or_off_energy_has_no_percent(self):
        live = {e["key"]: e for e in gcr.registry()}
        self.assertEqual({k: live[k]["energy_rate_pct"] for k in live}, {"fury": None, "arcane_power": None,
                                                                         "spirit": None, "wrath": -75,
                                                                         "essence": None, "hatred": -50,
                                                                         "discipline": None, "mana": None,
                                                                         "maelstrom": None})
        self.assertIsNone(gcr.energy_rate_percent(10.0, 10.0))
        self.assertEqual(gcr.energy_rate_percent(0.0, 10.0), -100)
        self.assertEqual(gcr.energy_rate_percent(20.0, 10.0), 100)

    def test_a_rate_that_is_not_a_whole_percent_is_refused(self):
        with self.assertRaises(SystemExit) as caught:
            gcr.energy_rate_percent(2.55, 10.0)
        self.assertIn("not a whole percent", str(caught.exception))

    def test_a_built_mechanism_goes_live(self):
        # The Witch Doctor's Mana is live and paid by the pulse like the others'.
        live = [e for e in gcr.registry() if e["d3_class"] == "Witch Doctor"]
        self.assertEqual([(e["key"], e["power"], e["paid_by"]) for e in live], [("mana", "Mana", "module")])
        # Runic Power with its decay off is the Monk's, built with it: a class that is not a Death Knight has no
        # Runic Power decay in the core (Player::RegenerateAll), so the Necromancer's Essence needs nothing more.
        live = [e for e in with_live_class(gcr, "Necromancer", 90) if e["d3_class"] == "Necromancer"]
        self.assertEqual([(e["key"], e["power"], e["decay"], e["needs"]) for e in live],
                         [("essence", "Runic Power", "none", [])])

    def test_a_changed_energy_rate_rule_is_caught(self):
        # The percent formula and the whole-percent refusal each have a planted copy that must be seen.
        formula = mutated_generator("percent = (regen / native - 1) * 100", "percent = (regen / native) * 100")
        self.assertNotEqual(formula.energy_rate_percent(2.5, 10.0), -75)
        refusal = mutated_generator("if percent != int(percent):", "if False:")
        try:
            refusal.energy_rate_percent(2.55, 10.0)
        except SystemExit:
            self.fail("the mutant still refused a fractional percent")
        sloppy = mutated_generator("if regen == native:\n        return None", "if False:\n        return None")
        self.assertNotEqual(sloppy.energy_rate_percent(10.0, 10.0), None)


class ParagonSource(unittest.TestCase):
    def test_per_point_comes_from_paragon_csv(self):
        self.assertEqual(gcr.paragon_per_point(),
                         {"mana": 4.0, "fury": 1.0, "spirit": 1.0, "essence": 1.0, "maelstrom": 1.0,
                          "wrath": 0.5, "arcane_power": 0.5, "hatred": 0.5})

    def patched_paragon(self, change):
        original = gcr.read

        def read(path):
            rows = [dict(r) for r in original(path)]
            if path.name == "paragon.csv":
                change(rows)
            return rows
        gcr.read = read
        try:
            return gcr.paragon_per_point()
        finally:
            gcr.read = original

    @staticmethod
    def resource_row(rows, key):
        return next(r for r in rows if key in r["resource_keys"].split(";"))

    def test_a_disagreeing_per_point_is_refused(self):
        with self.assertRaises(SystemExit) as caught:
            self.patched_paragon(lambda rows: self.resource_row(rows, "fury").update(per_point="2"))
        self.assertIn("disagrees", str(caught.exception))

    def test_a_resource_in_two_rows_is_refused(self):
        with self.assertRaises(SystemExit) as caught:
            self.patched_paragon(lambda rows: self.resource_row(rows, "mana").update(
                resource_keys="mana;wrath"))
        self.assertIn("two Maximum Resource rows", str(caught.exception))

    def test_a_quarter_point_is_refused(self):
        with self.assertRaises(SystemExit) as caught:
            self.patched_paragon(lambda rows: self.resource_row(rows, "wrath").update(effect_per_point="+0.25"))
        self.assertIn("whole or half", str(caught.exception))


class DisplayPower(unittest.TestCase):
    """Item 4: ChrClasses.DisplayPower follows the registry's primary slot."""

    def test_only_the_mage_paladin_hunter_and_shaman_rows_are_overlaid(self):
        sql, client, overlays = gcr.display_power(gcr.registry())
        self.assertEqual([(o["ID"], o["DisplayPower"], o["Name_Lang_enUS"]) for o in overlays],
                         [(8, 3, "Mage"), (2, 3, "Paladin"), (3, 3, "Hunter"), (7, 1, "Shaman")])
        self.assertIn("DELETE FROM `chrclasses_dbc` WHERE `ID` IN (1,2,3,7,8);", sql)
        self.assertEqual((MODULE / "data/sql/db-world/updates" / gcr.DISPLAY_POWER_MIGRATION)
                         .read_text(encoding="utf-8"), sql)
        # The client file also carries the class names (class_names, world_0027).
        self.assertEqual(gcr.CLIENT_CHRCLASSES.read_bytes(), gcr.class_names(client)[1])

    def test_the_client_file_differs_from_stock_in_two_fields(self):
        """DisplayPower of the Mage, the Paladin, the Hunter and the Shaman, the names of the Warrior, the Mage, the Paladin and the Hunter, and the
        Paladin's, the Hunter's and the Shaman's SpellClassSet (the Crusader's, the Demon Hunter's and the Shaman's records' families since
        their 2a, generate_class_creation.py): nothing else."""
        from dbc_store import Store, schema
        columns = schema(MODULE.parent, "chrclasses_dbc")
        stock = Store((gcr.SERVER_DBC / "ChrClasses.dbc").read_bytes(), columns)
        patched = Store(gcr.CLIENT_CHRCLASSES.read_bytes(), columns)
        # Classes 12, 13 and 14 are the Monk's, the Necromancer's and the Witch Doctor's, appended whole by generate_class_creation.py
        # (test_class_creation.py checks them).
        self.assertEqual(sorted(stock.rows) + [12, 13, 14], sorted(patched.rows))
        differing = {}
        for class_id in stock.rows:
            before, after = stock.decode(class_id), patched.decode(class_id)
            for field in before:
                if before[field] != after[field]:
                    differing.setdefault(class_id, {})[field] = (before[field], after[field])
        self.assertEqual(differing, {1: {"Name_Lang_enUS": ("Warrior", "Barbarian")},
                                     2: {"DisplayPower": (0, 3), "Name_Lang_enUS": ("Paladin", "Crusader"),
                                         "SpellClassSet": (10, 24)},
                                     3: {"DisplayPower": (0, 3), "Name_Lang_enUS": ("Hunter", "Demon Hunter"),
                                         "SpellClassSet": (9, 25)},
                                     7: {"DisplayPower": (0, 1), "SpellClassSet": (11, 27)},
                                     8: {"DisplayPower": (0, 3), "Name_Lang_enUS": ("Mage", "Wizard")}})

    def test_a_wrong_slot_is_caught(self):
        entries = [dict(e) for e in gcr.registry()]
        for e in entries:
            if e["key"] == "arcane_power":
                e["power_id"] = 0
        _, client, overlays = gcr.display_power(entries)
        self.assertEqual([o["ID"] for o in overlays], [2, 3, 7])
        self.assertNotEqual(client, gcr.CLIENT_CHRCLASSES.read_bytes())


class Sources(unittest.TestCase):
    CHANGED = ["src/classes/barbarian/dc_barbarian_call_of_the_ancients.cpp", "src/combat/dc_combat.cpp",
               "src/combat/dc_passives.cpp", "src/classes/barbarian/dc_barbarian_passives.cpp", "src/classes/barbarian/dc_barbarian_primaries.cpp", "src/combat/dc_spell_numbers.cpp",
               "src/combat/dc_spell_values.h", "src/stats/dc_stats.cpp", "src/classes/wizard/dc_wizard.cpp",
               "src/combat/dc_cost_math.h"]

    def test_no_class_resource_is_hard_wired(self):
        for path in [*self.CHANGED, *("src/classes/barbarian/" + p.name for p in barbarian_source.files((".cpp",)))]:
            text = (MODULE / path).read_text(encoding="utf-8")
            for word in ("POWER_RAGE", "POWER_MANA", "RagePerFury", "ManaPerArcanePower"):
                code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//"))
                if path.endswith("dc_cost_math.h") and word == "RagePerFury":
                    self.assertIn('Find("Barbarian", "fury")->scale', code)
                    continue
                self.assertNotIn(word, code, f"{path} still names {word}")


def login_failures(text):
    """What is wrong with the stats login's start rule in dc_stats.cpp `text` ([] when it is right): a resource that
    starts full is set to its maximum and one that does not to 0 (Wrath, which the core fills as Energy)."""
    wrong = []
    login = text[text.index("void Login(Player* player)"):]
    login = login[:login.index("catch (std::exception const& error)")]
    rule = ("for (Resources::Resource const* resource : {SheetOf(player).resource, SheetOf(player).second})\n"
            "                    if (resource)\n"
            "                        player->SetPower(Resources::Slot(*resource),\n"
            "                                         resource->startsFull ? player->GetMaxPower(Resources::Slot(*resource)) : 0);")
    if rule not in login:
        wrong.append("a resource that starts full is set to its maximum and one that does not to 0, the class's own "
                     "registry rows, its primary and its second")
    elif not 0 <= login.find("RestoreLife(player, share);") < login.index(rule) < login.find("Save(player);"):
        wrong.append("after the maximum is published and before the sheet is saved")
    if any(word in login for word in ("Monk", "Spirit", "Wizard", "Barbarian", "Fury", "ArcanePower")):
        wrong.append("no class is named: the registry says who starts full")
    return wrong


class Login(unittest.TestCase):
    STATS = MODULE / "src/stats/dc_stats.cpp"

    def test_login_fills_the_resources_that_start_full(self):
        self.assertEqual([], login_failures(self.STATS.read_text(encoding="utf-8")))

    def test_the_guard_fails_its_mutants(self):
        real = self.STATS.read_text(encoding="utf-8")
        mutants = {
            "every_class_fills": ("resource->startsFull ? player->GetMaxPower(Resources::Slot(*resource)) : 0);",
                                  "player->GetMaxPower(Resources::Slot(*resource)));"),
            "fills_to_zero": ("resource->startsFull ? player->GetMaxPower(Resources::Slot(*resource)) : 0);", "0);"),
            "an_empty_start_left_as_the_core_filled_it": (
                "resource->startsFull ? player->GetMaxPower(Resources::Slot(*resource)) : 0);",
                "resource->startsFull ? player->GetMaxPower(Resources::Slot(*resource)) : player->GetPower(Resources::Slot(*resource)));"),
            "fills_before_the_life_is_restored": ("                RestoreLife(player, share);\n", ""),
            "names_the_monk": ("                    if (resource)\n", "                    if (resource && resource->key[0] == 'S' /* Monk */)\n"),
            "the_second_left_out": (", SheetOf(player).second})", "})"),
            "never_saved_after": ("                Save(player);\n                LOG_INFO(\"server.loading\"", "                LOG_INFO(\"server.loading\""),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply once")
                self.assertTrue(login_failures(real.replace(old, new)), name + " survived")


if __name__ == "__main__":
    unittest.main(verbosity=2)
