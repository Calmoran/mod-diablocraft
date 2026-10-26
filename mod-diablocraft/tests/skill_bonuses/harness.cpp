#include "../../src/items/dc_skill_bonuses.h"
#include <cassert>
#include <cstdint>
#include <iostream>

int main()
{
    // K5: skills are base spell ids now. These three are the catalogue's own
    // skill_ids, read out of the generated SQL rather than invented, so the
    // test reads like the data it stands in for.
    std::uint32_t const bash = 81002, frenzy = 81000, rend = 81008;
    DC::Items::SkillBonuses bonuses;
    assert(bonuses.Get(bash) == 0);
    bonuses.Set(1, bash, 9);
    bonuses.Set(1, bash, 9); // repeated equip/login notification
    assert(bonuses.Get(bash) == 9);
    bonuses.Set(2, bash, 15);
    bonuses.Set(3, frenzy, 12);
    assert(bonuses.Get(bash) == 24 && bonuses.Get(frenzy) == 12);
    assert(bonuses.Get(rend) == 0);
    bonuses.Set(1, frenzy, 9); // changed affix retains contribution identity
    assert(bonuses.Get(bash) == 15 && bonuses.Get(frenzy) == 21);
    bonuses.Remove(1);
    bonuses.Remove(1);
    bonuses.Remove(2);
    assert(bonuses.Get(bash) == 0 && bonuses.Get(frenzy) == 12);
    // An id that is not a skill contributes nothing rather than defaulting in.
    assert(bonuses.Get(0) == 0);
    std::cout << "Skill bonuses: stacking, skill isolation, replacement, duplicate equip and removal passed.\n";
}
