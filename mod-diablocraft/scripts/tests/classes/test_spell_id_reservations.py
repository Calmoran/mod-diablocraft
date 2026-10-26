#!/usr/bin/env python3
"""Per-bead spell id reservations (diablocraft-syh98): two branches cannot take the same id, and a merged id never moves.

The failure this closes: two branches in review each took "the next free id" from their own base and gave 85921 and 83563 to different
records. Here two fixture branches, cut from one nightly after the PM reserved for both beads, each add a record through the real
generate_spells.choose_helper_id and get different ids; a fold of the two stays sound; an id a branch takes from another bead's range, an id
in no reservation, a changed merged id and an edited sheet are all refused. Every scenario is also run against broken copies of
spell_id_reservations.py and must fail on each (a check that cannot fail checks nothing).

The fixture is a throw-away git repo laid out like the real one (mod-diablocraft/data/...), with small pools. Nothing touches the real tree
except RealTree, which runs `check` on the checkout (a note, not a failure, when there is no nightly to compare with).

Run: python3 mod-diablocraft/scripts/tests/classes/test_spell_id_reservations.py
"""
import contextlib
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_spells as gen  # noqa: E402
import spell_id_reservations as real  # noqa: E402

LIB = Path(real.__file__)
HELPERS = "mod-diablocraft/data/generated/spell_helper_ids.csv"
CATEGORIES = "mod-diablocraft/data/generated/spell_cooldown_categories.csv"
BUFFS = "mod-diablocraft/data/legendary_power_buffs.csv"
SHEET = real.SHEET_REL


def load_module(source, name="spell_id_reservations_under_test"):
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader=None))
    module.__file__ = str(LIB)
    sys.modules[name] = module  # dataclasses look the module up by name
    exec(compile(source, str(LIB), "exec"), module.__dict__)
    return module


def pools_of(mod):
    return {
        "helper:demon_hunter": mod.Pool("helper:demon_hunter", 100, 199, HELPERS, "spell_id", "demon_hunter"),
        "category:demon_hunter": mod.Pool("category:demon_hunter", 10, 29, CATEGORIES, "category", "demon_hunter"),
        "power_buff": mod.Pool("power_buff", 500, 549, BUFFS, "spell_id"),
    }


def git(repo, *args, check=True):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, env=env)
    if check and out.returncode != 0:
        raise AssertionError(f"git {' '.join(args)}: {out.stderr}")
    return out.stdout


def write(repo, rel, text):
    path = Path(repo) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def commit(repo, message):
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)


class Fixture:
    """nightly with two merged helper rows (100, 101), one category (10), one power buff (500) and an empty sheet."""

    def __init__(self, mod):
        self.mod, self.pools = mod, pools_of(mod)
        self.dir = tempfile.TemporaryDirectory()
        self.repo = Path(self.dir.name)
        git(self.repo, "init", "-q", "-b", "nightly")
        write(self.repo, ".gitattributes", "*.csv merge=union\n")
        write(self.repo, HELPERS, "identity,spell_id,class\nOld A - token storage,100,demon_hunter\nOld B - token storage,101,demon_hunter\n")
        write(self.repo, CATEGORIES, "skill,category,class\nOld skill,10,demon_hunter\n")
        write(self.repo, BUFFS, "spell_id,owner,stat\n500,Old_Item,armor_pct\n")
        write(self.repo, SHEET, "bead,pool,first,last,note\n")
        commit(self.repo, "nightly")

    def close(self):
        self.dir.cleanup()

    def pm_reserves(self, bead, *takes):
        argv = ["reserve", "--bead", bead]
        for take in takes:
            argv += ["--take", take]
        git(self.repo, "switch", "-q", "nightly")
        with contextlib.redirect_stdout(io.StringIO()):
            self.mod.main(argv, pools=self.pools, root=self.repo)
        commit(self.repo, f"reserve for {bead}")

    def branch(self, bead, start="nightly"):
        git(self.repo, "switch", "-q", "-c", f"w/{bead}", start)

    def add_helper(self, identity):
        """What the generator does on this branch for a new identity: the lowest free id of the bead's reservation."""
        held = self.mod.Held(self.pools, root=self.repo, environ={})
        rows = (self.repo / HELPERS).read_text().splitlines()[1:]
        ids = {line.split(",")[0]: int(line.split(",")[1]) for line in rows}
        wanted = gen.choose_helper_id(identity, ids, {}, "demon_hunter", lambda pool: (held.allowed(pool), held.shortfall(pool)))
        with (self.repo / HELPERS).open("a", newline="\n") as f:
            f.write(f"{identity},{wanted},demon_hunter\n")
        commit(self.repo, f"helper {identity}")
        return wanted

    def append(self, rel, line):
        with (self.repo / rel).open("a", newline="\n") as f:
            f.write(line + "\n")
        commit(self.repo, f"edit {rel}")

    def check(self, **kw):
        return self.mod.check_tree(self.repo, self.pools, environ={}, **kw)


