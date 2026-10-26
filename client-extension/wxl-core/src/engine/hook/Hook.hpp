// Named hooking over MinHook: install by name + address, enable in one batch.
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

/// Named hooking over MinHook: a feature installs a hook by name and address; the trampoline is
/// returned through the original out-pointer.
///
/// Multiple parties may detour one address. MinHook holds a single detour slot per target, so they
/// are chained instead: each party's original points at the next party's detour, and the last one's
/// at the trampoline. Not calling original suppresses the parties behind and the engine function.
///
/// MinHook is given the head only, and only at Enable time, so a chain's order is fixed before the
/// address is patched.
namespace wxl::hook
{
    /// Chain position: lower runs first, closest to the caller. Equal values keep install order.
    constexpr int kDefaultPriority = 0;

    /**
     * @brief Initialises the hooking engine once at startup.
     * @return true if initialisation succeeded.
     */
    bool Init();

    /**
     * @brief Registers one detour in its target's chain.
     *
     * The address is patched at Enable time, so a bad one is reported there rather than here.
     * @param name      label used for logging.
     * @param target    engine function address to detour.
     * @param detour    replacement function.
     * @param original  receives the next link in the chain, ending at the engine function.
     * @param priority  chain position; see kDefaultPriority.
     * @return true if the detour was registered.
     */
    bool Install(const char* name, void* target, void* detour, void** original,
                 int priority = kDefaultPriority);

    /**
     * @brief Registers one detour, taking the target as an integer address.
     * @param name      label used for logging.
     * @param target    engine function address to detour.
     * @param detour    replacement function.
     * @param original  receives the next link in the chain, ending at the engine function.
     * @param priority  chain position; see kDefaultPriority.
     * @return true if the detour was registered.
     */
    inline bool Install(const char* name, uintptr_t target, void* detour, void** original,
                        int priority = kDefaultPriority)
    {
        return Install(name, reinterpret_cast<void*>(target), detour, original, priority);
    }

    /**
     * @brief Typed detour install: the detour and the trampoline out-pointer must share ONE
     *        function type, so wiring a hook to the wrong original no longer compiles.
     *
     * Replaces the call-site boilerplate
     *   Install(name, addr, reinterpret_cast<void*>(&hk), reinterpret_cast<void**>(&orig))
     * with
     *   Install(name, addr, &hk, &orig)
     * @param name      label used for logging.
     * @param target    engine function address to detour.
     * @param detour    replacement function (deducing the shared function type).
     * @param original  receives the next link in the chain; must point to a pointer of the same type.
     * @param priority  chain position; see kDefaultPriority.
     * @return true if the detour was registered.
     */
    template <class Fn>
    bool Install(const char* name, uintptr_t target, Fn* detour, Fn** original,
                 int priority = kDefaultPriority)
    {
        return Install(name, reinterpret_cast<void*>(target),
                       reinterpret_cast<void*>(detour), reinterpret_cast<void**>(original),
                       priority);
    }

    /** @brief Patches and enables one target's chain immediately. */
    bool Enable(void* target);

    inline bool Enable(uintptr_t target)
    {
        return Enable(reinterpret_cast<void*>(target));
    }

    /**
     * @brief Patches every chain registered since the last call and enables the batch.
     *
     * Called once per install phase, so a chain reaches MinHook only once its parties for that phase
     * have registered.
     * @return true if every pending chain was patched and the batch enabled.
     */
    bool EnableAll();
}
