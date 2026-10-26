"""diablocraft-7h5tr (pylons and shrines P3, docs/proposals/pylons.md 4.2, 6.4, 6.7, 6.8 and 7): the objects.

  * src/combat/dc_pylon_math.h compiled into tests/pylon_objects/harness.cpp and driven: one use, a pylon reaching the
    whole floor, a shrine only within the radius of its tunable row, a member on another floor getting nothing, the
    entries and the pylon-only predicate; single-rule mutants fail the same driver;
  * combat_0054_pylon_objects.sql against data/pylon_buffs.csv, data/d3/pylons.csv and the look rows (type 22, one
    charge, the kind's record, the entry the header names); docs/contracts/pylon-messages.md's table against the same;
  * source guards that dc_pylons.cpp calls each piece where the plan puts it (they prove the call is there, not that it
    runs; syntax_check.sh compiles the C++, and the in-game steps are in docs/test-diablocraft-7h5tr.md).
"""
import csv
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_pylon_math.h"
CPP = SRC / "combat/dc_pylons.cpp"
HARNESS = MODULE / "tests/pylon_objects/harness.cpp"
SHEET = MODULE / "data/pylon_buffs.csv"
TUNABLES = MODULE / "data/tunables/combat.csv"
D3 = MODULE / "data/d3/pylons.csv"
MIGRATION = MODULE / "data/sql/db-world/updates/combat_0054_pylon_objects.sql"
GENERATOR = MODULE / "scripts/generate/rifts/generate_pylon_objects.py"
CONTRACT = REPO / "docs/contracts/pylon-messages.md"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch/pylons"


