// Native modern-M2 reader: serves a wrapped external animation file as the flat track blob.
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

// A sequence whose keyframes are not stored in the model streams them from a companion file, and a
// modern companion file puts the very same flat track blob behind a one-chunk wrapper. Unwrapping is
// therefore the whole of the difference, and it belongs here rather than anywhere upstream of the
// read: the bytes are resident, nothing has looked at them yet, and the payload slides onto the
// buffer base the rebase already uses -- so the allocation the model owns keeps its identity and the
// only thing that changes is how many of its bytes count as the file.
//
// A file that is already flat is left exactly as it arrived.
//
// One shape stays out of reach: a model with an externalized skeleton splits the same companion file
// into separate event / attachment / bone chunks instead of one, which is a different unwrap and has
// no home while such models are refused at load.

#include "../ExtensionApi.hpp"
#include "M2NativeInternal.hpp"

#include "engine/assets/shared/models/m2/M2Format.hpp"
#include "offsets/game/M2.hpp"

#include <windows.h>

#include <cstdint>
#include <cstring>

namespace
{
    namespace off = wxl::offsets::game::m2;
    namespace fmt = wxl::structure::m2;

    constexpr uint32_t kChunkHeaderBytes = 8; // the wrapper's tag plus its payload size

    off::M2_AnimLoadCompleteFn g_origAnimLoadComplete = nullptr;

    /// Slides a wrapped payload onto the buffer base and shortens the record to it. POD locals only
    /// (this runs under the SEH guard below).
    void UnwrapCore(void* node, uint32_t* unwrappedTo)
    {
        auto* n = static_cast<off::LoadNode*>(node);
        if (!n || !n->record) return;
        auto* record = static_cast<off::IoRecord*>(n->record);
        auto* bytes  = reinterpret_cast<uint8_t*>(record->buffer);
        if (!bytes || record->size < kChunkHeaderBytes) return;
        if (wxl::runtime::m2native::detail::Rd32(bytes) != fmt::kMagicAFM2) return;

        const uint32_t payload = wxl::runtime::m2native::detail::Rd32(bytes + 4);
        if (static_cast<uint64_t>(kChunkHeaderBytes) + payload > record->size) return;

        std::memmove(bytes, bytes + kChunkHeaderBytes, payload);
        record->size = payload;
        *unwrappedTo = payload;
    }

    void UnwrapGuarded(void* node, uint32_t* unwrappedTo)
    {
        __try { UnwrapCore(node, unwrappedTo); }
        __except (EXCEPTION_EXECUTE_HANDLER) { *unwrappedTo = 0; }
    }

    void __cdecl hkAnimLoadComplete(void* node)
    {
        uint32_t unwrappedTo = 0;
        UnwrapGuarded(node, &unwrappedTo);
        if (unwrappedTo)
            WLOG_INFO("m2native-anim: streamed sequence unwrapped to %u byte(s)", unwrappedTo);
        g_origAnimLoadComplete(node);
    }
}

namespace wxl_modern_m2
{
    bool InstallAnimUnwrap()
    {
        if (!HookAttachByName("M2.AnimLoadComplete", &hkAnimLoadComplete, &g_origAnimLoadComplete))
            return false;
        WLOG_INFO("m2native-anim: wrapped external animation files are unwrapped in place");
        return true;
    }
}
