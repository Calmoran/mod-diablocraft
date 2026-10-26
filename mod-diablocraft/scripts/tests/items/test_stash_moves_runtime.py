"""The account stash moves, compiled from the production source (diablocraft-stash-audit, 1b).

    python3 mod-diablocraft/scripts/tests/items/test_stash_moves_runtime.py

dc_stash.cpp from MaxTabs() to the diagnostics marker is cut out of the real file and compiled
against the doubles in stash_harness.cpp.in: a bag model with the core's store/merge/remove rules,
a durable table model that commits a transaction whole or not at all and refuses a second link for
one item guid, and a logout/login that rebuilds memory from the rows. AddressSanitizer is on, so an
item the code touches after the inventory save freed it is a failed run. Nothing is a worldserver
build: this proves the move logic and its failure steps, not live client behaviour.

Each scenario is its own test. MutationsAreCaught re-compiles with one deliberate break of the
production text and requires the scenarios that guard it to fail. SweepSql runs the statements the
account-deletion hook sends against a real MySQL (the fixture mysqld), together with the character
deletion statements the core runs, and requires the stash to survive the second and not the first.
"""
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import fixture_db
import harness_env

ROOT = Path(__file__).resolve().parents[4]
SOURCE = ROOT / "mod-diablocraft/src/items/dc_stash.cpp"
HEADER = ROOT / "mod-diablocraft/src/items/dc_stash.h"
TEMPLATE = ROOT / "mod-diablocraft/scripts/stash_harness.cpp.in"
ITEM_TEMPLATE_H = ROOT / "azerothcore-wotlk/src/server/game/Entities/Item/ItemTemplate.h"
UPDATES = ROOT / "mod-diablocraft/data/sql/db-world/updates"
SCRATCH = ROOT / "azerothcore-wotlk/build/_agent-scratch/stash-moves-runtime"

START = "    std::uint8_t MaxTabs()"
END = "        // -------------------------------------------------------------- diagnostics"

LOADER = '''void LoadItems(Key const& key, Container& container)
        {
            // The SQL join stands in as a read of the durable rows (harness).
            for (auto const& link : db.links)
            {
                if (std::get<0>(link.first) != key.account || std::get<1>(link.first) != key.Mode())
                    continue;
                ItemRow const& row = db.items.at(link.second);
                uint32 const max = stackSizes.count(row.entry) ? stackSizes[row.entry] : 1;
                Item* item = MakeItem(link.second, row.entry, row.count, max);
                item->owner = 0;
                container.items[std::uint16_t(std::get<2>(link.first) * SlotsPerTab + std::get<3>(link.first))] = item;
            }
        }'''


