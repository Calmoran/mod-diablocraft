/*
 * World of DiabloCraft - the Mystic's enchant rules (the D3 way;
 * docs/research/mystic-enchant.md).
 *
 * Pure functions only, so scripts/tests/crafting/enchant_rule_tests.cpp compiles this exact header
 * against the generated pool and the generated price table. Nothing here reads a database or a
 * player: dc_items_enchant.cpp (which line may become what) and dc_mystic.cpp (what a roll costs)
 * supply the data and the draws, and the tests supply theirs.
 *
 * Who may be enchanted, what a roll costs, which affixes a line may become, and which lines
 * the window may list. The numbers are data: the price table is D3's own
 * (x1_EnchantItemAffixUseCountCostScalars, data/d3/mystic_cost_scalars.csv), the base gold is
 * the tunable mystic_base_gold, and the pool brackets are affix_pools.csv.
 */

#ifndef DC_ENCHANT_RULE_H
#define DC_ENCHANT_RULE_H

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <set>
#include <string>
#include <utility>
#include <vector>

namespace DC::Enchant
{
    // Rare, legendary and set items. Normal and magic cannot be enchanted (research 2.1).
    inline bool Eligible(std::string const& rarity)
    {
        return rarity == "rare" || rarity == "legendary" || rarity == "set";
    }

    // One breakpoint of D3's price table: at the count-th paid roll the base is multiplied by
    // tenths / 10. Between breakpoints the scalar is a straight line (research 10.1).
    struct Scalar
    {
        unsigned count = 0, tenths = 0;
    };

    // Gold for paid roll number `roll` (1 is the first): floor(base * scalar(roll)), in whole gold.
    // The scalar is kept as tenths over the segment length so the only rounding is the final
    // division; a whole base gives an exact result. nullopt for a roll outside the table, a table
    // that is too short or not strictly increasing, or a base that is not a finite non-negative
    // number: the caller refuses the enchant rather than inventing a price.
    inline std::optional<std::uint64_t> Price(double base, unsigned roll, std::vector<Scalar> const& table)
    {
        if (!std::isfinite(base) || base < 0 || table.size() < 2 || roll < table.front().count ||
            roll > table.back().count)
            return std::nullopt;
        for (std::size_t i = 1; i < table.size(); ++i)
        {
            Scalar const& a = table[i - 1];
            Scalar const& b = table[i];
            if (b.count <= a.count || b.tenths < a.tenths)
                return std::nullopt;
            if (roll > b.count)
                continue;
            long long const span = b.count - a.count;
            long long const scaled = static_cast<long long>(a.tenths) * span +
                                     (static_cast<long long>(b.tenths) - a.tenths) * (roll - a.count);
            double const gold = std::floor(base * static_cast<double>(scaled) / (10.0 * static_cast<double>(span)));
            if (!std::isfinite(gold) || gold >= 18446744073709551615.0)
                return std::nullopt;
            return static_cast<std::uint64_t>(gold);
        }
        return std::nullopt;
    }

    // D3's mutually exclusive groups (reference/d3planner/data_stats.js statGroups, pinned in the
    // research 3.1), for the ids our items carry: an item holds one member of each. The main
    // attribute and the skill bonuses are groups already, because the caller names them by
    // their pool id (mainstat, skill_<slot>); everything else is its own group.
    inline std::string Exclusion(std::string const& poolId)
    {
        struct Member
        {
            char const* id;
            char const* group;
        };
        static Member const members[] = {
            {"wpnphy", "weapon"},       {"wpnfir", "weapon"},      {"wpncol", "weapon"},    {"wpnpsn", "weapon"},
            {"wpnarc", "weapon"},       {"wpnlit", "weapon"},      {"wpnhol", "weapon"},    {"dmgphy", "elemental"},
            {"dmgfir", "elemental"},    {"dmgcol", "elemental"},   {"dmgpsn", "elemental"}, {"dmgarc", "elemental"},
            {"dmglit", "elemental"},    {"dmghol", "elemental"},   {"resall", "resistany"}, {"resist", "resistany"},
            {"resphy", "resistany"},    {"resfir", "resistany"},   {"rescol", "resistany"}, {"respsn", "resistany"},
            {"resarc", "resistany"},    {"reslit", "resistany"},   {"hitfear", "onhit"},    {"hitstun", "onhit"},
            {"hitblind", "onhit"},      {"hitfreeze", "onhit"},    {"hitchill", "onhit"},   {"hitslow", "onhit"},
            {"hitimmobilize", "onhit"}, {"hitknockback", "onhit"}, {"lph", "lifeper"},      {"laek", "lifeper"},
        };
        for (Member const& member : members)
            if (poolId == member.id)
                return member.group;
        return poolId;
    }

