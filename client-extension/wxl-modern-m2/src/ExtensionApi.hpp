// wxl-modern-m2: the extension-wide service table pointer and hook-install convenience, shared by every
// translation unit in this DLL.
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

#pragma once

#include "common/ExtensionConfig.hpp"
#include "wxl/FdidApi.h"
#include "wxl/M2ArenaApi.h"
#include "wxl/M2DrawApi.h"
#include "wxl/PluginApi.h"

#include <windows.h>

#include <cstdint>
#include <cstdlib>

/// See wxl-adt's ExtensionApi.hpp for the reasoning behind every pattern here: the core hands this
/// pointer to WXL_Load once and it lives for the process lifetime, so every detour installed later
/// reaches it through here rather than threading an `api` parameter through the call chain.
namespace wxl_modern_m2
{
    extern const WXL_Api* g_api;

    /// True builds the whole native M2 pipeline in; false is the single point that would leave the
    /// client on its stock M2 reader.
    inline constexpr bool kEnabled = true;

    // --- wxl-db2's FileDataID resolver, fetched lazily (extensions load alphabetically; wxl-db2
    // loads before wxl-modern-m2, so this always resolves once anything actually asks for a path). ----------
    extern const WXL_FdidApi* g_fdid;

    inline const WXL_FdidApi* Fdid()
    {
        if (!g_fdid)
            g_fdid = static_cast<const WXL_FdidApi*>(g_api->GetInterface("wxl.fdid", WXL_FDID_API_VERSION));
        return g_fdid;
    }

    inline const char* ResolveTexture(uint32_t fileDataId)
    {
        const WXL_FdidApi* fdid = Fdid();
        return fdid ? fdid->ResolveTexture(fileDataId) : nullptr;
    }

    // --- the core-owned large-M2 arena, published (Boot phase, before any extension loads) as
    // "wxl.m2arena" -- always present by the time wxl-modern-m2's own WXL_Load runs, but fetched through the
    // same lazy accessor as every other cross-binary service for one uniform pattern. -----------------
    extern const WXL_M2ArenaApi* g_arena;

    inline const WXL_M2ArenaApi* Arena()
    {
        if (!g_arena)
            g_arena = static_cast<const WXL_M2ArenaApi*>(g_api->GetInterface("wxl.m2arena", WXL_M2ARENA_API_VERSION));
        return g_arena;
    }

    /**
     * @brief Typed detour install over WXL_Api::HookAttach: detour and original share one function
     *        type, deduced, so wiring a hook to the wrong original no longer compiles. Mirrors
     *        wxl::hook::Install's own convenience overload, which this extension cannot link against.
     */
    template <class Fn>
    inline int HookAttach(const char* name, uintptr_t target, Fn* detour, Fn** original,
                          int priority = WXL_HOOK_DEFAULT_PRIORITY)
    {
        return g_api->HookAttach(name, target, reinterpret_cast<void*>(detour),
                                 reinterpret_cast<void**>(original), priority);
    }

    /**
     * @brief Typed detour install over WXL_Api::HookAttachByName: resolves `pointName` ("Namespace.Name")
     *        against the core's centralized HookPoints table instead of carrying a raw offset here.
     */
    template <class Fn>
    inline int HookAttachByName(const char* pointName, Fn* detour, Fn** original,
                                int priority = WXL_HOOK_DEFAULT_PRIORITY)
    {
        return g_api->HookAttachByName(pointName, reinterpret_cast<void*>(detour),
                                       reinterpret_cast<void**>(original), priority);
    }

    // Per-file installers, called from WXL_Load in Module.cpp.
    bool InstallM2CompatBones();       // BonePalette.cpp (gated)
    bool InstallEmitterBlend();        // EmitterBlend.cpp (gated)
    bool InstallM2PerFrameUpdate();    // PerFrameUpdate.cpp (gated)
    bool InstallM2SceneHitTestSort();  // HitTestSort.cpp (gated)
    bool InstallM2Draw();              // M2Draw.cpp (unconditional -- owns the DIP vtable slot)
    bool InstallM2SetupBatchAlpha();   // SetupMaterial.cpp (gated)
    bool InstallCombinerPatch();       // render/CombinerPatch.cpp (gated)
    bool InstallAnimUnwrap();          // AnimUnwrap.cpp (gated)
    bool InstallM2CompatLoader();      // CompatLoader.cpp (gated)
    bool InstallM2Native();            // NativeLoad.cpp (gated)
    bool InstallM2Memory();            // Memory.cpp (gated)
    bool InstallModernM2();            // ModernM2.cpp (gated)
    bool InstallM2LodVariant();        // load/LodModelVariant.cpp (unconditional -- inert until a
                                        // caller actually requests a synthetic per-tier name)

