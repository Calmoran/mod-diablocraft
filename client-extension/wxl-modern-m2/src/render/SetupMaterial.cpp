// The scene renderer's per-batch alpha/material setup: publish OnM2SetupBatchAlpha after the native setter.
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
#include "CombinerPatch.hpp"

#include "engine/events/Event.hpp"

#include "offsets/game/M2.hpp"

#include <windows.h>

#include <cstdint>

namespace
{
    namespace ev = wxl::events;
    namespace m2 = wxl::offsets::game::m2;
    namespace combiner = wxl::runtime::m2combiner;

    m2::M2_SetupBatchAlphaFn g_origSetupAlpha = nullptr;

    /**
     * @brief Detours per-batch alpha/material setup, emitting OnM2SetupBatchAlpha with the model and blend.
     *
     * Runs after the native setter picks the alpha-test reference from the blend mode, so a
     * subscriber can re-push a different reference. The draw-context reads are guarded so a
     * malformed context never faults the render thread. Also arms CombinerPatch.cpp's own shader
     * substitution when the about-to-draw element is one a skin-finalize pass tagged for it -- this
     * is the only point in the per-batch draw sequence that already resolves both the live skin
     * profile (via the instance's model) and the element's own batch index, so tagging happens here
     * once instead of duplicating the model/skin walk in a second hook closer to the actual bind.
     * @param ctx  draw context.
     */
    void __fastcall hkSetupBatchAlpha(void* ctx)
    {
        g_origSetupAlpha(ctx);

        void*    model = nullptr;
        uint16_t blend = 0;
        __try
        {
            auto* dc   = static_cast<m2::DrawContext*>(ctx);
            void* inst = dc->instance;
            void* mat  = dc->material;
            if (inst) model = reinterpret_cast<void*>(static_cast<m2::M2Instance*>(inst)->model);
            if (mat)  blend = static_cast<m2::Material*>(mat)->blend;

            void* elem = dc->element;
            if (model && elem)
            {
                void* skin = static_cast<m2::M2Model*>(model)->skin;
                const uint32_t batchIndex =
                    *reinterpret_cast<const uint32_t*>(static_cast<uint8_t*>(elem) + m2::kOffElementBatchIndex);
                if (skin && combiner::IsAddAlphaBatch(skin, batchIndex))
                    combiner::ArmNextBind();
            }
        }
        __except (EXCEPTION_EXECUTE_HANDLER) { model = nullptr; }

        if (model)
        {
            ev::M2SetupBatchAlphaArgs a{ model, blend };
            wxl_modern_m2::g_api->Emit(uint32_t(ev::Event::OnM2SetupBatchAlpha), &a);
        }
    }
}

namespace wxl_modern_m2
{
    bool InstallM2SetupBatchAlpha()
    {
        HookAttachByName("M2.SetupMaterial", &hkSetupBatchAlpha, &g_origSetupAlpha);
        return true;
    }
}
