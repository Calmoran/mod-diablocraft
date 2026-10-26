#ifndef DC_SLOT_VENDOR_RULE_H
#define DC_SLOT_VENDOR_RULE_H

#include "dc_roll_class.h"

#include <string>

// The legendary slot vendors' purchase (docs/proposals/kadala.md 6.5): the decisions of the buy hook,
// free of the core so scripts/tests/items/test_slot_vendors.py compiles this header and drives it with the sheets' values. The hook
// (dc_slot_vendor.cpp) gathers the facts, asks here, and does what the answer says.
namespace DC::SlotVendor
{
    // 6.5 step 3: the class the named item rolls for. A class-only item's own class, else its class set's class (the
    // drops' rule, DropClass), otherwise the buyer's: a Wizard who buys an Immortal King's piece gets it rolled for a
    // Barbarian. Empty only when the buyer's class is not a playable one and the item names none.
    inline std::string RollClassFor(std::string const& designated, std::string const& setClass,
                                    std::string const& buyerClass)
    {
        std::string const own = DC::RollClass::DropClass(designated, setClass);
        return own.empty() ? buyerClass : own;
    }

    // What the hook found: the stock path's own checks (Player.cpp:10946 onward) that a purchase of ours still needs,
    // the entry's stock level condition, the roll class and whether a bag cell exists.
    struct Facts
    {
        bool alive = false, inReach = false, onList = false, conditionMet = false, rollClassKnown = false,
             bagFree = false;
        unsigned count = 0;
    };

    enum class Verdict
    {
        Buy,
        Dead,
        BadCount,
        TooFar,
        NotListed,
        ConditionNotMet,
        NothingToRoll,
        BagsFull
    };

    // The stock path's order, then ours. The first refusal wins, and every refusal comes before anything is staged.
    inline Verdict Judge(Facts const& f)
    {
        if (!f.alive)
            return Verdict::Dead;
        if (f.count != 1)
            return Verdict::BadCount;
        if (!f.inReach)
            return Verdict::TooFar;
        if (!f.onList)
            return Verdict::NotListed;
        if (!f.conditionMet)
            return Verdict::ConditionNotMet;
        if (!f.rollClassKnown)
            return Verdict::NothingToRoll;
        if (!f.bagFree)
            return Verdict::BagsFull;
        return Verdict::Buy;
    }
} // namespace DC::SlotVendor

#endif
