"""Opening a Greater Rift (diablocraft-0uyw, greater-rifts brief part 2).

Compiles the production pieces against core doubles:
  - dc_gr_ready.h as it is (the refusals, the level parser, the reply rules, the player-facing words);
  - Start, Tick and RespondGreaterRift cut out of dc_gr_open.cpp (the ready check's order of events:
    revalidate, then the opener's Keystone, then the run, the refund when the run fails, the timeout,
    the roster still being who it was);
with the Keystone cost and the proposal timeout read from data/tunables/rifts.csv, and the words
cross-checked against 09-rifts 7.9.4's table. A source scan covers what a double cannot reach (the
open path's roster, the closed-roster refusals); it says so below.

Since diablocraft-s4vx it also drives the two windows' route (DCRIFTENROLL, docs/contracts/rift-enrollment-messages.md):
the real router and bridge header in front of the cut Window, Begin, Respond, Resend and OpenWindow, and every record
the ready check pushes (P, T, L), checked against the contract's own words.

DC_GR_OPEN_SOURCE and DC_GR_READY_SOURCE point the compile at mutated copies (mutation runs)."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from split_sources import rifts_text  # noqa: E402
import harness_env
import tunables_csv

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / 'mod-diablocraft'
OPEN = Path(os.environ.get('DC_GR_OPEN_SOURCE', MODULE / 'src/rifts/dc_gr_open.cpp'))
READY = Path(os.environ.get('DC_GR_READY_SOURCE', MODULE / 'src/rifts/dc_gr_ready.h'))
SOURCE = OPEN.read_text(encoding='utf-8')
RIFTS = rifts_text()
QUESTS = (MODULE / 'src/rifts/dc_rift_quests.cpp').read_text(encoding='utf-8')
DESIGN = (ROOT / 'docs/design/09-rifts.md').read_text(encoding='utf-8')
CONTRACT = (ROOT / 'docs/contracts/rift-enrollment-messages.md').read_text(encoding='utf-8')
BRIDGE = MODULE / 'src/common/dc_bridge.h'

COST = int(tunables_csv.value('rifts', 'greater_rift_keystone_cost'))
TIMEOUT = int(tunables_csv.value('rifts', 'gr_proposal_timeout_seconds'))
START = int(tunables_csv.value('rifts', 'greater_rift_start_level'))
assert (COST, TIMEOUT, START) == (1, 40, 1), (COST, TIMEOUT, START)  # the brief; 09-rifts 7.9.2


def definition(marker: str) -> str:
    start = SOURCE.index(marker)
    opening = SOURCE.index('{', start)
    end, depth = opening + 1, 1
    while depth:
        depth += (SOURCE[end] == '{') - (SOURCE[end] == '}')
        end += 1
    return SOURCE[start:end]


# --- cross-source: the tunables the code reads exist, with the values the brief and 7.9.2 name ----
read = set(re.findall(r'Tunable\("(\w+)"\)', SOURCE))
assert read == {'greater_rift_start_level', 'gr_proposal_timeout_seconds', 'greater_rift_keystone_cost'}, read
generated = (MODULE / 'data/generated/tunables_0008.sql').read_text(encoding='utf-8')
for name, value in (('greater_rift_keystone_cost', '1.0'), ('gr_proposal_timeout_seconds', '40.0')):
    assert re.search(r"\('rifts', '%s', NULL, %s," % (name, re.escape(value)), generated), name

# --- cross-source: the words are 7.9.4's table, character for character ---------------------------
table = {
    'Declined': 'Greater Rift <rank> cancelled. Declined: <names>.',
    'Timeout': 'Greater Rift <rank> cancelled. No response: <names>.',
    'Offline': 'Greater Rift <rank> cancelled. Unavailable: <names> (offline).',
    'Logout': 'Greater Rift <rank> cancelled. <name> logged out.',
    'PartyChanged': 'Greater Rift <rank> cancelled. Party changed: <name> <joined/left>.',
    'Disbanded': 'Greater Rift <rank> cancelled. The party disbanded.',
    'StartFailed': 'Greater Rift <rank> cancelled before start. <reasonText>',
}
for line in table.values():
    assert '`' + line + '`' in DESIGN, line
for line in ('Everyone accepted. Starting Greater Rift <rank>...', 'Greater Rift <rank> has started. Entering the rift.',
             'Accepted. Waiting for the party.', 'Your response is already recorded.',
             'That Greater Rift ready check is no longer active.',
             'You are not a member of that Greater Rift ready check.',
             'Your party already has a Greater Rift ready check in progress.'):
    assert line in DESIGN, line
assert 'Accept: .dc rift accept <proposalId>' in DESIGN and 'Decline: .dc rift decline <proposalId>' in DESIGN

# --- cross-source: the window's wire is the contract's, and the code box is gone -----------------------
assert 'ParseLevel' not in SOURCE + READY.read_text(encoding='utf-8') and 'BeginGreaterRift' not in SOURCE
assert 'GOSSIP_SENDER_MAIN, ACTION_GREATER);' in SOURCE and ', true);' not in definition('void OpenObeliskMenu')  # no input box
assert re.search(r'else\s+OpenWindow\(player\);', definition('bool ObeliskSelect'))                       # Greater Rift opens the window
prefix = re.search(r'constexpr char const\* WINDOW = "(\w+)";', SOURCE).group(1)
assert prefix == 'DCRIFTENROLL' and '`%s`' % prefix in CONTRACT and prefix in (MODULE.parent / 'docs/contracts/window-bridge.md').read_text(encoding='utf-8')
obelisk = re.search(r'constexpr std::uint32_t OBELISK_ENTRY = (\d+);', SOURCE).group(1)
assert obelisk == re.search(r'constexpr std::uint32_t OBELISK_ENTRY = (\d+);', RIFTS).group(1) == '910011'    # the hub's obelisk
route = re.search(r'DC::Bridge::Routes\(\)\.Add\(WINDOW, (\{[^}]*\}), Window\)', SOURCE)
assert route and route.group(1) == '{"crafting", "artisan_burst", "artisan_per_second"}', route and route.group(1)
for row in ('artisan_burst', 'artisan_per_second'):
    assert tunables_csv.value('crafting', row) is not None, row
assert 'crafting/artisan_burst' in CONTRACT
FLAT = re.sub(r'\s+', ' ', CONTRACT)
reasons = re.search(r'one of (`[a-z_]+`(?:, `[a-z_]+`)+)', FLAT).group(1).replace('`', '').replace(' ', '')
statuses = re.search(r'`status` is (`\w+`, `\w+` or `\w+`)', FLAT).group(1).replace('`', '').replace(' or ', ',').replace(', ', ',')
assert reasons == 'declined,timeout,offline,logout,party_changed,disbanded,start_failed' and statuses == 'waiting,accepted,declined'
# The walk-away watch (C, diablocraft-4a85): the artisan windows' poll, run from the world update, and in the contract.
RANGE_LUA = (MODULE / 'lua/aio/dc_aio_range.lua').read_text(encoding='utf-8')
assert re.search(r'constexpr uint32 WATCH_MS = (\d+);', SOURCE).group(1) == re.search(r'local WATCH_MS = (\d+)', RANGE_LUA).group(1) == '500'
assert re.search(r'if \(watchElapsed >= WATCH_MS\)\s*\{\s*watchElapsed = 0;\s*WatchRange\(\);', SOURCE)
assert '| `C` | pushed when a player who got `L` walks out of range of the obelisk' in CONTRACT and 'every 500 ms' in CONTRACT
assert 'closes itself after a moment' not in CONTRACT and 'replaced by a Close button' in CONTRACT
BRIDGE_CPP = (MODULE / 'src/common/dc_bridge.cpp').read_text(encoding='utf-8')   # not compilable here: scanned
assert 'bool Push(Player* player' in BRIDGE_CPP and 'Wire<Player>(Send(), player, prefix).Record(fields)' in BRIDGE_CPP

# --- the start's order, in the source, for what the doubles below cannot show ---------------------
# The roster the ready check closed is the roster the run opens with: OpenRun takes it, and a late
# joiner reaches nobody (the three places that would have enrolled one refuse a Greater run).
assert 'party = greater->roster' in RIFTS and 'rift.mode = greater ? "gr" : "nr"' in RIFTS
assert 'rift.grRank = greater ? greater->level : 0' in RIFTS
assert 'GetTimeAllowed()' in RIFTS and not re.search(r'GetTimeAllowed\(\)\s*[+*]?\s*900', RIFTS)  # the clock is the quest's
assert QUESTS.count('Its roster is closed.') == 3 and 'party.mode != "gr"' in QUESTS, QUESTS.count('Its roster is closed.')
assert SOURCE.count('SpendKeystones(opener') == 1 and 'SpendKeystones(member' not in SOURCE  # the opener only
migration = (MODULE / 'data/sql/db-world/updates/rifts_0011_rift_quests.sql').read_text(encoding='utf-8')
assert len(re.findall(r'\b900\b', migration)) >= 3, 'the three Greater variants carry the 15:00 TimeAllowed'

HARNESS = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <map>
#include <mutex>
#include <set>
#include <string>
#include <vector>
using uint32 = std::uint32_t;
#include "%(ready)s"

#define LOG_INFO(...) ((void)0)
#define LOG_ERROR(...) ((void)0)
struct ObjectGuid {
    std::uint64_t raw = 0;
    ObjectGuid() = default;
    explicit ObjectGuid(std::uint64_t r) : raw(r) {}
    std::uint64_t GetRawValue() const { return raw; }
    std::uint32_t GetCounter() const { return static_cast<std::uint32_t>(raw); }
};
struct Group {
    struct MemberSlot { ObjectGuid guid; std::string name; };
    ObjectGuid guid;
    std::vector<MemberSlot> slots;
    ObjectGuid GetGUID() const { return guid; }
    std::vector<MemberSlot> const& GetMemberSlots() const { return slots; }
};
struct Player;
struct GameObject {};
constexpr float INTERACTION_DISTANCE = 5.0f;
std::uint32_t findEntry = 0; float findRange = 0;
struct WorldSession { Player* owner = nullptr; };
std::map<std::uint64_t, std::vector<std::string>> heard;   // what each player was told
struct Player {
    ObjectGuid guid;
    std::string name;
    bool inWorld = true;
    Group* group = nullptr;
    WorldSession session;
    bool inCombat = false, atObelisk = true;
    GameObject obelisk;
    bool IsInCombat() const { return inCombat; }
    GameObject* FindNearestGameObject(std::uint32_t entry, float range) { findEntry = entry; findRange = range; return atObelisk ? &obelisk : nullptr; }
    ObjectGuid GetGUID() const { return guid; }
    std::string GetName() const { return name; }
    bool IsInWorld() const { return inWorld; }
    Group* GetGroup() const { return group; }
    WorldSession* GetSession() { return &session; }
};
struct ChatHandler {
    Player* who;
    explicit ChatHandler(WorldSession* s) : who(s->owner) {}
    void SendSysMessage(std::string const& text);
};
void ChatHandler::SendSysMessage(std::string const& text) { heard[who->guid.raw].push_back(text); }
std::uint32_t now = 1000;
std::uint32_t getMSTime() { return now; }
std::map<std::uint64_t, Player*> world;
// The core's own rule (ObjectAccessor.cpp FindPlayer): a player not in the world is not found.
namespace ObjectAccessor { Player* FindPlayer(ObjectGuid g) { auto f = world.find(g.raw); return f == world.end() || !f->second->IsInWorld() ? nullptr : f->second; } }
double budget = 50;   // the window's two budget rows
namespace DC::Tunables {
    double Get(std::string const& category, std::string const& name) {
        if (category == "crafting") { assert(name == "artisan_burst" || name == "artisan_per_second"); return budget; }
        assert(category == "rifts");
        if (name == "greater_rift_start_level") return %(start)d;
        if (name == "greater_rift_keystone_cost") return %(cost)d;
        assert(name == "gr_proposal_timeout_seconds");
        return %(timeout)d;
    }
}

#include "%(bridge)s"
std::map<std::uint64_t, std::vector<std::string>> pushed;   // what each player's window was sent, record by record
namespace DC::Bridge {
    bool Push(Player* player, std::string const& prefix, std::vector<std::string> const& fields) {
        static Wire<Player>::Sender const sender = [](Player* p, std::string const&, std::string const& record) { pushed[p->guid.raw].push_back(record); };
        return Wire<Player>(sender, player, prefix).Record(fields);   // the production wire: cleaned, capped at 255 bytes
    }
}
bool hub = true;
std::uint64_t keystoneCount = 2; unsigned unlockedLevel = 9; std::uint64_t engineNext = 5;
long long validatedLevel = -1;
namespace DC::World { bool IsInHub(Player*) { return hub; } }
namespace DC::Rifts {
    struct GreaterStart { unsigned level = 0; std::vector<Player*> roster; };
    struct GrLevels { unsigned unlocked = 1; };
    GrLevels GreaterRiftLevels(std::uint32_t) { GrLevels l; l.unlocked = unlockedLevel; return l; }
    std::uint64_t Keystones(Player*) { return keystoneCount; }
    struct Eng { std::uint64_t operator()() { return engineNext++; } };
    Eng& Engine() { static Eng e; return e; }
    // doubles for what Start reaches
    std::string validateAnswer;
    std::vector<std::string> calls;
    bool spendOk = true, openOk = true;
    std::string openError = "Could not create a fresh, recorded rift instance.";
    GreaterStart opened;
    Player* openedBy = nullptr;
    std::string Validate(Player*, std::vector<Player*> const&, long long level) { calls.push_back("validate"); validatedLevel = level; return validateAnswer; }
    bool SpendKeystones(Player* p, unsigned n) { calls.push_back("spend:" + p->name + ":" + std::to_string(n)); return spendOk; }
    void RefundKeystones(Player* p, unsigned n, std::uint64_t id) { calls.push_back("refund:" + p->name + ":" + std::to_string(n) + ":" + std::to_string(id)); }
    bool OpenRun(Player* p, void const*, void*, std::string& error, GreaterStart const* g) {
        calls.push_back("open");
        openedBy = p;
        opened = *g;
        if (!openOk) error = openError;
        // diablocraft-zw5n: OpenRun teleports the roster into the instance before it returns, and a far
        // teleport takes the player out of the world (Player.cpp TeleportTo, RemovePlayerFromMap).
        if (openOk) for (Player* member : g->roster) member->inWorld = false;
        return openOk;
    }
    std::mutex proposalMutex;
'''

DEFS = '\n'.join([
    re.search(r'constexpr char const\* WINDOW = "\w+";', SOURCE).group(0),
    re.search(r'constexpr std::uint32_t OBELISK_ENTRY = \d+;', SOURCE).group(0),
    definition('unsigned Tunable(char const* name)'),
    definition('Player* Online(std::uint64_t raw)'),
    definition('void Say(Player* player, std::string const& text)'),
    definition('struct Queued') + ';',
    'std::vector<Queued> queued;',
    definition('std::string Names(Queued const& q'),
    definition('void SayAll(Queued const& q'),
    definition('void Push(Player* player'),
    definition('void PushProposal(Queued const& q'),
    definition('void PushResult(Queued const& q'),
    definition('void Cancel(Queued const& q'),
    definition('bool ProposalFor(std::uint64_t guid)'),
    definition('bool BuildRoster(Player* opener'),
    definition('void Queue(Player* opener'),
    definition('void Start(Queued const& q)'),
    definition('void Tick()'),
    re.search(r'constexpr uint32 WATCH_MS = \d+;', SOURCE).group(0),
    'std::mutex watchMutex;',
    re.search(r'std::set<std::uint64_t> watching;', SOURCE).group(0),
    definition('void WatchRange()'),
    definition('void OpenWindow(Player* player)'),
    definition('std::string Begin(Player* opener'),
    definition('std::string Respond(Player* player'),
    definition('void Resend(Player* player)'),
    definition('void Window(Player& player'),
    definition('void RespondGreaterRift(Player* player'),
])

MAIN = r'''
}
using namespace DC::Rifts;
namespace G = DC::Rifts::Gr;

Player a{ObjectGuid(1), "Opener"}, b{ObjectGuid(2), "Second"}, c{ObjectGuid(3), "Third"};
Group party{ObjectGuid(900), {{ObjectGuid(1), "Opener"}, {ObjectGuid(2), "Second"}, {ObjectGuid(3), "Third"}}};

std::vector<std::string> replies;   // what the router answered, by player
DC::Bridge::Router<Player> router{[](Player* p, std::string const& prefix, std::string const& record) { replies.push_back(prefix + "\t" + record); }};
DC::Bridge::Outcome lastOutcome;
std::string ask(Player& p, std::string const& message) {   // one window message; the router's one answer ("" when it sent none)
    replies.clear();
    lastOutcome = router.Dispatch(&p, "DCRIFTENROLL\t" + message, 0);
    return replies.empty() ? "" : replies.back();
}
std::string const MALFORMED = "DCRIFTENROLL\tX|That request was not understood.";
std::string refused(std::string const& text) { return "DCRIFTENROLL\tX|" + text; }
void reset() {
    heard.clear(); calls.clear(); queued.clear(); watching.clear(); world.clear(); pushed.clear(); replies.clear();
    now = 1000; validateAnswer.clear(); spendOk = openOk = true; opened = GreaterStart{}; openedBy = nullptr;
    hub = true; keystoneCount = 2; unlockedLevel = 9; engineNext = 5; budget = 50; validatedLevel = -1; findEntry = 0; findRange = 0;
    for (Player* p : {&a, &b, &c}) { p->inWorld = true; p->group = &party; p->session.owner = p; p->inCombat = false; p->atObelisk = true; world[p->guid.raw] = p; }
    party.slots = {{ObjectGuid(1), "Opener"}, {ObjectGuid(2), "Second"}, {ObjectGuid(3), "Third"}};
}
Queued make(unsigned level = 7, std::uint64_t id = 4242) {
    Queued q;
    q.proposal.id = id; q.proposal.opener = 1; q.proposal.level = level;
    q.proposal.deadline = now + %(timeout)d * 1000;
    q.group = 900;
    for (Player* p : {&a, &b, &c}) { q.proposal.roster.push_back({p->guid.raw, G::Reply::Waiting}); q.names[p->guid.raw] = p->name; }
    queued.push_back(q);
    return q;
}
bool told(Player& p, std::string const& text) {
    auto& v = heard[p.guid.raw];
    return std::find(v.begin(), v.end(), text) != v.end();
}
int count(std::string const& what) { return (int)std::count(calls.begin(), calls.end(), what); }

int main() {
    // ---- CheckOpen: every refusal, its order, and both edges of each bound ----
    G::OpenAsk ok; ok.level = 5; ok.start = %(start)d; ok.unlocked = 5; ok.keystones = %(cost)d; ok.cost = %(cost)d; ok.members = 4; ok.partyCap = 4;
    assert(G::CheckOpen(ok) == G::Refusal::None);                    // exactly the unlocked level, exactly the Keystone, a full party
    G::OpenAsk x = ok; x.level = 6;            assert(G::CheckOpen(x) == G::Refusal::AboveUnlocked);
    x = ok; x.level = ok.start - 1;            assert(G::CheckOpen(x) == G::Refusal::BelowStart);
    x = ok; x.level = ok.start;                assert(G::CheckOpen(x) == G::Refusal::None);
    x = ok; x.keystones = ok.cost - 1;         assert(G::CheckOpen(x) == G::Refusal::NoKeystone);
    x = ok; x.keystones = 0;                   assert(G::CheckOpen(x) == G::Refusal::NoKeystone);
    x = ok; x.members = 5;                     assert(G::CheckOpen(x) == G::Refusal::TooManyMembers);
    x = ok; x.memberInRun = true;              assert(G::CheckOpen(x) == G::Refusal::MemberInRun);
    x = ok; x.memberInRun = true; x.level = 99; x.keystones = 0; assert(G::CheckOpen(x) == G::Refusal::MemberInRun);   // told first
    x = ok; x.level = 99; x.keystones = 0;     assert(G::CheckOpen(x) == G::Refusal::AboveUnlocked);                   // level before Keystone
    x = ok; x.cost = 3; x.keystones = 2;       assert(G::CheckOpen(x) == G::Refusal::NoKeystone);                      // the cost is the tunable's
    x.keystones = 3;                           assert(G::CheckOpen(x) == G::Refusal::None);
    assert(G::RefusalText(G::Refusal::NoKeystone, 1, 5, 4, 1, "") == "You need 1 Greater Rift Keystone.");
    assert(G::RefusalText(G::Refusal::NoKeystone, 1, 5, 4, 2, "") == "You need 2 Greater Rift Keystones.");
    assert(G::RefusalText(G::Refusal::MemberInRun, 1, 5, 4, 1, "Second") == "Second is already in a rift.");
    assert(G::RefusalText(G::Refusal::AboveUnlocked, 1, 5, 4, 1, "") == "That Greater Rift level is not available. Choose 1 to 5.");

    // ---- Answer ----
    {
        G::Proposal p; p.roster = {{1}, {2}, {3}};
        assert(G::Answer(p, 9, true) == G::Verdict::NotOnRoster);
        assert(G::Answer(p, 1, true) == G::Verdict::Pending);
        assert(G::Answer(p, 1, true) == G::Verdict::Pending);            // the same answer again is harmless
        assert(G::Answer(p, 1, false) == G::Verdict::AlreadyAnswered);   // the opposite one is refused
        assert(p.roster[0].reply == G::Reply::Accepted);
        assert(G::Answer(p, 2, true) == G::Verdict::Pending);
        assert(G::Answer(p, 3, true) == G::Verdict::Start);               // only when EVERY member accepted
        G::Proposal d; d.roster = {{1}, {2}};
        assert(G::Answer(d, 2, false) == G::Verdict::Declined);
        assert(G::Answer(d, 2, true) == G::Verdict::AlreadyAnswered);
        G::Proposal solo; solo.roster = {{1}};
        assert(G::Answer(solo, 1, true) == G::Verdict::Start);            // a solo opener still answers
        G::Proposal e; e.deadline = 100;
        assert(!G::Expired(e, 99) && G::Expired(e, 100) && G::Expired(e, 101));
        e.deadline = 0xFFFFFFF0u;                                          // the 32-bit ms clock wraps
        assert(!G::Expired(e, 0xFFFFFFE0u) && G::Expired(e, 5));
        p.roster[1].reply = G::Reply::Waiting;
        assert(G::StillWaiting(p) == std::vector<std::uint64_t>{2});
    }

    // ---- Start: the order, and who pays ----
    reset();
    {
        Queued q = make();
        Start(q);
        assert((calls == std::vector<std::string>{"validate", "spend:Opener:%(cost)d", "open"}));   // checked, then paid by the opener only, then opened
        assert(openedBy == &a && opened.level == 7);
        assert((opened.roster == std::vector<Player*>{&a, &b, &c}));                              // the closed roster, in order
        for (Player* p : {&a, &b, &c}) {
            assert(told(*p, G::StartingText(7)) && told(*p, G::StartedText(7)));
            assert(heard[p->guid.raw].size() == 2);
        }
    }
    reset();   // a member the check cannot reach: nothing is paid, nothing opens
    {
        Queued q = make(); world.erase(3);
        Start(q);
        assert(calls.empty());
        assert(told(a, G::CancelMessage(7, G::Reason::StartFailed, "Third is not available.")));
    }
    reset();   // the revalidation refuses: nothing is paid
    {
        validateAnswer = "Second is already in a rift.";
        Start(make());
        assert((calls == std::vector<std::string>{"validate"}));
        for (Player* p : {&a, &b, &c}) assert(told(*p, G::CancelMessage(7, G::Reason::StartFailed, "Second is already in a rift.")));
    }
    reset();   // the Keystone cannot be taken: no run
    {
        spendOk = false;
        Start(make());
        assert((calls == std::vector<std::string>{"validate", "spend:Opener:%(cost)d"}));
        assert(told(b, G::CancelMessage(7, G::Reason::StartFailed, "The Keystone could not be taken.")));
    }
    reset();   // the run fails after the Keystone is paid: it is given back, once, to the opener
    {
        openOk = false;
        Start(make(7, 777));
        assert((calls == std::vector<std::string>{"validate", "spend:Opener:%(cost)d", "open", "refund:Opener:%(cost)d:777"}));
        assert(told(c, G::CancelMessage(7, G::Reason::StartFailed, openError)));
        assert(!told(c, G::StartedText(7)));
    }

    // ---- RespondGreaterRift: the replies, through the real queue ----
    reset();
    {
        make();
        RespondGreaterRift(&a, 1, true);                       assert(told(a, G::StaleText()));          // no such ready check
        RespondGreaterRift(&a, 4242, true);                    assert(told(a, G::AcceptedText()) && queued.size() == 1 && calls.empty());
        RespondGreaterRift(&a, 4242, false);                   assert(told(a, G::AlreadyRecordedText()) && queued.size() == 1);
        Player outsider{ObjectGuid(8), "Outsider"}; world[8] = &outsider; outsider.session.owner = &outsider;
        RespondGreaterRift(&outsider, 4242, true);             assert(told(outsider, G::NotOnRosterText()));
        RespondGreaterRift(&b, 4242, true);                    assert(calls.empty() && queued.size() == 1);
        RespondGreaterRift(&c, 4242, true);                    // the last accept starts it, once
        assert(count("open") == 1 && queued.empty());
        RespondGreaterRift(&c, 4242, true);                    assert(told(c, G::StaleText()) && count("open") == 1);
    }
    reset();   // a decline ends it for everyone, and opens nothing
    {
        make();
        RespondGreaterRift(&a, 4242, true);
        RespondGreaterRift(&b, 4242, false);
        assert(queued.empty() && calls.empty());
        for (Player* p : {&a, &b, &c}) assert(told(*p, G::CancelMessage(7, G::Reason::Declined, "Second")));
    }
    reset();   // an answer after the deadline is too late, even before the tick has said so
    {
        make();
        now += %(timeout)d * 1000;
        RespondGreaterRift(&a, 4242, true);
        assert(told(a, G::StaleText()) && calls.empty());
    }


    // ======== the two windows (docs/contracts/rift-enrollment-messages.md) ========
    assert(router.Add(WINDOW, %(route)s, Window));   // the production registration's limits, on the real router
    std::string const id = "100005";                 // the first ready check after reset(): 100000 + engine value 5

    // ---- L: the opening window gets the levels the server allows, and nothing else ----
    reset();
    OpenWindow(&a);
    assert((pushed[1] == std::vector<std::string>{"L|%(start)d|9|2|%(cost)d"}) && pushed.size() == 1);   // start, unlocked, Keystones held, cost
    assert(heard.empty() && queued.empty());                                                                   // opening the window starts nothing
    unlockedLevel = 41; keystoneCount = 0; pushed.clear();
    OpenWindow(&b);
    assert((pushed[2] == std::vector<std::string>{"L|%(start)d|41|0|%(cost)d"}));                              // the opener's own numbers, read now
    reset(); a.inCombat = true;
    OpenWindow(&a);
    assert(pushed.empty() && told(a, "Use the obelisk from the hub while out of combat."));
    reset(); hub = false;
    OpenWindow(&a);
    assert(pushed.empty() && told(a, "Use the obelisk from the hub while out of combat."));
    reset(); make();
    OpenWindow(&b);
    assert(pushed.empty() && told(b, G::AlreadyQueuedText()));                                                  // one ready check per party

    // ---- C: the opening window closes on walk-away, and the server says so (diablocraft-4a85) ----
    reset();
    OpenWindow(&a); pushed.clear(); findEntry = 0;
    WatchRange();
    assert(pushed.empty() && watching.count(1));                                                                // still at the obelisk: nothing
    assert(findEntry == 910011 && findRange == INTERACTION_DISTANCE);                                           // the open check's own obelisk and range
    a.atObelisk = false;
    WatchRange();
    assert((pushed[1] == std::vector<std::string>{"C"}) && pushed.size() == 1 && watching.empty());            // walked away: C, to that player only
    a.atObelisk = true; WatchRange(); a.atObelisk = false; WatchRange();
    assert(pushed[1].size() == 1);                                                                              // once; a new L starts a new watch
    reset(); OpenWindow(&a); OpenWindow(&b); pushed.clear();
    b.atObelisk = false; WatchRange();
    assert(pushed.size() == 1 && pushed[2] == std::vector<std::string>{"C"} && watching.count(1));             // each player's own range
    reset(); OpenWindow(&a); pushed.clear();
    validateAnswer = "You need 1 Greater Rift Keystone.";
    assert(ask(a, "open\t5") == refused(validateAnswer));                                                     // a refused open: the window stays up
    a.atObelisk = false; WatchRange();
    assert(pushed[1] == std::vector<std::string>{"C"});                                                         // and still closes on walk-away
    reset(); OpenWindow(&a); OpenWindow(&b); ask(a, "open\t7"); pushed.clear();
    a.atObelisk = b.atObelisk = false; WatchRange();
    assert(pushed.empty() && watching.empty() && queued.size() == 1);                                           // the P closed both windows: no C, the ready check untouched
    reset(); OpenWindow(&a); pushed.clear(); world.erase(1); a.atObelisk = false;
    WatchRange();
    assert(pushed.empty() && watching.empty());                                                                 // gone from the world: dropped, nothing sent
    reset(); OpenWindow(&a); pushed.clear(); a.inWorld = false; a.atObelisk = false;
    WatchRange();
    assert(pushed.empty() && watching.empty());
    reset(); a.inCombat = true; OpenWindow(&a);
    assert(watching.empty());                                                                                   // no L, no watch

    // ---- open: the level is the only thing the client sends ----
    reset();
    assert(ask(a, "open\t7") == "");                                                                            // no reply: the P records are the answer
    assert(queued.size() == 1 && queued[0].proposal.level == 7 && queued[0].proposal.opener == 1 && validatedLevel == 7);
    assert(findEntry == 910011 && findRange == INTERACTION_DISTANCE);                                           // at the obelisk, not just anywhere in the hub
    assert(calls == std::vector<std::string>{"validate"} && queued[0].proposal.id == 100005);
    assert(std::count_if(queued[0].proposal.roster.begin(), queued[0].proposal.roster.end(), [](G::Member const& m) { return m.reply != G::Reply::Waiting; }) == 0);
    for (Player* p : {&a, &b, &c}) {   // every member, the opener first among them, gets the window
        assert(pushed[p->guid.raw].size() == 1);
        assert(pushed[p->guid.raw][0] == "P|100005|1|GR|7|1|Opener|%(timeout)d000|3|1|Opener|waiting|2|Second|waiting|3|Third|waiting");
        assert(told(*p, "Accept: .dc rift accept 100005") && told(*p, "Decline: .dc rift decline 100005"));   // the fallback stays
    }
    reset();   // solo: the same ready check with just you
    a.group = nullptr;
    assert(ask(a, "open\t3") == "" && queued.size() == 1 && queued[0].group == 0);
    assert((pushed[1] == std::vector<std::string>{"P|100005|1|GR|3|1|Opener|%(timeout)d000|1|1|Opener|waiting"}) && pushed.size() == 1);
    reset();   // a level the server does not allow is the server's refusal, in the window, and nothing is queued
    validateAnswer = "That Greater Rift level is not available. Choose 1 to 9.";
    assert(ask(a, "open\t99") == refused(validateAnswer) && validatedLevel == 99 && queued.empty() && pushed.empty());
    assert(ask(a, "open\t4294967295") == refused(validateAnswer) && validatedLevel == 4294967295LL);          // any whole number reaches the server's own check
    validateAnswer = "You need 1 Greater Rift Keystone.";
    assert(ask(a, "open\t5") == refused(validateAnswer) && queued.empty() && heard.empty());
    for (char const* bad : {"open", "open\t", "open\t7\t8", "open\t-1", "open\t+7", "open\t4294967296", "open\tx", "open\t 7", "OPEN\t7", "open7", "", "sync\t1", "respond", "launch\t7"}) {
        reset();
        assert(ask(a, bad) == MALFORMED && queued.empty() && calls.empty() && pushed.empty());
    }
    reset(); a.atObelisk = false;
    assert(ask(a, "open\t7") == refused("Stand at the Rift Obelisk to open a Greater Rift.") && queued.empty() && calls.empty());
    reset(); a.inCombat = true;
    assert(ask(a, "open\t7") == refused("Use the obelisk from the hub while out of combat.") && queued.empty() && calls.empty());
    reset(); hub = false;
    assert(ask(a, "open\t7") == refused("Use the obelisk from the hub while out of combat.") && queued.empty());
    reset(); make();
    assert(ask(a, "open\t7") == refused(G::AlreadyQueuedText()) && queued.size() == 1);                         // the opener is already in one
    assert(ask(b, "open\t7") == refused(G::AlreadyQueuedText()) && queued.size() == 1);                         // so is the member who asks
    reset(); party.slots.push_back({ObjectGuid(5), "Ghost"});
    assert(ask(a, "open\t7") == refused(G::CancelMessage(7, G::Reason::Offline, "Ghost")) && queued.empty() && calls.empty());
    reset(); budget = 0;    // a route nobody set the budget for answers nothing and does nothing
    assert(ask(a, "open\t7") == "" && lastOutcome == DC::Bridge::Outcome::Throttled && queued.empty() && calls.empty());

    // ---- respond: the answers, and the pushes every one of them makes ----
    reset();
    ask(a, "open\t7"); pushed.clear(); heard.clear(); calls.clear();                                         // (open validated once; the start validates again)
    assert(ask(a, "respond\t" + id + "\taccept") == "" && told(a, G::AcceptedText()));
    for (Player* p : {&a, &b, &c}) {                       // everyone sees the new status, at a higher revision
        assert(pushed[p->guid.raw].size() == 1);
        assert(pushed[p->guid.raw][0] == "P|100005|2|GR|7|1|Opener|%(timeout)d000|3|1|Opener|accepted|2|Second|waiting|3|Third|waiting");
    }
    now += 5000;                                           // the countdown is the server's: it only runs down
    assert(ask(b, "respond\t" + id + "\taccept") == "");
    assert(pushed[3].back() == "P|100005|3|GR|7|1|Opener|%(timeout_left)d|3|1|Opener|accepted|2|Second|accepted|3|Third|waiting");
    assert(calls.empty() && queued.size() == 1);
    assert(ask(a, "respond\t" + id + "\taccept") == "" && pushed[2].back().rfind("P|100005|4|", 0) == 0);          // the same answer again is harmless
    assert(ask(b, "respond\t" + id + "\tdecline") == refused(G::AlreadyRecordedText()) && queued.size() == 1);    // the opposite one is refused
    assert(ask(c, "respond\t1\taccept") == refused(G::StaleText()));
    Player outsider{ObjectGuid(8), "Outsider"}; world[8] = &outsider; outsider.session.owner = &outsider;
    size_t const seen = pushed[1].size();
    assert(ask(outsider, "respond\t" + id + "\taccept") == refused(G::NotOnRosterText()) && ask(outsider, "respond\t" + id + "\tdecline") == refused(G::NotOnRosterText()));
    assert(queued.size() == 1 && pushed[1].size() == seen && pushed[8].empty());                                  // an outsider changes nothing
    for (std::string const bad : std::vector<std::string>{"respond", "respond\t" + id, "respond\t" + id + "\tmaybe", "respond\t" + id + "\tACCEPT", "respond\t" + id + "\taccept\t1", "respond\t0\taccept", "respond\tx\taccept", "respond\t\taccept", "respond\t-1\tdecline", "respond\t" + id + "\t"})
        assert(ask(c, bad) == MALFORMED && queued.size() == 1);
    pushed.clear(); heard.clear();
    assert(ask(c, "respond\t" + id + "\taccept") == "" && queued.empty());                                         // the last accept starts it, once
    assert((calls == std::vector<std::string>{"validate", "spend:Opener:%(cost)d", "open"}));
    for (Player* p : {&a, &b, &c}) {                                                                               // starting, then started: same revision, no P after the start
        assert((pushed[p->guid.raw] == std::vector<std::string>{
            "T|100005|5|starting|7|Opener||" + G::StartingText(7), "T|100005|5|started|7|Opener||" + G::StartedText(7)}));   // 4 P pushes before it
        assert(told(*p, G::StartingText(7)) && told(*p, G::StartedText(7)));
    }
    reset();   // a decline cancels it for everyone, with the server's words and the reason
    ask(a, "open\t7"); ask(a, "respond\t" + id + "\taccept"); pushed.clear(); calls.clear();
    assert(ask(b, "respond\t" + id + "\tdecline") == "" && queued.empty() && calls.empty());
    for (Player* p : {&a, &b, &c})
        assert((pushed[p->guid.raw] == std::vector<std::string>{"T|100005|3|cancelled|7|Opener|declined|" + G::CancelMessage(7, G::Reason::Declined, "Second")}));
    assert(ask(c, "respond\t" + id + "\taccept") == refused(G::StaleText()));                                      // nothing left to answer
    reset();   // the start fails: starting, then the cancel with its own words
    ask(a, "open\t7"); validateAnswer = "Second is already in a rift."; calls.clear();   // fine when opened, not any more at the start
    ask(a, "respond\t" + id + "\taccept"); ask(b, "respond\t" + id + "\taccept"); pushed.clear();
    ask(c, "respond\t" + id + "\taccept");
    for (Player* p : {&a, &b, &c})
        assert((pushed[p->guid.raw] == std::vector<std::string>{"T|100005|4|starting|7|Opener||" + G::StartingText(7),
            "T|100005|4|cancelled|7|Opener|start_failed|" + G::CancelMessage(7, G::Reason::StartFailed, "Second is already in a rift.")}));

    // ---- Tick pushes the cancel too, to everyone it can still reach ----
    reset();
    make(); now += %(timeout)d * 1000;
    Tick();
    for (Player* p : {&a, &b, &c})
        assert((pushed[p->guid.raw] == std::vector<std::string>{"T|4242|2|cancelled|7|Opener|timeout|" + G::CancelMessage(7, G::Reason::Timeout, "Opener, Second, Third")}));
    reset();   // a member who logged out of the world has no window to push to, and nothing crashes
    make(); world.erase(3); b.inWorld = false;
    Tick();
    assert(pushed[3].empty() && pushed[1].size() == 1 && pushed[1][0].find("|logout|") != std::string::npos);
    reset();   // the group changed
    make(); c.group = nullptr; party.slots.pop_back();
    Tick();
    assert(pushed[1].size() == 1 && pushed[1][0].find("|party_changed|") != std::string::npos);
    reset();
    make(); a.group = b.group = c.group = nullptr;
    Tick();
    assert(pushed[2].size() == 1 && pushed[2][0].find("|disbanded|") != std::string::npos);

    // ---- sync: a reloaded window gets the ready check back with its own deadline, and nothing else ----
    reset();
    ask(a, "open\t7"); ask(a, "respond\t" + id + "\taccept"); pushed.clear();
    now += 12000;
    assert(ask(b, "sync") == "" && pushed.size() == 1);
    assert(pushed[2] == std::vector<std::string>{"P|100005|2|GR|7|1|Opener|%(timeout_sync)d|3|1|Opener|accepted|2|Second|waiting|3|Third|waiting"});
    assert(queued.size() == 1 && queued[0].revision == 2 && queued[0].proposal.deadline == 1000 + %(timeout)d * 1000);   // nothing created or renewed
    pushed.clear();
    assert(ask(outsider, "sync") == "" && pushed.empty());                                                         // no ready check, no answer
    {   // another party's ready check is not this player's to see
        Queued other = queued[0]; other.proposal.id = 555; other.proposal.roster = {{8, G::Reply::Waiting}}; other.names = {{8, "Outsider"}};
        queued.push_back(other); world[8] = &outsider;
        assert(ask(b, "sync") == "" && pushed.size() == 1 && pushed[2].size() == 1 && pushed[2][0].rfind("P|100005|", 0) == 0);
        pushed.clear(); assert(ask(outsider, "sync") == "" && pushed.size() == 1 && pushed[8][0].rfind("P|555|", 0) == 0);
        queued.pop_back(); pushed.clear();
    }
    assert(ask(b, "sync\t1") == MALFORMED);
    reset(); assert(ask(a, "sync") == "" && pushed.empty());

    // ---- the records themselves ----
    {
        G::Proposal p; p.id = 999999; p.opener = 4294967295u; p.level = 75; p.deadline = 140000;
        std::map<std::uint64_t, std::string> names;
        for (std::uint64_t g = 4294967291u; g <= 4294967295u; ++g) { p.roster.push_back({g, G::Reply::Accepted}); names[g] = "Abcdefghijkl"; }
        auto fields = G::ProposalRecord(p, 99, names, 100000);
        std::string joined; for (size_t i = 0; i < fields.size(); ++i) joined += (i ? "|" : "") + fields[i];
        assert(std::string("DCRIFTENROLL").size() + 1 + joined.size() <= DC::Bridge::MaxMessage);                     // five full names fit the wire cap
        assert(G::RemainingMs(p, 140000) == 0 && G::RemainingMs(p, 140001) == 0 && G::RemainingMs(p, 139999) == 1);   // never negative
        p.deadline = 0xFFFFFFF0u; assert(G::RemainingMs(p, 0xFFFFFFE0u) == 16 && G::RemainingMs(p, 5) == 0);          // the 32-bit clock wraps
        names.clear(); p.deadline = 5000;
        assert(G::ProposalRecord(p, 1, names, 4000)[6] == "");                                                       // a name the server lost is empty, never another field
    }
    {
        int seen = 0;
        for (G::Reason r : {G::Reason::Declined, G::Reason::Timeout, G::Reason::Offline, G::Reason::Logout, G::Reason::PartyChanged, G::Reason::Disbanded, G::Reason::StartFailed}) {
            std::string const want = std::string(",") + %(reasons_c)s + ",";
            assert(want.find(std::string(",") + G::ReasonWord(r) + ",") != std::string::npos); ++seen;                 // every reason word is in the contract
        }
        assert(seen == 7);
        std::string const statuses = std::string(",") + %(statuses_c)s + ",";
        for (G::Reply r : {G::Reply::Waiting, G::Reply::Accepted, G::Reply::Declined})
            assert(statuses.find(std::string(",") + G::StatusWord(r) + ",") != std::string::npos);
        assert(G::LevelsRecord(1, 25, 3, 1) == (std::vector<std::string>{"L", "1", "25", "3", "1"}));
    }

    // ---- Tick: the clock and the roster ----
    reset();
    {
        Queued q = make();
        Tick();
        assert(queued.size() == 1 && heard.empty());           // nothing wrong: it stays
        q.proposal.roster[0].reply = G::Reply::Accepted;
        queued[0].proposal.roster[0].reply = G::Reply::Accepted;
        now += %(timeout)d * 1000 - 1;
        Tick();
        assert(queued.size() == 1);                            // one ms before the deadline
        now += 1;
        Tick();
        assert(queued.empty());
        for (Player* p : {&a, &b, &c}) assert(told(*p, G::CancelMessage(7, G::Reason::Timeout, "Second, Third")));   // only who was still waiting
    }
    reset();   // a member logs out
    {
        make(); b.inWorld = false;
        Tick();
        assert(queued.empty() && told(a, G::CancelMessage(7, G::Reason::Logout, "Second")));
    }
    reset();   // a member leaves the group
    {
        make(); c.group = nullptr; party.slots.pop_back();
        Tick();
        assert(queued.empty() && told(a, G::CancelMessage(7, G::Reason::PartyChanged, "Third left")));
    }
    reset();   // a stranger joins the group
    {
        make(); party.slots.push_back({ObjectGuid(5), "Newcomer"});
        Tick();
        assert(queued.empty() && told(b, G::CancelMessage(7, G::Reason::PartyChanged, "Newcomer joined")));
    }
    reset();   // the party disbands
    {
        make(); a.group = b.group = c.group = nullptr;
        Tick();
        assert(queued.empty() && told(c, G::CancelMessage(7, G::Reason::Disbanded, "")));
    }
    reset();   // a solo opener: no group before, none now, stays until its own deadline
    {
        Queued q = make(); queued.clear();
        q.group = 0; q.proposal.roster.resize(1); q.names = {{1, "Opener"}}; a.group = nullptr;
        queued.push_back(q);
        Tick();
        assert(queued.size() == 1);
        now += %(timeout)d * 1000;
        Tick();
        assert(queued.empty() && told(a, G::CancelMessage(7, G::Reason::Timeout, "Opener")));
    }
}
''' % {'ready': READY.as_posix(), 'start': START, 'cost': COST, 'timeout': TIMEOUT, 'route': route.group(1),
        'timeout_left': TIMEOUT * 1000 - 5000, 'timeout_sync': TIMEOUT * 1000 - 12000,
        'reasons_c': '"%s"' % reasons, 'statuses_c': '"%s"' % statuses}

code = (HARNESS % {'ready': READY.as_posix(), 'bridge': BRIDGE.as_posix(), 'start': START, 'cost': COST, 'timeout': TIMEOUT}) + DEFS + MAIN

cmake = shutil.which('cmake')
if not cmake:
    raise SystemExit('cmake is not on PATH; this harness compiles a small C++ program')
with tempfile.TemporaryDirectory(prefix='dc-gr-open-') as directory:
    folder = Path(directory)
    (folder / 'test.cpp').write_text(code, encoding='utf-8')
    (folder / 'CMakeLists.txt').write_text(
        'cmake_minimum_required(VERSION 3.20)\nproject(gr_open LANGUAGES CXX)\nset(CMAKE_CXX_STANDARD 20)\n'
        'add_executable(gr_open test.cpp)\ntarget_compile_options(gr_open PRIVATE -UNDEBUG)\n', encoding='utf-8')
    env = dict(os.environ)
    subprocess.run([cmake, '-S', directory, '-B', str(folder / 'build')], env=env, check=True)
    subprocess.run([cmake, '--build', str(folder / 'build')], env=env, check=True)
    harness_env.run([str(folder / 'build' / 'gr_open')], env=env, check=True)
print('PASS: Greater Rift opening: refusals, ready check, start order and refund, timeout and roster, words, tunables.')
