// Compiles dc_granted_passive_rule.h (the production header) and drives it with the generated data: which bases roll a class
// passive, that the roll reaches every passive of a class (the full list, whatever the player chose), what a worn item grants and
// what Passives::Has searches (diablocraft-enuxm, Hellfire Amulet).
// argv: bases.tsv (d3_id, rarity, presets), passives.tsv (class_id, passive name; unlock order), the d3_id that must roll.
#include "dc_granted_passive_rule.h"

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <vector>

using namespace DC::GrantedPassive;

static int failures = 0;
#define CHECK(cond)                                                                      \
    do                                                                                   \
    {                                                                                    \
        if (!(cond))                                                                     \
        {                                                                                \
            std::printf("FAILED line %d: %s\n", __LINE__, #cond);                        \
            ++failures;                                                                  \
        }                                                                                \
    } while (0)

static std::vector<std::vector<std::string>> table(char const* path)
{
    std::ifstream in(path);
    std::vector<std::vector<std::string>> rows;
    std::string line;
    while (std::getline(in, line))
    {
        std::vector<std::string> cells;
        std::stringstream stream(line);
        std::string cell;
        while (std::getline(stream, cell, '\t'))
            cells.push_back(cell);
        while (cells.size() < 3)
            cells.push_back("");
        rows.push_back(cells);
    }
    return rows;
}

static std::vector<std::string> split(std::string const& text)
{
    std::vector<std::string> parts;
    std::stringstream stream(text);
    std::string part;
    while (std::getline(stream, part, ';'))
        parts.push_back(part);
    return parts;
}

struct Stored
{
    std::string kind, affixId;
};

int main(int argc, char** argv)
{
    if (argc < 4)
        return 2;
    // 1. Which bases roll: the one named, and no ethereal, though the ethereals list the same preset.
    unsigned listing = 0, rolling = 0, ethereal = 0;
    for (auto const& row : table(argv[1]))
    {
        std::vector<std::string> const presets = split(row[2]);
        bool const lists = std::find(presets.begin(), presets.end(), "extra_passive") != presets.end();
        bool const rolls = Rolls(presets, row[1]);
        listing += lists;
        rolling += rolls;
        if (lists && row[1] == "ethereal")
        {
            ++ethereal;
            CHECK(!rolls);
        }
        CHECK(rolls == (row[0] == argv[3]));
    }
    CHECK(listing > 1 && ethereal > 0 && rolling == 1);
    CHECK(!Rolls({"mainstat", "sockets"}, "legendary"));
    CHECK(!Rolls({}, "legendary"));

    // 2. The roll is uniform over the class's whole list and reaches every passive of it.
    std::map<std::string, std::vector<std::string>> byClass;
    for (auto const& row : table(argv[2]))
        byClass[row[0]].push_back(row[1]);
    CHECK(byClass.size() >= 2);
    for (auto const& [classId, list] : byClass)
    {
        CHECK(list.size() >= 2);
        std::set<std::string> reached;
        for (std::size_t slot = 0; slot < list.size(); ++slot)
        {
            std::string const got = Pick(list, (slot + 0.5) / list.size());
            CHECK(got == list[slot]);
            reached.insert(got);
        }
        CHECK(reached.size() == list.size());
        CHECK(Pick(list, 0.0) == list.front());
        CHECK(Pick(list, -3.0) == list.front());
        CHECK(Pick(list, 0.9999999999) == list.back());
        CHECK(Pick(list, 1.0) == list.back());
        CHECK(Pick(list, 7.0) == list.back());
    }
    CHECK(Pick({}, 0.5).empty());

    // 3. What a worn item grants: its 'passive' row, nothing from any other kind of row.
    std::vector<Stored> plain = {{"primary", "str"}, {"power", "Rend"}, {"socket", "sockets"}};
    CHECK(Granted(plain).empty());
    std::vector<Stored> amulet = {{"primary", "int"}, {"passive", "Weapons Master"}, {"power", "x"}};
    CHECK(Granted(amulet) == "Weapons Master");
    std::vector<Stored> twice = {{"passive", "A"}, {"passive", "B"}};
    CHECK(Granted(twice) == "A");
    CHECK(Granted(std::vector<Stored>{}).empty());

    // 4. What Has searches: the chosen passives, then each granted one once; a copy of a chosen one adds nothing.
    std::vector<std::string> chosen = {"Ruthless", "Weapons Master"};
    CHECK(Merge(chosen, {}) == chosen);
    CHECK(Merge(chosen, {"Bloodthirst"}) == (std::vector<std::string>{"Ruthless", "Weapons Master", "Bloodthirst"}));
    CHECK(Merge(chosen, {"Ruthless"}) == chosen);
    CHECK(Merge({}, {"Bloodthirst", "Bloodthirst", ""}) == (std::vector<std::string>{"Bloodthirst"}));
    // The player swaps the chosen copy away: the granted one is still there.
    CHECK(Merge({"Ruthless"}, {"Weapons Master"}) == (std::vector<std::string>{"Ruthless", "Weapons Master"}));

    if (failures)
        return 1;
    std::printf("granted passive OK (%zu classes, %u bases list the preset, %u roll)\n", byClass.size(), listing, rolling);
    return 0;
}
