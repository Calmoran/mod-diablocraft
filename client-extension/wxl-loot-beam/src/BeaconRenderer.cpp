// wxl-loot-beam: the additive triangle queue behind the beacon.
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

#include "BeaconRenderer.hpp"

#include "game/Camera.hpp"

#include <windows.h>
#include <d3d9.h>

#include <cmath>
#include <cstring>
#include <vector>

namespace wxl::scripts::loot_beam::beacon_gfx
{
    namespace gfx = wxl::game::gfx;
    namespace gx  = wxl::game::gx;
    namespace cam = wxl::game::camera;

    namespace
    {
        struct Vertex { float x, y, z; gfx::Color color; };
        static_assert(sizeof(Vertex) == 16, "Vertex must match the declared vertex format stride");

        std::vector<Vertex> g_vertices;
        gfx::Depth          g_depth        = gfx::Depth::Tested;
        float               g_push         = 0.0f;
        float               g_pushPerYard  = 0.0f;
        bool                g_hasMatrices  = false;
        float               g_viewOverride[16] = {};
        float               g_projOverride[16] = {};

        // D3DBLEND_ONE. The SDK names only the two source-over factors it needs; additive is the whole
        // point here, so the constant is carried locally rather than widening the core's enum.
        constexpr unsigned kBlendOne = 2;
        // D3DCMP_GREATEREQUAL. Absent from the gx constants, which only ever needed the standard one.
        constexpr unsigned kGreaterEqual = 7;

        constexpr unsigned kTouchedStates[] = {
            gx::rs::kZEnable, gx::rs::kShadeMode, gx::rs::kZWrite, gx::rs::kAlphaTest,
            gx::rs::kSrcBlend, gx::rs::kDestBlend, gx::rs::kCullMode, gx::rs::kZFunc,
            gx::rs::kAlphaBlend, gx::rs::kFogEnable, gx::rs::kStencilEnable,
            gx::rs::kLighting, gx::rs::kColorWrite, gx::rs::kScissorTest,
            24 /*D3DRS_ALPHAREF*/, 25 /*D3DRS_ALPHAFUNC*/,
        };
        constexpr size_t kTouchedStateCount = sizeof(kTouchedStates) / sizeof(kTouchedStates[0]);

        constexpr unsigned kTouchedStages[][2] = {
            { 0, gx::tss::kColorOp },  { 0, gx::tss::kColorArg1 },
            { 0, gx::tss::kAlphaOp },  { 0, gx::tss::kAlphaArg1 },
            { 1, gx::tss::kColorOp },
        };
        constexpr size_t kTouchedStageCount = sizeof(kTouchedStages) / sizeof(kTouchedStages[0]);

        // Every sampler stage the beacon clears before drawing. It is untextured, so no texture is
        // wanted, but the reason it clears all of them and not just stage 0 is the scene depth: a
        // module that samples the scene depth (wxl-modern-water does, through an INTZ copy) can leave
        // that depth texture bound to a sampler after its pass, and binding the same surface as both a
        // sampler and the depth target is what makes a depth test against it read garbage. Clearing
        // every stage removes the overlap.
        constexpr unsigned kMaxTextureStages = 16;

        // --- scene-depth occlusion ---
        //
        // The world is drawn into a sampleable depth surface (an INTZ texture on this client), but a
        // fixed-function depth test against that surface is not reliable once the client's d3d9 shim is
        // in the path -- on this client it rejects the beam no matter what is in front of it. So the
        // test is done explicitly: the world depth is bound as a texture and a pixel shader compares each
        // fragment's own depth against it, discarding the fragment when something nearer is in front.
        // The fragment depth comes from a matching vertex shader rather than from a generated texture
        // coordinate, so the comparison uses exactly the projection the world was rasterised with.
        void* g_depthVS = nullptr;
        void* g_depthPS = nullptr;

        constexpr const char* kOcclusionVSHLSL =
            "float4x4 wvp : register(c0);\n"
            "struct VS_OUT { float4 pos : POSITION; float4 color : COLOR0; float4 clip : TEXCOORD0; };\n"
            "VS_OUT main(float4 pos : POSITION, float4 color : COLOR0)\n"
            "{\n"
            "    VS_OUT o;\n"
            "    o.pos = mul(pos, wvp);\n"
            "    o.clip = o.pos;\n"
            "    o.color = color;\n"
            "    return o;\n"
            "}\n";

