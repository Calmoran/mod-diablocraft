/*
 * World of DiabloCraft - the Artisan and Jeweler window handlers (contract
 * docs/contracts/window-bridge.md).
 *
 * DCARTISAN and DCJEWELER carry the same actions `.dc artisan` and `.dc jeweler` carry. This header
 * is everything between the bridge's parsed Request and the checked functions in src/crafting (dc_crafting_internal.h):
 * strict field parsing, the NPC gate, the call, and the reply (the result plus what changed in the
 * player's account funds, bags and rolled items). It includes no core header, so the compiled test
 * (scripts/tests/crafting/test_crafting_window.py) drives this production code with a fake Game; dc_crafting.cpp
 * supplies the real one, whose methods call Artisan(), Salvage(), Craft(), Socket() and the rest
 * unchanged. The rules stay where they live: this file adds none.
 *
 * Game is a duck-typed template argument:
 *   void Gate(Npc)                       throws when the NPC is out of range, dead, in combat, trading...
 *                                        (Npc::Nobody: the player's own state only, no NPC needed)
 *   void Salvage(guid) / Bulk(rarity) / Craft(id, count) / Repair(Npc) / Transmog() / Socket(guid, seq, gem)
 *   void Combine(id, count) / Jewelry(id, count)
 *   EnchantState Place(guid)             the Mystic's view of one item: its lines and price, or its pending choices
 *   std::vector<EnchantAffix> Preview(guid, seq)   what a line can become (the `?`)
 *   void Roll(guid, seq) / Pick(guid, choice)      pay and store three choices / apply one (1 keeps the line)
 *   bool SocketFilled(guid, seq)         does that socket row hold a gem right now (true when unsure)
 *   Bags Carried() / Funds Balance()     the player's bags and account funds right now, in memory
 *   std::optional<Rolled> Detail(guid, withOffers)   the rolled-item rows, nullopt for a plain stack
 *   void Failed()                        an action threw: roll the account operation back
 */
#ifndef DC_CRAFTING_WINDOW_H
#define DC_CRAFTING_WINDOW_H

#include "dc_bridge.h"

#include <cstdint>
#include <cstdio>
#include <exception>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <utility>
#include <vector>

namespace DC::Crafting::Window
{
    enum class Npc
    {
        Blacksmith,
        Mystic,
        Jeweler,
        Nobody, // no NPC: the player must be alive, out of combat and not trading, nothing more
        Cube,   // Kanai's Cube, an object in the Sanctum (dc_cube_window.h): the player's own state and the Cube in reach
    };

    // Which gate a socket request needs: putting a gem into an EMPTY socket works
    // anywhere; taking a gem out, or putting one over another, is the Jeweler's. dc_jeweler.cpp's
    // Socket() and the handler below both ask this, so the rule is written once.
    constexpr Npc SocketGate(bool gemGiven, bool socketFilled)
    {
        return gemGiven && !socketFilled ? Npc::Nobody : Npc::Jeweler;
    }

    // What the player carries (equipment, backpack, bags; not the bank), keyed by item guid.
    // bag and slot are the core's raw values (255 = equipment or backpack, 19..22 = a bag).
    struct Held
    {
        std::uint32_t entry = 0, count = 0, bag = 0, slot = 0;
        bool operator==(Held const& other) const
        {
            return entry == other.entry && count == other.count && bag == other.bag && slot == other.slot;
        }
    };
    using Bags = std::map<std::uint64_t, Held>;

    // The account ledger as decimal strings (exact, never a number). valid is false when the
    // account economy is off or the ledger could not be read; nothing is reported then.
    struct Funds
    {
        bool valid = false;
        std::string gold;
        std::map<std::uint32_t, std::string> materials;
    };

    struct AffixRow
    {
        unsigned seq = 0;
        std::string id, kind;
        double value = 0;
        bool rerolled = false;
        int parent = -1;
        std::uint32_t gem = 0;
    };
    struct OfferRow
    {
        unsigned choice = 0;
        std::string id;
        double value = 0;
    };
    struct Rolled
    {
        std::string rarity;
        bool locked = false;
        unsigned attempts = 0;
        std::vector<AffixRow> affixes;
        std::vector<OfferRow> offers;
    };

