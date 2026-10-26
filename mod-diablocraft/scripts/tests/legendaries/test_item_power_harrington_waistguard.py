"""Legendary rest, bead diablocraft-ikpbp: Harrington Waistguard (a belt, list row 60, K3), and the event it builds, N-CHEST.

  "Opening a chest grants [100 - 135]% increased damage for 10 seconds."
  * the numbers are read from d3planner (item_waist.js, Unique_Belt_105_x1: the 100-135 and the 10 seconds), the item's roll and the power file through
    decode_pow.py (Item_Power_Passive ItemPassive_Unique_Ring_685_x1.pow: 1-1.35; SF_1 'Buff Duration' = 10); the table (data/legendary_powers.csv) holds ONE
    `player` row for the belt: `damage_dealt_pct` 100-135 under `triggered` 10 seconds, fired by the new `chest` event, rolled once per item;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator accepts the
    `chest` event only as the event of a triggered window or an effect, with no skills;
  * the production rules (src/combat/dc_item_power_math.h: Fire, PlayerFactor, Holds' `triggered`, Owned, RollPowers) are compiled and driven with the
    generated row: while the belt is worn and rolled, a chest opened at time t multiplies the damage dealt by 1 + N/100 from t to t + 10 s inclusive and not
    after, a chest opened again renews it, another event, an unworn belt, another owner's and an unrolled one change nothing; a Primal rolls 135;
  * mutants of the row and the rules fail the same driver; source-text guards that a chest the core flips to GO_ACTIVATED, opened by a player, fires the
    `chest` event, and only when some row listens, and only once per opening (diablocraft-69lxx: the core sets GO_ACTIVATED again on every release of a
    half-looted chest, with the releasing player, so ChestOpen::Openings of dc_chest_open_math.h, compiled and driven by tests/item_power_chest_open,
    counts only the change into activated from another state). The C++ is compile-checked by syntax_check.sh and the in-game steps are in
    docs/test-diablocraft-ikpbp.md.
"""
import csv
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
import generate_legendary_powers as generator  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
EVENTS = SRC / "combat/dc_item_powers_events.cpp"
HARNESS = MODULE / "tests/item_power_harrington_waistguard/harness.cpp"
OPEN_HARNESS = MODULE / "tests/item_power_chest_open/harness.cpp"
OPEN_MATH = SRC / "combat/dc_chest_open_math.h"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_Belt_105_x1"
STAT = "damage_dealt_pct"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
g = lambda x: "%.10g" % x  # noqa: E731


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


def words():
    """(the damage's low, its high, the seconds) from d3planner's belt."""
    text = (REPO / "reference/d3planner/item_waist.js").read_text(encoding="utf-8")
    start = text.index('id: "%s"' % OWNER)
    item = text[start:text.index("},\n\n", start)]
    m = re.search(r'format: "Opening a chest grants %d%% increased damage for (\d+) seconds\.", min: (\d+), max: (\d+)', item)
    assert m, item
    return float(m[2]), float(m[3]), float(m[1])