        // c0 is { minZ, proj14, maxZ - minZ, proj10 }: a raw depth in [minZ, maxZ] maps back to a view
        // depth by ndc = (raw - minZ) / (maxZ - minZ), view = proj14 / (ndc - proj10). clip.w is that
        // view depth, so the test is a view-depth comparison with a small bias for terrain LOD.
        constexpr const char* kOcclusionPSHLSL =
            "sampler2D s0 : register(s0);\n"
            "float4 span : register(c0);\n"
            "float4 main(float4 clip : TEXCOORD0, float4 color : COLOR0) : COLOR\n"
            "{\n"
            "    float2 uv = clip.xy / clip.w * float2(0.5, -0.5) + 0.5;\n"
            "    float raw = tex2Dlod(s0, float4(uv, 0, 0)).r;\n"
            "    float ndc = span.z > 0.0001 ? (raw - span.x) / span.z : raw;\n"
            "    float scene = span.y / (ndc - span.w);\n"
            "    if (clip.w > scene + 0.35) discard;\n"
            "    return color;\n"
            "}\n";

        // d3dcompiler_47 is delay-loaded by the client and may not be loaded when the first beacon
        // draws; resolve it on demand so a client without it simply keeps the fixed-function fallback.
        using D3DCompileFn = long(__stdcall*)(const char*, size_t, const char*, const void*, void*,
                                              const char*, const char*, unsigned, unsigned, void**, void**);
        D3DCompileFn D3DCompileProc()
        {
            static D3DCompileFn fn = []() -> D3DCompileFn {
                HMODULE m = GetModuleHandleA("d3dcompiler_47.dll");
                if (!m) m = LoadLibraryA("d3dcompiler_47.dll");
                return m ? reinterpret_cast<D3DCompileFn>(GetProcAddress(m, "D3DCompile")) : nullptr;
            }();
            return fn;
        }

        void* CompileVertexShader(gx::Device9 dev, const char* hlsl)
        {
            const D3DCompileFn compile = D3DCompileProc();
            if (!compile || !hlsl || !dev) return nullptr;
            void* code = nullptr;
            void* err  = nullptr;
            const long hr = compile(hlsl, std::strlen(hlsl), nullptr, nullptr, nullptr, "main", "vs_2_0",
                                    0, 0, &code, &err);
            if (err) gx::Release(err);
            if (hr < 0 || !code) return nullptr;

            const void* bytecode = gx::Vtbl<const void*(__stdcall*)(void*)>(code, 3)(code);
            void* shader = nullptr;
            using CreateShaderFn = long(__stdcall*)(void*, const void*, void**);
            gx::Vtbl<CreateShaderFn>(dev.raw(), 91 /* CreateVertexShader */)(dev.raw(), bytecode, &shader);
            gx::Release(code);
            return shader;
        }

        void Mul4x4(const float* a, const float* b, float* out)
        {
            for (int i = 0; i < 4; ++i)
                for (int j = 0; j < 4; ++j)
                {
                    float s = 0.0f;
                    for (int k = 0; k < 4; ++k) s += a[i * 4 + k] * b[k * 4 + j];
                    out[i * 4 + j] = s;
                }
        }

        // Turns the depth surface into the texture the shader samples. A surface that belongs to a
        // depth texture answers IDirect3DResource9::GetContainer (vtable slot 11); a standalone
        // depth-stencil surface does not, and then the fixed-function test is the only option left.
        void* DepthTexture(void* surface)
        {
            if (!surface) return nullptr;
            struct Guid { unsigned long d1; unsigned short d2; unsigned short d3; unsigned char d4[8]; };
            static const Guid kTexture = { 0x85c31227, 0x3de5, 0x4f00,
                                           { 0x9b, 0x3a, 0xf1, 0x1a, 0xc3, 0x8c, 0x18, 0xb5 } };
            using GetContainerFn = long(__stdcall*)(void*, const Guid&, void**);
            void* texture = nullptr;
            const long hr = gx::Vtbl<GetContainerFn>(surface, 11)(surface, kTexture, &texture);
            return hr >= 0 ? texture : nullptr;
        }

        // --- one-shot depth probe ---
        // Copies the world depth at a chosen screen point into a 1x1 R32F target and reads it back, so
        // the sampled value can be compared against the value the shader reconstructs. Logged once.
        void* g_probePS = nullptr;
        bool  g_probed  = false;
        float g_probeRaw = -99.0f;
        float g_probeBeamZ = -1.0f;
        float g_probeUV[2] = { 0.0f, 0.0f };
        int   g_setupPath = -1;
        int   g_setupVS = 0, g_setupPS = 0, g_setupTex = 0;
        int   g_texLevels = -1;
        int   g_texW = 0, g_texH = 0, g_texFmt = 0;

        constexpr const char* kProbeHLSL =
            "sampler2D s0 : register(s0);\n"
            "float4 uv : register(c0);\n"
            "float4 main(float2 t : TEXCOORD0) : COLOR { return tex2Dlod(s0, float4(uv.xy, 0, 0)).rrrr; }\n";

