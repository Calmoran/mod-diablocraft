#!/usr/bin/env python3
"""A character made at the starting level earns its reach-level achievements (diablocraft-egn4j).

The client keeps the achievements window shut until a character has any achievement. Player::Create checks the
criteria at level 1; dc_world.cpp's creation path then raises the level with SetLevel, which (unlike GiveLevel) never
updates ACHIEVEMENT_CRITERIA_TYPE_REACH_LEVEL. These checks read the core to confirm that split still holds, and the
module source for the fix: the update right after the creation SetLevel, before any save, and a re-check scheduled on
every login for characters made before the fix. Single-rule mutants of the source must fail them.
"""
import re
from pathlib import Path

MODULE = Path(__file__).resolve().parents[3]
CORE = MODULE.parent / "azerothcore-wotlk/src/server/game"
WORLD = MODULE / "src/common/dc_world.cpp"
UPDATE = "player->UpdateAchievementCriteria(ACHIEVEMENT_CRITERIA_TYPE_REACH_LEVEL);"


def body(text, marker):
    start = text.index(marker)
    end, depth = text.index("{", start) + 1, 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


def test_the_core_updates_reach_level_only_in_give_level():
    player = (CORE / "Entities/Player/Player.cpp").read_text()
    assert "UpdateAchievementCriteria(ACHIEVEMENT_CRITERIA_TYPE_REACH_LEVEL);" in body(player, "void Player::GiveLevel(")
    calls = [m.start() for m in re.finditer(r"ACHIEVEMENT_CRITERIA_TYPE_REACH_LEVEL", player)]
    assert len(calls) == 1, "the core now updates reach-level somewhere else too: re-read the fix"
    assert "CheckAllAchievementCriteria();" in body(player, "bool Player::Create(")


def check(text):
    start = text.index("        if (creation)\n        {\n            // Player::Create already owns a map")
    creation = text[start:text.index("        else\n", start)]
    assert creation.index("player->SetLevel(startingLevel);") < creation.index(UPDATE), "no reach-level update after SetLevel"
    login = body(text, "void OnPlayerLogin(Player* player) override")
    assert re.search(r"player->m_Events\.AddEventAtOffset\(\[player\] \{ " + re.escape(UPDATE) + r" \}, 1s\);", login), \
        "no reach-level re-check at login"


def test_the_fix():
    check(WORLD.read_text())


MUTANTS = [
    ("no update at creation", "            " + UPDATE + "\n            player->InitStatsForLevel();", "            player->InitStatsForLevel();"),
    ("the update before SetLevel", "            player->SetLevel(startingLevel);\n", "            " + UPDATE + "\n            player->SetLevel(startingLevel);\n"),
    ("no login re-check", "        player->m_Events.AddEventAtOffset([player] { " + UPDATE + " }, 1s);\n", ""),
]


def test_mutants_are_killed():
    base = WORLD.read_text()
    for what, old, new in MUTANTS:
        assert base.count(old) == 1, "mutant target moved: " + what
        mutant = base.replace(old, new)
        if what == "the update before SetLevel":
            mutant = mutant.replace("            // achievements window shut. The start's own SaveToDB stores what this earns.\n"
                                    "            " + UPDATE + "\n", "            // achievements window shut. The start's own SaveToDB stores what this earns.\n", 1)
        try:
            check(mutant)
        except (AssertionError, ValueError):
            print("PASS mutant killed:", what)
            continue
        raise AssertionError("mutant survived: " + what)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
