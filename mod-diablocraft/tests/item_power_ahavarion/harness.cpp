// Drives the Ahavarion rules (N-CTF and N-PYLON) of src/combat/dc_item_power_math.h (which kill fires the row, creature type names)
// and src/combat/dc_pylon_math.h (which shrine a random draw picks) with the rows the generator emitted.
// Input, tab separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax>
//   <fireOn> <fireSkills;..> <chance> <icd> now <ms> | wears <owner> <since> | clear
//   fire <event> <skill> <scale> <draw> <target type name or ->   -> "stat=value;..." of the effect rows ItemPower::Fire fires
//   ctype <number>                                                -> CreatureTypeName
//   shrine <roll>                                                 -> the name of the kind RandomShrine picks, and whether it is a pylon
//   shrines                                                       -> the count and the names of every kind RandomShrine can pick
//   rolls <coefficient> <chance> <draw>                           -> Proc::Rolls: 1 when the chance falls
// A chance falls when <draw> < the percent asked.
#include "combat/dc_item_power_math.h"
#include "combat/dc_proc_math.h"
#include "combat/dc_pylon_math.h"

#include <cstdio>
#include <fstream>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <vector>

using namespace DC::Combat;

static std::vector<std::string> Split(std::string const& text, char by)
{
    std::vector<std::string> cells;
    std::stringstream stream(text);
    std::string cell;
    while (std::getline(stream, cell, by))
        cells.push_back(cell);
    return cells;
}

int main(int argc, char** argv)
{
    if (argc < 2)
        return 2;
    std::ifstream in(argv[1]);
    std::vector<ItemPower::Row> rows;
    ItemPower::Situation sit;
    std::string line;
    while (std::getline(in, line))
    {
        auto c = Split(line, '\t');
        if (c.empty())
            continue;
        if (c[0] == "row")
        {
            ItemPower::Row row{c[1],
                               static_cast<unsigned>(std::stoul(c[2])),
                               c[3],
                               c[4],
                               c[5],
                               std::stod(c[6]),
                               std::stod(c[7]),
                               c[8],
                               std::stod(c[9]),
                               Split(c[10], ';'),
                               std::stod(c[11]),
                               static_cast<unsigned>(std::stoul(c[12]))};
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
        else if (c[0] == "clear")
            sit = ItemPower::Situation{};
        else if (c[0] == "fire")
        {
            double const draw = std::stod(c[4]);
            sit.targetType = c[5] == "-" ? std::string() : c[5];
            std::string out;
            char text[96];
            for (ItemPower::Fired const& f :
                 ItemPower::Fire(rows, {}, sit, c[1], c[2], std::stod(c[3]), [&](double pct) { return draw < pct; }))
            {
                std::snprintf(text, sizeof text, "%s=%g;", f.stat.c_str(), f.value);
                out += text;
            }
            std::printf("%s\n", out.c_str());
        }
        else if (c[0] == "ctype")
            std::printf("%s\n", ItemPower::CreatureTypeName(static_cast<unsigned>(std::stoul(c[1]))).c_str());
        else if (c[0] == "shrine")
        {
            Pylons::Kind const kind = Pylons::RandomShrine(std::stod(c[1]));
            std::printf("%s %d\n", Pylons::Names[static_cast<unsigned>(kind)], Pylons::IsPylon(kind) ? 1 : 0);
        }
        else if (c[0] == "shrines")
        {
            std::set<std::string> seen;
            for (int step = 0; step <= 1000; ++step)
                seen.insert(Pylons::Names[static_cast<unsigned>(Pylons::RandomShrine(step / 1000.0))]);
            std::string names;
            for (std::string const& name : seen)
                names += name + ",";
            std::printf("%u %zu %s\n", Pylons::ShrineCount, seen.size(), names.c_str());
        }
        else if (c[0] == "rolls")
        {
            double const draw = std::stod(c[3]);
            std::printf("%d\n", Proc::Rolls(std::stod(c[1]), std::stod(c[2]), [&](double pct) { return draw < pct; }) ? 1 : 0);
        }
    }
    return 0;
}
