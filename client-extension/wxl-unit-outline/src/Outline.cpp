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

#include "Outline.hpp"
#include "Hlsl.hpp"

#include "game/Unit.hpp"
#include "game/World.hpp"

#include <d3d9.h>

#ifdef GetObject
#undef GetObject
#endif

namespace unitoutline
{
    namespace world = wxl::game::world;
    namespace unit  = wxl::game::unit;

    constexpr uint32_t kFmtA8R8G8B8 = 21;

    // Blur resolution relative to the frame. Half costs a quarter of the fetches, and the upscale it
    // implies is only visible when the sampler is left on point filtering -- OutlinePass now states
    // linear, so the halo, which is low-frequency by construction, survives it.
    constexpr unsigned kBlurDivisor = 2;

    class ScopedDeviceState final
    {
    public:
        explicit ScopedDeviceState(gx::Device9 dev)
        {
            auto* d = static_cast<IDirect3DDevice9*>(dev.raw());
            if (d && SUCCEEDED(d->CreateStateBlock(D3DSBT_ALL, &state_)) && state_)
                state_->Capture();
        }

        ~ScopedDeviceState() { Restore(); }

        void Restore()
        {
            if (!state_) return;
            state_->Apply();
            state_->Release();
            state_ = nullptr;
        }

    private:
        IDirect3DStateBlock9* state_ = nullptr;
    };

    Outline::Outline()
    {
        on<&Outline::OnEndScene>(ev::Event::OnEndScene);
        on<&Outline::OnM2Batch>(ev::Event::OnM2BatchDraw);
        on<&Outline::OnDeviceLost>(ev::Event::OnDeviceLost);
    }

    void Outline::ColorForReaction(int reaction, float* c)
    {
        if (reaction < 2)      { c[0] = 1.0f; c[1] = 0.0f; c[2] = 0.0f; } // hostile
        else if (reaction < 4) { c[0] = 1.0f; c[1] = 1.0f; c[2] = 0.0f; } // neutral
        else                   { c[0] = 0.0f; c[1] = 1.0f; c[2] = 0.0f; } // friendly
        c[3] = 1.0f;
    }

    // Drops everything tied to a device. The objects hold the device alive until they are released,
    // so this is also what actually frees the old one.
    void Outline::Discard()
    {
        gx::Release(fillPS_);
        gx::Release(blurPS_);
        gx::Release(applyPS_);
        fillPS_  = nullptr;
        blurPS_  = nullptr;
        applyPS_ = nullptr;
        gx::ReleaseResetResources(); // every target this binary made, whatever it ends up being
        stamped_ = false;
        count_   = 0;
    }

    bool Outline::EnsureResources(gx::Device9 dev)
    {
        // A resolution change destroys the device and creates a new one rather than resetting it, and
        // nothing announces that. Shaders and targets belong to the device that made them, so the
        // pointer changing is the signal to rebuild -- handing the old ones to the new device faults
        // the driver rather than failing a call.
        if (dev.raw() != device_)
        {
            Discard();
            device_ = dev.raw();
        }

        if (!fillPS_)  fillPS_  = gx::CompilePixelShader(dev, kFillHLSL, "ps_2_0");
        if (!blurPS_)  blurPS_  = gx::CompilePixelShader(dev, kBlurHLSL, "ps_2_0");
        if (!applyPS_) applyPS_ = gx::CompilePixelShader(dev, kApplyHLSL, "ps_2_0");

        // A freshly created target holds whatever was in that memory, and the mask is otherwise only
        // wiped after a frame that stamped into it, so its first clear belongs here.
        if (!mask_.surface && gx::EnsureBackbufferTarget(dev, mask_, kFmtA8R8G8B8))
            ClearMask(dev);

        if (!blurA_.surface) gx::EnsureBackbufferTarget(dev, blurA_, kFmtA8R8G8B8, kBlurDivisor);
        if (!blurB_.surface) gx::EnsureBackbufferTarget(dev, blurB_, kFmtA8R8G8B8, kBlurDivisor);

        return fillPS_ && blurPS_ && applyPS_
            && mask_.surface && blurA_.surface && blurB_.surface;
    }

