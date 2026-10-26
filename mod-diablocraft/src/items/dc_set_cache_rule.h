#ifndef DC_SET_CACHE_RULE_H
#define DC_SET_CACHE_RULE_H

#include <string>

// The set caches' open (docs/proposals/kadala.md 6.6 and 6.7.4): the decisions of the open hook, free
// of the core so scripts/tests/items/test_set_caches.py compiles this header and drives it with the sheets' values. The hook
// (dc_set_cache.cpp) gathers the facts, asks here, and does what the answer says.
namespace DC::SetCache
{
    // The cache's own slot is freed first, so the pieces need one free bag slot fewer than the set has.
    inline unsigned SlotsNeeded(unsigned pieces)
    {
        return pieces > 0 ? pieces - 1 : 0;
    }

    struct Facts
    {
        bool alive = false, inCombat = false, inTrade = false, rollClassesKnown = false;
        unsigned pieces = 0, freeSlots = 0;
    };

    enum class Verdict
    {
        Open,
        Dead,
        InCombat,
        InTrade,
        NothingToRoll,
        BagsShort
    };

    // The same three refusals as the identify rule (G7, dc_identify_rule.h, in its order), then ours. The first refusal
    // wins, and every refusal comes before anything is destroyed or staged.
    inline Verdict Judge(Facts const& f)
    {
        if (!f.alive)
            return Verdict::Dead;
        if (f.inCombat)
            return Verdict::InCombat;
        if (f.inTrade)
            return Verdict::InTrade;
        if (f.pieces == 0 || !f.rollClassesKnown)
            return Verdict::NothingToRoll;
        if (f.freeSlots < SlotsNeeded(f.pieces))
            return Verdict::BagsShort;
        return Verdict::Open;
    }

    // The chat line of a refusal, "" for an open.
    inline std::string Refusal(Verdict verdict, std::string const& setName, unsigned pieces, unsigned freeSlots)
    {
        switch (verdict)
        {
            case Verdict::Dead:
                return "You cannot open a cache while dead.";
            case Verdict::InCombat:
                return "You cannot open a cache in combat.";
            case Verdict::InTrade:
                return "That cache is in a trade.";
            case Verdict::NothingToRoll:
                return setName + " has nothing to open into. Report it.";
            case Verdict::BagsShort:
            {
                unsigned const needed = SlotsNeeded(pieces);
                return setName + " needs " + std::to_string(needed) + " free bag slot" + (needed == 1 ? "" : "s") +
                       "; you have " + std::to_string(freeSlots) + ".";
            }
            case Verdict::Open:
                break;
        }
        return "";
    }
} // namespace DC::SetCache

#endif