        float ReadDepthAt(gx::Device9 dev, void* depthTexture, const float uv[2])
        {
            auto* d = static_cast<IDirect3DDevice9*>(dev.raw());
            if (!d || !depthTexture) return -99.0f;
            if (!g_probePS) g_probePS = gx::CompilePixelShader(dev, kProbeHLSL, "ps_3_0");
            if (!g_probePS) return -98.0f;
            if (g_texLevels < 0)
            {
                auto* dt = static_cast<IDirect3DTexture9*>(depthTexture);
                D3DSURFACE_DESC sd = {};
                if (SUCCEEDED(dt->GetLevelDesc(0, &sd)))
                {
                    g_texLevels = int(dt->GetLevelCount());
                    g_texW = int(sd.Width);
                    g_texH = int(sd.Height);
                    g_texFmt = int(sd.Format);
                }
            }

            IDirect3DTexture9* target = nullptr;
            IDirect3DSurface9* targetSurface = nullptr;
            IDirect3DSurface9* system = nullptr;
            if (FAILED(d->CreateTexture(1, 1, 1, D3DUSAGE_RENDERTARGET, D3DFMT_R32F, D3DPOOL_DEFAULT, &target, nullptr)))
                return -97.0f;
            target->GetSurfaceLevel(0, &targetSurface);
            if (FAILED(d->CreateOffscreenPlainSurface(1, 1, D3DFMT_R32F, D3DPOOL_SYSTEMMEM, &system, nullptr)))
            {
                gx::Release(targetSurface); gx::Release(target); return -96.0f;
            }

            IDirect3DSurface9* oldRT = nullptr; d->GetRenderTarget(0, &oldRT);
            IDirect3DSurface9* oldDS = nullptr; d->GetDepthStencilSurface(&oldDS);
            IDirect3DPixelShader9* oldPS = nullptr; d->GetPixelShader(&oldPS);
            IDirect3DBaseTexture9* oldTex = nullptr; d->GetTexture(0, &oldTex);
            IDirect3DVertexShader9* oldVS = nullptr; d->GetVertexShader(&oldVS);
            D3DVIEWPORT9 oldVp = {}; d->GetViewport(&oldVp);
            DWORD oldZEnable = 0, oldBlend = 0, oldATest = 0;
            d->GetRenderState(D3DRS_ZENABLE, &oldZEnable);
            d->GetRenderState(D3DRS_ALPHABLENDENABLE, &oldBlend);
            d->GetRenderState(D3DRS_ALPHATESTENABLE, &oldATest);
            DWORD oldMag = 0, oldMin = 0, oldMip = 0;
            d->GetSamplerState(0, D3DSAMP_MAGFILTER, &oldMag);
            d->GetSamplerState(0, D3DSAMP_MINFILTER, &oldMin);
            d->GetSamplerState(0, D3DSAMP_MIPFILTER, &oldMip);

            const D3DVIEWPORT9 vp1 = { 0, 0, 1, 1, 0.0f, 1.0f };
            d->SetRenderTarget(0, targetSurface);
            d->SetDepthStencilSurface(nullptr);
            d->SetViewport(&vp1);
            d->SetRenderState(D3DRS_ZENABLE, D3DZB_FALSE);
            d->SetRenderState(D3DRS_ALPHABLENDENABLE, FALSE);
            d->SetRenderState(D3DRS_ALPHATESTENABLE, FALSE);
            d->SetVertexShader(nullptr);
            d->SetPixelShader(static_cast<IDirect3DPixelShader9*>(g_probePS));
            const float uvc[4] = { uv[0], uv[1], 0.0f, 0.0f };
            d->SetPixelShaderConstantF(0, uvc, 1);
            d->SetTexture(0, static_cast<IDirect3DBaseTexture9*>(depthTexture));
            d->SetSamplerState(0, D3DSAMP_MAGFILTER, D3DTEXF_POINT);
            d->SetSamplerState(0, D3DSAMP_MINFILTER, D3DTEXF_POINT);
            d->SetSamplerState(0, D3DSAMP_MIPFILTER, D3DTEXF_NONE);
            gx::DrawFullscreenQuad(dev);

            float value = -95.0f;
            if (SUCCEEDED(d->GetRenderTargetData(targetSurface, system)))
            {
                D3DLOCKED_RECT lr;
                if (SUCCEEDED(system->LockRect(&lr, nullptr, D3DLOCK_READONLY)))
                {
                    value = *static_cast<const float*>(lr.pBits);
                    system->UnlockRect();
                }
            }

            // Restore every piece of state the 1x1 probe touched. Missing the viewport here renders the
            // whole rest of the frame -- world included -- into a single pixel.
            d->SetVertexShader(oldVS);
            d->SetPixelShader(oldPS);
            d->SetTexture(0, oldTex);
            d->SetRenderTarget(0, oldRT);
            d->SetDepthStencilSurface(oldDS);
            d->SetViewport(&oldVp);
            d->SetRenderState(D3DRS_ZENABLE, oldZEnable);
            d->SetRenderState(D3DRS_ALPHABLENDENABLE, oldBlend);
            d->SetRenderState(D3DRS_ALPHATESTENABLE, oldATest);
            d->SetSamplerState(0, D3DSAMP_MAGFILTER, oldMag);
            d->SetSamplerState(0, D3DSAMP_MINFILTER, oldMin);
            d->SetSamplerState(0, D3DSAMP_MIPFILTER, oldMip);
            gx::Release(oldVS); gx::Release(oldPS); gx::Release(oldTex);
            gx::Release(oldRT); gx::Release(oldDS);
            gx::Release(system); gx::Release(targetSurface); gx::Release(target);
            return value;
        }

