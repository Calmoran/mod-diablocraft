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

#include "engine/hook/Hook.hpp"
#include "common/Log.hpp"

#include <MinHook.h>

#include <deque>
#include <iterator>
#include <vector>

namespace wxl::hook
{
    namespace
    {
        /// One party on an address. original is the caller's own trampoline variable; the chain owns
        /// it and rewrites it whenever the chain's shape changes.
        struct Link
        {
            const char* name;
            void*       detour;
            void**      original;
            int         priority;
        };

        /// Every party on one address, head first. MinHook only ever sees the head.
        struct Chain
        {
            void*             target;
            std::vector<Link> links;
            void*             trampoline; ///< valid once patched
            bool              patched;
        };

        /// deque rather than vector: FindChain hands out a Chain*, and registering a further address
        /// must not move the existing ones.
        std::deque<Chain>& Chains()
        {
            static std::deque<Chain> chains;
            return chains;
        }

        Chain* FindChain(void* target)
        {
            for (Chain& chain : Chains())
                if (chain.target == target) return &chain;
            return nullptr;
        }

        Chain& ChainFor(void* target)
        {
            if (Chain* existing = FindChain(target)) return *existing;
            Chains().push_back(Chain{target, {}, nullptr, false});
            return Chains().back();
        }

        /// Points every party at its successor and the last one at the engine function.
        ///
        /// Each store is a single aligned pointer write, so a call in flight through a live chain
        /// reads either the old successor or the new one.
        void Relink(Chain& chain)
        {
            const size_t count = chain.links.size();
            if (count == 0) return;

            for (size_t i = 0; i + 1 < count; ++i)
                *chain.links[i].original = chain.links[i + 1].detour;

            // Before Patch there is no trampoline to close the tail on.
            if (chain.patched)
                *chain.links[count - 1].original = chain.trampoline;
        }

        /// Hands the head to MinHook and closes the tail on the returned trampoline.
        bool Patch(Chain& chain)
        {
            if (chain.patched) return true;

            const MH_STATUS status = MH_CreateHook(chain.target, chain.links.front().detour,
                                                   &chain.trampoline);
            if (status != MH_OK)
            {
                // Every party is named: the address no longer belongs to a single install site.
                for (const Link& link : chain.links)
                    WLOG_ERROR("hook: create '%s' @0x%p failed (%s)", link.name, chain.target,
                               MH_StatusToString(status));
                return false;
            }

            chain.patched = true;
            Relink(chain);
            return true;
        }
    }

    /**
     * @brief Initialises the hooking engine once at startup.
     * @return true if initialisation succeeded.
     */
    bool Init()
    {
        MH_STATUS status = MH_Initialize();
        if (status != MH_OK)
        {
            WLOG_ERROR("hook: MH_Initialize failed (%s)", MH_StatusToString(status));
            return false;
        }
        return true;
    }

    /**
     * @brief Registers one detour in its target's chain.
     * @param name      label used for logging.
     * @param target    engine function address to detour.
     * @param detour    replacement function.
     * @param original  receives the next link in the chain, ending at the engine function.
     * @param priority  chain position; see kDefaultPriority.
     * @return true if the detour was registered.
     */
    bool Install(const char* name, void* target, void* detour, void** original, int priority)
    {
        Chain& chain = ChainFor(target);

        auto at = chain.links.end();
        while (at != chain.links.begin() && std::prev(at)->priority > priority) --at;

        // Taking the head of a live chain means repointing MinHook at another detour while calls may
        // be running through the old one.
        if (chain.patched && at == chain.links.begin())
        {
            WLOG_ERROR("hook: '%s' @0x%p claims the head of a live chain held by '%s'",
                       name, target, chain.links.front().name);
            return false;
        }

        chain.links.insert(at, Link{name, detour, original, priority});
        Relink(chain);

        WLOG_DEBUG("hook: installed '%s' @0x%p (%zu on this address)", name, target,
                   chain.links.size());
        return true;
    }

    bool Enable(void* target)
    {
        Chain* chain = FindChain(target);
        if (!chain)
        {
            WLOG_ERROR("hook: enable @0x%p: nothing installed there", target);
            return false;
        }
        if (!Patch(*chain)) return false;

        const MH_STATUS status = MH_EnableHook(target);
        if (status != MH_OK && status != MH_ERROR_ENABLED)
        {
            WLOG_ERROR("hook: enable @0x%p failed (%s)", target, MH_StatusToString(status));
            return false;
        }
        WLOG_DEBUG("hook: enabled early @0x%p", target);
        return true;
    }

    /**
     * @brief Patches every chain registered since the last call and enables the batch.
     * @return true if every pending chain was patched and the batch enabled.
     */
    bool EnableAll()
    {
        bool patched = true;
        for (Chain& chain : Chains())
        {
            if (chain.links.empty()) continue;
            if (!Patch(chain)) patched = false;
        }

        MH_STATUS status = MH_EnableHook(MH_ALL_HOOKS);
        if (status != MH_OK)
        {
            WLOG_ERROR("hook: enable all failed (%s)", MH_StatusToString(status));
            return false;
        }
        return patched;
    }
}
