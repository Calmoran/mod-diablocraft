// wxl-modern-m2: native M2 (MD21/M3) reader + M2 render/compat pipeline, as an out-of-core extension.
// Entry point.
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

#include "ExtensionApi.hpp"

const WXL_PluginInfo* __cdecl WXL_Query(void)
{
    static const WXL_PluginInfo info = {
        sizeof(WXL_PluginInfo),
        WXL_API_VERSION,
        "wxl-modern-m2",
        1,
        WXL_CLIENT_BUILD,
    };
    return &info;
}

int __cdecl WXL_Load(const WXL_Api* api)
{
    if (!api || api->apiVersion != WXL_API_VERSION) return 0;

    wxl_modern_m2::g_api = api;

    // M2Draw is unconditional: the 32-bit start-index expansion and ribbon multi-texture fold are
    // stock-compatibility fixes, not modern-only features (ex core render's InstallM2DrawHooks(),
    // always called regardless of modernM2Support). It also owns the DrawIndexedPrimitive vtable slot
    // and publishes wxl.m2draw, so it must install before anything that might need that interface.
    wxl_modern_m2::InstallM2Draw();

    if constexpr (wxl_modern_m2::kEnabled)
    {
        wxl_modern_m2::InstallM2Memory();
        wxl_modern_m2::InstallM2CompatBones();
        wxl_modern_m2::InstallEmitterBlend();
        wxl_modern_m2::InstallM2PerFrameUpdate();
        wxl_modern_m2::InstallM2SceneHitTestSort();
        wxl_modern_m2::InstallM2SetupBatchAlpha();
        wxl_modern_m2::InstallCombinerPatch();
        wxl_modern_m2::InstallAnimUnwrap();
        wxl_modern_m2::InstallM2CompatLoader();
        wxl_modern_m2::InstallM2Native();
        wxl_modern_m2::InstallModernM2();
        wxl_modern_m2::InstallM2LodVariant();
    }

    api->Log(WXL_LOG_INFO, "wxl-modern-m2", "native M2 reader active");
    return 1;
}
