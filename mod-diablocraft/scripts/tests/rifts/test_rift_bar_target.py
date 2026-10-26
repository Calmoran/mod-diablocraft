"""diablocraft-owe7u: the rift progress target is 30,000 (300 D3 points), for the Nephalem and the Greater Rift quest.

Ruling 2026-10-16 (decisions.md): rift_quests.csv's bar_hundredths goes from 65,000 to 30,000 for 910020 and 910023.
rifts_0019_one_bar.sql set 65,000 and is applied (live and dev); it stays as it shipped, and a new numbered migration,
rifts_0032_bar_target.sql, sets the new count.

1. Sheet: both quest rows say 30,000, inside the core's 16-bit quest counter.
2. Frozen: rifts_0019 still carries 65,000 and its applied hash (applied_migrations.csv); the generator's render of it does
   not follow the sheet, so a rerun neither warns nor rewrites it.
3. New: rifts_0032 is the generator's render of the sheet and its data/generated mirror; it updates exactly the two bar
   quests; replaying every world migration's `RequiredNpcOrGoCount1` updates in the updater's filename order ends on 30,000.
4. Readers: the run's bar is read back from quest_template (no number in code), so nothing else holds 65,000 or 30,000.
"""
import csv
import hashlib
import re
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_rifts as G

MODULE = Path(__file__).resolve().parents[3]
UPDATES = MODULE / "data/sql/db-world/updates"
NEW_BAR, OLD_BAR, BARS = 30000, 65000, (910020, 910023)
COUNTER_MAX = 65535                                            # QuestDef.h CreatureOrGOCount is a uint16


def read(path):
    return Path(path).read_text(encoding="utf-8")


# --- 1. the sheet ---------------------------------------------------------------------------------------------------------
sheet = [r for r in csv.DictReader((MODULE / "data/d3/rift_quests.csv").open(encoding="utf-8", newline="")) if r["kind"] == "quest"]
assert [(int(r["entry_id"]), r["mode"], int(r["bar_hundredths"])) for r in sheet] == [(910020, "nr", NEW_BAR), (910023, "gr", NEW_BAR)], sheet
assert NEW_BAR <= COUNTER_MAX

# --- 2. rifts_0019 stays as it shipped -----------------------------------------------------------------------------------
old = read(UPDATES / "rifts_0019_one_bar.sql")
assert [int(n) for n in re.findall(r"RequiredNpcOrGoCount1` = (\d+)", old)] == [OLD_BAR, OLD_BAR], old
assert str(NEW_BAR) not in old
applied = {row[0]: row[1] for row in csv.reader((MODULE / "data/sql/applied_migrations.csv").open(encoding="utf-8", newline="")) if row}
assert hashlib.sha1((UPDATES / "rifts_0019_one_bar.sql").read_bytes()).hexdigest().upper() == applied["db-world/updates/rifts_0019_one_bar.sql"]
quests, _ = G.read_quests()
assert G.bar_sql(quests) == old, "the render of rifts_0019 follows the sheet; it must keep the 65,000 it shipped"
assert read(MODULE / "data/generated/rift_one_bar.sql") == old

# --- 3. rifts_0032 ---------------------------------------------------------------------------------------------------------
new = read(UPDATES / G.BAR_TARGET_MIGRATION)
assert G.BAR_TARGET_MIGRATION == "rifts_0032_bar_target.sql"
assert G.bar_target_sql(quests) == new and read(MODULE / "data/generated/rift_bar_target.sql") == new
updates = re.findall(r"^UPDATE `quest_template` SET (.*?) WHERE `ID` = (\d+);$", new, re.M)
assert updates == [(f"`RequiredNpcOrGoCount1` = {NEW_BAR}", str(i)) for i in BARS], updates
assert not re.search(r"\b(INSERT|DELETE|REPLACE)\b", new)      # a count change only: no relation, template or addon row moves

count = {}
for path in sorted(UPDATES.glob("*.sql")):                     # the updater's order
    for value, entry in re.findall(r"^UPDATE `quest_template` SET `RequiredNpcOrGoCount1` = (\d+) WHERE `ID` = (\d+);$", read(path), re.M):
        count[int(entry)] = (int(value), path.name)
assert {i: count[i] for i in BARS} == {i: (NEW_BAR, G.BAR_TARGET_MIGRATION) for i in BARS}, count

# --- 4. the readers hold no copy of the number ---------------------------------------------------------------------------
for path in sorted((MODULE / "src/rifts").glob("*.[ch]*")):
    code = "\n".join(line.split("//")[0] for line in read(path).splitlines())
    assert not re.search(r"\b(65000|30000)\b", code), path.name   # 65535 is the core's counter, not a bar
loader = read(MODULE / "src/rifts/dc_rift_scripts.cpp")
assert "SELECT ID, RequiredNpcOrGoCount1 FROM quest_template" in loader
assert "rift.requiredUnits = (greater ? greaterQuest : nephalemQuest).units;" in read(MODULE / "src/rifts/dc_rift_open.cpp")

print(f"PASS: both rift quests count {NEW_BAR} (rifts_0032 after the applied rifts_0019 at {OLD_BAR}); no reader holds the number")
