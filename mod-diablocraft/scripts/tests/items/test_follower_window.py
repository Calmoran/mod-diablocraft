"""The Follower window's server half: the records it sends, the Damage and Toughness it shows, the route and the push.

What runs: tests/follower_window/harness.cpp compiles the real src/items/dc_follower_window.h, dc_follower_gear_rule.h and
src/stats/dc_sheet_summary.h with no core and drives them (the player's summary unchanged against its pre-split formula over
2000 sheets; a follower's Damage and Toughness moving with each stat its gear can give; the text of every record; the usable
slots), and each rule is killed by a mutant that must turn it red. The labels in docs/contracts/followers.md are checked against
what the header sends. What does not run: the route, the push and the commands need a Player, a Map and a database, so source
guards pin that the C++ uses the one formula, registers the prefix the contract names, reads the budget rows that exist, and
answers each verb with the call its command runs. The tooltips and the client are the UI lane's.
"""
import csv
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
HARNESS = MODULE / "tests/follower_window/harness.cpp"
HEADERS = ("items/dc_follower_window.h", "items/dc_follower_gear_rule.h", "stats/dc_sheet_summary.h",
           "combat/dc_weapon_flat.h")
CONTRACT = (REPO / "docs/contracts/followers.md").read_text(encoding="utf-8")
GEAR = (SRC / "items/dc_follower_gear.cpp").read_text(encoding="utf-8")
SCRATCH = harness_env.private_scratch(REPO / "azerothcore-wotlk/build/_agent-scratch/follower_window_test")


def code(text):
    """Source with comments removed, so prose cannot satisfy a wiring check."""
    return "\n".join(line.split("//")[0] for line in text.splitlines()
                     if not line.strip().startswith(("//", "*", "/*")))


def build_and_run(label, replace=None):
    compiler = shutil.which("c++") or shutil.which("g++")
    if not compiler:
        raise unittest.SkipTest("no C++ compiler")
    tree = SCRATCH / label
    shutil.rmtree(tree, ignore_errors=True)
    shutil.copytree(SRC / "common", tree / "src/common")
    for name in HEADERS:
        (tree / "src" / name).parent.mkdir(parents=True, exist_ok=True)
        text = (SRC / name).read_text(encoding="utf-8")
        if replace and replace[0] == name:
            text = text.replace(replace[1], replace[2])
        (tree / "src" / name).write_text(text, encoding="utf-8")
    (tree / "tests/follower_window").mkdir(parents=True)
    shutil.copy(HARNESS, tree / "tests/follower_window/harness.cpp")
    binary = tree / "harness"
    built = subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-I", str(tree / "src"), "-o", str(binary),
                            str(tree / "tests/follower_window/harness.cpp")], capture_output=True, text=True)
    if built.returncode:
        return built.returncode, built.stdout, built.stderr
    ran = harness_env.run([str(binary)], capture_output=True, text=True)
    return ran.returncode, ran.stdout, ran.stderr