    int Outline::FindTarget(void* model) const
    {
        for (int hop = 0; model && hop < 8; ++hop, model = unit::ModelParent(model))
            for (int i = 0; i < count_; ++i)
                if (targets_[i].model == model) return i;
        return -1;
    }

    void Outline::AddTarget(unsigned long long guid, void* player)
    {
        if (!guid || count_ >= kMaxTargets) return;
        const bool isPlayer = (guid >> 32) == 0;

        void* obj = world::ResolveObject(guid, isPlayer ? world::kTypeMaskPlayer : world::kTypeMaskUnit);
        if (!obj) return;

        void* model = unit::Model(obj);
        if (!model) return;

        for (int i = 0; i < count_; ++i)
            if (targets_[i].model == model) return; // dedup

        const int reaction = player ? unit::Reaction(obj, player) : 5;
        targets_[count_].model    = model;
        targets_[count_].isPlayer = isPlayer;
        ColorForReaction(reaction, targets_[count_].color);
        ++count_;
    }

    void Outline::RebuildTargets()
    {
        void* player = world::ResolveObject(world::ActivePlayerGuid(), world::kTypeMaskPlayer);
        count_ = 0;
        AddTarget(world::MouseoverGuid(), player);
        // Torment patch (PINNED.md): hover only, as D3; upstream also outlines the target here.
    }

    bool Outline::ShouldStampBatch(gx::Device9 dev) const
    {
        if (!dev) return false;

        // Attached particles, glows and billboards draw through the same model context as the mesh.
        // The silhouette is the geometry that claims to be solid: a blended batch is not one, and
        // neither is a batch that declines to write depth, since an effect must not occlude what is
        // behind it. Letting either in puts a broad card in the mask, which the blur turns into a
        // blob sitting next to the unit.
        return dev.GetRenderState(gx::rs::kAlphaBlend) == 0
            && dev.GetRenderState(gx::rs::kZWrite) != 0;
    }

    // Draw the model again into the mask render target, with full device-state save/restore.
    void Outline::StampSilhouette(gx::Device9 dev, const ev::M2BatchDrawArgs& a, int idx)
    {
        // No state block: this runs once per model batch, and capturing the whole device to recover
        // four render states and one constant was the module's largest CPU cost. Everything this
        // function changes is saved by hand below.
        void* oldRT = nullptr; dev.GetRenderTarget(0, &oldRT);
        void* oldDS = nullptr; dev.GetDepthStencil(&oldDS);
        void* oldPS = nullptr; dev.GetPixelShader(&oldPS);
        unsigned char oldVP[24]; dev.GetViewport(oldVP);
        float oldC0[4]; dev.GetPixelShaderConstantF(0, oldC0, 1);
        const unsigned sAB = dev.GetRenderState(gx::rs::kAlphaBlend);
        const unsigned sZE = dev.GetRenderState(gx::rs::kZEnable);
        const unsigned sZW = dev.GetRenderState(gx::rs::kZWrite);
        const unsigned sZF = dev.GetRenderState(gx::rs::kZFunc);

        dev.SetRenderTarget(0, mask_.surface);
        if (targets_[idx].isPlayer)
        {
            // Players: depth-test against the scene so walls occlude the outline.
            dev.SetDepthStencil(oldDS);
            dev.SetRenderState(gx::rs::kZEnable, 1);
            dev.SetRenderState(gx::rs::kZWrite, 0);
            dev.SetRenderState(gx::rs::kZFunc, gx::cmp::kLessEqual);
        }
        else
        {
            // NPCs: see-through (no depth).
            dev.SetDepthStencil(nullptr);
            dev.SetRenderState(gx::rs::kZEnable, 0);
        }
        stamped_ = true;
        dev.SetRenderState(gx::rs::kAlphaBlend, 0);
        dev.SetPixelShader(fillPS_);
        dev.SetPixelShaderConstantF(0, targets_[idx].color, 1);
        dev.DrawIndexedPrimitive(a.primType, a.baseVertex, a.minIndex, a.numVerts, a.startIndex, a.primCount);

        dev.SetPixelShader(oldPS);
        dev.SetRenderTarget(0, oldRT);
        dev.SetDepthStencil(oldDS);
        dev.SetViewport(oldVP);
        dev.SetRenderState(gx::rs::kAlphaBlend, sAB);
        dev.SetRenderState(gx::rs::kZEnable, sZE);
        dev.SetRenderState(gx::rs::kZWrite, sZW);
        dev.SetRenderState(gx::rs::kZFunc, sZF);
        dev.SetPixelShaderConstantF(0, oldC0, 1);
        gx::Release(oldRT);
        gx::Release(oldDS);
        gx::Release(oldPS);
    }

