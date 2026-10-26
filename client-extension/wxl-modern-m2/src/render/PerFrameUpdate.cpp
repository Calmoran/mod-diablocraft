// Per-render-context per-frame model update: publish OnM2PerFrameUpdate per visible M2 each frame.
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

#include "../ExtensionApi.hpp"

#include "engine/events/Event.hpp"

#include "offsets/game/M2.hpp"

#include <windows.h>

namespace
{
    namespace ev = wxl::events;
    namespace m2 = wxl::offsets::game::m2;

    m2::M2_PerFrameUpdateFn g_origM2PerFrame = nullptr;

    /**
     * @brief Detours the per-render-ctx M2 scene-graph update, emitting OnM2PerFrameUpdate per visible M2.
     *
     * Fires recursively through the scene graph once per visible M2 render context per frame -- this
     * is the correct hook point for per-frame bone-matrix copy and geoset (index buffer) filtering,
     * both of which must run in step with the render context rather than once per EndScene.
     * @param renderCtx  the M2 render context being updated.
     * @param edx        thiscall dummy.
     */
    void __fastcall hkM2PerFrameUpdate(void* renderCtx, void* edx)
    {
        g_origM2PerFrame(renderCtx, edx);
        ev::M2PerFrameUpdateArgs a{ renderCtx };
        wxl_modern_m2::g_api->Emit(uint32_t(ev::Event::OnM2PerFrameUpdate), &a);
    }
}

namespace wxl_modern_m2
{
    bool InstallM2PerFrameUpdate()
    {
        HookAttachByName("M2.PerFrameUpdate", &hkM2PerFrameUpdate, &g_origM2PerFrame);
        return true;
    }
}
