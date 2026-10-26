// The statements that delete a character's follower gear (src/items/dc_follower_gear_rule.h DeleteCharacterSql), one per line
// behind `SQL `, for the test to run against the fixture database. Argument: the character guid.
#include "../../src/items/dc_follower_gear_rule.h"

#include <cstdio>
#include <cstdlib>

int main(int argc, char** argv)
{
    if (argc != 2)
        return 2;
    for (std::string const& statement : DC::Items::FollowerGear::DeleteCharacterSql(std::uint32_t(std::strtoul(argv[1], nullptr, 10))))
        std::printf("SQL %s\n", statement.c_str());
    return 0;
}