    // mask -> blurA (horizontal) -> blurB (vertical) -> frame. A blur reaches further than a
    // neighbour test, so the falloff is a gradient rather than a one-texel step and the width is a
    // radius rather than a tap offset.
    //
    // The state block does not capture render targets, so those are the one thing saved by hand.
    void Outline::OutlinePass(gx::Device9 dev)
    {
        ScopedDeviceState state(dev);
        void* oldRT = nullptr; dev.GetRenderTarget(0, &oldRT);
        void* oldDS = nullptr; dev.GetDepthStencil(&oldDS);

        dev.SetRenderState(gx::rs::kZEnable, 0);
        dev.SetRenderState(gx::rs::kCullMode, gx::cull::kNone);
        dev.SetRenderState(gx::rs::kAlphaBlend, 0);

        // The blur passes have to overwrite their target completely. Four states inherited from the
        // frame can reject a pixel instead, and any pixel not written keeps what the previous frame
        // left there -- which reads as old halos frozen in screen space.
        dev.SetRenderState(gx::rs::kAlphaTest, 0);
        dev.SetRenderState(gx::rs::kScissorTest, 0);
        dev.SetRenderState(gx::rs::kStencilEnable, 0);
        dev.SetRenderState(gx::rs::kColorWrite, gx::colorwrite::kAll);

        // Sampling is inherited too. Point filtering would quantise the kernel back to texel centres
        // and defeat the fractional offsets, and wrap addressing lets the taps at the frame's edge
        // pull in the opposite side.
        for (unsigned stage = 0; stage < 2; ++stage)
        {
            dev.SetSamplerState(stage, gx::samp::kMagFilter, gx::filter::kLinear);
            dev.SetSamplerState(stage, gx::samp::kMinFilter, gx::filter::kLinear);
            dev.SetSamplerState(stage, gx::samp::kMipFilter, gx::filter::kNone);
            dev.SetSamplerState(stage, gx::samp::kAddressU, gx::address::kClamp);
            dev.SetSamplerState(stage, gx::samp::kAddressV, gx::address::kClamp);
        }

        dev.SetVertexShader(nullptr);
        dev.SetDepthStencil(nullptr);
        dev.SetPixelShader(blurPS_);

        // The step is in blur-target texels, spread_ in frame pixels, hence the divisor.
        const float step = spread_ / float(kBlurDivisor);
        const float horizontal[4] = { 1.0f / blurA_.width, 0.0f, step, 0.0f };
        dev.SetRenderTarget(0, blurA_.surface);
        dev.SetTexture(0, mask_.texture);
        dev.SetPixelShaderConstantF(0, horizontal, 1);
        gx::DrawFullscreenQuad(dev);

        const float vertical[4] = { 0.0f, 1.0f / blurB_.height, step, 0.0f };
        dev.SetRenderTarget(0, blurB_.surface);
        dev.SetTexture(0, blurA_.texture);
        dev.SetPixelShaderConstantF(0, vertical, 1);
        gx::DrawFullscreenQuad(dev);

        const float apply[4] = { intensity_, 0.0f, 0.0f, 0.0f };
        dev.SetRenderTarget(0, oldRT);
        dev.SetDepthStencil(oldDS);
        dev.SetTexture(0, blurB_.texture);
        dev.SetTexture(1, mask_.texture);
        dev.SetPixelShader(applyPS_);
        dev.SetPixelShaderConstantF(0, apply, 1);
        dev.SetRenderState(gx::rs::kAlphaBlend, 1);
        dev.SetRenderState(gx::rs::kSrcBlend, gx::blend::kSrcAlpha);
        dev.SetRenderState(gx::rs::kDestBlend, gx::blend::kInvSrcAlpha);
        gx::DrawFullscreenQuad(dev);

        dev.SetPixelShader(nullptr);
        state.Restore();

        // After the restore, not before: the block captured the bindings from before this pass, so
        // unbinding first would just be undone. The mask becomes a render target again next frame,
        // and a surface bound as both target and texture source is invalid -- which shows up as the
        // mask keeping its contents and silhouettes piling up.
        dev.SetTexture(0, nullptr);
        dev.SetTexture(1, nullptr);

        gx::Release(oldRT);
        gx::Release(oldDS);
    }

