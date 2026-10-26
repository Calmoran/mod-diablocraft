#pragma once
// The Monk's Mantras, what dc_monk.cpp calls. One mechanism runs the four (dc_monk_mantras.cpp); the "only one Mantra"
// state is dc_monk_mantras.h's. For each Mantra: Is, whether `spellId` is the Mantra or one of its runes; Cast, the
// press (it becomes the Mantra in force, the activation runs, the pulse starts); Touch, the pulse starts when the
// Mantra is slotted and none runs.
#include <cstdint>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Monk
{
    namespace Mantras
    {
        // The always-on hook: a PlayerScript that, at login and then once a second, starts the pulse of each Mantra a
        // Monk has on its skill bar, so a passive needs no press and a Mantra slotted later starts without one.
        void RegisterScripts();
    } // namespace Mantras

    namespace Salvation
    {
        bool Is(std::uint32_t spellId);
        // `targets` are the Monk and the allies within its radius: they gain the active's resistance for its seconds.
        void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
        void Touch(Player* player);
        // The dodge chance in percent the aura gives `unit` (Monk::Dodge, called on every incoming hit); also where
        // Divine Protection sees the holder's Life.
        double Dodge(Unit const* unit);
    } // namespace Salvation

    namespace Healing
    {
        bool Is(std::uint32_t spellId);
        // Each ally the cast resolved wears the absorb.
        void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
        void Touch(Player* player);
        // One hit of the Monk's landed: Boon of Inspiration heals the Monk and the group.
        void Landed(Player* player, std::uint32_t spellId);
    } // namespace Healing

    namespace Retribution
    {
        bool Is(std::uint32_t spellId);
        void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
        // Transgression's attack speed is the pulse: Touch keeps it up while the rune is slotted.
        void Touch(Player* player);
        // A hit taken by `victim` (Monk::Taken from the combat engine): the passive of every Monk in the victim's group
        // (the victim itself included) within the Mantra's radius reflects the hit.
        void Taken(Unit* victim, Unit* attacker);
    } // namespace Retribution

    namespace Conviction
    {
        bool Is(std::uint32_t spellId);
        void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
        void Touch(Player* player);
        // A Monk hit landed (Monk::Landed): keeps the aura's pulse running while the Mantra is slotted, and
        // Annihilation's kill.
        void Landed(Player* player, Unit* target, std::uint32_t spellId);
    } // namespace Conviction
} // namespace DC::Combat::Monk
