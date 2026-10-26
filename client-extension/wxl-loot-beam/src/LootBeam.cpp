// wxl-loot-beam: the world-space beacon over lootable NPC bodies.
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

#include "LootBeam.hpp"
#include "BeaconRenderer.hpp"
#include "LootFields.hpp"
#include "UnitFields.hpp"

#include "game/Camera.hpp"
#include "game/Gfx.hpp"
#include "game/Pick.hpp"
#include "game/Script.hpp"
#include "game/Unit.hpp"
#include "game/World.hpp"

#include <windows.h>

#include <cmath>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace wxl::scripts::loot_beam
{
    namespace ev    = wxl::events;
    namespace gfx   = wxl::game::gfx;
    namespace gx    = wxl::game::gx;
    namespace world = wxl::game::world;
    namespace unit  = wxl::game::unit;
    namespace cam   = wxl::game::camera;
    namespace script = wxl::game::script;

    namespace
    {
        using namespace wxl_loot_beam; // the descriptor-field offsets from UnitFields.hpp

        constexpr const char* kIniSection = "LootBeam";
        constexpr float       kTwoPi      = 6.28318530717959f;
        constexpr float       kUnitToByte = 255.0f;
        // Bumped when a shipped default changes in a way an existing file must adopt. A file older
        // than this has its stale keys replaced with the current shipped defaults.
        constexpr int         kConfigVersion = 9;

        // INI key stem and panel label per GearTier, in the order the panel lists them. The stem names
        // the keys Tier.<Stem>.Enabled and Tier.<Stem>.Color.
        struct TierDef { const char* stem; const char* label; };
        constexpr TierDef kTierDefs[kTierCount] = {
            { "Currency",  "Currency"  },
            { "Poor",      "Poor"      },
            { "Common",    "Common"    },
            { "Uncommon",  "Uncommon"  },
            { "Rare",      "Rare"      },
            { "Epic",      "Epic"      },
            { "Legendary", "Legendary" },
            { "Set",       "Set"       }, // Torment patch (PINNED.md): was Artifact; server value 7
            { "Primal",    "Primal"    }, // Torment patch (PINNED.md): was Heirloom; server value 8
        };

        // Descriptor reads are guarded: a wrong field index or a half-built object reads a nearby heap
        // dword. The validators reject an address that cannot be a live block before the SEH frame is
        // even entered, and the frame catches the rest.
        bool ValidPointer(uintptr_t address, size_t size)
        {
            return address >= 0x10000 && (address & 3) == 0 && address < 0xFFF00000 &&
                   size <= 0xFFF00000 - address;
        }

        bool ReadU32(uintptr_t address, uint32_t& out)
        {
            __try
            {
                out = *reinterpret_cast<const uint32_t*>(address);
                return true;
            }
            __except (EXCEPTION_EXECUTE_HANDLER)
            {
                return false;
            }
        }

        bool ReadPtr(uintptr_t address, uintptr_t& out)
        {
            __try
            {
                out = *reinterpret_cast<const uintptr_t*>(address);
                return true;
            }
            __except (EXCEPTION_EXECUTE_HANDLER)
            {
                return false;
            }
        }

        bool ReadU64(uintptr_t address, unsigned long long& out)
        {
            __try
            {
                out = *reinterpret_cast<const unsigned long long*>(address);
                return true;
            }
            __except (EXCEPTION_EXECUTE_HANDLER)
            {
                return false;
            }
        }

        float Clamp01(float v) { return v < 0.0f ? 0.0f : (v > 1.0f ? 1.0f : v); }

        // A tiny xorshift so a mote's drift and flicker vary without <random>'s weight. The state
        // lives on the beacon, seeded from its GUID, so two corpses do not sparkle in lockstep.
        uint32_t NextRandom(uint32_t& state)
        {
            state ^= state << 13;
            state ^= state >> 17;
            state ^= state << 5;
            return state;
        }

        float Random01(uint32_t& state)
        {
            return float(NextRandom(state) >> 8) * (1.0f / 16777216.0f);
        }

        // Puts one mote back at the start of its life: a fresh spot in the beam, a fresh drift and a
        // fresh flicker. The age starts part-way in so a new beacon's motes are not all at the same
        // point of their fade the instant the body appears.
        void SpawnSparkle(Sparkle& sp, uint32_t& rng, const BeamStyle& style)
        {
            const float top  = fmaxf(style.height, style.baseOffset + 0.1f);
            const float span = top - style.baseOffset;
            const float ang  = Random01(rng) * kTwoPi;
            const float rad  = sqrtf(Random01(rng)) * style.beamWidth * 1.5f;
            const float dir  = Random01(rng) * kTwoPi;
            const float drift = style.sparkleDrift * (0.4f + 1.2f * Random01(rng));

            sp.vel[0] = cosf(dir) * drift;
            sp.vel[1] = sinf(dir) * drift;
            sp.vel[2] = style.sparkleRise * (0.5f + Random01(rng));
            sp.life   = style.sparkleLife * (0.6f + 0.8f * Random01(rng));
            sp.age    = Random01(rng) * sp.life * 0.5f;
            sp.twinkle      = Random01(rng) * kTwoPi;
            sp.twinkleSpeed = style.sparkleTwinkle * (0.6f + 0.8f * Random01(rng));

            // Spread the field over most of the beam's height so a tall marker is not just a hot
            // base; the initial age is applied to the offset so the fade is desynced too. The
            // birth height is biased low -- min of three uniforms is a quadratic falloff -- so motes
            // are born progressively less often the higher they are, denser at the foot than the crest.
            const float h = fminf(fminf(Random01(rng), Random01(rng)), Random01(rng));
            sp.pos[0] = cosf(ang) * rad + sp.vel[0] * sp.age;
            sp.pos[1] = sinf(ang) * rad + sp.vel[1] * sp.age;
            sp.pos[2] = style.baseOffset + span * 0.85f * h + sp.vel[2] * sp.age;
        }

        // Drifts one mote and respawns it once it has outlived its life or climbed out of the beam.
        void AdvanceSparkle(Sparkle& sp, uint32_t& rng, const BeamStyle& style, float dt)
        {
            sp.age += dt;
            sp.pos[0] += sp.vel[0] * dt;
            sp.pos[1] += sp.vel[1] * dt;
            sp.pos[2] += sp.vel[2] * dt;
            sp.twinkle += sp.twinkleSpeed * dt;

            const float top = fmaxf(style.height, style.baseOffset + 0.1f);
            if (sp.age >= sp.life || sp.pos[2] > top)
                SpawnSparkle(sp, rng, style);
        }

        gfx::Color Pack(float alpha, const float rgb[3])
        {
            const uint32_t a = uint32_t(Clamp01(alpha) * kUnitToByte + 0.5f);
            const uint32_t r = uint32_t(Clamp01(rgb[0]) * kUnitToByte + 0.5f);
            const uint32_t g = uint32_t(Clamp01(rgb[1]) * kUnitToByte + 0.5f);
            const uint32_t b = uint32_t(Clamp01(rgb[2]) * kUnitToByte + 0.5f);
            return (a << 24) | (r << 16) | (g << 8) | b;
        }

        /**
         * @brief Reads a unit's health field. False when the object has no readable update block.
         */
        bool UnitHealth(void* unit, uint32_t& health)
        {
            uintptr_t descriptors = 0;
            if (!ReadPtr(reinterpret_cast<uintptr_t>(unit) + kObjectDescriptorField, descriptors))
                return false;
            if (!ValidPointer(descriptors, kUnitHealthField + sizeof(uint32_t)))
                return false;
            return ReadU32(descriptors + kUnitHealthField, health);
        }

        /**
         * @brief Reads the server's loot-beam tier off a corpse. False when there is no hint.
         *
         * The companion AzerothCore module (mod-loot-beam) writes the corpse's tier into
         * UNIT_FIELD_PADDING: 1..8 are item qualities 0..7 stored as quality + 1, 9 is a corpse
         * whose loot held money but no gear, and 0 is the untouched default ("no hint"). That is why
         * a stored value of 1..8 is already the GearTier index it maps to. Anything out of range is
         * treated as no hint, and the locally learned loot is used instead.
         */
        bool UnitLootBeamTier(void* unit, int& tier)
        {
            uintptr_t descriptors = 0;
            if (!ReadPtr(reinterpret_cast<uintptr_t>(unit) + kObjectDescriptorField, descriptors))
                return false;
            if (!ValidPointer(descriptors, kUnitLootBeamField + sizeof(uint32_t)))
                return false;

            uint32_t value = 0;
            if (!ReadU32(descriptors + kUnitLootBeamField, value))
                return false;

            if (value == kLootBeamCurrencyHint)
            {
                tier = kTierCurrency;
                return true;
            }
            if (value < 1 || value > kLootBeamQualityMax + 1)
                return false;

            tier = int(value);
            return true;
        }

        /**
         * @brief True when the object is a unit that is dead and (optionally) still flagged lootable.
         *
         * Dead is the health field being zero. The strict test adds UNIT_DYNFLAG_LOOTABLE, but only
         * trusts the flags value when every set bit is one the field may carry -- a wrong offset lands
         * on unrelated heap whose high bits betray it, and the test then falls back to the health-only
         * verdict instead of turning into noise.
         */
        bool IsLootableCorpse(void* unit, const BeamStyle& style)
        {
            const unsigned mask = world::TypeMask(unit);
            if (!(mask & world::kTypeMaskUnit)) return false;
            if (mask & world::kTypeMaskPlayer) return false; // a player corpse gets its own marker

            uint32_t health = 1;
            if (!UnitHealth(unit, health) || health != 0) return false;

            if (style.requireLootable)
            {
                uintptr_t descriptors = 0;
                if (!ReadPtr(reinterpret_cast<uintptr_t>(unit) + kObjectDescriptorField, descriptors))
                    return false;
                if (!ValidPointer(descriptors, kUnitDynamicFlagsField + sizeof(uint32_t)))
                    return false;

                uint32_t flags = 0;
                const bool read = ReadU32(descriptors + kUnitDynamicFlagsField, flags);
                if (read && (flags & ~kDynamicFlagKnownMask) == 0)
                {
                    if (!(flags & kDynamicFlagLootable)) return false;
                }
            }
            return true;
        }

        // --- INI helpers -------------------------------------------------------------------------

        unsigned long long FileStamp(const std::string& path)
        {
            WIN32_FILE_ATTRIBUTE_DATA data;
            if (!GetFileAttributesExA(path.c_str(), GetFileExInfoStandard, &data))
                return 0;
            return (static_cast<unsigned long long>(data.ftLastWriteTime.dwHighDateTime) << 32) |
                   data.ftLastWriteTime.dwLowDateTime;
        }

        std::string Trim(std::string text)
        {
            const size_t first = text.find_first_not_of(" \t\r\n");
            if (first == std::string::npos)
                return std::string();
            const size_t last = text.find_last_not_of(" \t\r\n");
            return text.substr(first, last - first + 1);
        }

        bool ReadBool(const std::string& path, const char* key, bool fallback)
        {
            return GetPrivateProfileIntA(kIniSection, key, fallback ? 1 : 0, path.c_str()) != 0;
        }

        float ReadFloat(const std::string& path, const char* key, float fallback, float lo, float hi)
        {
            char buf[64] = {};
            GetPrivateProfileStringA(kIniSection, key, "", buf, sizeof(buf), path.c_str());
            if (!buf[0])
                return fallback;
            char* end = nullptr;
            const float v = std::strtof(buf, &end);
            if (end == buf || v != v)
                return fallback;
            return v < lo ? lo : (v > hi ? hi : v);
        }

        int ReadInt(const std::string& path, const char* key, int fallback, int lo, int hi)
        {
            const int v = GetPrivateProfileIntA(kIniSection, key, fallback, path.c_str());
            return v < lo ? lo : (v > hi ? hi : v);
        }

        // Accepts "#RRGGBB" / "RRGGBB" or "R,G,B" (0-255). Anything else leaves out untouched.
        void ReadColor(const std::string& path, const char* key, float out[3])
        {
            char buf[64] = {};
            GetPrivateProfileStringA(kIniSection, key, "", buf, sizeof(buf), path.c_str());
            const std::string text = Trim(buf);
            if (text.empty())
                return;

            int r = -1, g = -1, b = -1;
            if (text.find(',') != std::string::npos)
            {
                if (std::sscanf(text.c_str(), "%d , %d , %d", &r, &g, &b) != 3)
                    return;
            }
            else
            {
                const char* hex = text.c_str();
                if (*hex == '#')
                    ++hex;
                char* end = nullptr;
                const unsigned long v = std::strtoul(hex, &end, 16);
                if (end == hex || *end != '\0' || std::strlen(hex) != 6)
                    return;
                r = int((v >> 16) & 0xFF);
                g = int((v >> 8) & 0xFF);
                b = int(v & 0xFF);
            }

            out[0] = Clamp01(float(r < 0 ? 0 : (r > 255 ? 255 : r)) / 255.0f);
            out[1] = Clamp01(float(g < 0 ? 0 : (g > 255 ? 255 : g)) / 255.0f);
            out[2] = Clamp01(float(b < 0 ? 0 : (b > 255 ? 255 : b)) / 255.0f);
        }

        void WriteInt(const std::string& path, const char* key, int value)
        {
            char buf[16];
            std::snprintf(buf, sizeof(buf), "%d", value);
            WritePrivateProfileStringA(kIniSection, key, buf, path.c_str());
        }

        void WriteFloat(const std::string& path, const char* key, float value)
        {
            char buf[32];
            std::snprintf(buf, sizeof(buf), "%.3f", value);
            WritePrivateProfileStringA(kIniSection, key, buf, path.c_str());
        }

        void WriteColor(const std::string& path, const char* key, const float rgb[3])
        {
            const int r = int(Clamp01(rgb[0]) * 255.0f + 0.5f);
            const int g = int(Clamp01(rgb[1]) * 255.0f + 0.5f);
            const int b = int(Clamp01(rgb[2]) * 255.0f + 0.5f);
            char buf[16];
            std::snprintf(buf, sizeof(buf), "#%02X%02X%02X", r, g, b);
            WritePrivateProfileStringA(kIniSection, key, buf, path.c_str());
        }

        bool SameStyle(const BeamStyle& a, const BeamStyle& b)
        {
            if (!(a.enabled == b.enabled && a.height == b.height && a.baseOffset == b.baseOffset &&
                  a.beamWidth == b.beamWidth &&
                  a.widthPerYard == b.widthPerYard &&
                  a.color[0] == b.color[0] && a.color[1] == b.color[1] && a.color[2] == b.color[2] &&
                  a.beamAlpha == b.beamAlpha && a.pulse == b.pulse && a.pulseSpeed == b.pulseSpeed &&
                  a.fadeIn == b.fadeIn && a.fadeOut == b.fadeOut &&
                  a.maxDistance == b.maxDistance &&
                  a.showBeam == b.showBeam && a.throughWalls == b.throughWalls &&
                  a.depthPush == b.depthPush && a.depthPushPerYard == b.depthPushPerYard &&
                  a.requireLootable == b.requireLootable && a.lootColor == b.lootColor &&
                  a.serverColor == b.serverColor && a.showSparkles == b.showSparkles &&
                  a.sparkleCount == b.sparkleCount && a.sparkleSize == b.sparkleSize &&
                  a.sparkleAlpha == b.sparkleAlpha && a.sparkleRise == b.sparkleRise &&
                  a.sparkleDrift == b.sparkleDrift && a.sparkleLife == b.sparkleLife &&
                  a.sparkleTwinkle == b.sparkleTwinkle))
                return false;

            for (int t = 0; t < kTierCount; ++t)
            {
                if (a.tiers[t].enabled != b.tiers[t].enabled)
                    return false;
                for (int c = 0; c < 3; ++c)
                    if (a.tiers[t].color[c] != b.tiers[t].color[c])
                        return false;
            }
            return true;
        }
    }

    LootBeam::LootBeam()
    {
        on<&LootBeam::OnUpdate>(ev::Event::OnUpdate);
        on<&LootBeam::OnM2Batch>(ev::Event::OnM2BatchDraw);
        on<&LootBeam::OnWorldSceneEnd>(ev::Event::OnWorldSceneEnd);
        on<&LootBeam::OnWorldEnter>(ev::Event::OnWorldEnter);
        on<&LootBeam::OnWorldLeave>(ev::Event::OnWorldLeave);
        on<&LootBeam::OnDeviceLost>(ev::Event::OnDeviceLost);
    }

    void LootBeam::Log(int level, const char* fmt, ...) const
    {
        if (!api_ || !api_->Log) return;
        va_list ap;
        va_start(ap, fmt);
        char msg[512];
        std::vsnprintf(msg, sizeof(msg), fmt, ap);
        va_end(ap);
        api_->Log(level, "wxl-loot-beam", "%s", msg);
    }

    void LootBeam::LoadConfig(const std::string& iniPath)
    {
        iniPath_     = iniPath;
        configStamp_ = FileStamp(iniPath_);
        LoadConfigNow();

        // A first run has no file to edit, so lay one down from the defaults.
        if (FileStamp(iniPath_) == 0)
        {
            SaveConfig();
            Log(WXL_LOG_INFO, "wrote default config to %s", iniPath_.c_str());
        }

        Log(WXL_LOG_INFO,
            "config: throughWalls=%d maxDistance=%.0f height=%.0f baseOffset=%.2f beamWidth=%.2f "
            "widthPerYard=%.3f beamAlpha=%.2f",
            style_.throughWalls ? 1 : 0, style_.maxDistance, style_.height, style_.baseOffset,
            style_.beamWidth, style_.widthPerYard, style_.beamAlpha);
    }

    void LootBeam::LoadConfigNow()
    {
        BeamStyle s = BeamStyle{};
        s.enabled        = ReadBool(iniPath_,  "Enabled",       s.enabled);
        s.height         = ReadFloat(iniPath_, "Height",        s.height,        0.0f, 40.0f);
        s.beamWidth      = ReadFloat(iniPath_, "BeamWidth",     s.beamWidth,     0.05f, 2.0f);
        s.baseOffset     = ReadFloat(iniPath_, "BaseOffset",    s.baseOffset,    0.0f, 10.0f);
        s.widthPerYard   = ReadFloat(iniPath_, "WidthPerYard",  s.widthPerYard,  0.0f, 0.05f);
        s.beamAlpha      = ReadFloat(iniPath_, "BeamAlpha",     s.beamAlpha,     0.0f, 1.0f);
        s.pulse          = ReadFloat(iniPath_, "Pulse",         s.pulse,         0.0f, 1.0f);
        s.pulseSpeed     = ReadFloat(iniPath_, "PulseSpeed",    s.pulseSpeed,    0.0f, 6.0f);
        s.fadeIn         = ReadFloat(iniPath_, "FadeIn",        s.fadeIn,        0.0f, 5.0f);
        s.fadeOut        = ReadFloat(iniPath_, "FadeOut",       s.fadeOut,       0.0f, 5.0f);
        s.maxDistance    = ReadFloat(iniPath_, "MaxDistance",   s.maxDistance,   0.0f, 400.0f);
        s.showBeam       = ReadBool(iniPath_,  "ShowBeam",      s.showBeam);
        s.throughWalls   = ReadBool(iniPath_,  "ThroughWalls",  s.throughWalls);
        s.depthPush      = ReadFloat(iniPath_, "DepthPush",        s.depthPush,        0.0f, 6.0f);
        s.depthPushPerYard = ReadFloat(iniPath_, "DepthPushPerYard", s.depthPushPerYard, 0.0f, 0.2f);
        s.requireLootable= ReadBool(iniPath_,  "RequireLootable", s.requireLootable);
        s.lootColor      = ReadBool(iniPath_,  "LootColor",       s.lootColor);
        s.serverColor    = ReadBool(iniPath_,  "ServerColor",     s.serverColor);
        ReadColor(iniPath_, "Color", s.color);

        s.showSparkles   = ReadBool(iniPath_,  "Sparkles",       s.showSparkles);
        s.sparkleCount   = ReadInt(iniPath_,   "SparkleCount",   s.sparkleCount,   0, kMaxSparkles);
        s.sparkleSize    = ReadFloat(iniPath_, "SparkleSize",    s.sparkleSize,    0.01f, 0.60f);
        s.sparkleAlpha   = ReadFloat(iniPath_, "SparkleAlpha",   s.sparkleAlpha,   0.0f, 1.0f);
        s.sparkleRise    = ReadFloat(iniPath_, "SparkleRise",    s.sparkleRise,    0.0f, 3.0f);
        s.sparkleDrift   = ReadFloat(iniPath_, "SparkleDrift",   s.sparkleDrift,   0.0f, 2.0f);
        s.sparkleLife    = ReadFloat(iniPath_, "SparkleLife",    s.sparkleLife,    0.2f, 6.0f);
        s.sparkleTwinkle = ReadFloat(iniPath_, "SparkleTwinkle", s.sparkleTwinkle, 0.0f, 12.0f);

        // Per-tier look. A file that predates the tier keys simply keeps the tier defaults above.
        for (int t = 0; t < kTierCount; ++t)
        {
            const std::string stem    = std::string("Tier.") + kTierDefs[t].stem;
            const std::string enabled = stem + ".Enabled";
            const std::string color   = stem + ".Color";
            s.tiers[t].enabled = ReadBool(iniPath_, enabled.c_str(), s.tiers[t].enabled);
            ReadColor(iniPath_, color.c_str(), s.tiers[t].color);
        }

        // A file written by an older build carries a distance cap and the wrong idea of depth, so a
        // few defaults are adopted for exactly those keys and persisted; an existing install then does
        // not have to be edited by hand.
        const int version = GetPrivateProfileIntA(kIniSection, "ConfigVersion", 0, iniPath_.c_str());
        const bool migrated = version < kConfigVersion;
        if (migrated)
        {
            if (version < 2)
            {
                s.maxDistance = 0.0f;
                if (s.beamWidth < 0.7f) s.beamWidth = 0.7f;
                if (s.beamAlpha < 0.6f) s.beamAlpha = 0.6f;
            }
            // Version 3 marks only still-lootable corpses, so a looted body's beam goes away; older
            // files defaulted to marking every corpse.
            if (version < 3) s.requireLootable = true;
            // Version 4 made the world hide the beacon again; version 5 reversed that. The default is
            // now world-occluded again (ThroughWalls=0), so an older file that never carried the key
            // adopts occlusion; a file that states the key keeps whatever the panel left it at.
            // Version 7 retunes the shipped look: a taller, narrower beam and a denser, tighter field
            // of smaller, faster sparkles, with the ground pool removed. An older file adopts the new
            // defaults; a file written at version 7 or later keeps whatever the panel left it at.
            if (version < 7)
            {
                s.height         = 20.0f;
                s.beamWidth      = 0.50f;
                s.sparkleCount   = 24;
                s.sparkleSize    = 0.04f;
                s.sparkleAlpha   = 0.90f;
                s.sparkleRise    = 1.00f;
                s.sparkleDrift   = 0.05f;
                s.sparkleLife    = 2.40f;
                s.sparkleTwinkle = 6.00f;
            }
            // Version 8 retunes the shipped palette and brightness: currency, poor and common go
            // pure black, rare/epic take their new custom tints, and the beam starts at 0.75 opacity.
            // An older file adopts the new defaults; a file written at version 8 or later keeps
            // whatever the panel left it at.
            if (version < 8)
            {
                s.tiers[kTierCurrency].color[0] = 0.00f;
                s.tiers[kTierCurrency].color[1] = 0.00f;
                s.tiers[kTierCurrency].color[2] = 0.00f;
                s.tiers[kTierPoor].color[0]   = 0.00f;
                s.tiers[kTierPoor].color[1]   = 0.00f;
                s.tiers[kTierPoor].color[2]   = 0.00f;
                s.tiers[kTierCommon].color[0] = 0.00f;
                s.tiers[kTierCommon].color[1] = 0.00f;
                s.tiers[kTierCommon].color[2] = 0.00f;
                s.tiers[kTierRare].color[0]   = 0.00f;
                s.tiers[kTierRare].color[1]   = 0.19607843f;
                s.tiers[kTierRare].color[2]   = 1.00f;
                s.tiers[kTierEpic].color[0]   = 0.58823529f;
                s.tiers[kTierEpic].color[1]   = 0.00f;
                s.tiers[kTierEpic].color[2]   = 1.00f;
                s.beamAlpha = 0.75f;
            }
            // Version 9 restores the world-space depth pull that keeps the beacon ahead of the coarser
            // terrain LOD at range; it was briefly replaced by a D3D9 depth bias, which DXVK scales out
            // of all proportion, and then removed. An older file adopts the defaults.
            if (version < 9)
            {
                s.depthPush        = 1.50f;
                s.depthPushPerYard = 0.02f;
            }
        }

        style_ = s;
        saved_ = s;

        if (migrated)
        {
            Log(WXL_LOG_INFO, "migrating config from version %d to %d", version, kConfigVersion);
            SaveConfig();
        }
    }

    void LootBeam::ReloadConfigIfChanged()
    {
        if (iniPath_.empty())
            return;

        // The stat is not free; a live edit does not need frame-accuracy.
        static DWORD lastCheck = 0;
        const DWORD now = GetTickCount();
        if (now - lastCheck < 1000u)
            return;
        lastCheck = now;

        const unsigned long long stamp = FileStamp(iniPath_);
        if (stamp == configStamp_)
            return;
        configStamp_ = stamp;
        LoadConfigNow();
        Log(WXL_LOG_INFO, "config reloaded from %s", iniPath_.c_str());
    }

    bool LootBeam::SaveConfig()
    {
        if (iniPath_.empty())
            return false;

        WriteInt(iniPath_,   "Enabled",         style_.enabled ? 1 : 0);
        WriteFloat(iniPath_, "Height",          style_.height);
        WriteFloat(iniPath_, "BeamWidth",       style_.beamWidth);
        WriteFloat(iniPath_, "BaseOffset",      style_.baseOffset);
        WriteFloat(iniPath_, "WidthPerYard",    style_.widthPerYard);
        WriteFloat(iniPath_, "BeamAlpha",       style_.beamAlpha);
        WriteFloat(iniPath_, "Pulse",           style_.pulse);
        WriteFloat(iniPath_, "PulseSpeed",      style_.pulseSpeed);
        WriteFloat(iniPath_, "FadeIn",          style_.fadeIn);
        WriteFloat(iniPath_, "FadeOut",         style_.fadeOut);
        WriteFloat(iniPath_, "MaxDistance",     style_.maxDistance);
        WriteInt(iniPath_,   "ShowBeam",        style_.showBeam ? 1 : 0);
        WriteInt(iniPath_,   "ThroughWalls",    style_.throughWalls ? 1 : 0);
        WriteFloat(iniPath_, "DepthPush",        style_.depthPush);
        WriteFloat(iniPath_, "DepthPushPerYard", style_.depthPushPerYard);
        WriteInt(iniPath_,   "RequireLootable", style_.requireLootable ? 1 : 0);
        WriteInt(iniPath_,   "LootColor",       style_.lootColor ? 1 : 0);
        WriteInt(iniPath_,   "ServerColor",     style_.serverColor ? 1 : 0);
        WriteColor(iniPath_, "Color",           style_.color);

        WriteInt(iniPath_,   "Sparkles",        style_.showSparkles ? 1 : 0);
        WriteInt(iniPath_,   "SparkleCount",    style_.sparkleCount);
        WriteFloat(iniPath_, "SparkleSize",     style_.sparkleSize);
        WriteFloat(iniPath_, "SparkleAlpha",    style_.sparkleAlpha);
        WriteFloat(iniPath_, "SparkleRise",     style_.sparkleRise);
        WriteFloat(iniPath_, "SparkleDrift",    style_.sparkleDrift);
        WriteFloat(iniPath_, "SparkleLife",     style_.sparkleLife);
        WriteFloat(iniPath_, "SparkleTwinkle",  style_.sparkleTwinkle);

        for (int t = 0; t < kTierCount; ++t)
        {
            const std::string stem    = std::string("Tier.") + kTierDefs[t].stem;
            const std::string enabled = stem + ".Enabled";
            const std::string color   = stem + ".Color";
            WriteInt(iniPath_,   enabled.c_str(), style_.tiers[t].enabled ? 1 : 0);
            WriteColor(iniPath_, color.c_str(),   style_.tiers[t].color);
        }

        // The ground glow was removed from the module; drop its keys so an old file does not carry
        // dead settings. A NULL string removes the key.
        WritePrivateProfileStringA(kIniSection, "GroundRadius", nullptr, iniPath_.c_str());
        WritePrivateProfileStringA(kIniSection, "GroundAlpha", nullptr, iniPath_.c_str());
        WritePrivateProfileStringA(kIniSection, "ShowGround", nullptr, iniPath_.c_str());

        WriteInt(iniPath_,   "ConfigVersion",   kConfigVersion);

        // The write bumps the file stamp; adopt it so the self-write is not mistaken for an external
        // edit (which would overwrite a panel tweak made right after Save).
        configStamp_ = FileStamp(iniPath_);
        saved_       = style_;
        Log(WXL_LOG_INFO, "settings saved to %s", iniPath_.c_str());
        return true;
    }

    void LootBeam::RevertConfig()
    {
        LoadConfigNow();
        Log(WXL_LOG_INFO, "settings reverted to %s", iniPath_.c_str());
    }

    bool LootBeam::HasUnsavedChanges() const
    {
        return !SameStyle(style_, saved_);
    }

    void LootBeam::DrawPanel(const WXL_Api& api)
    {
        if (!api.UiCheckbox || !api.UiSliderFloat || !api.UiSeparator || !api.UiText ||
            !api.UiColorEdit || !api.UiButton || !api.UiSameLine || !api.UiCollapsingHeader)
            return;

        int enabled = style_.enabled ? 1 : 0;
        if (api.UiCheckbox("Enable", &enabled)) style_.enabled = enabled != 0;

        api.UiText(inWorld_ ? "status: scanning for lootable bodies"
                            : "status: waiting for a world");

        if (api.UiCollapsingHeader("Beacon"))
        {
            api.UiSliderFloat("Height (yd)", &style_.height, 0.0f, 40.0f);
            api.UiSliderFloat("Beam width (yd)", &style_.beamWidth, 0.05f, 2.0f);
            api.UiSliderFloat("Base offset (yd)", &style_.baseOffset, 0.0f, 5.0f);
            api.UiSliderFloat("Min width / yd", &style_.widthPerYard, 0.0f, 0.05f);
            api.UiSliderFloat("Beam alpha", &style_.beamAlpha, 0.0f, 1.0f);

            float rgba[4] = { style_.color[0], style_.color[1], style_.color[2], 1.0f };
            if (api.UiColorEdit("Colour", rgba))
            {
                style_.color[0] = rgba[0];
                style_.color[1] = rgba[1];
                style_.color[2] = rgba[2];
            }
        }

        if (api.UiCollapsingHeader("Sparkles"))
        {
            int sparkles = style_.showSparkles ? 1 : 0;
            if (api.UiCheckbox("Show sparkles", &sparkles)) style_.showSparkles = sparkles != 0;

            // The SDK panel offers only float sliders, so the integer count is edited as one and
            // rounded on the way back.
            float count = float(style_.sparkleCount);
            if (api.UiSliderFloat("Count", &count, 0.0f, float(kMaxSparkles)))
                style_.sparkleCount = int(count + 0.5f);

            api.UiSliderFloat("Size (yd)", &style_.sparkleSize, 0.01f, 0.6f);
            api.UiSliderFloat("Alpha", &style_.sparkleAlpha, 0.0f, 1.0f);
            api.UiSliderFloat("Rise (yd/s)", &style_.sparkleRise, 0.0f, 3.0f);
            api.UiSliderFloat("Drift (yd/s)", &style_.sparkleDrift, 0.0f, 2.0f);
            api.UiSliderFloat("Life (s)", &style_.sparkleLife, 0.2f, 6.0f);
            api.UiSliderFloat("Twinkle", &style_.sparkleTwinkle, 0.0f, 12.0f);
        }

        if (api.UiCollapsingHeader("Behaviour"))
        {
            api.UiSliderFloat("Pulse", &style_.pulse, 0.0f, 1.0f);
            api.UiSliderFloat("Pulse speed", &style_.pulseSpeed, 0.0f, 6.0f);
            api.UiSliderFloat("Fade in (s)", &style_.fadeIn, 0.0f, 5.0f);
            api.UiSliderFloat("Fade out (s)", &style_.fadeOut, 0.0f, 5.0f);
            api.UiSliderFloat("Max distance (yd)", &style_.maxDistance, 0.0f, 400.0f);

            int beam = style_.showBeam ? 1 : 0;
            if (api.UiCheckbox("Beam", &beam)) style_.showBeam = beam != 0;
            int walls = style_.throughWalls ? 1 : 0;
            if (api.UiCheckbox("Through walls", &walls)) style_.throughWalls = walls != 0;
            if (!style_.throughWalls)
            {
                api.UiSliderFloat("Depth push (yd)", &style_.depthPush, 0.0f, 4.0f);
                api.UiSliderFloat("Depth push / yd", &style_.depthPushPerYard, 0.0f, 0.1f);
            }
            int lootable = style_.requireLootable ? 1 : 0;
            if (api.UiCheckbox("Only lootable corpses", &lootable)) style_.requireLootable = lootable != 0;
            int lootColor = style_.lootColor ? 1 : 0;
            if (api.UiCheckbox("Colour by loot rarity", &lootColor)) style_.lootColor = lootColor != 0;
            int serverColor = style_.serverColor ? 1 : 0;
            if (api.UiCheckbox("Use server loot colour", &serverColor)) style_.serverColor = serverColor != 0;
        }

        // One row per tier: a switch to draw it at all, and the colour it is drawn in. A tier switched
        // off leaves corpses that fall into it unmarked, so unwanted drops can be filtered out.
        if (api.UiCollapsingHeader("Gear tiers"))
        {
            for (int t = 0; t < kTierCount; ++t)
            {
                int on = style_.tiers[t].enabled ? 1 : 0;
                if (api.UiCheckbox(kTierDefs[t].label, &on))
                    style_.tiers[t].enabled = on != 0;

                api.UiSameLine();
                char id[32];
                std::snprintf(id, sizeof(id), "##tier%d", t);
                float rgba[4] = { style_.tiers[t].color[0], style_.tiers[t].color[1],
                                  style_.tiers[t].color[2], 1.0f };
                if (api.UiColorEdit(id, rgba))
                {
                    style_.tiers[t].color[0] = rgba[0];
                    style_.tiers[t].color[1] = rgba[1];
                    style_.tiers[t].color[2] = rgba[2];
                }
            }
        }

        api.UiSeparator();
        if (api.UiButton("Save")) SaveConfig();
        api.UiSameLine();
        if (api.UiButton("Revert")) RevertConfig();
        api.UiText(HasUnsavedChanges() ? "Unsaved changes" : "Matches wxl-loot-beam.ini");
    }

    int LootBeam::ScanUnits()
    {
        // Everything tracked starts unseen; a corpse that qualifies this frame marks itself seen, so
        // what is left unseen afterward is a body that was looted or despawned and must fade out.
        for (int i = 0; i < trackedCount_; ++i)
            beacons_[i].seen = false;

        beaconCount_ = 0;

        // A zero active-player GUID means no live session, and the object walk dereferences the
        // thread-local object manager without checking -- do not enter it there.
        if (world::ActivePlayerGuid() == 0)
            return 0;

        float camera[3];
        cam::GetPosition(camera);
        const float maxD2 = style_.maxDistance > 0.0f ? style_.maxDistance * style_.maxDistance : 0.0f;

        int  enumerated = 0;
        bool dumped     = false;

        // The walk reads the resident-object list; it is main-thread only, which the logic tick is.
        world::ForEachObject(world::kTypeMaskUnit, [&](unsigned long long guid, void* obj) -> bool {
            ++enumerated;
            if (!dumped)
            {
                uint32_t h = 1;
                if (UnitHealth(obj, h) && h == 0)
                {
                    dumped = true;
                    DumpUnit(obj, guid);
                }
            }
            if (!IsLootableCorpse(obj, style_)) return true;

            // Torment patch (PINNED.md): the tier is the server's alone, this viewer's own drops on the
            // corpse (docs/contracts/loot-beam-tier.md), read every frame; no tier, no beacon.
            int serverTier = -1;
            if (style_.lootColor && style_.serverColor) UnitLootBeamTier(obj, serverTier);
            if (serverTier < 0) return true;

            float p[3];
            world::UnitPosition(obj, p);

            if (maxD2 > 0.0f)
            {
                const float dx = p[0] - camera[0];
                const float dy = p[1] - camera[1];
                const float dz = p[2] - camera[2];
                if (dx * dx + dy * dy + dz * dz > maxD2) return true;
            }

            // Match on GUID so a corpse keeps its fade level while it is tracked; a newly seen one
            // enters at zero and eases up.
            Beacon* b = nullptr;
            for (int i = 0; i < trackedCount_; ++i)
            {
                if (beacons_[i].guid == guid) { b = &beacons_[i]; break; }
            }
            if (!b)
            {
                if (trackedCount_ >= kMaxBeacons) return true; // table full; let it go this pass
                b = &beacons_[trackedCount_++];
                b->guid = guid;
                b->fade = 0.0f;
                b->tier = -1;
                SeedSparkles(*b);
            }
            b->pos[0] = p[0];
            b->pos[1] = p[1];
            b->pos[2] = p[2];
            b->seen   = true;

            b->tier = serverTier; // Torment patch: follows the server down as well as up
            if (style_.lootColor && style_.serverColor && !loggedServerHint_ && serverTier >= 0)
            {
                loggedServerHint_ = true;
                Log(WXL_LOG_INFO, "diag: server loot hint guid=%llX tier=%d", guid, serverTier);
            }
            return true;
        });

        return enumerated;
    }

    // Reads the loot the client currently holds and, when it belongs to a tracked corpse, records the
    // GearTier of its rarest item on that beacon. The client keeps one loot at a time and only learns
    // a corpse's contents when loot is requested for it, so the tier is adopted the moment the loot
    // opens and kept on the tracked beacon afterwards. A tier is only ever raised, so the rarest item
    // seen -- from the server hint above or the loot the client learns here -- always owns the colour.
    void LootBeam::ScanLoot()
    {
        if (!style_.lootColor)
        {
            lootGuid_ = 0;
            lootTier_ = -1;
            return;
        }

        unsigned long long guid = 0;
        if (!ReadU64(kLootSourceGuid, guid))
        {
            lootGuid_ = 0;
            lootTier_ = -1;
            return;
        }

        if (guid != lootGuid_)
        {
            lootGuid_ = guid;
            lootTier_ = guid != 0 ? ReadLootTier() : -1;
            if (guid != 0)
                Log(WXL_LOG_INFO, "loot: source=%llX bestTier=%d", guid, lootTier_);
        }

        if (lootTier_ < 0) return;
        for (int i = 0; i < trackedCount_; ++i)
        {
            if (beacons_[i].guid == lootGuid_ && lootTier_ > beacons_[i].tier)
                beacons_[i].tier = lootTier_;
        }
    }

    // The GearTier of the rarest item in the currently open loot, asked of the client itself
    // (GetNumLootItems / GetLootSlotInfo) so no item-cache offset is reimplemented here. Returns -1
    // when there is no loot or the script state is not up; a slot whose fourth return is not a number
    // contributes nothing.
    int LootBeam::ReadLootTier()
    {
        void* state = script::Context();
        if (!state) return -1;

        const int base = script::StackTop(state);
        int       best = -1;

        script::PushGlobal(state, "GetNumLootItems");
        if (script::PCall(state, 0, 1, 0) == 0)
        {
            int count = int(script::ToNumber(state, -1));
            script::SetTop(state, base);
            if (count < 0) count = 0;
            if (count > kMaxLootSlots) count = kMaxLootSlots;

            for (int slot = 1; slot <= count; ++slot)
            {
                script::PushGlobal(state, "GetLootSlotInfo");
                script::PushNumber(state, double(slot));
                // texture, item, quantity, quality, locked
                if (script::PCall(state, 1, 5, 0) == 0)
                {
                    // The quality is the rarest thing the slot can tell us about; keep the highest
                    // over every slot. A slot that answers nil (an item the client has not cached)
                    // contributes nothing rather than counting as a grey.
                    if (script::IsNumber(state, -2))
                    {
                        const int quality = int(script::ToNumber(state, -2));
                        if (quality > best) best = quality;
                    }
                }
                script::SetTop(state, base);
            }
        }
        else
        {
            script::SetTop(state, base);
        }

        return best < 0 ? -1 : best + kTierPoor;
    }

    // Advances every tracked beacon's fade toward its target -- full when it was seen this frame, zero
    // when it was not -- and forgets the ones that have finished fading out.
    void LootBeam::UpdateFade(float dt)
    {
        const float inRate  = style_.fadeIn  > 0.001f ? 1.0f / style_.fadeIn  : 1.0e9f;
        const float outRate = style_.fadeOut > 0.001f ? 1.0f / style_.fadeOut : 1.0e9f;

        int kept = 0;
        for (int i = 0; i < trackedCount_; ++i)
        {
            Beacon b = beacons_[i];
            if (b.seen)
            {
                b.fade += inRate * dt;
                if (b.fade > 1.0f) b.fade = 1.0f;
            }
            else
            {
                b.fade -= outRate * dt;
                if (b.fade <= 0.0f) continue; // finished fading; forget it
            }
            if (b.fade > 0.001f) AdvanceSparkles(b, dt);
            beacons_[kept++] = b;
        }
        trackedCount_ = kept;

        beaconCount_ = 0;
        for (int i = 0; i < trackedCount_; ++i)
        {
            if (beacons_[i].fade > 0.001f) ++beaconCount_;
        }
    }

    // Reads a window of the update-field block around where health is expected and writes it to the
    // log, once per session. The field that reads 0 on a corpse is the health field; if none of them
    // do, the descriptor layout assumption is wrong and the offsets in UnitFields.hpp need revising.
    void LootBeam::DumpUnit(void* unit, unsigned long long guid)
    {
        uintptr_t descriptors = 0;
        if (!ReadPtr(reinterpret_cast<uintptr_t>(unit) + kObjectDescriptorField, descriptors) ||
            !ValidPointer(descriptors, 0x100))
        {
            Log(WXL_LOG_INFO, "diag: first unit guid=%llX has no readable descriptor", guid);
            return;
        }

        char window[320] = {};
        int  n = 0;
        // Health lives at 0x60; the strict path's dynamic flags at 0x13C. Dump both neighbourhoods so
        // a future client build can be checked at a glance.
        for (size_t off = 0x58; off <= 0x78 && n < int(sizeof(window)) - 24; off += 4)
        {
            uint32_t v = 0;
            if (!ReadU32(descriptors + off, v))
                v = 0xDEADBEEFu;
            n += std::snprintf(window + n, sizeof(window) - n, " %02X=%u", unsigned(off), v);
        }
        Log(WXL_LOG_INFO, "diag: first unit guid=%llX desc=%p%s", guid, (void*)descriptors, window);

        n = 0;
        for (size_t off = 0x12C; off <= 0x140 && n < int(sizeof(window)) - 24; off += 4)
        {
            uint32_t v = 0;
            if (!ReadU32(descriptors + off, v))
                v = 0xDEADBEEFu;
            n += std::snprintf(window + n, sizeof(window) - n, " %02X=%u", unsigned(off), v);
        }
        Log(WXL_LOG_INFO, "diag: first unit guid=%llX dynflags%s", guid, window);
    }

    namespace
    {
        // Soft falloff from a centre value of 1 at x = 0 to 0 at x = 1, with a flat top and a gentle
        // shoulder -- the difference between a lit volume and a hard-edged quad.
        float SoftEdge(float x)
        {
            const float a = x < 0.0f ? 0.0f : (x > 1.0f ? 1.0f : x);
            return 1.0f - a * a * (3.0f - 2.0f * a);
        }

        // The shaft's vertical profile: transparent where it leaves the body, rising to a soft peak a
        // short way up, then easing to nothing at the top. A profile that were merely brightest at the
        // bottom would read as a column with a cut-off base instead of light gathering in the air.
        float BeamVertical(float t)
        {
            constexpr float kRise = 0.22f;
            if (t < kRise) return 1.0f - SoftEdge(t / kRise);
            return SoftEdge((t - kRise) / (1.0f - kRise));
        }

        // The tint, pulled toward white by `whiten`: the middle of a light shaft is hotter and whiter
        // than its cooler, more coloured edges.
        gfx::Color PackTint(float alpha, const float rgb[3], float whiten)
        {
            const float c[3] = {
                rgb[0] + (1.0f - rgb[0]) * whiten,
                rgb[1] + (1.0f - rgb[1]) * whiten,
                rgb[2] + (1.0f - rgb[2]) * whiten,
            };
            return Pack(alpha, c);
        }

        // The largest beam grid. The actual grid is chosen per beam from how many pixels it covers on
        // screen (see QueueBeamColumn); these only cap it. A shaft is a thin thread -- four columns
        // across hold its falloff -- but a tall one, so the vertical count is the one worth spending.
        constexpr int kBeamMaxRows = 64;
        constexpr int kBeamMaxCols = 4;

        // Per-frame cap on the costly screen-space model picks. Terrain traces are cheap and are not
        // capped; this only stops a camp full of corpses from turning the model half of the test into
        // hundreds of cursor searches in one frame. When it runs out the terrain trace still carries the
        // shape, so the beam just loses its finer model silhouette for the rest of that frame.
        constexpr int kModelPickBudget = 1200;
        int g_modelPicksLeft = kModelPickBudget;

        // True when the shaft's bounding sphere may cross the view frustum. The planes come from the
        // engine's own combined view-projection (cam::GetViewProj), so a beacon this rejects would have
        // drawn no pixel; a conservative sphere test never drops one that is even partly visible. It is
        // the first line of defence when many corpses are around: a beacon behind the camera or off the
        // edge is skipped before its large additive quad reaches the rasteriser.
        bool BeamInView(const float pos[3], const BeamStyle& style)
        {
            const float* m = cam::GetViewProj();
            if (!m) return true; // no matrices yet; do not cull what cannot be tested

            const float lo = style.baseOffset;
            const float hi = fmaxf(style.height, lo + 0.1f);
            const float cx = pos[0];
            const float cy = pos[1];
            const float cz = pos[2] + 0.5f * (lo + hi);
            const float radius = 0.5f * (hi - lo) + style.beamWidth + 0.5f;

            // Row-vector clip space: clip = p * m. Each frustum plane is a column combination of m and
            // a point is inside it when the plane value is >= 0; the sphere is outside only when even
            // its nearest point is negative.
            const float planes[5][4] = {
                { m[0] + m[3], m[4] + m[7], m[8] + m[11], m[12] + m[15] }, // left
                { m[3] - m[0], m[7] - m[4], m[11] - m[8], m[15] - m[12] }, // right
                { m[1] + m[3], m[5] + m[7], m[9] + m[11], m[13] + m[15] }, // bottom
                { m[3] - m[1], m[7] - m[5], m[11] - m[9], m[15] - m[13] }, // top
                { m[2],        m[6],        m[10],        m[14]        }, // near (clip z >= 0)
            };

            for (const auto& p : planes)
            {
                const float dist = cx * p[0] + cy * p[1] + cz * p[2] + p[3];
                const float len  = sqrtf(p[0] * p[0] + p[1] * p[1] + p[2] * p[2]);
                if (dist + radius * len < 0.0f)
                    return false;
            }
            return true;
        }

        // True when a hit is cover rather than the ground the beam stands on: the eye->point segment
        // must reach the hit with more than `clearance` yards still to run before the point.
        bool HitIsCover(const float eye[3], const float to[3], const world::WorldHit& hit, float clearance)
        {
            const float hx = hit.pos.x - eye[0], hy = hit.pos.y - eye[1], hz = hit.pos.z - eye[2];
            const float hlen = sqrtf(hx * hx + hy * hy + hz * hz);
            const float dx = to[0] - eye[0], dy = to[1] - eye[1], dz = to[2] - eye[2];
            const float len = sqrtf(dx * dx + dy * dy + dz * dz);
            return len - hlen > clearance;
        }

        // The live device viewport in pixels, or false when there is no device yet.
        bool ViewportSize(float& w, float& h)
        {
            gx::Device9 dev(gx::RawDevice());
            if (!dev) return false;
            struct Viewport { unsigned x, y, width, height; float minZ, maxZ; };
            Viewport vp = {};
            if (dev.GetViewport(&vp) < 0 || vp.width == 0 || vp.height == 0) return false;
            w = float(vp.width); h = float(vp.height);
            return true;
        }

        // Projects a world point to a device pixel and runs the engine's cursor pick through it. The
        // pick is the only ray in the SDK that tests model geometry; the world intersect behind
        // TraceLine tests terrain and WMO only, so a tree or a rock is invisible to it. False when the
        // device/camera is not ready, the point is behind the eye, or the ray misses everything.
        bool PickProjected(const float eye[3], const float to[3], world::WorldHit& hit)
        {
            float vpW = 0.0f, vpH = 0.0f;
            if (!ViewportSize(vpW, vpH)) return false;

            const float* view = cam::GetView();
            const float* proj = cam::GetProjection();
            const float px = to[0] - eye[0], py = to[1] - eye[1], pz = to[2] - eye[2];
            const float vx = px * view[0] + py * view[4] + pz * view[8] + view[12];
            const float vy = px * view[1] + py * view[5] + pz * view[9] + view[13];
            const float vz = px * view[2] + py * view[6] + pz * view[10] + view[14];
            const float cw = vx * proj[3] + vy * proj[7] + vz * proj[11] + proj[15];
            if (cw <= 1.0e-3f) return false; // behind the eye: no pixel to shoot through

            const float cx = vx * proj[0] + vy * proj[4] + vz * proj[8] + proj[12];
            const float cy = vx * proj[1] + vy * proj[5] + vz * proj[9] + proj[13];
            const float ddcX = (0.5f * cx / cw + 0.5f) * vpW;
            const float ddcY = (0.5f - 0.5f * cy / cw) * vpH;
            return world::Pick(ddcX, ddcY, hit) != 0;
        }

        // An M2/doodad (a tree, a rock, a banner, another body) standing between the eye and a point.
        // Only a model hit is taken: terrain and WMO are the trace below, and re-taking them here would
        // count the ground under the beam a second time.
        bool ModelBlocked(const float eye[3], const float to[3], float clearance)
        {
            if (g_modelPicksLeft <= 0) return false;
            --g_modelPicksLeft;
            world::WorldHit hit;
            if (!PickProjected(eye, to, hit) || hit.type != 2) return false;
            return HitIsCover(eye, to, hit, clearance);
        }

        // True when terrain or WMO stands between the eye and a point, with at least `clearance` yards
        // of it. A beam stands on the ground, so a trace to it almost always meets that ground right at
        // the beam itself -- a bare hit is not occlusion. Only a hit well short of the point is.
        bool LineBlocked(const float eye[3], const float to[3], float clearance)
        {
            world::WorldHit hit;
            return world::TraceLine(eye, to, hit) && HitIsCover(eye, to, hit, clearance);
        }

        // The lowest t in [0,1] the eye can see up a beam column, found by bisection on the shape cover
        // usually has: hidden low, clear high, like a hill or a trunk. 2 means the whole column is
        // hidden. A clear column costs a single sample; a blocked one about seven, whatever the row
        // count -- which is what keeps the ray count at tens per beam instead of hundreds.
        template <class BlockedFn>
        float ColumnCut(BlockedFn blocked)
        {
            if (!blocked(0.0f)) return 0.0f;
            if (blocked(1.0f))  return 2.0f;
            float lo = 0.0f, hi = 1.0f;
            for (int i = 0; i < 5; ++i)
            {
                const float mid = 0.5f * (lo + hi);
                if (blocked(mid)) lo = mid; else hi = mid;
            }
            return hi;
        }

        // The shaft: one camera-facing billboard, gridded so a colour can sit on every vertex. The
        // horizontal falloff keeps the core bright and the edges transparent; the vertical one is
        // transparent at the floating base, peaks just above it, then eases to nothing at the top.
        // Interpolated across the grid, a few quads read as a soft, hot-cored volume. The grid is
        // reduced with distance -- a far shaft is a few pixels tall, so its falloff would be lost on
        // the screen anyway -- which keeps the near look unchanged while cutting the vertex work.
        void QueueBeamColumn(const float pos[3], float bodyZ, const BeamStyle& style, float alphaScale,
                             const float rgb[3], bool occlude)
        {
            float camera[3];
            cam::GetPosition(camera);
            const float dx = camera[0] - pos[0];
            const float dy = camera[1] - pos[1];
            const float dz = camera[2] - pos[2];
            const float len = sqrtf(dx * dx + dy * dy);
            const float dist = sqrtf(dx * dx + dy * dy + dz * dz);

            // Billboard across the view direction: the only vertical plane the camera sees face-on.
            float fx = 1.0f, fy = 0.0f;
            if (len > 1e-3f) { fx = dx / len; fy = dy / len; }
            const float sx = -fy, sy = fx;

            // A fixed-width beam becomes a sub-pixel thread at range; grow a floor under the half-width
            // so a distant corpse still shows a column. 0 leaves the taper alone.
            const float minHalfWidth = style.widthPerYard > 0.0f ? style.widthPerYard * dist : 0.0f;

            // minBaseZ clips the foot of the shaft up to the cover it stands behind, so the beam is
            // always there but the buried part never draws through the hill or wall in front of it.
            const float baseZ = bodyZ + style.baseOffset;
            const float topZ  = bodyZ + fmaxf(style.height, style.baseOffset + 0.1f);
            if (baseZ >= topZ - 0.05f) return; // cover swallows the whole shaft
            const float spanZ = topZ - baseZ;

            // The grid follows the shaft's own screen size: a beam that fills the frame is gridded
            // finely, a distant thread coarsely, so the vertex (and ray) work lands where it can be
            // seen. 5 px per cell is below what the eye resolves on a soft additive edge.
            int rows = kBeamMaxRows;
            int cols = kBeamMaxCols;
            float vpW = 0.0f, vpH = 0.0f;
            if (ViewportSize(vpW, vpH) && dist > 0.5f)
            {
                const float* proj = cam::GetProjection();
                const float invDist = 1.0f / dist;
                const float pxH = fabsf(proj[5]) * spanZ * invDist * 0.5f * vpH;
                const float pxW = fabsf(proj[0]) * (2.0f * style.beamWidth) * invDist * 0.5f * vpW;
                rows = int(pxH / 5.0f) + 1;
                cols = int(pxW / 5.0f) + 1;
                if (rows < 4)            rows = 4;
                if (rows > kBeamMaxRows) rows = kBeamMaxRows;
                if (cols < 2)            cols = 2;
                if (cols > kBeamMaxCols) cols = kBeamMaxCols;
            }
            else if (dist > 150.0f) { rows = 5;  cols = 2; }
            else if (dist > 80.0f)  { rows = 12; cols = 4; }

            float      xs[kBeamMaxRows + 1][kBeamMaxCols + 1];
            float      ys[kBeamMaxRows + 1][kBeamMaxCols + 1];
            float      zs[kBeamMaxRows + 1];
            gfx::Color cs[kBeamMaxRows + 1][kBeamMaxCols + 1];

            // One line-of-sight bisection per column, then every vertex in that column compares its
            // height to the cut. Terrain and model share the cut: both hide the beam from below, so the
            // higher of the two wins. The model pick is the costly half, so it is asked only while the
            // beam is close enough for its silhouette to span real pixels.
            const bool modelTest = occlude && dist < 250.0f;
            float cut[kBeamMaxCols + 1];
            for (int c = 0; c <= cols; ++c)
            {
                if (!occlude) { cut[c] = 0.0f; continue; }
                const float u = -1.0f + 2.0f * float(c) / float(cols);
                cut[c] = ColumnCut([&](float t) {
                    const float w = fmaxf(style.beamWidth * (1.0f - 0.55f * t), minHalfWidth);
                    const float p[3] = { pos[0] + sx * (w * u),
                                         pos[1] + sy * (w * u), baseZ + spanZ * t };
                    if (LineBlocked(camera, p, 2.0f)) return true;
                    return modelTest && ModelBlocked(camera, p, 2.0f);
                });
            }

            for (int r = 0; r <= rows; ++r)
            {
                const float t = float(r) / float(rows);
                const float w = fmaxf(style.beamWidth * (1.0f - 0.55f * t), minHalfWidth);
                const float v = BeamVertical(t);
                zs[r] = baseZ + spanZ * t;

                for (int c = 0; c <= cols; ++c)
                {
                    const float u = -1.0f + 2.0f * float(c) / float(cols);
                    const float h = SoftEdge(fabsf(u));
                    xs[r][c] = pos[0] + sx * (w * u);
                    ys[r][c] = pos[1] + sy * (w * u);

                    // 0 below the column's cut, 1 above it; Gouraud then fades across one cell.
                    const float vis = t >= cut[c] ? 1.0f : 0.0f;
                    cs[r][c] = PackTint(style.beamAlpha * v * h * vis * alphaScale, rgb,
                                        0.45f * h * (1.0f - 0.3f * t));
                }
            }

            for (int r = 0; r < rows; ++r)
            {
                for (int c = 0; c < cols; ++c)
                {
                    const float p00[3] = { xs[r][c],         ys[r][c],         zs[r] };
                    const float p10[3] = { xs[r][c + 1],     ys[r][c + 1],     zs[r] };
                    const float p11[3] = { xs[r + 1][c + 1], ys[r + 1][c + 1], zs[r + 1] };
                    const float p01[3] = { xs[r + 1][c],     ys[r + 1][c],     zs[r + 1] };
                    beacon_gfx::Triangle(p00, p10, p11, cs[r][c], cs[r][c + 1], cs[r + 1][c + 1]);
                    beacon_gfx::Triangle(p00, p11, p01, cs[r][c], cs[r + 1][c + 1], cs[r + 1][c]);
                }
            }
        }

        // Drifting, twinkling motes inside the beam. Each is a small camera-facing disc of light -- a
        // hot core easing out to a transparent rim through a shoulder ring -- so additive blending
        // turns it into a soft ball that glows at its centre rather than a flat square. Its brightness
        // rides the mote's own flicker phase and life envelope, and it swells a touch as it brightens.
        void QueueSparkles(const float pos[3], const Sparkle* sparkles, int count,
                           const BeamStyle& style, float alphaScale, const float rgb[3], bool occlude)
        {
            if (count <= 0)
                return;

            float camera[3];
            cam::GetPosition(camera);

            constexpr int   kSegments = 8;
            constexpr float kRing1 = 0.45f, kRing2 = 1.0f; // radii, as fractions of the mote size
            constexpr float kShoulder = 0.58f;             // brightness of the middle ring

            for (int i = 0; i < count; ++i)
            {
                const Sparkle& sp = sparkles[i];
                const float lifeT = sp.life > 0.001f ? sp.age / sp.life : 1.0f;

                // Ease in off the spawn, hold, then ease out, so a mote never pops in or cuts off.
                constexpr float kIn = 0.15f, kOut = 0.45f;
                float env = 1.0f;
                if (lifeT < kIn)              env = lifeT / kIn;
                else if (lifeT > 1.0f - kOut) env = (1.0f - lifeT) / kOut;
                if (env < 0.0f) env = 0.0f;
                if (env > 1.0f) env = 1.0f;

                const float twinkle = 0.5f + 0.5f * sinf(sp.twinkle);
                const float alpha   = style.sparkleAlpha * env * twinkle * alphaScale;
                if (alpha <= 0.003f)
                    continue;

                const float wx = pos[0] + sp.pos[0];
                const float wy = pos[1] + sp.pos[1];
                const float wz = pos[2] + sp.pos[2];

                // A mote the eye cannot see is dropped, so the particles never glitter through a wall.
                if (occlude)
                {
                    const float to[3] = { wx, wy, wz };
                    if (LineBlocked(camera, to, 2.0f)) continue;
                }

                // The disc lies in the plane perpendicular to the eye->mote ray, so it reads as a
                // round ball from any angle (the shaft's vertical billboard would foreshorten it when
                // the camera looks down). cross(worldUp, f) collapses when the ray is straight up or
                // down, so that degenerate case falls back to a world axis.
                float f[3] = { wx - camera[0], wy - camera[1], wz - camera[2] };
                float flen = sqrtf(f[0] * f[0] + f[1] * f[1] + f[2] * f[2]);
                if (flen < 1e-4f) { f[0] = 0.0f; f[1] = 1.0f; f[2] = 0.0f; flen = 1.0f; }
                f[0] /= flen; f[1] /= flen; f[2] /= flen;

                float r[3] = { -f[1], f[0], 0.0f };
                float rlen = sqrtf(r[0] * r[0] + r[1] * r[1]);
                if (rlen < 1e-4f) { r[0] = 1.0f; r[1] = 0.0f; r[2] = 0.0f; rlen = 1.0f; }
                r[0] /= rlen; r[1] /= rlen; r[2] /= rlen;

                float u[3] = { f[1] * r[2] - f[2] * r[1],
                               f[2] * r[0] - f[0] * r[2],
                               f[0] * r[1] - f[1] * r[0] };

                // A mote swells a little as it brightens, so a flicker reads as a glint.
                const float size = style.sparkleSize * (0.85f + 0.15f * twinkle);
                for (int k = 0; k < 3; ++k) { r[k] *= size; u[k] *= size; }

                const gfx::Color core     = PackTint(alpha, rgb, 0.85f);
                const gfx::Color shoulder = PackTint(alpha * kShoulder, rgb, 0.55f);
                const gfx::Color rim      = Pack(0.0f, rgb);

                float mid[kSegments][3];
                float edge[kSegments][3];
                for (int s = 0; s < kSegments; ++s)
                {
                    const float a  = kTwoPi * float(s) / float(kSegments);
                    const float ca = cosf(a), sa = sinf(a);
                    const float dx = r[0] * ca + u[0] * sa;
                    const float dy = r[1] * ca + u[1] * sa;
                    const float dz = r[2] * ca + u[2] * sa;

                    mid[s][0]  = wx + dx * kRing1; mid[s][1]  = wy + dy * kRing1; mid[s][2]  = wz + dz * kRing1;
                    edge[s][0] = wx + dx * kRing2; edge[s][1] = wy + dy * kRing2; edge[s][2] = wz + dz * kRing2;
                }

                const float centre[3] = { wx, wy, wz };
                for (int s = 0; s < kSegments; ++s)
                {
                    const int n = (s + 1) % kSegments;
                    beacon_gfx::Triangle(centre, mid[s], mid[n], core, shoulder, shoulder);
                    beacon_gfx::Triangle(mid[s], edge[s], edge[n], shoulder, rim, rim);
                    beacon_gfx::Triangle(mid[s], edge[n], mid[n], shoulder, rim, shoulder);
                }
            }
        }
    }

    // Seeds a new beacon's mote field from its GUID, so each corpse's sparkles drift and flicker on
    // their own schedule rather than in lockstep with every other beacon.
    void LootBeam::SeedSparkles(Beacon& b)
    {
        uint32_t seed = uint32_t(b.guid) ^ uint32_t(b.guid >> 32);
        seed ^= 0x9E3779B9u;
        if (seed == 0)
            seed = 0xA341316Cu;
        b.rngSeed = seed;
        for (int i = 0; i < kMaxSparkles; ++i)
            SpawnSparkle(b.sparkles[i], b.rngSeed, style_);
    }

    void LootBeam::AdvanceSparkles(Beacon& b, float dt)
    {
        if (style_.sparkleCount <= 0)
            return;
        for (int i = 0; i < kMaxSparkles; ++i)
            AdvanceSparkle(b.sparkles[i], b.rngSeed, style_, dt);
    }

    void LootBeam::QueueBeacon(const Beacon& beacon, float alphaScale, const float rgb[3])
    {
        // The scene depth surface this client exposes is not the world's, so a depth test rejects the
        // beam everywhere; the shaft is drawn through and its foot is clipped to cover instead, so it
        // is always present but never draws out of the ground or a wall it stands behind.
        beacon_gfx::SetDepth(gfx::Depth::Through);
        beacon_gfx::SetPush(0.0f, 0.0f);

        // The body is on the ground, so its own position is the height the shaft rises from. Using a
        // ground query for the shaft risked a bad hit on a lower surface burying it under the
        // rendered terrain, so the position of the body itself is used.
        const float baseZ = beacon.pos[2];

        // Per-row line-of-sight occlusion: every band of the shaft, and every mote, traces to the eye,
        // and whatever the eye cannot see is dropped. The beam stays (no despawn) but no part of it
        // draws through a hill or wall. The engine's own trace is the occluder here because the scene
        // depth surface this client exposes is not the world's.
        const bool occlude = !style_.throughWalls;

        if (occlude && occlDiag_ < 12)
        {
            ++occlDiag_;
            float eye[3];
            cam::GetPosition(eye);
            const float bz = beacon.pos[2];
            const float hz = bz + style_.height;
            for (int k = 0; k < 3; ++k)
            {
                const float z = bz + (hz - bz) * (k / 2.0f);
                const float to[3] = { beacon.pos[0], beacon.pos[1], z };
                world::WorldHit hit, mhit;
                const int ty = world::TraceLine(eye, to, hit);
                const int my = PickProjected(eye, to, mhit) ? mhit.type : 0;
                const float dx = to[0] - eye[0], dy = to[1] - eye[1], dz = to[2] - eye[2];
                const float len = sqrtf(dx * dx + dy * dy + dz * dz);
                Log(WXL_LOG_INFO, "occl: z=%.1f gap=%.2f type=%d t=%.3f mtype=%d", z,
                    ty ? (1.0f - hit.t) * len : -1.0f, ty, hit.t, my);
            }
        }

        if (style_.showBeam && style_.height > 0.01f)
            QueueBeamColumn(beacon.pos, baseZ, style_, alphaScale, rgb, occlude);

        if (style_.showSparkles && style_.sparkleCount > 0)
        {
            int count = style_.sparkleCount;
            if (count > kMaxSparkles) count = kMaxSparkles;
            QueueSparkles(beacon.pos, beacon.sparkles, count, style_, alphaScale, rgb, occlude);
        }
    }

    void LootBeam::OnWorldEnter(const ev::WorldEnterArgs& a)
    {
        inWorld_ = true;
        Log(WXL_LOG_INFO, "world entered (map %u)", a.mapId);
    }

    void LootBeam::OnWorldLeave(const ev::WorldLeaveArgs&)
    {
        inWorld_    = false;
        beaconCount_ = 0;
        trackedCount_ = 0;
        beacon_gfx::Clear();
    }

    void LootBeam::OnDeviceLost(const ev::DeviceResetArgs&)
    {
        // The depth-occlusion shader is a DEFAULT-pool resource; the device is about to free it.
        beacon_gfx::OnDeviceLost();
    }

    void LootBeam::OnUpdate(const ev::UpdateArgs& a)
    {
        ReloadConfigIfChanged();
        phase_ += a.dt * style_.pulseSpeed * kTwoPi;
        phase_ = fmodf(phase_, kTwoPi); // keep the phase bounded over a long session

        // One frame's worth of shapes only. The flush below empties the queue on the normal path, but
        // a frame that never reached the world scene pass would otherwise leave its shapes to pile up
        // under the next one.
        beacon_gfx::Clear();
        haveWorldMatrices_ = false; // recapture this frame's world matrices at the M2 pass
        g_modelPicksLeft   = kModelPickBudget;
        beacon_gfx::ResetOccluder();

        // Derive the world state live rather than trusting OnWorldEnter alone: a module loaded after
        // the client was already in-world would otherwise never see the enter event and stay dark.
        inWorld_ = world::CurrentMapId() >= 0;

        // The player's model instance, refreshed once a frame: the M2 pass compares every batch's model
        // against it to collect the character's silhouette (see OnM2Batch). The root of the chain, so a
        // mount (which parents the rider) is masked as well.
        void* model = inWorld_ ? world::ResolveObject(world::ActivePlayerGuid(), world::kTypeMaskPlayer) : nullptr;
        model = model ? unit::Model(model) : nullptr;
        for (int hop = 0; model && hop < 8; ++hop)
        {
            void* parent = unit::ModelParent(model);
            if (!parent) break;
            model = parent;
        }
        playerModel_ = model;

        if (!style_.enabled || !inWorld_)
        {
            beaconCount_  = 0;
            trackedCount_ = 0;
            return;
        }

        const int enumerated = ScanUnits();
        // Torment patch (PINNED.md): no ScanLoot(); the loot window's own read is not a tier source.
        UpdateFade(a.dt);
        if (beaconCount_ == 0)
        {
            if (!loggedFirstScan_)
            {
                loggedFirstScan_ = true;
                Log(WXL_LOG_INFO, "diag: map=%d player=%llu enumerated=%d beacons=0 (first scan)",
                    world::CurrentMapId(), world::ActivePlayerGuid(), enumerated);
            }
            if (++emptyFrameStreak_ >= 240 && emptyWarnings_ < 5)
            {
                ++emptyWarnings_;
                emptyFrameStreak_ = 0;
                Log(WXL_LOG_WARN,
                    "diag: 240 frames in world, enumerated=%d, no dead units -- the health field may be wrong",
                    enumerated);
            }
            return;
        }
        emptyFrameStreak_ = 0;

        if (!loggedFirstScan_)
        {
            loggedFirstScan_ = true;
            Log(WXL_LOG_INFO, "diag: map=%d player=%llu enumerated=%d beacons=%d (first scan)",
                world::CurrentMapId(), world::ActivePlayerGuid(), enumerated, beaconCount_);
        }

        // -1..+1 mapped into [1 - pulse, 1], so the beacon never gets brighter than the configured
        // alpha and a pulse of 0 is perfectly steady. The per-beacon fade folds in on top, so a body
        // still fading in or out is dimmed for the whole of its crossing.
        const float pulseScale = 1.0f - 0.5f * style_.pulse * (1.0f - sinf(phase_));
        for (int i = 0; i < trackedCount_; ++i)
        {
            if (beacons_[i].fade <= 0.001f) continue;

            const float* rgb = style_.color;
            const int    t   = beacons_[i].tier;
            if (style_.lootColor && t >= 0 && t < kTierCount)
            {
                // A tier switched off is filtered out entirely: the corpse gets no beacon at all, so
                // unwanted drops (bare currency, greys, ...) can be hidden without hiding everything.
                if (!style_.tiers[t].enabled) continue;
                rgb = style_.tiers[t].color;
            }

            // An off-screen shaft costs nothing to skip and would have drawn no pixel, so cull it
            // before the queue. That is where a camp full of corpses stops paying for the bodies
            // behind the camera or off the edge of the screen.
            if (!BeamInView(beacons_[i].pos, style_)) continue;

            QueueBeacon(beacons_[i], pulseScale * beacons_[i].fade, rgb);
        }
    }

    // Captured at a world draw: these are the matrices the depth buffer was written with. By the time
    // world-scene-end fires the client has put its own screen-space matrices back, so the live device
    // matrices are read here and handed to the beacon in the same frame.
    void LootBeam::OnM2Batch(const ev::M2BatchDrawArgs& a)
    {
        // Collect the active player's exact silhouette while its geometry is on the device. The engine
        // gives the SDK no model bounds, so the beam's player occlusion is this mask rather than a
        // stand-in primitive: the character's own batches, re-issued into a screen-sized target at its
        // real size and shape.
        if (playerModel_ && !style_.throughWalls)
        {
            for (void* m = a.model; m; m = unit::ModelParent(m))
            {
                if (m == playerModel_)
                {
                    beacon_gfx::StampOccluder(gx::Device9(a.device), a.primType, a.baseVertex,
                                              a.minIndex, a.numVerts, a.startIndex, a.primCount);
                    break;
                }
            }
        }

        if (haveWorldMatrices_) return; // fires per batch; once a frame is enough
        gx::Device9 dev(a.device);
        dev.GetTransform(gx::ts::kView, worldView_);
        dev.GetTransform(gx::ts::kProjection, worldProj_);
        haveWorldMatrices_ = true;
    }

    void LootBeam::OnWorldSceneEnd(const ev::WorldSceneEndArgs& a)
    {
        if (!style_.enabled || !inWorld_ || beaconCount_ == 0)
        {
            beacon_gfx::Clear();
            return;
        }

        gx::Device9 dev(a.device);

        // The live device matrices captured at the M2 pass turned out to be the client's stale ones
        // (the beam pinned to screen centre), so placement stays on gfx::SceneMatrices, which lands
        // the shaft correctly.
        beacon_gfx::SetMatrices(nullptr, nullptr);

        // One-shot: where the first beacon lands in clip space, so a beacon that draws only up close
        // can be told apart from one the far plane or an off-screen projection is rejecting.
        if (!loggedClipDiag_)
        {
            loggedClipDiag_ = true;
            int first = -1;
            for (int i = 0; i < trackedCount_; ++i)
            {
                if (beacons_[i].fade > 0.001f) { first = i; break; }
            }
            if (first < 0) first = 0;
            float eye[3];
            cam::GetPosition(eye);
            const float* view = cam::GetView();
            const float* proj = cam::GetProjection();
            const float px = beacons_[first].pos[0] - eye[0];
            const float py = beacons_[first].pos[1] - eye[1];
            const float pz = beacons_[first].pos[2] - eye[2];
            const float vx = px * view[0] + py * view[4] + pz * view[8] + view[12];
            const float vy = px * view[1] + py * view[5] + pz * view[9] + view[13];
            const float vz = px * view[2] + py * view[6] + pz * view[10] + view[14];
            const float cx = vx * proj[0] + vy * proj[4] + vz * proj[8] + proj[12];
            const float cy = vx * proj[1] + vy * proj[5] + vz * proj[9] + proj[13];
            const float cz = vx * proj[2] + vy * proj[6] + vz * proj[10] + proj[14];
            const float cw = vx * proj[3] + vy * proj[7] + vz * proj[11] + proj[15];
            const float dist = sqrtf(px * px + py * py + pz * pz);
            Log(WXL_LOG_INFO,
                "diag: beacon0=(%.0f,%.0f,%.0f) eye=(%.0f,%.0f,%.0f) dist=%.1f viewZ=%.1f "
                "ndc=(%.2f,%.2f,%.2f) w=%.1f projFar=%.0f proj10=%.4f proj11=%.4f proj14=%.2f",
                beacons_[first].pos[0], beacons_[first].pos[1], beacons_[first].pos[2], eye[0], eye[1],
                eye[2],
                dist, vz, cw != 0.0f ? cx / cw : 0.0f, cw != 0.0f ? cy / cw : 0.0f,
                cw != 0.0f ? cz / cw : 0.0f, cw,
                proj[14] != 0.0f ? -proj[14] / proj[10] : -1.0f,
                proj[10], proj[11], proj[14]);
        }

        const size_t queued = beacon_gfx::Pending();
        const long   result = beacon_gfx::Draw(dev, a.sceneDepth);

        if (!loggedFirstFlush_)
        {
            loggedFirstFlush_ = true;
            Log(WXL_LOG_INFO, "diag: first flush dev=%p depth=%p queued=%zu result=%ld",
                a.device, a.sceneDepth, queued, result);

            float praw = 0.0f, pbz = 0.0f, puv[2] = {};
            if (beacon_gfx::ProbeResult(&praw, &pbz, puv))
            {
                const float* pj = cam::GetProjection();
                const float d3d = pj[14] / (praw - pj[10]);
                const float gl  = (pj[14] * 0.5f) / (praw - (1.0f + pj[10]) * 0.5f);
                Log(WXL_LOG_INFO,
                    "probe: uv=(%.3f,%.3f) raw=%.6f beamZ=%.2f sceneD3D=%.2f sceneGL=%.2f",
                    puv[0], puv[1], praw, pbz, d3d, gl);

                const float grid[6][2] = { { 0.5f, 0.02f }, { 0.5f, 0.25f }, { 0.5f, 0.45f },
                                           { 0.5f, 0.65f }, { 0.5f, 0.85f }, { 0.5f, 0.98f } };
                for (int i = 0; i < 6; ++i)
                {
                    const float d = beacon_gfx::ReadDepthAtUV(dev, a.sceneDepth, grid[i][0], grid[i][1]);
                    Log(WXL_LOG_INFO, "probe grid: uv=(%.2f,%.2f) raw=%.6f scene=%.2f", grid[i][0],
                        grid[i][1], d, pj[14] / (d - pj[10]));
                }
            }
        }

        if (!loggedSetup_)
        {
            int path = -1, vs = 0, ps = 0, tex = 0;
            if (beacon_gfx::SetupResult(&path, &vs, &ps, &tex))
            {
                loggedSetup_ = true;
                Log(WXL_LOG_INFO, "occlusion setup: path=%d vs=%d ps=%d tex=%d", path, vs, ps, tex);
                int lv = 0, tw = 0, th = 0, tf = 0;
                if (beacon_gfx::DepthTextureInfo(&lv, &tw, &th, &tf))
                    Log(WXL_LOG_INFO, "depth texture: %dx%d levels=%d fmt=%d", tw, th, lv, tf);
            }
        }
    }
}