    inline bool ConfigTruthy(const char* raw, bool fallback) { return wxl::ext::config::Truthy(raw, fallback); }

    inline bool ConfigRaw(const char* name, char* buf, size_t cap)
    {
        return wxl::ext::config::Raw(name, buf, cap, "Extensions\\wxl-modern-m2\\wxl-modern-m2.cfg");
    }

    /// Feature toggle: an env var (falsy value disables) plus a .disable sentinel FILE (checked
    /// directly, independent of the .cfg mechanism), default ON.
    inline bool ConfigFlag(const char* envName, const char* disableFile)
    {
        char value[16] = {};
        if (ConfigRaw(envName, value, sizeof value) && !ConfigTruthy(value, true))
            return false;
        if (disableFile && GetFileAttributesA(disableFile) != INVALID_FILE_ATTRIBUTES)
            return false;
        return true;
    }

    inline uint64_t ConfigU64(const char* name, uint64_t fallback, uint64_t minValue, uint64_t maxValue)
    {
        char value[32] = {};
        if (!ConfigRaw(name, value, sizeof value)) return fallback;
        char* end = nullptr;
        const uint64_t parsed = std::strtoull(value, &end, 10);
        if (end == value) return fallback;
        if (parsed < minValue) return minValue;
        if (parsed > maxValue) return maxValue;
        return parsed;
    }

    inline uint32_t ConfigU32(const char* name, uint32_t fallback, uint32_t minValue, uint32_t maxValue)
    {
        return static_cast<uint32_t>(ConfigU64(name, fallback, minValue, maxValue));
    }

    /// Resolves a byte-count setting: an MB env var, then a KB one, then a default; a candidate
    /// outside [minKb, maxKb] is rejected and the next source tried.
    inline uint32_t ConfigBytesMbKb(const char* envMb, const char* envKb, uint32_t defBytes,
                                    uint32_t minKb, uint32_t maxKb)
    {
        char value[32] = {};
        if (ConfigRaw(envMb, value, sizeof value))
        {
            char* end = nullptr;
            const uint64_t mb = std::strtoull(value, &end, 10);
            const uint64_t kb = mb * 1024ull;
            if (end != value && kb >= minKb && kb <= maxKb)
                return static_cast<uint32_t>(kb * 1024ull);
        }
        if (ConfigRaw(envKb, value, sizeof value))
        {
            char* end = nullptr;
            const uint64_t kb = std::strtoull(value, &end, 10);
            if (end != value && kb >= minKb && kb <= maxKb)
                return static_cast<uint32_t>(kb * 1024ull);
        }
        return defBytes;
    }
}

// common/Log.hpp's WLOG_* macros need common/Log.cpp linked in, which is core/host/patcher-only (see
// its own doc comment) -- an extension has no such object file, so these route the same call-site
// syntax through WXL_Api::Log instead.
#define WLOG_TRACE(...) ::wxl_modern_m2::g_api->Log(WXL_LOG_TRACE, "wxl-modern-m2", __VA_ARGS__)
#define WLOG_DEBUG(...) ::wxl_modern_m2::g_api->Log(WXL_LOG_DEBUG, "wxl-modern-m2", __VA_ARGS__)
#define WLOG_INFO(...)  ::wxl_modern_m2::g_api->Log(WXL_LOG_INFO,  "wxl-modern-m2", __VA_ARGS__)
#define WLOG_WARN(...)  ::wxl_modern_m2::g_api->Log(WXL_LOG_WARN,  "wxl-modern-m2", __VA_ARGS__)
#define WLOG_ERROR(...) ::wxl_modern_m2::g_api->Log(WXL_LOG_ERROR, "wxl-modern-m2", __VA_ARGS__)
