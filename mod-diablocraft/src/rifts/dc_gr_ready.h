/*
 * World of DiabloCraft - opening a Greater Rift.
 *
 * The decisions of the obelisk's Greater Rift path with no core in them: what the opener may ask
 * for, what a ready-check reply does, and the player-facing words (09-rifts 7.9.4's table). The
 * glue that reads players, groups and the keystone balance is dc_gr_open.cpp; this file is what
 * the test compiles. Internal to the rifts folder.
 */

#ifndef DC_GR_READY_H
#define DC_GR_READY_H

#include <algorithm>
#include <cstdint>
#include <map>
#include <string>
#include <vector>

namespace DC::Rifts::Gr
{
    // --- what the opener may ask for ----------------------------------------------

    enum class Refusal
    {
        None,
        MemberInRun,
        TooManyMembers,
        BelowStart,
        AboveUnlocked,
        NoKeystone
    };

    struct OpenAsk
    {
        long long level = 0;                   // as typed
        unsigned start = 1;                    // greater_rift_start_level
        unsigned unlocked = 1;                 // the OPENER's own highest unlocked level
        std::uint64_t keystones = 0, cost = 1; // the opener's Keystones; greater_rift_keystone_cost
        unsigned members = 1, partyCap = 4;
        bool memberInRun = false;
    };

    // The refusals, in the order a player is told them: a member already in a run
    // first (nothing the opener does fixes that), then the level, then the Keystone.
    inline Refusal CheckOpen(OpenAsk const& ask)
    {
        if (ask.memberInRun)
            return Refusal::MemberInRun;
        if (ask.members > ask.partyCap)
            return Refusal::TooManyMembers;
        if (ask.level < static_cast<long long>(ask.start))
            return Refusal::BelowStart;
        if (ask.level > static_cast<long long>(ask.unlocked))
            return Refusal::AboveUnlocked;
        if (ask.keystones < ask.cost)
            return Refusal::NoKeystone;
        return Refusal::None;
    }

    // --- the ready check ------------------------------------------------------------

    enum class Reply : std::uint8_t
    {
        Waiting,
        Accepted,
        Declined
    };

    struct Member
    {
        std::uint64_t guid = 0;
        Reply reply = Reply::Waiting;
    };

    struct Proposal
    {
        std::uint64_t id = 0, opener = 0;
        unsigned level = 0;
        std::vector<Member> roster; // snapshot at Queue; closed for the life of the proposal
        std::uint32_t deadline = 0; // server ms
    };

    enum class Verdict
    {
        Pending,
        Start,
        Declined,
        NotOnRoster,
        AlreadyAnswered
    };

    // One reply. A repeat of the same answer is harmless; the opposite answer after one is recorded
    // is refused (7.9.4). The first decline ends the proposal; everyone accepted starts it.
    inline Verdict Answer(Proposal& proposal, std::uint64_t guid, bool accept)
    {
        auto found = std::find_if(proposal.roster.begin(), proposal.roster.end(),
                                  [&](Member const& member) { return member.guid == guid; });
        if (found == proposal.roster.end())
            return Verdict::NotOnRoster;
        Reply const wanted = accept ? Reply::Accepted : Reply::Declined;
        if (found->reply != Reply::Waiting && found->reply != wanted)
            return Verdict::AlreadyAnswered;
        found->reply = wanted;
        if (!accept)
            return Verdict::Declined;
        bool const all = std::all_of(proposal.roster.begin(), proposal.roster.end(),
                                     [](Member const& member) { return member.reply == Reply::Accepted; });
        return all ? Verdict::Start : Verdict::Pending;
    }

    // Wrap-safe: the server's ms clock is 32 bits.
    inline bool Expired(Proposal const& proposal, std::uint32_t now)
    {
        return static_cast<std::int32_t>(now - proposal.deadline) >= 0;
    }

    inline std::vector<std::uint64_t> StillWaiting(Proposal const& proposal)
    {
        std::vector<std::uint64_t> out;
        for (Member const& member : proposal.roster)
            if (member.reply == Reply::Waiting)
                out.push_back(member.guid);
        return out;
    }

    // --- the words (09-rifts 7.9.4's table, verbatim apart from the placeholders) -----

    enum class Reason
    {
        Declined,
        Timeout,
        Offline,
        Logout,
        PartyChanged,
        Disbanded,
        StartFailed
    };

    // `names` is the comma-joined names the reason is about; for a start failure it is the sentence
    // saying why. Party-changed carries "<name> joined/left" in `names`.
    inline std::string CancelMessage(unsigned level, Reason reason, std::string const& names)
    {
        std::string const head = "Greater Rift " + std::to_string(level) + " cancelled";
        switch (reason)
        {
            case Reason::Declined:
                return head + ". Declined: " + names + ".";
            case Reason::Timeout:
                return head + ". No response: " + names + ".";
            case Reason::Offline:
                return head + ". Unavailable: " + names + " (offline).";
            case Reason::Logout:
                return head + ". " + names + " logged out.";
            case Reason::PartyChanged:
                return head + ". Party changed: " + names + ".";
            case Reason::Disbanded:
                return head + ". The party disbanded.";
            case Reason::StartFailed:
                return head + " before start. " + names;
        }
        return head + ".";
    }

