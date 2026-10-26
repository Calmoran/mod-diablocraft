// Drives Monkey King's Garb's rules (diablocraft-w7wes) with the rows the generator emitted: the set counter, the
// 2-piece's damage taken while the vortex is up (PlayerFactor), the 4-piece's decoy number (SkillSetTo) with the
// decoy's own rules (dc_taunt_decoy_math.h) and the vortex's clock (dc_monk_sweeping_wind.h), and the 6-piece's damage
// per stack (PerStackFactor). Input, tab separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax>
//   <fireOn> <fireSkills;..> <chance> <icd> pieces <set> <n> | active <skill> | clear taken -> the multiplier of damage
//   taken now (PlayerFactor, damage_taken_pct) perstack <skill> <stacks> -> the multiplier of the skill's damage by
//   that many stacks decoy <stacks> -> the 4-piece's number for Sweeping Wind, then the explosion's percent at that
//   many stacks: "<number> <pct>" built <taunt> <delay> <blast> | within <distance> <radius> | second <index>
//   <tickSeconds> | millis <seconds>
#include "combat/dc_item_power_math.h"
#include "combat/dc_taunt_decoy_math.h"
#include "classes/monk/dc_monk_sweeping_wind.h"

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

int main(int argc, char** argv)
{
    if (argc < 2)
        return 2;
    std::ifstream in(argv[1]);
    std::vector<Row> rows;
    std::map<std::string, unsigned> counts;
    Situation sit;
    std::string line;
    while (std::getline(in, line))
    {
        auto c = Split(line, '\t');
        if (c.empty())
            continue;
        if (c[0] == "row")
        {
            Row row{c[1],
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
        else if (c[0] == "pieces")
            counts[c[1]] = static_cast<unsigned>(std::stoul(c[2]));
        else if (c[0] == "active")
            sit.active.insert(c[1]);
        else if (c[0] == "clear")
        {
            counts.clear();
            sit = Situation{};
        }
        else if (c[0] == "taken")
            std::printf("%.10g\n", PlayerFactor(rows, counts, "damage_taken_pct", sit));
        else if (c[0] == "perstack")
            std::printf("%.10g\n",
                        PerStackFactor(rows, counts, c[1], "damage_by_wind_stacks_pct", std::stod(c[2]), sit));
        else if (c[0] == "decoy")
        {
            double const number = SkillSetTo(rows, counts, "Sweeping Wind", "decoy_damage_pct_per_stack", 0, sit);
            std::printf("%.10g %.10g\n", number,
                        DC::Combat::TauntDecoy::BlastPct(number, static_cast<unsigned>(std::stoul(c[1]))));
        }
        else if (c[0] == "built")
            std::printf("%d\n",
                        DC::Combat::TauntDecoy::Built(std::stod(c[1]), std::stod(c[2]), std::stod(c[3])) ? 1 : 0);
        else if (c[0] == "within")
            std::printf("%d\n", DC::Combat::TauntDecoy::Within(std::stod(c[1]), std::stod(c[2])) ? 1 : 0);
        else if (c[0] == "second")
            std::printf("%d\n", DC::Combat::Monk::Wind::CompletesSecond(static_cast<unsigned>(std::stoul(c[1])),
                                                                        std::stod(c[2]))
                                    ? 1
                                    : 0);
        else if (c[0] == "millis")
            std::printf("%u\n", DC::Combat::TauntDecoy::Millis(std::stod(c[1])));
    }
    return 0;
}
