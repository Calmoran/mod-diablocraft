/*
 * World of DiabloCraft - opening a Greater Rift.
 *
 * The rules (docs/proposals/greater-rifts.md): the obelisk offers Nephalem Rift or Greater
 * Rift; the opener picks a level up to their own highest unlocked; one Greater Rift Keystone is
 * taken from the OPENER only; then the 09-rifts 7.9.2 ready check, start, closed roster and the
 * shared 15:00 deadline (the quest's own TimeAllowed). The refusals are clean and named: no
 * Keystone, a level above the opener's unlocked, a member already in a run.
 *
 * The two windows (docs/contracts/rift-enrollment-messages.md): picking Greater
 * Rift at the obelisk sends the opening window its level list (and C when the player walks away from the
 * obelisk, the artisan windows' range watch); its Open button and every member's
 * Accept / Decline come back as DCRIFTENROLL messages and enter the same functions as before. The
 * ready check pushes its state to the windows (P, T); `.dc rift accept <id>` / `.dc rift decline <id>`
 * stay as 7.9.4's player-accessible fallback, and the proposal's own chat lines tell every member so.
 */

#include "dc_gr_open.h"

#include "dc_gr_level.h"
#include "dc_gr_ready.h"
#include "dc_rift_quests.h"
#include "dc_rifts_internal.h"
#include "../common/dc_account_economy.h"
#include "../common/dc_bridge.h"
#include "../common/dc_tunables.h"
#include "../common/dc_world.h"
#include "../loot/dc_loot.h"

#include "Chat.h"
#include "GameObject.h"
#include "Group.h"
#include "Log.h"
#include "ObjectAccessor.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "PlayerEconomy.h"
#include "ScriptMgr.h"
#include "ScriptedGossip.h"
#include "Timer.h"
#include "WorldSession.h"

#include <algorithm>
#include <map>
#include <mutex>
#include <set>
#include <string>
#include <vector>

namespace DC::Rifts
{
    unsigned PartyCap();

    namespace
    {
        // Constants: the obelisk menu's two item actions, and the gossip text it is shown over
        // (the Keeper uses the same one).
        constexpr uint32 ACTION_NEPHALEM = 1, ACTION_GREATER = 2, MENU_TEXT = 1;

        // Identifiers: the window bridge prefix of the two windows (the contract), and the hub's Rift
        // Obelisk template (910011, as dc_rifts.cpp and dc_shatter.cpp each keep it).
        constexpr char const* WINDOW = "DCRIFTENROLL";
        constexpr std::uint32_t OBELISK_ENTRY = 910011;

        unsigned Tunable(char const* name)
        {
            return static_cast<unsigned>(DC::Tunables::Get("rifts", name));
        }

        Player* Online(std::uint64_t raw)
        {
            return ObjectAccessor::FindPlayer(ObjectGuid(raw));
        }

        void Say(Player* player, std::string const& text)
        {
            if (player && player->GetSession())
                ChatHandler(player->GetSession()).SendSysMessage(text);
        }

        // --- the Keystone: the account ledger with the economy on, the bag item with it off ------

        std::uint64_t Keystones(Player* player)
        {
            return DC::AccountEconomy::Enabled() ? DC::AccountEconomy::MaterialBalance(player, KEYSTONE_ITEM)
                                                 : player->GetItemCount(KEYSTONE_ITEM, false);
        }

        bool SpendKeystones(Player* player, unsigned count)
        {
            if (!DC::AccountEconomy::Enabled())
            {
                player->DestroyItemCount(KEYSTONE_ITEM, count, true);
                return true;
            }
            PlayerEconomy::Scope scope(player);
            if (!DC::AccountEconomy::DebitMaterial(player, KEYSTONE_ITEM, count))
                PlayerEconomy::Fail();
            return scope.Finish();
        }

        // A run that never started owes the Keystone back.
        void RefundKeystones(Player* player, unsigned count, std::uint64_t proposalId)
        {
            PlayerEconomy::Scope scope(player);
            if (!DC::Loot::GrantMaterial(player, KEYSTONE_ITEM, count,
                                         "gr:refund:" + std::to_string(proposalId) + ":" +
                                             std::to_string(player->GetGUID().GetCounter())))
                PlayerEconomy::Fail();
            if (!scope.Finish())
                LOG_ERROR("server", "[DC rifts] Greater Rift Keystone refund for {} did not commit (ready check {})",
                          player->GetName(), proposalId);
        }

