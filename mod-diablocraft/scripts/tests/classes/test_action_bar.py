"""Compile production WriteActionBar and exercise the eight server-owned buttons."""

import csv
import os
from pathlib import Path
import shutil
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env
import time


ROOT = Path(__file__).resolve().parents[4]
SOURCE = (ROOT / "mod-diablocraft/src/classes/dc_classes.cpp").read_text(encoding="utf-8")
OUT = ROOT / "azerothcore-wotlk/build/_agent-scratch/scripts/action-bar-tests"


def toolchain():
    """cmake from PATH, the host generator, and per-OS configure/build/run.

    This hardcoded C:/Program Files/CMake/bin/cmake.exe and the Visual Studio
    generator, which stopped working when the project moved to Linux. Windows
    still gets the Visual Studio project and the Release subfolder; on Linux the
    default generator writes the binary directly in build/.
    """
    found = shutil.which("cmake")
    if not found:
        raise SystemExit("cmake is not on PATH; this harness compiles a small C++ program")
    windows = os.name == "nt"
    configure = [found, "--fresh", "-S", str(OUT), "-B", str(OUT / "build")]
    build = [found, "--build", str(OUT / "build")]
    if windows:
        configure += ["-G", "Visual Studio 17 2022", "-A", "x64"]
        build += ["--config", "Release", "--", "-m:1"]
    binary = OUT / "build" / ("Release/action_bar_test.exe" if windows else "action_bar_test")
    return configure, build, str(binary)


def extract(signature: str) -> str:
    start = SOURCE.index(signature)
    opening = SOURCE.index("{", start)
    depth, end = 1, opening + 1
    while depth:
        depth += (SOURCE[end] == "{") - (SOURCE[end] == "}")
        end += 1
    return SOURCE[start:end]


def sample_spell_ids() -> list[int]:
    path = ROOT / "mod-diablocraft/data/d3/primary_effects.csv"
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) >= 6
    return [int(row["spell_id"]) for row in rows[:6]]


