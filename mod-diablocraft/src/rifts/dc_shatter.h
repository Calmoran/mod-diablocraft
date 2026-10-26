/*
 * World of DiabloCraft - `.dc shatter`, the obelisk destruction preview.
 *
 * A GM-only harness to watch the shatter sequence and try portal
 * displays in game before any of it is wired into the rift open path. It
 * changes nothing about how a rift opens.
 *
 * Internal to the rifts folder; other modules include dc_rifts.h.
 */

#ifndef DC_SHATTER_H
#define DC_SHATTER_H

namespace DC::Rifts::Shatter
{
    void RegisterScripts();
}

#endif // DC_SHATTER_H