    // The Mystic window's view of one item (docs/contracts/mystic-enchant-messages.md).
    // A line and a choice share a shape: the property, the pool it rolls in (primary, secondary or socket),
    // its roll (value2 and min2/max2 only on a two-part damage line) and, for a line, what it can become.
    struct EnchantAffix
    {
        unsigned seq = 0;
        std::string id, kind;
        int state = 0; // a line: 0 open, 1 enchanted, 2 gems in it, 3 nothing else it could be; unused in a choice
        double value = 0, value2 = 0, min = 0, max = 0, min2 = 0, max2 = 0;
    };
    struct EnchantMaterial
    {
        std::uint32_t entry = 0; // 0: any Imperial gem, none held
        std::string need, have, name;
        bool ok = false;
    };
    struct EnchantState
    {
        std::uint64_t guid = 0;
        std::uint32_t entry = 0;
        std::string rarity;
        bool enchanted = false, bind = false, pending = false;
        unsigned attempts = 0;
        std::vector<EnchantAffix> lines;   // pending == false
        std::vector<EnchantAffix> choices; // pending == true: the current line, then the two stored rolls
        std::string gold = "0";            // the next roll's price in published gold
        bool goldOk = false;
        std::vector<EnchantMaterial> materials;
    };
    // A paid roll shows the current line and two new ones.
    constexpr std::uint32_t EnchantChoices = 3;

    // Room in a packed record's fields, under the bridge's 255-byte wire cap after the prefix and
    // the record letter. A single field is far smaller than this.
    constexpr std::size_t PackBudget = 200;
    constexpr std::uint32_t Max = UINT32_MAX;

    inline std::string Number(double value)
    {
        char text[32];
        std::snprintf(text, sizeof text, "%.10g", value);
        return text;
    }

    // Sends `head` then as many `parts` as fit, again for the rest. Nothing to send when parts is empty.
    template<class W>
    void Pack(W const& wire, std::vector<std::string> const& head, std::vector<std::string> const& parts)
    {
        std::vector<std::string> record = head;
        std::size_t size = 0;
        for (auto const& field : head)
            size += field.size() + 1;
        std::size_t used = 0;
        for (auto const& part : parts)
        {
            if (used && size + part.size() + 1 > PackBudget)
            {
                wire.Record(record);
                record = head;
                size = 0;
                for (auto const& field : head)
                    size += field.size() + 1;
                used = 0;
            }
            record.push_back(part);
            size += part.size() + 1;
            ++used;
        }
        if (used)
            wire.Record(record);
    }

    inline std::string Num(std::uint64_t value)
    {
        return std::to_string(value);
    }

    // The rows of one rolled item: the item record, its affixes and, when asked, its open offers.
    template<class W>
    void SendRolled(W const& wire, std::uint64_t guid, Held const& held, Rolled const& rolled)
    {
        wire.Record({"A", Num(guid), Num(held.entry), Num(held.bag), Num(held.slot), rolled.rarity,
                     rolled.locked ? "1" : "0", Num(rolled.attempts)});
        std::vector<std::string> affixes, offers;
        for (auto const& a : rolled.affixes)
            affixes.push_back(Num(a.seq) + ":" + a.id + ":" + Number(a.value) + ":" + a.kind + ":" +
                              (a.rerolled ? "1" : "0") + ":" + std::to_string(a.parent) + ":" + Num(a.gem));
        for (auto const& o : rolled.offers)
            offers.push_back(Num(o.choice) + ":" + o.id + ":" + Number(o.value));
        Pack(wire, {"F", Num(guid)}, affixes);
        Pack(wire, {"O", Num(guid)}, offers);
    }

    inline std::string Packed(EnchantAffix const& a, std::string const& head, bool withState)
    {
        std::string out = head + ":" + a.id + ":" + a.kind + ":";
        if (withState)
            out += std::to_string(a.state) + ":";
        return out + Number(a.value) + ":" + Number(a.value2) + ":" + Number(a.min) + ":" + Number(a.max) + ":" +
               Number(a.min2) + ":" + Number(a.max2);
    }

    // N, then C (a roll is waiting) or L, P and T (the lines, the price and the materials). The window
    // draws what arrives and works nothing out.
    template<class W>
    void SendEnchant(W const& wire, EnchantState const& state)
    {
        std::string const guid = Num(state.guid);
        wire.Record({"N", guid, Num(state.entry), state.rarity, state.enchanted ? "1" : "0", Num(state.attempts),
                     state.bind ? "1" : "0", state.pending ? "1" : "0"});
        std::vector<std::string> parts;
        if (state.pending)
        {
            unsigned number = 0;
            for (auto const& choice : state.choices)
                parts.push_back(Packed(choice, Num(++number), false));
            Pack(wire, {"C", guid}, parts);
            return;
        }
        for (auto const& line : state.lines)
            parts.push_back(Packed(line, Num(line.seq), true));
        Pack(wire, {"L", guid}, parts);
        wire.Record({"P", guid, state.gold, state.goldOk ? "1" : "0"});
        for (auto const& material : state.materials)
            wire.Record({"T", guid, Num(material.entry), material.need, material.have, material.ok ? "1" : "0",
                         material.name});
    }