        // --- the proposals ------------------------------------------------------------------------

        struct Queued
        {
            Gr::Proposal proposal;
            std::uint64_t group = 0; // the group's raw guid, 0 for a solo opener
            unsigned revision = 1;   // of the P last pushed; a later P is higher (the contract)
            std::map<std::uint64_t, std::string> names;
        };

        std::mutex proposalMutex;
        std::vector<Queued> queued;

        std::string Names(Queued const& q, std::vector<std::uint64_t> const& guids)
        {
            std::string out;
            for (std::uint64_t guid : guids)
            {
                if (!out.empty())
                    out += ", ";
                auto found = q.names.find(guid);
                out += found == q.names.end() ? std::to_string(guid) : found->second;
            }
            return out;
        }

        void SayAll(Queued const& q, std::string const& text)
        {
            for (Gr::Member const& member : q.proposal.roster)
                Say(Online(member.guid), text);
        }

        // --- the windows' records (the contract; the roster's, never the client's, say who) ---------

        void Push(Player* player, std::vector<std::string> const& fields)
        {
            if (player && !DC::Bridge::Push(player, WINDOW, fields))
                LOG_ERROR("server", "[DC rifts] {} record for {} was not sent (too long, or no session)", fields[0],
                          player->GetName());
        }

        // The ready check as it stands, to every roster member online, or to `only`.
        void PushProposal(Queued const& q, Player* only = nullptr)
        {
            std::vector<std::string> const record = Gr::ProposalRecord(q.proposal, q.revision, q.names, getMSTime());
            for (Gr::Member const& member : q.proposal.roster)
                if (Player* player = Online(member.guid); player && (!only || player == only))
                    Push(player, record);
        }

        // `message` is the sentence SayAll sends in chat; the window shows the same one. `to` is the
        // roster as Players when Online() can no longer find them (the start, below).
        void PushResult(Queued const& q, char const* state, char const* reason, std::string const& message,
                        std::vector<Player*> const* to = nullptr)
        {
            auto const opener = q.names.find(q.proposal.opener);
            std::vector<std::string> const record = Gr::ResultRecord(
                q.proposal, q.revision + 1, state, opener == q.names.end() ? "" : opener->second, reason, message);
            if (to)
                for (Player* player : *to)
                    Push(player, record);
            else
                for (Gr::Member const& member : q.proposal.roster)
                    Push(Online(member.guid), record);
        }

        // Everyone on the original roster hears it, including a member who has just left (7.9.4).
        void Cancel(Queued const& q, Gr::Reason reason, std::string const& names)
        {
            std::string const message = Gr::CancelMessage(q.proposal.level, reason, names);
            SayAll(q, message);
            PushResult(q, "cancelled", Gr::ReasonWord(reason), message);
            LOG_INFO("server", "[DC rifts] Greater Rift {} ready check {} cancelled ({})", q.proposal.level,
                     q.proposal.id, message);
        }

        bool ProposalFor(std::uint64_t guid)
        {
            std::lock_guard<std::mutex> lock(proposalMutex);
            return std::any_of(queued.begin(), queued.end(),
                               [&](Queued const& q)
                               {
                                   return std::any_of(q.proposal.roster.begin(), q.proposal.roster.end(),
                                                      [&](Gr::Member const& m) { return m.guid == guid; });
                               });
        }

        // --- what a roster must satisfy, at Queue and again at the start --------------------------

