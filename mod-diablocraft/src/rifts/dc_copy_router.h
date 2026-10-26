/*
 * World of DiabloCraft - the copy router, without the core (docs/research/clustering.md section 2).
 *
 * A copy is one instance of an open-zone map with all that map's zones in it, keyed by (map, tier) (D3's game holding
 * every act; for bounty acts a copy of 751 holds acts 1 and 2, of 752 acts 3 and 4, of 753 act 5).
 * Each zone has its own cap, counted inside the copy: the players in that zone plus the seats promised to players on
 * their way. Where a player goes, on the zone's map:
 *   1. a party is never split: a copy of the map holding (or promised to) the party's leader, else the lowest-numbered
 * copy of the map holding another member, whatever its count (so a zone can go past its cap to keep a party together);
 * a member on another map is on another continent, and keeps nobody out of a copy of this one;
 *   2. else the lowest-numbered copy of the map and tier whose count in that zone, plus the one seat, fits the zone's cap;
 *   3. else a new copy, numbered with the lowest number free in the map and tier (a closed copy 2 is reused before a
 * copy 5).
 * A routed player holds a promised seat until they arrive or it times out. A copy with nobody in it and nothing
 * promised is empty from that moment and closes once it has been empty for the linger time; until then it is still a
 * copy with room. Nobody is ever moved to merge copies. A GM is routed like anyone but holds no seat and is never
 * counted.
 *
 * No core header: dc_open_rift.cpp keeps the instances, binds and hooks; scripts/tests/world/test_copy_router.py compiles this file
 * as it is and drives it.
 */
#ifndef DC_COPY_ROUTER_H
#define DC_COPY_ROUTER_H

#include <algorithm>
#include <cstdint>
#include <functional>
#include <map>
#include <string>
#include <vector>

namespace DC::Rifts::CopyRouter
{
    struct Seat
    {
        std::uint64_t player = 0;
        std::string zone;
        std::int64_t until = 0; // seconds; the seat is gone from this moment
    };

    struct Copy
    {
        std::uint32_t map = 0;
        unsigned tier = 0, number = 0;
        std::uint32_t instanceId = 0;
        std::map<std::uint64_t, std::string> inside; // player -> the zone they are sealed to (no GM)
        std::vector<Seat> promised;
        std::int64_t emptySince = -1; // seconds, -1 while someone is in it or promised

        unsigned InZone(std::string const& zone, std::uint64_t except) const
        {
            unsigned n = 0;
            for (auto const& [player, where] : inside)
                n += player != except && where == zone;
            for (Seat const& seat : promised)
                n += seat.player != except && seat.zone == zone;
            return n;
        }
        bool Holds(std::uint64_t player) const
        {
            return inside.count(player) ||
                   std::any_of(promised.begin(), promised.end(), [&](Seat const& s) { return s.player == player; });
        }
    };

    struct Rules
    {
        std::function<unsigned(std::string const& zone)> cap; // the zone's cap of strangers (rifts copy_cap_<zone>)
        std::int64_t linger = 0;                              // seconds an empty copy stays open (copy_linger_seconds)
        std::int64_t seatTimeout = 0; // seconds a promised seat is held (copy_seat_timeout_seconds)
    };

    // Where the router sends a player: an open copy (instanceId set), or a new one to open under `number`.
    struct Pick
    {
        std::uint32_t instanceId = 0;
        unsigned number = 0;
        bool open = false;
        bool party = false; // chosen to keep the party together (rule 1)
    };

    class Router
    {
    public:
        // Seats past their time go; a copy left with nobody and nothing promised is empty from then; a copy empty for
        // the linger time closes. Every other call runs this first, so time is read only where it is passed in.
        void Tidy(Rules const& rules, std::int64_t now)
        {
            for (Copy& copy : copies)
            {
                std::int64_t lastSeat = -1;
                copy.promised.erase(std::remove_if(copy.promised.begin(), copy.promised.end(),
                                                   [&](Seat const& s)
                                                   {
                                                       if (s.until > now)
                                                           return false;
                                                       lastSeat = std::max(lastSeat, s.until);
                                                       return true;
                                                   }),
                                    copy.promised.end());
                if (copy.inside.empty() && copy.promised.empty() && copy.emptySince < 0)
                    copy.emptySince = lastSeat >= 0 ? lastSeat : now;
            }
            copies.erase(std::remove_if(copies.begin(), copies.end(), [&](Copy const& c)
                                        { return c.emptySince >= 0 && now - c.emptySince >= rules.linger; }),
                         copies.end());
        }

