/*
 * World of DiabloCraft - the record a rift's centre-screen line travels in (contract
 * docs/contracts/rift-centre-text.md).
 *
 * A line is a kind and its coloured parts. The client draws it in the middle of the screen in its own size, fade and
 * place; the server fixes only the words and the colour of each part. This header is the record and nothing else (no
 * core header), so the test compiles it; dc_gr_progress.cpp hands the fields to DC::Bridge::Push. Internal to the rifts
 * folder.
 */

#ifndef DC_RIFT_TEXT_H
#define DC_RIFT_TEXT_H

#include <string>
#include <vector>

namespace DC::Rifts::Text
{
    // The addon whisper's prefix (the same wire as DCPARAGON).
    constexpr char const* Prefix = "DCRIFTTEXT";

    // The record's first field: a centre line. Reserved for the client to tell a record type apart should a second one
    // ever exist.
    constexpr char const* LineRecord = "C";

    // The kinds. The client may give each its own look and draws an unknown kind with its default one.
    constexpr char const* GreaterRiftComplete = "gr_complete";

    // One run of text in one colour: `colour` is six hex digits, RRGGBB, with no "#" and no "|c" escape.
    struct Part
    {
        std::string colour;
        std::string text;
    };

    // "C|<kind>|<colour>|<text>|<colour>|<text>...": the fields DC::Bridge::Push joins with '|'. The text of the parts
    // read in order is the whole line.
    inline std::vector<std::string> Fields(char const* kind, std::vector<Part> const& parts)
    {
        std::vector<std::string> fields{LineRecord, kind};
        for (Part const& part : parts)
        {
            fields.push_back(part.colour);
            fields.push_back(part.text);
        }
        return fields;
    }
} // namespace DC::Rifts::Text

#endif // DC_RIFT_TEXT_H
