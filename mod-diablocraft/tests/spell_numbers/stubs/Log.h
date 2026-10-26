/* Test double for the core's logging (step 3 harness only): counts, prints nothing. */
#ifndef DC_TEST_LOG_H
#define DC_TEST_LOG_H

#include <cstddef>

namespace DCTestLog
{
    inline std::size_t errors = 0;

    template <typename... Args>
    inline void Error(Args&&...) { ++errors; }
}

#define LOG_ERROR(category, ...) DCTestLog::Error(__VA_ARGS__)

#endif
