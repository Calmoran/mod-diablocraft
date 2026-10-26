// World camera matrix globals and the per-frame matrix builder address.
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
#include <cstddef>

// INTERNAL to the core. The world camera matrices, as static globals (the image is fixed-base, no
// ASLR, so they are read directly). float[16], row-major, D3D row-vector convention. They are valid
// only in-world: at the login / loading screen they sit at identity with the camera at the origin.
namespace wxl::offsets::engine::camera
{
    constexpr uintptr_t kProjection = 0x00ADF628;
    constexpr uintptr_t kView       = 0x00ADF5E8; // world -> view
    constexpr uintptr_t kViewProj   = 0x00ADF460;
    constexpr uintptr_t kCameraPos  = 0x00CD8F5C; // vec3

    // Per-frame builder that recomputes the view/projection from the camera state.
    constexpr uintptr_t kBuildCameraMatrices = 0x00795400;

    // --- the camera the world renderer reads ---
    // Returns the active world-frame camera (*(worldFrame + 0x7E20)), or null when there is no world
    // frame. The world scene render calls it and immediately calls a virtual on the result, so this is
    // where a scene rendered outside the world has to supply one.
    constexpr uintptr_t kGetActiveCamera = 0x004F5960;
    using GetActiveCameraFn = void*(__cdecl*)();

    // The camera vtable, exactly four entries: field of view, forward, right, up. Each is a single
    // field read, so an object laid out as below and pointed at this vtable answers all four with the
    // engine's own implementations rather than a hand-written stand-in.
    constexpr uintptr_t kSimpleCameraVTable = 0x00A1E864;
    constexpr size_t kCameraPosition = 0x08; // float[3]
    constexpr size_t kCameraForward  = 0x14; // float[3]
    constexpr size_t kCameraRight    = 0x20; // float[3]
    constexpr size_t kCameraUp       = 0x2C; // float[3]
    constexpr size_t kCameraFov      = 0x40; // float, full angle in radians

#pragma pack(push, 1)
    /** @brief The part of a camera the world renderer reads, at the offsets its methods use. */
    struct SimpleCamera
    {
        const void* vtable;                                  // 0x00
        uint8_t     _pad04[kCameraPosition - sizeof(void*)];
        float       position[3];                             // kCameraPosition
        float       forward[3];                              // kCameraForward
        float       right[3];                                // kCameraRight
        float       up[3];                                   // kCameraUp
        uint8_t     _pad38[kCameraFov - (kCameraUp + 12)];
        float       fov;                                     // kCameraFov
        // Slack for the fields past the four methods, which are not mapped: the engine only ever sees
        // this object through them, but it must not be shorter than what it claims to be.
        uint8_t     _tail[0x40];
    };
    static_assert(offsetof(SimpleCamera, position) == kCameraPosition, "SimpleCamera.position");
    static_assert(offsetof(SimpleCamera, forward)  == kCameraForward,  "SimpleCamera.forward");
    static_assert(offsetof(SimpleCamera, right)    == kCameraRight,    "SimpleCamera.right");
    static_assert(offsetof(SimpleCamera, up)       == kCameraUp,       "SimpleCamera.up");
    static_assert(offsetof(SimpleCamera, fov)      == kCameraFov,      "SimpleCamera.fov");
#pragma pack(pop)

    // Camera and view
    /// The world projection setup, ahead of the already-known matrix build - the place to change FOV or
    /// aspect handling for ultrawide or custom projections. __cdecl, caller-cleaned.
    constexpr uintptr_t kWorldProjectionSetup              = 0x004BF0C0;
    /// The actual screen-to-world ray construction under the known public wrapper - the right level to
    /// correct the ray for a modified projection. __cdecl, caller-cleaned.
    constexpr uintptr_t kScreenRayBuild                    = 0x004BF0F0;
    /// The small per-frame test that gates the underwater screen effect and audio - a modern-water
    /// extension can answer it from its own volumes. __thiscall, caller-cleaned.
    constexpr uintptr_t kUnderwaterCheck                   = 0x005FE7B0;
    /// The highest-fanout camera placement call in the client (12 sites) - one detour observes or
    /// overrides every camera repositioning. __thiscall, 3 stack args.
    constexpr uintptr_t kViewSet                           = 0x00603330;
    /// The per-frame camera advance, above matrix construction - the place to inject camera shake,
    /// offsets or a scripted path. __cdecl, caller-cleaned. Confirmed signature: two stack args,
    /// called as (0, cam) once per frame from a single call site, on the client's one main thread -
    /// cam is the same object kGetActiveCamera returns. An ordinary three-instruction prologue, no
    /// reentrancy concern - a plain HookAttach target like any other.
    constexpr uintptr_t kUpdateCallback                    = 0x00607B00;
    using UpdateCallbackFn = void(__cdecl*)(int unusedFirst, void* cam);

    // --- managed coordinate slots ---
    // A camera object (as returned by kGetActiveCamera) holds an array of "managed coordinate"
    // slots, each a small polymorphic object read/written through these two entry points rather
    // than as plain struct fields. Every caller of CameraGetCoord found in the binary uses only
    // index 7 (position) and 8 (target/look-at point), always as a pair - there is no separate yaw
    // concept, look direction is implied by position-to-target. During a real cinematic these two
    // slots are driven read-only by the active M2's own camera spline (a live-evaluated callback);
    // CameraSetCoord below only succeeds against a slot that is not in that mode.

    /// Reads a managed coordinate slot's current value (index 7 = position, 8 = target). Fails
    /// silently (leaves *out untouched, no visible return) if the slot isn't populated as a vector
    /// coordinate - there is no success/failure return value to check directly. __cdecl.
    constexpr uintptr_t kCameraGetCoord = 0x004C1290;
    using CameraGetCoordFn = void(__cdecl*)(void* cam, uint32_t index, float* out);

    /// Writes a new value into a managed coordinate slot directly, bypassing any spline/callback.
    /// Already used this way in retail for a camera attached to an M2 attachment point (vehicle
    /// seats and similar) - not something this project invented. Succeeds only if the target slot
    /// is already an allocated "manual/settable"-mode coordinate object; fails silently otherwise,
    /// same caveat as CameraGetCoord above. freezeAxisFlags bit 0x04/0x02/0x01 keeps the slot's
    /// current Z/Y/X instead of overwriting it from vec. __cdecl.
    constexpr uintptr_t kCameraSetCoord = 0x004C12B0;
    using CameraSetCoordFn = void(__cdecl*)(void* cam, uint32_t index, const float* vec, uint8_t freezeAxisFlags);
}
