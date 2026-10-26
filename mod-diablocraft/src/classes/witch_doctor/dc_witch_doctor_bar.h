#pragma once
// Which skill or rune of a Witch Doctor skill sits on the bar: what the pets' skills read when a pet is raised (the pet
// belongs to the rune that was slotted when it came).
#include "../dc_classes.h"
#include "../../combat/dc_spell_shells.h"

#include <cstdint>
#include <string>
#include <string_view>

class Player;

namespace DC::Combat::WitchDoctor
{
    struct Slotted
    {
        std::uint32_t id = 0; // the record of the skill or rune on the bar; 0 when the skill is not on it
        std::string rune;     // the rune's name; empty for the skill's own record
    };

    inline Slotted OnBar(Player* owner, std::string_view skill)
    {
        for (Classes::Slot const& slot : Classes::Bar(owner))
            if (auto const* row = Shells::FindAbility(slot.spellId); row && skill == row->skill)
                return {slot.spellId, row->rune};
        return {};
    }
} // namespace DC::Combat::WitchDoctor
