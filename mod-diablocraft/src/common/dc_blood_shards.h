#ifndef DC_BLOOD_SHARDS_H
#define DC_BLOOD_SHARDS_H

#include <cstdint>

// Blood Shards (docs/proposals/kadala.md 4.1 to 4.3): an account-and-mode
// ledger count, capped at 500 plus 10 per Greater Rift level the account has beaten alone
// (both numbers are loot tunables). The cap limits only what is received: it is checked at
// each credit, and spending is never blocked. Header-only so the test compiles this code.
namespace DC::BloodShards
{
// Constant (account_economy.csv): the Blood Shard item identity; ledger key, never a price.
constexpr std::uint32_t Entry = 102007;

inline std::uint64_t Cap(std::uint64_t base, std::uint64_t perLevel, std::uint64_t bestSolo)
{
    return base + perLevel * bestSolo;
}

struct Credit
{
    std::uint64_t granted = 0, lost = 0;
};

// What a credit of `amount` does to a ledger holding `held` under `cap`: it fills to the cap
// and the rest is lost (4.3 (a)). A balance already above a lowered cap is left alone.
inline Credit Fit(std::uint64_t held, std::uint64_t amount, std::uint64_t cap)
{
    std::uint64_t const room = held >= cap ? 0 : cap - held;
    std::uint64_t const granted = amount < room ? amount : room;
    return {granted, amount - granted};
}
} // namespace DC::BloodShards

#endif
