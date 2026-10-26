// Drives the production throttle and spelling of src/combat/dc_buff_values_math.h.
//   "number <x>"                                  prints the contract's spelling of x
//   "set <aura> <nowMs> <intervalMs> <v1> ..."    prints the record sent now, or "-"
//   "clear <aura>"                                prints the record sent, or "-"
//   "flush <nowMs> <intervalMs>"                  prints every record sent, ';' between them, or "-"
//   "timer <currentMs> <wantedMs>"                prints 1 when Show sets the aura's timer again, else 0
// A record prints as its fields joined by '|'.
#include "combat/dc_buff_values_math.h"

#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>

namespace BV = DC::Combat::BuffValues;

static std::string Spell(BV::Record const& record)
{
    std::string out;
    for (std::string const& field : BV::Fields(record.aura, record.gone, record.values))
        out += (out.empty() ? "" : "|") + field;
    return out;
}

int main(int argc, char** argv)
{
    if (argc < 2)
        return 2;
    std::ifstream in(argv[1]);
    BV::Channel channel;
    std::string line;
    while (std::getline(in, line))
    {
        std::istringstream words(line);
        std::string command;
        words >> command;
        if (command == "number")
        {
            double value;
            words >> value;
            std::printf("%s\n", BV::Number(value).c_str());
        }
        else if (command == "set")
        {
            std::uint32_t aura, now, interval;
            words >> aura >> now >> interval;
            BV::Values values;
            for (double value; words >> value;)
                values.push_back(value);
            auto sent = channel.Set(aura, values, now, interval);
            std::printf("%s\n", sent ? Spell(*sent).c_str() : "-");
        }
        else if (command == "timer")
        {
            std::int32_t current, wanted;
            words >> current >> wanted;
            std::printf("%d\n", BV::TimerDiffers(current, wanted) ? 1 : 0);
        }
        else if (command == "clear")
        {
            std::uint32_t aura;
            words >> aura;
            auto sent = channel.Clear(aura);
            std::printf("%s\n", sent ? Spell(*sent).c_str() : "-");
        }
        else if (command == "flush")
        {
            std::uint32_t now, interval;
            words >> now >> interval;
            std::string out;
            for (BV::Record const& record : channel.Flush(now, interval))
                out += (out.empty() ? "" : ";") + Spell(record);
            std::printf("%s\n", out.empty() ? "-" : out.c_str());
        }
    }
    return 0;
}
