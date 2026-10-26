#pragma once
// The rules of Command Golem's runes that need no core type, header-only so tests/necromancer_command_golem compiles this
// exact code: which rune is which, which record the Golem's blows are dealt as, how long the Bone Golem's tornado travels,
// how many pulses it makes where it stops, when each vein of the Blood Golem strikes, and what the Decay Golem's corpses are
// worth. The production half is dc_necromancer_command_golem.cpp (the active) and dc_necromancer_pets.cpp (the Golem).
#include <algorithm>
#include <cmath>
#include <string_view>

namespace DC::Combat::Necromancer::CommandGolem
{
    enum class Rune
    {
        None,
        BoneGolem,
        BloodGolem,
        DecayGolem,
        FleshGolem,
        IceGolem
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Bone Golem")
            return Rune::BoneGolem;
        if (name == "Blood Golem")
            return Rune::BloodGolem;
        if (name == "Decay Golem")
            return Rune::DecayGolem;
        if (name == "Flesh Golem")
            return Rune::FleshGolem;
        if (name == "Ice Golem")
            return Rune::IceGolem;
        return Rune::None;
    }

    // The Golem collapses into a pile of corpses (the skill and Flesh Golem); the other runes keep or rebuild it.
    inline bool Collapses(Rune rune)
    {
        return rune == Rune::None || rune == Rune::FleshGolem;
    }

    // The Golem's own blows come from the rune's record only where the rune changes their school (Decay Golem's Poison, Ice
    // Golem's Cold); the other runes' {damage_pct} is their active's, not the Golem's 450%.
    inline bool BlowsUseRuneRecord(Rune rune)
    {
        return rune == Rune::DecayGolem || rune == Rune::IceGolem;
    }

    // How long the Bone Golem takes to reach the place aimed at: the yards over its speed times the rune's scalar. None for
    // no speed.
    inline double TravelSeconds(double yards, double speed, double scalar)
    {
        return yards > 0 && speed > 0 && scalar > 0 ? yards / (speed * scalar) : 0.0;
    }

    // The pulses that fit a time at `interval` seconds. No interval, no pulses.
    inline unsigned Pulses(double seconds, double interval)
    {
        return seconds > 0 && interval > 0 ? static_cast<unsigned>(std::floor(seconds / interval + 1e-9)) : 0u;
    }

    // The point a share of the way from `a` to `b`, the share held between none and the whole.
    inline double Along(double a, double b, double share)
    {
        return a + (b - a) * std::clamp(share, 0.0, 1.0);
    }

    // When the `index`th vein of the Blood Golem strikes, in seconds after the Golem is sacrificed (the first at once).
    inline double VeinAt(unsigned index, double gapSeconds)
    {
        return gapSeconds > 0 ? index * gapSeconds : 0.0;
    }

    // Blood Golem's knockback (the power's Knockback Radius): where an enemy `distance` yards from the place stands after it:
    // one inside the radius is pushed out to its edge, one outside it stays.
    inline double PushedTo(double distance, double radius)
    {
        return radius > 0 && distance < radius ? radius : distance;
    }

    // Decay Golem grows with its meal: up to `maxPct` percent bigger at `most` corpses, in proportion to the corpses eaten.
    inline double ScaleBonusPct(unsigned corpses, unsigned most, double maxPct)
    {
        return most && maxPct > 0 ? maxPct * std::min(corpses, most) / most : 0.0;
    }

    // Decay Golem's growth is given back by the event of its last meal only. A meal takes the next number of a counter (no clock,
    // so two meals in one millisecond differ and an event that fires a millisecond before the game clock does is not early), and an
    // event's reset is due only while its meal's number is the one held.
    inline unsigned long long NextMeal(unsigned long long last)
    {
        return last + 1;
    }

    inline bool ResetDue(unsigned long long held, unsigned long long mine)
    {
        return held != 0 && held == mine;
    }

    // Decay Golem: "increasing its damage by {damage_bonus_pct} per corpse", of at most `most` corpses.
    inline double CorpseBonusPct(unsigned corpses, double perCorpsePct, unsigned most)
    {
        return std::min(corpses, most) * std::max(0.0, perCorpsePct);
    }
} // namespace DC::Combat::Necromancer::CommandGolem
