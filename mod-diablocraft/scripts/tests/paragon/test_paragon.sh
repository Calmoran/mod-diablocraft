#!/usr/bin/env bash
# Paragon C++ checks: CMake unit tests (paragon_tests.cpp and stat_tests.cpp) with Unix Makefiles and ctest.
# test_generate_sql.py, test_paragon_ids.py and test_paragon.lua are runner tests of their own.
#
#     mod-diablocraft/scripts/tests/paragon/test_paragon.sh
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
cd "$repo"
test_build='mod-diablocraft/build/tests-paragon'
cmake -S mod-diablocraft/scripts/tests/paragon -B "$test_build" -G 'Unix Makefiles' -DCMAKE_BUILD_TYPE=Release
cmake --build "$test_build" --parallel "${DC_BUILD_JOBS:-1}"
ctest --test-dir "$test_build" --output-on-failure --no-tests=error
