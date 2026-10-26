// B1 on the production path, not beside it.
//
// The first version of this task tested loot eligibility by RESTATING the
// predicate in Python and handing it a literal lower-case "barbarian". That
// passed while the shipped code was broken: the generated class map published
// the display label "Barbarian", dc_loot compared it case-sensitively against
// lower-case sheet tokens, and 202 of 1114 base items changed pool.
//
// So this compiles the production predicate - DC::RollClass::Eligible, which
// dc_loot.cpp's PickBaseItem calls since diablocraft-class-roll-rules - and
// drives it with the key read out of the GENERATED SQL. Nothing here restates
// the rule, and nothing here supplies the key by hand. The old "other class"
// pool is gone: an off-class drop rolls that class's own pool.
#include "dc_loot_extract.h"

#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

namespace
{
    struct Expectation
    {
        std::string usable, designation;
        bool own = false;
    };

    std::string Trim(std::string text)
    {
        while (!text.empty() && (text.back() == '\r' || text.back() == '\n'))
            text.pop_back();
        return text;
    }

    std::vector<Expectation> ReadItems(char const* path, std::string& error)
    {
        std::vector<Expectation> items;
        std::ifstream input(path);
        if (!input)
        {
            error = "cannot open items file";
            return items;
        }
        std::string line;
        while (std::getline(input, line))
        {
            line = Trim(line);
            if (line.empty())
                continue;
            // usable \t designation \t own, the verdict being what the
            // pre-change lower-case predicate produced for this row.
            std::istringstream fields(line);
            Expectation row;
            std::string own;
            std::getline(fields, row.usable, '\t');
            std::getline(fields, row.designation, '\t');
            std::getline(fields, own, '\t');
            row.own = own == "1";
            items.push_back(row);
        }
        return items;
    }
} // namespace

int main(int argc, char** argv)
{
    if (argc < 3)
    {
        std::cerr << "usage: eligibility_harness <items.tsv> <key.txt>\n";
        return 2;
    }
    std::string error;
    std::vector<Expectation> const items = ReadItems(argv[1], error);
    if (!error.empty() || items.empty())
    {
        std::cerr << "no items to check: " << error << "\n";
        return 2;
    }

    std::ifstream keyFile(argv[2]);
    std::string key;
    std::getline(keyFile, key);
    key = Trim(key);
    if (key.empty())
    {
        std::cerr << "no class key\n";
        return 2;
    }

    unsigned ownCount = 0, mismatches = 0;
    for (Expectation const& expected : items)
    {
        BaseItem item;
        item.usable = expected.usable;
        item.designation = expected.designation;
        bool const own = OwnClassItem(item, key);
        ownCount += own;
        if (own != expected.own)
        {
            if (mismatches < 5)
                std::cerr << "mismatch: usable=\"" << expected.usable << "\" designation=\"" << expected.designation
                          << "\" own " << own << " want " << expected.own << "\n";
            ++mismatches;
        }
    }

    std::cout << "key=" << key << " items=" << items.size() << " own=" << ownCount
              << " mismatches=" << mismatches << "\n";
    return mismatches ? 1 : 0;
}
