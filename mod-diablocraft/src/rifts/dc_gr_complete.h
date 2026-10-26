/*
 * World of DiabloCraft - the line a Greater Rift gives its run when the Guardian falls in time (D3: "Greater Rift
 * Complete! You finished with 13 minutes and 44 seconds remaining."). What has no core in it: the words and the
 * colour of each part. The sending is dc_gr_progress.cpp's, over the channel of dc_rift_text.h; this file is what the
 * test compiles. Internal to the rifts folder.
 */

#ifndef DC_GR_COMPLETE_H
#define DC_GR_COMPLETE_H

#include "dc_rift_text.h"

#include <string>
#include <vector>

namespace DC::Rifts::Gr
{
    // The parts' colours, RRGGBB: the line is grey, the numbers with their units green (D3's).
    constexpr char const* LineColour = "b2b2b2";
    constexpr char const* NumberColour = "00ff00";

    // "13 minutes", "1 minute": the number and its unit, a part of its own in the colour of the numbers.
    inline Text::Part Counted(unsigned count, char const* one, char const* many)
    {
        return {NumberColour, std::to_string(count) + " " + (count == 1 ? one : many)};
    }

    // "Greater Rift Complete! You finished with 13 minutes and 44 seconds remaining." in parts. A unit that is 0 drops
    // ("44 seconds remaining", "13 minutes remaining"); a clock with nothing left says "0 seconds".
    inline std::vector<Text::Part> CompleteParts(unsigned secondsLeft)
    {
        unsigned const minutes = secondsLeft / 60, seconds = secondsLeft % 60;
        std::vector<Text::Part> parts{{LineColour, "Greater Rift Complete! You finished with "}};
        if (minutes > 0)
            parts.push_back(Counted(minutes, "minute", "minutes"));
        if (minutes > 0 && seconds > 0)
            parts.push_back({LineColour, " and "});
        if (seconds > 0 || minutes == 0)
            parts.push_back(Counted(seconds, "second", "seconds"));
        parts.push_back({LineColour, " remaining."});
        return parts;
    }
} // namespace DC::Rifts::Gr

#endif // DC_GR_COMPLETE_H
