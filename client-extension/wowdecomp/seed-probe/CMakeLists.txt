# The version-proof probe: the client's own checksum code (wowdecomp's Win64/OsVersionHash.cpp, with the
# patch series applied) linked into a tiny exe with the linker's defaults for x64, which are the rebuilt
# client's (ASLR with high entropy), so it loads the way WowClient64.exe loads.
cmake_minimum_required(VERSION 3.20)
project(version_proof_probe CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if (NOT WOWDECOMP_DIR)
    message(FATAL_ERROR "set WOWDECOMP_DIR to the patched wowdecomp checkout")
endif ()
file(TO_CMAKE_PATH "${WOWDECOMP_DIR}" WOWDECOMP_DIR)
add_executable(version_proof_probe version_proof_probe.cpp ${WOWDECOMP_DIR}/Engine/Source/Os/Win64/OsVersionHash.cpp)
target_include_directories(version_proof_probe PRIVATE ${WOWDECOMP_DIR})
# The definitions wowdecomp's own CMakeLists.txt sets for an x64 build.
target_compile_definitions(version_proof_probe PRIVATE WOWDECOMP_ARCH_64=1 WIN32 _WINDOWS NOMINMAX WIN32_LEAN_AND_MEAN _CRT_SECURE_NO_WARNINGS)
# OsFileVersionInfo in the same file calls the version API.
target_link_libraries(version_proof_probe PRIVATE version)
