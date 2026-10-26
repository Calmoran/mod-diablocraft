"""Security fixes, world lane (docs/briefs/claude-world-security-fixes-brief.md).

G5  crafting `mats`, `mode choose/revive` and the admin `tier` are GM 3.
G8  single salvage refuses an equipped item, as bulk does.
G10 `.dc tierselect` works only in the hub (diablocraft-fjqx; was the obelisk) and honours a cooldown.

The two rules that are pure decisions (`TierChangeAllowed`, `SalvageEligible`)
live in headers the module includes; they are compiled and run here. What is a
fact about which code exists (command levels, which path calls the rule) is
read from source, and every source check is also run against a reverted copy of
the source and must then fail, so a green suite cannot be a check that never
looks.
"""
import re
import shutil
import subprocess
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import crafting_source  # noqa: E402
import harness_env

REPO_ROOT = Path(__file__).resolve().parents[4]
MODULE = REPO_ROOT / "mod-diablocraft"
HARNESS = MODULE / "tests" / "security_world"
# Scratch belongs in the build tree (AGENTS.md), not the system temp.
SCRATCH = REPO_ROOT / "azerothcore-wotlk" / "build" / "_agent-scratch" / "security_world"


def read(path):
    return (MODULE / path).read_text(encoding="utf-8")


def function_body(source, marker):
    start = source.index(marker)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def command_level_problems(crafting, hardcore, difficulty):
    problems = []
    for name, src, entry in (
        ("mats", crafting, '{"mats", Materials, SEC_ADMINISTRATOR, Console::No}'),
        ("mode choose", hardcore, '{"choose", HandleChoose, SEC_ADMINISTRATOR, Console::No}'),
        ("mode revive", hardcore, '{"revive", HandleRevive, SEC_ADMINISTRATOR, Console::Yes}'),
        ("tier", difficulty, '{"tier",HandleTier,SEC_ADMINISTRATOR,Console::No}'),
    ):
        if entry not in src:
            problems.append("%s is not GM 3" % name)
    return problems


def salvage_problems(crafting):
    problems = []
    body = function_body(crafting, "void Salvage(Player* player")
    single = body[: body.index("else")]
    if "Owned(player, guid)" not in single or "SalvageEligible(" not in single:
        problems.append("single salvage does not check SalvageEligible")
    if body.count("SalvageEligible(") < 2:
        problems.append("bulk salvage does not use SalvageEligible")
    return problems


def tier_problems(difficulty):
    problems = []
    if '{"tierselect",HandleChoose,SEC_PLAYER' not in difficulty:
        problems.append("tierselect does not go through HandleChoose")
    choose = function_body(difficulty, "static bool HandleChoose(")
    if "ChooseTier(" not in choose or "SelectTier(" in choose:
        problems.append("HandleChoose must call ChooseTier and not SelectTier")
    gate = function_body(difficulty, "bool ChooseTier(")
    if "bool inHub = DC::World::IsInHub(player);" not in gate:
        problems.append("ChooseTier does not ask DC::World::IsInHub")
    if "if (!TierChangeAllowed(" not in gate or gate.index("TierChangeAllowed(") > gate.index("SelectTier("):
        problems.append("ChooseTier does not check the gate before it selects")
    if "TIER_OBELISK" in difficulty or "910010" in difficulty or "FindNearestGameObject" in gate:
        problems.append("the removed difficulty obelisk 910010 is still looked up")
    if ('uint64 cooldownMs = uint64(std::max(0.0, Tunables::Get("monsters", "tier_change_cooldown_seconds")) * 1000.0);'
            not in gate):
        problems.append("cooldownMs is not the clamped tunable in milliseconds")
    if "TierChangeAllowed(inHub, hasLast, last, uint64(GameTime::GetGameTimeMS().count()), cooldownMs, error)" not in gate:
        problems.append("the gate is not called with inHub and cooldownMs unchanged")
    select = function_body(difficulty, "bool SelectTier(")
    if "if (!PartyMemberReady(DC::World::IsInHub(member), member->IsInCombat(), error)) return false;" not in select:
        problems.append("SelectTier does not ask every online member PartyMemberReady(IsInHub, IsInCombat)")
    if "FindConnectedPlayer(slot.guid)" not in select or "OpenWorld(member" in select:
        problems.append("SelectTier must skip offline members and not test members by OpenWorld")
    if "lastTierChangeMs[" not in gate:
        problems.append("a successful tier change does not stamp the cooldown clock")
    return problems


class SecurityWorldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.crafting = crafting_source.source()
        cls.hardcore = read("src/hardcore/dc_hardcore.cpp")
        cls.difficulty = read("src/difficulty/dc_difficulty.cpp")
        cls.compiler = shutil.which("c++") or shutil.which("g++")
        if not cls.compiler:
            raise unittest.SkipTest("no C++ compiler")
        SCRATCH.mkdir(parents=True, exist_ok=True)

    def build_and_run(self, name, tier_header, salvage_header):
        work = SCRATCH / name
        work.mkdir(parents=True, exist_ok=True)
        (work / "dc_tier_gate.h").write_text(tier_header, encoding="utf-8")
        (work / "dc_salvage_rule.h").write_text(salvage_header, encoding="utf-8")
        binary = work / "gate_harness"
        built = subprocess.run([self.compiler, "-std=c++17", "-O0", "-UNDEBUG", "-I", str(work),
                                str(HARNESS / "gate_harness.cpp"), "-o", str(binary)],
                               capture_output=True, text=True)
        self.assertEqual(built.returncode, 0, built.stderr[-3000:])
        return harness_env.run([str(binary)], capture_output=True, text=True)

    def headers(self):
        return read("src/difficulty/dc_tier_gate.h"), read("src/crafting/dc_salvage_rule.h")

    # -- pure rules, compiled from the module's own headers -----------------

    def test_gate_and_salvage_rules_hold(self):
        run = self.build_and_run("real", *self.headers())
        self.assertEqual((run.returncode, run.stdout.strip()), (0, "ok"), run.stderr[-2000:])

    def test_harness_fails_without_the_hub_check(self):
        tier, salvage = self.headers()
        mutated = tier.replace("if (!inHub)", "if (false)")
        self.assertNotEqual(mutated, tier)
        self.assertNotEqual(self.build_and_run("no_hub", mutated, salvage).returncode, 0)

    def test_harness_fails_with_the_old_obelisk_text(self):
        tier, salvage = self.headers()
        mutated = tier.replace('"Choose difficulty in the hub."', '"Go to the difficulty obelisk to change difficulty."')
        self.assertNotEqual(mutated, tier)
        self.assertNotEqual(self.build_and_run("old_text", mutated, salvage).returncode, 0)

    def test_harness_fails_without_the_cooldown(self):
        tier, salvage = self.headers()
        mutated = tier.replace("nowMs - lastMs < cooldownMs", "false")
        self.assertNotEqual(mutated, tier)
        self.assertNotEqual(self.build_and_run("no_cooldown", mutated, salvage).returncode, 0)

    def test_harness_fails_when_salvage_allows_equipped(self):
        tier, salvage = self.headers()
        mutated = salvage.replace("!equipped && !inTrade", "!inTrade")
        self.assertNotEqual(mutated, salvage)
        self.assertNotEqual(self.build_and_run("equipped", tier, mutated).returncode, 0)

    def test_harness_fails_when_salvage_quality_rule_is_mutated(self):
        # wpt7l.2: a crafted Primal paying Ashes, and a rule that never reaches the quality rows, both go red.
        tier, salvage = self.headers()
        for old, new in (("return !crafted && (", "return (" ),
                         ('qualityTier == "primal"', 'false'),
                         ('qualityTier == "ancient" ||', 'false ||')):
            mutated = salvage.replace(old, new)
            self.assertNotEqual(mutated, salvage, old)
            self.assertNotEqual(self.build_and_run("quality", tier, mutated).returncode, 0, old)

    # -- wiring, read from source, each with its reverted twin --------------

    def test_command_levels(self):
        self.assertEqual(command_level_problems(self.crafting, self.hardcore, self.difficulty), [])

    def test_command_levels_check_fails_when_reverted(self):
        for src_name, before, after in (
            ("crafting", "Materials, SEC_ADMINISTRATOR", "Materials, SEC_GAMEMASTER"),
            ("hardcore", "HandleChoose, SEC_ADMINISTRATOR", "HandleChoose, SEC_GAMEMASTER"),
            ("hardcore", "HandleRevive, SEC_ADMINISTRATOR", "HandleRevive, SEC_GAMEMASTER"),
            ("difficulty", "HandleTier,SEC_ADMINISTRATOR", "HandleTier,SEC_GAMEMASTER"),
        ):
            sources = {"crafting": self.crafting, "hardcore": self.hardcore, "difficulty": self.difficulty}
            self.assertIn(before, sources[src_name])
            sources[src_name] = sources[src_name].replace(before, after)
            self.assertTrue(command_level_problems(**sources), "%s revert went unnoticed" % before)

    def test_salvage_wiring(self):
        self.assertEqual(salvage_problems(self.crafting), [])

    def test_salvage_check_fails_when_reverted(self):
        # the pre-fix single path: Owned() and nothing else
        single = re.sub(r"Need\(SalvageEligible\(single.*?\);\n", "", self.crafting, count=1, flags=re.S)
        self.assertNotEqual(single, self.crafting)
        self.assertTrue(salvage_problems(single))
        # the pre-fix bulk path: the inline test
        bulk = self.crafting.replace("if (SalvageEligible(item->IsEquipped(), item->IsInTrade()))",
                                     "if (!item->IsEquipped() && !item->IsInTrade())")
        self.assertNotEqual(bulk, self.crafting)
        self.assertTrue(salvage_problems(bulk))

    def test_tier_wiring(self):
        self.assertEqual(tier_problems(self.difficulty), [])

    def test_tier_check_fails_when_reverted(self):
        d = self.difficulty
        reverts = (
            d.replace('{"tierselect",HandleChoose,', '{"tierselect",HandleSelect,'),
            d.replace("bool inHub = DC::World::IsInHub(player);",
                      "bool inHub = player->FindNearestGameObject(910010, 30.0f) != nullptr;"),
            d.replace("bool inHub = DC::World::IsInHub(player);", "bool inHub = true;"),
            d.replace("if (!TierChangeAllowed(", "if (false && !TierChangeAllowed("),
            d.replace("lastTierChangeMs[player", "lastTierChangeUnused[player"),
            d.replace("std::mutex stateMutex;\n", "std::mutex stateMutex;\nconstexpr uint32 TIER_OBELISK_ENTRY = 910010;\n"),
            d.replace("cooldownMs, error))", "0, error))"),
            d.replace("uint64(std::max(0.0, Tunables", "uint64(0 * Tunables"),
        )
        for reverted in reverts:
            self.assertNotEqual(reverted, d)
            self.assertTrue(tier_problems(reverted))

    def test_party_rule_wiring_fails_on_the_old_open_world_rule(self):
        d = self.difficulty
        old = d.replace("if (!PartyMemberReady(DC::World::IsInHub(member), member->IsInCombat(), error)) return false;",
                        'if (!OpenWorld(member->FindMap()) || member->IsInCombat()) { error = "All online party members must be outside instances and out of combat."; return false; }')
        self.assertNotEqual(old, d)
        self.assertTrue(tier_problems(old))

    def test_harness_fails_without_the_party_hub_check(self):
        tier, salvage = self.headers()
        mutated = tier.replace("inline bool PartyMemberReady(bool inHub, bool inCombat, std::string& error)\n{\n    if (!inHub)",
                               "inline bool PartyMemberReady(bool inHub, bool inCombat, std::string& error)\n{\n    if (false)")
        self.assertNotEqual(mutated, tier)
        self.assertNotEqual(self.build_and_run("no_party_hub", mutated, salvage).returncode, 0)

    def test_cooldown_tunable_row_exists_and_is_a_non_negative_number(self):
        import csv, io
        rows = [r for r in csv.DictReader(io.StringIO(read("data/tunables/monsters.csv")))
                if r["name"] == "tier_change_cooldown_seconds"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["unit"], "seconds")
        self.assertGreaterEqual(float(rows[0]["value"]), 0.0)

    def test_start_kit_is_not_gated(self):
        # dc_world.cpp picks tier 1 at character creation, before the player is in the hub.
        self.assertIn("Difficulty::SelectTier(player, 1, error)", read("src/common/dc_world.cpp"))


if __name__ == "__main__":
    unittest.main()
