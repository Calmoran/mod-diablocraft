"""Exercise production hub location helpers with position/teleport doubles.

The first scenarios use the old hub's frozen spawn (tests/scryer_hub) as the hub. The last one is the hub move of
diablocraft-976b: the hub is now the Sanctum of Torment (map 750, a synthetic spawn here, never the designer's) and a character
saved standing in the old hub (map 530, a closed area since) is moved to the Sanctum spawn by its next login or logout.
"""
from pathlib import Path
import csv
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[4]
source = (ROOT / 'mod-diablocraft/src/common/dc_world.cpp').read_text(encoding='utf-8')


def definition(marker):
    start = source.index(marker)
    end = source.index('{', start) + 1
    depth = 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end].replace(' override', '')


import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from generate_hub_relocation import point_rows
spawn = next(row for row in point_rows() if row['name'] == 'spawn')

harness = r'''
#include <cassert>
#include <cmath>
#define LOG_ERROR(...) ((void)0)
struct WorldLocation {
 unsigned map; float x,y,z,o;
 unsigned GetMapId() const { return map; }
 float GetOrientation() const { return o; }
 float GetExactDist(WorldLocation const* p) const {
  return std::sqrt((x-p->x)*(x-p->x)+(y-p->y)*(y-p->y)+(z-p->z)*(z-p->z));
 }
};
struct Session { bool logout=false; bool PlayerLogout() const { return logout; } };
struct Player : WorldLocation {
 Session session; unsigned instance=0,transfers=0,homebinds=0; bool succeeds=true;
 WorldLocation destination{};
 unsigned GetInstanceId() const { return instance; }
 Session* GetSession() { return &session; }
 char const* GetName() const { return "test"; }
 void SetHomebind(WorldLocation const&,unsigned) { ++homebinds; }
 bool TeleportTo(WorldLocation const& p) { ++transfers; destination=p; return succeeds; }
};
unsigned messages=0;
struct ChatHandler {
 explicit ChatHandler(Session*) {}
 void SendSysMessage(char const*) { ++messages; }
};
bool ready=true;
'''
harness += 'WorldLocation hub{' + ','.join([spawn['map_id']] + [spawn[k] + 'f' for k in ('x','y','z','o')]) + '};\n'
harness += 'unsigned hubArea=' + spawn['area_id'] + ';\n'
harness += definition('bool AtHubSpawn(') + '\n' + definition('void MoveToHubSpawn(')
harness += '\n' + definition('    void OnPlayerBeforeLogout(')
harness += r'''
int main() {
 Player player; static_cast<WorldLocation&>(player)=hub;
 player.session.logout=true;
 player.map=558; player.instance=7; // Any old dungeon position.
 OnPlayerBeforeLogout(&player);
 assert(player.transfers==1 && player.homebinds==1);
 assert(player.destination.map==hub.map && player.destination.x==hub.x);
 assert(messages==0);
 // Core finalizes far transfer, or saves near-transfer destination, before logout save.
 static_cast<WorldLocation&>(player)=player.destination; player.instance=0;
 player.session.logout=false;
 MoveToHubSpawn(&player,"login");
 assert(player.transfers==1); // Next login does not transfer again.
 player.x+=5; player.session.logout=true;
 OnPlayerBeforeLogout(&player);
 assert(player.transfers==2 && player.destination.x==hub.x); // Same map, off spawn.
 player.session.logout=false;
 MoveToHubSpawn(&player,"login");
 assert(player.transfers==3); // Old/crash save still has a login fallback.
 static_cast<WorldLocation&>(player)=hub;
 player.o+=0.2f; MoveToHubSpawn(&player,"login"); assert(player.transfers==4);
 ready=false; OnPlayerBeforeLogout(&player); assert(player.transfers==4);
 ready=true; player.succeeds=false;
 player.session.logout=true; OnPlayerBeforeLogout(&player); assert(messages==0);
 player.session.logout=false; MoveToHubSpawn(&player,"login"); assert(messages==1);
 // The hub moved: the old hub (map 530) is closed, and a character saved standing at its old spawn is moved, once, to the new one.
 WorldLocation const oldHub = hub;
 hub = WorldLocation{750u, 101.5f, -200.0f, 300.0f, 1.1f};
 hubArea = 4273u;
 Player saved; static_cast<WorldLocation&>(saved) = oldHub;
 assert(saved.map != hub.map);
 MoveToHubSpawn(&saved,"login");
 assert(saved.transfers==1 && saved.homebinds==1);
 assert(saved.destination.map==750u && saved.destination.x==hub.x && saved.destination.y==hub.y && saved.destination.z==hub.z);
 static_cast<WorldLocation&>(saved) = saved.destination;
 MoveToHubSpawn(&saved,"login");
 assert(saved.transfers==1); // standing at the Sanctum spawn it is not moved again
 Player twin; static_cast<WorldLocation&>(twin) = hub; twin.map = 530u; // the same coordinates on the old hub's map are not the spawn
 MoveToHubSpawn(&twin,"login");
 assert(twin.transfers==1 && twin.destination.map==750u);
 Player leaving; static_cast<WorldLocation&>(leaving) = oldHub; leaving.session.logout=true;
 OnPlayerBeforeLogout(&leaving);
 assert(leaving.transfers==1 && leaving.destination.map==750u); // saved at the Sanctum spawn, never in the closed hub
}
'''
import host_cmake
env = host_cmake.environment()
with tempfile.TemporaryDirectory(prefix='dc-hub-login-') as directory:
    folder = Path(directory)
    (folder / 'test.cpp').write_text(harness, encoding='utf-8')
    (folder / 'CMakeLists.txt').write_text(
        'cmake_minimum_required(VERSION 3.20)\nproject(hub_login_tests LANGUAGES CXX)\n'
        'add_executable(hub_login_tests test.cpp)\ntarget_compile_features(hub_login_tests PRIVATE cxx_std_17)\n'
        'target_compile_options(hub_login_tests PRIVATE ' + host_cmake.undebug() + ')\n', encoding='utf-8')
    configure, build, binary = host_cmake.commands(folder, folder / 'build', 'hub_login_tests')
    for command in (configure, build, [binary]):
        subprocess.run(command, env=env, check=True)
print('PASS: logout destination, same-map logout, no repeat login transfer, fallback, orientation, unavailable data, teleport failure, login and logout from the closed old hub')
