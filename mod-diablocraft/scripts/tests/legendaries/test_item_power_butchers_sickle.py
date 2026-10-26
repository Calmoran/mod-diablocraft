"""Legendary rest, bead diablocraft-v052u: The Butcher's Sickle (a one-hand axe, list row 64, K3), and the piece it builds, N-PULLFX.

  "[20-25]% chance to drag enemies to you when attacking."
  * the words and the range are d3planner's (item_onehand.js, Unique_Axe_1H_006_x1: custom leg_thebutcherssickle, min 20 max 25); the power file's numbers are read through
    decode_pow.py (Item_Power_Passive ItemPassive_Unique_Axe_1H_006.pow: 0.2-0.25; SF_0 'max Range' = 40, SF_3 'Internal CoolUp/Down' = 6, SF_6 'stun duration' = 2).
    The table (data/legendary_powers.csv) holds SIX rows for the axe: the `effect` `pull_enemy` [20-25] (the chance, rolled once per item) on `hit`, and the fixed
    `player` rows `pull_yards` 40, `pull_stun_seconds` 2, `pull_cooldown_seconds` 6, and the hook's damage `pull_damage` and `pull_damage_delta`, each the file's
    Table(LegendaryProcDmg, 59) / 5 = 358.2 / 5 = 71.64 (the damage runs from 71.64 to 143.28), the table read by decode_pow.py into data/d3/legendary_proc_dmg_table.csv;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator accepts `pull_enemy` only as
    an item's chance (a range, 0 to 100) on every hit with the three companion rows, and the companion rows only beside it;
  * the production rules (src/combat/dc_item_power_math.h: Fire, DragReady; dc_proc_math.h: Rolls) are compiled and driven with the generated rows: a hit of any skill
    fires the effect with the item's rolled chance and nothing else does; a drag is ready only for an enemy within 40 yards (the end inclusive) and 6 seconds after the
    last drag (the end inclusive, right across the clock's wrap), the damage is the minimum plus the delta by a draw, and the chance is the item's, scaled by the hit's proc coefficient (none: never); mutants of the rows and the rules fail the same driver;
  * source-text guards that the executor judges reach and cooldown before it rolls, starts the cooldown only for a drag, deals the hook's damage, pulls the enemy to the
    wearer and holds it in the stun stretched by StunFactor. The C++ is compile-checked by syntax_check.sh and the in-game steps are in docs/test-diablocraft-v052u.md.
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
HARNESS = MODULE / "tests/item_power_butchers_sickle/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_Axe_1H_006_x1"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
g = lambda x: "%.10g" % x  # noqa: E731
YARDS, STUN, COOLDOWN = 40.0, 2.0, 6.0
DAMAGE = 71.64   # Table(LegendaryProcDmg, 59) / 5 = 358.2 / 5, and the delta is the same


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]




class Table(unittest.TestCase):
    def test_the_sources_say_20_to_25_percent_to_drag_enemies(self):
        text = (REPO / "reference/d3planner/item_onehand.js").read_text(encoding="utf-8")
        start = text.index('id: "%s"' % OWNER)
        item = text[start:text.index("},\n\n", start)]
        self.assertIn('format: "%d%% chance to drag enemies to you when attacking.", min: 20, max: 25', item)
        self.assertIn("[20-25]% chance to drag enemies to you when attacking.", (REPO / "docs/research/legendary-catalogue.csv").read_text(encoding="utf-8"))

    def test_the_power_file_has_the_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("no D3 archives on this machine")
        run = lambda *a: harness_env.run([sys.executable, str(MODULE / "scripts/decode_pow.py"), *a], capture_output=True, text=True).stdout  # noqa: E731
        power = run("power", "ItemPassive_Unique_Axe_1H_006")
        for label, number in (("max Range", "40"), ("Internal CoolUp/Down", "6"), ("stun duration", "2")):
            self.assertRegex(power, r"'%s' = %s\b" % (label, number))
        self.assertIn("ItemPassive_Unique_Axe_1H_006.pow: 0.2-0.25", run("item", OWNER))

    def test_the_damage_is_the_tables_level_59_over_5(self):
        with (MODULE / "data/d3/legendary_proc_dmg_table.csv").open(encoding="utf-8", newline="") as stream:
            sheet = list(csv.DictReader(stream, strict=True))
        self.assertEqual(list(range(76)), [int(r["level"]) for r in sheet])
        value = float(sheet[59]["value"])
        self.assertAlmostEqual(358.2, value, places=3)
        rows = {r[4]: r[5] for r in mine()}
        self.assertAlmostEqual(value / 5, rows["pull_damage"], places=6)
        self.assertAlmostEqual(value / 5, rows["pull_damage_delta"], places=6)

    def test_the_sheet_is_what_decode_pow_reads(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("no D3 archives on this machine")
        table = decode_pow.power_table("LegendaryProcDmg")
        with (MODULE / "data/d3/legendary_proc_dmg_table.csv").open(encoding="utf-8", newline="") as stream:
            sheet = [float(r["value"]) for r in csv.DictReader(stream, strict=True)]
        self.assertEqual(len(table), len(sheet))
        for a, b in zip(table, sheet):
            self.assertAlmostEqual(a, b, places=3)
        text = run = harness_env.run([sys.executable, str(MODULE / "scripts/decode_pow.py"), "power", "ItemPassive_Unique_Axe_1H_006"], capture_output=True, text=True).stdout
        self.assertIn("'damage ' = Table(LegendaryProcDmg,59) / 5", text)
        self.assertIn("'damage Delta' = Table(LegendaryProcDmg,59) / 5", run)

    def test_six_rows_for_the_axe(self):
        self.assertEqual([
            (OWNER, 0, "effect", "", "pull_enemy", 20.0, 25.0, "", 0.0, "", 0.0, 0, "hit", "", 100.0, 0.0),
            (OWNER, 0, "player", "", "pull_cooldown_seconds", COOLDOWN, COOLDOWN, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0),
            (OWNER, 0, "player", "", "pull_damage", DAMAGE, DAMAGE, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0),
            (OWNER, 0, "player", "", "pull_damage_delta", DAMAGE, DAMAGE, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0),
            (OWNER, 0, "player", "", "pull_stun_seconds", STUN, STUN, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0),
            (OWNER, 0, "player", "", "pull_yards", YARDS, YARDS, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0),
        ], sorted(mine(), key=lambda r: (r[2] != "effect", r[4])))

    def test_the_render_is_the_newest_full_table_and_the_applied_one_is_left(self):
        self.assertEqual(GENERATED.read_bytes(), (MODULE / "data/sql/db-world/updates" / GENERATED.name).read_bytes())
        self.assertGreaterEqual(GENERATED.name, "legendary_powers_0066_table.sql")


class Generator(unittest.TestCase):
    EFFECT = {"owner": OWNER, "pieces": "", "kind": "effect", "skill": "", "stat": "pull_enemy", "value_min": "20", "value_max": "25", "cond": "", "cond_arg": "",
              "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "hit", "fire_skills": "", "chance_pct": "", "icd_seconds": "",
              "source": "s", "note": "n"}
    BASE = {**EFFECT, "kind": "player", "fire_on": "", "value_min": "1", "value_max": "1"}
    COMPANIONS = {"pull_yards": "40", "pull_stun_seconds": "2", "pull_cooldown_seconds": "6", "pull_damage": "71.64", "pull_damage_delta": "71.64"}

    def render_with(self, effect=None, companions=None, drop=()):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="sickle-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            rows = read_csv("data/legendary_powers.csv")
            kept = [r for r in rows if r["owner"] != OWNER]
            added = [] if effect == "none" else [{**self.EFFECT, **(effect or {})}]
            for stat, number in self.COMPANIONS.items():
                if stat not in drop:
                    added.append({**self.BASE, "stat": stat, "value_min": number, "value_max": number, **((companions or {}).get(stat, {}))})
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(kept + added)
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_real_rows_pass(self):
        self.assertEqual(6, len([r for r in self.render_with() if r[0] == OWNER]))

    def test_it_refuses_what_it_cannot_carry(self):
        refused = {
            "the effect on a kill": dict(effect={"fire_on": "kill"}),
            "named skills": dict(effect={"fire_skills": "Frenzy"}),
            "a chance column": dict(effect={"chance_pct": "50"}),
            "a cooldown column": dict(effect={"icd_seconds": "6"}),
            "a condition": dict(effect={"cond": "triggered", "cond_arg": "5"}),
            "a set level": dict(effect={"pieces": "2"}),
            "no chance": dict(effect={"value_min": "0", "value_max": "0"}),
            "a chance over 100": dict(effect={"value_min": "50", "value_max": "150"}),
            "no yards row": dict(drop=("pull_yards",)),
            "no stun row": dict(drop=("pull_stun_seconds",)),
            "no cooldown row": dict(drop=("pull_cooldown_seconds",)),
            "no damage row": dict(drop=("pull_damage",)),
            "no damage delta row": dict(drop=("pull_damage_delta",)),
            "a yards range": dict(companions={"pull_yards": {"value_max": "50"}}),
            "a cooldown on an event": dict(companions={"pull_cooldown_seconds": {"fire_on": "hit"}}),
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
        files = {"combat/dc_item_power_math.h": header_text}
        for name in ("dc_item_proc_math.h", "dc_proc_math.h"):
            files["combat/" + name] = (SRC / "combat" / name).read_text(encoding="utf-8")
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        return Path(tempfile.mkdtemp(prefix="itemsickle-%s-" % name, dir=str(SCRATCH))), binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the item's words and the power file's numbers, not from the code."""
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        cool = int(COOLDOWN * 1000)
        # worn and rolled: a hit of any skill (or none) fires the effect with the item's own roll, at 20, 22.5 and 25
        for roll in (20, 22.5, 25):
            wear = clear + [(T("wears", OWNER), None), (T("rolled", OWNER, "", "pull_enemy", roll), None), (T("now", 5000), None)]
            for skill in ("", "Frenzy", "Whirlwind", "Lashing Tail Kick"):
                out += wear + [(T("fire", "hit", skill), "pull_enemy:%s" % g(roll))]
            for event in ("kill", "cast", "taken", "tick", "chest", "hit_element", "hits", ""):
                out += wear + [(T("fire", event, "Frenzy"), "none")]
        # worn, nothing rolled yet; the axe in the bag; another owner's axe; not worn
        out += clear + [(T("wears", OWNER), None), (T("fire", "hit", "Frenzy"), "none")]
        out += clear + [(T("rolled", OWNER, "", "pull_enemy", 22), None), (T("fire", "hit", "Frenzy"), "none")]
        out += clear + [(T("wears", "Other Axe"), None), (T("rolled", "Other Axe", "", "pull_enemy", 22), None), (T("fire", "hit", "Frenzy"), "none")]
        # reach: the enemy within 40 yards, the end inclusive; nothing past it, behind the wearer or with no reach
        for distance, yards, want in ((0, 40, 1), (10, 40, 1), (39.99, 40, 1), (40, 40, 1), (40.01, 40, 0), (100, 40, 0), (-1, 40, 0), (10, 0, 0), (10, -5, 0), (0, 0, 0)):
            out.append((T("ready", distance, yards, 100000, 0, 0, COOLDOWN), str(want)))
        # the cooldown: nothing before 6 seconds, the end inclusive; a clock that went back does not free it; none before the first drag
        for now, want in ((100000, 0), (100001, 0), (100000 + cool - 1, 0), (100000 + cool, 1), (200000, 1)):
            out.append((T("ready", 10, 40, now, 1, 100000, COOLDOWN), str(want)))
        # across the clock's wrap (a uint32 of ms, about 49.7 days): a drag just below 2^32 is 796 ms old at now 500, and 6 seconds old at 5704; a stale drag (30 days) is old
        for now, last, want in ((500, 4294967000, 0), (5703, 4294967000, 0), (5704, 4294967000, 1), (20000, 4294967000, 1), (1000 + 2592000000, 1000, 1), (99999, 100000, 1)):
            out.append((T("ready", 10, 40, now, 1, last, COOLDOWN), str(want)))
        out.append((T("ready", 10, 40, 100000, 0, 99999999, COOLDOWN), "1"))
        out.append((T("ready", 10, 40, 100000, 0, 100000, COOLDOWN), "1"))   # no drag yet: a stamp that happens to be now is nothing
        out += [(T("ready", 10, 40, 100000, 1, 100000, 0), "1"), (T("ready", 10, 40, 100000, 1, 100000, -3), "1"), (T("ready", 41, 40, 200000, 1, 100000, COOLDOWN), "0")]
        # the hook's damage: the minimum plus the delta by a draw from 0 to 1 (clamped), nothing below nothing
        for minimum, delta, unit, want in ((DAMAGE, DAMAGE, 0, DAMAGE), (DAMAGE, DAMAGE, 1, 2 * DAMAGE), (DAMAGE, DAMAGE, 0.5, 1.5 * DAMAGE), (DAMAGE, DAMAGE, 2, 2 * DAMAGE),
                                           (DAMAGE, DAMAGE, -1, DAMAGE), (-5, 10, 1, 10), (-5, 10, 0, 0), (DAMAGE, -3, 1, DAMAGE), (0, 0, 0.5, 0)):
            out.append((T("damage", minimum, delta, unit), g(want)))
        # the chance: the item's, scaled by the proc coefficient of the hit that struck (none: never), falling when the draw is below it
        for chance, coefficient, draw, want in ((20, "1", 19.99, 1), (20, "1", 20, 0), (25, "1", 24.99, 1), (25, "1", 25, 0), (25, "0.13", 3.24, 1), (25, "0.13", 3.25, 0), (20, "0.5", 9.99, 1),
                                                (20, "0.5", 10, 0), (20, "-", 0, 0), (20, "0", 0, 0), (0, "1", 0, 0), (-5, "1", 0, 0)):
            out.append((T("chance", chance, coefficient, draw), str(want)))
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
        self.assertGreater(len(want), 60)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(6, len(rows))
        want, _ = self.drive(real, rows, "want")
        effect = [r for r in rows if r[2] == "effect"][0]
        others = [r for r in rows if r[2] != "effect"]
        row_mutants = {
            "another_event": [effect[:12] + ("kill",) + effect[13:]] + others,
            "named_skills_only": [effect[:13] + ("Frenzy",) + effect[14:]] + others,
            "no_row": others,
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        for name, (old, new) in {
            "reach_end_is_exclusive": ("distance < 0 || distance > yards", "distance < 0 || distance >= yards"),
            "no_reach_limit": ("distance < 0 || distance > yards", "distance < 0"),
            "negative_distance_counts": ("distance < 0 || distance > yards", "distance > yards"),
            "no_reach_is_a_drag": ("if (yards <= 0 || ", "if ("),
            "cooldown_end_is_exclusive": ("(now - last) >= static_cast<std::uint32_t>(std::max(0.0, cooldownSeconds)", "(now - last) > static_cast<std::uint32_t>(std::max(0.0, cooldownSeconds)"),
            "no_cooldown": ("return (now - last) >= static_cast<std::uint32_t>(std::max(0.0, cooldownSeconds) * 1000.0);", "return true;"),
            "the_cooldown_is_in_seconds": ("(std::max(0.0, cooldownSeconds) * 1000.0)", "(std::max(0.0, cooldownSeconds))"),
            "the_wrap_blocks_the_drag": ("return (now - last) >= static_cast<std::uint32_t>(std::max(0.0, cooldownSeconds)", "return now >= last && (now - last) >= static_cast<std::uint32_t>(std::max(0.0, cooldownSeconds)"),
            "the_damage_ignores_the_draw": ("std::max(0.0, delta) * std::min(1.0, std::max(0.0, unit))", "std::max(0.0, delta)"),
            "the_damage_has_no_delta": ("std::max(0.0, delta) * std::min(1.0, std::max(0.0, unit));", "0.0;"),
            "the_draw_is_not_clamped_in_the_damage": ("std::min(1.0, std::max(0.0, unit));\n    }\n\n    // N-FEAR", "unit;\n    }\n\n    // N-FEAR") if False else ("std::max(0.0, minimum) + std::max(0.0, delta)", "minimum + std::max(0.0, delta)"),
            "the_first_drag_waits": ("        if (!dragged)\n            return true;\n", ""),
        }.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply")
                _, got = self.drive(real.replace(old, new, 1), rows, name)
                self.assertNotEqual(want, got, name + " survived")


def drag_failures(effects):
    """What is wrong with the drag executor in `effects` ([] when it is right)."""
    flat = re.sub(r"\s+", " ", effects)
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    start = flat.find("void Drag(Player* player, Unit* target, ItemPower::Row const& row, double chancePct, double coefficient) {")
    need("the executor exists", start >= 0)
    end = flat.find("// Bul-Kathos", start)
    body = flat[start:end] if start >= 0 and end > start else ""
    need("an enemy that is not alive, the wearer itself and a dead wearer are left alone",
         "if (!player->IsAlive() || !target || target == player || !target->IsAlive()) return;" in body)
    for stat in ("pull_yards", "pull_stun_seconds", "pull_cooldown_seconds"):
        need("the %s row is the item's" % stat, 'ItemPower::OwnerNumber(Data().rows, row.owner, "player", "%s")' % stat in body)
    need("the cooldown has its own key, apart from the event's", 'std::string const key = row.owner + "|drag";' in body)
    for stat in ("pull_damage", "pull_damage_delta"):
        need("the %s row is the item's" % stat, 'ItemPower::OwnerNumber(Data().rows, row.owner, "player", "%s")' % stat in body)
    need("the hook's damage is dealt as the wearer's under the stock record, absolute",
         "hit.total = ItemPower::DragDamage(damage, delta, rand_norm()); if (hit.total > 0) Combat::DealHit(player, target, DragRecord, hit, true);" in body)
    need("a target the damage killed is not pulled", "if (!target->IsAlive()) return; Abilities::Pull(" in body)
    need("the stun is stretched by StunFactor", "Control(player, target, ItemPower::FreezeHold, stun * ItemPowers::StunFactor(player));" in body)
    need("reach and cooldown are judged first, then the chance, under the lock",
         "std::lock_guard<std::mutex> lock(mutex);" in body and
         "if (!ItemPower::DragReady(player->GetExactDist(target), yards, now, last != fired.end(), last != fired.end() ? last->second : 0, cooldown) || "
         "!Proc::Rolls(coefficient, chancePct, [](float pct) { return roll_chance_f(pct); })) return;" in body)
    need("the cooldown starts only for a drag", "return; fired[key] = now; }" in body)
    need("the enemy is dragged to the wearer", "Abilities::Pull(target, player->GetPosition());" in body)
    need("the damage comes before the pull and the pull before the stun",
         0 <= body.find("DealHit(player, target, DragRecord") < body.find("Abilities::Pull(") < body.find("Control(player, target, ItemPower::FreezeHold") if "Abilities::Pull(" in body else False)
    need("the executor's branch is the pull_enemy stat with its target and row, at the hit's coefficient",
         'else if (one.stat == "pull_enemy" && target && one.row) Drag(player, target, *one.row, one.value, scale);' in flat)
    return wrong


class Hooks(unittest.TestCase):
    def test_the_drag_executor(self):
        self.assertEqual([], drag_failures(EFFECTS.read_text(encoding="utf-8")))

    def test_the_effects_file_includes_the_pull(self):
        self.assertIn('#include "dc_movement_effects.h"', EFFECTS.read_text(encoding="utf-8"))

    def test_the_source_guards_fail_their_mutants(self):
        real = EFFECTS.read_text(encoding="utf-8")
        mutants = {
            "a_corpse_is_dragged": ("|| target == player || !target->IsAlive())", "|| target == player)"),
            "no_yards_row": ('"player", "pull_yards")', '"player", "pull_range")'),
            "no_stun_row": ('"player", "pull_stun_seconds")', '"player", "pull_stun")'),
            "no_cooldown_row": ('"player", "pull_cooldown_seconds")', '"player", "pull_cooldown")'),
            "the_events_key": ('row.owner + "|drag"', "ItemPower::FireKey(row)"),
            "no_reach_check": ("!ItemPower::DragReady(player->GetExactDist(target), yards, now, last != fired.end(), last != fired.end() ? last->second : 0, cooldown) ||", ""),
            "the_chance_ignores_the_coefficient": ("DragReady(player->GetExactDist(target), yards, now, last != fired.end(), last != fired.end() ? last->second : 0, cooldown) ||\n                    !Proc::Rolls(coefficient, chancePct,", "DragReady(player->GetExactDist(target), yards, now, last != fired.end(), last != fired.end() ? last->second : 0, cooldown) ||\n                    !Proc::Rolls(1.0, chancePct,"),
            "a_failed_roll_starts_the_cooldown": ("return; fired[key] = now;", "fired[key] = now; return;") if False else ("                    return;\n                fired[key] = now;\n            }\n            // The hook's damage first", "                    fired[key] = now;\n                    return;\n            }\n            // The hook's damage first"),
            "never_pulled": ("Abilities::Pull(target, player->GetPosition());", "Abilities::Pull(target, target->GetPosition());"),
            "knocked_away_instead": ("Abilities::Pull(target, player->GetPosition());", "Abilities::Knock(player, target, 5.0);"),
            "no_stun": ("Control(player, target, ItemPower::FreezeHold, stun * ItemPowers::StunFactor(player));", "Control(player, target, ItemPower::FreezeHold, 0.0);"),
            "no_stun_factor": ("stun * ItemPowers::StunFactor(player)", "stun"),
            "no_damage_row": ('"player", "pull_damage")', '"player", "pull_dmg")'),
            "no_delta_row": ('"player", "pull_damage_delta")', '"player", "pull_dmg_delta")'),
            "no_damage_dealt": ("Combat::DealHit(player, target, DragRecord, hit, true);", ";"),
            "damage_without_the_draw": ("ItemPower::DragDamage(damage, delta, rand_norm())", "ItemPower::DragDamage(damage, delta, 0.0)"),
            "a_dead_target_is_pulled": ("if (!target->IsAlive())\n                return;\n            Abilities::Pull(", "Abilities::Pull("),
            "not_dispatched": ('else if (one.stat == "pull_enemy" && target && one.row)', 'else if (one.stat == "pull_enemies" && target && one.row)'),
            "ignores_the_hit_coefficient": ("Drag(player, target, *one.row, one.value, scale);", "Drag(player, target, *one.row, one.value, 1.0);"),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply")
                self.assertNotEqual([], drag_failures(real.replace(old, new, 1)), name + " survived")


if __name__ == "__main__":
    unittest.main()
