#pragma once
// Horrify's rules that need no core type, header-only so tests/witch_doctor_horrify compiles this exact code: which
// rune is which, whether a cast immobilizes what it frightens and the Mana a rune returns for the enemies it horrified.
// The production half is dc_witch_doctor_horrify.cpp.
#include <cstdint>
#include <string_view>

class Player;

namespace DC::Combat::WitchDoctor::Horrify
{
    enum class Rune
    {
        None,
        FrighteningAspect, // armor for a while after the cast
        FaceOfDeath,       // a wider circle
        Phobia,            // the enemies run in Fear and are not immobilized, for longer
        RuthlessTerror,    // Mana for every horrified enemy
        Stalker            // movement speed for a while after the cast
    };

    inline Rune RuneOf(std::string_view rune)
    {
        if (rune == "Frightening Aspect")
            return Rune::FrighteningAspect;
        if (rune == "Face of Death")
            return Rune::FaceOfDeath;
        if (rune == "Phobia")
            return Rune::Phobia;
        if (rune == "Ruthless Terror")
            return Rune::RuthlessTerror;
        if (rune == "Stalker")
            return Rune::Stalker;
        return Rune::None;
    }

    // "causing them to tremor in Fear and be Immobilized": the skill and every rune hold the frightened enemy still,
    // except Phobia ("Enemies are no longer Immobilized and will instead run in Fear").
    inline bool Immobilizes(Rune rune)
    {
        return rune != Rune::Phobia;
    }

    // The production half (dc_witch_doctor_horrify.cpp), called from dc_witch_doctor.cpp.
    bool Is(std::uint32_t spellId);
    // The cast of Horrify or one of its runes: the fear (and the root) on the enemies in the circle, then what the rune
    // adds.
    void Cast(Player* player, std::uint32_t spellId);
} // namespace DC::Combat::WitchDoctor::Horrify
