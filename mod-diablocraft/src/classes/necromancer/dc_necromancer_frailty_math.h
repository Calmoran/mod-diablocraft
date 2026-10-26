#pragma once
// The rules of Frailty's runes that need no core type, header-only so tests/necromancer_frailty compiles this exact code: which rune is
// which and which enemies the curse kills. The production half is dc_necromancer_frailty.cpp.
#include <string_view>

namespace DC::Combat::Necromancer::Frailty
{
    enum class Rune
    {
        None,
        EarlyGrave,
        HarvestEssence,
        VolatileDeath,
        ScentOfBlood,
        AuraOfFrailty
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Early Grave")
            return Rune::EarlyGrave;
        if (name == "Harvest Essence")
            return Rune::HarvestEssence;
        if (name == "Volatile Death")
            return Rune::VolatileDeath;
        if (name == "Scent of Blood")
            return Rune::ScentOfBlood;
        if (name == "Aura of Frailty")
            return Rune::AuraOfFrailty;
        return Rune::None;
    }

    // "A crippling curse that kills enemies with less than {life_threshold_pct} health": whether an enemy with `lifePct` percent of its Life
    // left is killed (a Life of 0 or more is under no threshold of 0 or less: no threshold, no kill).
    inline bool Executes(double lifePct, double thresholdPct)
    {
        return lifePct < thresholdPct;
    }
} // namespace DC::Combat::Necromancer::Frailty
