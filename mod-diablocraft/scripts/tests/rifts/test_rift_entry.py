"""Compile and exercise the production rift-access callback with core doubles."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env
import tempfile

root = Path(__file__).resolve().parents[4]
# RiftPlayer, and with it OnPlayerNotAvoidSatisfy, moved to dc_rift_quests.cpp
# in the 2026-09-17 split. Same code, new file.
source = (root / "mod-diablocraft/src/rifts/dc_rift_quests.cpp").read_text(encoding="utf-8")
start = source.index("bool OnPlayerNotAvoidSatisfy(")
end = source.index("{", start) + 1
depth = 1
while depth:
    depth += (source[end] == "{") - (source[end] == "}")
    end += 1
callback = source[start:end].replace(" override", "")
floors_header = (root / "mod-diablocraft/src/rifts/dc_rift_floors.h").as_posix()
code = r'''
#include <cassert>
#include <mutex>
#include <string>
#include <unordered_map>
#include "FLOORS_HEADER"
using DC::Rifts::LiveRuns;
using uint32 = unsigned;
struct DungeonProgressionRequirements {};
struct Save { unsigned GetInstanceId() { return 42; } } save;
struct Bind { Save* save; } binding{&save};
struct Manager {
    Bind* result = nullptr;
    Bind* PlayerGetBoundInstance(unsigned guid, unsigned map, unsigned difficulty) {
        assert(guid == 5 && map == 604 && difficulty == 0);
        return result;
    }
} manager;
auto* sInstanceSaveMgr = &manager;
struct Player {
    unsigned GetGUID() { return 5; }
    unsigned GetDifficulty(bool raid) { assert(!raid); return 0; }
} player;
struct Rift { unsigned long long id = 0; unsigned instanceId = 0, mapId = 0, dungeonId = 0, floor = 1; std::string state; };
LiveRuns<Rift> live;  // the production book (dc_rift_floors.h)
std::mutex riftMutex;
struct Hooks {
'''
code += callback + r'''
};
int main() {
    Hooks hooks;
    auto check = [&] { return hooks.OnPlayerNotAvoidSatisfy(&player, nullptr, 604, true); };
    assert(hooks.OnPlayerNotAvoidSatisfy(nullptr, nullptr, 604, true));
    assert(check()); // An ordinary player with no binding still needs level 71.
    manager.result = &binding;
    binding.save = nullptr;
    assert(check());
    binding.save = &save;
    assert(check()); // An ordinary WoW dungeon binding is not a rift.
    auto run = [&](unsigned map, char const* state) {
        live.Clear();
        Rift rift; rift.id = 1; rift.instanceId = 42; rift.mapId = map; rift.state = state;
        live.Start(rift);
    };
    run(602, "open");
    assert(check()); // Binding must match the destination, not just an instance ID.
    run(604, "closed");
    assert(check());
    for (auto state : {"open", "guardian", "complete"}) {
        run(604, state);
        assert(!check()); // A bound live rift owns its own entry rules.
    }
    // Rift floors (F1): a LATER floor of a live run owns its entry rules too, whatever floor 1 was.
    live.Clear();
    Rift first; first.id = 2; first.instanceId = 7; first.mapId = 602; first.state = "open";
    live.Start(first);
    assert(live.AddFloor(2, 42, 604, 0) == 2);
    assert(!check());
    live.Find(2)->state = "closed";
    assert(check()); // and a closed run refuses on every floor
    live.Clear();
    first.id = 3; first.instanceId = 42; first.mapId = 602; first.state = "open";
    live.Start(first);
    assert(check()); // the instance id is a floor of ANOTHER map: not this destination's rift
    manager.result = nullptr;
    assert(check()); // Unbound party outsiders cannot use the exception.
}
'''
# Portable toolchain resolution (2026-09-17). This used to hardcode
# C:/Program Files/CMake/bin/cmake.exe and the Visual Studio generator, which
# stopped working the day the project moved to Linux and left this harness
# silently dead. cmake now comes from PATH, the generator is whatever cmake
# picks by default, and the assert-keeping flag is chosen per compiler: MSVC
# spells it /UNDEBUG, everyone else -UNDEBUG.
def _toolchain():
    found = shutil.which("cmake")
    if not found:
        raise SystemExit("cmake is not on PATH; this harness compiles a small C++ program")
    windows = os.name == "nt"
    generator = ["-G", "Visual Studio 17 2022", "-A", "x64"] if windows else []
    buildargs = ["--config", "Release", "--", "-m:1"] if windows else []
    undebug = "/UNDEBUG" if windows else "-UNDEBUG"
    return found, generator, buildargs, undebug, windows


def _binary(folder, name, windows):
    return str(folder / "build" / ("Release/" + name + ".exe" if windows else name))

env = {key.upper(): value for key, value in os.environ.items()}
cmake, _gen, _buildargs, _undebug, _win = _toolchain()
with tempfile.TemporaryDirectory(prefix="dc-rift-entry-") as directory:
    folder = Path(directory)
    (folder / "test.cpp").write_text(code.replace("FLOORS_HEADER", floors_header), encoding="utf-8")
    (folder / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.20)\nproject(rift_entry LANGUAGES CXX)\n"
        "add_executable(rift_entry test.cpp)\n"
        "target_compile_options(rift_entry PRIVATE " + _undebug + ")\n", encoding="utf-8")
    subprocess.run([cmake, "-S", directory, "-B", str(folder / "build"),
                    ] + _gen, env=env, check=True)
    subprocess.run([cmake, "--build", str(folder / "build"), ] + _buildargs, env=env, check=True)
    harness_env.run([_binary(folder, "rift_entry", _win)], env=env, check=True)
print("PASS: live rift access and unrelated/missing/mismatched/closed binding refusal.")
