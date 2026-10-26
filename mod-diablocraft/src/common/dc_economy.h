// Constant (1): Displayed-gold to native-copper conversion; Currency denomination contract, not a price.
// Constant (102006): Legacy Gold Bar item identity; Migration content ID.
#ifndef DC_ECONOMY_H
#define DC_ECONOMY_H
#include <cstdint>
#include <limits>
#include <stdexcept>
class Player;
namespace DC::Economy
{
    // One WoW copper is one displayed gold. The balance
    // is kept in copper and shown 1:1, so every D3 gold figure is used as
    // published and this factor is 1. GoldCost stays as the one named place the
    // conversion would live if it ever came back.
    constexpr std::uint64_t CopperPerGold = 1;
    // account_economy.csv: legacy Gold Bar denomination, before account cutover.
    // One bar is 100,000 gold, which is now 100,000 copper.
    constexpr std::uint32_t GoldBarEntry = 102006;
    std::uint64_t CopperPerBar();
    struct Payment { bool ok=false; std::uint32_t bars=0,copper=0; };
    inline Payment Plan(std::uint32_t copper,std::uint32_t bars,std::uint64_t cost)
    {
        auto const denomination = CopperPerBar();
        if(cost>std::uint64_t(copper)+std::uint64_t(bars)*denomination) return {};
        std::uint64_t broken=cost>copper?(cost-copper+denomination-1)/denomination:0;
        return {true,static_cast<std::uint32_t>(broken),static_cast<std::uint32_t>(copper+broken*denomination-cost)};
    }
    inline std::uint64_t GoldCost(std::uint64_t gold)
    {
        if (gold > std::numeric_limits<std::uint64_t>::max() / CopperPerGold)
            throw std::overflow_error("Gold price overflow");
        return gold * CopperPerGold;
    }
    std::uint64_t Balance(Player const* player);
    bool CanAfford(Player const* player, std::uint64_t copper);
    // Changes join the current account operation; callers commit inventory and fees together.
    bool Charge(Player* player, std::uint64_t copper);
    bool Credit(Player* player, std::uint64_t copper);
    void KnowCurrency(Player* player, std::uint32_t entry);
    void RegisterScripts();
} // namespace DC::Economy
#endif