# ---------------------------------------------------------------- scenarios: each takes the module under test and raises on a wrong answer


def scenario_two_branches_get_different_ids(mod):
    fx = Fixture(mod)
    try:
        fx.pm_reserves("diablocraft-aaa1", "helper:demon_hunter=2", "power_buff=1")
        fx.pm_reserves("diablocraft-bbb2", "helper:demon_hunter=2", "power_buff=1")
        fx.branch("diablocraft-aaa1")
        a = fx.add_helper("A - token storage")
        git(fx.repo, "switch", "-q", "nightly")
        fx.branch("diablocraft-bbb2")
        b = fx.add_helper("B - token storage")
        assert a != b, f"both branches took {a}"
        assert {a, b} == {102, 104}, (a, b)
        for bead in ("aaa1", "bbb2"):
            git(fx.repo, "switch", "-q", f"w/diablocraft-{bead}")
            problems, _ = fx.check()
            assert problems == [], problems
        # the fold of the two: sound, and the helper map holds three distinct ids more
        git(fx.repo, "switch", "-q", "nightly")
        fx.branch("diablocraft-fold1")
        git(fx.repo, "merge", "-q", "--no-edit", "w/diablocraft-aaa1")
        git(fx.repo, "merge", "-q", "--no-edit", "w/diablocraft-bbb2")
        problems, _ = fx.check()
        assert problems == [], problems
        ids = [line.split(",")[1] for line in (fx.repo / HELPERS).read_text().splitlines()[1:]]
        assert len(ids) == len(set(ids)) == 4, ids
    finally:
        fx.close()


def scenario_a_merged_id_never_moves(mod):
    fx = Fixture(mod)
    try:
        fx.pm_reserves("diablocraft-aaa1", "helper:demon_hunter=2")
        fx.branch("diablocraft-aaa1")
        text = (fx.repo / HELPERS).read_text().replace("Old A - token storage,100,", "Old A - token storage,102,")
        write(fx.repo, HELPERS, text)
        commit(fx.repo, "renumber a merged record")
        problems, _ = fx.check()
        assert any("id 100" in p and "gone or moved" in p for p in problems), problems
        problems, _ = fx.check(allow_removed=[100])
        assert not any("gone or moved" in p for p in problems), problems
        # a reservation never offers an id in use, and release gives back what was not used
        git(fx.repo, "switch", "-q", "nightly")
        rows = mod.parse_sheet((fx.repo / SHEET).read_text(), fx.pools)
        used = mod.used_now(fx.repo, fx.pools)
        row = mod.reserve(rows, fx.pools, used, "diablocraft-zzz9", "helper:demon_hunter", "3")
        assert not set(row.ids()) & used["helper:demon_hunter"], row
        assert row.first == 104, row  # 102-103 are aaa1's
    finally:
        fx.close()


def scenario_another_beads_id_is_refused(mod):
    fx = Fixture(mod)
    try:
        fx.pm_reserves("diablocraft-aaa1", "power_buff=2", "helper:demon_hunter=1")
        fx.pm_reserves("diablocraft-bbb2", "power_buff=2")
        fx.branch("diablocraft-bbb2")
        fx.append(BUFFS, "501,Taken_From_Aaa,armor_pct")  # 501-502 are aaa1's
        problems, _ = fx.check()
        assert any("501" in p and "reserved for diablocraft-aaa1" in p for p in problems), problems
        git(fx.repo, "switch", "-q", "-C", "w/diablocraft-bbb2", "nightly")
        fx.append(BUFFS, "540,Nobody_Reserved,armor_pct")
        problems, _ = fx.check()
        assert any("540" in p and "in no reservation" in p for p in problems), problems
        git(fx.repo, "switch", "-q", "-C", "w/diablocraft-bbb2", "nightly")
        fx.append(BUFFS, "503,Own_Id,armor_pct")  # bbb2's own range is 503-504
        problems, _ = fx.check()
        assert problems == [], problems
    finally:
        fx.close()


