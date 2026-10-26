// Synthetic per-tier model names, resolved entirely through one file-open redirect. Any request for
// "<stem>$LODnn<rest>" is transparently served real bytes under a name the model cache has never seen
// before, so it loads and caches this tier as an entirely independent model object from the base one:
//
// - The model itself ("<stem>$LODnn.m2"): the marker is stripped and the real .m2 is served, so the
//   tier loads through the exact same path (native reader, OnM2SkinFinalize contract rebuild) as any
//   other model.
// - Its skin profile: the native loader builds its own request from the model's OWN path stem
//   (kBuildSkinPath -> "<pathStem><NN>.skin", NN = the profile the quality knob picked), which for a
//   marker-bearing stem comes out as ".../stem$LODnnNN.skin". Rather than stripping the marker and
//   letting that resolve to the base numbered skin, this redirects straight to ".../stem_lodnn.skin" --
//   the real LOD-tier skin sits under a DIFFERENT naming scheme than the numbered profiles, so serving
//   it from here is the only way it is ever reached.
//
// Routing the skin substitution through the SAME request the native loader already issues (instead of
// a manual post-load buffer swap) means it rides the native async read and its ONE normal
// kFinishLoadingSkinProfile completion -- no second finalize, no free/replace race against the base
// skin's own in-flight read, which is why an earlier post-load-swap version of this file went invisible
// at distance (the base skin's async completion clobbered the swapped-in buffer moments after loading).
//
// Net effect: a caller that wants "this model, but coarser" just asks for a different name
// (BuildVariantName) through the normal model-creation path. Everything else -- caching, sharing
// across instances that ask for the same tier, eviction -- is the native model cache's own job.
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

#include "LodModelVariant.hpp"
#include "../ExtensionApi.hpp"

#include "offsets/engine/Io.hpp"
#include "offsets/game/M2.hpp"

#include <cctype>
#include <cstdio>
#include <cstring>

namespace
{
    namespace io = wxl::offsets::engine::io;
    namespace m2 = wxl::offsets::game::m2;

    constexpr char   kMarker         = '$'; // "$LODnn", nn = two ASCII digits
    constexpr char   kMarkerTag[]    = "$LOD";
    constexpr size_t kMarkerTagLen   = 4;
    constexpr size_t kMarkerTotalLen = kMarkerTagLen + 2;

    bool g_installed = false;
    io::Storage_FileOpenFn g_origFileOpen = nullptr;

    /**
     * @brief Finds "$LODnn" in name and rewrites the redirect target into out.
     *
     * A trailing "<2 digits>.skin" right after the marker is the native loader's own
     * skin-profile request (kBuildSkinPath, no separator from the stem) -- redirected to
     * "_lodNN.skin" instead of the profile-numbered file it asked for. Everything else (the model
     * file itself, any other sibling probe) is served by removing the marker and keeping the rest
     * verbatim. Case-insensitive tag match: the native model cache lowercases the whole path
     * (CM2Cache::CreateShared's own SStrLower pass) before it ever reaches this hook, so a marker
     * written as "$LOD02" by BuildVariantName arrives here as "$lod02".
     * @return true on a match (out holds the redirect target).
     */
    bool BuildRedirect(const char* name, char* out, size_t outSize)
    {
        const char* hit = std::strchr(name, kMarker);
        while (hit)
        {
            if (_strnicmp(hit, kMarkerTag, kMarkerTagLen) == 0)
            {
                const char d0 = hit[kMarkerTagLen];
                const char d1 = hit[kMarkerTagLen + 1];
                if (d0 >= '0' && d0 <= '9' && d1 >= '0' && d1 <= '9')
                {
                    const uint32_t tier      = static_cast<uint32_t>((d0 - '0') * 10 + (d1 - '0'));
                    const size_t   beforeLen = static_cast<size_t>(hit - name);
                    const char*    after     = hit + kMarkerTotalLen;
                    const size_t   afterLen  = std::strlen(after);

                    if (tier > 0 && afterLen == 7 &&
                        std::isdigit(static_cast<unsigned char>(after[0])) &&
                        std::isdigit(static_cast<unsigned char>(after[1])) &&
                        _stricmp(after + 2, ".skin") == 0)
                    {
                        if (beforeLen + 16 > outSize) return false;
                        std::memcpy(out, name, beforeLen);
                        std::snprintf(out + beforeLen, outSize - beforeLen, "_lod%02u.skin", tier);
                        return true;
                    }

                    if (beforeLen + afterLen + 1 > outSize) return false;
                    std::memcpy(out, name, beforeLen);
                    std::memcpy(out + beforeLen, after, afterLen + 1); // + NUL
                    return true;
                }
            }
            hit = std::strchr(hit + 1, kMarker);
        }
        return false;
    }

    int __stdcall hkFileOpen(void* archive, const char* name, uint32_t flags, void** out)
    {
        char real[m2::kSkinPathBufSize];
        if (name && BuildRedirect(name, real, sizeof real))
        {
            const int ok = g_origFileOpen(archive, real, flags, out);
            WLOG_INFO("m2-lod-variant: '%s' -> '%s' (%s)", name, real, ok ? "ok" : "FAILED");
            return ok;
        }
        return g_origFileOpen(archive, name, flags, out);
    }
}

namespace wxl::runtime::m2lodvariant
{
    bool BuildVariantName(const char* realModelPath, uint32_t tier, char* outBuf, size_t outBufSize)
    {
        if (!realModelPath || !outBuf || tier == 0 || tier > 99) return false;
        const char* ext     = std::strrchr(realModelPath, '.');
        const size_t stemLen = ext ? static_cast<size_t>(ext - realModelPath) : std::strlen(realModelPath);
        const char*  extStr  = ext ? ext : ".m2";
        const int written = std::snprintf(outBuf, outBufSize, "%.*s%s%02u%s",
                                          static_cast<int>(stemLen), realModelPath, kMarkerTag, tier, extStr);
        return written > 0 && static_cast<size_t>(written) < outBufSize;
    }

    bool Installed() { return g_installed; }
}

namespace wxl_modern_m2
{
    bool InstallM2LodVariant()
    {
        HookAttach("Storage.FileOpen", wxl::offsets::engine::io::kFileOpen,
                  &hkFileOpen, &g_origFileOpen);
        g_installed = true;
        WLOG_INFO("m2-lod-variant: installed");
        return true;
    }
}
