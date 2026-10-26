// Storage I/O hook: client-side file providers and transforms, layered over the client's own
// (now fully native) archive reads.
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

#include <cstdint>
#include <string>
#include <vector>

namespace wxl::runtime::storage
{
    /**
     * @brief Arms the archive-mount safety nets: tolerates a corrupted/missing required archive
     *        instead of hard-failing boot, and forces the expansion-content-present flag on.
     *
     * Must run before the client builds its archive set, so call it from the DLL entry on the loader
     * thread (not from the deferred main thread, which the client's startup races past).
     */
    void InstallArchiveGuard();

    /**
     * @brief Hooks the client archive file-I/O primitives so client providers and transforms can
     *        participate (see RegisterClientProvider / RegisterClientTransform).
     *
     * Every archive read otherwise runs exactly as stock: real archives (named or loose-directory,
     * including a Patch-* the client's own patch-name scan finds) mount and read natively. Call once
     * at startup, before EnableAll.
     */
    void Install();

    /**
     * @brief Callback type for client-side virtual file providers.
     * @param name  file name requested by the engine
     * @param out   receives the file bytes when the provider claims the name
     * @return true if this provider supplied bytes for name, false to defer
     */
    using ClientProvideFn = bool(*)(const char* name, std::vector<uint8_t>& out);

    /**
     * @brief Registers a client-side file provider: supplies whole bytes for a name without any
     *        archive read (e.g. a drop-in model converted on the spot from a loose source file).
     *
     * Providers are checked in TryServe before the native archive open. A provider that returns
     * true claims the file; the first claimant wins. Safe to call from a global constructor
     * (no hooking engine involved -- just a function pointer stored in a list).
     * @param fn  provider callback to register
     */
    void RegisterClientProvider(ClientProvideFn fn);

    /**
     * @brief Callback type for a client-side name redirect.
     * @param name  file name the engine asked for
     * @param out   receives the name to open instead when the redirect claims it
     * @return true to open `out` in place of `name`, false to leave the request alone
     */
    using ClientRedirectFn = bool(*)(const char* name, std::string& out);

    /**
     * @brief Registers a redirect: answers one name with a different file, without copying bytes.
     *
     * This runs before providers and before the native open, so everything downstream sees only the
     * name it was given. That is what makes it the right tool for swapping a whole asset family at
     * once: a model's companions are named after the model, so redirecting the request redirects the
     * skin, the animations and the skeleton with it, and nothing has to agree about it separately.
     *
     * A redirect must not claim a name it would produce itself, or the first request loops. Redirects
     * are checked in registration order and the first claimant wins.
     * @param fn  redirect callback to register
     */
    void RegisterClientRedirect(ClientRedirectFn fn);

    /**
     * @brief Callback type for a client-side byte transform.
     * @param name  file name opened
     * @param raw   the bytes as natively read
     * @param out   receives the reshaped bytes when the transform claims the file
     * @return true if this transform reshaped raw into out, false to leave raw untouched
     */
    using ClientTransformFn = bool(*)(const char* name, const std::vector<uint8_t>& raw, std::vector<uint8_t>& out);

    /**
     * @brief Registers a client-side transform for names ending with suffix (case-insensitive).
     *
     * Unlike a provider, a transform runs AFTER a successful native open: the file already exists in
     * an archive/directory the client mounted itself, and this reshapes what it read (e.g.
     * re-encoding a texture format the client cannot decode) before the native caller sees it.
     * Filtering by suffix keeps every open cheap -- a name matching no registered suffix never pays
     * for the extra read a transform needs to inspect bytes.
     * @param suffix  lowercase suffix a name must end with to be offered to fn (e.g. ".blp")
     * @param fn      transform callback
     */
    void RegisterClientTransform(const char* suffix, ClientTransformFn fn);

    /**
     * @brief Filter for materialized bytes before the native loader sees them.
     * @return Byte count to expose to native code; may trim trailing module side tables.
     */
    using ServeFilterFn = uint32_t(*)(const char* name, const uint8_t* buffer, uint32_t size);

    /** Registers a served-bytes filter; safe from a module global constructor. */
    void RegisterServeFilter(ServeFilterFn fn);
}
