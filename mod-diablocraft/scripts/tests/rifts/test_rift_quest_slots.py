"""A rift quest never takes a second quest-log slot and no path leaves a hidden one (diablocraft-m6ix).

The core's Player::AddQuest takes the next free slot without asking whether the id is already in the log
(azerothcore-wotlk/src/server/game/Entities/Player/PlayerQuest.cpp, AddQuest), while the status map keeps one
entry per id; slots are not saved (PlayerStorage.cpp _LoadQuestStatus rebuilds them at login). A slot that
outlives its status, or doubles up, is invisible to every status-based check, and the log reads "full".

Cuts the production functions ClearQuestSlots, StripRunQuest and GiveRunQuest out of
src/rifts/dc_rift_quests.cpp (brace-balanced from their signatures) and compiles them against a quest-log
double that behaves like the core where it matters: AddQuest takes the next free slot with no duplicate
check, FindQuestSlot finds the first slot, SetQuestSlot(slot, 0) empties it, the status map holds one entry
per id. The harness then drives the cases: an orphan slot (no status), a duplicated slot, a repeated start,
a strip with a ghost left, and other quests' slots staying put.

DC_RIFT_QUEST_SOURCE points the compile at a mutated copy (mutation runs)."""
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
CORE = (ROOT / 'azerothcore-wotlk/src/server/game/Entities/Player/PlayerQuest.cpp').read_text(encoding='utf-8')
STORAGE = (ROOT / 'azerothcore-wotlk/src/server/game/Entities/Player/PlayerStorage.cpp').read_text(encoding='utf-8')


def function(text, signature):
    match = re.search(r'\n[ \t]*' + re.escape(signature) + r'\s*\{', text)   # the definition, not a forward declaration
    if not match:
        raise SystemExit('test_rift_quest_slots: anchor `%s` is not in %s; renamed or moved, update this harness'
                         % (signature, SOURCE.name))
    brace = match.end() - 1
    depth = 0
    for index in range(brace, len(text)):
        depth += {'{': 1, '}': -1}.get(text[index], 0)
        if depth == 0:
            return text[match.start() + 1:index + 1]
    raise SystemExit('test_rift_quest_slots: unbalanced braces after %s' % signature)


# --- cross-source: what the double claims about the core is what the core does -------------------
add = function(CORE, 'void Player::AddQuest(Quest const* quest, Object* questGiver)')
assert 'uint16 log_slot = FindQuestSlot(0);' in add and 'SetQuestSlot(log_slot, quest_id, qtime);' in add
assert 'FindQuestSlot(quest_id)' not in add, 'the core now checks for a held id itself; this test and the fix need a rethink'
assert 'm_QuestStatus[quest_id]' in add                                    # one status entry per id
load = function(STORAGE, 'void Player::_LoadQuestStatus(PreparedQueryResult result)')
assert 'SetQuestSlot(slot, quest_id, uint32(quest_time))' in load         # slots are rebuilt from rows at login

clear = function(TEXT, 'void ClearQuestSlots(Player* player, std::uint32_t questId)')
strip = function(TEXT, 'void StripRunQuest(Player* player, std::uint32_t questId)')
give = function(TEXT, 'void GiveRunQuest(Rift const& rift, Player* member, char const* notice)')
# order inside GiveRunQuest: the held-status return, then the orphan clear, then the room check and the add
assert give.index('QUEST_STATUS_REWARDED') < give.index('ClearQuestSlots(member, rift.questId)') \
    < give.index('member->CanAddQuest(quest, false)') < give.index('member->AddQuestAndCheckCompletion(quest, nullptr)')

