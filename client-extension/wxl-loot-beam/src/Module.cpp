// wxl-loot-beam: extension entry points and the overlay-panel bridge.
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

#include "LootBeam.hpp"

#include "wxl/PluginApi.h"
#include "wxl/EventScript.hpp"

#include <windows.h>

#include <new>
#include <string>

// The two exports the core resolves by name. WXL_Query must have no side effects (it describes the
// module before anything runs); WXL_Load receives the core's service table and is where the module is
// built. The event base class has no table until Bind is called, so the instance is constructed here,
// from WXL_Load, rather than at static-initialisation time.
namespace
{
    const WXL_Api* g_api = nullptr;
    wxl::scripts::loot_beam::LootBeam* g_module = nullptr;

    std::string ModuleDirectory()
    {
        HMODULE module = nullptr;
        if (!GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                                    GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                                reinterpret_cast<LPCSTR>(&ModuleDirectory), &module))
            return std::string();
        char path[MAX_PATH] = {};
        const DWORD n = GetModuleFileNameA(module, path, MAX_PATH);
        std::string dir(path, n);
        const size_t slash = dir.find_last_of("\\/");
        return slash == std::string::npos ? std::string() : dir.substr(0, slash + 1);
    }

    void __cdecl DrawPanel(void*)
    {
        if (g_api && g_module) g_module->DrawPanel(*g_api);
    }
}

extern "C" __declspec(dllexport) const WXL_PluginInfo* __cdecl WXL_Query()
{
    static const WXL_PluginInfo info = {
        sizeof(WXL_PluginInfo),
        WXL_API_VERSION,
        "wxl-loot-beam",
        1,
        WXL_CLIENT_BUILD,
    };
    return &info;
}

extern "C" __declspec(dllexport) int __cdecl WXL_Load(const WXL_Api* api)
{
    if (!api || api->apiVersion != WXL_API_VERSION) return 0;
    g_api = api;

    wxl::ext::EventScript::Bind(api);

    g_module = new (std::nothrow) wxl::scripts::loot_beam::LootBeam();
    if (!g_module)
    {
        if (api->Log) api->Log(WXL_LOG_ERROR, "wxl-loot-beam", "module allocation failed");
        return 0;
    }
    g_module->SetApi(api);
    g_module->LoadConfig(ModuleDirectory() + "wxl-loot-beam.ini");

    // Torment patch (PINNED.md): no overlay panel, as D3 has no beam settings; the .ini stays hand-editable.
    if (api->Log) api->Log(WXL_LOG_INFO, "wxl-loot-beam", "loot beam loaded");
    return 1;
}
