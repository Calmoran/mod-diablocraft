// wxl-db2's ModelFileData table, published for other extensions to consume via
// WXL_Api::GetInterface("wxl.modeldata", WXL_MODEL_DATA_API_VERSION).
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

#ifndef WXL_MODEL_DATA_API_H
#define WXL_MODEL_DATA_API_H

#include <stdint.h>

// The per-model facts the asset pipeline records next to a model rather than inside it: how many
// reduced skin profiles it ships, its bounding box, and the material set it draws from. A consumer
// that needs "how far can this model be degraded" asks here instead of probing the archive for
// sibling files -- the table is the authority, an existence probe is only ever a guess about it.
//
// Loading is lazy: the first Lookup/FileDataIdForPath call decodes the table, so an extension that
// never asks pays nothing. Every call is safe before that point and after a failed load.

#ifdef __cplusplus
extern "C" {
#endif

#define WXL_MODEL_DATA_API_VERSION 1

typedef struct WXL_ModelFileData
{
    uint32_t fileDataId;
    uint32_t flags;
    /// Reduced skin profiles this model ships beyond its base one; 0 means it has none.
    uint32_t lodCount;
    uint32_t modelResourcesId;
    float    geoBox[6];
} WXL_ModelFileData;

typedef struct WXL_ModelDataApi
{
    uint32_t structSize;
    uint32_t apiVersion;

    /// 1 once the table decoded. Triggers the load on first call.
    int(__cdecl* Loaded)(void);
    /// The decoder's own words when the load refused; "" otherwise. Never NULL.
    const char*(__cdecl* Error)(void);
    uint32_t(__cdecl* RowCount)(void);

    /**
     * @brief Model path -> FileDataID, the reverse of WXL_FdidApi::ResolveModel.
     * @param modelPath either separator, any case, with or without an extension.
     * @return 0 when the path is not in the client's path table.
     */
    uint32_t(__cdecl* FileDataIdForPath)(const char* modelPath);

    /// @return 0 when the table holds no row for this id (out untouched).
    int(__cdecl* Lookup)(uint32_t fileDataId, WXL_ModelFileData* out);

    /// FileDataIdForPath + Lookup in one call. @return 0 when either step misses.
    int(__cdecl* LookupByPath)(const char* modelPath, WXL_ModelFileData* out);
} WXL_ModelDataApi;

#ifdef __cplusplus
}
#endif

#endif // WXL_MODEL_DATA_API_H