    // One entry of the item's slot pool, in the slot's display order. weaponClass names the
    // damage bracket of a two-part weapon damage row and is empty for every other affix.
    struct Cand
    {
        std::string id, kind;
        double min = 0, max = 0, min2 = 0, max2 = 0, step = 0;
        std::string weaponClass;
        unsigned order = 0;
    };

    // One affix row of the item. kind is the row's own: primary, secondary, preset, socket or gem.
    struct Row
    {
        unsigned seq = 0;
        std::string id, kind;
        bool rerolled = false;
    };

    // A line or a choice as the window draws it: the property, the pool it rolls in, and the roll.
    // value2 and min2/max2 are 0 except on a two-part damage line, whose two parts both belong to it.
    struct Pick
    {
        unsigned seq = 0;
        std::string id, kind;
        double value = 0, value2 = 0, min = 0, max = 0, min2 = 0, max2 = 0;
    };

    // What a line can be: the window greys a line it cannot replace and says why.
    enum class State
    {
        Open = 0,      // can be replaced
        Enchanted = 1, // the one the item is locked to; can be replaced again
        Gems = 2,      // the sockets hold gems
        Nothing = 3,   // fewer than two things it could become
    };

    struct Line
    {
        Pick pick;
        State state = State::Open;
        unsigned order = 0;
    };

    // Ctx is what only the caller knows (class, base item, the draw). It must provide:
    //   std::string PoolId(std::string const& rowId)   the pool id a row belongs to: str/dex/int are
    //                                                  "mainstat", a skill choice is its group id
    //   std::vector<Cand> Expand(Cand const&)          what a pool entry rolls as for this player and
    //                                                  item: mainstat -> the class's attribute, a skill
    //                                                  group -> that class's skills, anything the item
    //                                                  cannot carry (a shield line on a quiver, a group
    //                                                  with no skill for the class) -> empty
    //   void Shuffle(std::vector<Cand>&)               the draw
    //   std::size_t Index(std::size_t count)           a draw in [0, count)
    //   std::pair<double,double> Value(Cand const&)    a fresh roll: value, and value2 on a damage row
    //   std::string WeaponClass()                      the item's own damage bracket, "" for a non-weapon

    // The pool entries `target` may be replaced by, in pool order: the same kind (primary or
    // secondary) as the line being replaced, nothing from a group another line of the item already
    // holds, and the line's own affix is allowed (a fresh value). The weapon damage line is the
    // exception on both sides: it only ever becomes a damage row of the weapon's own
    // bracket, and no other line ever becomes one. Entries the caller cannot roll are dropped.
    template<class Ctx>
    std::vector<Cand> Replacements(std::vector<Cand> const& pool, Row const& target, std::vector<Row> const& rows,
                                   Ctx& ctx)
    {
        std::string const ownId = ctx.PoolId(target.id);
        auto own = std::find_if(pool.begin(), pool.end(), [&](Cand const& c) { return c.id == ownId; });
        if (own == pool.end())
            return {};
        bool const damage = !own->weaponClass.empty();
        std::string const weaponClass = ctx.WeaponClass();
        std::set<std::string> used;
        for (Row const& row : rows)
        {
            if (row.seq == target.seq || row.kind == "gem" || (target.kind == "socket" && row.kind == "socket"))
                continue;
            used.insert(Exclusion(ctx.PoolId(row.id)));
        }
        std::vector<Cand> out;
        for (Cand const& c : pool)
        {
            if (c.kind != own->kind || c.weaponClass.empty() == damage || (damage && c.weaponClass != weaponClass))
                continue;
            if (used.count(Exclusion(c.id)) || ctx.Expand(c).empty())
                continue;
            out.push_back(c);
        }
        return out;
    }

    // The two new choices: two different pool entries drawn from Replacements, each rolled fresh
    // (a damage row rolls its own two parts). Empty when fewer than two exist.
    template<class Ctx>
    std::vector<Pick> NewChoices(std::vector<Cand> const& pool, Row const& target, std::vector<Row> const& rows,
                                 Ctx& ctx)
    {
        std::vector<Cand> eligible = Replacements(pool, target, rows, ctx);
        ctx.Shuffle(eligible);
        std::vector<Pick> out;
        for (Cand const& c : eligible)
        {
            std::vector<Cand> options = ctx.Expand(c);
            Cand const& rolled = options[ctx.Index(options.size())];
            auto [value, value2] = ctx.Value(rolled);
            Pick pick;
            pick.seq = target.seq;
            pick.id = rolled.id;
            pick.kind = rolled.id == "sockets" ? "socket" : rolled.kind;
            pick.value = value;
            pick.value2 = value2;
            pick.min = rolled.min;
            pick.max = rolled.max;
            pick.min2 = rolled.min2;
            pick.max2 = rolled.max2;
            out.push_back(pick);
            if (out.size() == 2)
                return out;
        }
        return {};
    }

