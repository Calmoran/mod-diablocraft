#pragma once
// Elemental Weapon's rules that need no core type, header-only so tests/shaman_elemental_weapon compiles this exact
// code: which rune is which imbue, which skills an imbue boosts, what rides on a hit, how many hits a strike-again
// needs, how much more Maelstrom a skill generates and what an imbue puts on the character sheet. The production half
// is dc_shaman_elemental_weapon.cpp, called from dc_shaman.cpp.
#include "dc_shaman_attunement.h"
#include "../../combat/dc_damage_buckets.h"

#include <cstdint>
#include <optional>
#include <string_view>

class Player;
class Unit;

namespace DC::Combat::Shaman::ElementalWeapon
{
    enum class Rune
    {
        Off,            // no Elemental Weapon on the bar: no imbue
        Base,           // the skill itself: every skill a little stronger
        Flametongue,    // Fire skills; Fire hits burn
        Frostbrand,     // Cold skills; Cold hits chill, and freeze once while activated
        Windfury,       // Lightning skills; every few Lightning hits strike again
        Rockbiter,      // Physical skills; more Armor
        MaelstromWeapon // every few Primary casts make the next Secondary free; activated, Primaries generate more
    };

    // The imbue a record gives: the skill itself is the base imbue, a rune names its own, a stranger is none.
    inline Rune RuneOf(std::string_view name)
    {
        if (name.empty())
            return Rune::Base;
        if (name == "Flametongue")
            return Rune::Flametongue;
        if (name == "Frostbrand")
            return Rune::Frostbrand;
        if (name == "Windfury")
            return Rune::Windfury;
        if (name == "Rockbiter")
            return Rune::Rockbiter;
        if (name == "Maelstrom Weapon")
            return Rune::MaelstromWeapon;
        return Rune::Off;
    }

    // The element a hit deals: the one the class names for it through the element seam (Elemental Blast and Primal Shock deal the
    // Shaman's Attunement whatever their record's school is), else the record's own school. `seam` names an element as the engine
    // does ("fire", "cold", "lightning", "physical"), or is empty.
    inline Attunement::Element DealtElement(char const* seam, Attunement::Element record)
    {
        std::string_view const name = seam ? std::string_view(seam) : std::string_view();
        if (name == "fire")
            return Attunement::Element::Fire;
        if (name == "cold")
            return Attunement::Element::Cold;
        if (name == "lightning")
            return Attunement::Element::Lightning;
        if (name == "physical")
            return Attunement::Element::Physical;
        return record;
    }

    // Whether the imbue boosts the damage of a skill of `element`: the base imbue every skill, a rune its own element.
    inline bool Boosts(Rune rune, Attunement::Element element)
    {
        switch (rune)
        {
            case Rune::Base:
                return true;
            case Rune::Flametongue:
                return element == Attunement::Element::Fire;
            case Rune::Frostbrand:
                return element == Attunement::Element::Cold;
            case Rune::Windfury:
                return element == Attunement::Element::Lightning;
            case Rune::Rockbiter:
                return element == Attunement::Element::Physical;
            default:
                return false;
        }
    }

    // The damage bonuses a hit of `element` gets: the passive's while the imbue stands and the activation's on top of
    // it while it is activated ("an additional N% more damage", a factor of its own). `passive` and `activated` are the
    // rune's numbers, 0 where it states none.
    struct Bonus
    {
        double passivePct = 0;
        double activePct = 0;
    };
    inline Bonus DamageBonus(Rune rune, Attunement::Element element, bool active, double passive, double activated)
    {
        Bonus bonus;
        if (Boosts(rune, element))
        {
            bonus.passivePct = passive;
            bonus.activePct = active ? activated : 0.0;
        }
        return bonus;
    }

    // What a landed hit of `element` sets going besides its damage.
    struct Effect
    {
        bool burn = false;   // Flametongue: a Fire hit burns the enemy
        bool chill = false;  // Frostbrand: a Cold hit chills it
        bool freeze = false; // Frostbrand activated: and freezes it (once per enemy per activation)
        bool echo = false;   // Windfury: a Lightning hit counts toward the strike again
    };
    inline Effect EffectOf(Rune rune, Attunement::Element element, bool active)
    {
        Effect effect;
        effect.burn = rune == Rune::Flametongue && element == Attunement::Element::Fire;
        effect.chill = rune == Rune::Frostbrand && element == Attunement::Element::Cold;
        effect.freeze = effect.chill && active;
        effect.echo = rune == Rune::Windfury && element == Attunement::Element::Lightning;
        return effect;
    }

    // "Every Nth hit/cast": counts one more and says whether this one is the Nth, starting the count over when it is.
    // No number, never.
    inline bool Reached(unsigned& count, unsigned every)
    {
        if (!every)
            return false;
        if (++count >= every)
        {
            count = 0;
            return true;
        }
        return false;
    }

    // The percent more Maelstrom a generating skill pays: the base imbue's on every one; Maelstrom Weapon's, activated, on
    // a Primary only. `pct` is the imbue record's `regen_pct`.
    inline double GenerationPct(Rune rune, bool active, bool primary, double pct)
    {
        if (rune == Rune::Base)
            return pct;
        return rune == Rune::MaelstromWeapon && active && primary ? pct : 0.0;
    }

    // What an imbue puts on the character sheet: Rockbiter's Armor (the passive's, and the activation's on top) and the
    // attack speed Windfury's activation gives.
    struct Sheet
    {
        double armorPct = 0;
        double attackSpeedPct = 0;
    };
    inline Sheet SheetOf(Rune rune, bool active, double passiveArmor, double activeArmor, double activeSpeed)
    {
        Sheet sheet;
        if (rune == Rune::Rockbiter)
            sheet.armorPct = passiveArmor + (active ? activeArmor : 0.0);
        if (rune == Rune::Windfury && active)
            sheet.attackSpeedPct = activeSpeed;
        return sheet;
    }

    // The production half (dc_shaman_elemental_weapon.cpp).
    bool Is(std::uint32_t spellId);
    // The cast hits nothing; the imbue's effects come from the hits and casts around it.
    std::optional<double> BasePct(std::uint32_t spellId);
    // A cast of `spellId` resolved: Elemental Weapon activates, a Primary counts toward Maelstrom Weapon, a Secondary
    // uses up a free cast.
    void Cast(Player* player, std::uint32_t spellId);
    // The imbue's damage factors for a hit of `spellId`.
    void Multipliers(Player* player, std::uint32_t spellId, DC::Combat::Factors& out);
    // The percent more Maelstrom the imbue gives what `spellId` generates.
    double GenerationPct(Player* player, std::uint32_t spellId);
    // A hit of `spellId` landed on `target`.
    void Landed(Player* player, Unit* target, std::uint32_t spellId);
    // The imbue in force, the activation's end, the sheet numbers and the buffs; called from the class's upkeep.
    void Upkeep(Player* player);
    void Forget(Player* player);
} // namespace DC::Combat::Shaman::ElementalWeapon
