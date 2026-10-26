// Offline harness for diablocraft-xw2m (the Mystic rebuilt the D3 way). It compiles the production
// header src/items/dc_enchant_rule.h - the rules dc_items.cpp and dc_crafting.cpp call - and drives it
// with what the generators emit and with an independent oracle, which scripts/tests/crafting/test_mystic_enchant.py
// extracts into TSV files:
//
//   argv[1] pool.tsv     slot \t bracket \t affix_id \t kind \t min \t max \t min2 \t max2 \t step \t weapon_class \t
//   order
//                        (every row of the generated dc_affix_pool)
//   argv[2] groups.tsv   id \t group   (D3Planner's pinned statGroups, the exclusive groups only)
//   argv[3] scalars.tsv  use_count \t scalar_tenths   (the generated dc_mystic_scalar)
//   argv[4] prices.tsv   base \t roll \t gold   (an exact-fraction oracle over data/d3/mystic_cost_scalars.csv)
//
// The draws and the class lookups (main stat, a skill group's skills) are test doubles; everything the
// rules decide is the production header's. It does NOT test the database, the Player or the window.

#include "dc_enchant_rule.h"

#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <map>
#include <random>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

using namespace DC::Enchant;

namespace
{
    unsigned failures = 0;

    void Check(bool ok, std::string const& message)
    {
        if (!ok)
        {
            std::cerr << "FAILED: " << message << "\n";
            ++failures;
        }
    }

    std::vector<std::vector<std::string>> Read(char const* path)
    {
        std::ifstream in(path);
        if (!in)
            throw std::runtime_error(std::string("cannot read ") + path);
        std::vector<std::vector<std::string>> rows;
        std::string line;
        while (std::getline(in, line))
        {
            std::vector<std::string> cells;
            std::stringstream stream(line);
            std::string cell;
            while (std::getline(stream, cell, '\t'))
                cells.push_back(cell);
            if (!line.empty() && line.back() == '\t')
                cells.push_back("");
            rows.push_back(cells);
        }
        return rows;
    }

    std::map<std::string, std::vector<Cand>> pools; // slot|bracket -> entries in display order
    std::map<std::string, std::string> oracleGroup; // D3Planner's exclusive groups, id -> group

    // The oracle's group of a POOL id: the same naming dc_items.cpp's PoolId gives a line (every main stat is
    // "mainstat"), then D3Planner's own statGroups, else the id itself.
    std::string Group(std::string const& poolId)
    {
        auto found = oracleGroup.find(poolId);
        return found == oracleGroup.end() ? poolId : found->second;
    }

    // The test double of what dc_items.cpp's MysticCtx knows about the player and the item.
    struct Ctx
    {
        std::string weapon;
        bool shield = false;
        mutable std::mt19937 rng{7};

        double Unit() const
        {
            return std::uniform_real_distribution<double>(0.0, 1.0)(rng);
        }
        static bool SkillGroup(std::string const& id)
        {
            return id.rfind("skill_", 0) == 0;
        }
        std::string PoolId(std::string const& id) const
        {
            if (id == "str" || id == "dex" || id == "int")
                return "mainstat";
            if (SkillGroup(id) && id.size() > 2 &&
                (id.substr(id.size() - 2) == "_a" || id.substr(id.size() - 2) == "_b"))
                return id.substr(0, id.size() - 2);
            return id;
        }
        std::vector<Cand> Expand(Cand const& c) const
        {
            if (c.id == "baseblock" || c.id == "blockamount" || c.id == "blockamountdelta" ||
                (c.id == "block" && !shield))
                return {};
            if (c.id == "mainstat")
            {
                Cand e = c;
                e.id = "int";
                return {e};
            }
            if (SkillGroup(c.id))
            {
                Cand a = c, b = c;
                a.id = c.id + "_a";
                b.id = c.id + "_b";
                return {a, b};
            }
            return {c};
        }
        void Shuffle(std::vector<Cand>& list) const
        {
            std::shuffle(list.begin(), list.end(), rng);
        }
        std::size_t Index(std::size_t count) const
        {
            return std::uniform_int_distribution<std::size_t>(0, count - 1)(rng);
        }
        std::pair<double, double> Value(Cand const& c) const
        {
            double const value = std::floor(c.min + (c.max - c.min) * Unit() + 0.5);
            if (c.max2 <= 0)
                return {value, 0.0};
            double const low = c.min2 - c.min, high = c.max2 - c.max;
            return {value, value + std::floor((high <= low ? std::max(0.0, low) : low + (high - low) * Unit()) + 0.5)};
        }
        std::string WeaponClass() const
        {
            return weapon;
        }
    };