harness = r'''
#include <cassert>
#include <cstdint>
#include <map>
#include <string>
#include <vector>
using uint16 = std::uint16_t; using uint32 = std::uint32_t;
constexpr uint16 MAX_QUEST_LOG_SIZE = 25;
enum QuestStatus { QUEST_STATUS_NONE, QUEST_STATUS_COMPLETE, QUEST_STATUS_INCOMPLETE, QUEST_STATUS_FAILED, QUEST_STATUS_REWARDED };
struct Quest {};
struct Object {};
struct ObjectGuid {};
struct WorldSession {};
std::vector<std::string> chat;
struct ChatHandler { explicit ChatHandler(WorldSession*) {} void SendSysMessage(char const* t) { chat.push_back(t); } };
struct Player {
    uint32 slots[MAX_QUEST_LOG_SIZE] = {};
    std::map<uint32, QuestStatus> status;
    WorldSession session; int abandons = 0, removes = 0;
    WorldSession* GetSession() { return &session; }
    ObjectGuid GetGUID() const { return {}; }
    QuestStatus GetQuestStatus(uint32 id) const { auto f = status.find(id); return f == status.end() ? QUEST_STATUS_NONE : f->second; }
    uint16 FindQuestSlot(uint32 id) const { for (uint16 i = 0; i < MAX_QUEST_LOG_SIZE; ++i) if (slots[i] == id) return i; return MAX_QUEST_LOG_SIZE; }
    void SetQuestSlot(uint16 slot, uint32 id, uint32 = 0) { slots[slot] = id; }
    void AbandonQuest(uint32) { ++abandons; }
    void RemoveActiveQuest(uint32 id, bool) { status.erase(id); ++removes; }
    void RemoveTimedQuest(uint32) {}   // the timed set is test_gr_logout_quest.py's concern
    bool CanAddQuest(Quest const*, bool) { return FindQuestSlot(0) < MAX_QUEST_LOG_SIZE; }
    // The core's AddQuest, as read above: next free slot, no duplicate check, one status entry per id.
    void AddQuestAndCheckCompletion(Quest const*, Object*) { uint16 s = FindQuestSlot(0); if (s >= MAX_QUEST_LOG_SIZE) return; status[quest_] = QUEST_STATUS_INCOMPLETE; slots[s] = quest_; }
    uint32 quest_ = 0;
    unsigned held(uint32 id) const { unsigned n = 0; for (uint32 v : slots) n += v == id; return n; }
};
struct Rift { uint32 questId = 0; };
struct ObjMgr { Quest q; Quest const* GetQuestTemplate(uint32 id) { return id ? &q : nullptr; } } objMgr; ObjMgr* sObjectMgr = &objMgr;
struct EnrollGuard {};
int enrolls = 0, progresses = 0;
void EnrollMember(Rift const&, ObjectGuid) { ++enrolls; }
void SetQuestProgress(Player*, Rift const&) { ++progresses; }
FUNCTIONS
int main() {
    uint32 const RIFT = 910023, OTHER = 5001, OTHER2 = 5002;
    auto fill = [](Player& p, uint32 id, uint16 slot) { p.slots[slot] = id; };

    // -- StripRunQuest: an orphan slot (the status is gone, the slot is not) is cleared, not skipped.
    { Player p; fill(p, OTHER, 0); fill(p, RIFT, 1); fill(p, OTHER2, 2);
      StripRunQuest(&p, RIFT);
      assert(p.held(RIFT) == 0 && p.held(OTHER) == 1 && p.held(OTHER2) == 1); }
    // -- a doubled slot: both go, with the status; other quests stay.
    { Player p; fill(p, RIFT, 0); fill(p, OTHER, 1); fill(p, RIFT, 2); p.status[RIFT] = QUEST_STATUS_INCOMPLETE;
      StripRunQuest(&p, RIFT);
      assert(p.held(RIFT) == 0 && p.GetQuestStatus(RIFT) == QUEST_STATUS_NONE && p.held(OTHER) == 1 && p.abandons == 1); }
    // -- a quest not held at all: nothing happens (no abandon call on nothing).
    { Player p; fill(p, OTHER, 0);
      StripRunQuest(&p, RIFT);
      assert(p.abandons == 0 && p.removes == 0 && p.held(OTHER) == 1); }
    // -- a null player or quest id is a no-op.
    StripRunQuest(nullptr, RIFT);
    { Player p; fill(p, RIFT, 0); StripRunQuest(&p, 0); assert(p.held(RIFT) == 1); }

    // -- GiveRunQuest: the first start takes one slot.
    Rift rift; rift.questId = RIFT;
    { Player p; p.quest_ = RIFT;
      GiveRunQuest(rift, &p, nullptr);
      assert(p.held(RIFT) == 1 && p.GetQuestStatus(RIFT) == QUEST_STATUS_INCOMPLETE && enrolls == 1); }
    // -- a repeated start, however many times, never takes a second slot.
    { Player p; p.quest_ = RIFT;
      for (int i = 0; i < 30; ++i) GiveRunQuest(rift, &p, nullptr);
      assert(p.held(RIFT) == 1); }
    // -- an orphan slot from earlier (no status): the next start reuses it, so the id is in ONE slot, never two.
    { Player p; p.quest_ = RIFT; fill(p, RIFT, 3);
      GiveRunQuest(rift, &p, nullptr);
      assert(p.held(RIFT) == 1 && p.GetQuestStatus(RIFT) == QUEST_STATUS_INCOMPLETE); }
    // -- ... and repeated strip + start cycles (a run that fails, again and again) leave the log as it was.
    { Player p; p.quest_ = RIFT; fill(p, OTHER, 0);
      for (int i = 0; i < 30; ++i) { GiveRunQuest(rift, &p, nullptr); StripRunQuest(&p, RIFT); }
      unsigned used = 0; for (uint32 v : p.slots) used += v != 0;
      assert(used == 1 && p.held(OTHER) == 1); }
    // -- a full log (25 other quests) still refuses with the notice, takes nothing.
    { Player p; p.quest_ = RIFT; for (uint16 i = 0; i < MAX_QUEST_LOG_SIZE; ++i) fill(p, 6000 + i, i);
      chat.clear(); GiveRunQuest(rift, &p, nullptr);
      assert(p.held(RIFT) == 0 && chat.size() == 1); }
    // -- a full log whose only 'other' entries are orphans of THIS quest is not full: they were the cause.
    { Player p; p.quest_ = RIFT; for (uint16 i = 0; i < MAX_QUEST_LOG_SIZE; ++i) fill(p, RIFT, i);
      GiveRunQuest(rift, &p, nullptr);
      assert(p.held(RIFT) == 1 && p.GetQuestStatus(RIFT) == QUEST_STATUS_INCOMPLETE); }
}
'''
harness = harness.replace('FUNCTIONS', clear + '\n' + strip + '\n' + give)

scratch = ROOT / 'azerothcore-wotlk/build/_agent-scratch/scripts'
scratch.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='rift-quest-slots-', dir=scratch) as folder:
    cpp = Path(folder) / 'test.cpp'
    exe = Path(folder) / 'test.exe'
    cpp.write_text(harness, encoding='utf-8')
    subprocess.run(['clang++', '-std=c++17', str(cpp), '-o', str(exe)], check=True)
    harness_env.run([str(exe)], check=True)
print('Rift quest slot checks passed')
