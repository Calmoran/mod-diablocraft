#pragma once
// What most Shaman files include: the class's own entry points, the class helpers, the engine's records, sheet numbers
// and tunables, and the core types a mechanic touches.
#include "dc_shaman.h"
#include "../dc_classes.h"
#include "../dc_resources.h"
#include "../../combat/dc_buff_values.h"
#include "../../combat/dc_spell_numbers.h"
#include "../../combat/dc_spell_shells.h"
#include "../../common/dc_common.h"
#include "../../common/dc_tunables.h"
#include "GameTime.h"
#include "Player.h"

#include <cstdint>
#include <string>
#include <string_view>

namespace DC::Combat::Shaman
{
    // Whether `player` is a Shaman: the class whose primary resource is Maelstrom.
    inline bool IsShaman(Player const* player)
    {
        return player && Classes::ClassIdOf(player) == Resources::Maelstrom.classId;
    }

    inline std::uint64_t Now()
    {
        return std::uint64_t(GameTime::GetGameTimeMS().count());
    }

    // The aura the buff bar shows for a buff of data/class_buffs.csv, 0 when the world has no such record.
    inline std::uint32_t BuffId(char const* identity)
    {
        return Shells::HelperFor(identity);
    }

    // A passive's record id by name, 0 when the catalogue has none.
    inline std::uint32_t PassiveId(std::string_view name)
    {
        for (auto const& row : Shells::Passives)
            if (name == row.name)
                return row.id;
        return 0;
    }

    // The skill's own record (no rune): the one that states the numbers its runes inherit.
    inline std::uint32_t BaseId(std::string_view skill)
    {
        for (auto const& row : Shells::Abilities)
            if (skill == row.skill && !*row.rune)
                return row.id;
        return 0;
    }

    inline double Tunable(char const* name)
    {
        return Tunables::Get("combat", name);
    }

    namespace Overcharge
    {
        // Maelstrom that did not fit is banked (dc_shaman_overcharge.cpp).
        void Overflow(Player* player, double overflow);
        // A cast of `spellId` began: a Secondary spends every stack.
        void Cast(Player* player, std::uint32_t spellId);
        // The damage bonus the carried stacks give a hit of `spellId`.
        void Multipliers(Player* player, std::uint32_t spellId, DC::Combat::Factors& out);
        // The buff bar and the timers; called from the class's upkeep.
        void Upkeep(Player* player);
        unsigned Stacks(Player* player);
        void Forget(Player* player);
    } // namespace Overcharge

    namespace Attunement
    {
        void Cast(Player* player, std::uint32_t spellId);
        void Multipliers(Player* player, DC::Combat::Factors& out);
        // The Attunement's element as the engine names an element ("fire", "cold", "physical", "lightning"); empty for a
        // player who is not a Shaman.
        char const* Current(Player* player);
        // The Attunement becomes `element` (named as Current names it); nothing for another name or a player who is not a Shaman.
        void MoveTo(Player* player, std::string_view element);
        void Upkeep(Player* player);
        void Forget(Player* player);
    } // namespace Attunement
} // namespace DC::Combat::Shaman