    struct Item
    {
        std::string slot;
        std::vector<Cand> pool;
        std::vector<Row> rows;
        std::vector<Pick> values;
        Ctx ctx;
    };

    // A weapon damage row is a pool row with a weapon class (a neck's wpnphy is a plain line).
    bool IsDamageId(Item const& item, std::string const& id)
    {
        return std::any_of(item.pool.begin(), item.pool.end(),
                           [&](Cand const& c) { return c.id == id && !c.weaponClass.empty(); });
    }

    // The weapon class a slot's own weapons roll in: the first one its pool carries.
    std::string WeaponOf(std::vector<Cand> const& pool, unsigned which)
    {
        std::vector<std::string> classes;
        for (Cand const& c : pool)
            if (!c.weaponClass.empty() && std::find(classes.begin(), classes.end(), c.weaponClass) == classes.end())
                classes.push_back(c.weaponClass);
        return classes.empty() ? "" : classes[which % classes.size()];
    }

    // A legal item of the slot: up to four primaries and two secondaries from distinct exclusive groups, with
    // its damage row first on a weapon, the sockets as several rows, a skill line resolved to a choice.
    Item Build(std::string const& slot, std::string const& bracket, unsigned seed)
    {
        Item item;
        item.slot = slot;
        item.ctx.rng.seed(seed);
        item.pool = pools[slot + "|" + bracket];
        item.ctx.weapon = WeaponOf(item.pool, seed);
        item.ctx.shield = slot == "offhand";
        std::vector<Cand> usable;
        for (Cand const& c : item.pool)
            if ((c.weaponClass.empty() || c.weaponClass == item.ctx.weapon) && !item.ctx.Expand(c).empty())
                usable.push_back(c);
        item.ctx.Shuffle(usable);
        std::set<std::string> used;
        unsigned primaries = 0, secondaries = 0;
        auto take = [&](Cand const& c)
        {
            unsigned& count = c.kind == "secondary" ? secondaries : primaries;
            if (count >= (c.kind == "secondary" ? 2u : 4u) || used.count(Group(c.id)))
                return;
            used.insert(Group(c.id));
            ++count;
            Cand resolved = item.ctx.Expand(c)[0];
            unsigned const count_rows = c.id == "sockets" ? 1 + seed % 2 : 1;
            for (unsigned i = 0; i < count_rows; ++i)
            {
                unsigned const seq = static_cast<unsigned>(item.rows.size());
                std::string const kind = c.id == "sockets" ? "socket" : (seed % 3 == 0 ? "preset" : c.kind);
                item.rows.push_back({seq, resolved.id, kind, false});
                Pick pick;
                pick.seq = seq;
                pick.id = resolved.id;
                pick.kind = kind;
                pick.value = c.min;
                pick.value2 = c.weaponClass.empty() ? 0 : c.min2;
                pick.min = c.min;
                pick.max = c.max;
                pick.min2 = c.min2;
                pick.max2 = c.max2;
                item.values.push_back(pick);
            }
        };
        for (Cand const& c : usable)
            if (!c.weaponClass.empty())
            {
                take(c);
                break;
            }
        for (Cand const& c : usable)
            take(c);
        return item;
    }

    std::string KindOf(Item const& item, Row const& row)
    {
        for (Cand const& c : item.pool)
            if (c.id == item.ctx.PoolId(row.id))
                return c.kind;
        return "";
    }

