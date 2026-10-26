/*
 * Offline harness for the spell-number accessor (spell rewrite step 3).
 *
 * It compiles the real `src/combat/dc_spell_numbers.cpp` against the test
 * doubles in `stubs/`, fills the fake spell store from the records the
 * generator published, and answers the queries the Python driver asks. The
 * conversions under test are therefore the module's own, not a copy of them.
 *
 *     harness <records.tsv> <exact.tsv> <queries.tsv>
 *
 * records.tsv: id, proc chance, stacks, charges, max targets, mana cost in
 *              Rage units, duration ms,
 *              then per effect: base points, die sides, amplitude, chain,
 *              radius minimum (-1 when the effect has no radius row), radius
 *              per level, radius maximum. The three radius numbers are
 *              deliberately different from each other: the generator picks a
 *              row by its minimum, so reading the wrong one must be visible.
 * exact.tsv:   spell, token, qualifier, value - the dc_spell_values rows.
 * queries.tsv: which, spell, token, qualifier - one answer per line, either
 *              the number or the word "absent".
 */

#include "../../src/combat/dc_spell_numbers.h"
#include "DatabaseEnv.h"
#include "SpellMgr.h"
#include <cstdio>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

namespace
{
    std::vector<std::vector<std::string>> ReadTable(char const* path)
    {
        std::vector<std::vector<std::string>> rows;
        std::ifstream stream(path);
        std::string line;
        while (std::getline(stream, line))
        {
            if (line.empty())
                continue;
            std::vector<std::string> cells;
            std::string cell;
            std::istringstream pieces(line);
            while (std::getline(pieces, cell, '\t'))
                cells.push_back(cell);
            rows.push_back(cells);
        }
        return rows;
    }

    std::vector<SpellRadiusEntry> radii;   // one per effect that has a radius
}

int main(int argc, char** argv)
{
    if (argc != 4)
    {
        std::cerr << "usage: harness <records.tsv> <exact.tsv> <queries.tsv>\n";
        return 2;
    }

    auto records = ReadTable(argv[1]);
    radii.reserve(records.size() * MAX_SPELL_EFFECTS);
    for (auto const& row : records)
    {
        SpellInfo& info = sSpellMgr->Add(uint32(std::stoul(row[0])));
        info.ProcChance = uint32(std::stoul(row[1]));
        info.StackAmount = uint32(std::stoul(row[2]));
        info.ProcCharges = uint32(std::stoul(row[3]));
        info.MaxAffectedTargets = uint32(std::stoul(row[4]));
        info.ManaCost = uint32(std::stoul(row[5]));
        info.PowerType = uint32(std::stoul(row[30]));
        info.SpellFamilyName = uint32(std::stoul(row[31]));
        info.Duration = int32(std::stol(row[6]));
        info.RecoveryTime = uint32(std::stoul(row[7]));
        info.CategoryRecoveryTime = uint32(std::stoul(row[8]));
        for (std::size_t slot = 0; slot < MAX_SPELL_EFFECTS; ++slot)
        {
            std::size_t at = 9 + slot * 7;
            SpellEffectInfo& effect = info.Effects[slot];
            effect.BasePoints = int32(std::stol(row[at]));
            effect.DieSides = int32(std::stol(row[at + 1]));
            effect.Amplitude = uint32(std::stoul(row[at + 2]));
            effect.ChainTarget = uint32(std::stoul(row[at + 3]));
            float yards = std::stof(row[at + 4]);
            if (yards >= 0.0f)
            {
                radii.push_back(SpellRadiusEntry{0, yards, std::stof(row[at + 5]),
                                                 std::stof(row[at + 6])});
                effect.RadiusEntry = &radii.back();
            }
        }
    }

    for (auto const& row : ReadTable(argv[2]))
        WorldDatabase.Rows.push_back({Field{row[0]}, Field{row[1]},
                                      Field{row.size() > 2 ? row[2] : std::string()},
                                      Field{row.size() > 3 ? row[3] : row[2]}});

    for (auto const& row : ReadTable(argv[3]))
    {
        std::string const& which = row[0];
        uint32_t spell = uint32_t(std::stoul(row[1]));
        std::string const& token = row[2];
        std::string qualifier = row.size() > 3 ? row[3] : std::string();

        std::optional<double> value;
        if (which == "get")
            value = DC::Combat::Numbers::Get(spell, token, qualifier);
        else if (which == "own")
            value = DC::Combat::Numbers::Own(spell, token, qualifier);
        else if (which == "inherited")
            value = DC::Combat::Numbers::Inherited(spell, token, qualifier);
        else if (which == "has")
        {
            std::printf("%s\n", DC::Combat::Numbers::Has(spell, token, qualifier) ? "yes" : "no");
            continue;
        }
        else if (which == "num")
        {
            std::printf("%.6f\n", DC::Combat::Numbers::Num(spell, token, qualifier));
            continue;
        }
        else
        {
            std::cerr << "unknown query " << which << "\n";
            return 2;
        }

        if (value)
            std::printf("%.6f\n", *value);
        else
            std::printf("absent\n");
    }

    std::fprintf(stderr, "exact rows loaded: %zu\n", DC::Combat::Numbers::ExactCount());
    return 0;
}
