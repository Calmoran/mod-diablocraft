/*
 * World of DiabloCraft - the window bridge (contract
 * docs/contracts/window-bridge.md).
 *
 * A window action reaches the server as a plain addon message "PREFIX<TAB>field<TAB>field",
 * which OnPlayerBeforeSendChatMessage sees before the chat handler's switch. This header is
 * everything between that message and the checked C++ function a window's button calls:
 *
 *   prefix router -> per-player token bucket (per prefix) -> bounded parser -> handler
 *
 * and the one reply shape, "PREFIX<TAB>X|message", for a refusal. It includes no core header,
 * so the compiled test (scripts/tests/ui/test_window_bridge.py) drives the production code itself; the
 * PlayerScript and the packet live in dc_bridge.cpp. Actor is the core's Player (a test double
 * in the test): it only has to answer GetGUID().GetRawValue().
 *
 * Order matters and is part of the contract: the bucket runs BEFORE the parser, and a request
 * over budget is dropped without a word. A flood therefore costs the server one prefix lookup
 * per message and earns no reply, so no reply is ever sent faster than the bucket allows.
 * dc_request_gap.h holds the bucket next to the G1 gap: one header, one clock.
 */
#ifndef DC_BRIDGE_H
#define DC_BRIDGE_H

#include "dc_request_gap.h"
#include "dc_tunables.h"

#include <cstddef>
#include <cstdint>
#include <exception>
#include <functional>
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <utility>
#include <vector>

namespace DC::Bridge
{
    // The 3.3.5a client sends an addon message of at most 255 bytes (prefix, tab and payload
    // together), and the client reassembles a reply under the same cap. Protocol constants,
    // not game numbers.
    constexpr std::size_t MaxMessage = 255;
    constexpr std::size_t MaxPrefix = 16;
    constexpr std::size_t MaxFields = 16;

    // The refusal texts the router itself sends (contract: refusal codes).
    constexpr char const* TextMalformed = "That request was not understood.";
    constexpr char const* TextFailed = "That did not work.";

    // A handler refuses with this; the router sends "X|text" and nothing else.
    class Refusal : public std::exception
    {
    public:
        explicit Refusal(std::string text)
            : text_(std::move(text))
        {
        }
        char const* what() const noexcept override
        {
            return text_.c_str();
        }

    private:
        std::string text_;
    };

    // The payload after the prefix, split on tabs. Every accessor is bounded and returns
    // nullopt for anything that is not exactly the wanted shape; a handler never sees a raw
    // number string, and never calls stoul.
    class Request
    {
    public:
        std::vector<std::string> fields;

        std::size_t Count() const
        {
            return fields.size();
        }

        // Digits only, no sign, no space, no leading '+', within [lo, hi], no overflow.
        std::optional<std::uint32_t> Uint(std::size_t index, std::uint32_t lo, std::uint32_t hi) const
        {
            if (index >= fields.size())
                return std::nullopt;
            std::string const& text = fields[index];
            if (text.empty() || text.size() > 10)
                return std::nullopt;
            std::uint64_t value = 0;
            for (char c : text)
            {
                if (c < '0' || c > '9')
                    return std::nullopt;
                value = value * 10 + static_cast<std::uint64_t>(c - '0');
            }
            if (value < lo || value > hi)
                return std::nullopt;
            return static_cast<std::uint32_t>(value);
        }

        std::optional<bool> Flag(std::size_t index) const
        {
            if (index >= fields.size() || (fields[index] != "0" && fields[index] != "1"))
                return std::nullopt;
            return fields[index] == "1";
        }

        // A verb or key: [A-Za-z0-9_], 1..maxLen bytes.
        std::optional<std::string> Token(std::size_t index, std::size_t maxLen) const
        {
            if (index >= fields.size() || fields[index].empty() || fields[index].size() > maxLen)
                return std::nullopt;
            for (char c : fields[index])
                if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_'))
                    return std::nullopt;
            return fields[index];
        }
    };

    // Splits `message` after "PREFIX<TAB>" on tabs, keeping empty fields (DCSLOT sends an empty
    // rune). False when the message is over the wire cap, has too many fields or holds a control
    // byte. The prefix counts into the cap because the client's does.
    inline bool Parse(std::string const& message, std::size_t prefixLength, Request& out)
    {
        out.fields.clear();
        if (message.size() > MaxMessage)
            return false;
        for (char c : message)
            if ((static_cast<unsigned char>(c) < 0x20 && c != '\t') || c == 0x7f)
                return false;
        if (message.size() <= prefixLength)
            return true;
        std::size_t begin = prefixLength + 1; // past the tab
        for (;;)
        {
            std::size_t end = message.find('\t', begin);
            out.fields.push_back(message.substr(begin, end == std::string::npos ? std::string::npos : end - begin));
            if (out.fields.size() > MaxFields)
                return false;
            if (end == std::string::npos)
                return true;
            begin = end + 1;
        }
    }

    // A field of a reply record: the separators cannot appear inside it.
    inline std::string Clean(std::string text)
    {
        for (char& c : text)
            if (c == '|' || c == '\t' || static_cast<unsigned char>(c) < 0x20 || c == 0x7f)
                c = ' ';
        return text;
    }