class HarnessTests(unittest.TestCase):
    def test_the_records_and_the_summary(self):
        code_, out, err = build_and_run("real")
        self.assertEqual(code_, 0, err[-3000:])
        self.assertIn("compared 2000 sheets", out)
        self.assertIn("follower window OK", out)

    def test_every_detail_label_is_in_the_contract_in_order(self):
        code_, out, err = build_and_run("labels")
        self.assertEqual(code_, 0, err[-2000:])
        rows = [line[len("DETAIL "):].split("|") for line in out.splitlines() if line.startswith("DETAIL ")]
        self.assertEqual(len(rows), 22)
        table = CONTRACT[CONTRACT.index("| group | label | value |"):CONTRACT.index("Value shapes:")]
        position = 0
        for _group, label in rows:
            word = "Damage Increased by Strength" if label.startswith("Damage Increased by ") else label
            found = table.find("`" + word + "`", position)
            self.assertGreaterEqual(found, 0, f"{label!r} is not in the contract's table after the row before it")
            position = found

    def test_each_rule_has_a_mutant_that_turns_it_red(self):
        summary = "stats/dc_sheet_summary.h"
        window = "items/dc_follower_window.h"
        rule = "items/dc_follower_gear_rule.h"
        mutants = {
            "the follower's main stat is not read": (summary, "sheet[in.mainStat]", "sheet[Stat::Strength]"),
            "the owner's damage buckets are dropped": (summary, "out.damage *= in.multiplier;", ""),
            "the flat damage is not averaged in": (summary, "in.averageHit + DC::Combat::FlatDamageAverage(sheet)",
                                                   "in.averageHit"),
            "attacks per second are not counted": (summary, "* critFactor * sheet.attacksPerSecond;", "* critFactor;"),
            "armor does not toughen": (summary, "(1 - sheet.armorDR) * resistFactor", "resistFactor"),
            "resistance does not toughen": (summary, "* resistFactor * (1 - sheet.classDR)", "* (1 - sheet.classDR)"),
            "toughness leaves out life": (summary, "sheet.maxLife / defenseFactor", "1 / defenseFactor"),
            "damage reduction shows the fraction": (window, "Pct(sheet.armorDR * 100)", "Pct(sheet.armorDR)"),
            "arcane and holy show one of them": (window, "(sheet.resistance[Index(Element::Arcane)] + "
                                                         "sheet.resistance[Index(Element::Holy)]) / 2",
                                                 "sheet.resistance[Index(Element::Arcane)]"),
            "the digits are not grouped": (window, "out.insert(out.begin(), ',');", "out.insert(out.begin(), '.');"),
            "a percent has no sign": (window, 'return Fixed(value, 2) + "%";', "return Fixed(value, 2);"),
            "every main stat reads Strength": (window, 'return "Dexterity";', 'return "Strength";'),
            "the header leaves out the level": (window, "std::to_string(view.level)}", '"0"}'),
            "the tiers lose their pick": (window, "view.tiers[tier].pick, view.allSkills", '"", view.allSkills'),
            "all skills is always off": (window, 'view.allSkills ? "1" : "0"', '"0"'),
            "the window's hire request goes through": (window, 'return verb == "hire" ? HireRefusal : std::string_view();',
                                                       "return std::string_view();"),
            "every window request is refused": (window, 'return verb == "hire" ? HireRefusal : std::string_view();',
                                                "return HireRefusal;"),
            "the refusal does not say where to hire": (window, "Talk to the follower in the hub to hire them.",
                                                       "That follower is not available."),
            "an empty slot reads as worn": (window, "std::to_string(slot.entry)", '"1"'),
            "the off-hand beside a two-hander is usable": (rule, "if (slot == Slot::OffHand && held.twoHanded)\n"
                                                                 "            return false;", ""),
            "a slot no kind names is usable": (rule, "return std::any_of(kinds.begin(), kinds.end(),",
                                               "return true || std::any_of(kinds.begin(), kinds.end(),"),
            "the relic slot can be unusable": (rule, "if (slot == Slot::Relic)\n            return true;", ""),
        }
        for name, (header, old, new) in mutants.items():
            with self.subTest(name):
                text = (SRC / header).read_text(encoding="utf-8")
                self.assertEqual(text.count(old), 1, f"the mutant's text is not in {header} once: {old!r}")
                code_, _out, err = build_and_run("mutant", (header, old, new))
                self.assertNotEqual(code_, 0, f"the harness stayed green with: {name}")
                self.assertIn("FAIL", err, f"it failed, but not on a check: {err[-500:]}")
        shutil.rmtree(SCRATCH, ignore_errors=True)


