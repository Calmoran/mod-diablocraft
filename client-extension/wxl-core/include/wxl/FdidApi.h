// wxl-db2's FileDataID resolver, published for other extensions to consume via
// WXL_Api::GetInterface("wxl.fdid", WXL_FDID_API_VERSION).
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

#ifndef WXL_FDID_API_H
#define WXL_FDID_API_H

#include <stdint.h>

// Backed by TextureFilePath.db2 / ModelFilePath.db2 / TextureFileData.db2, read the same way every
// other client-side asset is: through the client's own already-mounted archive set (see wxl-db2's
// storage seam), no separate process involved. wxl-adt/wxl-wmo/wxl-m2 fetch this once at load and keep
// the pointer for the process lifetime, same as WXL_Api itself.

#ifdef __cplusplus
extern "C" {
#endif

#define WXL_FDID_API_VERSION 2

typedef struct WXL_FdidApi
{
    uint32_t structSize;
    uint32_t apiVersion;

    /// Texture FileDataID (MDID/MHID) -> backslash path, or NULL when unresolved.
    const char*(__cdecl* ResolveTexture)(uint32_t fileDataId);

    /// Model FileDataID (MDDF/MODF) -> backslash path, or NULL when unresolved.
    const char*(__cdecl* ResolveModel)(uint32_t fileDataId);

    /// MaterialResourcesID -> the texture that material names, or NULL. Materials are how the
    /// customization tables state what to paint: a recipe's layers carry one each, and nothing else
    /// turns one into a file. `usageHint` picks between the several files a material can list (a
    /// diffuse, a mask); the resolver falls back to the usual one and then to whatever exists.
    const char*(__cdecl* ResolveMaterialTexture)(uint32_t materialResourcesId, uint32_t usageHint);
} WXL_FdidApi;

#ifdef __cplusplus
}
#endif

#endif // WXL_FDID_API_H
