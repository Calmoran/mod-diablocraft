#pragma once
// Shield Glare's rules that need no core type, header-only so tests/crusader_shield_glare compiles this exact code:
// which rune is which, which enemies the glare catches beyond the core's cone, and which of them are low enough for
// Emblazoned Shield to explode. The production half is dc_crusader_shield_glare.cpp.
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Crusader::ShieldGlare
{
    enum class Rune
    {
        None,
        DivineVerdict,    // blinded enemies take more damage
        Uncertainty,      // a chance to charm the enemies caught
        EmblazonedShield, // low enemies may explode when blinded
        ZealousGlare,     // Wrath for each enemy blinded
        Subdue            // the enemies hit are slowed
    };

    inline Rune RuneOf(std::string_view rune)
    {
        if (rune == "Divine Verdict")
            return Rune::DivineVerdict;
        if (rune == "Uncertainty")
            return Rune::Uncertainty;
        if (rune == "Emblazoned Shield")
            return Rune::EmblazonedShield;
        if (rune == "Zealous Glare")
            return Rune::ZealousGlare;
        if (rune == "Subdue")
            return Rune::Subdue;
        return Rune::None;
    }

    inline double ArcRadians(double degrees)
    {
        return degrees * 3.14159265358979323846 / 180.0;
    }

    // "Blinding all enemies up to {radius_yards} yards in front of you": an enemy the core's narrower cone did not
    // take, within the reach and the arc (the caller has asked whether it stands inside the arc).
    inline bool Caught(double distance, double reach, bool inArc, bool alreadyBlinded)
    {
        return !alreadyBlinded && inArc && reach > 0 && distance <= reach;
    }

    // "Enemies with health lower than {life_threshold_pct}": strictly below the threshold.
    inline bool Low(double healthPct, double thresholdPct)
    {
        return healthPct < thresholdPct;
    }

    // Zealous Glare: "Gain {gain_resource} Wrath for each enemy Blinded".
    inline double WrathFor(double perEnemy, unsigned enemies)
    {
        return perEnemy > 0 ? perEnemy * enemies : 0.0;
    }

    // The production half (dc_crusader_shield_glare.cpp), called from dc_crusader.cpp.
    bool Is(std::uint32_t spellId);
    // The glare deals no damage of its own: 0 for the skill and every rune, so Emblazoned Shield's explosion damage is not read as
    // the cone's.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The glare resolved on `targets`, the enemies of the core's cone: the rest of the arc, the blind, and what the
    // rune adds.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
} // namespace DC::Combat::Crusader::ShieldGlare
