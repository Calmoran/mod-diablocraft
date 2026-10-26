"""NPC outfits (diablocraft-0prr): the mirror-image answer for a dressed creature, the Wizard's
Mirror Image left as it is today, and the Rift Keeper's data.

What is run, and what is not:

  * `src/common/dc_world_outfits.h` is the production header and is compiled as it is. Its answer
    is fed the Keeper's row out of the GENERATED SQL, never a literal, and the bytes are decoded
    against the layout the core itself writes: the field types and the slot order are read out of
    `WorldSession::HandleMirrorImageDataRequest` in the pinned core (SpellHandler.cpp), so the
    answer is judged by the stock code's own text and not by a restatement of it.
  * The Wizard's Mirror Image (creature 900110) carries the stock clone aura. The only change on
    its path is `ChooseAnswer`, which must hand it to the core, with or without an outfit row, and
    there is no core patch: no file in core-patches/ touches SpellHandler.cpp.
  * Mutants of the header (a reversed slot loop, a swapped race and gender, the clone-aura check
    removed) are compiled and must turn the same checks red.
  * NOT run here: the client. The server answer is proved; that the 3.3.5 client dresses the NPC
    from it is the designer's screenshot. The .cpp (table loader, creature flag, packet hook) is only
    compile-checked (syntax_check.sh) and read for its few rules below.

    python mod-diablocraft/scripts/tests/world/test_npc_outfits.py
"""
import csv
import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import generate_npc_outfits as generator  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
ROOT = MODULE.parent
HEADER = MODULE / "src/common/dc_world_outfits.h"
SOURCE = MODULE / "src/common/dc_world_outfits.cpp"
HARNESS = MODULE / "tests/npc_outfits/harness.cpp"
SEED = MODULE / "data/generated/outfits_0003_npc_outfits.sql"
SEED_0002 = MODULE / "data/generated/outfits_0002_npc_outfits.sql"  # applied and frozen
SCHEMA = MODULE / "data/generated/outfits_0001_npc_outfit_schema.sql"
CSV = MODULE / "data/outfits/npc_outfits.csv"
CORE_HANDLER = ROOT / "azerothcore-wotlk/src/server/game/Handlers/SpellHandler.cpp"
WINGS = ROOT / "client-patch/wings-manifest.json"
SCRATCH = ROOT / "azerothcore-wotlk/build/_agent-scratch/npc_outfits"

KEEPER, MIRROR_IMAGE, AVATAR_RAIMENT, WHITE_WINGS = 910003, 900110, 665, 84006
KADALA = 910005  # diablocraft-ebbg
# The core's EQUIPMENT_SLOT_* name for each of our slot columns.
CORE_SLOT = dict(head="HEAD", shoulders="SHOULDERS", shirt="BODY", chest="CHEST", waist="WAIST", legs="LEGS",
                 feet="FEET", wrists="WRISTS", hands="HANDS", back="BACK", tabard="TABARD")
# item_template.InventoryType that belongs in each slot column.
INVENTORY_TYPES = dict(head={1}, shoulders={3}, shirt={4}, chest={5, 20}, waist={6}, legs={7}, feet={8},
                       wrists={9}, hands={10}, back={16}, tabard={19})
WIDTH = {"u8": 1, "u32": 4, "u64": 8}
GUID, DISPLAY, UNIT_CLASS = 4242, 50, 5


def core_layout():
    """([field types after SMSG_MIRRORIMAGE_DATA is opened], [slot names]) from the core's own code."""
    text = CORE_HANDLER.read_text(encoding="utf-8")
    start = text.index("void WorldSession::HandleMirrorImageDataRequest")
    body = text[start:text.index("\n}\n", start)]
    player = body[body.index("if (creator->IsPlayer())"):body.index("static EquipmentSlots")]
    head = body[body.index("WorldPacket data(SMSG_MIRRORIMAGE_DATA"):body.index("if (creator->IsPlayer())")]
    types = []
    for source in (head, player):
        for kind in re.findall(r"data << (guid|uint8|uint32)\b", source):
            types.append({"guid": "u64", "uint8": "u8", "uint32": "u32"}[kind])
    slots = re.findall(r"EQUIPMENT_SLOT_(\w+),", body[body.index("static EquipmentSlots"):body.index("// Display items")])
    slots = [name for name in slots if name != "END"]
    types += ["u32"] * len(slots)
    return types, slots


