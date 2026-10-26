"""diablocraft-dm9vg.20: the rift credit creature 910015 is the two rift bars' alone.

dc_rifts.cpp's loadBar reads `quest_template WHERE RequiredNpcOrGo1=910015` once untimed (the Nephalem bar) and once timed
(the Greater bar) and throws unless each is exactly one row; its sweep, no-abandon rule and XP zeroing take every quest on
910015. The bounty quests (bounties_0005, dm9vg.17) used 910015 untimed, so loading threw and rifts went off on dev. They
were moved by bounties_0006, but each regenerated bounties_0005 was reapplied by the updater after it (bounties_0006 unchanged,
so not again) and put them back (diablocraft-l2hsp): bounties_0005 now names the bounty credit creature itself.

1. Replay: every `quest_template` statement of the world migrations, in the updater's filename order, on a disposable
   MySQL (test_account_economy_sql.isolated) with the core's own table. Only the two bars end on 910015, one untimed and
   one timed; the bounty quests end on the bounty credit creature, also with bounties_0005 reapplied last (a regenerated
   file, as dev's updater does it). bounties_0006 alone, on a stock row, makes that creature. With bounties_0005 on
   910015 (the base) the reapplied replay fails.
2. Generator: bounties_0006 is the render and its mirror; its entry is used by nothing but it and bounties_0005; no bounty
   quest names 910015.
"""
import re
import subprocess
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_bounties as G

UPDATES = G.MODULE / "data/sql/db-world/updates"
CREDIT_SQL = UPDATES / G.CREDIT
BASE = G.MODULE.parent / "azerothcore-wotlk/data/sql/base/db_world"
RIFT_CREDIT, BARS = 910015, {910020: "untimed", 910023: "timed"}   # rifts_0011 / rifts_0019: the Nephalem and Greater bar
QUEST_STATEMENT = re.compile(r"^(INSERT INTO|REPLACE INTO|DELETE FROM|UPDATE) `quest_template`\s")


def table(name):
    """The core's own CREATE TABLE for `name`, from its base SQL."""
    text = (BASE / f"{name}.sql").read_text(encoding="utf-8")
    return re.search(rf"CREATE TABLE `{name}` \(.*?\) ENGINE=[^;]*;", text, re.S).group(0)


def statements(text):
    """The file's statements, comment lines dropped."""
    body = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("--"))
    return [s.strip() for s in re.split(r";\s*\n", body + "\n") if s.strip()]


def quest_statements(replace=None, again=None):
    """Every quest_template statement of the world migrations, in filename order (the updater's, test_migration_numbers).
    `replace` = (file name, old, new) mutates one file first; `again` names a file applied once more at the end, as the
    updater reapplies a changed file after the unchanged ones."""
    out, last = [], []
    for path in sorted(UPDATES.glob("*.sql")):
        text = path.read_text(encoding="utf-8")
        if replace and path.name == replace[0]:
            assert replace[1] in text, replace
            text = text.replace(replace[1], replace[2])
        found = [s + ";" for s in statements(text) if QUEST_STATEMENT.match(s)]
        out += found
        if path.name == again:
            last = found
    assert last or not again, again
    return "\n".join(out + last) + "\n"