        // --- player occluder mask ---
        //
        // The engine exposes no model bounds to the SDK, so the active player's exact silhouette is
        // collected instead of approximated: its own M2 batches are re-issued into a screen-sized target
        // (StampOccluder), and the beam's pixel shader drops the fragments that land on it. Same geometry,
        // same size, real shape -- arms, weapon and all.
        constexpr uint32_t kFmtA8R8G8B8 = 21; // D3DFMT_A8R8G8B8
        gx::RenderTarget g_mask;
        void* g_maskFillPS   = nullptr;
        void* g_maskCutoutPS = nullptr;
        void* g_maskSamplePS = nullptr;
        bool  g_maskCleared    = false;
        bool  g_maskHasContent = false;

        // Fills the mask with opaque white; the texture alpha is ignored here because a model's diffuse
        // alpha carries material data that would speckle the silhouette.
        constexpr const char* kMaskFillHLSL =
            "float4 main(float2 uv : TEXCOORD0) : COLOR0 { return float4(1,1,1,1); }\n";
        // Alpha-tested batches (hair, capes, wings) follow their real cutout instead of a solid card.
        constexpr const char* kMaskCutoutHLSL =
            "sampler2D s0 : register(s0);\n"
            "float4 main(float2 uv : TEXCOORD0) : COLOR0 { clip(tex2D(s0, uv).a - 0.5); return float4(1,1,1,1); }\n";
        // Beam side: keep the light's colour, scale its alpha to nothing wherever the mask is set.
        constexpr const char* kMaskSampleHLSL =
            "sampler2D s0 : register(s0);\n"
            "float4 scale : register(c0);\n"
            "float4 main(float4 color : COLOR0, float4 vpos : VPOS) : COLOR0 {\n"
            "  float m = tex2D(s0, vpos.xy * scale.xy).a;\n"
            "  return float4(color.rgb, color.a * (1.0 - m));\n"
            "}\n";

        class ScopedDeviceState final
        {
        public:
            explicit ScopedDeviceState(gx::Device9 dev)
            {
                auto* d = static_cast<IDirect3DDevice9*>(dev.raw());
                if (d && SUCCEEDED(d->CreateStateBlock(D3DSBT_ALL, &state_)) && state_)
                    state_->Capture();
            }
            ~ScopedDeviceState() { if (state_) { state_->Apply(); state_->Release(); } }
        private:
            IDirect3DStateBlock9* state_ = nullptr;
        };
    }

    bool ProbeResult(float* raw, float* beamZ, float* uv)
    {
        if (!g_probed) return false;
        *raw = g_probeRaw;
        *beamZ = g_probeBeamZ;
        uv[0] = g_probeUV[0];
        uv[1] = g_probeUV[1];
        return true;
    }

    bool SetupResult(int* path, int* vs, int* ps, int* tex)
    {
        if (g_setupPath < 0) return false;
        *path = g_setupPath;
        *vs = g_setupVS;
        *ps = g_setupPS;
        *tex = g_setupTex;
        return true;
    }

    float ReadDepthAtUV(wxl::game::gx::Device9 dev, void* sceneDepth, float u, float v)
    {
        void* const tex = DepthTexture(sceneDepth);
        if (!tex) return -99.0f;
        const float uv[2] = { u, v };
        return ReadDepthAt(dev, tex, uv);
    }

    bool DepthTextureInfo(int* levels, int* w, int* h, int* fmt)
    {
        if (g_texLevels < 0) return false;
        *levels = g_texLevels;
        *w = g_texW;
        *h = g_texH;
        *fmt = g_texFmt;
        return true;
    }

    void OnDeviceLost()
    {
        gx::Release(g_depthVS);
        gx::Release(g_depthPS);
        g_depthVS = nullptr;
        g_depthPS = nullptr;
        gx::Release(g_mask);
        gx::Release(g_maskFillPS);
        gx::Release(g_maskCutoutPS);
        gx::Release(g_maskSamplePS);
        g_maskFillPS = g_maskCutoutPS = g_maskSamplePS = nullptr;
    }

    void ResetOccluder()
    {
        // The mask is only trusted for the frame that stamped it: a frame the player did not draw
        // leaves nothing to sample, so the previous silhouette must not linger.
        g_maskCleared    = false;
        g_maskHasContent = false;
    }

