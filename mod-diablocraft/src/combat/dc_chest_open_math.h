#pragma once
// When a chest counts as opened, with no core type, so tests/item_power_chest_open compiles this exact code. The core
// calls SetLootState(GO_ACTIVATED, user) for a chest on every loot generation by its opener (Player::SendLoot, from
// GO_READY) and again on every release of a chest that is not yet empty (LootHandler, with the releasing player), so a
// state of "activated" alone is not an opening. An opening is the change from any other state to activated. The
// production half is ChestEvents in dc_item_powers_events.cpp.
#include <cstdint>
#include <set>
#include <tuple>

namespace DC::Combat::ChestOpen
{
    // One chest: its map, the map's instance (a raid copy has the same guid as another's) and its guid.
    using Key = std::tuple<std::uint32_t, std::uint32_t, std::uint64_t>;

    class Openings
    {
    public:
        // The chest's loot state changed. True when this is an opening: the chest was not activated before and is now.
        // Any other state (ready again after a respawn or a restock, emptied, deactivated) makes the next activation a
        // new opening.
        bool Changed(Key const& chest, bool activated)
        {
            if (!activated)
            {
                open.erase(chest);
                return false;
            }
            return open.insert(chest).second;
        }

        // The chest left the world while activated: its next life starts closed.
        void Forget(Key const& chest)
        {
            open.erase(chest);
        }

        std::size_t Held() const
        {
            return open.size();
        }

    private:
        std::set<Key> open;
    };
} // namespace DC::Combat::ChestOpen
