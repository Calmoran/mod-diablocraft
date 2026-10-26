// The stock orb pick round: `.dc orbrow` stands one "Orb candidate" (gameobject 910099) per candidate look in a line in front of the GM, each
// wearing its display, and whispers the labels left to right; a second `.dc orbrow`, or 10 minutes, takes the row away.
// A tester picks the red Health Globe, the orange Nephalem orb and the purple Greater Rift orb from the row on dev; nothing
// here applies a pick (rifts/gr_orb_display_id, rifts/nr_orb_display_id and the globe's globe_display_id take them).
#ifndef DC_ORB_PICK_H
#define DC_ORB_PICK_H

#include <array>
#include <cmath>
#include <cstdint>

namespace DC::OrbPick
{
    constexpr std::uint32_t CandidateObject = 910099; // world_objects.csv "Orb candidate"
    constexpr std::uint32_t LifetimeSeconds = 600;    // the row goes by itself
    constexpr float AheadYards = 6.0f;
    constexpr float SpacingYards = 3.0f;

    struct Candidate
    {
        std::uint32_t display;
        float scale;
        float lift; // yards the model's origin stands above the ground, so every look floats at one height
        char const* label;
        bool needsPatch; // tier 2: a Torment display row, so the client needs the Nightly patch to draw it
    };

    // The row wants bare spheres, so a look with a stand is not in it, except the Blood Orb kept as the red reference.
    // Tier 1: stock gameobject displays (a tunable swap, no client patch). Tier 2: the creature sphere looks as Torment
    // display rows 9701-9704 (world_object_displays.csv). The Ethereal Sphere is left out: its creature wears the
    // invisible stalker and its aura 54141 has no visual, so no stock model shows it. Dropped for a stand, read from
    // the model vertices in the client: 7800 (a base and a neck under the orb) and 7161 (the translocator pedestal).
    // The scales and lifts come from the same vertices: each sphere is brought to about a globe's size (radius 0.35)
    // with its centre 0.6 yards up. The Flame and Ice Sphere models are centred on their origin at radius 2.3 and 2.0,
    // the Frost and Lightning ones hang 3.5 and 1.9 up, the Nexus orb is centred on its origin at 0.87; the Blood Orb
    // is on a pedestal by its model, so it stays as the client draws it.
    constexpr std::array<Candidate, 6> Candidates{{
        {8365, 1.0f, 0.0f, "Blood Orb (red, on a pedestal: the reference)", false},
        {7781, 0.4f, 0.6f, "Nexus Magic Orb Blue (bare)", false},
        {9701, 0.15f, 0.6f, "Flame Sphere (orange, bare)", true},
        {9702, 0.45f, -0.96f, "Frost Sphere (bare)", true},
        {9703, 0.17f, 0.6f, "Ice Sphere (bare)", true},
        {9704, 0.4f, -0.15f, "Lightning Orb (bare)", true},
    }};

    struct Spot
    {
        float x;
        float y;
    };

    // Candidate i of n, AheadYards in front of a GM at (x, y) facing o, SpacingYards apart, the first on the GM's left.
    inline Spot Place(float x, float y, float o, std::size_t i, std::size_t n)
    {
        float const across = (float(n - 1) / 2.0f - float(i)) * SpacingYards; // + is the GM's left
        return {x + AheadYards * std::cos(o) - across * std::sin(o),
                y + AheadYards * std::sin(o) + across * std::cos(o)};
    }

    void RegisterScripts();
} // namespace DC::OrbPick

#endif