    void StampOccluder(gx::Device9 dev, int primType, int baseVertex, unsigned minIndex,
                       unsigned numVerts, unsigned startIndex, unsigned primCount)
    {
        if (!dev) return;
        if (!g_mask.surface && !gx::EnsureBackbufferTarget(dev, g_mask, kFmtA8R8G8B8)) return;
        // Mesh only: attached particles, glows and billboards ride the same model context with alpha
        // blending on, and letting them in would mask the beam over their broad cards.
        if (dev.GetRenderState(gx::rs::kAlphaBlend) != 0) return;
        if (!g_maskFillPS)   g_maskFillPS   = gx::CompilePixelShader(dev, kMaskFillHLSL,   "ps_2_0");
        if (!g_maskCutoutPS) g_maskCutoutPS = gx::CompilePixelShader(dev, kMaskCutoutHLSL, "ps_2_0");
        if (!g_maskFillPS) return;

        ScopedDeviceState state(dev);
        void* oldRT = nullptr; dev.GetRenderTarget(0, &oldRT);
        void* oldDS = nullptr; dev.GetDepthStencil(&oldDS);
        void* oldPS = nullptr; dev.GetPixelShader(&oldPS);
        unsigned char oldVP[24]; dev.GetViewport(oldVP);
        const unsigned sAB = dev.GetRenderState(gx::rs::kAlphaBlend);
        const unsigned sZE = dev.GetRenderState(gx::rs::kZEnable);
        const unsigned sZW = dev.GetRenderState(gx::rs::kZWrite);
        const unsigned sZF = dev.GetRenderState(gx::rs::kZFunc);
        const unsigned sCW = dev.GetRenderState(gx::rs::kColorWrite);
        const unsigned sSt = dev.GetRenderState(gx::rs::kStencilEnable);
        const unsigned sSc = dev.GetRenderState(gx::rs::kScissorTest);
        const unsigned alphaRef = dev.GetRenderState(24 /*D3DRS_ALPHAREF*/);
        const bool cutout = dev.GetRenderState(gx::rs::kAlphaTest) != 0 && alphaRef >= 8;

        dev.SetRenderTarget(0, g_mask.surface);
        // No depth test. The mask target is non-multisampled while the scene depth is multisampled at
        // x2 but not at x1, and that mismatched pair made the stamp fill at x2 and come out empty at
        // x1 (the beam passed straight through the player). The player is always between the camera
        // and the beam, and a player behind terrain is already covered by the CPU trace, so the depth
        // test is not needed here and only made the result depend on the antialiasing setting. Depth
        // writes stay off regardless.
        dev.SetDepthStencil(oldDS);
        dev.SetRenderState(gx::rs::kZEnable, 0);
        dev.SetRenderState(gx::rs::kZWrite, 0);
        dev.SetRenderState(gx::rs::kColorWrite, gx::colorwrite::kAll);
        dev.SetRenderState(gx::rs::kStencilEnable, 0);
        dev.SetRenderState(gx::rs::kScissorTest, 0);
        if (!g_maskCleared)
        {
            dev.Clear(0, nullptr, gx::clear::kColor, 0x00000000, 1.0f, 0);
            g_maskCleared = true;
        }
        dev.SetRenderState(gx::rs::kAlphaBlend, 0);
        dev.SetPixelShader(cutout ? g_maskCutoutPS : g_maskFillPS);
        dev.DrawIndexedPrimitive(primType, baseVertex, minIndex, numVerts, startIndex, primCount);
        g_maskHasContent = true;

        dev.SetPixelShader(oldPS);
        dev.SetRenderTarget(0, oldRT);
        dev.SetDepthStencil(oldDS);
        dev.SetViewport(oldVP);
        dev.SetRenderState(gx::rs::kAlphaBlend, sAB);
        dev.SetRenderState(gx::rs::kZEnable, sZE);
        dev.SetRenderState(gx::rs::kZWrite, sZW);
        dev.SetRenderState(gx::rs::kZFunc, sZF);
        dev.SetRenderState(gx::rs::kColorWrite, sCW);
        dev.SetRenderState(gx::rs::kStencilEnable, sSt);
        dev.SetRenderState(gx::rs::kScissorTest, sSc);
        gx::Release(oldRT); gx::Release(oldDS); gx::Release(oldPS);
    }

    void Clear() { g_vertices.clear(); }
    size_t Pending() { return g_vertices.size() / 3; }
    void SetDepth(gfx::Depth depth) { g_depth = depth; }

    // The scene matrices the world was actually drawn with. gfx::SceneMatrices reports the projection
    // the client keeps for world geometry, but a module that wraps the device (wxl-modern-water) can
    // leave a different one in effect, and then a beam placed with the wrong projection lands right in
    // x/y but tests at the wrong depth. A caller that captured the live device matrices earlier in the
    // frame (at a world draw) hands them over here so the beam uses the same ones the depth was.
    void SetMatrices(const float* view, const float* projection)
    {
        if (!view || !projection) { g_hasMatrices = false; return; }
        std::memcpy(g_viewOverride, view, sizeof(g_viewOverride));
        std::memcpy(g_projOverride, projection, sizeof(g_projOverride));
        g_hasMatrices = true;
    }
    void SetPush(float yards, float perYard)
    {
        g_push        = yards   > 0.0f ? yards   : 0.0f;
        g_pushPerYard = perYard > 0.0f ? perYard : 0.0f;
    }