    void Prices(char const* scalars, char const* prices)
    {
        std::vector<Scalar> table;
        for (auto const& r : Read(scalars))
            table.push_back({static_cast<unsigned>(std::stoul(r[0])), static_cast<unsigned>(std::stoul(r[1]))});
        unsigned checked = 0;
        for (auto const& r : Read(prices))
        {
            double const base = std::stod(r[0]);
            unsigned const roll = static_cast<unsigned>(std::stoul(r[1]));
            auto got = Price(base, roll, table);
            Check(got && *got == std::stoull(r[2]), "price base " + r[0] + " roll " + r[1] + " expected " + r[2] +
                                                        " got " + (got ? std::to_string(*got) : "none"));
            ++checked;
        }
        Check(checked > 1000, "the price oracle was empty");
        // The brief's own spot values: roll 1 to 5 are 1.2, 1.4, 1.6, 1.8, 2.0; roll 10 is 6.0; each doubling after it
        // triples.
        std::vector<unsigned> thousand = {1200, 1400, 1600, 1800, 2000, 2800, 3600, 4400, 5200, 6000, 7200, 8400};
        for (unsigned n = 1; n <= thousand.size(); ++n)
        {
            auto got = Price(1000, n, table);
            Check(got && *got == thousand[n - 1], "base 1000 roll " + std::to_string(n));
        }
        for (unsigned n : {10u, 20u, 40u, 80u, 160u, 320u})
        {
            auto a = Price(1000, n, table);
            auto b = Price(1000, n * 2, table);
            Check(a && b && *b == *a * 3, "doubling roll " + std::to_string(n) + " triples the price");
        }
        // A roll outside the table, an empty or short table, an unsorted one, a bad base: refused, never invented.
        Check(!Price(1000, 0, table) && !Price(1000, 641, table), "a roll outside the table has no price");
        Check(!Price(1000, 1, {}) && !Price(1000, 1, {{1, 12}}), "a table with fewer than two rows has no price");
        Check(!Price(1000, 1, {{5, 20}, {2, 14}}) && !Price(1000, 5, {{1, 20}, {5, 12}}),
              "an unsorted or falling table has no price");
        Check(!Price(-1, 1, table) && !Price(std::nan(""), 1, table), "a bad base has no price");
    }

    void Groups()
    {
        // Every D3Planner member of an exclusive group our items carry is in the header's table, with the same group.
        for (auto const& [id, group] : oracleGroup)
            if (group != "mainstat" && group != "skill" && group != "caldesanns")
                Check(Exclusion(id) == group,
                      "exclusion group of " + id + " is " + Exclusion(id) + ", D3Planner says " + group);
        // The pool-level ids that stand for a whole group.
        Check(Exclusion("onhit") == "onhit" && Exclusion("elemental") == "elemental", "generic onhit and elemental");
        Check(Exclusion("vit") == "vit" && Exclusion("mainstat") == "mainstat" &&
                  Exclusion("skill_head") == "skill_head",
              "everything else is its own group");
    }

    unsigned items = 0, targets = 0, enchantable = 0, damageTargets = 0;

    // What the line may become, worked out here from D3Planner's groups and the pool alone: the entries of the line's own
    // pool and kind, in no exclusive group another line holds, damage rows only for a damage line (and only the weapon's
    // own), nothing the item cannot carry.
    std::vector<std::string> Expected(Item const& item, Row const& target)
    {
        std::vector<std::string> out;
        auto own = std::find_if(item.pool.begin(), item.pool.end(),
                                [&](Cand const& c) { return c.id == item.ctx.PoolId(target.id); });
        if (own == item.pool.end())
            return out;
        std::set<std::string> others;
        for (Row const& r : item.rows)
            if (r.seq != target.seq && r.kind != "gem" && !(target.kind == "socket" && r.kind == "socket"))
                others.insert(Group(item.ctx.PoolId(r.id)));
        for (Cand const& c : item.pool)
            if (c.kind == own->kind && c.weaponClass.empty() == own->weaponClass.empty() &&
                (c.weaponClass.empty() || c.weaponClass == item.ctx.weapon) && !others.count(Group(c.id)) &&
                !item.ctx.Expand(c).empty())
                out.push_back(c.id);
        return out;
    }

