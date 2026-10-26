/*
 * World of DiabloCraft - what a follower may wear, and what its gear makes of it, as pure functions (contract
 * docs/contracts/followers.md).
 *
 * Which of a follower's 14 slots an item goes in (the kinds of data/d3/followers_gear.csv, the relic of the item's own
 * follower), the follower's stat sheet from the affixes of its gear (the main stats counted 2.5 times, the crit damage
 * cap), and the creature numbers that sheet becomes (life, armor, resistances, one swing). No core types besides the
 * stat sheet of dc_common.h, so the harness test (tests/follower_gear/harness.cpp) compiles and drives this file
 * itself. The numbers come from data/d3/followers_gear_rules.csv through the dc_follower_gear_rule table; nothing
 * tunable is a literal here.
 */

#ifndef DC_FOLLOWER_GEAR_RULE_H
#define DC_FOLLOWER_GEAR_RULE_H

#include "../common/dc_common.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace DC::Items::FollowerGear
{
    // A follower's slots, in the order the Follower window lists them (data/d3/followers_gear.csv gear_slot).
    enum class Slot : std::uint8_t
    {
        Relic,
        Head,
        Shoulders,
        Chest,
        Gloves,
        Bracers,
        Belt,
        Pants,
        Boots,
        Ring1,
        Ring2,
        Neck,
        MainHand,
        OffHand
    };
    constexpr unsigned SlotCount = 14;

    inline constexpr std::array<std::string_view, SlotCount> SlotKeys = {
        "relic", "head",  "shoulders", "chest", "gloves", "bracers",  "belt",
        "pants", "boots", "ring1",     "ring2", "neck",   "mainhand", "offhand"};

    constexpr std::string_view KeyOf(Slot slot)
    {
        return SlotKeys[unsigned(slot)];
    }

    inline std::optional<Slot> SlotOf(std::string_view key)
    {
        for (unsigned index = 0; index < SlotCount; ++index)
            if (SlotKeys[index] == key)
                return Slot(index);
        return std::nullopt;
    }

    constexpr unsigned Bit(Slot slot)
    {
        return 1u << unsigned(slot);
    }

    // One row of dc_follower_gear_kind: this follower wears base items of this slot and type in this gear slot.
    struct Kind
    {
        unsigned follower = 0;
        Slot slot = Slot::Head;
        std::string itemSlot, itemType;
    };

    // What the equip rule needs to know of the item offered.
    struct Offered
    {
        bool relic = false; // one of the follower items (dc_follower_relic)
        unsigned relicFollower = 0;
        std::string itemSlot, itemType; // the base item's, for anything but a relic
        bool classBound = false;        // the base item names a class of its own (designated_class)
    };

    // What the follower holds now: the slots that are filled, and whether the main hand holds a two-hander.
    struct Held
    {
        unsigned filled = 0;
        bool twoHanded = false;
    };

    enum class Refusal : std::uint8_t
    {
        None,
        WrongFollower, // a relic of another follower
        ClassItem,     // an item of a class's own
        WrongKind,     // not a kind this follower wears
        HandBusy       // a two-hander needs both hands free, or the main hand holds one
    };

    inline char const* Words(Refusal refusal)
    {
        switch (refusal)
        {
            case Refusal::WrongFollower:
                return "That relic belongs to another follower.";
            case Refusal::ClassItem:
                return "That is a class's own item; a follower cannot use it.";
            case Refusal::WrongKind:
                return "This follower cannot wear that kind of item.";
            case Refusal::HandBusy:
                return "A two-handed weapon needs both hands free.";
            case Refusal::None:
                break;
        }
        return "";
    }

    struct Placement
    {
        Refusal refusal = Refusal::None;
        Slot slot = Slot::Head;
    };

    // The slot an item goes in, or why it does not. `wanted` names a slot the caller asks for (the Follower window
    // drops an item on a slot); it must be one the item fits. With none named, the first free slot of the item's kind
    // is taken, and when all are full the first one (the item in it goes back to the bags).
    inline Placement Place(unsigned follower, Offered const& item, std::vector<Kind> const& kinds,
                           std::optional<Slot> wanted, Held const& held)
    {
        Placement out;
        std::vector<Slot> fits;
        if (item.relic)
        {
            if (item.relicFollower != follower)
            {
                out.refusal = Refusal::WrongFollower;
                return out;
            }
            fits.push_back(Slot::Relic);
        }
        else
        {
            if (item.classBound)
            {
                out.refusal = Refusal::ClassItem;
                return out;
            }
            for (Kind const& kind : kinds)
                if (kind.follower == follower && kind.itemSlot == item.itemSlot && kind.itemType == item.itemType)
                    fits.push_back(kind.slot);
        }
        if (fits.empty())
        {
            out.refusal = Refusal::WrongKind;
            return out;
        }
        if (wanted)
        {
            if (std::find(fits.begin(), fits.end(), *wanted) == fits.end())
            {
                out.refusal = Refusal::WrongKind;
                return out;
            }
            out.slot = *wanted;
        }
        else
        {
            out.slot = fits.front();
            for (Slot slot : fits)
                if (!(held.filled & Bit(slot)))
                {
                    out.slot = slot;
                    break;
                }
        }
        bool const twoHander = !item.relic && item.itemSlot == "twohand";
        if (twoHander && out.slot == Slot::MainHand && (held.filled & Bit(Slot::OffHand)))
            out.refusal = Refusal::HandBusy;
        if (out.slot == Slot::OffHand && held.twoHanded)
            out.refusal = Refusal::HandBusy;
        return out;
    }

    // Whether the follower can put anything in a slot now: the relic slot always (its relic is its own), any other slot
    // that some kind of the follower's names, and the off-hand only while the main hand holds no two-hander. The
    // Follower window dims a slot this refuses.
    inline bool SlotUsable(unsigned follower, Slot slot, std::vector<Kind> const& kinds, Held const& held)
    {
        if (slot == Slot::Relic)
            return true;
        if (slot == Slot::OffHand && held.twoHanded)
            return false;
        return std::any_of(kinds.begin(), kinds.end(),
                           [&](Kind const& kind) { return kind.follower == follower && kind.slot == slot; });
    }

    // data/d3/followers_gear_rules.csv, in the units the code uses.
    struct StatRules
    {
        double mainStatMultiplier = 0; // Strength, Dexterity, Intelligence and Vitality from gear count this many times
        double critDamageCap = 0;      // the sheet's Critical Hit Damage, at most this
        double playerSharePct = 0;     // the part of Magic Find, Gold Find and Experience Gain the player gets
    };

    constexpr bool Usable(StatRules const& rules)
    {
        return rules.mainStatMultiplier > 0 && rules.critDamageCap > 0 && rules.playerSharePct > 0;
    }

    constexpr bool CountsTwiceAndAHalf(Stat stat)
    {
        return stat == Stat::Strength || stat == Stat::Dexterity || stat == Stat::Intelligence ||
               stat == Stat::Vitality;
    }

    // The value a gear contribution puts on the follower's sheet: the attribute points count the multiplier (a percent
    // bonus to an attribute is not points), everything else as rolled.
    constexpr double OnFollower(Contribution const& gear, StatRules const& rules)
    {
        return CountsTwiceAndAHalf(gear.stat) && gear.bucket == Bucket::Flat ? gear.value * rules.mainStatMultiplier
                                                                             : gear.value;
    }

    // The follower's sheet: its gear's contributions (already filtered to the affixes a follower uses) on a base with
    // no attributes of its own, then the crit damage cap.
    template<typename Calculate>
    StatSheet Sheet(BaseStats const& base, std::vector<Contribution> gear, StatRules const& rules, Calculate calculate)
    {
        for (Contribution& contribution : gear)
            contribution.value = OnFollower(contribution, rules);
        StatSheet sheet = calculate(base, gear);
        double& crit = sheet.values[Index(Stat::CritDamage)];
        crit = std::min(crit, rules.critDamageCap);
        return sheet;
    }

    // What a follower hands its player: the shared stats of its gear, at the share (data/d3/followers_stats.csv). The
    // value is the follower's own, before the share.
    constexpr double Shared(double followerValue, StatRules const& rules)
    {
        return followerValue * rules.playerSharePct / 100.0;
    }

    // The stock core's damage reductions, which the follower's creature is mitigated by. The sheet's reductions (armor
    // over armor plus 50 a level, resistance over resistance plus 5 a level) are matched by the core armor and
    // resistance that give the same reduction at the same level, so the core does the mitigation and no hook is needed.
    // Unit::CalcArmorReducedDamage: armor / (armor + 85 * L + 400), L the attacker's level, raised by 4.5 a level
    // above 59. Unit::GetEffectiveResistChance: resistance / (resistance + C), C = 150 + (L - 60)(L - 67.5) above level
    // 60, 50 + 2.5 (L - 20) up to 60, 50 below; at most 0.75 for both.
    constexpr double CoreReductionCap = 0.75;

    inline double CoreArmorConstant(unsigned attackerLevel)
    {
        double level = attackerLevel;
        if (level > 59)
            level += 4.5 * (level - 59);
        return 85.0 * level + 400.0;
    }

    inline double CoreResistConstant(unsigned attackerLevel)
    {
        double const level = attackerLevel;
        if (level > 60.0)
            return 150.0 + (level - 60.0) * (level - 67.5);
        if (level > 20.0)
            return 50.0 + (level - 20.0) * 2.5;
        return 50.0;
    }

    // The core value (armor or resistance) whose reduction is `reduction` against an attacker of this level.
    inline std::int32_t CoreValue(double reduction, double constant)
    {
        double const capped = std::clamp(reduction, 0.0, CoreReductionCap);
        return std::int32_t(std::lround(capped / (1.0 - capped) * constant));
    }

    // The template weapon the follower swings: its damage range and delay (milliseconds), or none.
    struct Weapon
    {
        bool present = false;
        double min = 0, max = 0, delayMs = 0;
    };

    // The core's schools a sheet's elements land on (0 physical: armor, not a resistance).
    constexpr std::array<unsigned, ElementCount> SchoolOfElement = {0, 2, 4, 3, 5, 6, 1};

    // The numbers the follower's creature takes.
    struct CreaturePlan
    {
        std::uint32_t maxHealth = 0;
        std::int32_t armor = 0;
        std::array<std::int32_t, 7> resistance{}; // by core school; 0 unused (physical is armor)
        bool swings = false;                      // a weapon: the swing below replaces the creature's stock damage
        double swingMin = 0, swingMax = 0;        // one swing
        std::uint32_t attackTimeMs = 0;
    };

    // The plan for a sheet. `mainStat` is the follower's own; `level` its level (the attackers' too). A swing is the
    // weapon's range plus the sheet's flat damage, times one plus the main stat a hundredth (damage_formula.csv steps 1
    // and 2); its period is the sheet's attacks per second.
    inline CreaturePlan Plan(StatSheet const& sheet, Stat mainStat, unsigned level, Weapon const& weapon)
    {
        CreaturePlan plan;
        plan.maxHealth = std::uint32_t(std::clamp(sheet.maxLife, 1.0, 4294967295.0));
        plan.armor = CoreValue(sheet.armorDR, CoreArmorConstant(level));
        // The sheet's reduction caps are the core's: the same 0.75.
        for (unsigned element = 1; element < ElementCount; ++element)
            plan.resistance[SchoolOfElement[element]] =
                CoreValue(sheet.resistanceDR[element], CoreResistConstant(level));
        if (weapon.present && weapon.max > 0)
        {
            double const flatLow = sheet[Stat::WeaponFlatDamage];
            double const flatHigh = flatLow + sheet[Stat::WeaponFlatDamageDelta];
            double const main = 1.0 + sheet[mainStat] / 100.0;
            plan.swings = true;
            plan.swingMin = (weapon.min + flatLow) * main;
            plan.swingMax = (weapon.max + flatHigh) * main;
            double const aps = sheet.attacksPerSecond > 0 ? sheet.attacksPerSecond : 1000.0 / weapon.delayMs;
            plan.attackTimeMs = std::uint32_t(std::lround(1000.0 / aps));
        }
        return plan;
    }

    // The core weapon damage that makes one swing of `swing`: a creature's melee is the weapon range times its attack
    // time in seconds (Unit::GetAPMultiplier), with no attack power or flat bonus behind it.
    inline double CoreWeaponDamage(double swing, std::uint32_t attackTimeMs)
    {
        return attackTimeMs ? swing * 1000.0 / attackTimeMs : swing;
    }

    // The relic powers (data/d3/followers.csv power).
    inline constexpr std::string_view PowerCannotDie = "cannot_die";
    inline constexpr std::string_view PowerAllSkills = "all_skills";
    inline constexpr std::string_view PowerCooldownHalf = "cooldown_half";

    // Damage a follower takes: none while a worn relic keeps it from dying (Enchanting Favor: it loses no Life).
    constexpr std::uint32_t Taken(bool cannotDie, std::uint32_t damage)
    {
        return cannotDie ? 0 : damage;
    }

    // What deleting a character leaves behind. The core deletes the character's item_instance rows by owner, parked
    // ones included, but the dc_ rows of an item follow it only through Item::DeleteFromDB, and a worn item has no
    // character_inventory row to be reached by. So its rolled rows (the tables Items::Erase clears) are found through
    // the gear row, which therefore goes last.
    inline std::vector<std::string> DeleteCharacterSql(std::uint32_t character)
    {
        std::vector<std::string> out;
        for (std::string_view table :
             {"dc_item_affix", "dc_item_instance", "dc_enchant_offer", "dc_item_unidentified", "dc_legendary_gem_rank"})
            out.push_back("DELETE d FROM " + std::string(table) +
                          " d JOIN dc_character_follower_gear g ON g.item_guid=d.item_guid WHERE g.guid=" +
                          std::to_string(character));
        out.push_back("DELETE FROM dc_character_follower_gear WHERE guid=" + std::to_string(character));
        return out;
    }
} // namespace DC::Items::FollowerGear

#endif