def read(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def tunable(name):
    row = next(r for r in read(TUNABLES) if r["name"] == name)
    return float(row["value"] or row["d3_value"])


def first_entry():
    return int(re.search(r"ObjectEntryFirst = (\d+);", MATH.read_text(encoding="utf-8")).group(1))


def drive(lines, header_text=None, name="real"):
    """One answer line per input line; None when the harness fails to run (a mutant may make it throw)."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="pylon-objects-%s-" % name, dir=str(SCRATCH)))   # the cases file only; the binary is the cache's
    try:
        # The harness includes the module's headers by relative path, so they are staged with it; a mutant replaces only
        # dc_pylon_math.h, and the same text is the same staged tree and the same binary.
        files = {"src/" + path.relative_to(SRC).as_posix(): path.read_bytes() for path in SRC.rglob("*")
                 if path.is_file() and path.suffix != ".cpp"}
        files["src/combat/dc_pylon_math.h"] = header_text or MATH.read_text(encoding="utf-8")
        files["tests/pylon_objects/harness.cpp"] = HARNESS.read_bytes()
        tree = harness_env.stage_files(files)
        try:
            binary = harness_env.build([tree / "tests/pylon_objects/harness.cpp"], flags=["-std=c++17", "-O1"])
        except harness_env.BuildError as error:
            if header_text is None:
                raise AssertionError("harness did not compile:\n" + error.stderr[-3000:])
            return None
        (work / "cases.txt").write_text("\n".join(lines) + "\n")
        done = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return None if done.returncode else done.stdout.splitlines()


class TheClick(unittest.TestCase):
    """6.4 through the header's own Spend: whom a click reaches, and that it reaches them once."""

    @classmethod
    def setUpClass(cls):
        cls.radius = tunable("shrine_share_radius_yards")

    def spend(self, kind, members, spent=0, radius=None):
        line = "spend %s %r %d %s" % (kind, self.radius if radius is None else radius, spent, " ".join(members))
        return drive([line])[0]

    def test_one_use(self):
        # The same object clicked again (a second player in the same tick, before the core takes it away): nothing.
        self.assertEqual("none", self.spend("power", ["1:0:1"], spent=1))
        self.assertEqual("1 1 1", self.spend("power", ["1:0:1"]))

    def test_a_pylon_reaches_the_whole_floor_and_no_other(self):
        far = self.radius * 10
        self.assertEqual("3 1 1 1 1 0", self.spend("conduit", ["1:0:1", "1:%r:1" % far, "1:%r:1" % (self.radius + 1),
                                                               "0:0:1"]))

    def test_a_shrine_reaches_only_those_near_the_clicker_on_its_floor(self):
        r = self.radius
        self.assertEqual("2 1 1 1 0 0", self.spend("frenzied", ["1:0:1", "1:%r:1" % r, "1:%r:1" % (r + 0.5),
                                                                "0:1:1"]))

    def test_a_member_on_another_floor_gets_no_shrine_buff_even_beside_the_clicker(self):
        self.assertEqual("1 1 1 0", self.spend("blessed", ["1:0:1", "0:0:1"]))

    def test_the_radius_is_the_rows_and_only_a_given_buff_counts(self):
        # A wider radius reaches the member at 70 yards; a member whose Give fails (a dead one, for a shrine) counts not.
        self.assertEqual("1 1 1 0", self.spend("fortune", ["1:0:1", "1:70:1"], radius=50))
        self.assertEqual("2 1 1 1", self.spend("fortune", ["1:0:1", "1:70:1"], radius=80))
        self.assertEqual("1 1 1 0", self.spend("speed", ["1:0:1", "1:5:0"]))

    def test_entries_and_the_pylon_only_predicate(self):
        first = first_entry()
        lines = ["object %d" % e for e in range(first - 1, first + 12)]
        out = drive(lines)
        self.assertEqual(["-1 0"] + ["%d %d" % (i, 1 if i < 5 else 0) for i in range(11)] + ["-1 0"], out)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        r = self.radius
        lines = ["spend power %r 1 1:0:1" % r, "spend power %r 0 1:0:1 1:%r:1 0:0:1" % (r, r * 3),
                 "spend blessed %r 0 1:0:1 1:%r:1 1:%r:1 0:0:1" % (r, r, r + 1), "spend speed %r 0 1:0:1 1:1:0" % r]
        lines += ["object %d" % e for e in range(first_entry() - 1, first_entry() + 12)]
        want = drive(lines)
        mutants = {
            "spent_twice": ("        if (spent)\n            return std::nullopt;\n", ""),
            "never_marked": ("        spent = true;\n", ""),
            "shrine_reaches_the_floor": ("(IsPylon(kind) || yards <= radius)", "(true || yards <= radius)"),
            "pylon_needs_the_radius": ("(IsPylon(kind) || yards <= radius)", "(yards <= radius)"),
            "edge_excluded": ("yards <= radius", "yards < radius"),
            "other_floor_reached": ("return sameFloor && (", "return ("),
            "failed_give_counts": ("&& give(member))", "&& (give(member) || true))"),
            "entry_past_the_last": ("entry >= ObjectEntryFirst + KindCount", "entry > ObjectEntryFirst + KindCount"),
            "shrine_object_is_a_pylon": ("return kind && IsPylon(*kind);", "return kind.has_value();"),
        }
        for name, (old, new) in mutants.items():
            self.assertEqual(1, real.count(old), "the %s mutation no longer applies to the header" % name)
            self.assertNotEqual(want, drive(lines, real.replace(old, new), name), "mutant %s passed" % name)


class TheTemplates(unittest.TestCase):
    """combat_0054 against the sheets it is made from."""

    def rows(self):
        text = MIGRATION.read_text(encoding="utf-8")
        return re.findall(r"^  \((\d+), (\d+), (\d+), '([^']*)', '', '', '', 1, (\d+), (\d+), ((?:0, ){22})'', '', 12340\)",
                          text, re.M)

    def test_one_type_22_object_per_kind_in_the_sheets_order(self):
        sheet = read(SHEET)
        rows = self.rows()
        self.assertEqual(len(sheet), len(rows))
        d3 = {r["name"] for r in read(D3)}
        for i, (buff, row) in enumerate(zip(sheet, rows)):
            entry, go_type, display, name, data0, data1, _ = row
            self.assertEqual(first_entry() + i, int(entry), buff["kind"])
            self.assertEqual(("22", "1"), (go_type, data1), buff["kind"])
            self.assertEqual(buff["spell_id"], data0, buff["kind"])
            self.assertIn(name, d3, "%s: a D3 name" % buff["kind"])
            self.assertTrue(name.lower().startswith(buff["kind"]) and name.lower().endswith(buff["group"]), name)
            look = "pylon_%s_display_id" % buff["kind"] if buff["group"] == "pylon" else "shrine_display_id"
            self.assertEqual(tunable(look), float(display), buff["kind"])

    def test_the_generator_and_the_header_agree_on_the_first_entry(self):
        self.assertEqual(first_entry(), int(re.search(r"^OBJECT_ENTRY_FIRST = (\d+)", GENERATOR.read_text(), re.M).group(1)))

    def test_the_looks_are_placeholders_for_alex(self):
        for row in read(TUNABLES):
            if row["name"] == "globe_display_id":
                continue    # the health globe's look, picked (8365, diablocraft-ivtf5): not a pylon or shrine row
            if row["name"].endswith("_display_id") or row["name"] == "shrine_share_radius_yards" \
                    or row["name"].startswith("pylon_list_"):
                self.assertEqual("", row["d3_value"], row["name"])
                self.assertIn("PLACEHOLDER", row["notes"], row["name"])

    def test_the_contract_table_is_the_sheets(self):
        table = re.findall(r"^\| `(\w+)` \| `(\w+)` \| (pylon|shrine) \| (\d+) \| (\d+) \|$",
                           CONTRACT.read_text(encoding="utf-8"), re.M)
        want = [(b["kind"], b["group"], str(first_entry() + i), b["spell_id"]) for i, b in enumerate(read(SHEET))]
        self.assertEqual(want, [(name, group, entry, record) for _k, name, group, entry, record in table])


class TheModule(unittest.TestCase):
    """dc_pylons.cpp calls each piece where the plan puts it."""

    @classmethod
    def setUpClass(cls):
        cls.text = CPP.read_text(encoding="utf-8")

    def body(self, signature):
        start = self.text.index(signature)
        return self.text[start:self.text.index("\n            }\n", start)]

    def test_the_click_spends_with_the_radius_row_then_takes_the_object(self):
        click = self.body("bool CanGameObjectGossipHello(")
        self.assertIn("KindOfObject(object->GetEntry())", click)
        self.assertIn('Tune("shrine_share_radius_yards")', click)
        self.assertIn("m->IsInMap(player)", click)
        self.assertIn("Give(m, *kind)", click)
        self.assertLess(click.index("Spend("), click.index("Gone(map"))
        self.assertLess(click.index("Gone(map"), click.index("object->Delete()"))
        self.assertLess(click.index("if (!player->IsAlive())"), click.index("Spend("))

    def test_spawn_registers_and_tells_and_a_map_change_lists(self):
        spawn = self.text[self.text.index("GameObject* Spawn("):self.text.index("void RegisterScripts()")]
        self.assertIn("ObjectEntry(kind)", spawn)
        self.assertIn('GetDefault<Standing>("DCPylons")->objects.push_back', spawn)
        self.assertIn("Tell(player, object)", spawn)
        self.assertIn("PLAYERHOOK_ON_MAP_CHANGED", self.text)
        self.assertIn("List(player);", self.body("void OnPlayerMapChanged("))
        self.assertIn('{"spawn", SpawnHere, SEC_GAMEMASTER, Console::No}', self.text)
        self.assertIn('Routes().Add(Prefix, {"combat", "pylon_list_burst", "pylon_list_per_second"}', self.text)

    def test_the_gm_commands_say_so_on_success(self):
        """diablocraft-25ipa (ruling 2026-10-11): each command prints one line when it works, its failure line otherwise."""
        spawn = self.text[self.text.index("static bool SpawnHere("):self.text.index("static bool Buff(")]
        self.assertRegex(spawn, r'if \(!Spawn\(player->GetMap\(\), \*kind, player->GetPosition\(\)\)\)\s+handler->PSendSysMessage\("No \{\} object'
                                r'[^;]*;\s+else[^\n]*\n\s+handler->PSendSysMessage\("\{\} spawned at your feet\.", Title\(\*kind\)\);')
        buff = self.text[self.text.index("static bool Buff("):]
        self.assertRegex(buff, r'if \(!Give\(player, \*kind\)\)\s+handler->PSendSysMessage\("The \{\} buff was not given'
                               r'[^;]*;\s+else[^\n]*\n\s+handler->PSendSysMessage\("\{\} buff given \(\{\} s\)\.", Title\(\*kind\), '
                               r'Tune\(Row\(\*kind, "seconds"\)\)\);')


if __name__ == "__main__":
    unittest.main()
