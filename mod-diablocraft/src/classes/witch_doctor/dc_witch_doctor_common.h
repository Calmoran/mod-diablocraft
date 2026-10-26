#pragma once
// What most Witch Doctor skill files share: the record of a spell when it belongs to a skill, the skill's own record,
// the class's tunables and the timed sheet numbers a skill gives the Witch Doctor.
#include "../../combat/dc_spell_shells.h"
#include "../../common/dc_common.h"
#include "../../common/dc_tunables.h"

#include <cstdint>
#include <string_view>

class Player;

namespace DC::Combat::WitchDoctor
{
    // The record of `spellId` when it is a skill or rune of the Witch Doctor's `skill`, else nullptr.
    inline Shells::Ability const* RowOf(std::uint32_t spellId, std::string_view skill)
    {
        auto const* row = Shells::FindAbility(spellId);
        return row && skill == row->skill ? row : nullptr;
    }

    // The skill's own record (no rune): the one that states the numbers its runes inherit.
    inline std::uint32_t BaseId(std::string_view skill)
    {
        for (auto const& row : Shells::Abilities)
            if (skill == row.skill && !*row.rune)
                return row.id;
        return 0;
    }

    inline double Tune(char const* name)
    {
        return DC::Tunables::Get("witchdoctor", name);
    }
} // namespace DC::Combat::WitchDoctor
