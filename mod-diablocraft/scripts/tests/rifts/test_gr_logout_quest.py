"""A logout takes the rift quest off the character for good, so a new Greater Rift is not refused (diablocraft-6q73).

Two defects stacked. (1) The core's Player::RemoveActiveQuest erases the status but not the id from the player's
timed-quest set, and SatisfyQuestTimed refuses any timed quest while that set is not empty ("you already have a
timed quest"); StripRunQuest never called RemoveTimedQuest. (2) HandleLogout ran in OnPlayerLogout, which
WorldSession::LogoutPlayer calls AFTER SaveToDB, so the strip never reached character_queststatus and the quest was
back at the next login. A Greater Rift member who logged out with others still online also kept the quest through a
2-minute grace, against 09-rifts 7.9.2 item 7 and 7.9.7 (a logout before the Guardian dies is a failed abandon).

Cross-source: the core facts above are asserted from the core's own text, so a core update that changes them fails
here. Then StripRunQuest, DetachMember and HandleLogout are cut out of src/rifts/dc_rift_quests.cpp and compiled
against a quest-log double that keeps the timed set the way the core does; the harness drives a Greater Rift and a
Nephalem Rift, solo and in a party. DC_RIFT_QUEST_SOURCE points the compile at a mutated copy (mutation runs)."""
from pathlib import Path
import os
import re
import subprocess
import tempfile

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / 'mod-diablocraft'
SOURCE = Path(os.environ.get('DC_RIFT_QUEST_SOURCE', MODULE / 'src/rifts/dc_rift_quests.cpp'))
TEXT = SOURCE.read_text(encoding='utf-8')
CORE_DIR = ROOT / 'azerothcore-wotlk/src/server/game'
QUEST = (CORE_DIR / 'Entities/Player/PlayerQuest.cpp').read_text(encoding='utf-8')
SESSION = (CORE_DIR / 'Server/WorldSession.cpp').read_text(encoding='utf-8')


def function(text, signature):
    match = re.search(r'\n[ \t]*' + re.escape(signature) + r'\s*\{', text)
    if not match:
        raise SystemExit('test_gr_logout_quest: anchor `%s` is not in the source; renamed or moved, update this harness'
                         % signature)
    depth = 0
    for index in range(match.end() - 1, len(text)):
        depth += {'{': 1, '}': -1}.get(text[index], 0)
        if depth == 0:
            return text[match.start() + 1:index + 1]
    raise SystemExit('test_gr_logout_quest: unbalanced braces after %s' % signature)


# --- cross-source: what the double claims about the core is what the core does ----------------------
remove = function(QUEST, 'void Player::RemoveActiveQuest(uint32 questId, bool update /*= true*/)')
assert 'RemoveTimedQuest' not in remove and 'm_timedquests' not in remove, 'the core now clears the timed set itself'
timed = function(QUEST, 'bool Player::SatisfyQuestTimed(Quest const* qInfo, bool msg) const')
assert '!m_timedquests.empty()' in timed and 'QUEST_SPECIAL_FLAGS_TIMED' in timed
logout = function(SESSION, 'void WorldSession::LogoutPlayer(bool save, bool redirecting)')
assert logout.index('OnPlayerBeforeLogout(_player)') < logout.index('SaveToDB(false, true)') < logout.index('OnPlayerLogout(_player)'), \
    'the hook order the fix rests on has changed'

# --- the hooks: the strip rides the before-logout hook, the after-logout hook leaves the quest alone ----
player_class = function(TEXT, 'class RiftPlayer final : public PlayerScript')
base = player_class[:player_class.index('void OnPlayerQuestAccept')]   # the constructor's hook list
assert 'PLAYERHOOK_ON_BEFORE_LOGOUT' in base
before = function(player_class, 'void OnPlayerBeforeLogout(Player* player) override')
after = function(player_class, 'void OnPlayerLogout(Player* player) override')
assert 'HandleLogout(player);' in before and 'HandleLogout' not in after