class Table(unittest.TestCase):
    def test_the_sources_say_100_to_135_for_10_seconds(self):
        self.assertEqual((100.0, 135.0, 10.0), words())
        self.assertIn("Opening a chest grants [100-135]% increased damage for 10 seconds.", (REPO / "docs/research/legendary-catalogue.csv").read_text(encoding="utf-8"))

    def test_the_power_file_has_the_same_ten_seconds_and_the_same_roll(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("no D3 archives on this machine")
        run = lambda *a: harness_env.run([sys.executable, str(MODULE / "scripts/decode_pow.py"), *a], capture_output=True, text=True).stdout  # noqa: E731
        self.assertRegex(run("power", "ItemPassive_Unique_Ring_685_x1"), r"'Buff Duration' = 10\b")
        self.assertIn("ItemPassive_Unique_Ring_685_x1.pow: 1-1.35", run("item", OWNER))

    def test_one_triggered_damage_row_on_the_chest_event(self):
        low, high, seconds = words()
        self.assertEqual([(OWNER, 0, "player", "", STAT, low, high, "triggered", seconds, "", 0.0, 0, "chest", "", 100.0, 0.0)], mine())

    def test_the_tooltip_says_it(self):
        m = re.search(r"INSERT INTO `dc_item_tooltip` VALUES \('%s','[^']*','([^']*)'" % OWNER,
                      (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertIn("Opening a chest grants 100–135% increased damage for 10 seconds.", m[1])

    def test_the_render_is_the_newest_full_table_and_the_applied_one_is_left(self):
        self.assertEqual(GENERATED.read_bytes(), (MODULE / "data/sql/db-world/updates" / GENERATED.name).read_bytes())
        self.assertGreaterEqual(GENERATED.name, "legendary_powers_0065_table.sql")


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "player", "skill": "", "stat": STAT, "value_min": "100", "value_max": "135", "cond": "triggered", "cond_arg": "10",
            "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "chest", "fire_skills": "", "chance_pct": "", "icd_seconds": "",
            "source": "s", "note": "n"}

    def render_with(self, edit):
        work = Path(tempfile.mkdtemp(prefix="waistguard-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            rows = read_csv("data/legendary_powers.csv")
            kept = [r for r in rows if r["owner"] != OWNER]
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(kept + [{**self.BASE, **edit}])
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_real_row_passes(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        self.assertEqual(1, len([r for r in self.render_with({}) if r[0] == OWNER]))

    def test_it_refuses_what_it_cannot_carry(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        refused = {
            "the chest event named for skills": {"fire_skills": "Rend"},
            "an unknown event": {"fire_on": "chests"},
            "a window with no event": {"fire_on": ""},
            "a window of no seconds": {"cond_arg": "0"},
        }
        for name, edit in refused.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    self.render_with(edit)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files={"combat/dc_item_power_math.h": header_text})
        return Path(tempfile.mkdtemp(prefix="itemwaistguard-%s-" % name, dir=str(SCRATCH))), binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the item's words and numbers, not from the code."""
        low, high, seconds = words()
        ms = int(seconds * 1000)
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        # not worn: a chest changes nothing
        out += clear + [(T("now", 1000), None), (T("event", "chest"), None), (T("dealt"), "1")]
        for roll in (low, 120, high):
            wear = clear + [(T("wears", OWNER), None), (T("rolled", OWNER, "", STAT, roll), None)]
            # worn and rolled, no chest opened yet: nothing
            out += wear + [(T("now", 5000), None), (T("dealt"), "1")]
            # a chest at 5000 ms: the window runs the 10 seconds, the end inclusive, and not after
            out += wear + [(T("now", 5000), None), (T("event", "chest"), None)]
            for t, on in ((5000, True), (5001, True), (9999, True), (5000 + ms - 1, True), (5000 + ms, True), (5000 + ms + 1, False), (30000, False)):
                out += [(T("now", t), None), (T("dealt"), g(1 + roll / 100) if on else "1")]
            # another chest inside the window renews it: from the second one, 10 seconds again
            out += wear + [(T("now", 5000), None), (T("event", "chest"), None), (T("now", 12000), None), (T("event", "chest"), None)]
            for t, on in ((15000, True), (22000, True), (22001, False)):
                out += [(T("now", t), None), (T("dealt"), g(1 + roll / 100) if on else "1")]
            # another event starts nothing
            out += wear + [(T("now", 5000), None)] + [(T("event", e), None) for e in ("hit", "kill", "kill_elite", "cast", "tick", "chests", "")] + [(T("dealt"), "1")]
        # worn, nothing rolled yet: the row is not on, even after a chest
        out += clear + [(T("wears", OWNER), None), (T("now", 5000), None), (T("event", "chest"), None), (T("dealt"), "1")]
        # a roll stored but the belt in the bag, and another owner's belt
        out += clear + [(T("rolled", OWNER, "", STAT, 120), None), (T("now", 5000), None), (T("event", "chest"), None), (T("dealt"), "1")]
        out += clear + [(T("wears", "Other Belt"), None), (T("rolled", "Other Belt", "", STAT, 120), None), (T("now", 5000), None), (T("event", "chest"), None), (T("dealt"), "1")]
        return out

    def drive(self, header_text, rows, name):
        cases = self.cases(rows)
        work, binary = self.build(header_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_every_rule_agrees_with_the_item_text(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(want), 30)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        want, _ = self.drive(real, rows, "want")
        row = rows[0]
        row_mutants = {
            "five_seconds": [row[:8] + (5.0,) + row[9:]],
            "fixed_a_tenth": [row[:5] + (10.0, 10.0) + row[7:]],
            "another_event": [row[:12] + ("kill",) + row[13:]],
            "no_condition": [row[:7] + ("", 0.0) + row[9:]],
            "another_stat": [row[:4] + ("damage_taken_pct",) + row[5:]],
            "no_row": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        window = real[real.index('if (row.cond == "triggered")'):] if 'if (row.cond == "triggered")' in real else ""
        self.assertTrue(window, "the triggered condition's text moved; update this test")
        for name, (old, new) in {
            "the_end_is_exclusive": ("<= static_cast<std::uint32_t>(row.arg", "< static_cast<std::uint32_t>(row.arg"),
            "the_window_never_ends": ("(situation.now - last->second) <= static_cast<std::uint32_t>(row.arg * 1000.0)", "true"),
            "the_window_is_in_seconds": ("static_cast<std::uint32_t>(row.arg * 1000.0)", "static_cast<std::uint32_t>(row.arg)"),
        }.items():
            with self.subTest(mutant=name):
                chunk = window[:window.index("}") + 1]   # the condition's block
                self.assertIn(old, chunk, name + " does not apply")
                _, got = self.drive(real.replace(chunk, chunk.replace(old, new, 1), 1), rows, name)
                self.assertNotEqual(want, got, name + " survived")


class Openings(unittest.TestCase):
    """diablocraft-69lxx: the chest event is one per opening. The core sets GO_ACTIVATED on the opener's first look (GO_READY -> GO_ACTIVATED, Player::SendLoot)
    and again on every release of a chest that is not empty (LootHandler, the releasing player), so the rule is the change into activated."""

    def cases(self):
        """[(command line, expected output line or None)]: worked out from how the core sets the loot state, not from the code."""
        out = []
        a, b = (1, 0, 500), (1, 0, 501)

        def state(chest, what, opens):
            out.append((T("state", *chest, what), "1" if opens else "0"))
        # the opener opens (ready -> activated): one opening
        state(a, "other", False)
        state(a, "activated", True)
        # leaves an item and closes: the core sets activated again with the releasing player: not an opening
        state(a, "activated", False)
        # reopens and closes again, twice more: still not
        state(a, "activated", False)
        state(a, "activated", False)
        # a second player opens the already-open chest and closes it without emptying it: not an opening, and another chest is its own
        state(b, "activated", True)
        state(a, "activated", False)
        state(b, "activated", False)
        # the chest is emptied (just deactivated), then respawns ready: the next opening counts again, once
        state(a, "other", False)
        state(a, "other", False)
        state(a, "activated", True)
        state(a, "activated", False)
        # a restock that sets it ready again while a half-looted copy is open: a new opening
        state(a, "other", False)
        state(a, "activated", True)
        # the same guid on another map and in another instance of the map is another chest
        for other in ((2, 0, 500), (1, 7, 500)):
            state(other, "activated", True)
            state(other, "activated", False)
        out.append((T("held"), "4"))
        # a chest that left the world while open starts closed
        out.append((T("forget", *a), None))
        out.append((T("held"), "3"))
        state(a, "activated", True)
        out.append((T("forget", *a), None))
        out.append((T("forget", 9, 9, 9), None))
        state(a, "activated", True)
        return out

    def drive(self, header_text, name):
        cases = self.cases()
        SCRATCH.mkdir(parents=True, exist_ok=True)
        binary = harness_env.build([OPEN_HARNESS], flags=["-std=c++17", "-O1"], files={"combat/dc_chest_open_math.h": header_text})
        work = Path(tempfile.mkdtemp(prefix="chestopen-%s-" % name, dir=str(SCRATCH)))
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_only_the_change_into_activated_is_an_opening(self):
        want, got = self.drive(OPEN_MATH.read_text(encoding="utf-8"), "real")
        self.assertGreater(len(want), 20)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = OPEN_MATH.read_text(encoding="utf-8")
        want, _ = self.drive(real, "want")
        mutants = {
            "every_activation_is_an_opening": ("return open.insert(chest).second;", "open.insert(chest);\n            return true;"),
            "a_release_forgets_it": ("if (!activated)\n            {\n                open.erase(chest);\n                return false;\n            }", "if (!activated)\n                return false;"),
            "forget_does_nothing": ("void Forget(Key const& chest)\n        {\n            open.erase(chest);\n        }", "void Forget(Key const&)\n        {\n        }"),
            "never_an_opening": ("return open.insert(chest).second;", "open.insert(chest);\n            return false;"),
            "a_chest_is_its_guid": ("using Key = std::tuple<std::uint32_t, std::uint32_t, std::uint64_t>;", "using Key = std::tuple<std::uint32_t, std::uint32_t, std::uint64_t>;\n    inline Key Fold(Key k) { return {0, 0, std::get<2>(k)}; }"),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply")
                if name == "a_chest_is_its_guid":
                    changed = real.replace(old, new, 1).replace("open.insert(chest)", "open.insert(Fold(chest))").replace("open.erase(chest)", "open.erase(Fold(chest))")
                else:
                    changed = real.replace(old, new, 1)
                _, got = self.drive(changed, name)
                self.assertNotEqual(want, got, name + " survived")


def event_failures(text):
    """What is wrong with the chest event's script in `text` ([] when it is right)."""
    flat = re.sub(r"\s+", " ", text)
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    need("it is a game object script", 'class ChestEvents final : public AllGameObjectScript' in flat and 'AllGameObjectScript("dc_item_power_chest_events")' in flat)
    need("it listens to the loot state change", "void OnGameObjectLootStateChanged(GameObject* go, uint32 state, Unit* user) override" in flat)
    need("only a chest, and only when a row listens",
         "if (!go || go->GetGoType() != GAMEOBJECT_TYPE_CHEST || !Data().events.count(\"chest\")) return;" in flat)
    need("an opening is the change into activated, judged under the lock",
         "opened = openings.Changed(KeyOf(go), state == GO_ACTIVATED);" in flat and "std::lock_guard<std::mutex> lock(mutex); opened =" in flat)
    need("nothing fires unless it is an opening", "if (!opened) return;" in flat)
    need("it fires the opener's chest event", 'if (Player* opener = user ? user->ToPlayer() : nullptr) Fire(opener, "chest", "", 1.0);' in flat)
    need("the fire comes after the opening is judged", flat.find("if (!opened) return;") < flat.find('Fire(opener, "chest", "", 1.0);'))
    need("a chest leaving the world is forgotten", "void OnGameObjectRemoveWorld(GameObject* go) override" in flat and "openings.Forget(KeyOf(go));" in flat)
    need("a chest is keyed by map, instance and guid", "return {go->GetMapId(), go->GetInstanceId(), go->GetGUID().GetRawValue()};" in flat)
    need("it is registered", "new ChestEvents();" in flat)
    return wrong


class Hooks(unittest.TestCase):
    def test_the_chest_script(self):
        self.assertEqual([], event_failures(EVENTS.read_text(encoding="utf-8")))

    def test_the_source_guards_fail_their_mutants(self):
        real = EVENTS.read_text(encoding="utf-8")
        mutants = {
            "every_activation_fires": ("opened = openings.Changed(KeyOf(go), state == GO_ACTIVATED);", "opened = state == GO_ACTIVATED;"),
            "any_state_is_an_opening": ("openings.Changed(KeyOf(go), state == GO_ACTIVATED)", "openings.Changed(KeyOf(go), true)"),
            "the_opening_is_not_asked": ("if (!opened)\n                    return;", ""),
            "never_forgotten": ("openings.Forget(KeyOf(go));", ""),
            "keyed_by_guid_alone": ("return {go->GetMapId(), go->GetInstanceId(), go->GetGUID().GetRawValue()};", "return {0, 0, go->GetGUID().GetRawValue()};"),
            "any_object": ("go->GetGoType() != GAMEOBJECT_TYPE_CHEST || ", ""),
            "always_looks": ('|| !Data().events.count("chest")', ""),
            "not_the_opener": ('Fire(opener, "chest", "", 1.0);', 'Fire(opener, "kill", "", 1.0);'),
            "a_creature_may_open": ("user ? user->ToPlayer() : nullptr", "user ? user->ToPlayer() : nullptr) || (user"),
            "not_registered": ("new ChestEvents();", ""),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply")
                self.assertNotEqual([], event_failures(real.replace(old, new, 1)), name + " survived")


if __name__ == "__main__":
    unittest.main()