    // V: what a line can become, with the range each would roll in.
    template<class W>
    void SendPreview(W const& wire, std::uint64_t guid, unsigned seq, std::vector<EnchantAffix> const& entries)
    {
        std::vector<std::string> parts;
        for (auto const& e : entries)
            parts.push_back(e.id + ":" + e.kind + ":" + Number(e.min) + ":" + Number(e.max) + ":" + Number(e.min2) +
                            ":" + Number(e.max2));
        Pack(wire, {"V", Num(guid), Num(seq)}, parts);
    }

    // What changed between two states, as records. `touched` is an item the action rewrote in
    // place (a socket, an enchant offer): it is sent whole even if its slot and count are equal.
    // Returns the number of items removed and added, for the result count.
    struct Counts
    {
        std::size_t removed = 0, added = 0;
    };
    template<class Game, class W>
    Counts Report(Game& game, W const& wire, Bags const& before, Funds const& fundsBefore, std::uint64_t touched)
    {
        Bags after = game.Carried();
        Funds fundsAfter = game.Balance();
        Counts counts;

        if (fundsBefore.valid && fundsAfter.valid)
        {
            if (fundsBefore.gold != fundsAfter.gold)
                wire.Record({"B", fundsAfter.gold});
            std::vector<std::string> changed;
            for (auto const& [entry, amount] : fundsAfter.materials)
            {
                auto was = fundsBefore.materials.find(entry);
                if (was == fundsBefore.materials.end() || was->second != amount)
                    changed.push_back(Num(entry) + ":" + amount);
            }
            Pack(wire, {"M"}, changed);
        }

        std::vector<std::string> removed;
        for (auto const& [guid, held] : before)
            if (!after.count(guid))
                removed.push_back(Num(guid));
        counts.removed = removed.size();
        Pack(wire, {"D"}, removed);

        std::vector<std::string> stacks;
        std::set<std::uint64_t> want;
        for (auto const& [guid, held] : after)
        {
            auto was = before.find(guid);
            if (was == before.end())
                ++counts.added;
            if (was == before.end() || !(was->second == held) || guid == touched)
                want.insert(guid);
        }
        for (auto guid : want)
        {
            Held const& held = after.at(guid);
            if (auto rolled = game.Detail(guid, guid == touched))
                SendRolled(wire, guid, held, *rolled);
            else
                stacks.push_back(Num(guid) + ":" + Num(held.entry) + ":" + Num(held.count) + ":" + Num(held.bag) + ":" +
                                 Num(held.slot));
        }
        Pack(wire, {"I"}, stacks);
        return counts;
    }

    // A precondition or read-only call: the game's runtime errors carry the texts the commands
    // print, so they reach the window as its refusal; the router would otherwise hide them.
    template<class F>
    void Plain(F&& call)
    {
        try
        {
            call();
        }
        catch (Bridge::Refusal const&)
        {
            throw;
        }
        catch (std::exception const& error)
        {
            throw Bridge::Refusal(error.what());
        }
    }

    // The one execution path: gate, run, report what changed, then the result. A failed action
    // still reports what it changed (a craft that stopped halfway made items) and then refuses.
    // The router turns any exception but Refusal into a generic line, so the game's runtime
    // errors (the same texts the commands print) are converted here.
    template<class Game, class W, class Action, class Tail>
    void Execute(Game& game, W const& wire, char const* verb, Npc npc, std::uint64_t touched, bool craft,
                 Action&& action, Tail&& tail)
    {
        Plain([&] { game.Gate(npc); });
        Bags before = game.Carried();
        Funds fundsBefore = game.Balance();
        bool failed = false;
        std::string failure;
        try
        {
            action();
        }
        catch (std::exception const& error)
        {
            failed = true;
            failure = error.what();
            game.Failed();
        }
        if (failed)
        {
            Report(game, wire, before, fundsBefore, 0);
            throw Bridge::Refusal(failure);
        }
        // The result first so the window knows what the records after it belong to.
        Bags after = game.Carried();
        std::size_t added = 0, removed = 0;
        for (auto const& [guid, held] : after)
            added += !before.count(guid);
        for (auto const& [guid, held] : before)
            removed += !after.count(guid);
        wire.Record({"R", verb, Num(craft ? added : removed)});
        Report(game, wire, before, fundsBefore, touched);
        tail();
        wire.Record({"E", verb});
    }
    template<class Game, class W, class Action>
    void Execute(Game& game, W const& wire, char const* verb, Npc npc, std::uint64_t touched, bool craft,
                 Action&& action)
    {
        Execute(game, wire, verb, npc, touched, craft, std::forward<Action>(action), [] {});
    }

