"""Compile the production respawn callbacks against a small player/core double."""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[4]
SOURCE = (ROOT / "mod-diablocraft/src/hardcore/dc_hardcore.cpp").read_text(encoding="utf-8")


def definition(marker: str) -> str:
    start = SOURCE.index(marker)
    opening = SOURCE.index("{", start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (SOURCE[end] == "{") - (SOURCE[end] == "}")
        end += 1
    return SOURCE[start:end].replace(" override", "")


HARNESS = r'''
#include <cassert>
#include <cstdint>
#include <mutex>
#include <string>
#include <unordered_map>
#include <chrono>
#include <vector>
using uint32 = std::uint32_t;
using uint64 = std::uint64_t;
enum class Mode { Unchosen, Normal, Hardcore };
Mode mode = Mode::Normal;
Mode Load(uint32) { return mode; }
struct Guid {
    bool player = true;
    bool IsPlayer() const { return player; }
    uint32 GetCounter() const { return 5; }
    std::uint64_t GetRawValue() const { return 5; }
};
using ObjectGuid = Guid;
constexpr unsigned CMSG_PLAYER_LOGIN = 1;
enum class LoginFailureReason { Disabled };
struct WorldPacket {
    unsigned opcode = CMSG_PLAYER_LOGIN;
    std::size_t length = 8, cursor = 0;
    bool player = true;
    unsigned GetOpcode() const { return opcode; }
    std::size_t size() const { return length; }
    std::size_t rpos() const { return cursor; }
    WorldPacket& operator>>(ObjectGuid& guid) { cursor += 8; guid.player = player; return *this; }
};
struct Database {
    bool locked = true;
    bool Query(char const*, unsigned guid, unsigned account) { return locked && guid == 5 && account == 7; }
} CharacterDatabase;
namespace WorldPackets::Character {
struct LogoutResponse {
    unsigned LogoutResult = 99;
    bool Instant = false;
    LogoutResponse* Write() { return this; }
};
}
namespace GameTime { std::chrono::seconds GetGameTime() { return std::chrono::seconds(1000); } }
struct Session {
    bool loading = false, inWorld = false;
    unsigned account = 7, failures = 0;
    bool PlayerLoading() const { return loading; }
    void* GetPlayer() const { return inWorld ? (void*)this : nullptr; }
    unsigned GetAccountId() const { return account; }
    void SendCharLoginFailed(LoginFailureReason reason) {
        assert(reason == LoginFailureReason::Disabled);
        ++failures;
    }
    std::vector<std::string> events;
    void SendPacket(WorldPackets::Character::LogoutResponse const* packet) {
        assert(packet->LogoutResult == 0 && packet->Instant);
        events.push_back("response");
    }
    void SetLogoutStartTime(long long at) {
        assert(at == 980 && events.back() == "response");
        events.push_back("queued");
    }
} session;
using WorldSession = Session;
struct WorldLocation { unsigned map = 0; float x = 0, y = 0, z = 0; };
int portals = 0;
struct Player {
    int teleports = 0;
    WorldLocation lastTeleport;
    bool TeleportTo(WorldLocation const& to) { ++teleports; lastTeleport = to; return true; }
    bool alive = false, veto = false;
    int health = 0, bones = 0;
    int map = 602, instance = 77;
    float x = 1, y = 2, z = 3;
    bool IsAlive() const { return alive; }
    Guid GetGUID() const { return {}; }
    void ResurrectPlayer(float pct) { assert(pct == 1.0f); alive = !veto; }
    void SpawnCorpseBones() { ++bones; }
    int GetMaxHealth() const { return 12345; }
    void SetHealth(int n) { health = n; }
    Session* GetSession() { return &session; }
    std::string GetName() const { return "Hubbar"; }
    int GetMapId() const { return map; }
    int GetInstanceId() const { return instance; }
    float GetPositionX() const { return x; }
    float GetPositionY() const { return y; }
    float GetPositionZ() const { return z; }
};
struct ChatHandler { ChatHandler(void*) {} void SendSysMessage(char const*) {} };
#define LOG_INFO(...) ((void)0)
int locks = 0, ejects = 0;
void Lock(Player*, std::string const&) { ++locks; }
void Eject(Player*, std::string const&) { ++ejects; }
'''
HARNESS += definition("void QueueLogout(Player* player)") + "\n"
HARNESS += "struct LoginHooks {\n" + definition("bool CanPacketReceive(") + "\n};\n"
HARNESS += definition("struct Pending") + ";\n"
HARNESS += "std::mutex pendingMutex; std::unordered_map<std::uint64_t, Pending> pending;\n"
HARNESS += "namespace DC::Rifts::TownPortal { bool OpenPair(Player*) { ++portals; return true; } }\n"
HARNESS += "namespace DC::Rifts { unsigned waitLeft = 0; unsigned GreaterRiftReviveWaitLeft(Player const*) { return waitLeft; } }\n"
HARNESS += definition("enum class Choice") + ";\n" + definition("struct Destination") + ";\n" + definition("char const* Name(Choice choice)") + "\n"
# The choice logic is test_revive_choices.py's, compiled from production there; here only what the hooks call.
HARNESS += r'''
Choice releaseChoice = Choice::Here;
Choice ReleaseChoice(Player*) { return releaseChoice; }
Destination Resolve(Player*, Choice choice) { Destination to; to.done = choice; to.at.map = 530; return to; }
int noted = 0;
void NoteRevive(Player const*, Choice) { ++noted; }
int sentToTown = 0; bool townLoaded = true;
bool SendToTown(Player*) { ++sentToTown; return townLoaded; }
'''
HARNESS += definition("bool Respawn(Player* player, Destination& to)") + "\nstruct Hooks {\n"
for marker in ("void OnPlayerJustDied(", "bool OnPlayerCanRepopAtGraveyard(", "void OnPlayerUpdate("):
    HARNESS += definition(marker) + "\n"
HARNESS += r'''};
int main() {
    Hooks hooks;
    Player p;
    QueueLogout(&p);
    assert((session.events == std::vector<std::string>{"response", "queued"}));
    LoginHooks login;
    WorldPacket packet;
    assert(!login.CanPacketReceive(&session, packet));
    assert(session.failures == 1 && packet.rpos() == 0);
    assert(!session.loading && !session.inWorld); // No player load/disconnect path.
    assert(!login.CanPacketReceive(&session, packet)); // Repeated attempt still blocked.
    assert(session.failures == 2);
    CharacterDatabase.locked = false;
    assert(login.CanPacketReceive(&session, packet)); // Same account's other character works.
    CharacterDatabase.locked = true;
    session.account = 8;
    assert(login.CanPacketReceive(&session, packet)); // Ownership enforcement stays in core.
    session.account = 7;
    packet.length = 7;
    assert(login.CanPacketReceive(&session, packet));
    packet.length = 8;
    packet.player = false;
    assert(login.CanPacketReceive(&session, packet));
    packet.player = true;
    packet.opcode = 2;
    assert(login.CanPacketReceive(&session, packet));
    packet.opcode = CMSG_PLAYER_LOGIN;
    session.loading = true;
    assert(login.CanPacketReceive(&session, packet));
    session.loading = false;
    session.inWorld = true;
    assert(login.CanPacketReceive(&session, packet));
    session.inWorld = false;
    assert(login.CanPacketReceive(nullptr, packet));
    assert(session.failures == 2);
    hooks.OnPlayerJustDied(&p);
    hooks.OnPlayerUpdate(&p, 50);
    assert(!p.alive && p.bones == 0); // Death waits for Release.
    assert(!hooks.OnPlayerCanRepopAtGraveyard(&p)); // Core teleport is vetoed.
    hooks.OnPlayerUpdate(&p, 50);
    assert(p.alive && p.health == 12345 && p.bones == 1);
    assert(p.teleports == 0 && portals == 0); // Release means Revive here: no move, no Town Portal.
    assert(p.map == 602 && p.instance == 77 && p.x == 1 && p.y == 2 && p.z == 3);
    hooks.OnPlayerUpdate(&p, 50);
    assert(p.bones == 1); // Duplicate update cannot resurrect twice.
    assert(noted == 1 && sentToTown == 0);
    assert(!hooks.OnPlayerCanRepopAtGraveyard(&p) && sentToTown == 1); // A living player: SendToTown deals with it, the core does not.
    townLoaded = false;
    assert(hooks.OnPlayerCanRepopAtGraveyard(&p) && sentToTown == 2); // No hub loaded yet: the core's own move stands.
    townLoaded = true;
    sentToTown = 0;

    p = Player{}; // Release with the body ruled out (a fall into the void, a fourth in a row): the checkpoint or town.
    releaseChoice = Choice::Town;
    hooks.OnPlayerJustDied(&p);
    assert(!hooks.OnPlayerCanRepopAtGraveyard(&p));
    hooks.OnPlayerUpdate(&p, 50);
    assert(p.alive && p.teleports == 1 && p.lastTeleport.map == 530);
    assert(sentToTown == 0); // a dead player is never "sent to town" by the hook; the revive moves it
    releaseChoice = Choice::Here;

    p = Player{}; // Release in the same tick as death, before its first update.
    hooks.OnPlayerJustDied(&p);
    assert(!hooks.OnPlayerCanRepopAtGraveyard(&p));
    assert(!hooks.OnPlayerCanRepopAtGraveyard(&p));
    hooks.OnPlayerUpdate(&p, 50);
    assert(p.alive && p.bones == 1);

    p = Player{}; // Dead character loaded without an in-memory death record.
    assert(!hooks.OnPlayerCanRepopAtGraveyard(&p));
    hooks.OnPlayerUpdate(&p, 50);
    assert(p.alive);

    p = Player{};
    hooks.OnPlayerJustDied(&p);
    p.alive = true; // GM revive supersedes a pending normal death.
    hooks.OnPlayerUpdate(&p, 50);
    assert(pending.empty() && p.bones == 0);

    p = Player{};
    p.veto = true; // Respect any other module's resurrection veto.
    assert(!hooks.OnPlayerCanRepopAtGraveyard(&p));
    hooks.OnPlayerUpdate(&p, 50);
    assert(!p.alive && p.bones == 0 && p.health == 0);

    p = Player{}; // Greater Rift rule 5 (diablocraft-214r): a release inside the wait revives when the wait is over.
    DC::Rifts::waitLeft = 5;
    hooks.OnPlayerJustDied(&p);
    assert(!hooks.OnPlayerCanRepopAtGraveyard(&p));
    hooks.OnPlayerUpdate(&p, 50);
    hooks.OnPlayerUpdate(&p, 50);
    assert(!p.alive && p.bones == 0 && pending.size() == 1); // still waiting, still remembered
    DC::Rifts::waitLeft = 0;
    hooks.OnPlayerUpdate(&p, 50);
    assert(p.alive && p.bones == 1 && pending.empty());

    p = Player{}; // a Hardcore death has no wait: it is final at once
    mode = Mode::Hardcore;
    DC::Rifts::waitLeft = 30;
    hooks.OnPlayerJustDied(&p);
    hooks.OnPlayerUpdate(&p, 50);
    DC::Rifts::waitLeft = 0;
    mode = Mode::Normal;
    assert(locks == 1 && ejects == 1);
    locks = ejects = 0;

    for (bool release : {false, true}) {
        p = Player{};
        mode = Mode::Hardcore;
        hooks.OnPlayerJustDied(&p);
        if (release) assert(!hooks.OnPlayerCanRepopAtGraveyard(&p));
        hooks.OnPlayerUpdate(&p, 50);
        assert(!p.alive && p.bones == 0);
    }
    assert(locks == 2 && ejects == 2);
}
'''

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import host_cmake
env = host_cmake.environment()
with tempfile.TemporaryDirectory(prefix="dc-respawn-") as directory:
    folder = Path(directory)
    (folder / "test.cpp").write_text(HARNESS, encoding="utf-8")
    (folder / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.20)\nproject(respawn_tests LANGUAGES CXX)\n"
        "add_executable(respawn_tests test.cpp)\n"
        "target_compile_features(respawn_tests PRIVATE cxx_std_17)\n"
        "target_compile_options(respawn_tests PRIVATE " + host_cmake.undebug() + ")\n", encoding="utf-8")
    configure, build, binary = host_cmake.commands(folder, folder / 'build', 'respawn_tests')
    for command in (configure, build, [binary]):
        subprocess.run(command, env=env, check=True)
print("PASS: deferred release, location, duplicate release, loaded death, GM revive, veto, hardcore.")
