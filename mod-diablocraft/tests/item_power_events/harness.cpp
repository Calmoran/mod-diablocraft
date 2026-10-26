// Drives the event rules of src/combat/dc_item_power_math.h (Fire, the `triggered` condition, ReductionFactor, PlayerSum, HitKinds) with the
// rows the generator emitted. Input, tab separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax> <fireOn> <fireSkills;..> <chance> <icd>
//   now <ms>                         -> the clock (no output)
//   wears <owner> <since>            -> an item (d3_id) put on (no output)
//   value <owner> <skill> <stat> <v> -> a worn item's stored number for a ranged row (no output)
//   clear                            -> an empty situation, nothing fired
//   enemies <n>                      -> the enemies the firing cast hit (enemies_hit_at_most, 2z25c; no output)
//   target <pct>                     -> the target's Life, percent of its maximum (target_life_at_least, i2d92; no output)
//   yards <d>                        -> the yards from the player to the enemy the event is about (storm_armor_shock, g8clb; no output)
//   fire <event> <skill> <scale> <draw> <n> (<set> <worn>)xn -> "stat=value;..." of the effect rows that fired; a chance falls when <draw> < percent
//   player <stat> <n> (<set> <worn>)xn     -> the multiplier of a `player` `_pct` stat
//   reduction <n> (<set> <worn>)xn         -> the multiplier of the damage_reduction_pct rows
//   sum <stat> <n> (<set> <worn>)xn        -> the sum of a `player` stat
//   hitkind <primary 0|1> <cost> <generated> -> "generator spender" as 0 or 1
//   opened <event>                   -> "owner/stat/arg;..." of the `triggered` rows of the event whose window opened now (Opened)
//   (a fired `stack_buff` also prints "@owner/stackSeconds/stackMax", what its row hands the caller: Stone Gauntlets, ghb4o)
//   stacked <held> <add> <most>      -> the stacks after a stack_buff fired (Stacked)
//   speed <owner> <stacks>           -> what that many stacks of the owner's slow leave of the attacks per second (StackedSpeedFactor)
//   buff <owner> <stat>              -> one stack's number of the owner's `buff` row (BuffValue)
//   factor <skill> <stat>            -> SkillFactor of the situation now, no set counts (Girdle of Giants, 5mn2l)
//   reuse <casts> <windowSeconds> <now>  -> ReuseCast on the driver's one window: "keepOpen opened used token" (y27fd)
//   reuseend <token>                 -> ReuseEnded: 1 when it closed the open window, else 0
//   reuseclear                       -> forget the window
//   setto <skill> <stat> <base>      -> SkillSetTo of the situation now, no set counts
//   roll <owner> <top 0|1>           -> RollPowers with a draw of the range's middle, "key=value;" (5mn2l)
//   stackfactor <stat> <sign> <n> (<owner> <stacks>)xn -> StackedFactor of the situation now, no set counts (Orb of Infinite Depth, anpkx)
//   stackskill <skill> <stat> <sign> <n> (<owner> <stacks>)xn -> the same for the buff rows that name <skill> (Fleshrake)
#include "combat/dc_item_power_math.h"

#include <cstdio>
#include <fstream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

using namespace DC::Combat::ItemPower;

static std::vector<std::string> Split(std::string const& text, char by)
{
    std::vector<std::string> cells;
    std::stringstream stream(text);
    std::string cell;
    while (std::getline(stream, cell, by))
        cells.push_back(cell);
    return cells;
}

static std::map<std::string, unsigned> Counts(std::vector<std::string> const& c, std::size_t at)
{
    std::map<std::string, unsigned> counts;
    for (std::size_t i = 0; i < std::stoul(c[at]); ++i)
        counts[c[at + 1 + 2 * i]] = static_cast<unsigned>(std::stoul(c[at + 2 + 2 * i]));
    return counts;
}