    // A field that may be left out: absent gives the fallback, present but malformed is refused.
    inline std::uint32_t OptionalUint(Bridge::Request const& request, std::size_t index, std::uint32_t low,
                                      std::uint32_t high, std::uint32_t fallback, char const* message)
    {
        if (request.Count() <= index)
            return fallback;
        auto value = request.Uint(index, low, high);
        if (!value)
            throw Bridge::Refusal(message);
        return *value;
    }
    inline std::uint32_t RequiredUint(Bridge::Request const& request, std::size_t index, std::uint32_t low,
                                      std::uint32_t high, char const* message)
    {
        auto value = request.Uint(index, low, high);
        if (!value)
            throw Bridge::Refusal(message);
        return *value;
    }
    inline void Exactly(Bridge::Request const& request, std::size_t most, std::size_t least = 0)
    {
        if (request.Count() > most || request.Count() < least)
            throw Bridge::Refusal(Bridge::TextMalformed);
    }

    // DCARTISAN: verb, then salvage guid | bulk rarity | craft id [count] | place guid | preview guid seq |
    // roll guid seq | pick guid choice | repair [0|1] | transmog (and forge, repairquote, repairitems). The same actions as
    // `.dc artisan`, with the same defaults: craft's count is 1 when left out; repair 0 is the
    // Blacksmith, 1 the Mystic.
    template<class Game, class Actor>
    void Artisan(Game& game, Bridge::Request const& request, Bridge::Wire<Actor> const& wire)
    {
        auto verb = request.Token(0, 12);
        if (!verb)
            throw Bridge::Refusal("Choose an action.");
        char const* bad = "That request was not understood.";
        if (*verb == "salvage")
        {
            Exactly(request, 2, 2);
            auto guid = RequiredUint(request, 1, 1, Max, bad);
            Execute(game, wire, "salvage", Npc::Blacksmith, 0, false, [&] { game.Salvage(guid); });
        }
        else if (*verb == "bulk")
        {
            Exactly(request, 2, 2);
            auto rarity = RequiredUint(request, 1, 0, Max, bad);
            Execute(game, wire, "bulk", Npc::Blacksmith, 0, false, [&] { game.Bulk(rarity); });
        }
        else if (*verb == "craft")
        {
            Exactly(request, 3, 2);
            auto id = RequiredUint(request, 1, 1, Max, bad);
            auto count = OptionalUint(request, 2, 1, Max, 1, bad);
            Execute(game, wire, "craft", Npc::Blacksmith, 0, true, [&] { game.Craft(id, count); });
        }
        else if (*verb == "forge")
        {
            Exactly(request, 3, 3);
            auto id = RequiredUint(request, 1, 1, Max, bad);
            auto count = RequiredUint(request, 2, 1, Max, bad);
            Execute(game, wire, "forge", Npc::Blacksmith, 0, true, [&] { game.Forge(id, count); });
        }
        else if (*verb == "repairquote" || *verb == "repairitems")
        {
            Exactly(request, 3, 3);
            auto scope = RequiredUint(request, 1, 0, 2, bad);
            auto guid = RequiredUint(request, 2, 0, Max, bad);
            if ((scope == 0) != (guid > 0))
                throw Bridge::Refusal(bad);
            if (*verb == "repairquote")
            {
                Plain([&] {
                    game.Gate(Npc::Blacksmith);
                    auto price = game.RepairPrice(scope, guid);
                    wire.Record({"Q", Num(scope), Num(guid), price.first, price.second ? "1" : "0"});
                });
                wire.Record({"E", "repairquote"});
            }
            else
                Execute(game, wire, "repairitems", Npc::Blacksmith, 0, false, [&] { game.RepairItems(scope, guid); });
        }
        else if (*verb == "place")
        {
            // Read-only: the item went into the Mystic's slot.
            Exactly(request, 2, 2);
            auto guid = RequiredUint(request, 1, 1, Max, bad);
            EnchantState state;
            Plain([&] { game.Gate(Npc::Mystic); state = game.Place(guid); });
            wire.Record({"R", "place", Num(guid)});
            SendEnchant(wire, state);
            wire.Record({"E", "place"});
        }
        else if (*verb == "preview")
        {
            // Read-only: the `?` on one line.
            Exactly(request, 3, 3);
            auto guid = RequiredUint(request, 1, 1, Max, bad);
            auto seq = RequiredUint(request, 2, 0, Max, bad);
            std::vector<EnchantAffix> entries;
            Plain([&] { game.Gate(Npc::Mystic); entries = game.Preview(guid, seq); });
            wire.Record({"R", "preview", Num(guid)});
            SendPreview(wire, guid, seq, entries);
            wire.Record({"E", "preview"});
        }
        else if (*verb == "roll")
        {
            // Pays now and stores the three choices; the reply is the item's state, with them.
            Exactly(request, 3, 3);
            auto guid = RequiredUint(request, 1, 1, Max, bad);
            auto seq = RequiredUint(request, 2, 0, Max, bad);
            Execute(game, wire, "roll", Npc::Mystic, 0, false, [&] { game.Roll(guid, seq); },
                    [&] { SendEnchant(wire, game.Place(guid)); });
        }
        else if (*verb == "pick")
        {
            // Choice 1 is the current line: the item stays as it was and the roll stays paid.
            Exactly(request, 3, 3);
            auto guid = RequiredUint(request, 1, 1, Max, bad);
            auto choice = RequiredUint(request, 2, 1, EnchantChoices, "That choice is not available.");
            Execute(game, wire, "pick", Npc::Mystic, 0, false, [&] { game.Pick(guid, choice); },
                    [&] { SendEnchant(wire, game.Place(guid)); });
        }
        else if (*verb == "repair")
        {
            Exactly(request, 2);
            auto which = OptionalUint(request, 1, 0, 1, 0, bad);
            Execute(game, wire, "repair", which == 1 ? Npc::Mystic : Npc::Blacksmith, 0, false,
                    [&] { game.Repair(which == 1 ? Npc::Mystic : Npc::Blacksmith); });
        }
        else if (*verb == "transmog")
        {
            Exactly(request, 1, 1);
            Plain([&] { game.Gate(Npc::Mystic); game.Transmog(); });
            wire.Record({"R", "transmog", "0"});
            wire.Record({"E", "transmog"});
        }
        else
            throw Bridge::Refusal("Unknown artisan action.");
    }

