# The client extension's unit tests, built and run by the client-extension CI job (Win32, like the
# client). Kept out of torment/: the extension loop compiles every .cpp under a module's folder.
cmake_minimum_required(VERSION 3.20)
project(torment_tests CXX)
set(CMAKE_CXX_STANDARD 20)  # as the module builds (wxl-core/CMakeLists.txt)

add_executable(key_table_test key_table_test.cpp)
target_include_directories(key_table_test PRIVATE ../torment)

add_executable(damage_text_test damage_text_test.cpp)
target_include_directories(damage_text_test PRIVATE ../torment)
