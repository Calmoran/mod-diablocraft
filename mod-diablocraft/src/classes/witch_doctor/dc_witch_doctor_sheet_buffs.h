#pragma once
// The Witch Doctor's timed numbers on the character sheet (dc_witch_doctor_sheet_buffs.cpp): put on when a skill or
// rune gives them, taken off when their time runs out. The rules they follow are dc_witch_doctor_buffs.h.
#include "../../common/dc_common.h"

#include <cstdint>

class Player;

namespace DC::Combat::WitchDoctor::SheetBuffs
{
    // `stat` rises by `perStack` for each stack, up to `maxStacks`, for `seconds` from now; `adds` stacks at once. `id`
    // names the buff (the spell that gives it), so a second cast of it stacks and restarts the same one. The stacks
    // held afterwards.
    unsigned Stack(Player* player, std::uint32_t id, Stat stat, Bucket bucket, double perStack, unsigned maxStacks,
                   double seconds, unsigned adds = 1);
    // What `id` puts on `stat` now, 0 once it ran out or when it was never given.
    double Current(Player* player, std::uint32_t id, Stat stat);
} // namespace DC::Combat::WitchDoctor::SheetBuffs