class Replay(unittest.TestCase):
    def test_only_the_two_rift_bars_use_the_rift_credit(self):
        from test_account_economy_sql import MYSQL, isolated
        stub_creature = table("creature_template") + "\n" + table("creature_template_model") + "\n" + (
            "INSERT INTO creature_template (entry, name, subname, npcflag, lootid, ScriptName) "
            "VALUES (2840, 'Stock', 'x', 1, 2840, 'npc_stock');\n"
            "INSERT INTO creature_template_model (CreatureID, Idx, CreatureDisplayID) VALUES (2840, 0, 1);\n"
            # a stale model on the entry (a database that had something there) goes
            f"INSERT INTO creature_template_model (CreatureID, Idx, CreatureDisplayID) VALUES ({G.CREDIT_CREATURE}, 0, 1);\n")

        def body(port):
            command = [str(MYSQL), "--no-defaults", "--protocol=tcp", "--host=127.0.0.1", f"--port={port}", "--user=root",
                       "--batch", "--raw", "--skip-column-names", "--default-character-set=utf8mb4"]

            def mysql(text, database=None):
                done = subprocess.run(command + ([f"--database={database}"] if database else []), input=text, text=True,
                                      capture_output=True, encoding="utf-8")
                return done.returncode, done.stdout.rstrip("\n"), done.stderr

            def replay(name, replace=None, again=None):
                mysql(f"CREATE DATABASE {name} CHARACTER SET utf8mb4;")
                code, _out, err = mysql(table("quest_template") + "\n" + quest_statements(replace, again), name)
                self.assertEqual(code, 0, err)
                return (mysql(f"SELECT ID, TimeAllowed>0 FROM quest_template WHERE RequiredNpcOrGo1={RIFT_CREDIT} ORDER BY ID",
                              name)[1],
                        mysql("SELECT COUNT(*), MIN(RequiredNpcOrGo1), MAX(RequiredNpcOrGo1) FROM quest_template "
                              f"WHERE ID BETWEEN {G.QUEST_ENTRIES.start} AND {G.QUEST_ENTRIES.stop - 1}", name)[1])

            bars, bounties = replay("credit_real")
            self.assertEqual(bars, "\n".join(f"{q}\t{int(kind == 'timed')}" for q, kind in sorted(BARS.items())),
                             "only the Nephalem (untimed) and Greater (timed) bars may use 910015 (dc_rifts.cpp loadBar)")
            count, low, high = bounties.split("\t")
            self.assertGreater(int(count), 0, "no bounty quest replayed")
            self.assertEqual((int(low), int(high)), (G.CREDIT_CREATURE, G.CREDIT_CREATURE))
            # dev's order (l2hsp): a regenerated bounties_0005 reapplied after the unchanged bounties_0006
            self.assertEqual(replay("credit_again", again=G.QUESTS), (bars, bounties))
            # the mutant: bounties_0005 on the rifts' credit, the base's state, reapplied last
            mutant = replay("credit_mutant", (G.QUESTS, f", {G.CREDIT_CREATURE}, ", f", {RIFT_CREDIT}, "), G.QUESTS)
            self.assertNotEqual(mutant[0], bars, "mutant survived: bounties_0005 names the bounty credit creature")

            # the creature, made by bounties_0006 alone (it sorts before rifts_0011, so it is cloned from stock 2840)
            mysql("CREATE DATABASE credit_creature CHARACTER SET utf8mb4;")
            self.assertEqual(mysql(stub_creature + table("quest_template"), "credit_creature")[0], 0)
            for _ in range(2):   # twice: the file re-applies cleanly
                code, _out, err = mysql(CREDIT_SQL.read_text(encoding="utf-8"), "credit_creature")
                self.assertEqual(code, 0, err)
            self.assertEqual(mysql("SELECT name, subname, npcflag, lootid, ScriptName, AIName FROM creature_template "
                                   f"WHERE entry={G.CREDIT_CREATURE}", "credit_creature")[1], "Bounty Progress\t\t0\t0\t\t")
            self.assertEqual(mysql(f"SELECT COUNT(*) FROM creature_template_model WHERE CreatureID={G.CREDIT_CREATURE}",
                                   "credit_creature")[1], "0", "never spawned, no model")

        isolated(body)


class Generator(unittest.TestCase):
    def test_the_migration_is_the_render_and_its_mirror(self):
        sql = G.render_quest_credit()
        self.assertEqual(CREDIT_SQL.read_text(encoding="utf-8"), sql)
        self.assertEqual((G.MODULE / "data/generated" / G.CREDIT).read_text(encoding="utf-8"), sql)
        self.assertNotIn(G.CREDIT, (G.MODULE / "data/sql/applied_migrations.csv").read_text(encoding="utf-8"))

    def test_the_entry_is_its_own(self):
        self.assertNotEqual(G.CREDIT_CREATURE, RIFT_CREDIT)
        word = re.compile(rf"\b{G.CREDIT_CREATURE}\b")
        users = sorted(p.relative_to(G.MODULE).as_posix() for folder in ("data", "src")
                       for p in (G.MODULE / folder).rglob("*") if p.is_file() and p.suffix in (".sql", ".csv", ".cpp", ".h")
                       and word.search(p.read_text(encoding="utf-8", errors="replace")))
        self.assertEqual(users, sorted(f"{folder}/{name}" for folder in ("data/generated", "data/sql/db-world/updates")
                                       for name in (G.QUESTS, G.CREDIT)))

    def test_no_bounty_quest_names_the_rift_credit(self):
        rift = re.compile(rf"\b{RIFT_CREDIT}\b")
        for sql in (G.render_quests(), (UPDATES / G.QUESTS).read_text(encoding="utf-8"),
                    (G.MODULE / "data/generated" / G.QUESTS).read_text(encoding="utf-8")):
            self.assertIsNone(rift.search(sql), "a bounty quest on the rifts' credit creature (dc_rifts.cpp loadBar)")
            self.assertIn(f"'', {G.CREDIT_CREATURE}, 1, ", sql)


if __name__ == "__main__":
    unittest.main()
