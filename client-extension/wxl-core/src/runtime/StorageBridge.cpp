// Publishes wxl.storage: the client-side file-provider hook, made reachable by an out-of-core
// extension. Bridges WXL_ProvideFn (plain-C, ABI-safe) onto StorageHook's own
// std::vector<uint8_t>&-based ClientProvideFn, which an extension cannot call directly (no STL, no
// C++ ABI crosses the WXL_Api boundary -- see PluginApi.h).
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

#include "engine/storage/StorageHook.hpp"
#include "runtime/Extensions.hpp"

#include "engine/assets/shared/common/Text.hpp"
#include "wxl/StorageApi.h"

#include <mutex>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace
{
    using wxl::modern::assets::common::text::EndsWithCI;

    void __cdecl SinkWrite(void* ctx, const void* data, uint32_t len)
    {
        auto* out = static_cast<std::vector<uint8_t>*>(ctx);
        const auto* bytes = static_cast<const uint8_t*>(data);
        out->insert(out->end(), bytes, bytes + len);
    }

    // Every extension-registered provider funnels through the single ClientProvideFn this file
    // registers with StorageHook, so an extension registering a provider never needs the core rebuilt.
    std::mutex                        g_mutex;
    std::vector<WXL_ProvideFn>        g_providers;

    /** @brief Snapshots the registered extension providers, so none run under the registration lock. */
    std::vector<WXL_ProvideFn> ProvidersSnapshot()
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        return g_providers;
    }

    /** @brief The one ClientProvideFn StorageHook ever sees; fans out to every extension provider. */
    bool ClientProviderBridge(const char* name, std::vector<uint8_t>& out)
    {
        const WXL_ByteSink sink{ &out, &SinkWrite };
        for (WXL_ProvideFn fn : ProvidersSnapshot())
        {
            out.clear();
            if (fn(name, &sink)) return true;
        }
        out.clear();
        return false;
    }

    void __cdecl ApiRegisterClientProvider(WXL_ProvideFn fn)
    {
        if (!fn) return;
        std::lock_guard<std::mutex> lock(g_mutex);
        g_providers.push_back(fn);
    }

    // Extension-registered transforms, kept as (suffix, fn) pairs here rather than one-per-suffix in
    // StorageHook: StorageHook only ever sees the single bridge below, registered once per suffix.
    std::vector<std::pair<std::string, WXL_TransformFn>> g_transforms;

    std::vector<std::pair<std::string, WXL_TransformFn>> TransformsSnapshot()
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        return g_transforms;
    }

    /** @brief The ClientTransformFn StorageHook calls; fans out to every matching extension transform. */
    bool ClientTransformBridge(const char* name, const std::vector<uint8_t>& raw, std::vector<uint8_t>& out)
    {
        const std::string_view nameView(name);
        for (const auto& [suffix, fn] : TransformsSnapshot())
        {
            if (!EndsWithCI(nameView, suffix)) continue;
            out.clear();
            const WXL_ByteSink sink{ &out, &SinkWrite };
            if (fn(name, raw.data(), static_cast<uint32_t>(raw.size()), &sink)) return true;
        }
        out.clear();
        return false;
    }

    void __cdecl ApiRegisterClientTransform(const char* suffix, WXL_TransformFn fn)
    {
        if (!fn || !suffix || !*suffix) return;
        {
            std::lock_guard<std::mutex> lock(g_mutex);
            g_transforms.emplace_back(suffix, fn);
        }
        wxl::runtime::storage::RegisterClientTransform(suffix, &ClientTransformBridge);
    }

    // Extension-registered redirects. Same arrangement as providers: StorageHook only ever sees the
    // single bridge below, registered once.
    std::vector<WXL_RedirectFn> g_redirects;

    std::vector<WXL_RedirectFn> RedirectsSnapshot()
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        return g_redirects;
    }

    /// A path the client can express at all fits comfortably; a redirect that wants more than this is
    /// not naming a file the engine could have asked for.
    constexpr uint32_t kMaxRedirectName = 260;

    /** @brief The ClientRedirectFn StorageHook calls; offers the name to every extension redirect. */
    bool ClientRedirectBridge(const char* name, std::string& out)
    {
        char buffer[kMaxRedirectName];
        for (WXL_RedirectFn fn : RedirectsSnapshot())
        {
            buffer[0] = '\0';
            if (!fn(name, buffer, kMaxRedirectName)) continue;
            buffer[kMaxRedirectName - 1] = '\0'; // a redirect that filled the buffer still ends here
            if (!buffer[0]) continue;            // a claim with nothing in it is a decline
            out.assign(buffer);
            return true;
        }
        out.clear();
        return false;
    }

    void __cdecl ApiRegisterClientRedirect(WXL_RedirectFn fn)
    {
        if (!fn) return;
        std::lock_guard<std::mutex> lock(g_mutex);
        g_redirects.push_back(fn);
    }

    const WXL_StorageApi g_storageApi = {
        sizeof(WXL_StorageApi), WXL_STORAGE_API_VERSION, &ApiRegisterClientProvider,
        &ApiRegisterClientTransform, &ApiRegisterClientRedirect,
    };

    struct Registrar
    {
        Registrar()
        {
            wxl::runtime::storage::RegisterClientProvider(&ClientProviderBridge);
            wxl::runtime::storage::RegisterClientRedirect(&ClientRedirectBridge);
            wxl::runtime::extensions::PublishInterface(
                "wxl.storage", WXL_STORAGE_API_VERSION, const_cast<WXL_StorageApi*>(&g_storageApi));
        }
    } g_registrar;
}