    void Outline::OnM2Batch(const ev::M2BatchDrawArgs& a)
    {
        // Not merely "are the resources there" but "are they this device's": a batch can arrive on a
        // freshly created device before the EndScene that rebuilds them.
        if (count_ == 0 || a.device != device_) return;
        if (!fillPS_ || !mask_.surface) return;
        const int idx = FindTarget(a.model);
        if (idx < 0) return;

        gx::Device9 dev(a.device);
        if (!ShouldStampBatch(dev)) return;
        StampSilhouette(dev, a, idx);
    }

    // Stages 0 and 1 are dropped first: the blur and the composite sampled the mask, and a surface
    // still bound as a texture cannot be made a render target -- the clear would be dropped and the
    // silhouettes would survive into the next frame.
    void Outline::ClearMask(gx::Device9 dev)
    {
        ScopedDeviceState state(dev);
        void* oldRT = nullptr; dev.GetRenderTarget(0, &oldRT);
        void* oldDS = nullptr; dev.GetDepthStencil(&oldDS);

        dev.SetTexture(0, nullptr);
        dev.SetTexture(1, nullptr);
        dev.SetRenderTarget(0, mask_.surface);
        dev.SetDepthStencil(nullptr);

        // A clear is bounded by the scissor rect the same way a draw is, so an inherited one would
        // leave part of the mask untouched.
        dev.SetRenderState(gx::rs::kScissorTest, 0);
        dev.SetRenderState(gx::rs::kColorWrite, gx::colorwrite::kAll);
        dev.Clear(0, nullptr, gx::clear::kTarget, 0x00000000, 1.0f, 0);

        dev.SetRenderTarget(0, oldRT);
        dev.SetDepthStencil(oldDS);
        gx::Release(oldRT);
        gx::Release(oldDS);
    }

    void Outline::OnEndScene(const ev::EndSceneArgs& a)
    {
        const bool stamped = stamped_;
        stamped_ = false;

        gx::Device9 dev(a.device);
        if (!dev) return;

        // EnsureResources first and unconditionally: it creates the shaders and targets, and nothing
        // can ever be stamped until it has.
        if (!EnsureResources(dev)) return;

        // The clear is paired with the stamping rather than run unconditionally: the mask starts
        // empty and is wiped at the end of every frame that wrote into it, so a frame that stamps
        // nothing finds it already empty and pays for nothing.
        if (stamped)
        {
            OutlinePass(dev);
            ClearMask(dev);
        }
        RebuildTargets();
    }

    // The mask is a D3DPOOL_DEFAULT resource, so it has to go before the engine resets the device.
    // Releasing zeroes it and EnsureResources recreates it on the next frame; the pixel shaders are
    // not pool resources and survive the reset untouched.
    //
    // In-core scripts got this for free from the core's own reset sweep. An extension carries its
    // own copy of the gx facade, so its targets are its own to release.
    void Outline::OnDeviceLost(const ev::DeviceResetArgs&)
    {
        gx::ReleaseResetResources(); // sweeps this binary's targets, whatever they end up being
        stamped_ = false;
    }
}

const WXL_PluginInfo* __cdecl WXL_Query(void)
{
    static const WXL_PluginInfo info = {
        sizeof(WXL_PluginInfo),
        WXL_API_VERSION,
        "UnitOutline",
        1,
        WXL_CLIENT_BUILD,
    };
    return &info;
}

int __cdecl WXL_Load(const WXL_Api* api)
{
    if (!api || api->apiVersion != WXL_API_VERSION) return 0;

    // Ahead of the constructor, which is where the handlers bind.
    wxl::ext::EventScript::Bind(api);
    static unitoutline::Outline outline;

    api->Log(WXL_LOG_INFO, "UnitOutline", "outline active on mouseover and target");
    return 1;
}
