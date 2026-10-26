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
// Compile: fxc /T ps_3_0 /E main /Fh CombinersModAddAlphaPs.h /Vn kCombinersModAddAlphaPs CombinersModAddAlpha.ps.hlsl

sampler2D sDiffuse : register(s0); // base texture (texture unit 0)
sampler2D sOverlay : register(s1); // additive overlay texture (texture unit 1)

float4 gFogColor : register(c2); // xyz = fog colour; matches the stock combiner's fog register

// Sharpens the linear per-vertex grazing term into a steeper falloff: unchanged near full-facing, but
// dropping toward zero much closer to the true silhouette than the raw interpolated value would --
// linear left a thin but visible ring where alpha was small but not yet zero. Tuned by eye; 3.0 was the
// first value that reliably hid the mesh edge without also visibly shrinking the haze itself.
static const float kGrazingPower = 3.0;

float4 main(float4 color : COLOR0, float2 uv0 : TEXCOORD0, float2 uv1 : TEXCOORD1, float fog : FOG,
           float grazing : TEXCOORD2) : COLOR
{
    float4 base    = tex2D(sDiffuse, uv0);
    float4 overlay = tex2D(sOverlay, uv1);

    float3 rgb = (color.rgb * base.rgb + overlay.rgb * overlay.a) * gFogColor.rgb;
    rgb = lerp(gFogColor.rgb, rgb, fog);

    return float4(rgb, base.a * pow(grazing, kGrazingPower));
}