        // "" when the roster may open a Greater Rift of `level`, else the sentence for the opener.
        std::string Validate(Player* opener, std::vector<Player*> const& roster, long long level)
        {
            std::uint32_t questId = 0;
            {
                std::lock_guard<std::mutex> lock(dataMutex);
                questId = greaterQuest.id;
            }
            if (!questId)
                return "The Greater Rift quest is not loaded; see the startup log.";
            Quest const* anyQuest = sObjectMgr->GetQuestTemplate(questId);
            if (!anyQuest)
                return "The Greater Rift quest is missing; apply rifts_0011_rift_quests.sql.";

            Gr::OpenAsk ask;
            ask.level = level;
            ask.start = Tunable("greater_rift_start_level");
            ask.unlocked = GreaterRiftLevels(opener->GetGUID().GetCounter()).unlocked;
            ask.cost = Tunable("greater_rift_keystone_cost");
            ask.keystones = Keystones(opener);
            ask.members = static_cast<unsigned>(roster.size());
            ask.partyCap = PartyCap();
            std::string who;
            for (Player* member : roster)
            {
                std::string const name = member->GetName();
                if (!member->IsInWorld() || !member->GetSession() || !DC::World::IsInHub(member) ||
                    member->IsInCombat())
                    return name + " must be in the hub, out of combat.";
                if (!member->IsAlive())
                    return name + " is dead.";
                if (!PlayableClass(member))
                    return name + "'s class cannot enter a rift yet.";
                Rift run;
                if (EnrolledRun(member->GetGUID(), run) || Current(member, run))
                {
                    ask.memberInRun = true;
                    who = name;
                    break;
                }
                // One timed quest at a time, and a free slot: all of it before anything is paid.
                {
                    QuestStatus const status = member->GetQuestStatus(questId);
                    if (status != QUEST_STATUS_NONE && status != QUEST_STATUS_REWARDED)
                        return name + " still has a Greater Rift quest in their log.";
                }
                if (!member->CanAddQuest(anyQuest, false) || !member->SatisfyQuestTimed(anyQuest, false))
                    return name + " has no room for the quest (a full quest log or another timed quest).";
            }
            return Gr::RefusalText(Gr::CheckOpen(ask), ask.start, ask.unlocked, ask.partyCap, ask.cost, who);
        }

        // The roster as Players: the opener's group, every member online, or the opener alone.
        // False with the offline member's name in `offline`.
        bool BuildRoster(Player* opener, std::vector<Player*>& roster, std::string& offline)
        {
            Group* group = opener->GetGroup();
            if (!group)
            {
                roster.push_back(opener);
                return true;
            }
            for (Group::MemberSlot const& slot : group->GetMemberSlots())
            {
                Player* member = ObjectAccessor::FindPlayer(slot.guid);
                if (!member || !member->IsInWorld())
                {
                    offline = slot.name;
                    return false;
                }
                roster.push_back(member);
            }
            return true;
        }

        // --- Queue ---------------------------------------------------------------------------------

        void Queue(Player* opener, long long level, std::vector<Player*> const& roster)
        {
            Queued q;
            q.proposal.opener = opener->GetGUID().GetRawValue();
            q.proposal.level = static_cast<unsigned>(level);
            q.proposal.deadline = getMSTime() + Tunable("gr_proposal_timeout_seconds") * 1000;
            q.group = opener->GetGroup() ? opener->GetGroup()->GetGUID().GetRawValue() : 0;
            for (Player* member : roster)
            {
                q.proposal.roster.push_back({member->GetGUID().GetRawValue(), Gr::Reply::Waiting});
                q.names[member->GetGUID().GetRawValue()] = member->GetName();
            }
            {
                std::lock_guard<std::mutex> lock(proposalMutex);
                // Short enough to type. A reply to a proposal from before a restart finds none
                // (the list is empty) unless it lands on a fresh id by chance, and then it is only
                // an answer from someone on that new roster.
                // ponytail: random 6 digits, not a persisted counter; add one if replies from
                // before a restart ever matter.
                do
                    q.proposal.id = 100000 + Engine()() % 900000;
                while (std::any_of(queued.begin(), queued.end(),
                                   [&](Queued const& other) { return other.proposal.id == q.proposal.id; }));
                queued.push_back(q);
            }
            std::string const id = std::to_string(q.proposal.id);
            std::string const seconds = std::to_string(Tunable("gr_proposal_timeout_seconds"));
            SayAll(q, "Greater Rift " + std::to_string(q.proposal.level) + " ready check from " + opener->GetName() +
                          ". Respond within " + seconds + " s.");
            SayAll(q, "Accept: .dc rift accept " + id);
            SayAll(q, "Decline: .dc rift decline " + id);
            PushProposal(q);
            LOG_INFO("server", "[DC rifts] {} queued Greater Rift {} for {} (ready check {})", opener->GetName(),
                     q.proposal.level, roster.size(), q.proposal.id);
        }

        // --- the start -----------------------------------------------------------------------------

