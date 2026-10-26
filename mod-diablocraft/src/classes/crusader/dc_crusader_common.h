#pragma once
// What most Crusader files include: the Crusader's own entry points, the class helpers, the engine's records, sheet
// numbers, strike paths and tunables, and the core types a skill touches. A file includes this and only what it alone
// needs.
#include "dc_crusader.h"
#include "../dc_classes.h"
#include "../dc_resources.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_spell_numbers.h"
#include "../../combat/dc_spell_shells.h"
#include "../../common/dc_common.h"
#include "../../common/dc_tunables.h"
#include "GameTime.h"
#include "Player.h"
#include "SpellAuras.h"
#include "Unit.h"

#include <cstdint>
#include <mutex>
#include <string_view>
#include <unordered_map>
#include <vector>

namespace DC::Combat::Crusader
{
    // The record of `spellId` when it is a skill or rune of the Crusader's `skill`, else nullptr.
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

    // The spell on the Crusader's bar for `skill` (the skill or its slotted rune), 0 when it is not slotted.
    inline std::uint32_t Slotted(Player* player, std::string_view skill)
    {
        for (Classes::Slot const& slot : Classes::Bar(player))
            if (RowOf(slot.spellId, skill))
                return slot.spellId;
        return 0;
    }

    // A stun of `seconds` on `target` (stock "Ice Blast", one MOD_STUN effect): control immunity answers nothing.
    void Stun(Player* player, Unit* target, double seconds);
    // An Immobilize of `seconds` on `target` (stock "Earthgrab", one MOD_ROOT effect).
    void Root(Player* player, Unit* target, double seconds);
    // The enemy blinded for `seconds` (stock "Dizzy", one MOD_CONFUSE effect): it wanders and does not attack.
    void Blind(Player* player, Unit* target, double seconds);
    // The blind `Blind` put on `target` taken off again (a charmed enemy fights; it does not wander).
    void Unblind(Player* player, Unit* target);
    // The enemy Feared for `seconds` (stock "Fear", one MOD_FEAR effect): it runs from the Crusader. True when the fear took hold.
    bool Fear(Player* player, Unit* target, double seconds);
    // The enemy taunted for `seconds` (stock "Challenging Shout", one MOD_TAUNT effect): it attacks the Crusader. True when the taunt took hold:
    // an enemy that cannot be taunted answers false.
    bool Taunt(Player* player, Unit* target, double seconds);
    // The enemy's attack speed cut by `pct` percent for `seconds` (stock "Slow", one MOD_MELEE_HASTE effect). Nothing for no percent.
    void Weary(Player* player, Unit* target, double pct, double seconds);
    // `amount` of Life healed to `target` by `caster`, as the spell `spellId` (Holy), through the core's own heal.
    void Heal(Player* caster, Unit* target, std::uint32_t spellId, double amount);
    // `points` of Wrath a skill generates, times the Crusader's resource generation item factor for that skill; nothing for another class.
    void PayWrath(Player* player, std::uint32_t spellId, double points);
    // `points` of Wrath to the Crusader, through the core's own energize, for an effect that gives some; nothing for another class.
    void GainWrath(Player* player, std::uint32_t spellId, double points);
    // A slow of `pct` percent on `target` for `seconds` (stock "Dazed", one MOD_DECREASE_SPEED effect). Nothing for no percent.
    void Slow(Player* player, Unit* target, double pct, double seconds);

    inline std::uint64_t Now()
    {
        return std::uint64_t(GameTime::GetGameTimeMS().count());
    }

    // The timed sheet numbers (dc_crusader_buffs.cpp). `id` names the buff (the spell that gives it), so a second cast
    // of it stacks or restarts the same one.
    namespace Buffs
    {
        // `stat` rises by `perStack` for each stack, up to `maxStacks`, for `seconds` from now; `adds` stacks at once.
        void Stack(Player* player, std::uint32_t id, Stat stat, Bucket bucket, double perStack, unsigned maxStacks,
                   double seconds, unsigned adds = 1);
        // The stacks `id` holds on `stat` now; 0 once it ran out.
        unsigned Stacks(Player* player, std::uint32_t id, Stat stat);
    } // namespace Buffs
} // namespace DC::Combat::Crusader
