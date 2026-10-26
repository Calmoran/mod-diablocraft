#pragma once
// The Crusader's passives: Heavenly Strength, Fervor, Vigilant, Righteousness, Insurmountable, Fanaticism; Indestructible, Holy
// Cause, Wrathful, Divine Fortress, Lord Commander, Hold Your Ground; Long Arm of the Law, Iron Maiden, Renewal, Finery, Blunt,
// Towering Shield. The rules
// that need no core type, header-only so tests/crusader_passives compiles this exact code; the game glue is
// dc_crusader_passives.cpp. Numbers: crusader_passive_values.csv, through each passive's record.
#include "../../common/dc_common.h"

#include <algorithm>
#include <cstdint>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Crusader::Passive
{
    // What the Crusader holds: a one-handed or a two-handed weapon in the main hand, and a shield in the off hand.
    struct Wield
    {
        bool oneHand = false;
        bool twoHand = false;
        bool shield = false;
    };

    // Fervor: "While wielding a one-handed weapon, your attack speed is increased by ... and all cooldowns are reduced
    // by ...".
    inline bool FervorOn(Wield const& wield)
    {
        return wield.oneHand;
    }

    // Heavenly Strength: "You can wield a two-handed weapon in your main hand while bearing a shield ... Your damage
    // dealt is reduced by {damage_dealt_reduction_pct}": the reduction is the price of that grip, so it is taken while
    // a two-handed weapon and a shield are both held and never otherwise.
    inline double HeavenlyStrengthPct(Wield const& wield, double reductionPct)
    {
        return wield.twoHand && wield.shield && reductionPct > 0 ? reductionPct : 0.0;
    }

    // Heavenly Strength's grip: the core's Titan's Grip rule is told yes for a Crusader who has the passive, and no for
    // anyone else (another class never holds a two-handed weapon with a shield, and a Crusader without the passive
    // does not either). Dual wield stays what it was: the Crusader has none, so the core still refuses a two-handed
    // weapon in the off hand.
    inline bool HeavenlyStrengthGrip(bool crusader, bool passiveOn)
    {
        return crusader && passiveOn;
    }

    // The grip held with no right to it: a two-handed weapon and a shield together after the passive was unpicked (or
    // the grip was never allowed). The shield comes off, as the core does for a two-hander without Titan's Grip.
    inline bool GripBroken(Wield const& wield, bool gripAllowed)
    {
        return wield.twoHand && wield.shield && !gripAllowed;
    }

    // Vigilant: "Reduce all non-Physical damage taken by {damage_reduction_pct}".
    inline bool VigilantReduces(Element element)
    {
        return element != Element::Physical;
    }

    // Fanaticism: "Increase the attack speed of Punish, Slash, Smite and Justice by {attack_speed_pct}".
    inline bool FanaticismSkill(std::string_view skill)
    {
        return skill == "Punish" || skill == "Slash" || skill == "Smite" || skill == "Justice";
    }

    // Attack speed bonuses add to each other (D3: the sheet's speed is the weapon's times one plus the sum), so the
    // passive's share goes into the sum the skill's speed was built from: `aps` is the hand's attacks per second with
    // `iasPct` already in it. The result keeps to the attack speed cap and never falls below what it was.
    inline double FanaticismAps(double aps, double iasPct, double bonusPct, double cap)
    {
        if (aps <= 0 || bonusPct <= 0 || 1.0 + iasPct / 100.0 <= 0)
            return aps;
        double const sped = aps * (1.0 + (iasPct + bonusPct) / 100.0) / (1.0 + iasPct / 100.0);
        return std::max(aps, std::min(cap, sped));
    }

    // Righteousness: "Your primary skills generate an additional {generated_resource} Wrath": the extra a cast of a
    // skill of the category pays, nothing for another category.
    inline double RighteousnessWrath(bool primary, double extra)
    {
        return primary && extra > 0 ? extra : 0.0;
    }

    // Insurmountable: "Blocking an attack generates {gain_resource} Wrath".
    inline double InsurmountableWrath(double gain)
    {
        return gain > 0 ? gain : 0.0;
    }

    // Fervor's cooldown reduction as the sheet takes it, held to the 0 to 100 it holds.
    inline double CooldownContribution(double pct)
    {
        return std::clamp(pct, 0.0, 100.0);
    }

    // What the update script keeps on the sheet, one bit each: Fervor while a one-handed weapon is wielded, Vigilant,
    // Righteousness' larger Wrath pool.
    enum Bit : unsigned
    {
        FervorBit = 1,
        VigilantBit = 2,
        RighteousnessBit = 4,
        DivineFortressBit = 8,
        HoldGroundBit = 16,
        IronMaidenBit = 32,
        FineryBit = 64,
    };

    // Long Arm of the Law: "Increase the duration of the Active effect of all Laws by {duration_seconds} seconds": an effect
    // of `seconds` lasts `bonus` longer; an effect of no time stays no time.
    inline double LongArm(double seconds, double bonus)
    {
        return seconds > 0 && bonus > 0 ? seconds + bonus : seconds;
    }

    // Renewal: "Whenever you successfully block, you gain {heal_life} Life".
    inline double RenewalHeal(double life)
    {
        return life > 0 ? life : 0.0;
    }

    // Finery: "Gain {primary_stat_pct} Strength for every gem socketed into your gear": the percent of Strength the gems give.
    inline double FineryPct(double perGem, unsigned gems)
    {
        return perGem > 0 ? perGem * gems : 0.0;
    }

    // Blunt: "Increase the damage of Justice and Blessed Hammer by {damage_bonus_pct}".
    inline bool BluntSkill(std::string_view skill)
    {
        return skill == "Justice" || skill == "Blessed Hammer";
    }

    // Towering Shield: "Increase the damage of Punish, Shield Bash and Blessed Shield by {damage_bonus_pct}".
    inline bool ToweringDamageSkill(std::string_view skill)
    {
        return skill == "Punish" || skill == "Shield Bash" || skill == "Blessed Shield";
    }

    // Towering Shield: "Reduce the cooldown of Shield Glare by {cooldown_reduction_pct}".
    inline bool ToweringCooldownSkill(std::string_view skill)
    {
        return skill == "Shield Glare";
    }

    // Indestructible: "When you receive fatal damage, you instead become immune to damage, gain {damage_bonus_pct} increased
    // damage and gain {heal_per_hit_life} Life per Kill for {duration_seconds} seconds. This effect may occur once every
    // {internal_cooldown_seconds} seconds." One Crusader's state: the time the save lasts and the time before it may save again.
    struct Fatal
    {
        std::uint64_t until = 0;   // immune, stronger and healed per kill until this moment
        std::uint64_t readyAt = 0; // the save may happen again from this moment

        bool Active(std::uint64_t now) const
        {
            return now < until;
        }

        // A hit of `damage` on a Crusader with `health` left: a fatal one (it takes all the health) saves once the cooldown has
        // run. True when it saved; the caller then drops the damage.
        bool Save(std::uint64_t now, std::uint32_t damage, std::uint32_t health, std::uint64_t cooldownMs, std::uint64_t durationMs)
        {
            if (now < readyAt || damage < health || durationMs == 0)
                return false;
            until = now + durationMs;
            readyAt = now + cooldownMs;
            return true;
        }
    };

    // Holy Cause: "Whenever you deal Holy damage, you heal up to {heal_pct} of your total Life": the Life a Holy hit heals.
    inline double HolyCauseHeal(bool holy, double maxLife, double healPct)
    {
        return holy && maxLife > 0 && healPct > 0 ? maxLife * healPct / 100.0 : 0.0;
    }

    // Wrathful: "Each point of Wrath spent heals you for {heal_per_hit_life} Life": the Life a cast that cost `wrath` heals.
    inline double WrathfulHeal(double perPoint, double wrath)
    {
        return perPoint > 0 && wrath > 0 ? perPoint * wrath : 0.0;
    }

    // Divine Fortress: "Your Armor is increased by a percent equal to your shield's Block Chance".
    inline double DivineFortressPct(double blockChancePct)
    {
        return std::max(0.0, blockChancePct);
    }

    // Lord Commander: "The cooldown of Steed Charge is reduced by {cooldown_reduction_pct:steed_charge} and Bombardment by
    // {cooldown_reduction_pct:bombardment}": the sheet's qualifier of a skill it names, empty for any other.
    inline std::string_view LordCommanderQualifier(std::string_view skill)
    {
        if (skill == "Steed Charge")
            return "steed_charge";
        if (skill == "Bombardment")
            return "bombardment";
        return {};
    }

    // The milliseconds a cut of `pct` percent takes off a cooldown that has `leftMs` to run; never more than is left.
    inline std::uint32_t CooldownCut(std::uint32_t leftMs, double pct)
    {
        double const cut = leftMs * std::clamp(pct, 0.0, 100.0) / 100.0;
        return std::uint32_t(cut + 0.5);
    }

    // Lord Commander: "Damage dealt by Phalanx is increased {damage_bonus_pct}".
    inline bool LordCommanderDamage(std::string_view skill)
    {
        return skill == "Phalanx";
    }

    // Hold Your Ground: "You can no longer Dodge, but your Block Chance is increased by {block_pct}": the factor on every dodge
    // chance a Crusader holding it would have had.
    inline double DodgeFactor(bool holdYourGround)
    {
        return holdYourGround ? 0.0 : 1.0;
    }

    // The production half (dc_crusader_passives.cpp), called from dc_crusader.cpp.
    // The passives' factors on a hit of `spellId`: Heavenly Strength's reduction, Holy Cause's, Indestructible's and Lord Commander's
    // bonuses, each a multiplier of its own.
    void Multipliers(Player* player, std::uint32_t spellId, std::vector<std::pair<std::string, double>>& out);
    // A skill's attacks per second `base`, with Fanaticism's share added for the four skills it names
    // (Combat::AttacksPerSecond and HandAttacksPerSecond).
    double AttackSpeed(Player* player, std::uint32_t spellId, double base);
    // A cast of `spellId` hit at least one enemy: Righteousness pays its extra Wrath for a primary.
    void Connected(Player* player, std::uint32_t spellId);
    // The Crusader blocked a hit: Insurmountable pays its Wrath and Renewal heals.
    void Blocked(Player* player);
    // The seconds Long Arm of the Law adds to the active effect of a Law of this Crusader's (0 without the passive).
    double LongArmSeconds(Player* player);
    // A hit of the Crusader's landed (Crusader::Landed): Holy Cause heals for a Holy one.
    void Landed(Player* player, std::uint32_t spellId);
    // The multiplier on a dodge chance (Combat's outcome hook and spell hook): 0 for a Crusader holding Hold Your Ground, else 1.
    double DodgeFactor(Unit const* unit);
    // A hit of `damage` is about to be dealt to `victim` (a UnitScript hook): Indestructible turns a fatal one into immunity.
    void Damage(Player* victim, std::uint32_t& damage);
    // The update script that keeps the sheet rows (once, at startup).
    void Register();
} // namespace DC::Combat::Crusader::Passive
