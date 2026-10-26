#pragma once
// The Monk's timed effects. A rune that says "increases the damage of all your attacks by 15% for
// 10 seconds", "enemies take 10% additional damage for 10 seconds" or "enemies deal 20% less damage" is a number with
// an end time, kept by the module like Static Charge's mark (no aura record, no icon: that is the class_buffs.csv
// work). This file is the part that needs no core type, so tests/monk_effects compiles this exact code.
#include <algorithm>
#include <cstdint>
#include <unordered_map>
#include <vector>

namespace DC::Combat::Monk
{
    // The numbers one holder (a Monk, or an enemy) wears, one entry per key (the rune's spell id). Casting a key again
    // refreshes its end time; with maxStacks above 1 each cast adds a stack (up to the cap) and refreshes the whole
    // entry, d3planner's buff rule (buffs.js addBuff: refresh true, maxstacks).
    class Book
    {
    public:
        void Apply(std::uint32_t key, double pctPerStack, std::uint64_t now, std::uint64_t ms, unsigned maxStacks = 1)
        {
            Drop(now);
            Entry* entry = Find(key);
            if (!entry)
            {
                entries_.push_back({key, pctPerStack, 0, 0});
                entry = &entries_.back();
            }
            entry->pctPerStack = pctPerStack;
            entry->stacks = std::min(entry->stacks + 1, std::max(1u, maxStacks));
            entry->until = now + ms;
        }

        // Sum of pct * stacks over the live entries.
        double Total(std::uint64_t now)
        {
            Drop(now);
            double total = 0;
            for (Entry const& entry : entries_)
                total += entry.pctPerStack * entry.stacks;
            return total;
        }

        // Product of (1 - pct * stacks / 100) over the live entries, never below 0: each "deals x% less" is its own
        // cut.
        double LessFactor(std::uint64_t now)
        {
            Drop(now);
            double factor = 1.0;
            for (Entry const& entry : entries_)
                factor *= std::max(0.0, 1.0 - entry.pctPerStack * entry.stacks / 100.0);
            return factor;
        }

        unsigned Stacks(std::uint32_t key, std::uint64_t now)
        {
            Drop(now);
            Entry const* entry = Find(key);
            return entry ? entry->stacks : 0;
        }

        void Remove(std::uint32_t key)
        {
            entries_.erase(
                std::remove_if(entries_.begin(), entries_.end(), [key](Entry const& e) { return e.key == key; }),
                entries_.end());
        }

        bool Empty() const
        {
            return entries_.empty();
        }

    private:
        struct Entry
        {
            std::uint32_t key;
            double pctPerStack;
            unsigned stacks;
            std::uint64_t until;
        };

        Entry* Find(std::uint32_t key)
        {
            for (Entry& entry : entries_)
                if (entry.key == key)
                    return &entry;
            return nullptr;
        }

        void Drop(std::uint64_t now)
        {
            entries_.erase(
                std::remove_if(entries_.begin(), entries_.end(), [now](Entry const& e) { return e.until <= now; }),
                entries_.end());
        }

        std::vector<Entry> entries_;
    };

    // Books by holder (a guid). An enemy that dies or despawns leaves its book behind; Sweep drops the books that ran
    // out, and Of calls it when the table has grown past `limit`.
    class Ledger
    {
    public:
        explicit Ledger(std::size_t limit = 512)
            : limit_(limit)
        {
        }

        Book& Of(std::uint64_t holder, std::uint64_t now)
        {
            if (books_.size() >= limit_ && !books_.count(holder))
                Sweep(now);
            return books_[holder];
        }

        // The holder's book if it has one; never creates one (a read must not grow the table).
        Book* Peek(std::uint64_t holder)
        {
            auto found = books_.find(holder);
            return found == books_.end() ? nullptr : &found->second;
        }

        void Sweep(std::uint64_t now)
        {
            for (auto it = books_.begin(); it != books_.end();)
            {
                it->second.Total(now);
                it = it->second.Empty() ? books_.erase(it) : std::next(it);
            }
        }

        std::size_t Size() const
        {
            return books_.size();
        }

    private:
        std::size_t limit_;
        std::unordered_map<std::uint64_t, Book> books_;
    };
} // namespace DC::Combat::Monk
