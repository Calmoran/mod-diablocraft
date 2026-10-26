#pragma once
// The Shaman's Attunement: always one of four elements, it becomes the element of the last Secondary or Primal skill cast,
// after runes; the Shaman starts in Lightning. The rule needs no core type, header-only so the harness in
// tests/shaman_attunement compiles this exact code. The state, the buff and the effects are dc_shaman_attunement.cpp.
#include <cstdint>
#include <string_view>

namespace DC::Combat::Shaman::Attunement
{
    enum class Element : std::uint8_t { Fire, Cold, Physical, Lightning };
    inline constexpr Element Start = Element::Lightning;

    // The skills and runes that carry no element of their own, so casting them leaves the Attunement as it is (the draft
    // gives them "Attuned" or no element: Elemental Blast follows the Attunement and keeps it, Bloodlust and the plain and
    // Eternal Ascendance name none). The sheets resolve those cells to a school for the picker; this is the memory of which
    // they were. A rune is named by its skill and its own name; an empty rune is the skill itself.
    struct Keeps
    {
        std::string_view skill;
        std::string_view rune; // "*" every rune and the skill itself
    };
    inline constexpr Keeps KeepsAttunement[] = {
        {"Elemental Blast", "*"},
        {"Bloodlust", "*"},
        {"Ascendance", ""},
        {"Ascendance", "Eternal Ascendance"},
    };

    // Whether a cast of `skill` and `rune` of the catalogue category `category` moves the Attunement.
    inline bool Sets(std::string_view category, std::string_view skill, std::string_view rune)
    {
        if (category != "Secondary" && category != "Primal")
            return false;
        for (Keeps const& keeps : KeepsAttunement)
            if (keeps.skill == skill && (keeps.rune == "*" || keeps.rune == rune))
                return false;
        return true;
    }

    // The Attunement after a cast of element `cast` (`sets` from Sets).
    inline Element After(Element current, bool sets, Element cast)
    {
        return sets ? cast : current;
    }

    // The tooltip table (draft 1.5): what each element gives. Only one is nonzero.
    struct Bonus
    {
        double damagePct = 0;       // Fire: damage dealt
        double lifeRegenPct = 0;    // Cold: maximum Life regenerated each second
        double armorPct = 0;        // Physical: Armor
        double attackSpeedPct = 0;  // Lightning: attack speed
    };
    struct Table
    {
        double fireDamagePct, coldLifeRegenPct, physicalArmorPct, lightningAttackSpeedPct;
    };

    // `multiplier` is the passive that raises the bonus (Elemental Harmony triples it), 1 for none.
    inline Bonus BonusOf(Element element, Table const& table, double multiplier = 1.0)
    {
        Bonus bonus;
        switch (element)
        {
            case Element::Fire:
                bonus.damagePct = table.fireDamagePct * multiplier;
                break;
            case Element::Cold:
                bonus.lifeRegenPct = table.coldLifeRegenPct * multiplier;
                break;
            case Element::Physical:
                bonus.armorPct = table.physicalArmorPct * multiplier;
                break;
            case Element::Lightning:
                bonus.attackSpeedPct = table.lightningAttackSpeedPct * multiplier;
                break;
        }
        return bonus;
    }

    // The element of the school a record deals (dc_shaman_attunement.cpp).
    Element ElementOf(std::uint32_t spellId);
} // namespace DC::Combat::Shaman::Attunement