    void Triangle(const float a[3], const float b[3], const float c[3],
                  gfx::Color ca, gfx::Color cb, gfx::Color cc)
    {
        g_vertices.push_back(Vertex{ a[0], a[1], a[2], ca });
        g_vertices.push_back(Vertex{ b[0], b[1], b[2], cb });
        g_vertices.push_back(Vertex{ c[0], c[1], c[2], cc });
    }

    long Draw(gx::Device9 dev, void* sceneDepth)
    {
        // Emptied on every path, including a graphics-down one, so a module that queues while the
        // device is away never has its shapes appear all at once when it comes back.
        struct Emptied { ~Emptied() { g_vertices.clear(); } } emptied;

        if (!dev || g_vertices.empty()) return 0;

        float view[16], projection[16];
        if (g_hasMatrices)
        {
            std::memcpy(view, g_viewOverride, sizeof(view));
            std::memcpy(projection, g_projOverride, sizeof(projection));
        }
        else if (!gfx::SceneMatrices(view, projection))
        {
            return 0;
        }

        void* oldVS = nullptr; dev.GetVertexShader(&oldVS);
        void* oldPS = nullptr; dev.GetPixelShader(&oldPS);

        void* oldTextures[kMaxTextureStages] = {};
        for (unsigned i = 0; i < kMaxTextureStages; ++i)
            dev.GetTexture(i, &oldTextures[i]);

        void* oldDepth = nullptr;
        if (sceneDepth)
        {
            dev.GetDepthStencil(&oldDepth);
            dev.SetDepthStencil(sceneDepth);
        }

        float oldWorld[16], oldView[16], oldProjection[16];
        dev.GetTransform(gx::ts::kWorld, oldWorld);
        dev.GetTransform(gx::ts::kView, oldView);
        dev.GetTransform(gx::ts::kProjection, oldProjection);

        unsigned oldStates[kTouchedStateCount];
        for (size_t i = 0; i < kTouchedStateCount; ++i)
            oldStates[i] = dev.GetRenderState(kTouchedStates[i]);

        unsigned oldStages[kTouchedStageCount];
        for (size_t i = 0; i < kTouchedStageCount; ++i)
            oldStages[i] = dev.GetTextureStageState(kTouchedStages[i][0], kTouchedStages[i][1]);

        // Untextured, unlit, vertex-coloured geometry through the fixed-function pipeline. Every one of
        // these is inherited from whatever drew last, and any one left wrong rejects the draw outright
        // or repaints it in a colour that is not the one asked for.
        dev.SetVertexShader(nullptr);
        dev.SetPixelShader(nullptr);
        for (unsigned i = 0; i < kMaxTextureStages; ++i)
            dev.SetTexture(i, nullptr);
        dev.SetFVF(gx::fvf::kXyz | gx::fvf::kDiffuse);

        dev.SetTextureStageState(0, gx::tss::kColorOp,   gx::top::kSelectArg1);
        dev.SetTextureStageState(0, gx::tss::kColorArg1, gx::ta::kDiffuse);
        dev.SetTextureStageState(0, gx::tss::kAlphaOp,   gx::top::kSelectArg1);
        dev.SetTextureStageState(0, gx::tss::kAlphaArg1, gx::ta::kDiffuse);
        dev.SetTextureStageState(1, gx::tss::kColorOp,   gx::top::kDisable);

        // The scene's view matrix carries no translation: the world is drawn about the camera, so a
        // world-space vertex has to be moved to that origin or it projects thousands of units away.
        float eye[3];
        cam::GetPosition(eye);

        // Pull every vertex toward the eye along its own ray. A point moved along the ray keeps its
        // screen pixel and only loses depth, so this is a distance (yards the terrain LOD can differ
        // by) rather than a depth-buffer unit -- and it cannot reorder the beacon against anything more
        // than `push` yards nearer than it. This is what keeps the beacon ahead of the coarser terrain
        // LOD at range, where the surface the client renders sits above the collision height the body
        // was placed on; without it a plain depth test hides the beacon beyond a few yards. It is
        // disabled in Through mode, where depth is not consulted at all.
        if (g_push > 0.0f || g_pushPerYard > 0.0f)
        {
            for (Vertex& v : g_vertices)
            {
                const float dx = v.x - eye[0];
                const float dy = v.y - eye[1];
                const float dz = v.z - eye[2];
                const float dist = sqrtf(dx * dx + dy * dy + dz * dz);
                if (dist <= 1.0e-3f) continue;

                float nearDist = dist - (g_push + g_pushPerYard * dist);
                if (nearDist < dist * 0.25f) nearDist = dist * 0.25f; // never cross the eye
                const float s = nearDist / dist;
                v.x = eye[0] + dx * s;
                v.y = eye[1] + dy * s;
                v.z = eye[2] + dz * s;
            }
        }

        const float toCameraOrigin[16] = {
            1.0f,    0.0f,    0.0f,    0.0f,
            0.0f,    1.0f,    0.0f,    0.0f,
            0.0f,    0.0f,    1.0f,    0.0f,
            -eye[0], -eye[1], -eye[2], 1.0f,
        };

        dev.SetTransform(gx::ts::kWorld, toCameraOrigin);
        dev.SetTransform(gx::ts::kView, view);
        dev.SetTransform(gx::ts::kProjection, projection);

        dev.SetRenderState(gx::rs::kLighting, 0);
        dev.SetRenderState(gx::rs::kFogEnable, 0); // world fog would tint the beacon with distance
        dev.SetRenderState(gx::rs::kCullMode, gx::cull::kNone);
        // Discard a fragment whose interpolated alpha is at or below ~1.5% (4 of 255). Additive light
        // contributes almost nothing there, so the test trims the all-but-transparent rim and the
        // faded ends of the falloff before they reach the blender, reclaiming fill on the soft edges.
        // The cut sits below anything the eye can resolve against the world, so the picture is
        // unchanged.
        dev.SetRenderState(gx::rs::kAlphaTest, 1);
        dev.SetRenderState(24 /*D3DRS_ALPHAREF*/, 4);
        dev.SetRenderState(25 /*D3DRS_ALPHAFUNC*/, 5 /*D3DCMP_GREATER*/);
        dev.SetRenderState(gx::rs::kStencilEnable, 0);
        dev.SetRenderState(gx::rs::kScissorTest, 0);
        dev.SetRenderState(gx::rs::kColorWrite, gx::colorwrite::kAll);
        dev.SetRenderState(gx::rs::kShadeMode, gx::shade::kGouraud);

        // Light adds to the frame rather than covering it: source colour scaled by its own alpha,
        // added straight onto what is behind. That both keeps the shaft from looking like a pane of
        // coloured glass and makes overlapping soft geometry sum into a glow.
        dev.SetRenderState(gx::rs::kAlphaBlend, 1);
        dev.SetRenderState(gx::rs::kSrcBlend, gx::blend::kSrcAlpha);
        dev.SetRenderState(gx::rs::kDestBlend, kBlendOne);
        dev.SetRenderState(gx::rs::kZWrite, 0); // a marker is not part of the world

        if (g_depth == gfx::Depth::Through)
        {
            dev.SetRenderState(gx::rs::kZEnable, 0);
            // The player's exact silhouette, sampled per fragment: where it covers the screen the
            // beam's alpha is scaled to nothing, so the shaft disappears behind the character's real
            // shape instead of a stand-in box.
            if (g_maskHasContent && g_mask.texture)
            {
                if (!g_maskSamplePS) g_maskSamplePS = gx::CompilePixelShader(dev, kMaskSampleHLSL, "ps_3_0");
                if (g_maskSamplePS)
                {
                    const float scale[4] = { 1.0f / float(g_mask.width), 1.0f / float(g_mask.height), 0.0f, 0.0f };
                    dev.SetTexture(0, g_mask.texture);
                    dev.SetSamplerState(0, gx::samp::kAddressU,  gx::address::kClamp);
                    dev.SetSamplerState(0, gx::samp::kAddressV,  gx::address::kClamp);
                    dev.SetSamplerState(0, gx::samp::kMagFilter, gx::filter::kPoint);
                    dev.SetSamplerState(0, gx::samp::kMinFilter, gx::filter::kPoint);
                    dev.SetSamplerState(0, gx::samp::kMipFilter, gx::filter::kNone);
                    dev.SetPixelShader(g_maskSamplePS);
                    dev.SetPixelShaderConstantF(0, scale, 1);
                }
            }
        }
        else
        {
            // Which end of the depth range is near is a property of the client's projection, not a
            // constant: standard depth maps near to 0 and wants LessEqual, a reversed-Z projection maps
            // near to 1 and wants GreaterEqual. d(ndcZ)/d(viewZ) is -proj[14]*proj[11], so its sign
            // says which one this is -- and using the wrong one inverts the whole test, hiding the
            // beacon where it should show and showing it where something should hide it.
            const bool reversed = (-projection[14] * projection[11]) < 0.0f;

            // Prefer the explicit test: bind the world depth and let the pixel shader reject what is
            // in front. The fixed-function test is kept only for a client whose depth surface is not a
            // sampleable texture, or whose d3dcompiler is missing.
            void* const depthTexture = DepthTexture(sceneDepth);
            if (!g_depthVS) g_depthVS = CompileVertexShader(dev, kOcclusionVSHLSL);
            if (!g_depthPS) g_depthPS = gx::CompilePixelShader(dev, kOcclusionPSHLSL, "ps_3_0");
            if (g_setupPath < 0)
            {
                g_setupVS   = g_depthVS ? 1 : 0;
                g_setupPS   = g_depthPS ? 1 : 0;
                g_setupTex  = depthTexture ? 1 : 0;
                g_setupPath = (g_depthVS && g_depthPS && depthTexture) ? 1 : 2;
            }

            if (g_depthVS && g_depthPS && depthTexture)
            {
                // The vertex shader takes the whole point to clip transform, so it needs the world
                // matrix folded in; the pixel shader only needs the depth mapping.
                float worldView[16], worldViewProj[16];
                Mul4x4(toCameraOrigin, view, worldView);
                Mul4x4(worldView, projection, worldViewProj);

                struct Viewport { unsigned x, y, width, height; float minZ, maxZ; };
                Viewport vp = {};
                dev.GetViewport(&vp);
                const float span[4] = { vp.minZ, projection[14], vp.maxZ - vp.minZ, projection[10] };

                if (!g_probed && !g_vertices.empty())
                {
                    g_probed = true;
                    const Vertex& v0 = g_vertices[0];
                    const float px = v0.x - eye[0], py = v0.y - eye[1], pz = v0.z - eye[2];
                    const float vx = px * view[0] + py * view[4] + pz * view[8] + view[12];
                    const float vy = px * view[1] + py * view[5] + pz * view[9] + view[13];
                    const float vz = px * view[2] + py * view[6] + pz * view[10] + view[14];
                    const float cx = vx * projection[0] + vy * projection[4] + vz * projection[8] + projection[12];
                    const float cy = vx * projection[1] + vy * projection[5] + vz * projection[9] + projection[13];
                    const float cw = vz * projection[11];
                    g_probeUV[0] = cw != 0.0f ? 0.5f * cx / cw + 0.5f : 0.5f;
                    g_probeUV[1] = cw != 0.0f ? -0.5f * cy / cw + 0.5f : 0.5f;
                    g_probeBeamZ = cw;
                    g_probeRaw = ReadDepthAt(dev, depthTexture, g_probeUV);
                }

                // Sampling the surface that is still bound as the depth target is feedback; DXVK may
                // answer with something other than the depth. The shader does the test itself, so the
                // fixed-function depth target is not needed for this draw.
                dev.SetDepthStencil(nullptr);

                using SetVSConstFn = long(__stdcall*)(void*, unsigned, const float*, unsigned);
                gx::Vtbl<SetVSConstFn>(dev.raw(), 94 /* SetVertexShaderConstantF */)(dev.raw(), 0, worldViewProj, 4);
                dev.SetVertexShader(g_depthVS);
                dev.SetPixelShader(g_depthPS);
                dev.SetPixelShaderConstantF(0, span, 1);
                dev.SetTexture(0, depthTexture);
                dev.SetSamplerState(0, gx::samp::kAddressU,  gx::address::kClamp);
                dev.SetSamplerState(0, gx::samp::kAddressV,  gx::address::kClamp);
                dev.SetSamplerState(0, gx::samp::kMagFilter, gx::filter::kPoint);
                dev.SetSamplerState(0, gx::samp::kMinFilter, gx::filter::kPoint);
                dev.SetSamplerState(0, gx::samp::kMipFilter, gx::filter::kNone);
                dev.SetRenderState(gx::rs::kZEnable, 0);
            }
            else
            {
                dev.SetRenderState(gx::rs::kZEnable, 1);
                dev.SetRenderState(gx::rs::kZFunc, reversed ? kGreaterEqual : gx::cmp::kLessEqual);
            }
        }

        const long result = dev.DrawPrimitiveUP(gx::prim::kTriangleList,
                                                unsigned(g_vertices.size() / 3),
                                                g_vertices.data(), sizeof(Vertex));

        for (size_t i = 0; i < kTouchedStageCount; ++i)
            dev.SetTextureStageState(kTouchedStages[i][0], kTouchedStages[i][1], oldStages[i]);
        for (size_t i = 0; i < kTouchedStateCount; ++i)
            dev.SetRenderState(kTouchedStates[i], oldStates[i]);

        dev.SetTransform(gx::ts::kWorld, oldWorld);
        dev.SetTransform(gx::ts::kView, oldView);
        dev.SetTransform(gx::ts::kProjection, oldProjection);

        if (sceneDepth)
        {
            dev.SetDepthStencil(oldDepth);
            gx::Release(oldDepth);
        }

        for (unsigned i = 0; i < kMaxTextureStages; ++i)
        {
            dev.SetTexture(i, oldTextures[i]);
            gx::Release(oldTextures[i]);
        }
        dev.SetPixelShader(oldPS);
        dev.SetVertexShader(oldVS);

        gx::Release(oldPS);
        gx::Release(oldVS);

        return result;
    }
}
