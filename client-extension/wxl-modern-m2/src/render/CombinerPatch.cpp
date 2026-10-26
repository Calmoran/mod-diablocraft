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
#include "shaders/CombinersModAddAlphaPs.h"
#include "shaders/CombinersModAddAlphaVs.h"

#include "game/Gx.hpp"
#include "offsets/engine/Gx.hpp"
#include "offsets/engine/Shader.hpp"

#include <windows.h>
#include <d3d9.h>

#include <cstdint>
#include <cstring>
#include <unordered_map>
#include <unordered_set>

namespace
{
    namespace shoff = wxl::offsets::engine::shader;
    namespace gxoff  = wxl::offsets::engine::gx;

    using GxSetFn = void(__fastcall*)(void* device, void* edx, uint32_t selector, void* value);

    bool g_enabled = true;
    shoff::EffectBindFn g_origEffectBind = nullptr;

    // (skin -> tagged batch indices). Written once per batch at skin finalize; read once per draw.
    std::unordered_map<void*, std::unordered_set<uint32_t>> g_tagged;

    // Frame stash: armed by SetupMaterial.cpp's hook for the batch about to bind, consumed by the very
    // next EffectBind call. Render is single-threaded, so a plain flag is enough -- no atomics.
    bool g_pendingBind = false;

    void* g_vsWrapper = nullptr; // lazily minted, cached for the process lifetime
    void* g_psWrapper = nullptr;
    bool  g_mintFailed = false;

    /**
     * @brief Mints the minimal GxState-bindable shader object the deferred flush reads: creates the
     *        live D3D9 shader from the hardcoded bytecode and wraps it in the same layout a native
     *        CGxShader exposes (live handle, created flag, bytecode pointer/length).
     * @param bytecode  hardcoded shader bytecode (a `kCombinersModAddAlpha{Vs,Ps}` array).
     * @param len       byte length of that array.
     * @param vertex    true mints a vertex shader, false a pixel shader.
     * @return the wrapper, or null if the device is not up or creation failed.
     */
    void* MintWrapper(const void* bytecode, uint32_t len, bool vertex)
    {
        auto* dev = static_cast<IDirect3DDevice9*>(wxl::game::gx::RawDevice());
        if (!dev) return nullptr;

        void* handle = nullptr;
        if (vertex)
        {
            IDirect3DVertexShader9* vs = nullptr;
            if (FAILED(dev->CreateVertexShader(static_cast<const DWORD*>(bytecode), &vs)) || !vs)
                return nullptr;
            handle = vs;
        }
        else
        {
            IDirect3DPixelShader9* ps = nullptr;
            if (FAILED(dev->CreatePixelShader(static_cast<const DWORD*>(bytecode), &ps)) || !ps)
                return nullptr;
            handle = ps;
        }

        auto* copy = new uint8_t[len];
        std::memcpy(copy, bytecode, len);

        auto* w = new uint8_t[shoff::kCgxShaderWrapBytes]();
        *reinterpret_cast<void**>(w + shoff::kCgxShaderHandle)  = handle;
        *reinterpret_cast<uint32_t*>(w + shoff::kCgxShaderCreated) = 1;
        *reinterpret_cast<uint32_t*>(w + shoff::kCgxShaderByteLen) = len;
        *reinterpret_cast<const void**>(w + shoff::kCgxShaderBytePtr) = copy;
        return w;
    }

    void __cdecl hkEffectBind(uint32_t vtxIdx, uint32_t pixIdx)
    {
        g_origEffectBind(vtxIdx, pixIdx);

        if (!g_pendingBind) return;
        g_pendingBind = false;
        if (!g_enabled) return;

        if (!g_vsWrapper && !g_mintFailed)
        {
            g_vsWrapper = MintWrapper(kCombinersModAddAlphaVs, sizeof(kCombinersModAddAlphaVs), true);
            g_psWrapper = MintWrapper(kCombinersModAddAlphaPs, sizeof(kCombinersModAddAlphaPs), false);
            g_mintFailed = (!g_vsWrapper || !g_psWrapper);
            if (g_mintFailed) WLOG_WARN("m2-combiner: shader creation failed, leaving batches on native blend");
        }
        if (!g_vsWrapper || !g_psWrapper) return;

        void* gxDev = *reinterpret_cast<void**>(gxoff::kGxDevicePtr);
        if (!gxDev) return;
        auto* set = reinterpret_cast<GxSetFn>(shoff::kGxStateSet);
        set(gxDev, nullptr, shoff::kStateVertexShader, g_vsWrapper);
        set(gxDev, nullptr, shoff::kStatePixelShader,  g_psWrapper);
    }
}

namespace wxl::runtime::m2combiner
{
    void MarkAddAlphaBatch(void* skin, uint32_t batchIndex)
    {
        if (!skin) return;
        g_tagged[skin].insert(batchIndex);
    }

    bool IsAddAlphaBatch(void* skin, uint32_t batchIndex)
    {
        if (!skin || g_tagged.empty()) return false;
        auto it = g_tagged.find(skin);
        return it != g_tagged.end() && it->second.count(batchIndex) != 0;
    }

    void ArmNextBind() { g_pendingBind = true; }
}

namespace wxl_modern_m2
{
    bool InstallCombinerPatch()
    {
        g_enabled = ConfigU32("WXL_M2_COMBINER_PATCH_ENABLED", 1, 0, 1) != 0;
        HookAttachByName("Shader.EffectBind", &hkEffectBind, &g_origEffectBind);
        WLOG_INFO("m2-combiner: installed (enabled=%d)", g_enabled ? 1 : 0);
        return true;
    }
}
