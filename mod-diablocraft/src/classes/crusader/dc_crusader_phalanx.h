#pragma once
// Phalanx's rules that need no core type, header-only so tests/crusader_phalanx compiles this exact code: which rune is
// which, what its avatars do, what each rune's cast owes (the cost given back and the cooldown), how fast a charge
// runs, who a Stampede stuns, when a bowman shoots, and where the line of a charge ends. The production half is
// dc_crusader_phalanx.cpp.
#include "dc_crusader_consecration.h"

#include <algorithm>
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;
struct Position;

namespace DC::Combat::Crusader::Phalanx
{
    enum class Rune
    {
        None,
        Bowmen,        // the avatars follow and shoot
        ShieldCharge,  // a shield bash where they arrive
        Stampede,      // warhorses, with a chance to stun
        ShieldBearers, // the avatars stand and hold a place
        Bodyguard      // the avatars fight beside the Crusader
    };

    inline Rune RuneOf(std::string_view rune)
    {
        if (rune == "Bowmen")
            return Rune::Bowmen;
        if (rune == "Shield Charge")
            return Rune::ShieldCharge;
        if (rune == "Stampede")
            return Rune::Stampede;
        if (rune == "Shield Bearers")
            return Rune::ShieldBearers;
        if (rune == "Bodyguard")
            return Rune::Bodyguard;
        return Rune::None;
    }

    enum class Behavior
    {
        Charge, // run to the target point and go
        Follow, // follow the Crusader and shoot
        Stand,  // stand at the target point
        Fight   // follow the Crusader and fight what it fights
    };

    // "Summon powerful avatars who charge forward to the targeted destination" is the skill and two of its runes;
    // the other three keep the avatars back: "no longer march forward", "stand at the summoned location", "Instead of
    // sending the avatars out away from you".
    inline Behavior BehaviorOf(Rune rune)
    {
        switch (rune)
        {
            case Rune::Bowmen:
                return Behavior::Follow;
            case Rune::ShieldBearers:
                return Behavior::Stand;
            case Rune::Bodyguard:
                return Behavior::Fight;
            default:
                return Behavior::Charge;
        }
    }

    // "Enemies caught in the charge path take {damage_pct} weapon damage": the charge runes hit the line; the others
    // send no avatar down it.
    inline bool HitsTheLine(Rune rune)
    {
        return BehaviorOf(rune) == Behavior::Charge;
    }

    // The three runes the power file makes free (Power/x1_Crusader_Phalanx3.pow SF_5: Rune_E ? 0 : Rune_D ? 0 : Rune_A
    // ? 0 : the cost) and gives a cooldown instead ("can only be summoned once every {internal_cooldown_seconds}
    // seconds"). Their records cost nothing (the rune sheet's "Wrath cost removed"), so the cast only starts the cooldown.
    inline bool FreeButGated(Rune rune)
    {
        return rune == Rune::Bowmen || rune == Rune::ShieldBearers || rune == Rune::Bodyguard;
    }

    inline double CooldownSeconds(Rune rune, double internalCooldown)
    {
        return FreeButGated(rune) && internalCooldown > 0 ? internalCooldown : 0.0;
    }

    // How many times as fast as the plain charge a rune's avatars run: the power file's base speed with the rune's
    // modifier added (SF_13 + SF_12 for Shield Charge, SF_13 + SF_43 for Stampede), over the base.
    inline double SpeedRatio(Rune rune, double base, double shieldChargeBonus, double stampedeBonus)
    {
        if (base <= 0)
            return 1.0;
        double const bonus = rune == Rune::ShieldCharge ? shieldChargeBonus
                             : rune == Rune::Stampede   ? stampedeBonus
                                                        : 0.0;
        return (base + std::max(0.0, bonus)) / base;
    }

    // The multiple of its creature's own run speed the avatars run at: the charge's yards a second over the creature's,
    // times the rune's ratio. With no speed set (or no creature speed to compare) the creature's own speed.
    inline double RunRate(double yardsPerSecond, double creatureYardsPerSecond, double ratio)
    {
        return (yardsPerSecond > 0 && creatureYardsPerSecond > 0 ? yardsPerSecond / creatureYardsPerSecond : 1.0) * ratio;
    }

    // Stampede: "a {proc_chance_pct} chance to Stun enemies": a roll in [0, 100) under the chance, for that rune only.
    inline bool Stuns(Rune rune, double roll, double chancePct)
    {
        return rune == Rune::Stampede && chancePct > 0 && roll < chancePct;
    }

    // Bowmen: a bowman shoots once its clock has run the fire rate.
    inline bool ShotDue(double clockMs, double fireSeconds)
    {
        return fireSeconds > 0 && clockMs >= fireSeconds * 1000.0;
    }

    // Where the avatars stop: the target point, but never farther from the Crusader than the power's reach. The share
    // of the way from the Crusader to the point that the run covers.
    inline double RunShare(double distance, double reach)
    {
        return distance <= 0 || reach <= 0 ? 0.0 : std::min(1.0, reach / distance);
    }

    // Avatars side by side across the line of the charge: the sideways offset of avatar `index` of `count`, centred.
    inline double Abreast(unsigned index, unsigned count, double gap)
    {
        return count ? (double(index) - (double(count) - 1.0) / 2.0) * gap : 0.0;
    }

    // The production half (dc_crusader_phalanx.cpp), called from dc_crusader.cpp.
    bool Is(std::uint32_t spellId);
    // The line hit the cast deals: the skill's own percentage for the charge runes, 0 for the others and for the
    // bash's.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast resolved its line on `targets`: Stampede's stuns, the cost given back and the cooldown of the gated
    // runes.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    // The cast landed at `center`: the avatars are summoned, and what they do begins.
    void Ground(Player* player, std::uint32_t spellId, Position const& center);
    // `count` avatars that follow `player` and fight what it fights for `seconds`, side by side at `origin`, each blow
    // `spellId`'s own damage_pct: the Bodyguard's, and any other rune that sends the same fighters (Falling Sword's Rise
    // Brothers).
    void Fighters(Player* player, std::uint32_t spellId, unsigned count, double seconds, Position const& origin);
    // The Phalanx avatar's creature script (Combat::RegisterScripts).
    void RegisterScripts();
} // namespace DC::Combat::Crusader::Phalanx