    // DCJEWELER: verb, then socket guid seq gemGuid | remove guid seq | combine id [count] | craft id [count].
    // The Jeweler no longer repairs: the verb is gone and so is `.dc jeweler repair`.
    // combine's count is 1 when left out, as craft's is; the whole count is checked before anything is
    // taken (Combine() in dc_jeweler.cpp). craft's id is a dc_jeweler_catalog recipe (Sovereign Amulet / Ring, the
    // Hellfire pair); the same full-batch checks run in Craft() (dc_crafting_shared.cpp).
    template<class Game, class Actor>
    void Jeweler(Game& game, Bridge::Request const& request, Bridge::Wire<Actor> const& wire)
    {
        auto verb = request.Token(0, 12);
        if (!verb)
            throw Bridge::Refusal("Choose an action.");
        char const* bad = "That request was not understood.";
        if (*verb == "socket")
        {
            Exactly(request, 4, 4);
            auto guid = RequiredUint(request, 1, 1, Max, bad);
            auto seq = RequiredUint(request, 2, 0, Max, bad);
            auto gem = RequiredUint(request, 3, 1, Max, "Choose an item, socket row and bag gem.");
            Execute(game, wire, "socket", SocketGate(true, game.SocketFilled(guid, seq)), guid, false,
                    [&] { game.Socket(guid, seq, gem); });
        }
        else if (*verb == "remove")
        {
            Exactly(request, 3, 3);
            auto guid = RequiredUint(request, 1, 1, Max, bad);
            auto seq = RequiredUint(request, 2, 0, Max, bad);
            Execute(game, wire, "remove", Npc::Jeweler, guid, false, [&] { game.Socket(guid, seq, 0); });
        }
        else if (*verb == "combine")
        {
            Exactly(request, 3, 2);
            auto id = RequiredUint(request, 1, 1, Max, bad);
            auto count = OptionalUint(request, 2, 1, Max, 1, bad);
            Execute(game, wire, "combine", Npc::Jeweler, 0, false, [&] { game.Combine(id, count); });
        }
        else if (*verb == "craft")
        {
            Exactly(request, 3, 2);
            auto id = RequiredUint(request, 1, 1, Max, bad);
            auto count = OptionalUint(request, 2, 1, Max, 1, bad);
            Execute(game, wire, "craft", Npc::Jeweler, 0, true, [&] { game.Jewelry(id, count); });
        }
        else
            throw Bridge::Refusal("Unknown Jeweler action.");
    }
} // namespace DC::Crafting::Window

#endif
