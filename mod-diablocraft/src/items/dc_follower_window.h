/*
 * World of DiabloCraft - the Follower window's records (contract docs/contracts/followers.md "Messages"), as pure text.
 *
 * Everything the window draws about one follower arrives as the records this builds from a View: the header, the four
 * attributes with Damage and Toughness, the Details rows, the 14 gear slots and the four skill tiers. The window reads
 * these and computes nothing. No core header, so tests/follower_window/harness.cpp compiles this file itself and
 * scripts/tests/items/test_follower_window.py checks the text against the contract.
 */

#ifndef DC_FOLLOWER_WINDOW_H
#define DC_FOLLOWER_WINDOW_H

#include "../common/dc_common.h"
#include "../stats/dc_sheet_summary.h"
#include "dc_follower_gear_rule.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace DC::Items::FollowerGear::Window
{
    struct SlotRow
    {
        std::uint32_t entry = 0;
        std::uint64_t guid = 0;
        bool usable = false;
    };

    struct TierRow
    {
        unsigned level = 0;
        std::string pick; // the picked skill's skill_id (data/d3/followers.csv), empty when none
    };

    // What the window shows of one follower. `sheet`, `mainStat` and `summary` are the follower's own; `allSkills` is
    // the worn relic's all_skills power.
    struct View
    {
        unsigned follower = 0;
        bool hired = false;
        bool hub = false;
        unsigned level = 1;
        StatSheet sheet;
        Stat mainStat = Stat::Strength;
        DC::Stats::Summary summary;
        std::array<SlotRow, SlotCount> slots;
        std::vector<TierRow> tiers;
        bool allSkills = false;
    };

    using Record = std::vector<std::string>;

    // Hiring is a talk option on the follower's NPC in the hub, so the window's `hire` request is refused with this;
    // the window keeps gear, skills and dismiss. Empty for every other request.
    constexpr std::string_view HireRefusal = "Talk to the follower in the hub to hire them.";

    constexpr std::string_view Refusal(std::string_view verb)
    {
        return verb == "hire" ? HireRefusal : std::string_view();
    }

    // Value shapes of a Details row: a whole number, two decimals, two decimals and a percent sign; the digits before
    // the point in groups of three. A value that rounds to zero prints as zero, never as a negative zero.
    inline std::string Grouped(std::string const& digits)
    {
        std::string out;
        int count = 0;
        for (auto it = digits.rbegin(); it != digits.rend(); ++it)
        {
            if (count && count % 3 == 0)
                out.insert(out.begin(), ',');
            out.insert(out.begin(), *it);
            ++count;
        }
        return out;
    }

    inline std::string Fixed(double value, int decimals)
    {
        double const scale = std::pow(10.0, decimals);
        double const rounded = std::round(std::fabs(value) * scale) / scale;
        bool const negative = value < 0 && rounded > 0;
        auto const whole = static_cast<std::uint64_t>(std::floor(rounded));
        std::string text = Grouped(std::to_string(whole));
        if (decimals)
        {
            auto const fraction = static_cast<std::uint64_t>(std::llround((rounded - double(whole)) * scale));
            std::string const tail = std::to_string(fraction);
            text += "." + std::string(std::size_t(decimals) - tail.size(), '0') + tail;
        }
        return negative ? "-" + text : text;
    }

    inline std::string Int(double value)
    {
        return Fixed(value, 0);
    }
    inline std::string Num(double value)
    {
        return Fixed(value, 2);
    }
    inline std::string Pct(double value)
    {
        return Fixed(value, 2) + "%";
    }

    // The whole number a record carries ungrouped (A's attributes, Damage and Toughness).
    inline std::string Whole(double value)
    {
        return std::to_string(static_cast<std::uint64_t>(std::llround(std::max(0.0, value))));
    }

    inline std::string_view MainStatWord(Stat stat)
    {
        if (stat == Stat::Dexterity)
            return "Dexterity";
        if (stat == Stat::Intelligence)
            return "Intelligence";
        return "Strength";
    }

    // The Details rows of a sheet, in display order: group, label, value. Dodge Chance and Life Steal exist on no sheet
    // yet, so they read zero.
    inline std::vector<Record> Details(View const& view)
    {
        StatSheet const& sheet = view.sheet;
        std::vector<Record> rows;
        auto add = [&](char const* group, std::string label, std::string value)
        { rows.push_back({group, std::move(label), std::move(value)}); };
        add("offense", "Damage Increased by " + std::string(MainStatWord(view.mainStat)), Pct(sheet[view.mainStat]));
        add("offense", "Attacks per Second", Num(sheet.attacksPerSecond));
        add("offense", "Critical Hit Chance", Pct(sheet[Stat::CritChance]));
        add("offense", "Critical Hit Damage", Pct(sheet[Stat::CritDamage]));
        add("defense", "Armor", Int(sheet[Stat::Armor]));
        add("defense", "Block Amount", Int(sheet[Stat::BlockAmountMin]) + "-" + Int(sheet[Stat::BlockAmountMax]));
        add("defense", "Block Chance", Pct(sheet[Stat::BlockChance]));
        add("defense", "Dodge Chance", Pct(0));
        add("defense", "Damage Reduction", Pct(sheet.armorDR * 100));
        for (auto const& [label, element] : {std::pair<char const*, Element>{"Physical", Element::Physical},
                                             {"Fire", Element::Fire},
                                             {"Cold", Element::Cold},
                                             {"Lightning", Element::Lightning},
                                             {"Poison", Element::Poison}})
            add("defense", std::string(label) + " Resistance", Int(sheet.resistance[Index(element)]));
        add("defense", "Arcane/Holy Resistance",
            Int((sheet.resistance[Index(Element::Arcane)] + sheet.resistance[Index(Element::Holy)]) / 2));
        add("life", "Maximum Life", Int(sheet.maxLife));
        add("life", "Life per Second", Num(sheet[Stat::LifeRegen]));
        add("life", "Life Steal", Pct(0));
        add("life", "Life per Kill", Int(sheet[Stat::LifePerKill]));
        add("life", "Life per Hit", Int(sheet[Stat::LifePerHit]));
        add("adventure", "Gold Find", Pct(sheet[Stat::GoldFind]));
        add("adventure", "Magic Find", Pct(sheet[Stat::MagicFind]));
        return rows;
    }

    // The records of an open, in the contract's order: W, A, every D, every G, every K, E.
    inline std::vector<Record> Records(View const& view)
    {
        std::vector<Record> out;
        out.push_back({"W", std::to_string(view.follower), view.hired ? "1" : "0", view.hub ? "1" : "0",
                       std::to_string(view.level)});
        out.push_back({"A", Whole(view.sheet[Stat::Strength]), Whole(view.sheet[Stat::Dexterity]),
                       Whole(view.sheet[Stat::Intelligence]), Whole(view.sheet[Stat::Vitality]),
                       Whole(view.summary.damage), Whole(view.summary.toughness)});
        for (Record& row : Details(view))
        {
            row.insert(row.begin(), "D");
            out.push_back(std::move(row));
        }
        for (unsigned index = 0; index < SlotCount; ++index)
        {
            SlotRow const& slot = view.slots[index];
            out.push_back({"G", std::string(SlotKeys[index]), std::to_string(slot.entry), std::to_string(slot.guid),
                           slot.usable ? "1" : "0"});
        }
        for (std::size_t tier = 0; tier < view.tiers.size(); ++tier)
            out.push_back({"K", std::to_string(tier + 1), std::to_string(view.tiers[tier].level),
                           view.tiers[tier].pick, view.allSkills ? "1" : "0"});
        out.push_back({"E"});
        return out;
    }
} // namespace DC::Items::FollowerGear::Window

#endif