int main(int argc, char** argv)
{
    if (argc < 2)
        return 2;
    std::ifstream in(argv[1]);
    std::vector<Row> rows;
    Situation sit;
    Reuse reuse;
    std::string line;
    while (std::getline(in, line))
    {
        auto c = Split(line, '\t');
        if (c.empty())
            continue;
        if (c[0] == "row")
        {
            Row row{c[1], static_cast<unsigned>(std::stoul(c[2])), c[3], c[4], c[5], std::stod(c[6]), std::stod(c[7]), c[8], std::stod(c[9]),
                    Split(c[10], ';'), std::stod(c[11]), static_cast<unsigned>(std::stoul(c[12]))};
            row.fireOn = c[13];
            row.fireSkills = Split(c[14], ';');
            row.chancePct = std::stod(c[15]);
            row.icdSeconds = std::stod(c[16]);
            rows.push_back(row);
        }
        else if (c[0] == "now")
            sit.now = static_cast<std::uint32_t>(std::stoul(c[1]));
        else if (c[0] == "wears")
            sit.wornSince[c[1]] = static_cast<std::uint32_t>(std::stoul(c[2]));
        else if (c[0] == "value")
            sit.itemValues[c[1]].push_back({c[2], c[3], std::stod(c[4]), c[1]});
        else if (c[0] == "clear")
            sit = Situation{};
        else if (c[0] == "enemies")
            sit.enemiesHit = static_cast<unsigned>(std::stoul(c[1]));
        else if (c[0] == "target")
            sit.targetLifePct = std::stod(c[1]);
        else if (c[0] == "yards")
            sit.eventYards = std::stod(c[1]);
        else if (c[0] == "fire")
        {
            double const draw = std::stod(c[4]);
            std::string out;
            char text[96];
            for (Fired const& f : Fire(rows, Counts(c, 5), sit, c[1], c[2], std::stod(c[3]), [&](double pct) { return draw < pct; }))
            {
                std::snprintf(text, sizeof text, "%s=%g;", f.stat.c_str(), f.value);
                out += text;
                if (f.stat == "stack_buff")
                {
                    std::snprintf(text, sizeof text, "@%s/%g/%u;", f.row ? f.row->owner.c_str() : "", f.row ? f.row->stackSeconds : 0,
                                  f.row ? f.row->stackMax : 0);
                    out += text;
                }
            }
            std::printf("%s\n", out.c_str());
        }
        else if (c[0] == "player")
            std::printf("%g\n", PlayerFactor(rows, Counts(c, 2), c[1], sit));
        else if (c[0] == "reduction")
            std::printf("%g\n", ReductionFactor(rows, Counts(c, 1), sit));
        else if (c[0] == "sum")
            std::printf("%g\n", PlayerSum(rows, Counts(c, 2), c[1], sit));
        else if (c[0] == "opened")
        {
            std::string out;
            for (Row const* row : Opened(rows, sit, c[1]))
                out += row->owner + "/" + row->stat + "/" + std::to_string(static_cast<int>(row->arg)) + ";";
            std::printf("%s\n", out.c_str());
        }
        else if (c[0] == "stacked")
            std::printf("%u\n", Stacked(static_cast<unsigned>(std::stoul(c[1])), std::stod(c[2]), static_cast<unsigned>(std::stoul(c[3]))));
        else if (c[0] == "speed")
            std::printf("%g\n", StackedSpeedFactor(rows, c[1], static_cast<unsigned>(std::stoul(c[2]))));
        else if (c[0] == "buff")
            std::printf("%g\n", BuffValue(rows, c[1], c[2]));
        else if (c[0] == "factor")
            std::printf("%g\n", SkillFactor(rows, std::map<std::string, unsigned>{}, c[1], c[2], sit));
        else if (c[0] == "reuse")
        {
            ReuseStep const step = ReuseCast(reuse, static_cast<unsigned>(std::stoul(c[1])), std::stod(c[2]), static_cast<std::uint32_t>(std::stoul(c[3])));
            std::printf("%d %d %u %u\n", step.keepOpen ? 1 : 0, step.opened ? 1 : 0, step.used, step.token);
        }
        else if (c[0] == "reuseend")
            std::printf("%d\n", ReuseEnded(reuse, static_cast<std::uint32_t>(std::stoul(c[1]))) ? 1 : 0);
        else if (c[0] == "reuseclear")
            reuse = Reuse{};
        else if (c[0] == "setto")
            std::printf("%g\n", SkillSetTo(rows, std::map<std::string, unsigned>{}, c[1], c[2], std::stod(c[3]), sit));
        else if (c[0] == "stackfactor")
            std::printf("%g\n", StackedFactor(rows, std::map<std::string, unsigned>{}, Counts(c, 3), c[1], std::stod(c[2]), sit));
        else if (c[0] == "stackskill")
            std::printf("%g\n", StackedFactor(rows, std::map<std::string, unsigned>{}, Counts(c, 4), c[2], std::stod(c[3]), sit, c[1]));
        else if (c[0] == "roll")
        {
            std::string out;
            char text[160];
            for (Rolled const& r : RollPowers(rows, c[1], c[2] == "1", [](double low, double high) { return (low + high) / 2; }))
            {
                std::snprintf(text, sizeof text, "%s=%g;", r.key.c_str(), r.value);
                out += text;
            }
            std::printf("%s\n", out.c_str());
        }
        else if (c[0] == "hitkind")
        {
            HitKind const kind = HitKinds(c[1] == "1", std::stod(c[2]), std::stod(c[3]));
            std::printf("%d %d\n", kind.generator ? 1 : 0, kind.spender ? 1 : 0);
        }
    }
    return 0;
}
