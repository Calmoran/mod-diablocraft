/* Test double for a query result (step 3 harness only). */
#ifndef DC_TEST_QUERYRESULT_H
#define DC_TEST_QUERYRESULT_H

#include "Field.h"
#include <memory>
#include <vector>

class ResultSet
{
public:
    explicit ResultSet(std::vector<std::vector<Field>> rows) : _rows(std::move(rows)) {}

    Field* Fetch() { return _rows[_current].data(); }
    bool NextRow() { return ++_current < _rows.size(); }

private:
    std::vector<std::vector<Field>> _rows;
    std::size_t _current = 0;
};

using QueryResult = std::shared_ptr<ResultSet>;

#endif
