// Drives Primordial Soul (diablocraft-tt86k): the REAL Wizard::TargetFactor, cut out of src/classes/wizard/dc_wizard.cpp by
// scripts/tests/legendaries/test_item_power_primordial_soul.py (dc_primordial_soul_extract.h), with the REAL ItemPower::PassiveSetTo of
// src/combat/dc_item_power_math.h fed the rows the generator emitted. DOUBLES, which prove nothing about the core: the Player and Unit,
// the passive lookup (Has, PassiveId), the number sheet (Num: `num` commands carry the sheet's own values), the clock, the marks'
// store, and ItemPowers::PassiveSetTo, which stands for the thin wrapper of dc_item_powers.cpp (state of the worn items, then the
// rule of the math header); the Python test pins that wrapper's lines.
// Input, tab separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax> <fireOn> <fireSkills;..> <chance> <icd>
//   num <token> <value> | wears <owner> | has <0|1> | now <ms> | mark <target> <school> <expiresMs> | clear (the worn items, passive, marks)
//   factor <target>   -> Wizard::TargetFactor of that enemy
//   raised <base>     -> ItemPower::PassiveSetTo of Elemental Exposure's damage_taken_pct from <base>
#include "combat/dc_item_power_math.h"

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <map>
#include <mutex>
#include <sstream>
#include <string>
#include <string_view>
#include <vector>

using uint32 = std::uint32_t;
using uint64 = std::uint64_t;

struct ObjectGuid
{
    uint64 raw = 0;
    uint64 GetRawValue() const
    {
        return raw;
    }
};
class Player
{
};
class Unit
{
public:
    ObjectGuid guid;
    ObjectGuid GetGUID() const
    {
        return guid;
    }
};

static std::vector<DC::Combat::ItemPower::Row> rows;
static DC::Combat::ItemPower::Situation situation;
static std::map<std::string, double> sheet;
static bool passive = false;
static uint64 clock_ms = 0;

namespace DC::Combat::ItemPowers
{
    double PassiveSetTo(Player const*, std::string const& name, std::string const& token, double base)
    {
        static std::map<std::string, unsigned> const none;
        return ItemPower::PassiveSetTo(rows, none, name, token, base, situation);
    }
}

namespace DC::Combat::Wizard
{
    namespace
    {
        struct Marks
        {
            std::map<unsigned, uint64> exposure;
        };
        struct State
        {
            std::map<uint64, Marks> marks;
        };
        State state;
        std::recursive_mutex mutex;

        double Num(uint32, std::string_view token, std::string_view = {})
        {
            return sheet.at(std::string(token));
        }
        uint32 PassiveId(std::string_view name)
        {
            return name == "Elemental Exposure" ? 83273 : 0;
        }
        bool Has(Player*, char const*)
        {
            return passive;
        }
        State& StateOf(Player*)
        {
            return state;
        }
        uint64 Now()
        {
            return clock_ms;
        }
    } // namespace

#include "dc_primordial_soul_extract.h"
} // namespace DC::Combat::Wizard

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
    Player player;
    std::string line;
    while (std::getline(in, line))
    {
        auto c = Split(line, '\t');
        if (c.empty())
            continue;
        if (c[0] == "row")
        {
            DC::Combat::ItemPower::Row row{c[1], static_cast<unsigned>(std::stoul(c[2])), c[3], c[4], c[5], std::stod(c[6]), std::stod(c[7]),
                                           c[8], std::stod(c[9]), Split(c[10], ';'), std::stod(c[11]), static_cast<unsigned>(std::stoul(c[12]))};
            row.fireOn = c[13];
            row.fireSkills = Split(c[14], ';');
            row.chancePct = std::stod(c[15]);
            row.icdSeconds = std::stod(c[16]);
            rows.push_back(row);
        }
        else if (c[0] == "num")
            sheet[c[1]] = std::stod(c[2]);
        else if (c[0] == "wears")
            situation.wornSince[c[1]] = 0;
        else if (c[0] == "has")
            passive = c[1] == "1";
        else if (c[0] == "now")
            clock_ms = std::stoull(c[1]);
        else if (c[0] == "mark")
            DC::Combat::Wizard::state.marks[std::stoull(c[1])].exposure[static_cast<unsigned>(std::stoul(c[2]))] = std::stoull(c[3]);
        else if (c[0] == "clear")
        {
            situation = DC::Combat::ItemPower::Situation{};
            passive = false;
            DC::Combat::Wizard::state.marks.clear();
        }
        else if (c[0] == "factor")
        {
            Unit enemy;
            enemy.guid.raw = std::stoull(c[1]);
            std::printf("%.10g\n", DC::Combat::Wizard::TargetFactor(&player, &enemy));
        }
        else if (c[0] == "raised")
        {
            static std::map<std::string, unsigned> const none;
            std::printf("%.10g\n", DC::Combat::ItemPower::PassiveSetTo(rows, none, "Elemental Exposure", "damage_taken_pct", std::stod(c[1]), situation));
        }
    }
    return 0;
}
