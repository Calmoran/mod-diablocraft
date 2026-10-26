// Native modern-M2 reader: the MD21 container demux (harvests the MD20 body + auxiliary chunks).
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

#include "M2NativeInternal.hpp"

#include <cstdint>
#include <cstring>

namespace
{
    namespace fmt = wxl::structure::m2;

    /// MD21-container tag as the little-endian dword read of the on-disk bytes. Unique among WoW chunked
    /// formats, these tags are NOT byte-reversed ('MD21' on disk reads back 0x3132444D).
    constexpr uint32_t Tag(const char (&s)[5])
    {
        return uint32_t(uint8_t(s[0])) | (uint32_t(uint8_t(s[1])) << 8) |
               (uint32_t(uint8_t(s[2])) << 16) | (uint32_t(uint8_t(s[3])) << 24);
    }
}

namespace wxl::runtime::m2native::detail
{
    /**
     * @brief Walks the MD21 container, harvesting the body location and the auxiliary chunks.
     * @param buf   resident container bytes.
     * @param size  container byte size.
     * @param s     receives the harvest.
     * @return true when an MD20 body large enough for a full header was found.
     */
    bool ScanContainer(const uint8_t* buf, uint32_t size, Scan& s)
    {
        std::memset(&s, 0, sizeof s);
        uint32_t offV = 0;
        while (offV + 8 <= size)
        {
            const uint32_t tag = Rd32(buf + offV);
            const uint32_t sz  = Rd32(buf + offV + 4);
            if (sz > size || offV + 8 + sz > size) break; // malformed tail; keep what we have
            const uint8_t* payload = buf + offV + 8;

            switch (tag)
            {
            case fmt::kMagicMD21: // the MD20 body itself
                s.bodyOff  = offV + 8;
                s.bodySize = sz;
                break;
            case Tag("TXID"):
            {
                uint32_t n = sz / 4;
                if (n > kMaxTxid) n = kMaxTxid;
                for (uint32_t i = 0; i < n; ++i) s.txid[i] = Rd32(payload + i * 4);
                s.txidCount = n;
                break;
            }
            case Tag("SFID"):
                s.sfidCount = sz / 4;
                if (s.sfidCount) s.sfidFirst = Rd32(payload);
                break;
            case Tag("TXAC"): s.skipMask |= kSkipTxac; break;
            case Tag("LDV1"): s.skipMask |= kSkipLdv1; break;
            case Tag("AFID"): s.skipMask |= kSkipAfid; break;
            case Tag("SKID"): s.skipMask |= kSkipSkid; break;
            case Tag("PFID"):
            case Tag("BFID"): s.skipMask |= kSkipPhysBone; break;
            default:          s.skipMask |= kSkipOther; break;
            }
            offV += 8 + sz;
        }
        return s.bodyOff != 0 && s.bodySize >= sizeof(fmt::M2Header) &&
               s.bodyOff + s.bodySize <= size;
    }
}
