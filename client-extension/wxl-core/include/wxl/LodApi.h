// wxl-modern-engine's LOD quality coordinator, published for other extensions to consume via
// WXL_Api::GetInterface("wxl.lod", WXL_LOD_API_VERSION).
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

#ifndef WXL_LOD_API_H
#define WXL_LOD_API_H

#include <stdint.h>

// Terrain, placed-object and model level of detail are three different file formats read by three
// different extensions, but they share one axis: how aggressively to reduce detail right now. This
// interface is the one place that axis lives, so wxl-modern-adt/wxl-modern-m2/wxl-modern-wmo apply the
// same decision to their own format instead of each picking its own threshold.

#ifdef __cplusplus
extern "C" {
#endif

#define WXL_LOD_API_VERSION 1

typedef struct WXL_LodApi
{
    uint32_t structSize;
    uint32_t apiVersion;

    /**
     * @brief Chooses which of a model's numbered view profiles (0 .. nViews-1) to load, from the
     *        live quality knob: a higher-detail profile only while quality clears that profile's own
     *        threshold, falling back to the lowest (coarsest) profile that does.
     * @param nViews profile count a model actually carries (MD20 numSkinProfiles), 1..4.
     * @return the chosen profile index, or 0 for nViews outside 1..4 (no way to choose, use the
     *         model's own profile 0).
     */
    uint32_t(__cdecl* ModelSkinProfile)(uint32_t nViews);

    /// The live model-quality scalar (0..256) ModelSkinProfile reads. Read once per model load, not
    /// per frame; a config change only takes effect for models loaded afterward.
    uint32_t(__cdecl* ModelQuality)(void);
} WXL_LodApi;

#ifdef __cplusplus
}
#endif

#endif // WXL_LOD_API_H