        // Every member answered Accept. Re-check everything, take the opener's Keystone, open the
        // run. Anything that fails before the run exists cancels the whole attempt with the
        // Keystone untouched; a failure after it gives the Keystone back.
        void Start(Queued const& q)
        {
            unsigned const level = q.proposal.level;
            auto fail = [&](std::string const& why) { Cancel(q, Gr::Reason::StartFailed, why); };
            SayAll(q, Gr::StartingText(level));
            PushResult(q, "starting", "", Gr::StartingText(level));

            std::vector<Player*> roster;
            for (Gr::Member const& member : q.proposal.roster)
            {
                Player* player = Online(member.guid);
                if (!player)
                    return fail(Names(q, {member.guid}) + " is not available.");
                roster.push_back(player);
            }
            Player* opener = Online(q.proposal.opener);
            if (!opener)
                return fail("The opener is not available.");
            if (std::string const why = Validate(opener, roster, level); !why.empty())
                return fail(why);

            unsigned const cost = Tunable("greater_rift_keystone_cost");
            if (!SpendKeystones(opener, cost))
                return fail("The Keystone could not be taken.");
            GreaterStart start;
            start.level = level;
            start.roster = roster;
            std::string error;
            if (!OpenRun(opener, nullptr, nullptr, error, &start))
            {
                RefundKeystones(opener, cost, q.proposal.id);
                return fail(error);
            }
            // OpenRun has teleported the roster, and a player between maps is out of the world, so
            // Online() finds no one: the Players resolved above hear it.
            for (Player* player : roster)
                Say(player, Gr::StartedText(level));
            PushResult(q, "started", "", Gr::StartedText(level), &roster);
        }

        // --- the clock ------------------------------------------------------------------------------

        // Once a second: the deadline, and the roster still being who it was.
        void Tick()
        {
            struct Done
            {
                Queued q;
                Gr::Reason reason;
                std::string names;
            };
            std::vector<Done> done;
            {
                std::lock_guard<std::mutex> lock(proposalMutex);
                for (auto it = queued.begin(); it != queued.end();)
                {
                    Done verdict{*it, Gr::Reason::Timeout, ""};
                    bool cancel = false;
                    std::set<std::uint64_t> roster;
                    for (Gr::Member const& member : it->proposal.roster)
                    {
                        roster.insert(member.guid);
                        Player* player = Online(member.guid);
                        if (!player || !player->IsInWorld())
                        {
                            if (!cancel)
                                verdict = {*it, Gr::Reason::Logout, Names(*it, {member.guid})};
                            cancel = true;
                        }
                    }
                    if (!cancel)
                    {
                        // Who is in the group now against who was when it was queued.
                        unsigned noGroup = 0;
                        for (Gr::Member const& member : it->proposal.roster)
                        {
                            Player* player = Online(member.guid);
                            Group* group = player->GetGroup();
                            std::uint64_t const now = group ? group->GetGUID().GetRawValue() : 0;
                            if (!now)
                                ++noGroup;
                            if (now != it->group && !cancel)
                            {
                                verdict = {*it, Gr::Reason::PartyChanged, Names(*it, {member.guid}) + " left"};
                                cancel = true;
                            }
                            if (!cancel && group)
                                for (Group::MemberSlot const& slot : group->GetMemberSlots())
                                    if (!roster.count(slot.guid.GetRawValue()))
                                    {
                                        verdict = {*it, Gr::Reason::PartyChanged, slot.name + " joined"};
                                        cancel = true;
                                        break;
                                    }
                        }
                        if (cancel && it->group && noGroup == it->proposal.roster.size())
                            verdict = {*it, Gr::Reason::Disbanded, ""};
                    }
                    if (!cancel && Gr::Expired(it->proposal, getMSTime()))
                    {
                        verdict = {*it, Gr::Reason::Timeout, Names(*it, Gr::StillWaiting(it->proposal))};
                        cancel = true;
                    }
                    if (!cancel)
                    {
                        ++it;
                        continue;
                    }
                    done.push_back(verdict);
                    it = queued.erase(it);
                }
            }
            for (Done const& d : done)
                Cancel(d.q, d.reason, d.names);
        }

        // --- the opening window's walk-away (the contract's C; the artisan windows' range watch) ------

        // Constant: dc_crafting.lua's WATCH_MS, the same poll for the same job.
        constexpr uint32 WATCH_MS = 500;

        std::mutex watchMutex;
        std::set<std::uint64_t> watching; // were sent L, and their opening window has not closed since