    void OneItem(Item& item)
    {
        ++items;
        std::set<std::string> held;
        for (Row const& r : item.rows)
            if (r.kind != "gem")
                held.insert(Group(item.ctx.PoolId(r.id)));
        for (Row const& target : item.rows)
        {
            ++targets;
            std::string const targetKind = KindOf(item, target);
            std::string const tag = item.slot + " seq " + std::to_string(target.seq) + " (" + target.id + ")";
            std::set<std::string> others;
            for (Row const& r : item.rows)
                if (r.seq != target.seq && !(target.kind == "socket" && r.kind == "socket"))
                    others.insert(Group(item.ctx.PoolId(r.id)));
            bool const damage = IsDamageId(item, target.id);
            damageTargets += damage;
            auto fresh = NewChoices(item.pool, target, item.rows, item.ctx);
            auto eligible = Replacements(item.pool, target, item.rows, item.ctx);
            auto preview = Preview(item.pool, target, item.rows, item.ctx);
            std::vector<std::string> offered;
            for (Cand const& c : eligible)
                offered.push_back(c.id);
            Check(offered == Expected(item, target), tag + ": the entries the line can become are not the oracle's");
            // Every entry offered is of the line's own pool, in no group another line holds, and a damage line
            // only ever meets damage rows of the weapon's own bracket (and nothing else meets one).
            for (Cand const& c : eligible)
            {
                Check(c.kind == targetKind, tag + ": " + c.id + " is not of the line's pool");
                Check(!others.count(Group(c.id)), tag + ": " + c.id + " breaks an exclusion group the item holds");
                Check(c.weaponClass.empty() == !damage, tag + ": " + c.id + " crosses the damage rule");
                Check(!damage || c.weaponClass == item.ctx.weapon, tag + ": " + c.id + " is another weapon's damage");
            }
            std::set<std::string> distinct;
            for (Pick const& p : preview)
            {
                Check(!others.count(Group(item.ctx.PoolId(p.id))), tag + ": preview " + p.id + " breaks a group");
                Check(p.max >= p.min && IsDamageId(item, p.id) == damage, tag + ": preview " + p.id);
                Check(!damage || (p.min2 > 0 && p.max2 >= p.min2),
                      tag + ": preview of a damage row has no second range");
                distinct.insert(p.id);
            }
            Check(distinct.size() == preview.size(), tag + ": preview lists an affix twice");
            Check(fresh.empty() || fresh.size() == 2, tag + ": new choices are two or none");
            Check(!fresh.empty() == (eligible.size() >= 2), tag + ": two choices exactly when two entries can be had");
            if (fresh.size() == 2)
            {
                ++enchantable;
                Check(fresh[0].id != fresh[1].id, tag + ": the two choices are the same affix");
                for (Pick const& p : fresh)
                {
                    bool const isDamage = IsDamageId(item, p.id);
                    Check(isDamage == damage, tag + ": " + p.id + " crosses the damage rule");
                    Check(!others.count(Group(item.ctx.PoolId(p.id))), tag + ": " + p.id + " breaks a group");
                    Check(p.seq == target.seq, tag + ": a choice is for another line");
                    Check(p.kind == (p.id == "sockets" ? "socket" : targetKind),
                          tag + ": " + p.id + " is of another pool");
                    Check(p.value >= p.min - 0.5 && p.value <= p.max + 0.5, tag + ": " + p.id + " rolled outside its own range");
                    if (isDamage)
                    {
                        // Its OWN fresh two-part range: the pool's bracket for this weapon, both parts rolled.
                        bool own = false;
                        for (Cand const& c : item.pool)
                            own = own || (c.id == p.id && c.weaponClass == item.ctx.weapon && c.min == p.min &&
                                          c.max == p.max && c.min2 == p.min2 && c.max2 == p.max2);
                        Check(own, tag + ": " + p.id + " does not carry its own bracket");
                        Check(p.value2 >= p.min2 && p.value2 <= p.max2 && p.value2 > p.value,
                              tag + ": " + p.id + " second part");
                    }
                    else
                    {
                        // An ordinary line rolls the pool row's own second range when it has one (jewelry's
                        // +X-Y Physical Damage), and a one-part row carries none.
                        double min2 = 0, max2 = 0;
                        for (Cand const& c : item.pool)
                            if (c.id == item.ctx.PoolId(p.id) && c.weaponClass.empty() && c.max2 > 0)
                                min2 = c.min2, max2 = c.max2;
                        Check(p.min2 == min2 && p.max2 == max2, tag + ": " + p.id + " carries another second range");
                        if (max2 > 0)
                            Check(p.value2 >= p.min2 && p.value2 <= p.max2 && p.value2 > p.value,
                                  tag + ": " + p.id + " second part");
                        else
                            Check(p.value2 == 0, tag + ": a one-part choice carries a second part");
                    }
                }
            }
        }
        // The lines the window lists.
        std::vector<Line> lines = Lines(item.pool, item.rows, item.values, false, item.ctx);
        unsigned sockets = 0, listable = 0;
        bool gems = false;
        std::set<unsigned> seen;
        for (Row const& r : item.rows)
        {
            sockets += r.kind == "socket";
            gems = gems || r.kind == "gem";
        }
        unsigned socketLines = 0;
        for (Line const& l : lines)
        {
            Check(seen.insert(l.pick.seq).second, "a line is listed twice: " + l.pick.id);
            Check(l.state == State::Open || l.state == State::Nothing, "an unlocked item lists only open lines");
            socketLines += l.pick.kind == "socket";
            Row const* row = nullptr;
            for (Row const& r : item.rows)
                if (r.seq == l.pick.seq)
                    row = &r;
            Check(row && (Expected(item, *row).size() < 2) == (l.state == State::Nothing),
                  "a line is greyed exactly when it has fewer than two things it could become: " + l.pick.id);
            if (l.state == State::Open)
                Check(
                    Replacements(item.pool, Row{l.pick.seq, l.pick.id, "primary", false}, item.rows, item.ctx).size() >=
                        2,
                    "an open line has fewer than two things it could become");
            if (l.pick.kind == "socket")
                Check(l.pick.id == "sockets" && l.pick.value == sockets,
                      "the sockets are one line whose value is their count");
            ++listable;
        }
        Check(socketLines <= 1, "the sockets are listed as one line");
        Check(lines.size() <= item.rows.size() && listable == lines.size(), "listing");
        // Tooltip order: primary pool, secondary pool, sockets, each by the pool's display order.
        for (std::size_t i = 1; i < lines.size(); ++i)
        {
            auto rank = [](Line const& l) { return l.pick.kind == "socket" ? 3 : l.pick.kind == "secondary" ? 2 : 1; };
            Check(rank(lines[i - 1]) < rank(lines[i]) ||
                      (rank(lines[i - 1]) == rank(lines[i]) && lines[i - 1].order <= lines[i].order),
                  "lines are not in tooltip order");
        }
        (void) gems;
    }

