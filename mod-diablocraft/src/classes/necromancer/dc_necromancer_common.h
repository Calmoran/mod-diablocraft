#pragma once
// What most Necromancer files include: the Necromancer's own entry points, the class helpers, the engine's records, sheet
// numbers, strike paths and tunables, and the core types a skill touches. A file includes this and only what it alone
// needs.
#include "dc_necromancer.h"
#include "../dc_classes.h"
#include "../dc_resources.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_spell_numbers.h"
#include "../../combat/dc_spell_shells.h"
#include "../../common/dc_common.h"
#include "../../common/dc_tunables.h"
#include "Player.h"
#include "SpellAuras.h"
#include "Unit.h"

#include <cstdint>
#include <string_view>
#include <vector>

namespace DC::Combat::Necromancer
{
    // The record of `spellId` when it is a skill or rune of the Necromancer's `skill`, else nullptr.
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

    // The spell on the Necromancer's bar for `skill` (the skill or its slotted rune), 0 when it is not slotted.
    inline std::uint32_t Slotted(Player* player, std::string_view skill)
    {
        for (Classes::Slot const& slot : Classes::Bar(player))
            if (RowOf(slot.spellId, skill))
                return slot.spellId;
        return 0;
    }

    // A stun of `seconds` on `target` (stock "Ice Blast", one MOD_STUN effect): control immunity answers nothing.
    void Stun(Player* player, Unit* target, double seconds);
    // A slow of `pct` percent on `target` for `seconds` (stock "Dazed", one MOD_DECREASE_SPEED effect). Nothing for no
    // percent.
    void Slow(Player* player, Unit* target, double pct, double seconds);
    // Takes the Necromancer's slow off `target` before its time.
    void Unslow(Player* player, Unit* target);
    // The enemy Feared for `seconds` (stock "Fear", one MOD_FEAR effect): it runs from the Necromancer.
    void Fear(Player* player, Unit* target, double seconds);
    // The enemy's attack speed cut by `pct` percent for `seconds` (stock "Slow", one MOD_MELEE_HASTE effect). Nothing for
    // no percent.
    void Weary(Player* player, Unit* target, double pct, double seconds);
    // "at the cost of {pct}% Health": `pct` percent of the Necromancer's maximum Life taken, never leaving less than 1.
    void SpendLife(Player* player, double pct);
    // `amount` of Life healed to the Necromancer by the spell `spellId` (Physical), through the core's own heal.
    void Heal(Player* player, std::uint32_t spellId, double amount);
    // `points` of Essence a skill generates, times the Necromancer's resource generation item factor for that skill;
    // nothing for another class.
    void PayEssence(Player* player, std::uint32_t spellId, double points);

    // The timed sheet numbers (dc_necromancer_buffs.cpp). `id` names the buff (the spell that gives it), so a second cast
    // of it stacks or restarts the same one.
    namespace Buffs
    {
        // `stat` rises by `perStack` for each stack, up to `maxStacks`, for `seconds` from now; `adds` stacks at once.
        void Stack(Player* player, std::uint32_t id, Stat stat, Bucket bucket, double perStack, unsigned maxStacks,
                   double seconds, unsigned adds = 1);
        // The number `id` keeps on `stat` set to `value` (0 takes it off), for a number that follows something that changes
        // (the enemies cursed), not a time.
        void Set(Player* player, std::uint32_t id, Stat stat, Bucket bucket, double value);
    } // namespace Buffs
} // namespace DC::Combat::Necromancer
