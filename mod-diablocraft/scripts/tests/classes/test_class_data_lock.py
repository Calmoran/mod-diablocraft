"""diablocraft-mage-login-hang: no dc_classes.cpp lock scope calls back out.

A new level-1 Mage hung the world thread on its first login (30 s watchdog,
2026-09-23). OnPlayerLogin -> GrantShells held dataMutex, a plain std::mutex,
around Player::addSpell. The core casts a passive spell as it is learned
(Player::_addSpell), and Evocation's passive shell carries the dc_wizard_buff
AuraScript, whose Applied -> Refresh -> Passives::Has -> Classes::Playable
locks dataMutex again on the same thread. The Barbarian's passives carry no
script, which is why a Warrior never hung.

What this proves, and how:

  * **Every dataMutex scope is a lookup.** Each `lock_guard<std::mutex>
    lock(dataMutex)` scope in dc_classes.cpp is cut out by brace matching, and
    none may call a method through a pointer (`->name(`, the only way into the
    Player, the core or a script; reading a field such as `entry->spellId` is
    fine) or call a function of this file that takes dataMutex itself.
  * **The check bites.** The same check runs on the pre-fix GrantShells and
    must fail it.
  * **The precondition is live.** A class passive shell in the generated SQL
    is bound to an AuraScript, so learning one does run module code.

What it does not prove: anything about the running server. It is a static
check of one file; a new Mage's first login is the live test.

    python mod-diablocraft/scripts/tests/classes/test_class_data_lock.py
"""

import csv
import re
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[3]
SOURCE = MODULE / "src" / "classes" / "dc_classes.cpp"
GENERATED = MODULE / "data" / "generated"

LOCK = "std::lock_guard<std::mutex> lock(dataMutex);"
# Const Player getters that read a field and run no script. Anything else
# called through a pointer under the lock fails the check.
PURE_GETTERS = {"getClass", "GetLevel"}

# GrantShells as it was at 9795150, the binary that hung.
BEFORE_FIX = """
void GrantShells(Player* player)
{
    std::vector<std::uint32_t> added;
    {
        std::lock_guard<std::mutex> lock(dataMutex);
        auto const own = classShells.find(ClassId(player));
        for (std::uint32_t spellId : own == classShells.end() ? std::vector<std::uint32_t>{} : own->second)
            if (!player->HasSpell(spellId) && player->addSpell(spellId, SPEC_MASK_ALL, true, false, false))
                added.push_back(spellId);
    }
}
"""


def scopes(source):
    """The text from each dataMutex lock to the end of the block holding it."""
    found = []
    for match in re.finditer(re.escape(LOCK), source):
        depth, end = 0, match.end()
        while end < len(source):
            char = source[end]
            if char == "{":
                depth += 1
            elif char == "}":
                if depth == 0:
                    break
                depth -= 1
            end += 1
        found.append(source[match.end():end])
    return found


def lockers(source):
    """Names of the functions in this file that take dataMutex."""
    names = set()
    for match in re.finditer(re.escape(LOCK), source):
        head = source[:match.start()]
        signature = re.findall(r"\n[\w:<>,\s*&]+?\b(\w+)\(([^;{}]*)\)\s*(?:const\s*)?\{", head)
        if signature:
            names.add(signature[-1][0])
    return names


def violations(source):
    names = lockers(source)
    bad = []
    for scope in scopes(source):
        code = re.sub(r"//[^\n]*", "", scope)
        if set(re.findall(r"->\s*(\w+)\s*\(", code)) - PURE_GETTERS:
            bad.append(("calls out", code.strip()))
        for name in names:
            if re.search(r"\b%s\s*\(" % re.escape(name), code):
                bad.append(("re-locks through " + name, code.strip()))
    return bad


class DataLock(unittest.TestCase):
    def test_every_scope_is_a_lookup(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertGreaterEqual(len(scopes(source)), 10)
        self.assertIn("Playable", lockers(source))
        self.assertEqual(violations(source), [])

    def test_the_hanging_grant_fails_the_check(self):
        self.assertTrue(any(kind == "calls out" and "addSpell" in code
                            for kind, code in violations(BEFORE_FIX)))

    def test_a_class_passive_shell_runs_a_script_when_learned(self):
        rows = {int(row["spell_id"]): row for row in
                csv.DictReader((GENERATED / "spell_shells.csv").open(encoding="utf-8-sig"))}
        sql = (GENERATED / "spell_shells.sql").read_text(encoding="utf-8")
        bound = {(rows[int(spell)]["name"], script) for spell, script in re.findall(r"\((\d+),'(\w+)'\)", sql)
                 if int(spell) in rows and rows[int(spell)]["kind"] == "passive"}
        self.assertIn(("Evocation", "dc_wizard_buff"), bound)


if __name__ == "__main__":
    unittest.main()