def scenario_the_generator_needs_a_reservation(mod):
    fx = Fixture(mod)
    try:
        fx.pm_reserves("diablocraft-aaa1", "helper:demon_hunter=1")
        fx.branch("diablocraft-ccc3")  # a bead nobody reserved for
        try:
            fx.add_helper("C - token storage")
        except SystemExit as e:
            assert "reserve" in str(e.code) and "diablocraft-ccc3" in str(e.code), e.code
        else:
            raise AssertionError("an unreserved bead got an id")
        git(fx.repo, "switch", "-q", "--detach", "nightly")  # not on a bead branch either
        try:
            fx.add_helper("D - token storage")
        except SystemExit as e:
            assert "no bead" in str(e.code), e.code
        else:
            raise AssertionError("a detached HEAD got an id")
        git(fx.repo, "switch", "-q", "nightly")
        fx.branch("diablocraft-aaa1")
        fx.add_helper("A - token storage")
        try:
            fx.add_helper("A2 - token storage")  # the one id it reserved is used up
        except SystemExit as e:
            assert "reserve" in str(e.code), e.code
        else:
            raise AssertionError("an exhausted reservation gave another id")
    finally:
        fx.close()


def scenario_the_sheet_is_written_on_nightly_only(mod):
    fx = Fixture(mod)
    try:
        fx.branch("diablocraft-aaa1")
        write(fx.repo, SHEET, "bead,pool,first,last,note\ndiablocraft-aaa1,power_buff,500,501,self-served\n")
        commit(fx.repo, "a worker reserves for itself")
        problems, _ = fx.check()
        assert any("never edits the sheet" in p for p in problems), problems
        git(fx.repo, "switch", "-q", "nightly")
        fx.pm_reserves("diablocraft-aaa1", "power_buff=1")
        problems, _ = fx.check()
        assert problems == [], problems
    finally:
        fx.close()


def scenario_the_sheet_refuses_what_overlaps(mod):
    pools = pools_of(mod)
    head = "bead,pool,first,last,note\n"
    good = head + "diablocraft-aaa1,power_buff,500,502,\ndiablocraft-bbb2,power_buff,503,504,\n"
    assert len(mod.parse_sheet(good, pools)) == 2
    for name, bad in {
        "overlap": head + "diablocraft-aaa1,power_buff,500,502,\ndiablocraft-bbb2,power_buff,502,504,\n",
        "outside the block": head + "diablocraft-aaa1,power_buff,490,502,\n",
        "unknown pool": head + "diablocraft-aaa1,nothing,1,2,\n",
        "not a bead": head + "aaa1,power_buff,500,502,\n",
        "header": "bead,pool\n",
        "backwards": head + "diablocraft-aaa1,power_buff,502,500,\n",
    }.items():
        try:
            mod.parse_sheet(bad, pools)
        except SystemExit:
            continue
        raise AssertionError(f"the sheet accepted: {name}")


def scenario_reserve_and_release(mod):
    fx = Fixture(mod)
    try:
        fx.pm_reserves("diablocraft-aaa1", "helper:demon_hunter=5")  # 102-106
        fx.pm_reserves("diablocraft-bbb2", "helper:demon_hunter=3")  # 107-109
        rows = mod.parse_sheet((fx.repo / SHEET).read_text(), fx.pools)
        assert [(r.bead, r.first, r.last) for r in rows] == [("diablocraft-aaa1", 102, 106), ("diablocraft-bbb2", 107, 109)], rows
        used = mod.used_now(fx.repo, fx.pools)
        for bad in ("100-101", "105-110", "190-200", "0"):  # a merged id, another bead's, past the block, no count
            try:
                mod.reserve(rows, fx.pools, used, "diablocraft-ccc3", "helper:demon_hunter", bad)
            except SystemExit:
                continue
            raise AssertionError(f"reserved {bad}")
        grand = mod.reserve(rows, fx.pools, used, "diablocraft-ccc3", "helper:demon_hunter", "110-111", "an id already chosen")
        assert (grand.first, grand.last) == (110, 111)
        # aaa1 merged having used 102 and 103 only: release shrinks it, and the freed ids are the first fit again
        git(fx.repo, "switch", "-q", "nightly")
        fx.append(HELPERS, "A1,102,demon_hunter")
        fx.append(HELPERS, "A2,103,demon_hunter")
        used = mod.used_now(fx.repo, fx.pools)
        shrunk = mod.release(rows, used, "diablocraft-aaa1")
        assert [(r.first, r.last) for r in shrunk if r.bead == "diablocraft-aaa1"] == [(102, 103)], shrunk
        assert [r for r in shrunk if r.bead == "diablocraft-bbb2"] == [r for r in rows if r.bead == "diablocraft-bbb2"]
        again = mod.reserve(shrunk, fx.pools, used, "diablocraft-ddd4", "helper:demon_hunter", "3")
        assert (again.first, again.last) == (104, 106), again
        assert mod.release(rows, used, "diablocraft-bbb2") == [r for r in rows if r.bead != "diablocraft-bbb2"]  # none used: the row goes
    finally:
        fx.close()