def keeper_row():
    """The Keeper's dc_npc_outfit row as it is in the generated SQL: {column: int}."""
    text = SEED.read_text(encoding="utf-8")
    columns = re.search(r"INSERT INTO dc_npc_outfit \(([^)]*)\)", text)[1].split(",")[:-1]
    match = re.search(r"^\((%d(?:,\d+){%d}),'" % (KEEPER, len(columns) - 1), text, re.M)
    assert match, "the Keeper has no row in " + SEED.name
    return dict(zip(columns, map(int, match[1].split(","))))


def manifest_names():
    """{spell id: name} for every entry of client-patch/wings-manifest.json that has both."""
    found = {}

    def walk(node):
        if isinstance(node, dict):
            if "spell_id" in node and "name" in node:
                found[str(node["spell_id"])] = node["name"]
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(json.loads(WINGS.read_text(encoding="utf-8")))
    return found


def build(workdir, header_text):
    compiler = shutil.which("c++") or shutil.which("g++")
    if not compiler:
        raise unittest.SkipTest("no C++ compiler")
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "dc_world_outfits.h").write_text(header_text, encoding="utf-8")
    binary = workdir / "harness"
    built = subprocess.run([compiler, "-std=c++17", "-O0", "-UNDEBUG", "-I", str(workdir), str(HARNESS), "-o", str(binary)],
                           capture_output=True, text=True)
    if built.returncode:
        raise AssertionError("the harness did not compile:\n" + built.stderr[-6000:])
    return binary


def run(binary, *args):
    ran = harness_env.run([str(binary), *map(str, args)], capture_output=True, text=True)
    assert ran.returncode == 0, ran.stderr
    return ran.stdout.strip()


def synthetic_display(entry):
    return 100000 + entry


def decode(hex_bytes, types):
    raw, at, out = bytes.fromhex(hex_bytes), 0, []
    for kind in types:
        out.append(int.from_bytes(raw[at:at + WIDTH[kind]], "little"))
        at += WIDTH[kind]
    return out, len(raw) - at


def answer_for(binary, row):
    slots = [row[name] for name in generator.SLOTS]
    return run(binary, "answer", GUID, DISPLAY, UNIT_CLASS, *(row[key] for key in generator.LOOKS),
               *(synthetic_display(item) if item else 0 for item in slots))


# Every field different from every other, so a swap of two of them cannot give the same bytes (the
# Keeper's race and gender are both 1).
PROBE = dict(entry=1, race=4, gender=0, skin=1, face=2, hair=3, hair_color=5, facial_hair=6,
             **{name: 1000 + at for at, name in enumerate(generator.SLOTS)})


def check_answer(binary, row):
    """Every way the Keeper's answer can disagree with the core's layout; empty when it agrees."""
    return check_one(binary, row) + check_one(binary, PROBE)


def check_one(binary, row):
    types, slots = core_layout()
    values, left = decode(answer_for(binary, row), types)
    problems = []
    expected = [GUID, DISPLAY, row["race"], row["gender"], UNIT_CLASS, row["skin"], row["face"], row["hair"],
                row["hair_color"], row["facial_hair"], 0]
    expected += [synthetic_display(row[name]) if row[name] else 0 for name in generator.SLOTS]
    if left:
        problems.append("%d bytes beyond the core's layout" % left)
    if slots != [CORE_SLOT[name] for name in generator.SLOTS]:
        problems.append("the core's slot order %s is not our columns' %s" % (slots, list(generator.SLOTS)))
    if values != expected:
        problems.append("decoded %s, expected %s" % (values, expected))
    return problems


def check_choice(binary):
    """The Wizard's Mirror Image (clone aura, no row) and a row holder, through ChooseAnswer."""
    cases = {(1, 0): "Stock", (1, 1): "Stock", (0, 0): "Stock", (0, 1): "Outfit"}
    return ["clone=%d row=%d answered %s" % (*case, got) for case, want in cases.items()
            if (got := run(binary, "choose", *case)) != want]