    // What `?` shows: every entry the line can become, with the range it would roll in.
    template<class Ctx>
    std::vector<Pick> Preview(std::vector<Cand> const& pool, Row const& target, std::vector<Row> const& rows, Ctx& ctx)
    {
        std::vector<Pick> out;
        for (Cand const& c : Replacements(pool, target, rows, ctx))
            for (Cand const& e : ctx.Expand(c))
            {
                Pick pick;
                pick.seq = target.seq;
                pick.id = e.id;
                pick.kind = e.id == "sockets" ? "socket" : e.kind;
                pick.min = e.min;
                pick.max = e.max;
                pick.min2 = e.min2;
                pick.max2 = e.max2;
                out.push_back(pick);
            }
        return out;
    }

    // The three choices a paid roll shows: the line as it is on the item now FIRST (the current value is
    // always the first of the three), then the two rolls stored with the roll. `lines` are the item's lines as
    // listed, `seq` the line the roll was paid on and `socket` whether that was the sockets, whose one line any
    // socket row's seq stands for. nullopt when the line is no longer on the item.
    inline std::optional<std::vector<Pick>> Waiting(std::vector<Pick> const& lines, unsigned seq, bool socket,
                                                    std::vector<Pick> const& stored)
    {
        auto current = std::find_if(lines.begin(), lines.end(),
                                    [&](Pick const& p) { return p.seq == seq || (socket && p.kind == "socket"); });
        if (current == lines.end())
            return std::nullopt;
        std::vector<Pick> out{*current};
        out.insert(out.end(), stored.begin(), stored.end());
        return out;
    }

    // The lines the window lists for an item. `values` carries each row's stored roll, keyed by seq
    // (the caller reads them from the item); `locked` is the item's enchant lock. A locked item lists only
    // the enchanted line. The sockets are one line, at the first socket's seq. Rows the pool does not
    // know (a legendary power, a preset outside the slot's pool) and gems are never listed. Sorted the
    // way the tooltip is: primary pool, secondary pool, sockets, by the pool's display order.
    template<class Ctx>
    std::vector<Line> Lines(std::vector<Cand> const& pool, std::vector<Row> const& rows,
                            std::vector<Pick> const& values, bool locked, Ctx& ctx)
    {
        std::vector<Line> out;
        bool socketsListed = false;
        bool gems = std::any_of(rows.begin(), rows.end(), [](Row const& r) { return r.kind == "gem"; });
        for (Row const& row : rows)
        {
            if (row.kind == "gem" || (row.kind == "socket" && socketsListed))
                continue;
            std::string const poolId = ctx.PoolId(row.id);
            auto entry = std::find_if(pool.begin(), pool.end(), [&](Cand const& c) { return c.id == poolId; });
            if (entry == pool.end())
                continue;
            // The sockets' one line: the first socket's seq, its count as the value.
            bool const sockets = row.kind == "socket";
            bool enchanted = row.rerolled;
            if (sockets)
            {
                socketsListed = true;
                for (Row const& other : rows)
                    enchanted = enchanted || (other.kind == "socket" && other.rerolled);
            }
            if (locked && !enchanted)
                continue;
            auto stored = std::find_if(values.begin(), values.end(), [&](Pick const& p) { return p.seq == row.seq; });
            if (stored == values.end())
                continue;
            Line line;
            line.pick = *stored;
            line.pick.kind = sockets ? "socket" : entry->kind;
            line.order = entry->order;
            if (sockets)
            {
                line.pick.value = static_cast<double>(
                    std::count_if(rows.begin(), rows.end(), [](Row const& r) { return r.kind == "socket"; }));
                line.pick.value2 = 0;
            }
            if (sockets && gems)
                line.state = State::Gems;
            else if (Replacements(pool, row, rows, ctx).size() < 2)
                line.state = State::Nothing;
            else
                line.state = enchanted ? State::Enchanted : State::Open;
            out.push_back(line);
        }
        auto rank = [](Line const& l) { return l.pick.kind == "socket" ? 3 : l.pick.kind == "secondary" ? 2 : 1; };
        std::stable_sort(out.begin(), out.end(), [&](Line const& a, Line const& b)
                         { return rank(a) != rank(b) ? rank(a) < rank(b) : a.order < b.order; });
        return out;
    }
} // namespace DC::Enchant

#endif // DC_ENCHANT_RULE_H