SCENARIOS = [
    scenario_two_branches_get_different_ids,
    scenario_a_merged_id_never_moves,
    scenario_another_beads_id_is_refused,
    scenario_the_generator_needs_a_reservation,
    scenario_the_sheet_is_written_on_nightly_only,
    scenario_the_sheet_refuses_what_overlaps,
    scenario_reserve_and_release,
]


class Reservations(unittest.TestCase):
    def test_scenarios(self):
        for scenario in SCENARIOS:
            with self.subTest(scenario.__name__):
                scenario(real)

    def test_the_command_line(self):
        fx = Fixture(real)
        try:
            run = lambda *a: subprocess.run([sys.executable, str(LIB), *a, "--root", str(fx.repo)], capture_output=True, text=True, timeout=120)
            # the CLI reads the real pools from the generator; reserve in a real pool of the fixture tree
            out = run("reserve", "--bead", "diablocraft-aaa1", "--take", "power_buff=2", "--dry-run")
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("diablocraft-aaa1: power_buff 83550-83551", out.stdout)  # the fixture tree has no power buffs: the block's first ids
            self.assertEqual((fx.repo / SHEET).read_text(), "bead,pool,first,last,note\n")  # dry run wrote nothing
            out = run("reserve", "--bead", "diablocraft-aaa1", "--take", "power_buff=2")
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("diablocraft-aaa1,power_buff,83550,83551", (fx.repo / SHEET).read_text())
            self.assertIn("diablocraft-aaa1: 83550-83551", run("show").stdout)
            out = run("reserve", "--bead", "diablocraft-bbb2", "--take", "power_buff=83551-83552")
            self.assertEqual(out.returncode, 1)
            self.assertIn("already in use or reserved", out.stderr)
            self.assertEqual(run("release", "--bead", "diablocraft-aaa1").returncode, 0)
            self.assertNotIn("diablocraft-aaa1", (fx.repo / SHEET).read_text())  # none used: the row goes
            self.assertEqual(run("reserve", "--bead", "oops", "--take", "power_buff=1").returncode, 1)
            self.assertEqual(run("reserve", "--bead", "diablocraft-aaa1").returncode, 1)
        finally:
            fx.close()

    def test_the_current_bead(self):
        fx = Fixture(real)
        try:
            fx.branch("diablocraft-aaa1.2")
            self.assertEqual(real.current_beads(fx.repo, {}), ["diablocraft-aaa1.2"])
            self.assertEqual(real.current_beads(fx.repo, {"TORMENT_BEAD": "diablocraft-x1, diablocraft-y2"}), ["diablocraft-x1", "diablocraft-y2"])
            git(fx.repo, "switch", "-q", "nightly")
            self.assertEqual(real.current_beads(fx.repo, {}), [])
            git(fx.repo, "switch", "-q", "-c", "scratch")
            self.assertEqual(real.current_beads(fx.repo, {}), [])
        finally:
            fx.close()

    def test_without_a_nightly_it_says_what_it_did_not_check(self):
        with tempfile.TemporaryDirectory() as d:
            git(d, "init", "-q", "-b", "elsewhere")
            write(d, SHEET, "bead,pool,first,last,note\n")
            commit(d, "x")
            problems, notes = real.check_tree(Path(d), pools_of(real), environ={})
            self.assertEqual(problems, [])
            self.assertTrue(notes and "not checked" in notes[0], notes)


