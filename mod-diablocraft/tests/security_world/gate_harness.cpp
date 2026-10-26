// Runs the module's own G10 tier gate and G8 salvage rule (both pure headers).
#include <cassert>
#include <iostream>
#include <string>
#include "dc_salvage_rule.h"
#include "dc_tier_gate.h"

using DC::Crafting::SalvageEligible;
using DC::Crafting::SalvageQuality;
using DC::Difficulty::PartyMemberReady;
using DC::Difficulty::TierChangeAllowed;

int main()
{
    std::string e;
    // G10: outside the hub is refused whatever the cooldown state, with the text
    // the Difficulty window's server Lua shows too (contract: tier-messages.md).
    assert(!TierChangeAllowed(false, false, 0, 1000, 0, e));
    assert(e == "Choose difficulty in the hub.");
    assert(!TierChangeAllowed(false, true, 0, 999999, 5000, e));
    // In the hub, first change and a change after the cooldown pass.
    assert(TierChangeAllowed(true, false, 0, 1000, 5000, e));
    assert(TierChangeAllowed(true, true, 1000, 6000, 5000, e));
    // Inside the cooldown is refused, one millisecond before it ends included.
    e.clear();
    assert(!TierChangeAllowed(true, true, 1000, 3000, 5000, e));
    assert(!e.empty() && e != "Choose difficulty in the hub.");
    assert(!TierChangeAllowed(true, true, 1000, 5999, 5000, e));
    // Blank tunable (0) means no cooldown.
    assert(TierChangeAllowed(true, true, 1000, 1000, 0, e));
    // diablocraft-01zoh: an online party member outside the Sanctum, or in combat, blocks the change.
    e.clear();
    assert(PartyMemberReady(true, false, e) && e.empty());
    assert(!PartyMemberReady(false, false, e));
    assert(e == "All online party members must be in the Sanctum to change difficulty.");
    assert(!PartyMemberReady(false, true, e));
    assert(e == "All online party members must be in the Sanctum to change difficulty.");
    e.clear();
    assert(!PartyMemberReady(true, true, e));
    assert(e == "All online party members must be out of combat.");
    // G8: equipped and traded items are not salvageable, on either path.
    assert(SalvageEligible(false, false));
    assert(!SalvageEligible(true, false));
    assert(!SalvageEligible(false, true));
    assert(!SalvageEligible(true, true));
    // Kanai's Cube bead 2: an Ancient or Primal item pays its own quality row; a crafted one, a normal one and an
    // unknown tier pay by rarity alone (a crafted Primal must never pay Ashes).
    assert(SalvageQuality(false, "ancient") == "ancient");
    assert(SalvageQuality(false, "primal") == "primal");
    assert(SalvageQuality(false, "normal") == "normal");
    assert(SalvageQuality(false, "") == "normal");
    assert(SalvageQuality(false, "mythic") == "normal");
    assert(SalvageQuality(true, "primal") == "normal");
    assert(SalvageQuality(true, "ancient") == "normal");
    std::cout << "ok\n";
}
