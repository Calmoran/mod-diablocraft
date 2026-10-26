/*
 * World of DiabloCraft - classes (04-classes §2-§4).
 *
 * Warrior cleanup, level-derived unlocks, and the 6 + 4 skill bar.
 * Public surface of the classes folder.
 */

#ifndef DC_CLASSES_H
#define DC_CLASSES_H

#include <cstdint>
#include <string>
#include <vector>

class Player;

namespace DC::Classes
{
    // C4 and K2: the bar's shape is D3's, not ours. Both numbers are published
    // and reach dc_tunables as combat/active_skill_slots and
    // combat/passive_skill_slots through data/d3/character_rules.csv and the
    // data/tunables/_from_d3.csv manifest, so they are read at runtime rather than
    // compiled in. Slot indices themselves are unaffected: slot n stays slot n.
    unsigned ActiveSlots();
    unsigned PassiveSlots();

    // The potion's cooldown (one for every potion shell) shortened by `ms`; nothing when no potion is on cooldown.
    void ReducePotionCooldown(Player* player, std::uint32_t ms);

    struct Slot
    {
        unsigned slot = 0;
        // K3: skillId and spellId are what is saved and what everything matches
        // on. The names are the catalogue's label for that id, carried for display.
        std::string skill, rune;
        std::uint32_t skillId = 0, spellId = 0;
    };

    // K1/K2: unlock state is derived from level, never stored (04 §4).
    // The one class gate: true when this player's class has a generated catalogue.
    // dc_class_map lists only classes whose spells exist, so this replaces every
    // hardcoded CLASS_WARRIOR test rather than moving it somewhere else.
    bool Playable(Player const* player);
    // class_map.csv's primary_stat for this player's class ("Strength",
    // "Intelligence"), or "" when the class has no catalogue. The main stat a hit
    // scales with is read from here, not named in code.
    std::string PrimaryStatOf(Player const* player);
    // class_map.csv's class_id for this player's class, 0 when the class has no
    // catalogue. Generated tables keyed by class (the gear modifiers, the
    // regeneration aura) are looked up with it.
    std::uint32_t ClassIdOf(Player const* player);

    bool SkillUnlocked(Player const* player, std::string const& skill);
    bool RuneUnlocked(Player const* player, std::string const& skill, std::string const& rune);
    bool PassiveUnlocked(Player const* player, std::string const& passive);
    // K2 per slot: true only when that slot has an unlock-level row and the
    // character has reached it. A slot with no row is locked whatever its
    // neighbours do, so this - not the count below - is what decides a write.
    bool PassiveSlotUnlocked(Player const* player, unsigned slot);
    // How many slots are unlocked, for display only.
    unsigned PassiveSlotsOpen(Player const* player);

    // The character's current bar, in slot order.
    // K5: the base skill an id belongs to, so an affix that boosts a skill
    // boosts every rune of it. 0 when the id is not a catalogue entry.
    std::uint32_t SkillIdOf(std::uint32_t spellId);
    // The catalogue's category for a skill or rune id ("Primary" for a D3
    // Signature spell or a Barbarian primary), "" when the id is not a catalogue
    // entry (Prodigy reads it).
    std::string CategoryOf(std::uint32_t spellId);

    std::vector<Slot> Bar(Player* player);

    // Rewrites the six skills, active potion and Town Portal, then pushes the bar.
    void WriteActionBar(Player* player);
    // The same with a bar other than the saved one: Archon form puts its own
    // abilities on the six skill buttons and WriteActionBar(player) puts the
    // saved bar back.
    void WriteActionBar(Player* player, std::vector<Slot> const& bar);

    // Puts skill+rune in a slot and rewrites the WoW action bar. Refused in combat
    // or inside an instance (04 §3), if the skill or rune is not unlocked, or if a
    // skill it would take off the bar or give another rune is on cooldown
    // (it waits for the cooldown). A skill already on the bar moves here and frees its old
    // slot (K6). `error` says which.
    bool SetSlot(Player* player, unsigned slot, std::string const& skill, std::string const& rune, std::string& error);
    // One server step for a swap of two wells (a drag from one well to another): what sits in `from` goes to `to` and the other way
    // round, or moves when one of them is empty, in a single transaction, so a refusal can never leave a skill off the bar. Slots
    // are 0-based as SetSlot's. The combat and instance rules are SetSlot's; nothing a skill casts changes, so the cooldown rule has
    // nothing to refuse.
    bool SwapSlots(Player* player, unsigned from, unsigned to, std::string& error);

    // First free slot, or ActiveSlots() when the bar is full.
    unsigned FirstFreeSlot(Player* player);

    // World character start: replace the empty/new bar deterministically, clean the
    // Warrior book and grant the hidden shells after the level has been set.
    bool InitializeStarterBar(Player* player, std::string& error);

    // K2. Writes a passive into a slot. Refused in combat or an instance, if the
    // slot is not open at this level, if the passive is not unlocked, or if it is
    // already on the bar. `error` says which.
    bool SetPassive(Player* player, unsigned slot, std::string const& passive, std::string& error);

    // The passives currently slotted, in slot order.
    std::vector<std::string> Passives(Player* player);

    void RegisterScripts();
} // namespace DC::Classes

#endif // DC_CLASSES_H