class Answer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = build(SCRATCH / "real", HEADER.read_text(encoding="utf-8"))

    def test_the_answer_has_the_cores_layout_and_carries_the_keepers_look(self):
        self.assertEqual(check_answer(self.binary, keeper_row()), [])

    def test_the_answer_is_as_long_as_the_core_reserves_for_it(self):
        types, _ = core_layout()
        self.assertEqual(8 + sum(WIDTH[kind] for kind in types[1:]), 68)   # WorldPacket data(SMSG_MIRRORIMAGE_DATA, 68)

    def test_only_a_unit_without_the_clone_aura_and_with_a_row_is_answered_here(self):
        self.assertEqual(check_choice(self.binary), [])

    def test_the_wizards_mirror_image_is_still_answered_by_the_core(self):
        # No row for 900110 in the data, ChooseAnswer gives a clone-aura unit to the core even if
        # one were added, and no patch changes the core's handler.
        self.assertNotIn(MIRROR_IMAGE, [int(r["entry"]) for r in generator.read()])
        self.assertNotIn(str(MIRROR_IMAGE), SEED.read_text(encoding="utf-8"))
        self.assertEqual(run(self.binary, "choose", 1, 1), "Stock")
        patches = [p.name for p in (ROOT / "core-patches").glob("*.patch")
                   if "Handlers/SpellHandler.cpp" in p.read_text(encoding="utf-8", errors="replace")]
        self.assertEqual(patches, [])
        self.assertIn("HasCloneCasterAura", SOURCE.read_text(encoding="utf-8"))


class Mutants(unittest.TestCase):
    """The same checks, on a header with one rule broken, must fail."""

    def mutant(self, name, pattern, replacement):
        """The header with one regex hit rewritten, whatever the formatter did to its whitespace."""
        mutated, hits = re.subn(pattern, replacement, HEADER.read_text(encoding="utf-8"))
        self.assertEqual(hits, 1, "the mutation target %r is not unique" % pattern)
        return build(SCRATCH / name, mutated)

    def test_a_reversed_slot_loop_is_caught(self):
        binary = self.mutant("reversed", r"slotDisplays\[slot\]", "slotDisplays[SLOT_COUNT - 1 - slot]")
        self.assertTrue(check_answer(binary, keeper_row()))

    def test_a_swapped_race_and_gender_is_caught(self):
        binary = self.mutant("swapped", r"(data << std::uint8_t\(outfit\.race\);)(\s*)(data << std::uint8_t\(outfit\.gender\);)",
                             r"\3\2\1")
        self.assertTrue(check_answer(binary, keeper_row()))

    def test_dropping_the_clone_aura_check_is_caught(self):
        binary = self.mutant("noclone", r"\(!hasCloneCasterAura && hasOutfit\)", "hasOutfit")
        self.assertTrue(check_choice(binary))