    void Items()
    {
        std::set<std::string> slots;
        for (auto const& [key, entries] : pools)
            slots.insert(key.substr(0, key.find('|')));
        for (std::string const& slot : slots)
            for (std::string const bracket : {"rare", "legendary"})
            {
                if (pools[slot + "|" + bracket].empty())
                    continue;
                for (unsigned seed = 1; seed <= 60; ++seed)
                {
                    Item item = Build(slot, bracket, seed);
                    if (item.rows.empty())
                        continue;
                    OneItem(item);
                    // A weapon whose damage line is gone: no other line may ever become a damage row, held group or not.
                    Item bare = item;
                    bare.rows.clear();
                    bare.values.clear();
                    for (std::size_t i = 0; i < item.rows.size(); ++i)
                        if (!IsDamageId(item, item.rows[i].id))
                        {
                            bare.rows.push_back(item.rows[i]);
                            bare.values.push_back(item.values[i]);
                        }
                    if (bare.rows.size() != item.rows.size() && !bare.rows.empty())
                        OneItem(bare);
                }
            }
        Check(items > 500 && targets > 3000 && enchantable > 1500, "the item sample was too small to mean anything");
        Check(damageTargets > 100, "the sample held too few weapon damage lines");
    }

    // Ruling q-1004-21: an Arcane damage line becomes Lightning or any other damage row, only ever a damage row, each
    // with its own fresh two-part roll; no other line of a weapon ever becomes one.
    void DamageLines()
    {
        for (std::string const slot : {"onehand", "twohand"})
        {
            Item item = Build(slot, "legendary", 3);
            Row const* damage = nullptr;
            Row const* other = nullptr;
            for (Row const& r : item.rows)
            {
                if (IsDamageId(item, r.id))
                    damage = &r;
                else if (!other && r.kind != "socket")
                    other = &r;
            }
            Check(damage && other, slot + ": the built weapon has no damage line and another line");
            if (!damage || !other)
                continue;
            std::set<std::string> becomes;
            for (unsigned draw = 0; draw < 4000; ++draw)
            {
                for (Pick const& p : NewChoices(item.pool, *damage, item.rows, item.ctx))
                {
                    Check(IsDamageId(item, p.id) && p.min2 > 0 && p.value2 > p.value,
                          slot + ": a damage line became " + p.id);
                    becomes.insert(p.id);
                }
                for (Pick const& p : NewChoices(item.pool, *other, item.rows, item.ctx))
                    Check(!IsDamageId(item, p.id), slot + ": " + other->id + " became the damage line " + p.id);
            }
            std::set<std::string> everything;
            for (Cand const& c : item.pool)
                if (c.weaponClass == item.ctx.weapon)
                    everything.insert(c.id);
            Check(becomes == everything && everything.size() == 7,
                  slot + ": the damage line cannot become every damage row of its bracket, itself included");
        }
    }

