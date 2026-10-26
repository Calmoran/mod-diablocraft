// Compiles dc_charm.h (the production header) and drives it: what counts as a charmed monster, what stays "player-owned",
// and what a Greater Rift Guardian's arrival clears (N-CHARM, diablocraft-spr13).
#include "dc_charm.h"

#include <cassert>
#include <cstdio>

using namespace DC::Rifts::Charm;

static Body make(bool controlled, bool charmed)
{
    Body b;
    b.controlledByPlayer = controlled;
    b.charmed = charmed;
    return b;
}

int main()
{
    // A monster under a player's charm: the core flags it player-controlled for the charm's length.
    Body monster = make(true, true);
    assert(IsCharmedMonster(monster));
    assert(!PlayerOwned(monster));                       // the sweeps that skip a player's creatures do not skip it
    assert(ClearedByGuardian(false, monster));           // not hostile in faction while charmed, still cleared

    // An uncharmed monster is neither, and is cleared only by being hostile.
    Body plain = make(false, false);
    assert(!IsCharmedMonster(plain) && !PlayerOwned(plain));
    assert(ClearedByGuardian(true, plain) && !ClearedByGuardian(false, plain));

    // A player's pet, guardian, totem, critter or trigger is never a charmed monster, charmed or not.
    for (int kind = 0; kind < 5; ++kind)
    {
        Body b = make(true, true);
        (kind == 0 ? b.pet : kind == 1 ? b.guardian : kind == 2 ? b.totem : kind == 3 ? b.critter : b.trigger) = true;
        assert(!IsCharmedMonster(b));
        assert(PlayerOwned(b));                          // still the player's, still left alone
        assert(!ClearedByGuardian(false, b));            // and kept by the Guardian's sweep
    }

    // A pet the player owns without a charm (the common case).
    Body pet = make(true, false);
    pet.pet = true;
    assert(!IsCharmedMonster(pet) && PlayerOwned(pet) && !ClearedByGuardian(false, pet));

    std::puts("charm harness: ok");
    return 0;
}
