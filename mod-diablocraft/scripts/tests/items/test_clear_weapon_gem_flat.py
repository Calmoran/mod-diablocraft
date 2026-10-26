"""diablocraft-tdddf: items_0011 clears the saved weapon-gem flat damage, and the next login counts the gem once.

A character saved before the weapon-gem fix holds a Source::Gems WeaponFlatDamage contribution for each socketed
weapon Ruby in dc_character_stats.contributions; Load restores it, so the swing stays doubled until it is removed.

What runs, end to end:
1. Save: the pre-fix `Apply` (today's dc_items_equip.cpp with the fix's `continue` taken back out) equips a 100-200 sword
   with a Royal Ruby, next to an item Strength affix, a legendary gem's stat and a Paragon point; the live
   contributions go through the production `Serialize` (dc_common.cpp). That is the doubled character's row.
2. Migrate: on the fixture mysqld, a scratch database built from stats_0001 + stats_0002 gets that row, a row with
   no gem, a row longer than MySQL's default group_concat_max_len, and a row whose tokens read "2 27" off a
   contribution boundary; items_0011 runs twice.
3. Login: the production `DeserializeContributions` and `DropRebuiltSources` load each row, OnPlayerLogin's
   cache reset runs, then today's `Apply` re-equips the sword; the hit's `WeaponRange` + `WithFlatDamage` is read.
The doubled row reads 100 + 2X before the migration and 100 + X after it; every other contribution is unchanged.
Also checked against the sources: the ids the migration names, the serial format, and that nothing after the fix
writes a Gems WeaponFlatDamage(Delta) contribution while the login rebuilds the weapon cache.
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import fixture_db  # noqa: E402
import harness_env  # noqa: E402
import os
import re
import shutil
import subprocess
import tempfile
import unittest

import test_weapon_gem_flat_once as once  # noqa: E402  (its Apply harness, reused)

MODULE = Path(__file__).resolve().parents[3]
UPDATES = MODULE / "data/sql/db-characters/updates"
MIGRATION = UPDATES / "items_0011_clear_weapon_gem_flat.sql"
COMMON_H = MODULE / "src/common/dc_common.h"
COMMON_CPP = MODULE / "src/common/dc_common.cpp"
GEM_POWERS = MODULE / "src/combat/dc_gem_powers.cpp"
FIXED_LINE = 'if(statId=="wpnphy") { weaponDamage+=value; continue; }'
PRE_FIX_LINE = 'if(statId=="wpnphy") weaponDamage+=value;'
SCRATCH = "dc_scratch_tdddf_%d" % os.getpid()


def enum_index(name, member):
    body = re.search(r"enum class %s\b[^{]*\{(.*?)\};" % name, COMMON_H.read_text(encoding="utf-8"), re.S).group(1)
    names = [w for w in re.findall(r"\b([A-Z]\w*)\b", re.sub(r"//[^\n]*", "", body)) if w != "Count"]
    return names.index(member)


def cross_check():
    sql = MIGRATION.read_text(encoding="utf-8")
    gems, flat, delta = enum_index("Source", "Gems"), enum_index("Stat", "WeaponFlatDamage"), \
        enum_index("Stat", "WeaponFlatDamageDelta")
    assert "= '%d'" % gems in sql and "IN ('%d', '%d')" % (flat, delta) in sql, (gems, flat, delta)
    serialize = once.definition("std::string Serialize(std::vector<Contribution> const& contributions)",
                                COMMON_CPP.read_text(encoding="utf-8"))
    assert '"1 " << contributions.size()' in serialize and serialize.count("<< ' ' <<") == 5, serialize
    assert "LIKE '1 %'" in sql and "(n - 3) DIV 6" in sql
    # After the fix no writer is left: the item gem branch skips the sheet, the legendary gems name other stats.
    items = once.items_text()
    assert items.count(FIXED_LINE) == 1, "the weapon-gem fix is not in dc_items_equip.cpp"
    assert "WeaponFlatDamage" not in GEM_POWERS.read_text(encoding="utf-8")
    # The rebuild: login drops the weapon cache and re-applies every worn item.
    login = once.definition("void OnPlayerLogin(Player* player) override", items)
    assert "weaponExtra.erase(" in login and "Apply(player, player->GetItemByPos(INVENTORY_SLOT_BAG_0, slot), true)" in login
    load = (MODULE / "src/stats/dc_stats.cpp").read_text(encoding="utf-8")
    assert "DropRebuiltSources(state.contributions);" in load and "DeserializeContributions(" in load


def harness(items_file):
    """The Apply harness of test_weapon_gem_flat_once with a save/login main instead of its Run."""
    once.ITEMS = items_file
    head = once.program([])
    head = head[:head.index("void Run(std::uint32_t entry")]
    return (head.replace('#include "dc_common.h"\n', '#include "dc_common.h"\n#include "dc_numeric_data.h"\n'
                         '#include <iostream>\n', 1)
            + "namespace DC::NumericData {\n"
            "double Rule(char const*) { return 0; } unsigned MaximumLevel() { return 70; }\n"
            "double BaseFury(unsigned) { return 0; } BlockTuning Block() { return {}; }\n}\n"
            "Items::Instance Sword(std::uint32_t entry)\n{\n"
            "    Items::Instance sword; sword.itemGuid = 77; sword.baseItem = 900;\n"
            "    Items::Affix socket; socket.seq = 1; socket.kind = \"socket\";\n"
            "    Items::Affix gem; gem.seq = 2; gem.kind = \"gem\"; gem.affixId = \"ruby\"; gem.gemEntry = entry; gem.parentSeq = 1;\n"
            "    Items::Affix strength; strength.seq = 3; strength.kind = \"primary\"; strength.affixId = \"str\"; strength.value = 400;\n"
            "    sword.affixes = {socket, gem, strength};\n"
            "    return sword;\n}\n"
            "int main(int argc, char** argv)\n{\n"
            "    std::uint32_t const entry = std::stoul(argv[2]); double const value = std::stod(argv[3]);\n"
            "    Items::gemEffects = {{entry, {{\"weapon\", {\"wpnphy\", \"Ruby\", value}}}}};\n"
            "    Items::socketed = Sword(entry);\n"
            "    Player player; Item item; player.weapon = &item;\n"
            "    if (std::string(argv[1]) == \"save\")\n    {\n"
            "        Items::Apply(&player, &item, true);\n"
            "        Stats::AddContribution(0, {Source::Gems, Stat::CritChance, 0x4C47454D00000005ull, 5, Bucket::Flat, Element::Physical});\n"
            "        Stats::AddContribution(0, {Source::Paragon, Stat::Vitality, 3, 5, Bucket::Flat, Element::Physical});\n"
            "        std::cout << Serialize(Stats::live) << '\\n';\n        return 0;\n    }\n"
            "    std::string saved; std::getline(std::cin, saved);\n"
            "    Stats::live = DeserializeContributions(saved);\n"
            "    DropRebuiltSources(Stats::live);\n"
            "    Items::weaponExtra.erase(player.GetGUID().GetRawValue());\n"
            "    Items::Apply(&player, &item, true);\n"
            "    StatSheet worn = Stats::Sheet();\n"
            "    auto range = Combat::WithFlatDamage(Combat::WeaponRange(&player, false), worn);\n"
            "    std::printf(\"HIT %.9g %.9g STR %.9g CRIT %.9g\\n\", range.first, range.second, worn[Stat::Strength],\n"
            "                worn[Stat::CritChance]);\n"
            "    return 0;\n}\n")


def build(work, name, source):
    cpp = work / "common" / (name + ".cpp")
    cpp.write_text(source, encoding="utf-8")
    binary = work / name
    built = subprocess.run([once.CXX, "-std=c++20", "-O1", "-I", str(work / "common"), "-o", str(binary), str(cpp),
                            str(COMMON_CPP)], capture_output=True, text=True)
    assert built.returncode == 0, "the %s harness did not compile:\n%s" % (name, built.stderr[-4000:])
    return binary


def migrate(rows):
    """{guid: contributions} after items_0011 runs twice on a scratch copy of dc_character_stats."""
    mysql, defaults = fixture_db.mysql_and_defaults([])
    inserts = ",".join("(%d,70,1,0,'',%s)" % (guid, "'%s'" % text) for guid, text in rows.items())
    sql = ("DROP DATABASE IF EXISTS %s; CREATE DATABASE %s; USE %s;\n" % (SCRATCH, SCRATCH, SCRATCH)
           + (UPDATES / "stats_0001_character_stats.sql").read_text(encoding="utf-8") + "\n"
           + (UPDATES / "stats_0002_current_life.sql").read_text(encoding="utf-8") + "\n"
           + "INSERT INTO dc_character_stats (guid,level,max_life,armor,sheet,contributions) VALUES %s;\n" % inserts
           + MIGRATION.read_text(encoding="utf-8") + "\n" + MIGRATION.read_text(encoding="utf-8") + "\n"
           + "SELECT guid, contributions FROM dc_character_stats ORDER BY guid;\n")
    try:
        ran = subprocess.run([mysql, "--defaults-file=" + defaults, "--no-login-paths", "--batch", "--skip-column-names"],
                             input=sql, capture_output=True, text=True)
    finally:
        subprocess.run([mysql, "--defaults-file=" + defaults, "--no-login-paths", "-e", "DROP DATABASE IF EXISTS " + SCRATCH],
                       capture_output=True, text=True)
    assert ran.returncode == 0, ran.stderr
    return {int(line.split("\t")[0]): line.split("\t")[1] for line in ran.stdout.splitlines()}


def entries(text):
    tokens = text.split()
    assert tokens[0] == "1" and len(tokens) == 2 + 6 * int(tokens[1]), text
    return [tuple(tokens[i:i + 6]) for i in range(2, len(tokens), 6)]


def run():
    if not once.CXX:
        raise unittest.SkipTest("no C++ compiler")
    cross_check()
    entry, value = max(once.weapon_gems(), key=lambda gem: gem[1])
    fixed_source = once.ITEMS
    items = once.items_text()
    with tempfile.TemporaryDirectory(prefix="dc-gem-clear-") as folder:
        work = Path(folder)
        (work / "common").mkdir()
        (work / "combat").mkdir()
        for header in (MODULE / "src/common").glob("*.h"):
            shutil.copy(header, work / "common" / header.name)
        shutil.copy(MODULE / "src/combat/dc_weapon_flat.h", work / "combat/dc_weapon_flat.h")
        pre_fix = work / "dc_items_pre_fix.cpp"
        pre_fix.write_text(items.replace(FIXED_LINE, PRE_FIX_LINE), encoding="utf-8")
        try:
            saver = build(work, "save", harness(pre_fix))
            loginer = build(work, "login", harness(fixed_source))
        finally:
            once.ITEMS = fixed_source
        args = [str(entry), "%r" % value]
        saved = harness_env.run([str(saver), "save", *args], capture_output=True, text=True, check=True).stdout.strip()
        gem_rows = [e for e in entries(saved) if e[0] == "2" and e[1] == "27"]
        assert len(gem_rows) == 1 and float(gem_rows[0][3]) == value, "the pre-fix save lost its gem row: " + saved

        long_row = "1 %d %s %s" % (201, " ".join("1 0 %d 1.25 0 0" % (1000 + i) for i in range(200)), " ".join(gem_rows[0]))
        trap = "1 2 1 2 27 7 0 0 2 0 9 1 0 0"  # "2 27" read off a boundary: Intelligence id 27, then a Gems Strength
        no_gem = "1 1 1 0 5 10 0 0"
        after = migrate({1: saved, 2: long_row, 3: trap, 4: no_gem, 5: "1 0"})

        kept = [e for e in entries(saved) if e not in gem_rows]
        assert entries(after[1]) == kept, (saved, after[1])
        assert entries(after[2]) == entries(long_row)[:200], "the long row was cut or kept its gem row"
        assert (after[3], after[4], after[5]) == (trap, no_gem, "1 0"), after

        def login(text):
            out = harness_env.run([str(loginer), "login", *args], input=text + "\n", capture_output=True, text=True,
                                  check=True).stdout.split()
            return tuple(float(out[i]) for i in (1, 2, 4, 6))

        before_hit, after_hit = login(saved), login(after[1])
    assert before_hit[:2] == (100 + 2 * value, 200 + 2 * value), "the saved row should still double: %r" % (before_hit,)
    assert after_hit[:2] == (100 + value, 200 + value), "after the clear and a login: %r" % (after_hit,)
    assert after_hit[2:] == before_hit[2:] == (400, 5), (before_hit, after_hit)  # Strength and the legendary gem stay
    print("PASS clear weapon gem flat: a character saved with a %g Ruby hits %g-%g; after items_0011 and a login it "
          "hits %g-%g (the gem once); other contributions, a 201-entry row, a boundary trap and gemless rows "
          "unchanged; a rerun changes nothing" % (value, *before_hit[:2], *after_hit[:2]))


def early_table():
    """items_0011 sorts before stats_0001, so items_0004 creates dc_character_stats first on an empty database
    (test_fresh_characters_db runs the order). Its statement must stay stats_0001's, byte for byte, or a fresh
    realm and an upgraded one end with different tables."""
    early = UPDATES / "items_0004_character_stats_table.sql"
    stats = UPDATES / "stats_0001_character_stats.sql"
    assert early.name < MIGRATION.name < stats.name, (early.name, MIGRATION.name, stats.name)
    body = "".join(line for line in early.read_text(encoding="utf-8").splitlines(True) if not line.startswith("--"))
    assert body == stats.read_text(encoding="utf-8"), "items_0004's CREATE drifted from stats_0001's"
    print("PASS clear weapon gem flat: items_0004 creates dc_character_stats with stats_0001's exact statement, "
          "before items_0011 reads it")


class ClearWeaponGemFlat(unittest.TestCase):
    def test_early_table(self):
        early_table()

    def test_clear(self):
        run()


if __name__ == "__main__":
    early_table()
    run()