    // Every exclusive group with two members in a slot's pool: an item holding one never offers another, for any
    // line whose pool the other lives in.
    void ExclusionGroups()
    {
        unsigned scenarios = 0;
        std::map<std::string, std::vector<std::string>> members;
        for (auto const& [id, group] : oracleGroup)
            members[group].push_back(id);
        for (auto const& [key, pool] : pools)
        {
            std::string const slot = key.substr(0, key.find('|'));
            std::string const bracket = key.substr(key.find('|') + 1);
            if (bracket != "legendary")
                continue;
            for (auto const& [group, ids] : members)
            {
                if (group == "weapon" || group == "mainstat" || group == "skill" || group == "caldesanns")
                    continue;
                std::vector<Cand> inPool;
                for (Cand const& c : pool)
                    if (std::find(ids.begin(), ids.end(), c.id) != ids.end())
                        inPool.push_back(c);
                for (Cand const& held : inPool)
                    for (Cand const& wanted : inPool)
                    {
                        if (held.id == wanted.id)
                            continue;
                        // An item holding `held`, plus a filler line of the pool `wanted` lives in.
                        Item item;
                        item.slot = slot;
                        item.pool = pool;
                        item.ctx.weapon = WeaponOf(pool, 0);
                        item.ctx.shield = slot == "offhand";
                        item.rows.push_back({0, held.id, held.kind, false});
                        Pick hp;
                        hp.seq = 0;
                        hp.id = held.id;
                        hp.kind = held.kind;
                        item.values.push_back(hp);
                        const Cand* filler = nullptr;
                        for (Cand const& c : pool)
                            if (c.kind == wanted.kind && c.weaponClass.empty() && c.id != held.id &&
                                c.id != wanted.id && Group(c.id) != group && !item.ctx.Expand(c).empty() &&
                                c.id != "sockets")
                            {
                                filler = &c;
                                break;
                            }
                        if (!filler)
                            continue;
                        item.rows.push_back({1, item.ctx.Expand(*filler)[0].id, filler->kind, false});
                        ++scenarios;
                        for (unsigned draw = 0; draw < 300; ++draw)
                            for (Pick const& p : NewChoices(item.pool, item.rows[1], item.rows, item.ctx))
                                Check(Group(p.id) != group,
                                      slot + ": " + held.id + " is held and " + p.id + " was offered (" + group + ")");
                        for (Cand const& c : Replacements(item.pool, item.rows[1], item.rows, item.ctx))
                            Check(Group(c.id) != group, slot + ": " + held.id + " is held and " + c.id +
                                                            " can replace a line (" + group + ")");
                    }
            }
        }
        Check(scenarios > 10, "too few exclusion scenarios were built: " + std::to_string(scenarios));
    }