    // "X|message", cut so prefix + tab + record fits the wire cap.
    inline std::string RefusalRecord(std::string const& prefix, std::string const& text)
    {
        std::string record = "X|" + Clean(text);
        std::size_t room = MaxMessage - prefix.size() - 1;
        if (record.size() > room)
            record.resize(room);
        return record;
    }

    // Handed to a handler: the one way to answer. Record() joins fields with '|' and cleans
    // them. A record that would not fit the wire cap is a handler bug: nothing is sent and the
    // handler gets false, rather than a truncated record with a wrong last number.
    template<class Actor>
    class Wire
    {
    public:
        using Sender = std::function<void(Actor*, std::string const& prefix, std::string const& record)>;
        Wire(Sender const& send, Actor* actor, std::string const& prefix)
            : send_(send)
            , actor_(actor)
            , prefix_(prefix)
        {
        }

        bool Record(std::vector<std::string> const& fields) const
        {
            std::string record;
            for (std::size_t i = 0; i < fields.size(); ++i)
                record += (i ? "|" : "") + Clean(fields[i]);
            if (prefix_.size() + 1 + record.size() > MaxMessage)
                return false;
            send_(actor_, prefix_, record);
            return true;
        }

    private:
        Sender const& send_;
        Actor* actor_;
        std::string const& prefix_;
    };

    // Where a route's two numbers live (rows in data/tunables/<category>.csv). Both are
    // tunables; a row nobody set means the route refuses every request.
    struct Limits
    {
        std::string category, burst, perSecond;
    };

    enum class Outcome
    {
        NotBridge, // not a registered prefix: the message is none of ours
        Throttled, // over the bucket: dropped, no reply
        Refused,   // parsed badly or the handler refused: an X record went out
        Handled,
    };

    template<class Actor>
    class Router
    {
    public:
        using Handler = std::function<void(Actor&, Request const&, Wire<Actor> const&)>;
        using Sender = typename Wire<Actor>::Sender;

        explicit Router(Sender send)
            : send_(std::move(send))
        {
        }

        // Startup only; a route is never added while players are sending. False for a bad or
        // repeated prefix ("DC" + 1..14 of A-Z0-9, inside the client's 16-byte prefix cap).
        bool Add(std::string const& prefix, Limits limits, Handler handler)
        {
            if (prefix.size() < 3 || prefix.size() > MaxPrefix || prefix.compare(0, 2, "DC") != 0 ||
                routes_.count(prefix))
                return false;
            for (std::size_t i = 2; i < prefix.size(); ++i)
                if (!((prefix[i] >= 'A' && prefix[i] <= 'Z') || (prefix[i] >= '0' && prefix[i] <= '9')))
                    return false;
            auto route = std::make_unique<Route>();
            route->limits = std::move(limits);
            route->handler = std::move(handler);
            routes_.emplace(prefix, std::move(route));
            return true;
        }

        Outcome Dispatch(Actor* actor, std::string const& message, std::uint64_t nowMs)
        {
            std::size_t tab = message.find('\t');
            std::string prefix = message.substr(0, tab == std::string::npos ? message.size() : tab);
            if (prefix.size() > MaxPrefix)
                return Outcome::NotBridge;
            auto found = routes_.find(prefix);
            if (found == routes_.end())
                return Outcome::NotBridge;
            Route& route = *found->second;

            // The budget first: a flood is dropped before it is parsed or answered.
            auto const& limits = route.limits;
            if (!route.bucket.Admit(actor->GetGUID().GetRawValue(), nowMs,
                                    DC::Gap::BurstFromTunable(DC::Tunables::Get(limits.category, limits.burst)),
                                    DC::Gap::RateFromTunable(DC::Tunables::Get(limits.category, limits.perSecond))))
                return Outcome::Throttled;

            Request request;
            if (!Parse(message, prefix.size(), request))
            {
                send_(actor, prefix, RefusalRecord(prefix, TextMalformed));
                return Outcome::Refused;
            }
            Wire<Actor> wire(send_, actor, found->first);
            try
            {
                route.handler(*actor, request, wire);
            }
            catch (Refusal const& refusal)
            {
                send_(actor, prefix, RefusalRecord(prefix, refusal.what()));
                return Outcome::Refused;
            }
            catch (std::exception const&)
            {
                // what() of a library exception can name a table or a path; the player gets a plain line.
                send_(actor, prefix, RefusalRecord(prefix, TextFailed));
                return Outcome::Refused;
            }
            return Outcome::Handled;
        }

    private:
        struct Route
        {
            Limits limits;
            Handler handler;
            DC::Gap::PerPlayerBucket bucket;
        };
        Sender send_;
        std::map<std::string, std::unique_ptr<Route>> routes_;
    };
} // namespace DC::Bridge

class Player;

namespace DC::Bridge
{
    // The server's router; dc_bridge.cpp owns it. Each window's file calls Routes().Add() from
    // its RegisterScripts(); the loader runs DC::Bridge::RegisterScripts() before any of them.
    Router<Player>& Routes();

    // A record the server sends with no request to answer (a window's push). Same wire, same
    // 255-byte cap as Wire::Record: false and nothing sent when it does not fit or the player has no session.
    bool Push(Player* player, std::string const& prefix, std::vector<std::string> const& fields);
    void RegisterScripts();
} // namespace DC::Bridge

#endif
