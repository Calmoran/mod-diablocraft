// wxl-unit-outline: a reaction-colored silhouette outline on the mouseover and target units.
// A render script: it owns its shaders and logic and draws through the core gx facade; it never
// touches an offset or installs a hook. It subscribes to render events and self-registers at load.
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

namespace
{
    // Writes a batch into the mask, following the diffuse cutout. Wings, hair and fur are cards whose
    // shape lives entirely in texture alpha, so filling their quads solid traces the card instead of
    // the creature and the silhouette comes out as straight polygon edges.
    //
    // 0.5 is the cutout threshold the art is authored against, and the silhouette has to match what
    // the engine actually draws. A card does not end on a hard alpha edge -- it ramps down -- so a
    // lower threshold keeps the transparent fringe and outlines pixels nobody can see, which reads as
    // an angular shape floating around the model.
    const char* kFillHLSL =
        "sampler2D s0 : register(s0);\n"
        "float4 c0 : register(c0);\n"
        "float4 main(float2 uv : TEXCOORD0) : COLOR0 {\n"
        "  clip(tex2D(s0, uv).a - 0.5);\n"
        "  return c0;\n"
        "}\n";

    // A 9-tap Gaussian taken in 5 fetches, run twice with c0.xy carrying the axis. One shader rather
    // than the separate horizontal and vertical ones a baked-direction pipeline needs: the axis is a
    // constant here, so a second compile would buy nothing.
    //
    // The fractional offsets are the trick: each one lands between two texels, so bilinear filtering
    // returns their weighted pair in a single fetch. Fewer fetches than the 9 point taps it replaces
    // AND a smoother result, since the kernel is no longer quantised to texel centres. It relies on
    // linear filtering being set -- OutlinePass states it rather than inheriting it.
    //
    // RGB is premultiplied by coverage -- the fill writes colour only where it writes alpha, and the
    // mask is cleared to zero -- so colour and coverage blur together and divide back out in apply.
    const char* kBlurHLSL =
        "sampler2D m : register(s0);\n"
        "float4 p : register(c0);\n" // xy = texel step along the axis, z = spread
        "float4 main(float2 uv : TEXCOORD0) : COLOR0 {\n"
        "  float2 o = p.xy * p.z;\n"
        "  float4 s = tex2D(m, uv) * 0.2270270270;\n"
        "  s += (tex2D(m, uv + o*1.3846153846) + tex2D(m, uv - o*1.3846153846)) * 0.3162162162;\n"
        "  s += (tex2D(m, uv + o*3.2307692308) + tex2D(m, uv - o*3.2307692308)) * 0.0702702703;\n"
        "  return s;\n"
        "}\n";

    // The halo is the blurred field with the silhouette punched back out, so the unit itself stays
    // untouched and only the falloff around it is drawn.
    const char* kApplyHLSL =
        "sampler2D b : register(s0);\n" // blurred silhouette
        "sampler2D m : register(s1);\n" // original silhouette
        "float4 p : register(c0);\n"    // x = intensity
        "float4 main(float2 uv : TEXCOORD0) : COLOR0 {\n"
        "  float4 blur = tex2D(b, uv);\n"
        "  float inside = tex2D(m, uv).a;\n"
        "  float halo = saturate(blur.a * p.x) * (1.0 - inside);\n"
        "  clip(halo - 0.004);\n"
        "  float3 col = blur.a > 0.001 ? blur.rgb / blur.a : float3(1,1,1);\n"
        "  return float4(col, halo);\n"
        "}\n";
}