def main() -> None:
    set_slot = extract(
        "bool SetSlot(Player* player, unsigned slot, std::string const& skill, std::string const& rune,")
    assert "ShellFor(player, skill, rune, skillId, spellId)" in set_slot
    assert set_slot.index("AsyncCommitTransaction") < set_slot.index("WriteActionBar(player)")
    expected = sample_spell_ids()
    initializer = ",".join(f'{{{index}, "skill", "", {spell_id}}}'
                           for index, spell_id in enumerate(expected))
    expected_cpp = ",".join(str(spell_id) for spell_id in expected)
    code = r'''
#include <array>
#include <cstdint>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>
using uint8 = std::uint8_t;
using uint32 = std::uint32_t;
constexpr uint8 ACTION_BUTTON_SPELL = 0;
constexpr uint32 SPEC_MASK_ALL = 0xFFFFFFFF;
struct SpellInfo {};
struct SpellMgr {
    SpellInfo portal;
    SpellInfo const* GetSpellInfo(uint32 spell) { return spell == 81167 || spell == 81202 ? &portal : nullptr; }
} spellMgr;
SpellMgr* sSpellMgr = &spellMgr;
struct Player {
    std::map<uint8, std::pair<uint32, uint8>> buttons;
    std::vector<uint8> removed;
    unsigned sends = 0;
    uint8 sendMode = 0;
    std::set<uint32> known;
    void removeActionButton(uint8 slot) { removed.push_back(slot); buttons.erase(slot); }
    bool addActionButton(uint8 slot, uint32 spell, uint8 type) {
        buttons[slot] = {spell, type};
        return true;
    }
    void SendActionButtons(uint8 mode) { ++sends; sendMode = mode; }
    bool HasSpell(uint32 spell) const { return known.count(spell) != 0; }
    void learnSpell(uint32 spell) { known.insert(spell); }
    void removeSpell(uint32 spell, uint32, bool) { known.erase(spell); }
};
@POTIONS@
namespace DC::Inventory {
uint32 ActivePotionSpell(Player*) { return 81202; }
}
namespace DC::Classes {
// Production turned this into a read of dc_tunables (combat/active_skill_slots,
// audit row 22), so the stub is a function too. The harness has no database
// behind it and pins D3's published 6, which is what the row carries.
inline unsigned ActiveSlots() { return 6; }
constexpr unsigned ACTIVE_SLOTS = 6;
struct Slot {
    unsigned slot = 0;
    std::string skill, rune;
    std::uint32_t spellId = 0;
};
namespace {
constexpr std::uint32_t TOWN_PORTAL_SHELL = 81167;
// The potion cooldown packet is test_potion_cooldown.py's business, not the bar layout's.
inline void SendPotionCooldown(Player*, std::uint32_t) {}
@WRITE@
}
}
int checks = 0;
void check(bool pass, char const* name) {
    ++checks;
    if (!pass) throw std::runtime_error(name);
}
int main() {
    using namespace DC::Classes;
    std::vector<Slot> bar = {@BAR@};
    std::array<uint32, ACTIVE_SLOTS> expected = {@EXPECTED@};
    Player player;
    constexpr uint32 PLAYER_BUTTON_SENTINEL = 0xC0FFEE;
    player.buttons[8] = {PLAYER_BUTTON_SENTINEL, 1};
    player.known = {81205, 81211, 81220};   // shells of legendary potions no longer slotted
    WriteActionBar(&player, bar);
    check(!player.HasSpell(81205) && !player.HasSpell(81211) && !player.HasSpell(81220),
          "a legendary shell is unlearned once its potion is not the slotted one");
    check(player.removed == std::vector<uint8>({0, 1, 2, 3, 4, 5, 6, 7}),
          "only server-owned buttons 0-7 cleared");
    for (unsigned slot = 0; slot < ActiveSlots(); ++slot)
        check(player.buttons.at(uint8(slot)) == std::make_pair(expected[slot], ACTION_BUTTON_SPELL),
              "skill spell id/type written to its native button");
    check(player.buttons.at(6) == std::make_pair(uint32(81202), ACTION_BUTTON_SPELL),
          "Health Potion written to button 6/key 7");
    check(player.HasSpell(81202), "potion learned before its action is added");
    check(player.buttons.at(7) == std::make_pair(TOWN_PORTAL_SHELL, ACTION_BUTTON_SPELL),
          "Town Portal written to button 7/key 8");
    check(player.HasSpell(TOWN_PORTAL_SHELL),
          "Town Portal learned before AzerothCore validates its button");
    check(player.buttons.at(8).first == PLAYER_BUTTON_SENTINEL,
          "button 8/key 9 remains player-owned");
    check(player.sends == 1 && player.sendMode == 1,
          "native action buttons pushed immediately");
    std::cout << "PASS " << checks << " production action-bar checks\n";
}
'''
    code = (code.replace("@WRITE@", extract(
                "void WriteActionBar(Player* player, std::vector<Slot> const& bar)"))
            .replace("@BAR@", initializer)
            .replace("@EXPECTED@", expected_cpp)
            # The generated potion table (diablocraft-87qlt): every legendary shell the bar must unlearn.
            .replace("@POTIONS@", (ROOT / "mod-diablocraft/src/classes/dc_potion_table.h").read_text(encoding="utf-8")
                     .replace("#pragma once", "")))

    lock = ROOT / "build.lock"
    owner = f"Codex action-bar harness {os.getpid()} {time.time()}"
    while True:
        try:
            with lock.open("x", encoding="utf-8") as stream:
                stream.write(owner)
            break
        except FileExistsError:
            if time.time() - lock.stat().st_mtime >= 1800:
                raise RuntimeError("Stale build.lock; inspect owner")
            print("Waiting for server build lock", flush=True)
            time.sleep(10)

    try:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "test.cpp").write_text(code, encoding="utf-8")
        (OUT / "CMakeLists.txt").write_text(
            "cmake_minimum_required(VERSION 3.20)\n"
            "project(action_bar_test LANGUAGES CXX)\n"
            "add_executable(action_bar_test test.cpp)\n"
            "target_compile_features(action_bar_test PRIVATE cxx_std_17)\n",
            encoding="utf-8")
        cmake_configure, cmake_build, binary = toolchain()
        env = {key.upper(): value for key, value in os.environ.items()}
        for command in (cmake_configure, cmake_build):
            os.utime(lock, None)
            subprocess.run(command, env=env, check=True)
        os.utime(lock, None)
        harness_env.run([binary], env=env, check=True)
    finally:
        if lock.exists() and lock.read_text(encoding="utf-8") == owner:
            lock.unlink()


if __name__ == "__main__":
    main()
