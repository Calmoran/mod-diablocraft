#pragma once
/*
 * Pylons and shrines P1 (docs/proposals/pylons.md 4.3): which kinds there are, what each puts on the
 * stat sheet while it is worn, and the names of the tunable rows every number comes from. Pure arithmetic and tables,
 * so scripts/tests/rifts/test_pylon_buffs.py compiles this header and drives it with the numbers parsed out of the tunables sheet.
 * P3 adds the objects' entries and the click's share and one use (scripts/tests/rifts/test_pylon_objects.py).
 * P2 adds Conduit's pick and Greater Rift strike and Speed's knock-up test
 * (scripts/tests/rifts/test_pylon_conduit_speed.py).
 *
 * A kind's number is a row of data/tunables/combat.csv named `pylon_<kind>_<what>` or `shrine_<kind>_<what>`; the buff
 * record's text is baked from the same row (data/pylon_buffs.csv, generate_spells.py).
 */
#include "../common/dc_common.h"
#include "dc_damage_buckets.h"

#include <cstdint>
#include <iterator>
#include <map>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace DC::Combat::Pylons
{
    // The order is data/pylon_buffs.csv's; the five pylons come first.
    enum class Kind : unsigned
    {
        Power,
        Conduit,
        Channeling,
        Shield,
        Speed,
        Blessed,
        Empowered,
        Enlightened,
        Fleeting,
        Fortune,
        Frenzied,
        Count
    };
    inline constexpr unsigned KindCount = static_cast<unsigned>(Kind::Count);
    inline constexpr char const* Names[KindCount] = {"power",    "conduit", "channeling", "shield",
                                                     "speed",    "blessed", "empowered",  "enlightened",
                                                     "fleeting", "fortune", "frenzied"};

    inline constexpr bool IsPylon(Kind kind)
    {
        return static_cast<unsigned>(kind) <= static_cast<unsigned>(Kind::Speed);
    }

    // N-PYLON (Ahavarion): the kinds a shrine gives, the kinds that are not pylons, in Kind order. A random shrine effect is one of
    // them, `roll` in [0, 1) choosing evenly (1 or more takes the last).
    inline constexpr unsigned ShrineFirst = [] {
        unsigned first = 0;
        while (first < KindCount && IsPylon(static_cast<Kind>(first)))
            ++first;
        return first;
    }();
    inline constexpr unsigned ShrineCount = KindCount - ShrineFirst;
    inline Kind RandomShrine(double roll)
    {
        unsigned const at = roll > 0 ? static_cast<unsigned>(roll * ShrineCount) : 0;
        return static_cast<Kind>(ShrineFirst + (at < ShrineCount ? at : ShrineCount - 1));
    }

    inline std::optional<Kind> Parse(std::string_view name)
    {
        for (unsigned i = 0; i < KindCount; ++i)
        {
            std::string_view const candidate = Names[i];
            if (candidate.size() != name.size())
                continue;
            bool same = true;
            for (std::size_t j = 0; j < name.size(); ++j)
                same = same && (name[j] | 0x20) == candidate[j];
            if (same)
                return static_cast<Kind>(i);
        }
        return std::nullopt;
    }

    // The tunable row of one number of a kind: pylon_power_damage_pct, shrine_blessed_seconds...
    inline std::string Row(Kind kind, char const* what)
    {
        return std::string(IsPylon(kind) ? "pylon_" : "shrine_") + Names[static_cast<unsigned>(kind)] + "_" + what;
    }

    // What a kind puts on the sheet while it is worn (a Temporary contribution of its own id). Power's factor,
    // Enlightened's XP, Empowered's regeneration (the record's own aura) and Shield's immunity are not sheet stats.
    struct StatRow
    {
        Kind kind;
        Stat stat;
        Bucket bucket;
        char const* what;
    };
    inline constexpr StatRow StatRows[] = {
        {Kind::Channeling, Stat::CooldownReduction, Bucket::Flat, "cooldown_reduction_pct"},
        {Kind::Channeling, Stat::ResourceCostReduction, Bucket::Flat, "cost_reduction_pct"},
        {Kind::Speed, Stat::MovementSpeed, Bucket::Uncapped, "movement_pct"},
        {Kind::Speed, Stat::AttackSpeed, Bucket::Flat, "attack_speed_pct"},
        {Kind::Blessed, Stat::SpecificReduction, Bucket::Flat, "damage_taken_pct"},
        {Kind::Empowered, Stat::CooldownReduction, Bucket::Flat, "cooldown_reduction_pct"},
        {Kind::Fleeting, Stat::MovementSpeed, Bucket::Uncapped, "movement_pct"},
        {Kind::Fortune, Stat::MagicFind, Bucket::Flat, "magic_find_pct"},
        {Kind::Fortune, Stat::GoldFind, Bucket::Flat, "gold_find_pct"},
        {Kind::Frenzied, Stat::AttackSpeed, Bucket::Flat, "attack_speed_pct"},
    };

    // The sheet contributions of `kind` under the buff record `id`; `get` reads a tunable row by name.
    template<class Get>
    std::vector<Contribution> Contributions(Kind kind, std::uint64_t id, Get&& get)
    {
        std::vector<Contribution> out;
        for (StatRow const& row : StatRows)
            if (row.kind == kind)
                out.push_back(
                    {Source::Temporary, row.stat, id, get(Row(kind, row.what)), row.bucket, Element::Physical});
        return out;
    }

    // A buff is in force while the player lives and wears the record: a pylon's record persists through death (6.11)
    // but does nothing then, a shrine's is taken off by the core.
    inline constexpr bool Active(bool alive, bool wearing)
    {
        return alive && wearing;
    }

    // Does a kind change what the class's own cost and cooldown auras must charge? (RefreshModifiers rebuilds them.)
    inline bool TouchesModifiers(Kind kind)
    {
        for (StatRow const& row : StatRows)
            if (row.kind == kind && (row.stat == Stat::CooldownReduction || row.stat == Stat::ResourceCostReduction))
                return true;
        return false;
    }

    // P3 (pylons.md 4.2): the objects. One gameobject template per kind, stock type 22, its entry
    // the first below plus the kind's index (generate_pylon_objects.py writes them; docs/contracts/pylon-messages.md
    // names them for P4 and P5). Identities, not game numbers.
    inline constexpr std::uint32_t ObjectEntryFirst = 910120;
    inline constexpr std::uint32_t ObjectEntry(Kind kind)
    {
        return ObjectEntryFirst + static_cast<unsigned>(kind);
    }
    inline std::optional<Kind> KindOfObject(std::uint32_t entry)
    {
        if (entry < ObjectEntryFirst || entry >= ObjectEntryFirst + KindCount)
            return std::nullopt;
        return static_cast<Kind>(entry - ObjectEntryFirst);
    }
    // A pylon's object, never a shrine's (Greater Rift rule 3's exception, P4).
    inline bool IsPylonObject(std::uint32_t entry)
    {
        std::optional<Kind> const kind = KindOfObject(entry);
        return kind && IsPylon(*kind);
    }

    // 6.4: a pylon reaches every party member on the clicker's floor, a shrine only those on it within `radius` yards
    // of the clicker.
    inline bool Reaches(Kind kind, bool sameFloor, double yards, double radius)
    {
        return sameFloor && (IsPylon(kind) || yards <= radius);
    }

    // The click: one use. `spent` is the object's own mark, so a second click before the core takes the object away
    // gives nothing (nullopt). `members` is the clicker and its party; `floor(m)`, `yards(m)` and `give(m)` ask the
    // game whether m is on the clicker's floor, how far from the clicker, and put the buff on. Returns how many got it.
    template<class Member, class Floor, class Yards, class Give>
    std::optional<unsigned> Spend(bool& spent, Kind kind, double radius, std::vector<Member> const& members,
                                  Floor&& floor, Yards&& yards, Give&& give)
    {
        if (spent)
            return std::nullopt;
        spent = true;
        unsigned given = 0;
        for (Member const& member : members)
        {
            bool const on = floor(member); // the distance is asked only of a member on the clicker's map
            if (Reaches(kind, on, on ? yards(member) : 0.0, radius) && give(member))
                ++given;
        }
        return given;
    }

    // Power's separate multiplier in step 8 of the hit (`pct` its row), none while it is not in force.
    inline void PowerFactor(bool active, double pct, Factors& out)
    {
        if (active)
            AddFactor(out, "Dimensional Power", pct);
    }

    // Reconcile's sheet work: the kinds in force went from `before` to `now` (bit i is Kind i). Each kind that came or
    // went has its rows taken off and, if it is in force now, put back from `get`; before the first call after login
    // (`known` false) every kind is settled, so a saved sheet keeps nothing the player no longer wears. `record(kind)`
    // is the kind's buff record id, `remove(stat, id)` and `add(contribution)` the sheet's own calls. Returns whether a
    // kind that came or went changes the class's cost or cooldown auras.
    template<class Record, class Get, class Remove, class Add>
    bool Settle(bool known, unsigned before, unsigned now, Record&& record, Get&& get, Remove&& remove, Add&& add)
    {
        unsigned const changed = known ? (now ^ before) : ((1u << KindCount) - 1);
        bool modifiers = false;
        for (unsigned i = 0; i < KindCount; ++i)
        {
            if (!(changed & (1u << i)))
                continue;
            Kind const kind = static_cast<Kind>(i);
            std::uint64_t const id = record(kind);
            for (StatRow const& row : StatRows)
                if (row.kind == kind)
                    remove(row.stat, id);
            if (now & (1u << i))
                for (Contribution const& contribution : Contributions(kind, id, get))
                    add(contribution);
            modifiers = modifiers || TouchesModifiers(kind);
        }
        return modifiers;
    }
    // P2 (pylons.md 6.10): which of the monsters a Conduit pulse finds it strikes. `near` is the
    // pulse's list in its order; `last` is this wearer's last strike time (ms) per monster. A monster struck less than
    // `rehitMs` ago is passed over, and at most `cap` are struck; the ones chosen get `now`. Entries older than the
    // window are dropped, so the map holds only the last few seconds' monsters. Returns the indices into `near`.
    template<class Key>
    std::vector<std::size_t> ConduitPick(std::vector<Key> const& near, std::map<Key, std::uint32_t>& last,
                                         std::uint32_t now, double rehitMs, double cap)
    {
        for (auto entry = last.begin(); entry != last.end();)
            entry = double(std::uint32_t(now - entry->second)) >= rehitMs ? last.erase(entry) : std::next(entry);
        std::vector<std::size_t> picked;
        for (std::size_t i = 0; i < near.size() && double(picked.size()) < cap; ++i)
            if (last.emplace(near[i], now).second)
                picked.push_back(i);
        return picked;
    }

    // 6.10 (a), in a Greater Rift: a strike takes a share of the Life the struck monster has as a normal monster at the
    // run's level (its true Life over its elite Life factor), the share rolled between `minPct` and `maxPct` (`roll` in
    // [0, 1]). Nothing of the wearer's gear is an input.
    inline double GreaterStrike(double trueLife, double eliteFactor, double minPct, double maxPct, double roll)
    {
        double const normal = eliteFactor > 0 ? trueLife / eliteFactor : trueLife;
        return normal * (minPct + roll * (maxPct - minPct)) / 100.0;
    }

    // 6.10: what a strike deals: the skill hit (`skillHit`) outside a Greater Rift, GreaterStrike's share in one; in
    // both kinds of rift a Guardian or a boss takes it times `bossFactor` (D2: less to bosses and Guardians).
    inline double ConduitDamage(bool greater, double skillHit, double greaterShare, bool boss, double bossFactor)
    {
        return (greater ? greaterShare : skillHit) * (boss ? bossFactor : 1.0);
    }

    // 6.9 (a): Speed's knock-up throws a monster the wearer runs into: only while the wearer moves, never a Rift
    // Guardian, never a rooted monster (the stock knockback also spares bosses, giants and the knockback-immune).
    inline constexpr bool KnocksUp(bool moving, bool guardian, bool rooted)
    {
        return moving && !guardian && !rooted;
    }
} // namespace DC::Combat::Pylons
