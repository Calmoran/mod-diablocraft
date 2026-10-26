"""The followers' companion rules and rows (diablocraft-gh1c1.3).

What runs: the rules header src/campaign/dc_follower_rules.h compiled alone and driven with the values parsed out of
data/d3/followers_rules.csv (so a changed sheet is a changed test); the generator's own validation; its SQL applied to the
fixture mysqld's copy of the world. What does not: the AI, the gossip and the summon need a Map and a Player, so the
source guards below pin that the C++ reads the same rule names, tables and script name the sheets and migrations write.
Each rule of the header is killed by a mutant that must turn the harness red.
"""
import csv
import hashlib
import math
import re
import shutil
import subprocess
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_followers as gen
import harness_env

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SCRATCH = harness_env.private_scratch(REPO / "azerothcore-wotlk/build/_agent-scratch/followers_test")
SRC = MODULE / "src/campaign"
HEADER = SRC / "dc_follower_rules.h"
HARNESS = MODULE / "tests/followers/harness.cpp"


def sheet(name):
    with (MODULE / "data/d3" / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def rule_args():
    values = {r["rule"]: r["value"] for r in sheet("followers_rules.csv")}
    return [values[name] for name in gen.RULES]


def build_and_run(header_dir, label):
    compiler = shutil.which("c++") or shutil.which("g++")
    if not compiler:
        raise unittest.SkipTest("no C++ compiler")
    SCRATCH.mkdir(parents=True, exist_ok=True)
    binary = SCRATCH / f"harness_{label}"
    built = subprocess.run([compiler, "-std=c++17", "-I", str(header_dir), "-o", str(binary), str(HARNESS)],
                           capture_output=True, text=True)
    if built.returncode != 0:
        return built.returncode, built.stderr
    ran = harness_env.run([str(binary)] + rule_args(), capture_output=True, text=True)
    return ran.returncode, ran.stderr


class RulesTests(unittest.TestCase):
    def test_rules_on_the_sheets_values(self):
        code, err = build_and_run(SRC, "real")
        self.assertEqual(code, 0, err[-3000:])

    def test_each_rule_has_a_mutant_that_turns_it_red(self):
        original = HEADER.read_text(encoding="utf-8")
        mutants = {
            "the party rule leaves one step late": ("clock.partyMs >= rules.partyLeaveMs", "clock.partyMs > rules.partyLeaveMs"),
            "a follower not out comes to a party": ("if (!now.out || clock.partyMs", "if (clock.partyMs"),
            "the player's fall starts no timer": ("                clock.reviveLeftMs = rules.reviveMs;\n            }\n            Countdown",
                                                  "            }\n            Countdown"),
            "a fallen follower is back at once": ("clock.reviveLeftMs = rules.reviveMs;\n    }\n\n    // One step",
                                                  "(void)rules;\n    }\n\n    // One step"),
            "exactly at the yards is left behind": ("if (!(distance > rules.catchUpYards))", "if (!(distance >= rules.catchUpYards))"),
            "outside the hub talking hires": ("return inHub && follower != Id::None && hired != follower;",
                                              "return follower != Id::None && hired != follower;"),
            "the hired follower offers Hire again": ("return inHub && follower != Id::None && hired != follower;",
                                                     "return inHub && follower != Id::None;"),
            "no follower offers Hire": ("return inHub && follower != Id::None && hired != follower;",
                                        "return inHub && hired != follower;"),
            "the jump never starts the count over": ("        farMs = 0;\n        return true;", "        return true;"),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(name):
                self.assertEqual(original.count(old), 1, f"the mutant's text is not in the header once: {old!r}")
                folder = SCRATCH / "mutant"
                shutil.rmtree(folder, ignore_errors=True)
                folder.mkdir(parents=True)
                (folder / HEADER.name).write_text(original.replace(old, new), encoding="utf-8")
                code, err = build_and_run(folder, "mutant")
                self.assertNotEqual(code, 0, f"the harness stayed green with: {name}")
                self.assertIn("FAIL", err, f"it failed, but not on a check: {err[-500:]}")
        shutil.rmtree(SCRATCH / "mutant", ignore_errors=True)


class SheetTests(unittest.TestCase):
    def test_sheets_pass_the_generator(self):
        rows = gen.roster()
        self.assertEqual([r["id"] for r in rows], [1, 2, 3])
        self.assertEqual([name for name, *_ in gen.rules()], list(gen.RULES))

    def test_the_script_name_is_the_headers(self):
        self.assertEqual(gen.SCRIPT, "dc_follower")
        header = HEADER.read_text(encoding="utf-8")
        self.assertIn(f'Script = "{gen.SCRIPT}"', header)

    def test_the_server_reads_the_rules_the_sheet_writes(self):
        source = (SRC / "dc_followers.cpp").read_text(encoding="utf-8")
        for name in gen.RULES:
            self.assertEqual(source.count(f'"{name}"'), 1, name)
        self.assertEqual(sorted(re.findall(r'name == "(\w+)"', source)), sorted(gen.RULES))
        self.assertIn("FROM dc_follower_rule", source)
        self.assertIn("FROM dc_follower ORDER BY", source)

    def test_the_character_table_is_the_servers(self):
        source = (SRC / "dc_followers.cpp").read_text(encoding="utf-8")
        migration = (MODULE / "data/sql/db-characters/updates/followers_0001_character_follower.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS `dc_character_follower`", migration)
        for column in re.findall(r"^\s+`(\w+)`", migration, re.M):
            self.assertIn(column, source)
        self.assertIn("DELETE FROM dc_character_follower WHERE guid={}", source)

    def test_the_other_files_know_the_followers(self):
        self.assertIn("DC::Campaign::RegisterScripts();", (MODULE / "src/mod_diablocraft_loader.cpp").read_text(encoding="utf-8"))
        # Followers are not monsters of the tier, as the allies are not: difficulty scaling leaves them alone.
        self.assertIn("Campaign::Followers::IsFollowerScript(creature->GetScriptName())",
                      (MODULE / "src/difficulty/dc_difficulty.cpp").read_text(encoding="utf-8"))

    def test_talking_to_a_follower_hires_it_and_the_window_does_not(self):
        """ruling q-1021-158: hiring is a talk option on the hub NPC. The hello offers Hire where the rule says so and
        opens the window beside it; the select re-checks the rule and hires through Hire; the window's `hire` request
        is refused (src/items/dc_follower_gear.cpp), so the NPC is the only way."""
        creature = re.sub(r"//.*", "", (SRC / "dc_follower_creature.cpp").read_text(encoding="utf-8"))
        self.assertIn("OffersHire(World::IsInHub(player), Hired(player), row->id)", creature)
        self.assertIn("AddGossipItemFor(player, GOSSIP_ICON_CHAT, \"Hire \" + row->name + \".\", GOSSIP_SENDER_MAIN, HireAction);",
                      creature)
        self.assertIn("Items::FollowerGear::OpenWindow(player, unsigned(row->id));", creature)
        hello = creature[creature.index("bool OnGossipHello"):creature.index("bool OnGossipSelect")]
        # A companion answers its own player only; with no Hire to offer the talk opens the window as it did.
        self.assertIn("creature->GetOwnerGUID() != player->GetGUID()", hello)
        self.assertIn("SendGossipMenuFor(player, 1, creature->GetGUID());", hello)
        select = creature[creature.index("bool OnGossipSelect"):]
        self.assertIn("sender != GOSSIP_SENDER_MAIN", select)
        self.assertIn("action == HireAction && OffersHire(World::IsInHub(player), Hired(player), row->id)", select)
        self.assertIn("Hire(player, row->id)", select)
        self.assertNotIn("Dismiss(", creature)  # dismissing is the window's button
        gear = (MODULE / "src/items/dc_follower_gear.cpp").read_text(encoding="utf-8")
        body = gear[gear.index("void WindowRequest"):gear.index("class Commands")]
        self.assertNotIn("Followers::Hire(", body)  # the window cannot hire
        self.assertIn("Window::Refusal(*verb)", body)

    def test_the_donors_are_alexs_card(self):
        self.assertEqual([r["donor"] for r in gen.roster()], [28228, 4214, 15278])
        self.assertEqual([r["name"] for r in gen.roster()], ["Kormac", "Lyndon", "Eirena"])

    def test_the_three_stand_around_the_reading_facing_it(self):
        """Card q-1016-23: one .gps reading; the three stand a few yards apart around that point, all facing that way."""
        reading = (1924.5085, 10.852184, 330.02805, 5.3434134)
        rows = gen.hub()
        self.assertEqual([r["map"] for r in rows], [750] * 3)
        self.assertEqual([r["area"] for r in rows], [4273] * 3)
        self.assertEqual([r["o"] for r in rows], [reading[3]] * 3)
        self.assertEqual([r["z"] for r in rows], [reading[2]] * 3)
        centre = (sum(r["x"] for r in rows) / 3, sum(r["y"] for r in rows) / 3)
        self.assertAlmostEqual(centre[0], reading[0], 3)
        self.assertAlmostEqual(centre[1], reading[1], 3)
        for a in range(3):
            for b in range(a + 1, 3):
                gap = ((rows[a]["x"] - rows[b]["x"]) ** 2 + (rows[a]["y"] - rows[b]["y"]) ** 2) ** 0.5
                self.assertTrue(2.5 <= gap <= 7, f"{a} and {b} stand {gap:.2f} yards apart")
        # Side by side across the facing, not one behind another: the line they stand on is square to the facing.
        along = [(r["x"] - reading[0]) * math.cos(reading[3]) + (r["y"] - reading[1]) * math.sin(reading[3]) for r in rows]
        for value in along:
            self.assertAlmostEqual(value, 0, 3)

    def test_the_hub_sheet_names_the_roster_entries_and_free_guids(self):
        rows = gen.hub()
        self.assertEqual([r["entry"] for r in rows], [r["entry"] for r in gen.roster()])
        taken = set()
        for name in ("world_hub_placements.csv", "world_sanctum_retired_copies.csv", "world_tester_coffer.csv"):
            for row in sheet(name):
                for column in ("source_guid", "copy_guid"):
                    if row.get(column) and row.get("kind", "c") == "c":
                        taken.add(int(row[column]))
        self.assertFalse(taken & {r["guid"] for r in rows})

    def test_the_generator_refuses_bad_sheets(self):
        folder = SCRATCH / "sheets"
        shutil.rmtree(folder, ignore_errors=True)
        (folder / "data/d3").mkdir(parents=True)
        for name in ("followers_roster.csv", "followers_rules.csv", "followers_hub.csv"):
            shutil.copy(MODULE / "data/d3" / name, folder / "data/d3" / name)
        text = (folder / "data/d3/followers_roster.csv").read_text(encoding="utf-8")
        cases = {
            "entry taken by an ally": text.replace("900144", "900121"),
            "entry taken by the Crusader's Avatar": text.replace("900144", "900140"),
            "entry taken by the Crusader's Warhorse": text.replace("900143", "900141"),
            "entry taken by a Necromancer minion": text.replace("900142", "900150"),
            "a follower repeated": text.replace("900144", "900143"),
            "main stat swapped": text.replace("dexterity", "strength"),
            "an entry that is not a number": text.replace("900142", "none"),
        }
        for name, bad in cases.items():
            with self.subTest(name):
                (folder / "data/d3/followers_roster.csv").write_text(bad, encoding="utf-8")
                with self.assertRaises(ValueError):
                    gen.roster(folder)
        (folder / "data/d3/followers_roster.csv").write_text(text, encoding="utf-8")
        rules = (folder / "data/d3/followers_rules.csv").read_text(encoding="utf-8")
        (folder / "data/d3/followers_rules.csv").write_text(rules.replace("revive_seconds,20", "revive_seconds,0"), encoding="utf-8")
        with self.assertRaises(ValueError):
            gen.rules(folder)
        for name, bad in {"a negative party rule": rules.replace("party_leave_seconds,0,", "party_leave_seconds,-1,"),
                          "a zero catch-up": rules.replace("catch_up_seconds,5,", "catch_up_seconds,0,"),
                          "a zero catch-up distance": rules.replace("catch_up_yards,20,", "catch_up_yards,0,")}.items():
            with self.subTest(name):
                (folder / "data/d3/followers_rules.csv").write_text(bad, encoding="utf-8")
                with self.assertRaises(ValueError):
                    gen.rules(folder)
        (folder / "data/d3/followers_rules.csv").write_text(rules, encoding="utf-8")
        spots = (folder / "data/d3/followers_hub.csv").read_text(encoding="utf-8")
        for name, bad in {"a guid repeated": spots.replace("8001501", "8001500"),
                          "a guid below the module space": spots.replace("8001502", "7999999"),
                          "two on one spot": spots.replace("1922.0862,9.0823", "1924.5085,10.852184"),
                          "a facing past a turn": spots.replace("5.3434134,\"3 yards", "7.5,\"3 yards"),
                          "rows swapped": spots.replace("templar", "x").replace("scoundrel", "templar").replace("x", "scoundrel")}.items():
            with self.subTest(name):
                (folder / "data/d3/followers_hub.csv").write_text(bad, encoding="utf-8")
                with self.assertRaises(ValueError):
                    gen.hub(folder)
        shutil.rmtree(folder, ignore_errors=True)

    def test_the_generated_file_is_the_sheets_render(self):
        self.assertTrue(all(r["donor"] for r in gen.roster()), "every follower has its look (card q-1016-23)")
        render = gen.render_entries(MODULE)
        self.assertIsNotNone(render)
        for folder in ("data/generated", "data/sql/db-world/updates"):
            self.assertEqual((MODULE / folder / f"{gen.MIGRATION}.sql").read_text(encoding="utf-8"), render)

    def test_the_first_three_migrations_stay_as_they_ran_on_dev(self):
        """0001 to 0003 are applied on dev with the first entries; the fix is a new migration, never a rewrite of them."""
        frozen = {"followers_0001_roster": "fb3452af941f1bc798c14bdd4fcbfda0de83746a979b64af8399851376941a45",
                  "followers_0002_templates": "9006ca39e094c421438b127ff2b12d5d166f6c262746ef578f61d8d02676b7ea",
                  "followers_0003_hub": "8268f83c09a2244fff745fd7914f39b75ed2c78e02034c22193de613eb5b2140"}
        for name, digest in frozen.items():
            for folder in ("data/generated", "data/sql/db-world/updates"):
                with self.subTest(f"{folder}/{name}"):
                    data = (MODULE / folder / f"{name}.sql").read_bytes()
                    self.assertEqual(hashlib.sha256(data).hexdigest(), digest)

    def test_the_migration_has_every_step_of_the_fix(self):
        sql = gen.render_entries(MODULE)
        roster = {r["key"]: r for r in gen.roster()}
        # The roster rows with the new entries, and the party rule zero.
        self.assertIn("(1,900143,'Kormac'),\n(2,900144,'Lyndon'),\n(3,900142,'Eirena');", sql)
        self.assertIn("('party_leave_seconds',0,'seconds')", sql)
        # The Crusader's templates come back before the follower templates are written, and nothing writes 900140 or 900141 after.
        restore = sql.index("SET entry=900140,name='Avatar of the Order'")
        self.assertIn("SET entry=900141,name='Warhorse of the Order'", sql)
        self.assertLess(restore, sql.index("SET entry=900143,"))
        for entry in (900140, 900141):
            self.assertEqual(len(re.findall(rf"DELETE FROM creature_template WHERE entry={entry};", sql)), 1)
        # The hub rows move off the old entries only where they hold them.
        for r in gen.hub():
            legacy = roster[[k for k, v in roster.items() if v["id"] == r["id"]][0]]["legacy"]
            self.assertIn(f"guid={r['guid']} AND id IN ({r['entry']},{legacy})", sql)
        self.assertEqual({k: v["legacy"] for k, v in roster.items()}, gen.LEGACY_ENTRIES)

    def test_no_other_sheet_uses_a_follower_entry(self):
        ours = {r["entry"] for r in gen.roster()}
        users = {}
        for path in sorted((MODULE / "data/d3").glob("*.csv")) + [MODULE / "data/legendary_summons.csv"]:
            if path.name == "followers_roster.csv":
                continue
            with path.open(encoding="utf-8", newline="") as stream:
                reader = csv.DictReader(stream)
                if "entry" not in (reader.fieldnames or []):
                    continue
                for row in reader:
                    if row["entry"].isdigit() and int(row["entry"]) in ours:
                        users[int(row["entry"])] = path.name
        self.assertEqual(users, {}, "a follower entry is also a creature of another sheet")

    def test_the_party_rule_is_none_and_the_other_rules_are_d3s(self):
        values = {r["rule"]: float(r["value"]) for r in sheet("followers_rules.csv")}
        self.assertEqual(values, {"revive_seconds": 20, "party_leave_seconds": 0, "catch_up_seconds": 5, "catch_up_yards": 20})
        self.assertIn("q-1021-43", next(r["source"] for r in sheet("followers_rules.csv") if r["rule"] == "party_leave_seconds"))


    def test_followers_0004_writes_the_crusaders_templates_as_the_crusader_sheet_has_them(self):
        """followers_0004 writes the Phalanx's Avatar and Warhorse (900140, 900141) again, and on a world made from nothing it runs after every
        classes_ file, so a later edit of crusader_summons.csv would be undone there. This fails the day the two differ: the fix is then a new
        migration after the edit (and after 0004) that writes the Crusader's two templates, never a rewrite of the applied 0004. The tie is
        in docs/design/systems/torment/followers.md and classes-skills.md."""
        import generate_crusader_summons
        crusader = gen.body(generate_crusader_summons.render(MODULE))
        entries = (MODULE / "data/sql/db-world/updates" / f"{gen.MIGRATION}.sql").read_text(encoding="utf-8")
        self.assertIn(crusader, entries, "crusader_summons.csv's templates are not what followers_0004 writes: see this test's docstring")
        for entry in (900140, 900141):
            self.assertEqual(len(re.findall(rf"DELETE FROM creature_template WHERE entry={entry};", entries)), 1)
        # Planted: an edit of the sheet's Avatar is seen.
        edited = crusader.replace("Avatar of the Order", "Avatar of the Orders")
        self.assertNotEqual(edited, crusader)
        self.assertNotIn(edited, entries)


class SourceTests(unittest.TestCase):
    """The creature and the hire read the same hub, party and save rules the sheets and migrations write."""

    @classmethod
    def setUpClass(cls):
        cls.core = re.sub(r"\s+", " ", (SRC / "dc_followers.cpp").read_text(encoding="utf-8"))
        cls.creature = re.sub(r"\s+", " ", (SRC / "dc_follower_creature.cpp").read_text(encoding="utf-8"))

    def test_the_hub_copy_is_hidden_per_player_by_the_creatures_own_hook(self):
        self.assertIn("bool CanBeSeen(Player const* seer) override { return owner || !OutFor(seer, me->GetEntry()); }",
                      self.creature)
        # Only the player whose follower it is: OutFor reads the viewer's own state and the viewer's own companion.
        self.assertIn("auto found = states.find(viewer->GetGUID());", self.core)
        self.assertIn("ObjectAccessor::GetCreature(*viewer, companion)", self.core)
        self.assertIn("row->entry != entry", self.core)

    def test_the_view_is_asked_again_when_the_companion_appears_or_goes(self):
        self.assertIn("player->UpdateVisibilityOf(copy);", self.core)
        self.assertIn("if (!copy->GetOwnerGUID())", self.core)
        # After the summon, and where it is sent away: RefreshHub twice in Step and Appear, none elsewhere.
        self.assertEqual(self.core.count("RefreshHub(player);"), 2)
        appear = self.core[self.core.index("void Appear("):self.core.index("// One step for one player")]
        self.assertIn("RefreshHub(player);", appear)
        self.assertIn("found->second.companion = ObjectGuid::Empty;", self.core)

    def test_a_party_sends_it_home_with_the_hire_kept(self):
        step = self.core[self.core.index("void Step("):self.core.index("void Save(")]
        self.assertIn("Alone(player)", step)
        self.assertNotIn("found->second.hired = Id::None", step)
        self.assertNotIn("Save(", step)  # the hire is written by Hire and Dismiss only
        self.assertEqual(len(re.findall(r"Save\(player, ", self.core)), 2)

    def test_the_hire_is_saved_per_character_and_read_at_login(self):
        self.assertIn('"REPLACE INTO dc_character_follower (guid, follower) VALUES ({}, {})"', self.core)
        self.assertIn('"SELECT follower FROM dc_character_follower WHERE guid={}", player->GetGUID().GetCounter()', self.core)
        self.assertIn("state.hired = hired;", self.core)
        # Logging out clears the companion and the state, never the saved row.
        logout = self.core[self.core.index("void OnPlayerBeforeLogout"):self.core.index("void OnPlayerUpdate")]
        self.assertIn("states.erase(found);", logout)
        self.assertNotIn("dc_character_follower", logout)
        self.assertNotIn("Save(", logout)

    def test_a_missing_party_row_is_told_from_a_zero_one(self):
        self.assertIn("constexpr unsigned RuleCount = 4;", self.core)
        self.assertIn("return found == RuleCount && partyLeave >= 0 && Usable(rules);", self.core)


class FixtureDatabaseTests(unittest.TestCase):
    """The migrations against the fixture mysqld's copy of the world (never the live one)."""

    scratch = harness_env.private_name("dc_followers_test_gh1c1_3")

    @classmethod
    def setUpClass(cls):
        try:
            import fixture_db
            cls.mysql, cls.defaults = fixture_db.mysql_and_defaults([])
        except SystemExit as stopped:
            raise unittest.SkipTest(str(stopped))

    def query(self, sql, database="mysql", feed=None):
        ran = subprocess.run([self.mysql, "--defaults-file=" + self.defaults, "--no-login-paths", "-N", database] +
                             ([] if feed else ["-e", sql]), input=feed, capture_output=True, text=True)
        self.assertEqual(ran.returncode, 0, ran.stderr)
        return [tuple(line.split("\t")) for line in ran.stdout.splitlines()]

    def setUp(self):
        self.query(f"DROP DATABASE IF EXISTS {self.scratch}")
        self.query(f"CREATE DATABASE {self.scratch}")
        self.addCleanup(self.query, f"DROP DATABASE IF EXISTS {self.scratch}")

    def test_the_roster_migration_writes_the_tables_and_rules(self):
        self.query("", self.scratch, feed=gen.render_roster(MODULE))
        self.assertEqual(self.query("SELECT follower_id, entry, name FROM dc_follower ORDER BY follower_id", self.scratch),
                         [(str(r["id"]), str(r["entry"]), r["name"]) for r in gen.roster()])
        self.assertEqual(self.query("SELECT rule, value, unit FROM dc_follower_rule", self.scratch),
                         [(name, value, unit) for name, value, unit in
                          sorted(gen.rules(), key=lambda row: row[0])])
        # Run again: a re-applied migration leaves the same rows.
        self.query("", self.scratch, feed=gen.render_roster(MODULE))
        self.assertEqual(self.query("SELECT COUNT(*) FROM dc_follower", self.scratch), [("3",)])

    def test_the_character_migration_creates_its_table(self):
        sql = (MODULE / "data/sql/db-characters/updates/followers_0001_character_follower.sql").read_text(encoding="utf-8")
        self.query("", self.scratch, feed=sql)
        self.query("", self.scratch, feed=sql)
        self.query("INSERT INTO dc_character_follower (guid, follower) VALUES (7, 2) "
                   "ON DUPLICATE KEY UPDATE follower=2", self.scratch)
        self.assertEqual(self.query("SELECT guid, follower FROM dc_character_follower", self.scratch), [("7", "2")])

    def test_the_hub_migration_places_the_three_and_refuses_a_taken_guid(self):
        self.query("CREATE TABLE creature LIKE acore_world.creature", self.scratch)
        sql = gen.render_hub(MODULE)
        self.query("", self.scratch, feed=sql)
        self.query("", self.scratch, feed=sql)   # applied twice: the same three rows
        want = [(str(r["guid"]), str(r["entry"]), "750", "4273", "4273", "1", "1") for r in gen.hub()]
        self.assertEqual(self.query("SELECT guid, id, map, zoneId, areaId, spawnMask, phaseMask FROM creature ORDER BY guid",
                                    self.scratch), want)
        placed = self.query("SELECT position_x, position_y, position_z, orientation FROM creature ORDER BY guid", self.scratch)
        for row, spot in zip(placed, gen.hub()):
            for got, expected in zip(row, (spot["x"], spot["y"], spot["z"], spot["o"])):
                self.assertAlmostEqual(float(got), expected, delta=0.01)  # a FLOAT column prints shortened
        # A creature of another entry on a follower's guid stops the migration; nothing is overwritten.
        self.query("UPDATE creature SET id=31146 WHERE guid=8001501", self.scratch)
        ran = subprocess.run([self.mysql, "--defaults-file=" + self.defaults, "--no-login-paths", self.scratch],
                             input=sql, capture_output=True, text=True)
        self.assertNotEqual(ran.returncode, 0)
        self.assertEqual(self.query("SELECT id FROM creature WHERE guid=8001501", self.scratch), [("31146",)])

    def world_with_donors(self):
        """The scratch world with the tables the follower migrations touch and the stock rows they copy."""
        for table in ("creature", "creature_template", "creature_template_model"):
            self.query(f"CREATE TABLE {table} LIKE acore_world.{table}", self.scratch)
        donors = "28228,4214,15278,11194,16509"
        self.query(f"INSERT INTO creature_template SELECT * FROM acore_world.creature_template WHERE entry IN ({donors})", self.scratch)
        self.query(f"INSERT INTO creature_template_model SELECT * FROM acore_world.creature_template_model "
                   f"WHERE CreatureID IN ({donors})", self.scratch)

    def feed(self, sql):
        ran = subprocess.run([self.mysql, "--defaults-file=" + self.defaults, "--no-login-paths", self.scratch],
                             input=sql, capture_output=True, text=True)
        return ran

    def history(self, name):
        return (MODULE / "data/sql/db-world/updates" / f"{name}.sql").read_text(encoding="utf-8")

    def templates(self):
        return self.query("SELECT entry, name, ScriptName FROM creature_template WHERE entry BETWEEN 900140 AND 900144 ORDER BY entry",
                          self.scratch)

    def spawns(self):
        return self.query("SELECT guid, id FROM creature ORDER BY guid", self.scratch)

    def test_the_fix_restores_the_crusader_and_moves_the_followers_off_a_world_that_ran_the_first_three(self):
        self.world_with_donors()
        self.query("", self.scratch, feed=self.history("classes_0004_crusader_summons"))
        for name in ("followers_0001_roster", "followers_0002_templates", "followers_0003_hub"):
            self.query("", self.scratch, feed=self.history(name))
        # The bug as it stood on dev: the Templar and the Scoundrel wear the Crusader's two entries.
        self.assertEqual(self.templates(), [("900140", "Kormac", "dc_follower"), ("900141", "Lyndon", "dc_follower"),
                                            ("900142", "Eirena", "dc_follower")])
        self.assertEqual(self.spawns(), [("8001500", "900140"), ("8001501", "900141"), ("8001502", "900142")])
        sql = gen.render_entries(MODULE)
        for _ in range(2):  # and applied twice leaves the same world
            self.query("", self.scratch, feed=sql)
            self.assertEqual(self.templates(), [("900140", "Avatar of the Order", "dc_crusader_avatar"),
                                                ("900141", "Warhorse of the Order", "dc_crusader_avatar"),
                                                ("900142", "Eirena", "dc_follower"), ("900143", "Kormac", "dc_follower"),
                                                ("900144", "Lyndon", "dc_follower")])
            self.assertEqual(self.spawns(), [("8001500", "900143"), ("8001501", "900144"), ("8001502", "900142")])
            self.assertEqual(self.query("SELECT follower_id, entry FROM dc_follower ORDER BY follower_id", self.scratch),
                             [("1", "900143"), ("2", "900144"), ("3", "900142")])
            self.assertEqual(self.query("SELECT value FROM dc_follower_rule WHERE rule='party_leave_seconds'", self.scratch), [("0",)])
        # The Crusader's templates are the same bytes as classes_0004 writes, not an approximation of them.
        crusader = self.query("SELECT entry, name, subname, npcflag, faction, lootid, gossip_menu_id FROM creature_template "
                              "WHERE entry IN (900140,900141) ORDER BY entry", self.scratch)
        self.assertEqual(crusader, [("900140", "Avatar of the Order", "", "0", "35", "0", "0"),
                                    ("900141", "Warhorse of the Order", "", "0", "35", "0", "0")])

    def test_the_fix_runs_on_a_world_that_never_ran_the_first_three(self):
        self.world_with_donors()
        self.query("", self.scratch, feed=gen.render_entries(MODULE))
        self.assertEqual(self.spawns(), [("8001500", "900143"), ("8001501", "900144"), ("8001502", "900142")])
        self.assertEqual([row[0] for row in self.templates()], ["900140", "900141", "900142", "900143", "900144"])

    def test_the_fix_leaves_a_taken_hub_guid_alone(self):
        self.world_with_donors()
        self.query("", self.scratch, feed=gen.render_entries(MODULE))
        self.query("UPDATE creature SET id=31146 WHERE guid=8001501", self.scratch)
        ran = self.feed(gen.render_entries(MODULE))
        self.assertNotEqual(ran.returncode, 0)
        self.assertEqual(self.query("SELECT id FROM creature WHERE guid=8001501", self.scratch), [("31146",)])

    def test_the_donors_alex_picked_are_stock_creatures_with_a_model(self):
        for donor in (28228, 4214, 15278):
            count = self.query(f"SELECT COUNT(*) FROM acore_world.creature_template_model WHERE CreatureID={donor}")
            self.assertGreater(int(count[0][0]), 0, donor)

    def test_a_template_wears_its_donor_with_the_modules_ai(self):
        donor = self.query("SELECT entry FROM acore_world.creature_template WHERE entry IN (SELECT CreatureID FROM "
                           "acore_world.creature_template_model) AND `rank`=0 AND minlevel>0 ORDER BY entry LIMIT 1")[0][0]
        folder = SCRATCH / "donor"
        shutil.rmtree(folder, ignore_errors=True)
        (folder / "data/d3").mkdir(parents=True)
        shutil.copy(MODULE / "data/d3/followers_rules.csv", folder / "data/d3/followers_rules.csv")
        text = (MODULE / "data/d3/followers_roster.csv").read_text(encoding="utf-8")
        text = re.sub(r"(,70,)\d*(,)", lambda m: m.group(1) + donor + m.group(2), text)
        (folder / "data/d3/followers_roster.csv").write_text(text, encoding="utf-8")
        sql = gen.render_templates(folder)
        self.assertIsNotNone(sql)
        self.query("CREATE TABLE creature_template LIKE acore_world.creature_template", self.scratch)
        self.query("CREATE TABLE creature_template_model LIKE acore_world.creature_template_model", self.scratch)
        self.query(f"INSERT INTO creature_template SELECT * FROM acore_world.creature_template WHERE entry={donor}", self.scratch)
        self.query(f"INSERT INTO creature_template_model SELECT * FROM acore_world.creature_template_model WHERE CreatureID={donor}",
                   self.scratch)
        self.query("", self.scratch, feed=sql)
        rows = self.query("SELECT entry, name, subname, ScriptName, npcflag, minlevel, maxlevel, HealthModifier, DamageModifier, "
                          "`rank`, lootid, faction FROM creature_template WHERE entry >= 900142 ORDER BY entry", self.scratch)
        self.assertEqual(rows, [(str(r["entry"]), r["name"], r["subname"], "dc_follower", "1", "70", "70", "1", "1", "0", "0", "35")
                                for r in sorted(gen.roster(folder), key=lambda r: r["entry"])])
        models = self.query("SELECT COUNT(*) FROM creature_template_model WHERE CreatureID >= 900142", self.scratch)
        donor_models = int(self.query(f"SELECT COUNT(*) FROM acore_world.creature_template_model WHERE CreatureID={donor}")[0][0])
        self.assertEqual(models, [(str(3 * donor_models),)])
        shutil.rmtree(folder, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
