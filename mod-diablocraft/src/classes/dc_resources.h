#pragma once
// The class resource helper. Every module read
// or write of a class resource goes through here, keyed by class and resource:
// the registry row (dc_resource_data.h, generated from class_resources.csv)
// says which WoW power slot holds it and how many slot units one point is, so
// no caller names POWER_RAGE, POWER_MANA or a x10.
//
// Two write paths, because the callers used two and behaviour must not move:
// Add() is the clamped SetPower the Fury gains always used, Modify() is the
// core's Unit::ModifyPower (no write when nothing changes, AI notified).
#include "dc_resource_carry.h"
#include "dc_resource_data.h"
#include "Player.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <map>
#include <mutex>
#include <utility>

namespace DC::Resources
{
    using Resource = Data::Row;

    using Data::Find;

    // A class's primary (or second) resource by class_map.csv's class_id.
    inline Resource const* Of(std::uint32_t classId, Data::Role role = Data::Role::Primary)
    {
        for (Resource const& row : Data::Rows)
            if (row.classId == classId && row.role == role)
                return &row;
        return nullptr;
    }

    // The resources the module's class code names. A missing row is a compile
    // error, not a runtime surprise: dereferencing a null constant expression
    // is not a constant expression.
    inline constexpr Resource const& Fury = *Find("Barbarian", "fury");
    inline constexpr Resource const& ArcanePower = *Find("Wizard", "arcane_power");
    inline constexpr Resource const& Spirit = *Find("Monk", "spirit");
    inline constexpr Resource const& Hatred = *Find("Demon Hunter", "hatred");
    inline constexpr Resource const& Discipline = *Find("Demon Hunter", "discipline");
    inline constexpr Resource const& Mana = *Find("Witch Doctor", "mana");
    inline constexpr Resource const& Maelstrom = *Find("Shaman", "maelstrom");

    // True for the Mana slot of a class none of whose resources lives there.
    // The stock client draws a second Mana bar whenever Mana is not the shown
    // power and its maximum is not 0 (FrameXML AlternatePowerBar.lua:61-66),
    // so such a class keeps a Mana maximum of 0 (a Wizard on Energy has no
    // Mana bar; a Witch Doctor's Mana keeps it).
    inline bool ZeroMaximum(std::uint32_t classId, Powers slot)
    {
        if (slot != POWER_MANA)
            return false;
        for (Resource const& row : Data::Rows)
            if (row.classId == classId && row.power == POWER_MANA)
                return false;
        return true;
    }

    inline Powers Slot(Resource const& r)
    {
        return static_cast<Powers>(r.power);
    }

    // The scale conversion.
    inline double ToUnits(Resource const& r, double points)
    {
        return points * r.scale;
    }
    inline double ToPoints(Resource const& r, double units)
    {
        return units / r.scale;
    }

    using Data::ScaleOf;

    // Raw slot units, for callers that carry fractions of a unit themselves.
    inline std::uint32_t Units(Player const* player, Resource const& r)
    {
        return player->GetPower(Slot(r));
    }
    inline std::uint32_t MaxUnits(Player const* player, Resource const& r)
    {
        return player->GetMaxPower(Slot(r));
    }

    // Points.
    inline double Get(Player const* player, Resource const& r)
    {
        return player->GetPower(Slot(r)) / r.scale;
    }
    inline double Max(Player const* player, Resource const& r)
    {
        return player->GetMaxPower(Slot(r)) / r.scale;
    }

    // Whether the slot is the player's displayed power.
    inline bool Displayed(Player const* player, Resource const& r)
    {
        return player->getPowerType() == Slot(r);
    }

    // A change's part below one slot unit, per player and resource, carried to
    // its next change the same way: at one unit a point a 6.6 gain (a generation
    // bonus, a proc coefficient) pays 6 now and the 0.6 rides on, and a 5.33
    // Whirlwind tick takes 5 and owes 0.33, so changes add up as D3's
    // fractional resource does instead of each rounding. A gain reaching the
    // maximum drops its carry, as the core's own m_powerFraction does
    // (Player::Regenerate). The resource pulse forgets a player at logout.
    struct Owed
    {
        double gain = 0;
        double loss = 0;
    };
    struct Carries
    {
        std::mutex mutex;
        std::map<std::pair<Player const*, Resource const*>, Owed> owed;
    };
    inline Carries& CarryStore()
    {
        static Carries store;
        return store;
    }
    inline void ForgetCarry(Player const* player)
    {
        Carries& store = CarryStore();
        std::lock_guard<std::mutex> guard(store.mutex);
        for (auto it = store.owed.begin(); it != store.owed.end();)
            it = it->first.first == player ? store.owed.erase(it) : std::next(it);
    }