    // The enchant lock: a locked item lists only its enchanted line and nothing else is offered for another.
    void Locked()
    {
        Item item = Build("twohand", "legendary", 5);
        Check(item.rows.size() >= 4, "the locked-item fixture is too small");
        for (std::size_t chosen = 0; chosen < item.rows.size(); ++chosen)
        {
            std::vector<Row> rows = item.rows;
            for (Row& r : rows)
                r.rerolled = false;
            rows[chosen].rerolled = true;
            auto lines = Lines(item.pool, rows, item.values, true, item.ctx);
            Check(lines.size() == 1 && (lines[0].pick.seq == rows[chosen].seq ||
                                        (rows[chosen].kind == "socket" && lines[0].pick.kind == "socket")),
                  "a locked item lists its enchanted line alone: seq " + std::to_string(chosen) + " (" +
                      rows[chosen].id + ") listed " + std::to_string(lines.size()));
            Check(lines.size() == 1 && (lines[0].state == State::Enchanted || lines[0].state == State::Nothing),
                  "the enchanted line is marked enchanted");
            auto open = Lines(item.pool, rows, item.values, false, item.ctx);
            Check(open.size() > 1, "an unlocked item lists every line");
        }
        // The sockets are one enchanted line when any one socket row carries the mark (the last one here).
        Item sockets = Build("twohand", "legendary", 4);
        std::vector<Row> rows;
        std::vector<Pick> values;
        for (Row const& r : sockets.rows)
            if (r.kind != "socket")
                rows.push_back(r);
        for (Pick const& p : sockets.values)
            if (p.kind != "socket")
                values.push_back(p);
        for (unsigned seq : {200u, 201u, 202u})
        {
            rows.push_back({seq, "sockets", "socket", false});
            Pick pick;
            pick.seq = seq;
            pick.id = "sockets";
            pick.kind = "socket";
            pick.value = 1;
            values.push_back(pick);
        }
        unsigned count = 0;
        for (Row& r : rows)
        {
            r.rerolled = false;
            count += r.kind == "socket";
        }
        for (auto it = rows.rbegin(); it != rows.rend(); ++it)
            if (it->kind == "socket")
            {
                it->rerolled = true;
                break;
            }
                auto lines = Lines(sockets.pool, rows, values, true, sockets.ctx);
        Check(lines.size() == 1 && lines[0].pick.id == "sockets" && lines[0].pick.value == count,
              "a locked item whose sockets were enchanted lists the sockets as one line");
    }

    // A socketed gem makes the sockets line unreplaceable, and a pool with too little in it offers nothing.
    void States()
    {
        Item item = Build("twohand", "legendary", 4);
        std::vector<Row> rows;
        std::vector<Pick> values;
        for (Row const& r : item.rows)
            if (r.kind != "socket")
                rows.push_back(r);
        for (Pick const& p : item.values)
            if (p.kind != "socket")
                values.push_back(p);
        for (unsigned seq : {200u, 201u})
        {
            rows.push_back({seq, "sockets", "socket", false});
            Pick socket;
            socket.seq = seq;
            socket.id = "sockets";
            socket.kind = "socket";
            socket.value = 1;
            values.push_back(socket);
        }
        for (bool gemmed : {false, true})
        {
            std::vector<Row> withGem = rows;
            std::vector<Pick> withValues = values;
            if (gemmed)
            {
                withGem.push_back({300, "ruby", "gem", false});
                Pick gem;
                gem.seq = 300;
                gem.id = "ruby";
                gem.kind = "gem";
                withValues.push_back(gem);
            }
            unsigned socketLines = 0;
            for (Line const& l : Lines(item.pool, withGem, withValues, false, item.ctx))
            {
                socketLines += l.pick.kind == "socket";
                Check((l.pick.kind == "socket" && gemmed) == (l.state == State::Gems),
                      "only the sockets line is marked gems, and only when a gem is in it");
            }
            Check(socketLines == 1, "the sockets are listed as one line");
        }
        // Fewer than two entries to become: nothing.
        Cand vit, chd;
        vit.id = "vit";
        vit.kind = "primary";
        vit.min = 1;
        vit.max = 2;
        chd = vit;
        chd.id = "chd";
        std::vector<Cand> tiny = {vit, chd};
        Ctx ctx;
        Row only{0, "vit", "primary", false};
        Check(NewChoices(tiny, only, {only}, ctx).empty() == false, "two entries give two choices");
        tiny.pop_back();
        Check(NewChoices(tiny, only, {only}, ctx).empty(), "one entry gives none");
        Check(Replacements(tiny, Row{0, "unknown", "primary", false}, {}, ctx).empty(),
              "a line the pool does not know cannot be enchanted");
    }

