"""Legendary rest, bead diablocraft-kxdwe: Maloth's Focus (a staff, list row 63, K3), and the piece it builds, N-FEAR.

  "Enemies occasionally flee at the sight of this staff."
  * the words are d3planner's (item_twohand.js, Unique_Staff_006_x1: custom leg_malothsfocus, no number); the numbers are the power file's, read through
    decode_pow.py (Item_Power_Passive itemPassive_Unique_Staff_006.pow: 1; SF_0 'Fear Duration' = 2.5, SF_1 'Target Area Distance' = 30, SF_2 'Cooldown Duration' = 10,
    SF_3 'Cooldown Delta' = 5). The file holds no chance, so the cooldown alone paces the proc (D3's rule; no tunable, no card). The table
    (data/legendary_powers.csv) holds THREE rows for the staff: the `effect` `fear_enemies` 2.5 on the `tick` clock with `icd_seconds` 10, and the fixed `player` rows
    `fear_yards` 30 and `fear_cooldown_delta_seconds` 5;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator accepts `fear_enemies`
    only as an item's one fixed number on `tick`, with both companion rows, and the companion rows only beside it;
  * the production rules (src/combat/dc_item_power_math.h: Fire, ControlSpell, DelayedStamp, RetryStamp) are compiled and driven with the generated rows: the clock
    fires the effect once and not again until the cooldown (10 s, the end inclusive) is over; a stamp set ahead of now (the extra wait of the delta) holds it that
    long and then the cooldown; the stock Fear (5782) is the hold; the extra wait is the delta times a draw clamped to 0..1; a proc that found nobody frees the row
    after the 0.25 s check; mutants of the rows and the rules fail the same driver;
  * source-text guards that the executor feeds the fear enemies within the item's yards, in combat, stamps the row by what happened and holds each enemy with
    the stock Fear. The C++ is compile-checked by syntax_check.sh and the in-game steps are in docs/test-diablocraft-kxdwe.md.
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
EFFECTS = SRC / "combat/dc_item_powers_effects.cpp"
HARNESS = MODULE / "tests/item_power_maloths_focus/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_Staff_006_x1"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
g = lambda x: "%.10g" % x  # noqa: E731
FEAR = 5782
ROOT = 64695
SECONDS, YARDS, DELTA, COOLDOWN = 2.5, 30.0, 5.0, 10.0


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


class Table(unittest.TestCase):
    def test_the_sources_say_enemies_flee_at_the_sight_of_the_staff(self):
        text = (REPO / "reference/d3planner/item_twohand.js").read_text(encoding="utf-8")
        start = text.index('id: "%s"' % OWNER)
        item = text[start:text.index("},\n\n", start)]
        self.assertIn('format: "Enemies occasionally flee at the sight of this staff.", args: 0', item)
        self.assertIn("Enemies occasionally flee at the sight of this staff.", (REPO / "docs/research/legendary-catalogue.csv").read_text(encoding="utf-8"))

    def test_the_power_file_has_the_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("no D3 archives on this machine")
        run = lambda *a: harness_env.run([sys.executable, str(MODULE / "scripts/decode_pow.py"), *a], capture_output=True, text=True).stdout  # noqa: E731
        power = run("power", "itemPassive_Unique_Staff_006")
        for label, number in (("Fear Duration", "2.5"), ("Target Area Distance", "30"), ("Cooldown Duration", "10"), ("Cooldown Delta", "5")):
            self.assertRegex(power, r"'%s' = %s\b" % (label, number.replace(".", r"\.")))
        self.assertIn("itemPassive_Unique_Staff_006.pow: 1", run("item", OWNER))

    def test_three_rows_for_the_staff(self):
        self.assertEqual([
            (OWNER, 0, "effect", "", "fear_enemies", SECONDS, SECONDS, "", 0.0, "", 0.0, 0, "tick", "", 100.0, COOLDOWN),
            (OWNER, 0, "player", "", "fear_yards", YARDS, YARDS, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0),
            (OWNER, 0, "player", "", "fear_cooldown_delta_seconds", DELTA, DELTA, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0),
        ], sorted(mine(), key=lambda r: (r[2] != "effect", r[4] != "fear_yards")))

    def test_the_render_is_the_newest_full_table_and_the_applied_one_is_left(self):
        self.assertEqual(GENERATED.read_bytes(), (MODULE / "data/sql/db-world/updates" / GENERATED.name).read_bytes())
        self.assertGreaterEqual(GENERATED.name, "legendary_powers_0066_table.sql")


class Generator(unittest.TestCase):
    EFFECT = {"owner": OWNER, "pieces": "", "kind": "effect", "skill": "", "stat": "fear_enemies", "value_min": "2.5", "value_max": "2.5", "cond": "", "cond_arg": "",
              "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "tick", "fire_skills": "", "chance_pct": "", "icd_seconds": "10",
              "source": "s", "note": "n"}
    YARDS = {**EFFECT, "kind": "player", "stat": "fear_yards", "value_min": "30", "value_max": "30", "fire_on": "", "icd_seconds": ""}
    DELTA = {**EFFECT, "kind": "player", "stat": "fear_cooldown_delta_seconds", "value_min": "5", "value_max": "5", "fire_on": "", "icd_seconds": ""}

    def render_with(self, effect=None, yards=None, delta=None):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="maloth-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            rows = read_csv("data/legendary_powers.csv")
            kept = [r for r in rows if r["owner"] != OWNER]
            added = [{**self.EFFECT, **(effect or {})}] if effect != "none" else []
            added += [{**self.YARDS, **(yards or {})}] if yards != "none" else []
            added += [{**self.DELTA, **(delta or {})}] if delta != "none" else []
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(kept + added)
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_real_rows_pass(self):
        self.assertEqual(3, len([r for r in self.render_with() if r[0] == OWNER]))

    def test_it_refuses_what_it_cannot_carry(self):
        refused = {
            "the effect on a hit": dict(effect={"fire_on": "hit"}),
            "no clock period": dict(effect={"icd_seconds": ""}),
            "a chance": dict(effect={"chance_pct": "50"}),
            "a range": dict(effect={"value_max": "3"}),
            "no seconds": dict(effect={"value_min": "0", "value_max": "0"}),
            "a set level": dict(effect={"pieces": "2"}),
            "a condition": dict(effect={"cond": "triggered", "cond_arg": "5"}),
            "no yards row": dict(yards="none"),
            "no delta row": dict(delta="none"),
            "a yards range": dict(yards={"value_max": "40"}),
            "a delta on an event": dict(delta={"fire_on": "hit"}),
            "companion rows alone": dict(effect="none"),
        }
        for name, edits in refused.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    self.render_with(**edits)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files={"combat/dc_item_power_math.h": header_text})
        return Path(tempfile.mkdtemp(prefix="itemmaloth-%s-" % name, dir=str(SCRATCH))), binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the item's words and the power file's numbers, not from the code."""
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        wear = clear + [(T("wears", OWNER), None)]
        cool = int(COOLDOWN * 1000)
        proc = "fear_enemies:%s" % g(SECONDS)
        # worn, never fired: the clock fires it
        out += wear + [(T("now", 50000), None), (T("fire", "tick", ""), proc)]
        # fired at 50000: held for the cooldown, the end inclusive of the next moment it is over
        out += wear + [(T("now", 50000), None), (T("stamp", 50000), None)]
        for t, want in ((50000, "none"), (50001, "none"), (50000 + cool - 1, "none"), (50000 + cool, proc), (80000, proc)):
            out += [(T("now", t), None), (T("fire", "tick", ""), want)]
        # a stamp set ahead of now (the delta's extra wait): held until then, and then the cooldown
        out += wear + [(T("stamp", 53000), None)]
        for t, want in ((50000, "none"), (53000, "none"), (53000 + cool - 1, "none"), (53000 + cool, proc)):
            out += [(T("now", t), None), (T("fire", "tick", ""), want)]
        # other events and skills do not fire it; an unworn staff, another owner's, nothing
        out += wear + [(T("now", 50000), None)] + [(T("fire", e, ""), "none") for e in ("hit", "kill", "cast", "taken", "chest", "tick_", "")]
        out += clear + [(T("now", 50000), None), (T("fire", "tick", ""), "none")]
        out += clear + [(T("wears", "Other Staff"), None), (T("now", 50000), None), (T("fire", "tick", ""), "none")]
        # the hold is the stock Fear; the root is the root; nothing else is a hold
        out += [(T("spell", "fear_enemies"), str(FEAR)), (T("spell", "root_seconds"), str(ROOT)), (T("spell", "fear"), "0"), (T("spell", ""), "0")]
        # the extra wait: the delta times a draw clamped to 0..1, from now
        for now, delta, unit, want in ((1000, 5, 0, 1000), (1000, 5, 1, 6000), (1000, 5, 0.5, 3500), (1000, 5, 2, 6000), (1000, 5, -1, 1000), (1000, 0, 1, 1000),
                                       (1000, -5, 1, 1000), (1000, 5, 0.2, 2000)):
            out.append((T("delay", now, delta, unit), str(want)))
        # a proc that found nobody: the row may try again after the check, so the stamp leaves only that much of the cooldown
        for now, icd, retry, want in ((100000, 10, 0.25, 90250), (100000, 10, 1, 91000), (5000, 10, 0.25, 4294962546), (1000, 10, 1, 4294959296), (100000, 0.1, 0.25, 100000), (100000, 0.25, 0.25, 100000),
                                      (100000, 10, 0, 90000), (100000, 10, -1, 90000)):
            out.append((T("retry", now, icd, retry), str(want)))
        # and that stamp frees the row after the check and not before
        out += wear + [(T("stamp", 90250), None)]
        for t, want in ((100000, "none"), (100249, "none"), (100250, proc)):
            out += [(T("now", t), None), (T("fire", "tick", ""), want)]
        # the clock wraps (a uint32 of milliseconds, about 49.7 days): a stamp just below 2^32 is 796 ms old at now 500, and the cooldown ends 10 seconds after it
        wrap = 4294967000
        out += wear + [(T("stamp", wrap), None)]
        for t, want in ((500, "none"), (9703, "none"), (9704, proc), (20000, proc)):
            out += [(T("now", t), None), (T("fire", "tick", ""), want)]
        # a stamp set ahead of now across the wrap holds until the clock reaches it and then for the cooldown
        out += wear + [(T("stamp", 1000), None)]
        for t, want in ((4294966500, "none"), (4294967295, "none"), (1000, "none"), (10999, "none"), (11000, proc)):
            out += [(T("now", t), None), (T("fire", "tick", ""), want)]
        # an old stamp (30 days ago) is not ahead: the row fires
        out += wear + [(T("stamp", 1000), None), (T("now", 1000 + 2592000000), None), (T("fire", "tick", ""), proc)]
        # what is ahead: 1 ms to an hour in front of now, wrap included; the same moment, behind, and further in front are not
        for now, last, want in ((1000, 1001, 1), (1000, 1000, 0), (1000, 1000 + 3600000, 1), (1000, 1000 + 3600001, 0), (1000, 999, 0), (4294966000, 1000, 1), (1000, 4294966000, 0),
                                (1000, 1000 + 2592000000, 0)):
            out.append((T("ahead", now, last), str(want)))
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
        self.assertGreater(len(want), 40)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(3, len(rows))
        want, _ = self.drive(real, rows, "want")
        effect = [r for r in rows if r[2] == "effect"][0]
        others = [r for r in rows if r[2] != "effect"]
        row_mutants = {
            "five_seconds_of_fear": [effect[:5] + (5.0, 5.0) + effect[7:]] + others,
            "a_cooldown_of_five": [effect[:15] + (5.0,)] + others,
            "another_event": [effect[:12] + ("hit",) + effect[13:]] + others,
            "no_row": others,
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        for name, (old, new) in {
            "fear_is_the_root": ("stat == \"root_seconds\" ? RootHold : stat == \"fear_enemies\" ? FearHold : 0", "stat == \"root_seconds\" ? RootHold : stat == \"fear_enemies\" ? RootHold : 0"),
            "no_fear_hold": ("stat == \"root_seconds\" ? RootHold : stat == \"fear_enemies\" ? FearHold : 0", "stat == \"root_seconds\" ? RootHold : 0"),
            "the_stamp_ahead_does_not_hold": ("StampAhead(situation.now, last->second) || ", ""),
            "the_cooldown_end_is_exclusive": ("(situation.now - last->second) < static_cast<std::uint32_t>(icd * 1000.0)))", "(situation.now - last->second) <= static_cast<std::uint32_t>(icd * 1000.0)))"),
            "the_delay_is_in_seconds": ("* 1000.0 * std::min(1.0, std::max(0.0, unit))", "* std::min(1.0, std::max(0.0, unit))"),
            "the_draw_is_not_clamped": ("deltaSeconds) * 1000.0 * std::min(1.0, std::max(0.0, unit))", "deltaSeconds) * 1000.0 * unit"),
            "a_negative_delta_goes_back": ("std::max(0.0, deltaSeconds) * 1000.0", "deltaSeconds * 1000.0"),
            "retry_is_now": ("return now + static_cast<std::uint32_t>(wait) - static_cast<std::uint32_t>(cooldown);", "return now;"),
            "retry_adds_the_cooldown": ("return now + static_cast<std::uint32_t>(wait) - static_cast<std::uint32_t>(cooldown);", "return now + static_cast<std::uint32_t>(wait) + static_cast<std::uint32_t>(cooldown);"),
            "ahead_by_the_plain_comparison": ("StampAhead(situation.now, last->second) ||", "last->second > situation.now ||"),
            "ahead_by_a_signed_difference": ("StampAhead(situation.now, last->second) ||", "static_cast<std::int32_t>(last->second - situation.now) > 0 ||"),
            "ahead_includes_now": ("return ahead != 0 && ahead <= MaxStampAheadMs;", "return ahead <= MaxStampAheadMs;"),
            "ahead_end_exclusive": ("return ahead != 0 && ahead <= MaxStampAheadMs;", "return ahead != 0 && ahead < MaxStampAheadMs;"),
            "ahead_without_a_limit": ("return ahead != 0 && ahead <= MaxStampAheadMs;", "return ahead != 0;"),
            "no_ahead_at_all": ("StampAhead(situation.now, last->second) ||", ""),
        }.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply")
                _, got = self.drive(real.replace(old, new, 1), rows, name)
                self.assertNotEqual(want, got, name + " survived")


def frighten_failures(effects):
    """What is wrong with the fear executor in `effects` ([] when it is right)."""
    flat = re.sub(r"\s+", " ", effects)
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    start = flat.find("void Frighten(Player* player, ItemPower::Row const& row, double seconds) {")
    need("the executor exists", start >= 0)
    body = flat[start:flat.find("} // namespace Detail") if flat.find("} // namespace Detail") > start else None] if start >= 0 else ""
    body = body[:body.find("// Bul-Kathos")] if "// Bul-Kathos" in body else body
    need("the reach is the item's fear_yards row", 'ItemPower::OwnerNumber(Data().rows, row.owner, "player", "fear_yards")' in body)
    need("the extra wait is the item's delta row", 'ItemPower::OwnerNumber(Data().rows, row.owner, "player", "fear_cooldown_delta_seconds")' in body)
    need("only a living player in combat frightens, with reach", "if (yards > 0 && player->IsAlive() && player->IsInCombat())" in body)
    need("the enemies are the ones within the yards under the stock Fear", "Combat::Enemies(player, ItemPower::FearHold, player->GetPosition(), yards)" in body)
    need("each one is held with the stock Fear for the row's seconds", "Control(player, enemy, ItemPower::FearHold, seconds);" in body)
    need("the stamp is judged under the lock", "std::lock_guard<std::mutex> lock(mutex); clocks[player->GetGUID().GetRawValue()].fired[ItemPower::FireKey(row)] =" in body)
    need("feared enemies delay the next proc by a draw of the delta, nobody frees it after the check",
         "feared ? ItemPower::DelayedStamp(now, delta, rand_norm()) : ItemPower::RetryStamp(now, row.icdSeconds, ItemPower::TriggerCheckSeconds);" in body)
    need("the executor's branch is the fear_enemies stat with its row", 'else if (one.stat == "fear_enemies" && one.row) Frighten(player, *one.row, one.value);' in flat)
    return wrong


class Hooks(unittest.TestCase):
    def test_the_fear_executor(self):
        self.assertEqual([], frighten_failures(EFFECTS.read_text(encoding="utf-8")))

    def test_the_tick_clock_calls_it(self):
        self.assertIn('Fire(player, "tick", "", 1.0);', (SRC / "combat/dc_item_powers.cpp").read_text(encoding="utf-8"))

    def test_the_source_guards_fail_their_mutants(self):
        real = EFFECTS.read_text(encoding="utf-8")
        mutants = {
            "no_yards_row": ('"player", "fear_yards")', '"player", "fear_range")'),
            "no_delta_row": ('"player", "fear_cooldown_delta_seconds")', '"player", "fear_delta")'),
            "out_of_combat_frightens": (" && player->IsInCombat())", ")"),
            "any_spell_for_the_search": ("Combat::Enemies(player, ItemPower::FearHold,", "Combat::Enemies(player, 0,"),
            "root_instead_of_fear": ("Control(player, enemy, ItemPower::FearHold, seconds);", "Control(player, enemy, ItemPower::RootHold, seconds);"),
            "nobody_spends_the_cooldown": ("ItemPower::RetryStamp(now, row.icdSeconds, ItemPower::TriggerCheckSeconds)", "ItemPower::DelayedStamp(now, delta, rand_norm())"),
            "no_delay": ("ItemPower::DelayedStamp(now, delta, rand_norm())", "ItemPower::DelayedStamp(now, 0.0, rand_norm())"),
            "not_dispatched": ('else if (one.stat == "fear_enemies" && one.row)', 'else if (one.stat == "fear_enemy" && one.row)'),
            "stamped_outside_the_lock": ("std::lock_guard<std::mutex> lock(mutex);\n            clocks[player->GetGUID().GetRawValue()].fired", "clocks[player->GetGUID().GetRawValue()].fired"),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply")
                self.assertNotEqual([], frighten_failures(real.replace(old, new, 1)), name + " survived")


if __name__ == "__main__":
    unittest.main()