    // The whole units a change of `points` moves now (negative for a loss): its
    // own carry added, the whole units moved and the rest kept (Carry::Whole).
    inline int32 WholeUnits(Player const* player, Resource const& r, double points)
    {
        double const units = ToUnits(r, points);
        if (units == 0)
            return 0;
        Carries& store = CarryStore();
        std::lock_guard<std::mutex> guard(store.mutex);
        Owed& carry = store.owed[{player, &r}];
        double& owed = units > 0 ? carry.gain : carry.loss;
        double const whole = Carry::Whole(owed, std::fabs(units));
        if (units > 0 && player->GetPower(Slot(r)) + whole >= player->GetMaxPower(Slot(r)))
            owed = 0;
        return static_cast<int32>(units > 0 ? whole : -whole);
    }

    // The whole units a cast still owes once the core has charged `charged` units of a cost of `exact`: the part the
    // core dropped (Carry::Dropped) joins the resource's loss carry, so 25 Fury at 30% off takes 17, then 18, 35 for
    // two casts, while every number shown stays the core's.
    inline int32 CostOwed(Player const* player, Resource const& r, double exact, double charged)
    {
        double const dropped = Carry::Dropped(exact, charged);
        return dropped > 0 ? -WholeUnits(player, r, -ToPoints(r, dropped)) : 0;
    }

    // What a source outside the class (the hired Templar's Inspire: "Fury: 10% generated", Spirit and Essence likewise) scales the points a class's
    // skills generate. One function, set once at start, answering 1 for a resource it does not scale. Only a skill's own generation pays through
    // Generated (Energize, by default); a spend, a refund, a regeneration (Flow, the pulse) and a passive's gain (`generated` false) never do.
    using GenerationSource = double (*)(Player const*, Resource const&);
    inline GenerationSource& GenerationSourceOf()
    {
        static GenerationSource source = nullptr;
        return source;
    }

    // `points` of `r` a skill of the player's generates, with the scale on them (a gain only; a loss passes unchanged).
    inline double Generated(Player const* player, Resource const& r, double points)
    {
        GenerationSource const source = GenerationSourceOf();
        double const factor = points > 0 && source && player ? source(player, r) : 1.0;
        return factor > 0 ? points * factor : points;
    }

    // Add (or, negative, take) points, in whole units (WholeUnits) and clamped
    // between 0 and the maximum.
    inline void Add(Player* player, Resource const& r, double points)
    {
        int32 const current = player->GetPower(Slot(r));
        int32 const wanted = current + WholeUnits(player, r, points);
        int32 const cap = static_cast<int32>(player->GetMaxPower(Slot(r)));
        player->SetPower(Slot(r), std::clamp(wanted, 0, cap));
    }

    // The same change through Unit::ModifyPower, in whole units.
    inline void ModifyUnits(Player* player, Resource const& r, int32 units)
    {
        player->ModifyPower(Slot(r), units);
    }
    inline void Modify(Player* player, Resource const& r, double points)
    {
        ModifyUnits(player, r, WholeUnits(player, r, points));
    }

    // Take whole units already paid for (a channel tick that carries its own
    // fraction).
    inline void SpendUnits(Player* player, Resource const& r, int32 units)
    {
        ModifyUnits(player, r, -units);
    }

    inline void SetMax(Player* player, Resource const& r, double points)
    {
        player->SetMaxPower(Slot(r), static_cast<int32>(std::llround(ToUnits(r, points))));
    }

    inline void Empty(Player* player, Resource const& r)
    {
        player->SetPower(Slot(r), 0);
    }

    // Clamp current to the maximum after the maximum moved.
    inline void ClampToMax(Player* player, Resource const& r)
    {
        if (player->GetPower(Slot(r)) > player->GetMaxPower(Slot(r)))
            player->SetPower(Slot(r), player->GetMaxPower(Slot(r)));
    }

    // Maximum Resource from Paragon points spent in it (paragon.csv, by
    // resource): whole points only, so +0.5 per point is +1 per two points
    // and an odd point pays nothing until its pair.
    // The generator allows only whole or half values, so halves are exact.
    inline double ParagonMaximum(Resource const& r, std::uint32_t points)
    {
        std::uint64_t const halves = static_cast<std::uint64_t>(std::llround(r.paragonPerPoint * 2));
        return static_cast<double>(points * halves / 2);
    }

    // A gain through the core's own energize (Unit::EnergizeBySpell): adds,
    // clamps and sends the energize log, in whole units (WholeUnits).
    // A gain is a skill's generation and the scale on it (Generated) applies; `generated` false is anything else (a cost given back, a passive's
    // gain), which no source scales.
    inline void Energize(Player* player, Resource const& r, std::uint32_t spellId, double points, bool generated = true)
    {
        int32 const units = WholeUnits(player, r, generated ? Generated(player, r, points) : points);
        if (units > 0)
            player->EnergizeBySpell(player, spellId, std::uint32_t(units), Slot(r));
    }
} // namespace DC::Resources
