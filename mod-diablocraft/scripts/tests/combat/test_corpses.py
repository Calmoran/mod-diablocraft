"""The shared corpses: the records a kill leaves for a player's skills (src/combat/dc_corpses_math.h, dc_corpses.h and .cpp).

What this proves, and how:

  * **The rules that need no core type.** tests/corpses/harness.cpp compiles the real dc_corpses_math.h: a monster leaves a
    corpse and a player or a player's pet does not; a corpse is in reach at the edge of the radius and not past it, along
    the ground; past the cap the oldest corpse goes and a cap or a lifetime of nothing keeps none; a corpse is gone at its
    lifetime; a take is nearest first, the older of a tie first, up to the maximum, and out of the pile. A corpse is the
    dead body (diablocraft-cuqa4, the designer's q-1021-34 b): the record holds the body's guid, a corpse that expires, is pushed
    out by the cap or is kept none hands its body back once, a taken corpse hands it to the caller and not also back, a
    claim whose body is gone is dropped without handing anything back, and a corpse a skill made (no body) is never
    pruned. Used at will (diablocraft-im7mr.22): the window ends at its moment, a count finds at least the phantoms, a take is topped up to them and to its
    own maximum, never without the window. Thirty-four mutations planted in a scratch copy must each make it fail.
  * **The pile does what the rules say, in the core's terms.** The text of dc_corpses.cpp: the owner is the key, the two
    combat tunables are read for the cap and the lifetime, the owner's logout and map change empty the pile, the
    listeners of OnConsumed hear a take before it returns, and the body goes: a taken, expired or pushed-out corpse
    removes its dead body the way the core's decay does, unless another player's pile still holds a claim on it, a
    claim on a body that is gone is dropped before every call, and a once-a-second sweep expires the rest.
  * **The two numbers are the designer's.** combat.csv has corpse_cap at 30 and corpse_lifetime_seconds at 60, his answer on q-1021-35 (a),
    in his column with no D3 number, and the rendered migration carries both rows with those values.
  * **It names no class.** The shared folder holds no class name (AGENTS.md R1).

What it does not prove: the corpses on a running server, and the look of one (a card for the designer).

    python mod-diablocraft/scripts/tests/combat/test_corpses.py
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
HEADER = "src/combat/dc_corpses_math.h"
SOURCES = [HEADER, "tests/corpses/harness.cpp"]
CODE = MODULE / "src/combat/dc_corpses.cpp"
API = MODULE / "src/combat/dc_corpses.h"
SHEET = MODULE / "data/tunables/combat.csv"


def squeeze(text):
    return re.sub(r"\s+", " ", text)


def scratch_tree(mutate=None):
    files = {source[len("src/"):]: (MODULE / source).read_text(encoding="utf-8")
             for source in SOURCES if source.startswith("src/")}
    if mutate:
        path, old, new = mutate
        key = path[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([MODULE / "tests/corpses/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    return harness_env.run([str(binary)], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 30, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("a player leaves a corpse", (HEADER, "return victim.creature && !victim.controlledByPlayer;", "return !victim.controlledByPlayer;")),
            ("a pet leaves a corpse", (HEADER, "return victim.creature && !victim.controlledByPlayer;", "return victim.creature;")),
            ("the edge of the reach is out", (HEADER, "GroundDistance(corpse.spot, x, y) <= radius", "GroundDistance(corpse.spot, x, y) < radius")),
            ("the height counts", (HEADER, "return std::hypot(double(spot.x) - x, double(spot.y) - y);", "return std::hypot(std::hypot(double(spot.x) - x, double(spot.y) - y), double(spot.z));")),
            ("past the cap the newest goes", (HEADER, "corpses_.erase(corpses_.begin(), pushedOut);", "corpses_.pop_back();")),
            ("the cap is one more", (HEADER, "if (corpses_.size() > cap)", "if (corpses_.size() > cap + 1)")),
            ("a cap of nothing keeps a corpse", (HEADER, "if (cap == 0 || lifetimeMs == 0)", "if (lifetimeMs == 0)")),
            ("a lifetime of nothing keeps a corpse", (HEADER, "if (cap == 0 || lifetimeMs == 0)", "if (cap == 0)")),
            ("a corpse is gone a millisecond early", (HEADER, "nowMs - corpse.leftAtMs >= lifetimeMs", "nowMs - corpse.leftAtMs + 1 >= lifetimeMs")),
            ("a corpse lives a millisecond over", (HEADER, "nowMs - corpse.leftAtMs >= lifetimeMs", "nowMs - corpse.leftAtMs > lifetimeMs")),
            ("a clock behind the corpse expires it", (HEADER, "nowMs >= corpse.leftAtMs && nowMs - corpse.leftAtMs >= lifetimeMs", "nowMs - corpse.leftAtMs >= lifetimeMs")),
            ("the farthest corpse is taken first", (HEADER, "GroundDistance(corpses_[a].spot, x, y) < GroundDistance(corpses_[b].spot, x, y)", "GroundDistance(corpses_[a].spot, x, y) > GroundDistance(corpses_[b].spot, x, y)")),
            ("a tie goes to the newer", (HEADER, "std::stable_sort(near.begin(), near.end(),", "std::stable_sort(near.rbegin(), near.rend(),")),
            ("the maximum is ignored", (HEADER, "if (near.size() > max)", "if (false)")),
            ("a take leaves the corpse", (HEADER, "corpses_.erase(corpses_.begin() + std::ptrdiff_t(i));", "(void)i;")),
            ("a take reaches past the radius", (HEADER, "if (GroundDistance(corpses_[i].spot, x, y) <= radius)", "if (true)")),
            ("the window never ends", (HEADER, "return nowMs < untilMs;", "return true;")),
            ("the window ends a millisecond late", (HEADER, "return nowMs < untilMs;", "return nowMs <= untilMs;")),
            ("a count at will finds the fewer", (HEADER, "return atWill ? std::max(real, phantoms) : real;", "return atWill ? std::min(real, phantoms) : real;")),
            ("a count finds phantoms with no window", (HEADER, "return atWill ? std::max(real, phantoms) : real;", "return std::max(real, phantoms);")),
            ("a take is topped up with no window", (HEADER, "return atWill && wanted > taken ? wanted - taken : 0;", "return wanted > taken ? wanted - taken : 0;")),
            ("a take is topped up past its maximum", (HEADER, "std::size_t const wanted = std::min(max, phantoms);", "std::size_t const wanted = phantoms;")),
            ("a take is topped up past the phantoms", (HEADER, "std::size_t const wanted = std::min(max, phantoms);", "std::size_t const wanted = max;")),
            ("a take that found enough is topped up", (HEADER, "wanted > taken ? wanted - taken : 0", "wanted > 0 ? wanted : 0")),
            ("a new corpse keeps the expired", (HEADER, "Expire(nowMs, lifetimeMs);\n            if (cap == 0", "if (cap == 0")),
            ("a corpse pushed out by the cap keeps its body", (HEADER, "Release(corpses_.begin(), pushedOut);", "")),
            ("a skill-made corpse always takes the stand-in", (HEADER, "return skillBody ? skillBody : standIn;", "return standIn;")),
            ("a skill-made corpse never takes the stand-in", (HEADER, "return skillBody ? skillBody : standIn;", "return skillBody;")),
            ("a pile kept none keeps the bodies", (HEADER, "Release(corpses_.begin(), corpses_.end());", "")),
            ("an expired corpse keeps its body", (HEADER, "if (expired(corpse))\n                    released_.push_back(corpse.spot);", "if (expired(corpse))\n                    (void)corpse;")),
            ("a take also releases", (HEADER, "for (std::size_t i : near)\n                taken.push_back(corpses_[i].spot);", "for (std::size_t i : near)\n            {\n                taken.push_back(corpses_[i].spot);\n                released_.push_back(corpses_[i].spot);\n            }")),
            ("a prune drops a corpse with no body", (HEADER, "return corpse.spot.body != 0 && gone(corpse.spot);", "return gone(corpse.spot);")),
            ("a prune hands the bodies back", (HEADER, "void Prune(Gone gone)\n        {\n", "void Prune(Gone gone)\n        {\n            for (Corpse const& corpse : corpses_)\n                if (corpse.spot.body != 0 && gone(corpse.spot))\n                    released_.push_back(corpse.spot);\n")),
            ("no body is held when it is nothing", (HEADER, "return body != 0 && std::any_of(", "return std::any_of(")),
            ("the bodies include a corpse with none", (HEADER, "if (corpse.spot.body != 0)\n                    out.push_back(corpse.spot.body);", "out.push_back(corpse.spot.body);")),
            ("a sweep expires nothing", (HEADER, "void Sweep(std::uint64_t nowMs, std::uint64_t lifetimeMs)\n        {\n            Expire(nowMs, lifetimeMs);", "void Sweep(std::uint64_t nowMs, std::uint64_t lifetimeMs)\n        {\n            (void)nowMs;\n            (void)lifetimeMs;")),
        ]
        for label, mutation in mutations:
            with self.subTest(label):
                try:
                    tree = scratch_tree(mutation)
                except AssertionError as error:
                    self.fail(str(error))
                out = build_and_run(tree)
                self.assertNotEqual(out.returncode, 0, f"{label} was not caught: {out.stdout[-500:]}")


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))

    def test_the_pile_is_the_owners_and_the_numbers_are_the_combat_tunables(self):
        self.assertIn("return owner->GetGUID().GetRawValue();", self.code)
        self.assertIn('DC::Tunables::Get("combat", "corpse_cap")', self.code)
        self.assertIn('DC::Tunables::Get("combat", "corpse_lifetime_seconds")', self.code)
        self.assertIn("seconds * 1000", self.code)
        # Every pile call reads both: a lowered cap or lifetime applies to corpses already lying.
        self.assertIn("Now(), Cap(), LifetimeMs())", self.code)
        self.assertEqual(self.code.count("Now(), LifetimeMs())"), 2)

    def test_a_corpse_goes_with_the_floor_and_the_login(self):
        floors = self.code[self.code.index("class Floors"):self.code.index("class Commands")]
        self.assertIn("PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_MAP_CHANGED", floors)
        for hook in ("void OnPlayerLogout(Player* player) override { Forget(player); }",
                     "void OnPlayerMapChanged(Player* player) override { Forget(player); }"):
            self.assertIn(hook, floors)
        self.assertIn("piles.erase(Key(player));", self.code)

    def test_a_kill_corpse_is_the_monsters_stock_body_and_a_skill_corpse_gets_one_made(self):
        # No loot and no credit of its own anywhere: a kill's body is the monster's, found by guid; a skill's is summoned and killed
        # by itself (the designer, q-1021-63 b), and only there.
        for text in ("SummonGameObject", "DropCorpseLoot", "AddItem", "StoreNewItem", "KilledMonsterCredit",
                     "RewardPlayerAndGroupAtKill"):
            self.assertNotIn(text, self.code)
        self.assertEqual(self.code.count("SummonCreature"), 1)
        made = self.code[self.code.index("std::uint64_t MakeBody("):self.code.index("void RemoveBody(")]
        self.assertIn("owner->SummonCreature(entry, at, TEMPSUMMON_MANUAL_DESPAWN);", made)
        self.assertIn("body->SetDisplayId(display); body->SetNativeDisplayId(display);", made)
        self.assertIn("making = guid; body->KillSelf(false); making = 0;", made)
        self.assertIn("if (!entry) return 0;", made)
        # The corpse is left with the body's guid, the entry as the skill gave it, the body's creature from the rule.
        leave = self.code[self.code.index("bool LeaveMade("):self.code.index("std::uint64_t BodyBeingMade()")]
        self.assertIn("MakeBody(owner, at, BodyEntry(skillBody, StandIn()), skillBody ? 0 : LookOf(entry))", leave)
        # The corpse's own entry is only what the record says and where the look comes from: it is never summoned (a dead
        # monster's entry would run its death abilities and scripts again; Reviewer epdfp, diablocraft-y7597).
        self.assertNotRegex(leave, r"MakeBody\(owner, at, (BodyEntry\()?entry\b")
        self.assertNotRegex(leave, r"BodyEntry\(entry\b")
        self.assertIn("if (Leave(owner, at, entry, body)) return true;", leave)
        # A corpse not kept leaves no body behind.
        self.assertIn("RemoveBody(made);", leave)
        self.assertIn('DC::Tunables::Get("combat", "skill_corpse_body_entry")', self.code)
        self.assertIn("std::uint64_t BodyBeingMade() { return making; }", self.code)
        # The one thing the piece asks of the loot folder: whether the body still holds drops.
        self.assertEqual(re.findall(r"Loot::\w+", self.code), ["Loot::CorpseHoldsRows"])
        self.assertIn("ObjectAccessor::GetCreature(context, ObjectGuid(body))", self.code)
        # A body lies while it is a corpse (just died or lying) in this map; alive again or removed is gone.
        self.assertIn("creature->getDeathState() == DeathState::Corpse || creature->getDeathState() == DeathState::JustDied", self.code)

    def test_a_used_expired_or_pushed_out_corpse_takes_its_body_unless_another_pile_holds_it(self):
        remove = self.code[self.code.index("void RemoveUnclaimed("):self.code.index("class Sweeper")]
        self.assertIn("entry.second.Holds(spot.body)", remove)
        self.assertIn("RemoveBody(body);", remove)
        # A kill's body goes as the core's decay takes it (no new spawn time); a body made for a skill's corpse is unsummoned.
        gone = self.code[self.code.index("void RemoveBody("):self.code.index("std::uint64_t Key(")]
        self.assertIn("body->RemoveCorpse(false);", gone)
        self.assertIn("summon->UnSummon();", gone)
        # A body that still holds somebody's unlooted drops stays (the rows are on the body and go with it).
        self.assertIn("if (body->IsInWorld() && !Loot::CorpseHoldsRows(body))", remove)
        self.assertIn('#include "../loot/dc_corpse_loot.h"', self.code)
        self.assertIn("if (spot.body == 0) continue;", remove)  # a corpse a skill made has no body
        # Leave, Count and Consume all settle what they released; Consume adds the taken corpses.
        self.assertEqual(self.code.count("RemoveUnclaimed(owner, left);"), 3)
        self.assertIn("left.insert(left.end(), taken.begin(), taken.end());", self.code)
        # Leaving a floor leaves the bodies to the core's decay.
        floors = self.code[self.code.index("void Forget("):self.code.index("bool BodyLies(")]
        self.assertNotIn("RemoveCorpse", floors)

    def test_a_window_of_corpse_skills_used_at_will_tops_up_a_take_and_a_count(self):
        self.assertIn("void AtWill(Player* owner, std::uint64_t untilMs, std::size_t phantoms)", squeeze(API.read_text(encoding="utf-8")))
        self.assertIn("count = CountAtWill(count, phantoms > 0, phantoms);", self.code)
        self.assertIn("PhantomsFor(taken.size(), max, phantoms > 0, phantoms)", self.code)
        # The passives hear only the real corpses taken: the phantoms are added after the listeners.
        consume = self.code[self.code.index("std::vector<Spot> Consume("):self.code.index("void AtWill(")]
        self.assertLess(consume.index("listener(owner, taken)"), consume.index("taken.push_back(made)"))
        self.assertIn("windows.erase(Key(player));", self.code)  # leaving the floor or the game ends the window

    def test_a_claim_on_a_body_that_is_gone_is_dropped_before_every_call(self):
        for call in ("bool Leave(", "std::size_t Count(", "std::vector<Spot> Consume("):
            start = self.code.index(call)
            self.assertIn("Tidy(owner);", self.code[start:start + 400], call)
        self.assertIn("it->second.Prune(", self.code)

    def test_a_sweep_expires_the_corpses_once_a_second_whether_or_not_anyone_asks(self):
        sweeper = self.code[self.code.index("class Sweeper"):self.code.index("class Floors")]
        self.assertIn("WORLDHOOK_ON_UPDATE", sweeper)
        self.assertIn("static constexpr std::uint32_t SweepMs = 1000;", sweeper)
        self.assertIn("entry.second.Sweep(now, lifetime);", sweeper)
        self.assertIn("RemoveUnclaimed(player, left);", sweeper)
        self.assertIn("new Sweeper();", self.code)

    def test_a_take_tells_the_passives_before_it_returns(self):
        consume = self.code[self.code.index("std::vector<Spot> Consume("):self.code.index("void OnConsumed(")]
        self.assertLess(consume.index("pilesMutex"), consume.index("listener(owner, taken)"))
        self.assertIn("if (!taken.empty())", consume)
        self.assertIn("return taken;", consume)
        # The listeners run outside the pile's lock, so a passive may leave or take a corpse in turn.
        self.assertIn("RemoveUnclaimed(owner, left); if (!taken.empty()) for (Listener const& listener : listeners) listener(owner, taken);", consume)

    def test_the_api_names_the_owner_the_place_and_the_reach(self):
        api = squeeze(API.read_text(encoding="utf-8"))
        for line in ("bool Leave(Player* owner, Position const& at, std::uint32_t entry, std::uint64_t body = 0);",
                     "std::size_t Count(Player* owner, Position const& center, float radius);",
                     "std::vector<Spot> Consume(Player* owner, Position const& center, float radius, std::size_t max);",
                     "using Listener = std::function<void(Player* owner, std::vector<Spot> const& taken)>;",
                     "void OnConsumed(Listener listener);"):
            self.assertIn(line, api)

    def test_the_shared_corpses_name_no_class(self):
        for path in (CODE, API, MODULE / HEADER):
            text = path.read_text(encoding="utf-8")
            for name in ("Crusader", "Barbarian", "Monk", "Wizard", "Necromancer", "Witch Doctor", "Demon Hunter", "Essence"):
                self.assertNotIn(name, text, f"{path.name} names {name}")


class TheTwoNumbersAreAlexs(unittest.TestCase):
    # The designer's answer on card q-1021-35 (a), decisions.md 2026-10-22: a pile of 30, each corpse lasting 60 seconds.
    ANSWERS = {"corpse_cap": ("count", "30"), "corpse_lifetime_seconds": ("seconds", "60")}

    def rows(self):
        with SHEET.open(encoding="utf-8-sig", newline="") as stream:
            return {row["name"]: row for row in csv.DictReader(stream)}

    def test_the_sheet_has_both_with_alexs_values(self):
        rows = self.rows()
        for name, (unit, value) in self.ANSWERS.items():
            self.assertIn(name, rows)
            self.assertEqual(rows[name]["value"], value, f"{name} is the designer's answer on q-1021-35")
            self.assertEqual(rows[name]["d3_value"], "", f"{name}: no source gives a D3 number")
            self.assertEqual(rows[name]["unit"], unit)
            self.assertIn("q-1021-35", rows[name]["notes"])

    def test_the_rendered_migration_carries_both(self):
        state = (MODULE / "data/tunables/current_migration.txt").read_text(encoding="utf-8").strip()
        sql = (MODULE / "data/sql/db-world/updates" / state).read_text(encoding="utf-8")
        for name, (_, value) in self.ANSWERS.items():
            self.assertRegex(sql, r"'combat',\s*'%s',\s*NULL,\s*%s\.0," % (name, value))


if __name__ == "__main__":
    unittest.main()
