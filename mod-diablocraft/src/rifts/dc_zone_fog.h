/*
 * World of DiabloCraft - zone fog on the open-zone copy.
 *
 * The world map of map 751 shows each sub-area through the core's own explored bits (PLAYER_EXPLORED_ZONES), drawn by the
 * client through the WorldMapOverlay rows cloned onto the copy's world maps (world_open_rift_dbc.csv). The client's engine
 * covers the map with fog and uncovers the walked path, so the server lights the whole map: on every arrival in a copy the
 * bits of the open zones' areas are set.
 *
 * The rules, with no core types, so a test compiles them as they are (test_open_rift_script.py). The glue is
 * dc_open_rift.cpp.
 */

#ifndef DC_ZONE_FOG_H
#define DC_ZONE_FOG_H

#include <cstdint>
#include <map>
#include <vector>

namespace DC::Rifts::ZoneFog
{
    // One AreaTable row: its id, its zone (0 when it is a zone) and its explore bit.
    struct Area
    {
        std::uint32_t id = 0, zone = 0, exploreFlag = 0;
    };

    // The explored-zones words to set: word -> the bits of every area that is one of `zones` or lies in one. A bit
    // past `words` is dropped, as the core drops it (Player::CheckAreaExploreAndOutdoor).
    inline std::map<std::uint32_t, std::uint32_t> Masks(std::vector<Area> const& areas,
                                                        std::vector<std::uint32_t> const& zones, std::uint32_t words)
    {
        std::map<std::uint32_t, std::uint32_t> masks;
        for (Area const& area : areas)
            for (std::uint32_t zone : zones)
                if ((area.id == zone || area.zone == zone) && area.exploreFlag / 32 < words)
                    masks[area.exploreFlag / 32] |= 1u << (area.exploreFlag % 32);
        return masks;
    }
} // namespace DC::Rifts::ZoneFog

#endif // DC_ZONE_FOG_H