class KeeperData(unittest.TestCase):
    def test_the_keeper_is_a_female_human_in_the_avatar_raiment_with_the_white_wings(self):
        row = keeper_row()
        self.assertEqual((row["race"], row["gender"]), (1, 1))   # human, female
        self.assertEqual(sorted(row[name] for name in generator.SLOTS if row[name]),
                         [30150, 30151, 30152, 30153, 30154])      # Wowhead item-set=665
        self.assertEqual(row["head"], 30152)                      # Cowl of the Avatar
        self.assertEqual(row["shoulders"], 30154)                 # Mantle
        self.assertEqual(row["chest"], 30150)                     # Vestments
        self.assertEqual(row["hands"], 30151)                     # Gloves
        self.assertEqual(row["legs"], 30153)                      # Breeches
        self.assertIn("(%d,'%d')" % (KEEPER, WHITE_WINGS), SEED.read_text(encoding="utf-8"))
        self.assertEqual(manifest_names().get(str(WHITE_WINGS)), "Angelic Wings - White")

    def test_the_migrations_leave_the_keepers_name_gossip_flags_script_and_position_alone(self):
        sql = SCHEMA.read_text(encoding="utf-8") + SEED.read_text(encoding="utf-8")
        touched = set(re.findall(r"(?:INSERT INTO|^UPDATE|DELETE FROM|ALTER TABLE|CREATE TABLE IF NOT EXISTS)\s+`?(\w+)", sql, re.M))
        self.assertEqual(touched, {"dc_npc_outfit", "creature_template_addon"})

    def test_the_csv_and_the_generated_sql_agree(self):
        schema, seed = generator.render()
        self.assertEqual(schema, SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(seed, SEED.read_text(encoding="utf-8"))

    def test_the_cpp_registers_the_three_scripts_and_dc_world_calls_it(self):
        text = SOURCE.read_text(encoding="utf-8")
        for needle in ("CMSG_GET_MIRRORIMAGE_DATA", "UNIT_FLAG2_MIRROR_IMAGE", "SERVERHOOK_CAN_PACKET_RECEIVE",
                       "ChooseAnswer(", "WriteAnswer(", "FROM dc_npc_outfit"):
            self.assertIn(needle, text)
        self.assertIn("Outfits::RegisterScripts();", (MODULE / "src/common/dc_world.cpp").read_text(encoding="utf-8"))


class WorldDatabase(unittest.TestCase):
    """The set and the migrations against the fixture mysqld's copy of the world (never the live one)."""

    @classmethod
    def setUpClass(cls):
        import fixture_db
        try:
            cls.mysql, cls.defaults = fixture_db.mysql_and_defaults([])
        except SystemExit as stop:
            raise unittest.SkipTest(str(stop))

    def query(self, sql, database="acore_world"):
        ran = subprocess.run([self.mysql, "--defaults-file=" + self.defaults, "--no-login-paths", "-N", database, "-e", sql],
                             capture_output=True, text=True)
        self.assertEqual(ran.returncode, 0, ran.stderr)
        return [line.split("\t") for line in ran.stdout.splitlines()]

    def test_the_keepers_items_are_exactly_item_set_665_in_their_own_slots(self):
        members = {int(entry): int(kind) for entry, kind in
                   self.query("SELECT entry, InventoryType FROM item_template WHERE itemset = %d" % AVATAR_RAIMENT)}
        self.assertEqual(len(members), 5, members)
        row = keeper_row()
        worn = {row[name]: name for name in generator.SLOTS if row[name]}
        self.assertEqual(set(worn), set(members))
        for entry, slot in worn.items():
            self.assertIn(members[entry], INVENTORY_TYPES[slot], "item %d is in the %s column" % (entry, slot))

    def test_the_migrations_apply_twice_and_leave_the_row_and_the_wings_aura(self):
        scratch = "dc_outfit_test_0prr"
        self.query("DROP DATABASE IF EXISTS %s" % scratch, "mysql")
        self.query("CREATE DATABASE %s" % scratch, "mysql")
        try:
            self.query("CREATE TABLE creature_template_addon LIKE acore_world.creature_template_addon", scratch)
            for _ in range(2):
                for path in (SCHEMA, SEED_0002, SEED):
                    ran = subprocess.run([self.mysql, "--defaults-file=" + self.defaults, "--no-login-paths", scratch],
                                         input=path.read_text(encoding="utf-8"), capture_output=True, text=True)
                    self.assertEqual(ran.returncode, 0, ran.stderr)
            self.assertEqual(self.query("SELECT entry, race, gender, head, hands FROM dc_npc_outfit", scratch),
                             [[str(KEEPER), "1", "1", "30152", "30151"], [str(KADALA), "1", "1", "3732", "0"]])
            self.assertEqual(self.query("SELECT entry, head, chest FROM dc_npc_outfit WHERE entry=%d" % KADALA, scratch),
                             [[str(KADALA), "3732", "7711"]])
            self.assertEqual(self.query("SELECT entry, auras FROM creature_template_addon", scratch),
                             [[str(KEEPER), str(WHITE_WINGS)]])
        finally:
            self.query("DROP DATABASE IF EXISTS %s" % scratch, "mysql")


class GeneratorRules(unittest.TestCase):
    def good(self):
        with CSV.open(encoding="utf-8-sig", newline="") as stream:
            return [dict(next(csv.DictReader(stream)))]

    def test_the_sheet_validates(self):
        generator.validate(self.good())

    def test_bad_sheets_are_refused(self):
        for key, value in (("race", "0"), ("race", "12"), ("gender", "2"), ("face", "256"), ("head", "-1"),
                           ("entry", "x"), ("addon_auras", "84006 nine")):
            rows = self.good()
            rows[0][key] = value
            with self.assertRaises(ValueError, msg="%s=%s" % (key, value)):
                generator.validate(rows)
        with self.assertRaises(ValueError):
            generator.validate(self.good() * 2)


if __name__ == "__main__":
    unittest.main()