def extract(source, signature):
    start = source.index(signature)
    opening = source.index("{", start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def production(text=None):
    text = SOURCE.read_text() if text is None else text
    body = text[text.index(START):text.index(END)]
    body = body.replace(extract(body, "void LoadItems("), LOADER)
    return body + "\n    } // anonymous namespace, closed here so the scenarios can call it"


_cache = {}


def cache_template():
    """The core's bind-to-account flag, and the first Horadric Cache's entry and Flags as the world migrations leave
    them: bounties_0003's INSERT, then bounties_0004's `Flags | value` (diablocraft-rxvzd)."""
    flag = int(re.search(r"ITEM_FLAG_IS_BOUND_TO_ACCOUNT\s*=\s*(0x[0-9A-Fa-f]+)", ITEM_TEMPLATE_H.read_text()).group(1), 16)
    bound = re.search(r"SET `Flags` = `Flags` \| (\d+), `bonding` = 1 WHERE `entry` IN \((\d+),",
                      (UPDATES / "bounties_0004_cache_account_bound.sql").read_text())
    entry = bound.group(2)
    base = re.search(rf"\({entry}, 15, 0, '(?:[^']|'')*', \d+, \d+, (\d+),", (UPDATES / "bounties_0003_caches.sql").read_text())
    return flag, int(entry), int(base.group(1)) | int(bound.group(1))


def build(name, text=None):
    """Compile the harness around `text` (the production file); returns the binary path."""
    folder = SCRATCH / name
    folder.mkdir(parents=True, exist_ok=True)
    flag, entry, flags = cache_template()
    code = (TEMPLATE.read_text().replace("@HEADER@", str(HEADER)).replace("@PRODUCTION@", production(text))
            .replace("@BOUND_FLAG@", str(flag)).replace("@CACHE_ENTRY@", str(entry)).replace("@CACHE_FLAGS@", str(flags)))
    source = folder / "harness.cpp"
    source.write_text(code)
    result = subprocess.run(["g++", "-std=c++17", "-g", "-O0", "-fsanitize=address,undefined", "-fno-sanitize-recover=undefined",
                             "-Wall", "-Wextra", "-Wno-unused-parameter", "-Wno-unused-variable",
                             "-Wno-unused-function", str(source), "-o", str(folder / "harness")],
                            capture_output=True, text=True)
    (folder / "compile.log").write_text(result.stdout + result.stderr)
    if result.returncode:
        raise AssertionError(result.stderr[-6000:])
    return folder / "harness"


def run(binary, scenario):
    ran = harness_env.run([str(binary), scenario], capture_output=True, text=True,
                          env={"ASAN_OPTIONS": "detect_leaks=0:abort_on_error=0", "PATH": "/usr/bin:/bin"})
    return ran.returncode, ran.stdout, ran.stderr


def scenario_names(binary):
    ran = harness_env.run([str(binary), "list"], capture_output=True, text=True)
    return ran.stdout.split()


def binary():
    if "main" not in _cache:
        _cache["main"] = build("main")
    return _cache["main"]


class Scenarios(unittest.TestCase):
    """One test per scenario in the harness, generated below."""


def make(name):
    def test(self):
        code, out, err = run(binary(), name)
        self.assertEqual(code, 0, f"{name}\n{out}\n{err[-3000:]}")
        self.assertIn(f"PASS {name}", out)
    return test


# Scenario names are read from the harness source so the tests exist before it is compiled.
for _name in sorted(set(re.findall(r'scenarios\["([a-z_0-9]+)"\]', TEMPLATE.read_text()))):
    setattr(Scenarios, "test_" + _name, make(_name))


class TheHarnessCoversTheMoves(unittest.TestCase):
    def test_every_move_and_failure_step_has_a_scenario(self):
        names = set(re.findall(r'scenarios\["([a-z_0-9]+)"\]', TEMPLATE.read_text()))
        for needed in (
            "deposit_into_empty_slot", "deposit_swap_exchanges_both_items", "withdraw_to_empty_cell_and_auto",
            "withdraw_swap_exchanges_both_items", "rearrange_move_and_swap", "withdraw_stack_merges_into_bag_stack",
            "withdraw_stack_merge_commit_fails", "deposit_commit_fails", "deposit_swap_commit_fails",
            "withdraw_commit_fails", "withdraw_swap_commit_fails", "rearrange_commit_fails_leaves_the_session_alone",
            "deposit_swap_remeasure_fails", "withdraw_swap_remeasure_fails", "full_bags_refuse_withdraw_cleanly",
            "full_stash_refuses_deposit", "refused_items_stay_where_they_are", "an_aborted_session_moves_nothing",
            "buytab_commit_fails_buys_nothing", "account_sweep_drops_the_caches_and_prints_its_sql",
            "character_hooks_never_delete_stash_rows", "account_bound_template_goes_in_from_bags",
        ):
            self.assertIn(needed, names)

    def test_the_slice_is_the_production_text_not_a_copy(self):
        body = production()
        for piece in ("void Deposit(", "void Withdraw(", "void Rearrange(", "void Rebag(", "void BuyTab(",
                      "void AccountSweep(", "struct BagMove"):
            self.assertIn(piece, body)
        # the hand-written undo is gone for good
        for gone in ("ReturnToBags", "UnstoreOne"):
            self.assertNotIn(gone, SOURCE.read_text())


MUTATIONS = [
    # (name, old text, new text, scenarios that must fail)
    ("no-abort-on-failed-commit",
     "            Need(Commit(key, container, transaction), ReloadMessage);\n            move.saved = true;\n            AnnounceTaken(player, source, bag, slot);",
     "            Commit(key, container, transaction);\n            move.saved = true;\n            AnnounceTaken(player, source, bag, slot);",
     ["deposit_commit_fails", "deposit_swap_commit_fails"]),
    ("withdraw-ignores-failed-commit",
     "            Need(Commit(key, container, transaction), ReloadMessage);\n            move.saved = true;\n            if (swapped)",
     "            Commit(key, container, transaction);\n            move.saved = true;\n            if (swapped)",
     ["withdraw_commit_fails", "withdraw_swap_commit_fails", "withdraw_stack_merge_commit_fails"]),
    ("guard-does-not-kick",
     "                player->GetSession()->AbortEconomy();\n            }\n        };",
     "            }\n        };",
     ["deposit_commit_fails", "withdraw_commit_fails", "deposit_swap_remeasure_fails"]),
    ("guard-keeps-the-cache",
     "                if (held)\n                    delete held;\n                Purge(key);\n                PlayerEconomy::Fail();",
     "                if (held)\n                    delete held;\n                PlayerEconomy::Fail();",
     ["deposit_commit_fails", "withdraw_commit_fails"]),
    ("guard-leaks-the-held-item",
     "                if (held)\n                    delete held;\n                Purge(key);",
     "                Purge(key);",
     ["deposit_swap_remeasure_fails", "withdraw_swap_remeasure_fails"]),
    ("guard-does-not-fail-the-economy",
     "                Purge(key);\n                PlayerEconomy::Fail();\n                player->GetSession()->AbortEconomy();",
     "                Purge(key);\n                player->GetSession()->AbortEconomy();",
     ["deposit_commit_fails"]),
    ("aborted-session-may-move",
     '            Need(player && player->GetSession() && !player->GetSession()->EconomyAborted(),\n                 "Reconnect to use the Stash.");',
     "            Need(player && player->GetSession(), \"No session.\");",
     ["an_aborted_session_moves_nothing"]),
    ("deposit-does-not-park",
     "            source->DeleteFromInventoryDB(transaction);\n            Park(transaction, source);",
     "            source->DeleteFromInventoryDB(transaction);",
     ["deposit_into_empty_slot"]),
    ("deposit-keeps-the-bag-row",
     "            source->DeleteFromInventoryDB(transaction);\n            Park(transaction, source);",
     "            Park(transaction, source);",
     ["deposit_into_empty_slot"]),
    ("withdraw-keeps-the-link",
     "            container.items.erase(position);\n            ClearSlot(transaction, key, position);\n            if (swapped)",
     "            container.items.erase(position);\n            if (swapped)",
     ["withdraw_to_empty_cell_and_auto"]),
    ("rearrange-does-not-clear-both-slots-first",
     "            ClearSlot(transaction, key, from);\n            ClearSlot(transaction, key, to);",
     "            ClearSlot(transaction, key, from);",
     ["rearrange_move_and_swap"]),
    ("deposit-swap-skips-the-remeasure-guard",
     "                         CellsAreFree(player, destination) && StoreOne(player, destination, swapped),\n                     ReloadMessage);",
     "                         CellsAreFree(player, destination) && StoreOne(player, destination, swapped) || true,\n                     ReloadMessage);",
     ["deposit_swap_remeasure_fails"]),
    ("withdraw-stack-uses-freed-item-on-failure",
     "            Need(Commit(key, container, transaction), ReloadMessage);\n            move.saved = true;\n            if (swapped)",
     "            if (!Commit(key, container, transaction))\n            {\n                move.saved = true;\n                source->SetCount(source->GetCount());\n                throw std::runtime_error(ReloadMessage);\n            }\n            move.saved = true;\n            if (swapped)",
     ["withdraw_stack_merge_commit_fails"]),
    ("authorize-drops-the-stash-object",
     'Need(player->FindNearestCreature(StashEntry, ActionRange()) != nullptr, "Stand at the hub Stash.");',
     "",
     ["the_stash_object_and_the_player_gate_every_move"]),
    ("a-full-stash-is-not-refused",
     'throw std::runtime_error("The Stash is full.");',
     "return 0;",
     ["full_stash_refuses_deposit"]),
    # diablocraft-rxvzd: the stash takes a template bound to the account, and nothing else that is soulbound.
    ("account-bound-template-refused",
     "            else if (!item->IsBoundAccountWide())\n",
     "            else\n",
     ["account_bound_template_goes_in_from_bags"]),
    ("any-soulbound-item-goes-in",
     "            else if (!item->IsBoundAccountWide())\n",
     "            else if (false)\n",
     ["refused_items_stay_where_they_are"]),
    ("account-flag-skips-the-rolled-owner",
     "            if (rolled && rolled->boundAccount)\n                Need(rolled->boundAccount == key.account,",
     "            if (rolled && rolled->boundAccount && !item->IsBoundAccountWide())\n                Need(rolled->boundAccount == key.account,",
     ["account_bound_template_goes_in_from_bags"]),
    ("buytab-forgets-the-failure",
     "                Need(AccountEconomy::Commit(player, transaction),\n                     \"The purchase could not be committed; nothing was charged.\");",
     "                AccountEconomy::Commit(player, transaction);",
     ["buytab_commit_fails_buys_nothing"]),
]


class MutationsAreCaught(unittest.TestCase):
    pass


def make_mutation(index, name, old, new, scenarios):
    def test(self):
        source = SOURCE.read_text()
        self.assertEqual(source.count(old), 1, f"the text this mutation breaks is not in dc_stash.cpp once: {old[:70]!r}")
        mutated = build(f"mutation-{index}", source.replace(old, new))
        for scenario in scenarios:
            code, out, err = run(mutated, scenario)
            self.assertNotEqual(code, 0, f"mutation {name!r} survived scenario {scenario}\n{out}")
    return test


for _i, (_n, _o, _w, _s) in enumerate(MUTATIONS):
    setattr(MutationsAreCaught, "test_" + _n.replace("-", "_"), make_mutation(_i, _n, _o, _w, _s))


# --------------------------------------------------------------------------- the account sweep

SWEEP_DB = "dc_stash_sweep_test"
GEM_RANK_SQL = ROOT / "mod-diablocraft/data/sql/db-characters/updates/legendary_gems_0001_rank.sql"
CORE_STATEMENTS = ROOT / "azerothcore-wotlk/src/server/database/Database/Implementation/CharacterDatabase.cpp"


def character_delete_statements():
    """Player::DeleteFromDB's item statements, read from the pinned core (Player.cpp:4264, 4301)."""
    text = CORE_STATEMENTS.read_text()
    out = []
    for name in ("CHAR_DEL_CHAR_INVENTORY", "CHAR_DEL_ITEM_INSTANCE_BY_OWNER"):
        match = re.search(r'PrepareStatement\(' + name + r', "([^"]+)"', text)
        assert match, name
        out.append(match.group(1).replace("?", "{guid}"))
    return out


def mysql(sql, check=True):
    mysql_exe, defaults = fixture_db.mysql_exe(), str(fixture_db.defaults_file())
    ran = subprocess.run([mysql_exe, "--defaults-file=" + defaults, "--no-login-paths", "--init-command=SET SESSION sql_mode=''", "-N", "-B", SWEEP_DB if "CREATE DATABASE" not in sql and "DROP DATABASE" not in sql else "mysql", "-e", sql],
                         capture_output=True, text=True)
    if check and ran.returncode:
        raise AssertionError(ran.stderr)
    return ran.stdout.strip()


ROLLED = ("dc_item_instance", "dc_item_affix", "dc_enchant_offer", "dc_item_unidentified", "dc_legendary_gem_rank")


class SweepSql(unittest.TestCase):
    TABLES = ("item_instance", "character_inventory", "characters", "dc_item_instance", "dc_item_affix",
              "dc_enchant_offer", "dc_item_unidentified", "dc_account_stash", "dc_account_stash_tab",
              "dc_account_stash_item")

    @classmethod
    def setUpClass(cls):
        try:
            fixture_db.mysql_and_defaults([])
        except SystemExit as error:
            raise unittest.SkipTest(str(error))
        code, out, err = run(binary(), "account_sweep_drops_the_caches_and_prints_its_sql")
        assert code == 0, err
        cls.sql = [line[4:] for line in out.splitlines() if line.startswith("SQL ")]

    def setUp(self):
        mysql(f"DROP DATABASE IF EXISTS {SWEEP_DB}", check=False)
        mysql(f"CREATE DATABASE {SWEEP_DB}")
        for table in self.TABLES:
            mysql(f"CREATE TABLE {table} LIKE acore_characters.{table}")
        # The fixture's acore_characters predates the migrations that came after it was loaded; the gem
        # rank table is made from its own migration's CREATE, so the test needs no refreshed fixture.
        mysql(re.search(r"CREATE TABLE IF NOT EXISTS `dc_legendary_gem_rank`[^;]+", GEM_RANK_SQL.read_text()).group(0))
        self.addCleanup(mysql, f"DROP DATABASE IF EXISTS {SWEEP_DB}", False)
        # Two accounts, each with a stash holding a parked rolled item; a character of account 7
        # with an item in its bag; an item with a stash link and an OWNER (a fault, never deleted).
        for account, guid, item, tab in ((7, 5001, 90001, 1), (8, 5002, 90002, 1)):
            mysql(f"INSERT INTO dc_account_stash(account_id,mode,tabs_granted,revision) VALUES({account},'normal',1,3)")
            mysql(f"INSERT INTO dc_account_stash_tab(account_id,mode,tab_id) VALUES({account},'normal',0)")
            mysql(f"INSERT INTO item_instance(guid,itemEntry,owner_guid,count) VALUES({item},3000,0,1)")
            mysql(f"INSERT INTO dc_account_stash_item(account_id,mode,tab_id,slot_id,item_guid) VALUES({account},'normal',0,0,{item})")
            mysql(f"INSERT INTO dc_item_instance(item_guid) VALUES({item})")
            mysql(f"INSERT INTO dc_item_affix(item_guid,seq) VALUES({item},0)")
            mysql(f"INSERT INTO dc_enchant_offer(item_guid) VALUES({item})")
            mysql(f"INSERT INTO dc_item_unidentified(item_guid) VALUES({item})")
            mysql(f"INSERT INTO dc_legendary_gem_rank(item_guid) VALUES({item})")
        mysql("INSERT INTO dc_account_stash(account_id,mode,tabs_granted,revision) VALUES(7,'hardcore',1,0)")
        mysql("INSERT INTO item_instance(guid,itemEntry,owner_guid,count) VALUES(90003,3000,0,1)")
        mysql("INSERT INTO dc_account_stash_item(account_id,mode,tab_id,slot_id,item_guid) VALUES(7,'hardcore',0,0,90003)")
        mysql("INSERT INTO item_instance(guid,itemEntry,owner_guid,count) VALUES(90004,3000,5001,1)")
        mysql("INSERT INTO dc_account_stash_item(account_id,mode,tab_id,slot_id,item_guid) VALUES(7,'normal',0,1,90004)")
        for table, extra in (("dc_item_instance", ""), ("dc_item_affix", ",seq"), ("dc_enchant_offer", ""), ("dc_item_unidentified", ""), ("dc_legendary_gem_rank", "")):
            mysql(f"INSERT INTO {table}(item_guid{extra}) VALUES(90004{',0' if extra else ''})")
        mysql("INSERT INTO item_instance(guid,itemEntry,owner_guid,count) VALUES(90005,3000,5001,1)")
        mysql("INSERT INTO character_inventory(guid,bag,slot,item) VALUES(5001,0,23,90005)")

    def count(self, table, where="1"):
        return int(mysql(f"SELECT COUNT(*) FROM {table} WHERE {where}"))

    def test_the_hook_sent_statements(self):
        self.assertGreaterEqual(len(self.sql), 8, self.sql)
        self.assertTrue(all("{" not in statement for statement in self.sql), self.sql)

    def test_deleting_the_account_deletes_its_stash_and_parked_items_in_both_modes(self):
        for statement in self.sql:
            mysql(statement)
        self.assertEqual(self.count("dc_account_stash", "account_id=7"), 0)
        self.assertEqual(self.count("dc_account_stash_tab", "account_id=7"), 0)
        self.assertEqual(self.count("dc_account_stash_item", "account_id=7"), 0)
        for guid in (90001, 90003):
            self.assertEqual(self.count("item_instance", f"guid={guid}"), 0)
        for table in ROLLED:
            self.assertEqual(self.count(table, "item_guid=90001"), 0, table)

    def test_another_accounts_stash_is_not_touched(self):
        for statement in self.sql:
            mysql(statement)
        self.assertEqual(self.count("dc_account_stash", "account_id=8"), 1)
        self.assertEqual(self.count("dc_account_stash_item", "account_id=8"), 1)
        self.assertEqual(self.count("item_instance", "guid=90002"), 1)
        for table in ROLLED:
            self.assertEqual(self.count(table, "item_guid=90002"), 1, table)

    def test_an_item_a_character_owns_is_never_deleted_by_the_sweep(self):
        for statement in self.sql:
            mysql(statement)
        self.assertEqual(self.count("item_instance", "guid=90004"), 1)  # linked but owned: left for a person to look at
        for table in ROLLED:
            self.assertEqual(self.count(table, "item_guid=90004"), 1, table)  # and its rolled rows stay with it
        self.assertEqual(self.count("item_instance", "guid=90005"), 1)
        self.assertEqual(self.count("character_inventory", "guid=5001"), 1)

    def test_deleting_a_character_leaves_the_stash_alone(self):
        statements = character_delete_statements()
        self.assertEqual(len(statements), 2)
        self.assertIn("owner_guid", statements[1])
        for statement in statements:
            mysql(statement.format(guid=5001))
        self.assertEqual(self.count("dc_account_stash"), 3)
        self.assertEqual(self.count("dc_account_stash_item"), 4)
        for guid in (90001, 90002, 90003):
            self.assertEqual(self.count("item_instance", f"guid={guid}"), 1)
        self.assertEqual(self.count("item_instance", "guid=90005"), 0)  # the character's own item did go


    def test_the_character_check_is_not_vacuous(self):
        """A statement that did reach parked rows (owner 0) is seen by the same assertions."""
        mysql("DELETE FROM item_instance WHERE owner_guid = 0")
        self.assertEqual(self.count("item_instance", "guid=90001"), 0)
        self.assertEqual(self.count("dc_account_stash_item", "item_guid=90001"), 1)  # a link with no row: a lost item


class WhoCanDeleteAnAccount(unittest.TestCase):
    """The only account deletion in the core is AccountMgr::DeleteAccount, and the hook is its own."""

    def test_the_hook_is_registered_for_the_account_delete_event_and_nothing_else_deletes_rows(self):
        text = SOURCE.read_text()
        self.assertRegex(text, r'AccountScript\("dc_stash_account", \{ACCOUNTHOOK_ON_BEFORE_ACCOUNT_DELETE\}\)')
        self.assertIn("new StashAccount();", text)
        # character hooks: the player script is the logout hook and drops a cache only
        player = text[text.index("class StashPlayer"):]
        self.assertIn("PLAYERHOOK_ON_LOGOUT", player)
        self.assertNotIn("DELETE", player[:player.index("RegisterScripts")])
        # the rows are deleted in exactly one place: the sweep, and the dangling-link repair
        deleting = [m.start() for m in re.finditer(r'"DELETE ', text)]
        sweep = text[text.index("void AccountSweep("):text.index("class StashAccount")]
        outside = [pos for pos in deleting if not (text.index("void AccountSweep(") <= pos < text.index("class StashAccount"))]
        names = {text[max(0, pos - 80):pos + 70].replace("\n", " ") for pos in outside}
        # ClearSlot (a move), the dangling-link repair in LoadItems, nothing else
        for fragment in names:
            self.assertTrue("dc_account_stash_item" in fragment, fragment)
        self.assertIn("DELETE d FROM", sweep)

    def test_the_core_has_one_account_delete_path_and_it_runs_the_hook(self):
        core = ROOT / "azerothcore-wotlk/src/server/game/Accounts/AccountMgr.cpp"
        if not core.is_file():
            self.skipTest("the pinned core tree is not here")
        text = core.read_text()
        body = extract(text, "AccountOpResult AccountMgr::DeleteAccount(")
        self.assertIn("sScriptMgr->OnBeforeAccountDelete(accountId);", body)
        # it is called from one command; the website holds no account delete of its own (docs/test sheet)
        commands = (ROOT / "azerothcore-wotlk/src/server/scripts/Commands/cs_account.cpp").read_text()
        self.assertEqual(commands.count("AccountMgr::DeleteAccount("), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