        // Who walks out of the open check's own range of the obelisk is sent C. A member of a ready
        // check (its P closed the window) or a player gone from the world is dropped unsent.
        void WatchRange()
        {
            std::set<std::uint64_t> all;
            {
                std::lock_guard<std::mutex> lock(watchMutex);
                all = watching;
            }
            for (std::uint64_t guid : all)
            {
                Player* player = Online(guid);
                bool const gone = !player || !player->IsInWorld() || ProposalFor(guid);
                bool const away = !gone && !player->FindNearestGameObject(OBELISK_ENTRY, INTERACTION_DISTANCE);
                if (!gone && !away)
                    continue;
                {
                    std::lock_guard<std::mutex> lock(watchMutex);
                    watching.erase(guid);
                }
                if (away)
                    Push(player, {"C"});
            }
        }

        class GreaterRiftWorld final : public WorldScript
        {
        public:
            GreaterRiftWorld()
                : WorldScript("dc_gr_open_world", {WORLDHOOK_ON_UPDATE})
            {
            }
            void OnUpdate(uint32 diff) override
            {
                watchElapsed += diff;
                if (watchElapsed >= WATCH_MS)
                {
                    watchElapsed = 0;
                    WatchRange();
                }
                elapsed += diff;
                if (elapsed < 1000)
                    return;
                elapsed = 0;
                Tick();
            }

        private:
            uint32 elapsed = 0, watchElapsed = 0;
        };

        // The opener picked Greater Rift at the obelisk: the opening window gets the levels it may open
        // and the Keystones it holds. The server checks all of it again on `open`.
        void OpenWindow(Player* player)
        {
            if (!DC::World::IsInHub(player) || player->IsInCombat())
                return Say(player, "Use the obelisk from the hub while out of combat.");
            if (ProposalFor(player->GetGUID().GetRawValue()))
                return Say(player, Gr::AlreadyQueuedText());
            Push(player, Gr::LevelsRecord(Tunable("greater_rift_start_level"),
                                          GreaterRiftLevels(player->GetGUID().GetCounter()).unlocked,
                                          Keystones(player), Tunable("greater_rift_keystone_cost")));
            std::lock_guard<std::mutex> lock(watchMutex);
            watching.insert(player->GetGUID().GetRawValue());
        }

        // The opening window's Open: the level is all the client says. "" when the ready check was
        // queued, else the sentence for the opener.
        std::string Begin(Player* opener, long long level)
        {
            if (!DC::World::IsInHub(opener) || opener->IsInCombat())
                return "Use the obelisk from the hub while out of combat.";
            if (!opener->FindNearestGameObject(OBELISK_ENTRY, INTERACTION_DISTANCE))
                return "Stand at the Rift Obelisk to open a Greater Rift.";
            if (ProposalFor(opener->GetGUID().GetRawValue()))
                return Gr::AlreadyQueuedText();
            std::vector<Player*> roster;
            std::string offline;
            if (!BuildRoster(opener, roster, offline))
                return Gr::CancelMessage(static_cast<unsigned>(level), Gr::Reason::Offline, offline);
            for (Player* member : roster)
                if (ProposalFor(member->GetGUID().GetRawValue()))
                    return Gr::AlreadyQueuedText();
            if (std::string const why = Validate(opener, roster, level); !why.empty())
                return why;
            Queue(opener, level, roster);
            return "";
        }

        // One ready answer: "" when taken, else the sentence for the one who sent it.
        std::string Respond(Player* player, std::uint64_t proposalId, bool accept)
        {
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            Queued snapshot;
            Gr::Verdict verdict = Gr::Verdict::Pending;
            bool found = false;
            {
                std::lock_guard<std::mutex> lock(proposalMutex);
                auto it = std::find_if(queued.begin(), queued.end(),
                                       [&](Queued const& q) { return q.proposal.id == proposalId; });
                if (it != queued.end())
                {
                    found = true;
                    // The deadline is the server's: a late answer is a timeout the next tick has not
                    // yet announced.
                    if (Gr::Expired(it->proposal, getMSTime()))
                        found = false;
                    else
                    {
                        verdict = Gr::Answer(it->proposal, guid, accept);
                        if (verdict == Gr::Verdict::Pending)
                            ++it->revision;
                        snapshot = *it;
                        if (verdict == Gr::Verdict::Declined || verdict == Gr::Verdict::Start)
                        {
                            queued.erase(it);
                        }
                    }
                }
            }
            if (!found)
                return Gr::StaleText();
            switch (verdict)
            {
                case Gr::Verdict::NotOnRoster:
                    return Gr::NotOnRosterText();
                case Gr::Verdict::AlreadyAnswered:
                    return Gr::AlreadyRecordedText();
                case Gr::Verdict::Pending:
                    Say(player, Gr::AcceptedText());
                    PushProposal(snapshot);
                    return "";
                case Gr::Verdict::Declined:
                    Cancel(snapshot, Gr::Reason::Declined, Names(snapshot, {guid}));
                    return "";
                case Gr::Verdict::Start:
                    break;
            }
            Start(snapshot);
            return "";
        }

