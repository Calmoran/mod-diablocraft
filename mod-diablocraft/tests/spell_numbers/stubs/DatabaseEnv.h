/* Test double for the world database (step 3 harness only). */
#ifndef DC_TEST_DATABASEENV_H
#define DC_TEST_DATABASEENV_H

#include "Field.h"
#include "QueryResult.h"
#include <string>
#include <vector>

class TestWorldDatabase
{
public:
    // Rows the harness loaded from the generated SQL, returned for the one
    // query the accessor makes.
    std::vector<std::vector<Field>> Rows;

    QueryResult Query(std::string const&) const
    {
        return Rows.empty() ? QueryResult() : std::make_shared<ResultSet>(Rows);
    }
};

inline TestWorldDatabase WorldDatabase;

#endif