class BrokenCopies(unittest.TestCase):
    """Each scenario must fail on at least one broken copy that breaks the rule it pins."""

    MUTANTS = {
        "every bead may use every reserved id": ("return sorted(i for row in rows if row.pool == pool and row.bead in beads for i in row.ids())",
                                                 "return sorted(i for row in rows if row.pool == pool for i in row.ids())"),
        "a new id in no reservation passes": ("            if holder in beads:\n                continue\n", "            if True:\n                continue\n"),
        "another bead's id passes": ("            if holder in beads:\n", "            if holder is not None:\n"),
        "a moved merged id passes": ("for identifier in sorted(before - head - set(map(int, allow_removed))):", "for identifier in []:"),
        "overlapping reservations pass": ("            if other.pool == pool and row.first <= other.last and other.first <= row.last:", "            if False:"),
        "a range outside the block passes": ("        if not block.first <= row.first <= row.last <= block.last:", "        if False:"),
        "reserve ignores the other reservations": ("    taken = set(used[pool_name]) | {i for row in rows if row.pool == pool_name for i in row.ids()}", "    taken = set(used[pool_name])"),
        "reserve ignores ids in use": ("    taken = set(used[pool_name]) | {i for row in rows if row.pool == pool_name for i in row.ids()}", "    taken = {i for row in rows if row.pool == pool_name for i in row.ids()}"),
        "a branch may edit the sheet": ("    if branch not in SHEET_WRITERS and rows !=", "    if False and rows !="),
        "release keeps the unused tail": ("out.append(Row(row.bead, row.pool, row.first, max(mine), row.note))", "out.append(row)"),
        "the generator takes no reservation": ("def allowed(self, pool: str) -> list[int]:\n        return allowed_ids(self.rows, pool, self.beads)",
                                               "def allowed(self, pool: str) -> list[int]:\n        return list(range(self.pools[pool].first, self.pools[pool].last + 1))"),
    }

    def test_every_broken_copy_fails_a_scenario(self):
        source = LIB.read_text(encoding="utf-8")
        for name, (old, new) in self.MUTANTS.items():
            with self.subTest(name):
                self.assertEqual(source.count(old), 1, f"{name}: the text to break is not there once")
                broken = load_module(source.replace(old, new), "spell_id_reservations_broken")
                failed = []
                for scenario in SCENARIOS:
                    try:
                        scenario(broken)
                    except (AssertionError, SystemExit, ValueError, KeyError, TypeError):
                        failed.append(scenario.__name__)
                self.assertTrue(failed, f"no scenario noticed: {name}")


class RealTree(unittest.TestCase):
    def test_this_checkout_is_sound(self):
        problems, notes = real.check_tree(real.REPO, real.default_pools())
        self.assertEqual(problems, [], "\n".join(problems))

    def test_the_real_pools_do_not_overlap_each_other(self):
        pools = real.default_pools()
        ids = {}
        for pool in pools.values():
            if pool.name.startswith("category:"):
                continue  # categories are a separate id space
            for other in ids:
                self.assertTrue(pool.last < pools[other].first or pools[other].last < pool.first, f"{pool.name} overlaps {other}")
            ids[pool.name] = pool
        used = real.used_now(real.REPO, pools)
        for name, pool in pools.items():
            self.assertTrue(all(pool.first <= i <= pool.last for i in used[name]), f"{name} has an id outside its block")

    def test_the_generator_still_assigns_the_lowest_free_id_without_a_reservation(self):
        ids = {"a": 82400}
        self.assertEqual(gen.choose_helper_id("b", ids, {}, "barbarian"), 82401)
        self.assertEqual(gen.choose_category_id("s", {"x": 8100}, "barbarian"), 8101)

    def test_a_scratch_render_is_not_held_to_the_sheet(self):
        saved = gen.GENERATED
        try:
            with tempfile.TemporaryDirectory() as scratch:
                gen.GENERATED = Path(scratch)
                self.assertIsNone(gen.reserved_ids("helper:wizard"))
                self.assertEqual(gen.choose_helper_id("new - token storage", {}, {}, "wizard", gen.reserved_ids), 83300)
            gen.GENERATED = saved
            ids, message = gen.reserved_ids("helper:wizard")  # the repo's own outputs are held to the sheet
            self.assertIsInstance(ids, list)
            self.assertIn("helper:wizard", message)
        finally:
            gen.GENERATED = saved

    def test_the_generator_takes_category_ids_from_the_reservation(self):
        ids = {"x": 10}
        reserved = lambda pool: ([12, 13], "none")
        self.assertEqual(gen.choose_category_id("s", ids, "demon_hunter", reserved), 12)
        self.assertEqual(gen.choose_category_id("t", ids, "demon_hunter", reserved), 13)
        with self.assertRaises(SystemExit) as caught:
            gen.choose_category_id("u", ids, "demon_hunter", reserved)
        self.assertEqual(caught.exception.code, "none")
        self.assertEqual(gen.choose_category_id("x", ids, "demon_hunter", reserved), 10)  # a mapped skill keeps its id


if __name__ == "__main__":
    unittest.main()
