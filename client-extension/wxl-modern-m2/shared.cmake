# Declares this extension's cross-target-shared sources (src/engine/assets/shared/...) to the root
# CMakeLists.txt extension loop. Included with OPTIONAL, so an extension with no shared sources simply
# has no such file. Populate WXL_EXT_SHARED_SRC; the loop resets it before each include and appends it
# to the extension's own sources.
file(GLOB_RECURSE WXL_EXT_SHARED_SRC CONFIGURE_DEPENDS
     "${CMAKE_CURRENT_SOURCE_DIR}/src/engine/assets/shared/models/m2/*.cpp")
