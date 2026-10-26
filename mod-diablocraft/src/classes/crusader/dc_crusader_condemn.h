#pragma once
// Condemn's rules that need no core type, header-only so tests/crusader_condemn compiles this exact code: which rune is
// which, how long the explosion builds, what Reciprocate adds, how far Vacuum reaches on each pull and whom it takes,
// and the cooldown Eternal Retaliation gives back. The production half is dc_crusader_condemn.cpp.
#include <algorithm>
#include <cstdint>
#include <optional>
#include <string_view>

class Player;
class Unit;

namespace DC::Combat::Crusader::Condemn
{
    enum class Rune
    {
        None,
        Reciprocate,         // a share of the damage taken while it builds is added to the explosion
        Vacuum,              // enemies are sucked in as it charges
        EternalRetaliation,  // the cooldown is cut for each enemy hit
        ShatteringExplosion, // a wider explosion
        Unleashed            // it goes off at once
    };

    inline Rune RuneOf(std::string_view rune)
    {
        if (rune == "Reciprocate")
            return Rune::Reciprocate;
        if (rune == "Vacuum")
            return Rune::Vacuum;
        if (rune == "Eternal Retaliation")
            return Rune::EternalRetaliation;
        if (rune == "Shattering Explosion")
            return Rune::ShatteringExplosion;
        if (rune == "Unleashed")
            return Rune::Unleashed;
        return Rune::None;
    }

    // "unleashing it after {duration_seconds} seconds"; Unleashed: "The explosion now unleashes instantly".
    inline double BuildSeconds(Rune rune, double seconds)
    {
        return rune == Rune::Unleashed || seconds < 0 ? 0.0 : seconds;
    }

    // The time of the build is over from its end moment on; damage taken from then on is not counted.
    inline bool Building(std::uint64_t now, std::uint64_t until)
    {
        return now < until;
    }

    // Reciprocate: "{damage_share_pct} of all damage taken while the explosion is building is added to the damage of
    // the explosion". Nothing for another rune, for damage that is not damage or for no share.
    inline double Reciprocated(Rune rune, double taken, double sharePct)
    {
        return rune == Rune::Reciprocate && taken > 0 && sharePct > 0 ? taken * sharePct / 100.0 : 0.0;
    }

    // Vacuum: the pulses that fit the build, one every `interval` seconds. None without an interval.
    inline unsigned Pulses(double seconds, double interval)
    {
        return seconds > 0 && interval > 0 ? static_cast<unsigned>(seconds / interval + 1e-9) : 0u;
    }

    // Vacuum: "the closer it is to exploding, the more enemies it sucks in": the reach grows by `step` yards a pulse
    // from the explosion's own radius (pulse 1 is the first).
    inline double PullReach(double explosionRadius, double step, unsigned pulse)
    {
        return explosionRadius + (step > 0 ? step : 0.0) * pulse;
    }

    // Vacuum takes an enemy beyond the explosion and inside the reach of this pulse; one already inside the
    // explosion is left where it is.
    inline bool SuckedIn(double distance, double explosionRadius, double reach)
    {
        return distance > explosionRadius && distance <= reach;
    }

    // Eternal Retaliation: "Reduce the cooldown by {cooldown_reduction_seconds} second for each enemy hit by the
    // explosion."
    inline double CooldownCut(Rune rune, unsigned enemiesHit, double perEnemySeconds)
    {
        return rune == Rune::EternalRetaliation && perEnemySeconds > 0 ? enemiesHit * perEnemySeconds : 0.0;
    }

    // The production half (dc_crusader_condemn.cpp), called from dc_crusader.cpp.
    bool Is(std::uint32_t spellId);
    // Condemn deals no damage on the cast: 0 for the skill and every rune, so the explosion's 1160% is not read as the
    // cast's.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast: the explosion builds, and goes off after its time (at once for Unleashed).
    void Cast(Player* player, std::uint32_t spellId);
    // `victim` took `damage`: Reciprocate counts it while the explosion builds.
    void Taken(Player* victim, double damage);
} // namespace DC::Combat::Crusader::Condemn