    // Choice one is the line as it is on the item now; a roll stored by the code before the rebuild (two rows, no
    // second part) comes back as that line plus its two stored offers.
    void Waiting3()
    {
        std::vector<Pick> lines;
        for (unsigned seq : {0u, 1u, 2u})
        {
            Pick p;
            p.seq = seq;
            p.id = "line" + std::to_string(seq);
            p.kind = seq == 2 ? "socket" : "primary";
            p.value = 10 + seq;
            lines.push_back(p);
        }
        std::vector<Pick> stored(2);
        stored[0].id = "vit";
        stored[0].value = 5;
        stored[1].id = "chd";
        stored[1].value = 7;
        auto three = Waiting(lines, 1, false, stored);
        Check(three && three->size() == 3 && (*three)[0].id == "line1" && (*three)[0].value == 11,
              "the first choice is the current line");
        Check(three && (*three)[1].id == "vit" && (*three)[2].id == "chd", "then the two stored rolls, in order");
        auto sockets = Waiting(lines, 7, true, stored);
        Check(sockets && (*sockets)[0].id == "line2",
              "a sockets roll starts with the sockets line whatever socket row it was paid on");
        Check(!Waiting(lines, 9, false, stored), "a line that is gone has no choices");
    }

    void Eligibility()
    {
        for (char const* ok : {"rare", "legendary", "set"})
            Check(Eligible(ok), std::string(ok) + " can be enchanted");
        for (char const* no : {"normal", "magic", "ethereal", "", "Rare"})
            Check(!Eligible(no), std::string("'") + no + "' cannot be enchanted");
    }
} // namespace

int main(int argc, char** argv)
{
    if (argc != 5)
    {
        std::cerr << "usage: enchant_rule_tests pool.tsv groups.tsv scalars.tsv prices.tsv\n";
        return 2;
    }
    try
    {
        for (auto const& r : Read(argv[1]))
        {
            Cand c;
            c.id = r[2];
            c.kind = r[3];
            c.min = std::stod(r[4]);
            c.max = std::stod(r[5]);
            c.min2 = r[6].empty() ? 0 : std::stod(r[6]);
            c.max2 = r[7].empty() ? 0 : std::stod(r[7]);
            c.step = r[8].empty() ? 0 : std::stod(r[8]);
            c.weaponClass = r[9];
            c.order = static_cast<unsigned>(std::stoul(r[10].empty() ? "0" : r[10]));
            pools[r[0] + "|" + r[1]].push_back(c);
        }
        for (auto const& r : Read(argv[2]))
            oracleGroup[r[0]] = r[1];
        Eligibility();
        Prices(argv[3], argv[4]);
        Groups();
        Waiting3();
        States();
        Locked();
        DamageLines();
        ExclusionGroups();
        Items();
    }
    catch (std::exception const& error)
    {
        std::cerr << "harness error: " << error.what() << "\n";
        return 2;
    }
    if (failures)
    {
        std::cerr << failures << " check(s) failed\n";
        return 1;
    }
    std::cout << "PASS " << items << " items, " << targets << " lines, " << enchantable << " enchantable\n";
    return 0;
}
