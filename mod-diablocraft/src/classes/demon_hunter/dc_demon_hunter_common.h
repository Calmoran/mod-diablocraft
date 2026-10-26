#pragma once
// What most Demon Hunter skill files share: the record of a spell when it belongs to a skill, the skill's own record, the
// class's tunables and a flag held while a skill's own strikes land.
#include "../../combat/dc_spell_shells.h"
#include "../../common/dc_common.h"
#include "../../common/dc_tunables.h"

#include <cstdint>
#include <string_view>

class Player;

namespace DC::Combat::DemonHunter
{
    // The record of `spellId` when it is a skill or rune of the Demon Hunter's `skill`, else nullptr.
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
        return DC::Tunables::Get("demonhunter", name);
    }

    // Holds a flag set for as long as it lives: a skill's own strikes land through the engine's hooks too, and must not
    // start the skill again.
    struct Scope
    {
        explicit Scope(bool& flag) : flag_(flag)
        {
            flag_ = true;
        }
        ~Scope()
        {
            flag_ = false;
        }
        Scope(Scope const&) = delete;
        Scope& operator=(Scope const&) = delete;
        bool& flag_;
    };

    // The timed sheet numbers (dc_demon_hunter_buffs.cpp). `id` names the buff (the spell that gives it), so a second
    // cast of it stacks or restarts the same one.
    namespace Buffs
    {
        // `stat` rises by `perStack` for each stack, up to `maxStacks`, for `seconds` from now.
        void Stack(Player* player, std::uint32_t id, Stat stat, Bucket bucket, double perStack, unsigned maxStacks,
                   double seconds);
    } // namespace Buffs
} // namespace DC::Combat::DemonHunter
