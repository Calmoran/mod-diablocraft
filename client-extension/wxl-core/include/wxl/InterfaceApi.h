// The wxl-interface service interface: what wxl-interface-reforged publishes for any other extension
// to consume via WXL_Api::GetInterface("wxl.interface", WXL_INTERFACE_API_VERSION).
// Copyright (C) 2026 WarcraftXL
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with this program. If not, see <https://www.gnu.org/licenses/>.

#ifndef WXL_INTERFACE_API_H
#define WXL_INTERFACE_API_H

#include <stddef.h>
#include <stdint.h>

// The atlas map is a tree of std::string and std::unordered_map, which is a type that cannot cross a
// module boundary by value: the memory is allocated by wxl-interface-reforged's CRT and would be
// freed by the consumer's, and the layout depends on _ITERATOR_DEBUG_LEVEL and on which CRT flavour
// each binary was linked against. So what crosses is a PLAIN STRUCT THE CALLER OWNS, filled by a
// call into wxl-interface-reforged -- the one binary whose STL layout can walk the map -- with only
// plain values (const char*, uint16_t, float, uint32_t) in it. Plain C with __cdecl throughout, same
// reasoning as PluginApi.h.

#ifdef __cplusplus
extern "C" {
#endif

/// Bumped whenever the layout below changes. Independent of WXL_API_VERSION: a consumer records what
/// it compiled against and GetInterface only matches an exact version.
#define WXL_INTERFACE_API_VERSION 1

/// One atlas member, as GetAtlasInfo fills it in.
///
/// `file` is owned by wxl-interface-reforged and valid for the process lifetime, spelled the way the
/// stock texture loader takes a name: backslashes, and no .blp suffix. The texture coordinates are
/// the member's pixel rectangle divided by its atlas's dimensions, which is the form SetTexCoord
/// takes; width and height are the member's own pixel size, which is what a caller asking to be
/// sized to the atlas uses. The two tiling flags are 0 or 1 -- int rather than a C++ bool, which has
/// no guaranteed representation across a compiler boundary.
typedef struct WXL_AtlasInfo
{
    const char* file;
    uint16_t    width;
    uint16_t    height;
    float       left;
    float       right;
    float       top;
    float       bottom;
    int         tilesHorizontally;
    int         tilesVertically;
} WXL_AtlasInfo;

typedef struct WXL_InterfaceApi
{
    uint32_t structSize;
    uint32_t apiVersion;

    /**
     * @brief Looks one atlas member up by the name retail calls it.
     * @param name  atlas member name, MATCHED WITHOUT REGARD TO CASE, as retail matches it. A NULL
     *              or empty name is a legal argument and is a miss.
     * @param out   filled in on a hit; left untouched on a miss. NULL is legal and turns the call
     *              into a test for whether the name is known.
     * @return nonzero when @p name named a member.
     *
     * The first call builds the map out of the client's atlas tables. A table that cannot be decoded
     * leaves the map empty, in which case every call is a miss -- there is no state in which a hit
     * hands back a member pointing at nothing.
     */
    int(__cdecl* GetAtlasInfo)(const char* name, WXL_AtlasInfo* out);

    /**
     * @brief How many atlas members the map holds.
     * @return the count, or 0 before the first GetAtlasInfo call and after a failed table load.
     *
     * Does not itself build the map: a consumer that wants the count built asks for a member first.
     */
    uint32_t(__cdecl* AtlasCount)(void);
} WXL_InterfaceApi;

#ifdef __cplusplus
}
#endif

#endif // WXL_INTERFACE_API_H
