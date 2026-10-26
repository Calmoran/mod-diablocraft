// wxl-db2's retail lighting-table service, published for other extensions to consume via
// WXL_Api::GetInterface("wxl.light", WXL_LIGHT_API_VERSION).
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

#ifndef WXL_LIGHT_API_H
#define WXL_LIGHT_API_H

#include <stdint.h>

// The complete lighting the game's own tables prescribe for one place and one moment, mirroring
// wxl_db2::light::LightState field for field. Plain C, POD only (no STL types cross the boundary),
// same reasoning as every other published interface in this SDK.

#ifdef __cplusplus
extern "C" {
#endif

#define WXL_LIGHT_API_VERSION 1

typedef struct WXL_LightRgb
{
    float r, g, b;
} WXL_LightRgb;

typedef struct WXL_LightState
{
    int      valid;
    uint32_t lightId;   ///< winning Light row
    uint32_t paramsId;  ///< its clear-weather LightParams set

    WXL_LightRgb direct, ambient;
    WXL_LightRgb skyTop, skyMiddle, skyBand1, skyBand2, skySmog, skyFog;
    WXL_LightRgb sunColor, cloudSunColor, cloudEmissive, cloudLayer1Ambient, cloudLayer2Ambient;
    WXL_LightRgb oceanClose, oceanFar, riverClose, riverFar;
    WXL_LightRgb horizonAmbient, groundAmbient;
    WXL_LightRgb endFogColor, sunFogColor, fogHeightColor, endFogHeightColor;

    float shadowOpacity;
    float fogEnd, fogScaler, fogDensity;
    float fogHeight, fogHeightScaler, fogHeightDensity;
    float fogZScalar, mainFogStartDist, mainFogEndDist;
    float sunFogAngle, sunFogStrength, cloudDensity;
    float endFogColorDistance, fogStartOffset;
    float fogHeightCoefficients[4];
    float mainFogCoefficients[4];
    float heightDensityFogCoeff[4];

    uint32_t colorGradingFdid, darkerColorGradingFdid;

    /// From LightParams.
    uint32_t lightSkyboxId, cloudTypeId, paramsFlags;
    float glow, highlightSky;
    float waterShallowAlpha, waterDeepAlpha;
    float oceanShallowAlpha, oceanDeepAlpha;
    float sunPolar, sunAzimuth;
    float sunAttenuationStart, sunAttenuationEnd;
    float overrideSunPosition[3];
    float overrideCelestialSphere[3];

    /// From LightSkybox.
    uint32_t skyboxFdid, celestialSkyboxFdid, skyboxFlags;
} WXL_LightState;

typedef struct WXL_LightApi
{
    uint32_t structSize;
    uint32_t apiVersion;

    /// True once every required table (light/lightdata/lightparams) decoded; lightskybox is optional.
    int(__cdecl* StatusLoaded)(void);
    /// True once a load was attempted and a required table refused. Mutually exclusive with Loaded.
    int(__cdecl* StatusFailed)(void);
    /// The decoder's own words when StatusFailed is true; stable for the process, empty otherwise.
    const char*(__cdecl* StatusError)(void);
    void(__cdecl* StatusCounts)(uint32_t* lights, uint32_t* data, uint32_t* params, uint32_t* skyboxes);

    /// The state at (map, world position, day time in half-minutes 0..2880). First call triggers the
    /// load. Returns 0 (out untouched beyond a zeroed valid field) when the tables carry nothing for
    /// the map.
    int(__cdecl* Evaluate)(int mapId, const float worldPos[3], float timeHalfMinutes, WXL_LightState* out);

    /// What the light IS: the state where the camera stands, at the world's own time of day,
    /// recomputed once a frame. Returns 0 before the first frame of a world, or whenever Evaluate
    /// would.
    int(__cdecl* Current)(WXL_LightState* out);

    /// Evaluates as another map id, for a world built from a retail map's terrain: the tables key on
    /// the RETAIL id, which a custom map does not carry. Negative (the default) follows the live map.
    /// Applies to Current, not to Evaluate.
    void(__cdecl* SetMapOverride)(int mapId);
    int(__cdecl* MapOverride)(void);

    /// Holds Current at one moment of the day instead of following the world clock. Negative (the
    /// default) follows it. In half-minutes, same scale as Evaluate.
    void(__cdecl* SetTimeOverride)(float timeHalfMinutes);
    float(__cdecl* TimeOverride)(void);

    /// How far the world's own day has run, in those same half-minutes. What Current follows unless
    /// a time override holds it.
    float(__cdecl* WorldTimeHalfMinutes)(void);
} WXL_LightApi;

#ifdef __cplusplus
}
#endif

#endif // WXL_LIGHT_API_H