clear = function(TEXT, 'void ClearQuestSlots(Player* player, std::uint32_t questId)')
strip = function(TEXT, 'void StripRunQuest(Player* player, std::uint32_t questId)')
detach = function(TEXT, 'void DetachMember(Rift const& rift, ObjectGuid guid, Player* player, char const* reason, char const* notice)')
handle = function(TEXT, 'void HandleLogout(Player* player)')

harness = r'''
#include <cassert>
#include <cstdint>
#include <map>
#include <set>
#include <string>
#include <vector>
using uint16 = std::uint16_t; using uint32 = std::uint32_t; using uint64 = std::uint64_t;
constexpr uint16 MAX_QUEST_LOG_SIZE = 25;
enum QuestStatus { QUEST_STATUS_NONE, QUEST_STATUS_COMPLETE, QUEST_STATUS_INCOMPLETE, QUEST_STATUS_FAILED, QUEST_STATUS_REWARDED };
struct WorldSession {};
struct ChatHandler { explicit ChatHandler(WorldSession*) {} void SendSysMessage(char const*) {} };
struct ObjectGuid { uint64 raw = 0; uint64 GetRawValue() const { return raw; } bool operator!=(ObjectGuid o) const { return raw != o.raw; } };
struct Group {};
struct Player {
    uint32 slots[MAX_QUEST_LOG_SIZE] = {};
    std::map<uint32, QuestStatus> status;
    std::set<uint32> timed;                  // m_timedquests
    WorldSession session; Group group; bool grouped = false; ObjectGuid guid{7};
    WorldSession* GetSession() { return &session; }
    ObjectGuid GetGUID() const { return guid; }
    char const* GetName() const { return "the designer"; }
    Group* GetGroup() { return grouped ? &group : nullptr; }
    QuestStatus GetQuestStatus(uint32 id) const { auto f = status.find(id); return f == status.end() ? QUEST_STATUS_NONE : f->second; }
    uint16 FindQuestSlot(uint32 id) const { for (uint16 i = 0; i < MAX_QUEST_LOG_SIZE; ++i) if (slots[i] == id) return i; return MAX_QUEST_LOG_SIZE; }
    void SetQuestSlot(uint16 slot, uint32 id, uint32 = 0) { slots[slot] = id; }
    void AbandonQuest(uint32) {}
    // The core's RemoveActiveQuest erases the status and nothing else (asserted above).
    void RemoveActiveQuest(uint32 id, bool) { status.erase(id); }
    void RemoveTimedQuest(uint32 id) { timed.erase(id); }
    // SatisfyQuestTimed for a new timed quest: refused while the set is not empty.
    bool CanTakeTimedQuest() const { return timed.empty(); }
    void give(uint32 id) { status[id] = QUEST_STATUS_INCOMPLETE; slots[0] = id; timed.insert(id); }
};
struct Rift { uint64 id = 11; uint32 instanceId = 5; uint32 questId = 0; std::string mode; };
// The seams HandleLogout and DetachMember reach.
std::vector<std::string> sql; int closes = 0, urshiLeft = 0, leaves = 0, clears = 0, rescales = 0, urshiNotified = 0;
unsigned othersOnline = 0; bool inRun = true; Rift theRun;
struct Db { template <class... A> void Execute(char const* f, A&&...) { sql.push_back(f); } } CharacterDatabase;
#define LOG_INFO(...) ((void)0)
bool EnrolledRun(ObjectGuid, Rift& out) { out = theRun; return inRun; }
unsigned OnlineEnrolled(Rift const&, ObjectGuid) { return othersOnline; }
bool tries = true;   // the real one erases the member's entry, so a second call finds nothing and says nothing
void UrshiMemberLeft(uint32, ObjectGuid, Player* notify) { if (!tries) return; tries = false; ++urshiLeft; if (notify) ++urshiNotified; }
void LeaveMembership(uint32, ObjectGuid) { ++leaves; }
void ClearMembership(uint32) { ++clears; }
void RescaleForHeadcount(uint32) { ++rescales; }
void QueueClose(Rift const&) { ++closes; }
FUNCTIONS
bool sqlHas(char const* part) { for (auto const& s : sql) if (s.find(part) != std::string::npos) return true; return false; }
void reset() { sql.clear(); closes = urshiLeft = leaves = clears = rescales = urshiNotified = 0; othersOnline = 0; inRun = true; tries = true; }
bool gone(Player const& p, uint32 q) { return p.GetQuestStatus(q) == QUEST_STATUS_NONE && p.FindQuestSlot(q) == MAX_QUEST_LOG_SIZE && !p.timed.count(q); }
int main() {
    uint32 const GR = 910023, NR = 910020;
    // -- StripRunQuest alone: the timed set goes with the status, so a new timed quest is allowed.
    { Player p; p.give(GR); assert(!p.CanTakeTimedQuest());
      StripRunQuest(&p, GR);
      assert(gone(p, GR) && p.CanTakeTimedQuest()); }
    // -- ... even when the status is already gone and only the timed id is left (a stale set).
    { Player p; p.timed.insert(GR);
      StripRunQuest(&p, GR);
      assert(p.CanTakeTimedQuest()); }

    // -- Greater Rift, in a party, others still online: the member is detached and the quest goes. No grace.
    { reset(); Player p; p.grouped = true; p.give(GR); theRun = Rift(); theRun.mode = "gr"; theRun.questId = GR; othersOnline = 2;
      HandleLogout(&p);
      assert(gone(p, GR) && p.CanTakeTimedQuest());
      assert(sqlHas("state='detached'") && !sqlHas("state='offline'"));
      assert(leaves == 1 && closes == 0 && clears == 0);
      assert(urshiLeft == 1 && urshiNotified == 0); }          // the Urshi tries are lost, quietly
    // -- Greater Rift, solo: the run closes at once and the quest goes.
    { reset(); Player p; p.give(GR); theRun = Rift(); theRun.mode = "gr"; theRun.questId = GR;
      HandleLogout(&p);
      assert(gone(p, GR) && p.CanTakeTimedQuest() && closes == 1 && clears == 1 && urshiLeft >= 1); }
    // -- Greater Rift, in a party, the last one out: closes and the quest goes.
    { reset(); Player p; p.grouped = true; p.give(GR); theRun = Rift(); theRun.mode = "gr"; theRun.questId = GR;
      HandleLogout(&p);
      assert(gone(p, GR) && closes == 1); }
    // -- Nephalem Rift, in a party, others online: the member goes offline and KEEPS the quest through the grace.
    { reset(); Player p; p.grouped = true; p.give(NR); theRun = Rift(); theRun.mode = "nr"; theRun.questId = NR; othersOnline = 1;
      HandleLogout(&p);
      assert(p.GetQuestStatus(NR) == QUEST_STATUS_INCOMPLETE && sqlHas("state='offline'") && closes == 0 && urshiLeft >= 1); }
    // -- Nephalem Rift, solo: closes and the quest goes.
    { reset(); Player p; p.give(NR); theRun = Rift(); theRun.mode = "nr"; theRun.questId = NR;
      HandleLogout(&p);
      assert(gone(p, NR) && closes == 1); }
    // -- not in a run: nothing happens.
    { reset(); Player p; p.give(GR); inRun = false;
      HandleLogout(&p);
      assert(p.GetQuestStatus(GR) == QUEST_STATUS_INCOMPLETE && sql.empty() && closes == 0); }
}
'''
harness = harness.replace('FUNCTIONS', '\n'.join((clear, strip, detach, handle)))

scratch = ROOT / 'azerothcore-wotlk/build/_agent-scratch/scripts'
scratch.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='gr-logout-quest-', dir=scratch) as folder:
    cpp = Path(folder) / 'test.cpp'
    exe = Path(folder) / 'test.exe'
    cpp.write_text(harness, encoding='utf-8')
    subprocess.run(['clang++', '-std=c++17', str(cpp), '-o', str(exe)], check=True)
    harness_env.run([str(exe)], check=True)
print('Rift logout quest checks passed')
