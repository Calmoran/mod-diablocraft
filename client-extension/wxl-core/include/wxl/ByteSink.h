// A growable byte sink, shared by every published interface that hands variable-length bytes back
// across the extension ABI boundary (no std::vector, no C++ ABI -- see PluginApi.h).
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

#ifndef WXL_BYTE_SINK_H
#define WXL_BYTE_SINK_H

#ifdef __cplusplus
extern "C" {
#endif

/** Growable byte sink the caller hands a callee to write output bytes into, in order, once. */
typedef struct WXL_ByteSink
{
    void* ctx;
    void(__cdecl* Write)(void* ctx, const void* data, unsigned int len);
} WXL_ByteSink;

#ifdef __cplusplus
}
#endif

#endif // WXL_BYTE_SINK_H