    inline std::string RefusalText(Refusal refusal, unsigned start, unsigned unlocked, unsigned partyCap,
                                   std::uint64_t cost, std::string const& who)
    {
        switch (refusal)
        {
            case Refusal::None:
                return "";
            case Refusal::MemberInRun:
                return who + " is already in a rift.";
            case Refusal::TooManyMembers:
                return "Greater Rifts support one to " + std::to_string(partyCap) + " players.";
            case Refusal::BelowStart:
            case Refusal::AboveUnlocked:
                return "That Greater Rift level is not available. Choose " + std::to_string(start) + " to " +
                       std::to_string(unlocked) + ".";
            case Refusal::NoKeystone:
                return "You need " + std::to_string(cost) + " Greater Rift Keystone" + (cost == 1 ? "" : "s") + ".";
        }
        return "";
    }

    inline std::string StartingText(unsigned level)
    {
        return "Everyone accepted. Starting Greater Rift " + std::to_string(level) + "...";
    }
    inline std::string StartedText(unsigned level)
    {
        return "Greater Rift " + std::to_string(level) + " has started. Entering the rift.";
    }
    inline std::string AcceptedText()
    {
        return "Accepted. Waiting for the party.";
    }
    inline std::string AlreadyRecordedText()
    {
        return "Your response is already recorded.";
    }
    inline std::string StaleText()
    {
        return "That Greater Rift ready check is no longer active.";
    }
    inline std::string NotOnRosterText()
    {
        return "You are not a member of that Greater Rift ready check.";
    }
    inline std::string AlreadyQueuedText()
    {
        return "Your party already has a Greater Rift ready check in progress.";
    }

    // --- the records the windows are sent (docs/contracts/rift-enrollment-messages.md) --

    inline char const* StatusWord(Reply reply)
    {
        return reply == Reply::Accepted ? "accepted" : reply == Reply::Declined ? "declined" : "waiting";
    }

    inline char const* ReasonWord(Reason reason)
    {
        switch (reason)
        {
            case Reason::Declined:
                return "declined";
            case Reason::Timeout:
                return "timeout";
            case Reason::Offline:
                return "offline";
            case Reason::Logout:
                return "logout";
            case Reason::PartyChanged:
                return "party_changed";
            case Reason::Disbanded:
                return "disbanded";
            case Reason::StartFailed:
                return "start_failed";
        }
        return "";
    }

    // Server ms left at send, never negative; wrap-safe like Expired.
    inline std::uint32_t RemainingMs(Proposal const& proposal, std::uint32_t now)
    {
        std::int32_t const left = static_cast<std::int32_t>(proposal.deadline - now);
        return left > 0 ? static_cast<std::uint32_t>(left) : 0;
    }

    // `L`: the opening window. The openable levels are start..unlocked.
    inline std::vector<std::string> LevelsRecord(unsigned start, unsigned unlocked, std::uint64_t keystones,
                                                 std::uint64_t cost)
    {
        return {"L", std::to_string(start), std::to_string(unlocked), std::to_string(keystones),
                std::to_string(cost)};
    }

    // `P`: the ready check as it stands. A guid or id is a low guid; `names` maps a roster guid to its name.
    inline std::vector<std::string> ProposalRecord(Proposal const& proposal, unsigned revision,
                                                   std::map<std::uint64_t, std::string> const& names,
                                                   std::uint32_t now)
    {
        auto const name = [&](std::uint64_t guid)
        {
            auto const found = names.find(guid);
            return found == names.end() ? std::string() : found->second;
        };
        std::vector<std::string> out{"P",
                                     std::to_string(proposal.id),
                                     std::to_string(revision),
                                     "GR",
                                     std::to_string(proposal.level),
                                     std::to_string(proposal.opener),
                                     name(proposal.opener),
                                     std::to_string(RemainingMs(proposal, now)),
                                     std::to_string(proposal.roster.size())};
        for (Member const& member : proposal.roster)
        {
            out.push_back(std::to_string(member.guid));
            out.push_back(name(member.guid));
            out.push_back(StatusWord(member.reply));
        }
        return out;
    }

    // `T`: how the ready check ended, or that it is starting. `reason` is "" unless cancelled.
    inline std::vector<std::string> ResultRecord(Proposal const& proposal, unsigned revision, char const* state,
                                                 std::string const& openerName, char const* reason,
                                                 std::string const& message)
    {
        return {"T",
                std::to_string(proposal.id),
                std::to_string(revision),
                state,
                std::to_string(proposal.level),
                openerName,
                reason,
                message};
    }
} // namespace DC::Rifts::Gr

#endif // DC_GR_READY_H
