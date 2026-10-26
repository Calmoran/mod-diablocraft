// Drives N-STUN of src/combat/dc_item_power_math.h (Hellrack, diablocraft-n8m1a: Fire on a `hit` of any skill with the
// row's chance scaled by the hit's proc coefficient and its internal cooldown; ControlSpell, the stock aura of a
// control effect; ControlEvent, the event a control aura put on an enemy is) with the rows the generator emitted.
// Input, tab separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax>
//   <fireOn> <fireSkills;..> <chance> <icd> now <ms> | clear | wears <owner> | dice <percent>  -> the clock; an empty
//   situation; the item put on; a roll falls when it asks at least this fire <event> <skill> <scale>      ->
//   "stat=value;..." of the effect rows that fired, then "|" and each percent a roll was asked spell <stat> ->
//   ControlSpell(stat) event <id> <stun> <freeze> <confuse> <root>   -> ControlEvent of an aura with those effects
//   (1/0) and the Freeze mechanic
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

int main(int argc, char** argv)
{
    if (argc < 2)
        return 2;
    std::ifstream in(argv[1]);
    std::vector<Row> rows;
    Situation sit;
    double dice = 0;
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
        else if (c[0] == "now")
            sit.now = static_cast<std::uint32_t>(std::stoul(c[1]));
        else if (c[0] == "dice")
            dice = std::stod(c[1]);
        else if (c[0] == "wears")
        {
            sit.wornSince[c[1]] = 0;
            sit.itemValues[c[1]] = WornValues(rows, c[1], {});
        }
        else if (c[0] == "clear")
        {
            sit = Situation{};
            dice = 0;
        }
        else if (c[0] == "fire")
        {
            std::string out, asked;
            char text[96];
            auto roll = [&](double pct)
            {
                std::snprintf(text, sizeof text, "%g;", pct);
                asked += text;
                return pct >= dice;
            };
            for (Fired const& f : Fire(rows, std::map<std::string, unsigned>{}, sit, c[1], c.size() > 2 ? c[2] : "",
                                       c.size() > 3 ? std::stod(c[3]) : 1.0, roll))
            {
                std::snprintf(text, sizeof text, "%s=%g;", f.stat.c_str(), f.value);
                out += text;
            }
            std::printf("%s|%s\n", out.c_str(), asked.c_str());
        }
        else if (c[0] == "spell")
            std::printf("%u\n", ControlSpell(c[1]));
        else if (c[0] == "event")
            std::printf("%s\n", ControlEvent(static_cast<std::uint32_t>(std::stoul(c[1])), c[2] == "1", c[3] == "1",
                                             c[4] == "1", c[5] == "1"));
    }
    return 0;
}