        // `sync`: a reloaded window asks for the ready check it lost. Nothing is created or renewed;
        // PushProposal sends a roster only to a member on it.
        void Resend(Player* player)
        {
            std::vector<Queued> all;
            {
                std::lock_guard<std::mutex> lock(proposalMutex);
                all = queued;
            }
            for (Queued const& q : all)
                PushProposal(q, player);
        }

        // DCRIFTENROLL. Every rule is checked in the functions above; a message names a level or an
        // answer and nothing else.
        void Window(Player& player, DC::Bridge::Request const& request, DC::Bridge::Wire<Player> const& /*wire*/)
        {
            auto const verb = request.Token(0, 8);
            if (!verb)
                throw DC::Bridge::Refusal(DC::Bridge::TextMalformed);
            std::string why;
            if (*verb == "open" && request.Count() == 2)
            {
                auto const level = request.Uint(1, 0, 0xFFFFFFFFu);
                if (!level)
                    throw DC::Bridge::Refusal(DC::Bridge::TextMalformed);
                why = Begin(&player, *level);
            }
            else if (*verb == "respond" && request.Count() == 3)
            {
                auto const id = request.Uint(1, 1, 0xFFFFFFFFu);
                auto const decision = request.Token(2, 7);
                if (!id || !decision || (*decision != "accept" && *decision != "decline"))
                    throw DC::Bridge::Refusal(DC::Bridge::TextMalformed);
                why = Respond(&player, *id, *decision == "accept");
            }
            else if (*verb == "sync" && request.Count() == 1)
                Resend(&player);
            else
                throw DC::Bridge::Refusal(DC::Bridge::TextMalformed);
            if (!why.empty())
                throw DC::Bridge::Refusal(why);
        }
    } // namespace

    void OpenObeliskMenu(Player* player, GameObject* obelisk)
    {
        Rift run;
        if (PartyRun(player, run))
            return OfferRiftQuest(player, obelisk);
        ClearGossipMenuFor(player);
        AddGossipItemFor(player, GOSSIP_ICON_BATTLE, "Nephalem Rift", GOSSIP_SENDER_MAIN, ACTION_NEPHALEM);
        AddGossipItemFor(player, GOSSIP_ICON_BATTLE, "Greater Rift", GOSSIP_SENDER_MAIN, ACTION_GREATER);
        SendGossipMenuFor(player, MENU_TEXT, obelisk->GetGUID());
    }

    bool ObeliskSelect(Player* player, GameObject* obelisk, uint32 sender, uint32 action, char const* /*code*/)
    {
        if (sender != GOSSIP_SENDER_MAIN || (action != ACTION_NEPHALEM && action != ACTION_GREATER))
            return false;
        ClearGossipMenuFor(player);
        CloseGossipMenuFor(player);
        if (!player->IsWithinDistInMap(obelisk, INTERACTION_DISTANCE))
            return true;
        if (action == ACTION_NEPHALEM)
            OfferRiftQuest(player, obelisk);
        else
            OpenWindow(player);
        return true;
    }

    void RespondGreaterRift(Player* player, std::uint64_t proposalId, bool accept)
    {
        if (std::string const why = Respond(player, proposalId, accept); !why.empty())
            Say(player, why);
    }

    void RegisterGreaterRiftOpenScripts()
    {
        new GreaterRiftWorld();
        // The window's budget is the artisan windows' rows (the contract, Budget).
        if (!DC::Bridge::Routes().Add(WINDOW, {"crafting", "artisan_burst", "artisan_per_second"}, Window))
            LOG_ERROR("server", "[DC rifts] the {} window route was not registered", WINDOW);
    }
} // namespace DC::Rifts
