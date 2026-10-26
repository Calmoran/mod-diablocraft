// wxl-loot-beam: the additive, per-vertex-graduated draw the beacon uses.
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

#include "game/Gfx.hpp"
#include "game/Gx.hpp"

#include <cstddef>
#include <cstdint>

// The beacon does not use wxl::game::gfx's flush: that one blends source-over, which makes a light
// shaft read as a coloured pane and cannot make a gradient cheaper than one colour per triangle. This
// is a small, self-contained triangle queue drawn additively (source alpha added to the frame, never
// dimming what is behind it) with a colour on every vertex, so the GPU interpolates the falloffs and a
// handful of quads read as a soft volume. It reads the same scene matrices the world was drawn with,
// so it lands where its world coordinates say.
namespace wxl::scripts::loot_beam::beacon_gfx
{
    /// Empties the queue without drawing it.
    void Clear();

    /// How many triangles are queued.
    size_t Pending();

    /// The depth mode every queued shape is drawn with. Set once per frame before queueing.
    void SetDepth(wxl::game::gfx::Depth depth);

    /**
     * @brief How far every queued shape is pulled toward the eye, in yards, before it is drawn.
     *
     * At range the client renders terrain at a coarser LOD that sits above the collision height the
     * beacon is placed on, so a plain depth test loses the beacon beyond a few yards. Moving a vertex
     * along its own eye ray keeps its screen pixel and only reduces its depth, so a pull clears that
     * LOD without letting the beacon through anything more than `yards` in front of it. perYard scales
     * the pull with camera distance, for error that grows with range. Zero disables the pull.
     */
    void SetPush(float yards, float perYard);

    /// Overrides the scene matrices used to place and depth-test the queue. Null clears the override.
    void SetMatrices(const float* view, const float* projection);

    /// Releases the depth-occlusion shader, which is a DEFAULT-pool resource. Called on device loss;
    /// the shader is rebuilt lazily on the next draw.
    void OnDeviceLost();

    /**
     * @brief Starts a new frame's occluder mask: the previous frame's silhouette is dropped and the
     *        target stays untouched until the player's first batch stamps into it. Called once a frame.
     */
    void ResetOccluder();

    /**
     * @brief Stamps one batch of the active player's model into the occluder mask.
     *
     * The engine gives the SDK no model bounds, so the character's exact silhouette is collected by
     * re-issuing its own M2 batches into a screen-sized target: the same geometry at the same size, not
     * a stand-in box. The batch's vertex stream, shader and world transform are already bound when this
     * is called from the M2 draw, so only the render target and a solid-fill pixel shader are swapped in.
     * @param dev  the live device.
     * @param primType,baseVertex,minIndex,numVerts,startIndex,primCount  the native draw parameters.
     */
    void StampOccluder(wxl::game::gx::Device9 dev, int primType, int baseVertex, unsigned minIndex,
                       unsigned numVerts, unsigned startIndex, unsigned primCount);

    /**
     * @brief Reads the one-shot depth probe taken on the first occluded draw.
     * @param raw    receives the raw scene depth sampled at the beam's screen point.
     * @param beamZ  receives the beam's own view depth (the value the shader compares against).
     * @param uv     receives the screen uv the sample was taken at.
     * @return true if a probe has been taken.
     */
    bool ProbeResult(float* raw, float* beamZ, float* uv);

    /// Reports which occlusion path the last occluded draw took (1 = depth shader, 2 = fixed-function
    /// fallback) and whether the vertex shader, pixel shader and depth texture were available.
    bool SetupResult(int* path, int* vs, int* ps, int* tex);

    /// Reads the world depth at an arbitrary screen uv. Used only by the one-shot depth diagnostic.
    float ReadDepthAtUV(wxl::game::gx::Device9 dev, void* sceneDepth, float u, float v);

    /// Reports the sampled depth texture's level count, size and format, once known.
    bool DepthTextureInfo(int* levels, int* w, int* h, int* fmt);

    /// Queues a triangle with an independent colour at each vertex (Gouraud-interpolated).
    void Triangle(const float a[3], const float b[3], const float c[3],
                  wxl::game::gfx::Color ca, wxl::game::gfx::Color cb, wxl::game::gfx::Color cc);

    /**
     * @brief Draws everything queued and empties it, leaving the device as it was found.
     * @param dev         The live device.
     * @param sceneDepth  The world's depth surface, from OnWorldSceneEnd, or null.
     * @return The device's result for the draw, or 0 when nothing was queued.
     */
    long Draw(wxl::game::gx::Device9 dev, void* sceneDepth);
}
