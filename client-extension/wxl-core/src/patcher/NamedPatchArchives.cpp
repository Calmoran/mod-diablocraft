// wxl-named-patch-archives (patcher script): widens the client's own patch-archive directory scan
// from a single-letter wildcard to an arbitrary one, so a patch archive/folder can be named
// "Patch-Interface.MPQ" instead of only "Patch-A.MPQ".."Patch-Z.MPQ".
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
//
// The client's own patch-archive directory scan hands "patch-?.MPQ" and "patch-%s-?.MPQ" (locale
// variant) to its directory-listing helper as directory-scan patterns, i.e. Win32 FindFirstFile
// wildcards, not printf specifiers: '?' matches exactly one character, so the stock scan only ever
// finds single-letter names. '*' matches any run of characters, so the same scan then also finds
// "Patch-<anything>.MPQ" -- a real archive AND a plain directory with that name (the scan enumerates
// both; the engine already knows how to mount a directory as an uncompressed virtual archive, it just
// never gets offered one with a name this pattern didn't already match). Both format strings live back
// to back in the client's read-only data section, with the '?' byte at +9 and +6 respectively.

#include "patcher/PatchScript.hpp"

namespace
{
    using namespace wxl::patcher;

    class NamedPatchArchives final : public PatchScript
    {
    public:
        const char* name() const override { return "named-patch-archives"; }

        bool Apply(PeImage& pe) const override
        {
            const uint8_t asterisk = '*';
            struct Edit { uint32_t va; };
            const Edit edits[] = {
                { 0x9e2709 }, // '?' in "patch-%s-?.MPQ"
                { 0x9e2716 }, // '?' in "patch-?.MPQ"
            };
            for (const Edit& e : edits)
                if (!pe.WriteVa(e.va, &asterisk, 1)) return false;
            return true;
        }
    };

    const NamedPatchArchives g_namedPatchArchives;
}
