// wxl-unit-outline: reaction-colored silhouette outline on the mouseover and target units.
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

#include "wxl/EventScript.hpp"

#include "game/Gx.hpp"

// It owns its shaders, its target list and its render target, and draws purely through the SDK's gx
// facade and the unit/world accessors. It touches no offset and installs no hook: it binds member
// functions to render events and the core does the rest.
//
// Pipeline (one-frame): EndScene of frame N rebuilds the target list for frame N+1; during frame N+1 the
// per-batch event stamps each target's silhouette into a mask; EndScene of N+1 edge-detects the mask
// into the frame, then rebuilds again.
namespace unitoutline
{
    namespace ev = wxl::events;
    namespace gx = wxl::game::gx;

    class Outline final : public wxl::ext::EventScript
    {
    public:
        Outline(); // binds the event handlers

    private:
        // --- event handlers ---
        void OnEndScene(const ev::EndSceneArgs& a);
        void OnM2Batch(const ev::M2BatchDrawArgs& a);
        void OnDeviceLost(const ev::DeviceResetArgs& a);

        // --- steps ---
        bool EnsureResources(gx::Device9 dev);  // compile shaders + create the mask RT, once per device
        void Discard();                         // drop everything tied to the previous device
        void RebuildTargets();                  // mouseover + target -> colored entries
        void StampSilhouette(gx::Device9 dev, const ev::M2BatchDrawArgs& a, int idx);
        void OutlinePass(gx::Device9 dev);      // blur the mask separably, composite the halo
        void ClearMask(gx::Device9 dev);        // wipe the mask, every frame, unconditionally

        // --- helpers ---
        bool ShouldStampBatch(gx::Device9 dev) const;
        int  FindTarget(void* model) const;     // model or any parent in the list
        void AddTarget(unsigned long long guid, void* player);
        static void ColorForReaction(int reaction, float* outRgba);

        static constexpr int kMaxTargets = 2;
        struct Target { void* model; float color[4]; bool isPlayer; };

        Target             targets_[kMaxTargets]{};
        int                count_       = 0;
        void*              device_      = nullptr; // the device the resources below belong to
        gx::RenderTarget   mask_{};                // the silhouette
        gx::RenderTarget   blurA_{};               // horizontal pass output
        gx::RenderTarget   blurB_{};               // vertical pass output
        void*              fillPS_      = nullptr; // stamps a batch into the mask, following its cutout
        void*              blurPS_      = nullptr; // one Gaussian, run once per axis
        void*              applyPS_     = nullptr; // blurred field minus silhouette, into the frame
        bool               stamped_     = false; // a silhouette reached the mask this frame
        float              spread_      = 1.5f;    // frame pixels between blur taps
        float              intensity_   = 2.0f;    // halo opacity multiplier
    };
}
