// M2 ground-shadow draw: diagnosis of, and in-place guard against, camera-locked shadow sections.
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

#include "ShadowSpace.hpp"

#include "../ExtensionApi.hpp"
#include "engine/assets/shared/models/m2/M2Format.hpp"
#include "game/M2.hpp"
#include "offsets/game/M2.hpp"

#include <windows.h>

#include <atomic>
#include <cmath>
#include <cstdint>

namespace
{
    namespace off = wxl::offsets::game::m2;
    namespace fmt = wxl::structure::m2;

    bool              g_armed = false;
    std::atomic<bool> g_enabled{ true };

    std::atomic<uint32_t> g_statDraws{ 0 };
    std::atomic<uint32_t> g_statInflZero{ 0 };
    std::atomic<uint32_t> g_statInflFixed{ 0 };
    std::atomic<uint32_t> g_statOverride{ 0 };
    std::atomic<uint32_t> g_statStaleAnim{ 0 };
    std::atomic<uint32_t> g_statPaletteMismatch{ 0 };
    std::atomic<uint32_t> g_statFaults{ 0 };

    void ProbeShadowDraw(void* instance, void* section)
    {
        auto* inst = static_cast<off::M2Instance*>(instance);
        auto* shared = reinterpret_cast<uint8_t*>(inst->model);
        if (!shared) return;

        auto* sec = static_cast<fmt::M2SkinSection*>(section);

        // --- the value that actually selects the shadow vertex program ---
        const uint16_t inflDraw = sec->boneInfluences;
        const uint32_t ovr = *reinterpret_cast<const uint32_t*>(
            reinterpret_cast<const uint8_t*>(inst) + off::kOffInstSectionOverride);

        // --- which array is this section in: the shared runtime's own +0x18C copy, or somewhere else? ---
        auto* copyBase = *reinterpret_cast<uint8_t**>(shared + off::kOffModelSubmeshBuf);
        int32_t secIdx = -1;
        if (copyBase)
        {
            const ptrdiff_t delta = reinterpret_cast<uint8_t*>(sec) - copyBase;
            if (delta >= 0 && (delta % static_cast<ptrdiff_t>(sizeof(fmt::M2SkinSection))) == 0)
                secIdx = static_cast<int32_t>(delta / static_cast<ptrdiff_t>(sizeof(fmt::M2SkinSection)));
        }
        // ...and what the LIVE skin says at that same index, which is what FixSubmeshes patched.
        uint16_t inflSkin = 0xFFFFu;
        auto* skin = static_cast<wxl::game::m2::M2SkinProfile*>(
            reinterpret_cast<off::M2Model*>(shared)->skin);
        if (skin && skin->submeshes && secIdx >= 0 && static_cast<uint32_t>(secIdx) < skin->submeshCount)
            inflSkin = skin->submeshes[secIdx].boneInfluences;

        // --- palette freshness AND space, in one check ---
        const uint32_t lastAnim = inst->lastAnimFrame;
        uint32_t frame = 0xFFFFFFFFu;
        if (auto* scene = reinterpret_cast<off::M2SceneClock*>(inst->scene))
            frame = scene->frame;
        bool palMatchesRoot = true;
        if (const auto* pal = reinterpret_cast<const float*>(inst->bonePalettePtr))
        {
            const float* root = inst->viewRoot;
            palMatchesRoot = (std::fabs(pal[12] - root[12]) + std::fabs(pal[13] - root[13]) +
                              std::fabs(pal[14] - root[14])) < 0.01f;
        }

        if (inflDraw == 0)        g_statInflZero.fetch_add(1, std::memory_order_relaxed);
        if (ovr != 0)             g_statOverride.fetch_add(1, std::memory_order_relaxed);
        if (lastAnim != frame)    g_statStaleAnim.fetch_add(1, std::memory_order_relaxed);
        if (!palMatchesRoot)      g_statPaletteMismatch.fetch_add(1, std::memory_order_relaxed);

        // --- the intervention, folded into the same pass ---
        // A zero here means this draw takes the shadow variant that never applies c14..c16. The section
        // is a runtime copy, so lifting it to 1 is exactly what FixSubmeshes was supposed to guarantee;
        // doing it at the draw closes every path that could have bypassed it. Never touches the file.
        if (inflDraw == 0 && sec->indexCount != 0 && g_enabled.load(std::memory_order_relaxed))
        {
            sec->boneInfluences = 1;
            const uint32_t n = g_statInflFixed.fetch_add(1, std::memory_order_relaxed) + 1;
            if (n <= 8)
            {
                const char* stem = wxl::game::m2::M2Model(shared).GetPathStem();
                WLOG_WARN("m2shadow: lifted boneInfluences 0 -> 1 at the shadow draw for '%s' sec=%d "
                          "(inflSkin=%u ovr=0x%X) -- this section would have been camera-locked",
                          stem ? stem : "(no stem)", secIdx, inflSkin, ovr);
            }
        }
    }
}

namespace wxl::runtime::m2shadow
{
    void Arm(bool hookInstalled)
    {
        g_armed = hookInstalled;
        WLOG_INFO("m2shadow: shadow-draw probe + boneInfluences guard %s (rides the existing 0x%08X detour)",
                  hookInstalled ? "armed" : "NOT armed -- host hook missing",
                  static_cast<unsigned>(off::kRenderBatchShadowMap));
    }

    void OnShadowBatch(void* instance, void* section)
    {
        g_statDraws.fetch_add(1, std::memory_order_relaxed);
        if (!instance || !section) return;
        __try { ProbeShadowDraw(instance, section); }
        __except (EXCEPTION_EXECUTE_HANDLER) { g_statFaults.fetch_add(1, std::memory_order_relaxed); }
    }

    bool Installed() { return g_armed; }
    bool Enabled()   { return g_enabled.load(std::memory_order_relaxed); }

    void SetEnabled(bool on)
    {
        // Log only on an actual transition: the Lua panel writes the checkbox back every frame.
        if (g_enabled.exchange(on, std::memory_order_relaxed) != on)
            WLOG_INFO("m2shadow: boneInfluences guard %s", on ? "ENABLED" : "disabled (stock)");
    }

    Stats GetStats()
    {
        Stats s{};
        s.shadowDraws      = g_statDraws.load(std::memory_order_relaxed);
        s.influencesZero   = g_statInflZero.load(std::memory_order_relaxed);
        s.influencesFixed  = g_statInflFixed.load(std::memory_order_relaxed);
        s.overrideSections = g_statOverride.load(std::memory_order_relaxed);
        s.staleAnim        = g_statStaleAnim.load(std::memory_order_relaxed);
        s.paletteMismatch  = g_statPaletteMismatch.load(std::memory_order_relaxed);
        s.faults           = g_statFaults.load(std::memory_order_relaxed);
        return s;
    }
}