class WiringTests(unittest.TestCase):
    """What needs a Player and a database: read from the code with the comments out."""

    def test_one_formula_for_the_player_and_the_follower(self):
        stats = code((SRC / "stats/dc_stats.cpp").read_text(encoding="utf-8"))
        self.assertIn("return SheetSummaryOf(*found, in);", stats)
        self.assertIn("Stats::SheetSummaryOf(computed.sheet, inputs)", code(GEAR))
        # The crit factor, the defence factor and the resistance factor are written once, in the shared header.
        for name in ("critFactor", "defenseFactor", "resistFactor"):
            holders = [path.name for path in SRC.rglob("*")
                       if path.suffix in (".cpp", ".h") and name in code(path.read_text(encoding="utf-8"))]
            self.assertEqual(holders, ["dc_sheet_summary.h"], (name, holders))

    def test_the_follower_swings_its_own_weapon_and_the_summary_reads_its_stat(self):
        text = code(GEAR)
        view = text[text.index("Window::View ViewOf"):text.index("template<typename Send>")]
        self.assertIn("inputs.mainStat = computed.mainStat;", view)
        self.assertIn("(computed.weapon.min + computed.weapon.max) / 2", view)
        self.assertIn("computed.sheet", view)
        self.assertNotIn("DamageBonus", view)   # a player's buckets are not a follower's
        self.assertNotIn("DamageFactor", view)

    def test_the_route_is_the_contracts(self):
        text = code(GEAR)
        self.assertIn('Bridge::Routes().Add("DCFOLLOWER", {"ui", "follower_burst", "follower_per_second"}, WindowRequest);',
                      text)
        self.assertIn('Bridge::Push(player, "DCFOLLOWER", record)', text)
        verbs = set(re.findall(r'\*verb == "(\w+)"', text))
        self.assertEqual(verbs, {"equip", "unequip", "dismiss", "skill"})
        request = CONTRACT[CONTRACT.index("open <follower>"):CONTRACT.index("`<index>` and `<slot>`")]
        # `hire` is still a request on the wire, and always refused: ruling q-1021-158, hiring is the NPC's talk option.
        for verb in verbs | {"open", "hire"}:
            self.assertIn(verb + " <follower>", request, verb)

    def test_each_verb_runs_the_commands_call(self):
        text = code(GEAR)
        body = text[text.index("void WindowRequest"):text.index("class Commands")]
        self.assertIn("Equip(&player, *follower, std::int32_t(*index), wanted);", body)
        self.assertIn("TakeOff(&player, *follower, *slot);", body)
        self.assertIn("Campaign::Followers::Dismiss(&player);", body)
        # The commands call the same two.
        commands = text[text.index("class Commands"):]
        self.assertIn("Equip(player, Which(who), index, wanted);", commands)
        self.assertIn("TakeOff(player, Which(who), *parsed);", commands)
        # Hiring is the NPC's talk option (creature.cpp), never the window's: the request is refused before any call.
        self.assertNotIn("Followers::Hire(", body)
        self.assertLess(body.index("Window::Refusal(*verb)"), body.index("Equip(&player"))
        request = CONTRACT[CONTRACT.index("hire <follower>"):CONTRACT.index("dismiss <follower>")]
        self.assertIn("refused", request)
        self.assertIn("Talk to the follower in the hub to hire them.", request)

    def test_picks_are_f4s_by_skill_id(self):
        text = code(GEAR)
        body = text[text.index("void WindowRequest"):text.index("class Commands")]
        skill = body[body.index('*verb == "skill"'):]
        skill = skill[:skill.index("SendWindow")]
        self.assertIn("Classes::Follower::PickSkill(&player, *follower, *tier, id)", skill)
        self.assertIn("throw Bridge::Refusal(refusal);", skill)
        # A skill id keeps its hyphens, so the field is read whole and the table matches it; only a-z, 0-9 and - pass.
        self.assertIn("c == '-'", skill)
        self.assertIn("request.Uint(2, 1, 4)", skill)
        view = text[text.index("Window::View ViewOf"):text.index("template<typename Send>")]
        self.assertIn("Classes::Follower::PickOf(player, follower, ++tier)", view)
        # F4's command and the seam are one check: the command prints TryPick's words, the seam returns them.
        header = (SRC / "classes/follower/dc_follower_skills.h").read_text(encoding="utf-8")
        for seam in ("std::string PickOf(Player const* player, unsigned follower, unsigned tier);",
                     "std::string PickSkill(Player* player, unsigned follower, unsigned tier, std::string const& skill);"):
            self.assertIn(seam, header)
        skills = code((SRC / "classes/follower/dc_follower_skills.cpp").read_text(encoding="utf-8"))
        self.assertIn("std::string const refusal = TryPick(player, who, tier, choice);", skills)
        self.assertIn("return TryPick(player, std::to_string(follower), tier, skill);", skills)
        self.assertEqual(skills.count("REPLACE INTO dc_character_follower_skill"), 1)
        # The command's "1" and "2" are not skill ids.
        self.assertIn('if (skill == "1" || skill == "2")', skills)

    def test_the_budget_rows_exist_with_the_windows_numbers(self):
        with (MODULE / "data/tunables/ui.csv").open(encoding="utf-8", newline="") as stream:
            rows = {row["name"]: row for row in csv.DictReader(stream)}
        self.assertEqual((rows["follower_burst"]["value"], rows["follower_per_second"]["value"]), ("10", "5"))
        with (MODULE / "data/tunables/crafting.csv").open(encoding="utf-8", newline="") as stream:
            crafting = {row["name"]: row["value"] for row in csv.DictReader(stream)}
        self.assertEqual((crafting["cube_burst"], crafting["cube_per_second"]), ("10", "5"))
        name = (MODULE / "data/tunables/current_migration.txt").read_text(encoding="utf-8").strip()
        migration = (MODULE / "data/sql/db-world/updates" / name).read_text(encoding="utf-8")
        self.assertIn("('ui', 'follower_burst', NULL, 10.0,", migration)
        self.assertIn("('ui', 'follower_per_second', NULL, 5.0,", migration)

    def test_the_hello_pushes_the_window_and_the_prefix_is_listed(self):
        creature = code((SRC / "campaign/dc_follower_creature.cpp").read_text(encoding="utf-8"))
        self.assertIn("Items::FollowerGear::OpenWindow(player, unsigned(row->id));", creature)
        self.assertIn("void OpenWindow(Player* player, unsigned follower);",
                      (SRC / "items/dc_items.h").read_text(encoding="utf-8"))
        bridge = (REPO / "docs/contracts/window-bridge.md").read_text(encoding="utf-8")
        self.assertIn("`DCFOLLOWER`", bridge)

    def test_every_record_letter_the_header_sends_is_in_the_contract(self):
        header = (SRC / "items/dc_follower_window.h").read_text(encoding="utf-8")
        sent = set(re.findall(r'\{"([WAEGK])"', header))
        self.assertEqual(sent, {"W", "A", "G", "K", "E"})
        for letter in sent | {"D", "X"}:
            self.assertRegex(CONTRACT, rf"(?m)^{letter}(\||\s)", letter)


if __name__ == "__main__":
    unittest.main(verbosity=2)