        // `party`: the player's party, leader first, the player included or not (a solo player passes nothing). `map`: the
        // zone's map.
        Pick Route(Rules const& rules, std::int64_t now, std::uint32_t map, unsigned tier, std::string const& zone,
                   std::uint64_t player, std::vector<std::uint64_t> const& party)
        {
            Tidy(rules, now);
            Copy const* leaderCopy = nullptr;
            Copy const* memberCopy = nullptr;
            for (Copy const& copy : copies)
                for (std::size_t i = 0; i < party.size(); ++i)
                    if (copy.map == map && party[i] != player && copy.Holds(party[i]))
                    {
                        Copy const*& slot = i == 0 ? leaderCopy : memberCopy;
                        if (!slot || copy.number < slot->number)
                            slot = &copy;
                    }
            if (Copy const* together = leaderCopy ? leaderCopy : memberCopy)
                return {together->instanceId, together->number, false, true};
            Copy const* best = nullptr;
            for (Copy const& copy : copies)
                if (copy.map == map && copy.tier == tier && copy.InZone(zone, player) + 1 <= rules.cap(zone) &&
                    (!best || copy.number < best->number))
                    best = &copy;
            if (best)
                return {best->instanceId, best->number, false, false};
            return {0, FreeNumber(map, tier), true, false};
        }

        // The new copy `number` of (`map`, `tier`) is the instance the caller just made.
        void Opened(std::uint32_t map, unsigned tier, unsigned number, std::uint32_t instanceId)
        {
            Copy copy;
            copy.map = map;
            copy.tier = tier;
            copy.number = number;
            copy.instanceId = instanceId;
            copies.push_back(copy);
        }

        // The player is on their way into `instanceId`: one seat there, and none anywhere else.
        void Promise(Rules const& rules, std::int64_t now, std::uint32_t instanceId, std::uint64_t player,
                     std::string const& zone)
        {
            for (Copy& copy : copies)
                copy.promised.erase(std::remove_if(copy.promised.begin(), copy.promised.end(),
                                                   [&](Seat const& s) { return s.player == player; }),
                                    copy.promised.end());
            if (Copy* copy = Find(instanceId))
            {
                copy->promised.push_back({player, zone, now + rules.seatTimeout});
                copy->emptySince = -1;
            }
        }

        // Arrival (a routed trip, a town portal, a login): the player is inside, sealed to `zone`; their seat is used, and
        // they are in no other copy. An instance the router does not know (a copy closed while someone was still bound
        // to it, a restart) is adopted as a copy of its map and the arriving player's tier. A GM is never counted.
        void Enter(std::int64_t now, std::uint32_t instanceId, std::uint32_t map, unsigned tier, std::uint64_t player,
                   std::string const& zone, bool gm)
        {
            for (Copy& copy : copies)
                if (copy.Holds(player))
                {
                    copy.inside.erase(player);
                    copy.promised.erase(std::remove_if(copy.promised.begin(), copy.promised.end(),
                                                       [&](Seat const& s) { return s.player == player; }),
                                        copy.promised.end());
                    if (copy.inside.empty() && copy.promised.empty())
                        copy.emptySince = now;
                }
            Copy* copy = Find(instanceId);
            if (!copy)
            {
                Opened(map, tier, FreeNumber(map, tier), instanceId);
                copy = &copies.back();
            }
            if (!gm)
                copy->inside[player] = zone;
            if (!copy->inside.empty() || !copy->promised.empty())
                copy->emptySince = -1;
            else if (copy->emptySince < 0)
                copy->emptySince = now;
        }

        // The player left the copy `instanceId` (a trip out, logging out, a disconnect): their place there is free at once.
        // A seat promised elsewhere stays: a trip between copies leaves the old one during the loading screen.
        void Leave(std::int64_t now, std::uint32_t instanceId, std::uint64_t player)
        {
            if (Copy* copy = Find(instanceId); copy && copy->inside.erase(player) && copy->inside.empty() &&
                                               copy->promised.empty())
                copy->emptySince = now;
        }

        // The cap the core holds a copy to (the hook's maxPlayers): every zone's cap plus a party's overflow.
        static unsigned HardCap(std::vector<std::string> const& zones, Rules const& rules, unsigned partyOverflow)
        {
            unsigned total = 0;
            for (std::string const& zone : zones)
                total += rules.cap(zone) + partyOverflow;
            return total;
        }

        Copy* Find(std::uint32_t instanceId)
        {
            for (Copy& copy : copies)
                if (copy.instanceId == instanceId)
                    return &copy;
            return nullptr;
        }
        void Drop(std::uint32_t instanceId)
        {
            copies.erase(
                std::remove_if(copies.begin(), copies.end(), [&](Copy const& c) { return c.instanceId == instanceId; }),
                copies.end());
        }
        std::vector<Copy> const& Copies() const
        {
            return copies;
        }

    private:
        // The lowest number no copy of (`map`, `tier`) has.
        unsigned FreeNumber(std::uint32_t map, unsigned tier) const
        {
            unsigned number = 1;
            while (std::any_of(copies.begin(), copies.end(),
                               [&](Copy const& c) { return c.map == map && c.tier == tier && c.number == number; }))
                ++number;
            return number;
        }

        std::vector<Copy> copies;
    };
} // namespace DC::Rifts::CopyRouter

#endif
