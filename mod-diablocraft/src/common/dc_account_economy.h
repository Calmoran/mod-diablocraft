#ifndef DC_ACCOUNT_ECONOMY_H
#define DC_ACCOUNT_ECONOMY_H
#include "DatabaseEnv.h"
#include <cstdint>
#include <map>
#include <string>
class Player;
namespace DC::AccountEconomy
{
    struct Snapshot
    {
        std::uint32_t account = 0;
        std::string mode, gold, revision;
        std::map<std::uint32_t, std::string> materials;
    };
    bool Enabled();
    bool Eligible(Player const*);
    bool IsMaterial(std::uint32_t entry);
    std::uint64_t MaterialBalance(Player const*, std::uint32_t entry);
    // receipt is a stable source/reward identifier supplied by retryable grant callers.
    // Reusing a receipt for a different request refuses it. Empty receipts are new operations.
    // Blood Shards are capped (dc_blood_shards.h): a credit past the cap is cut to fit and the cut
    // amount comes back in *lost (0 for every other material and for a repeated receipt).
    bool CreditMaterial(Player*, std::uint32_t entry, std::uint64_t amount, std::string const& receipt = "",
                        std::uint64_t* lost = nullptr);
    bool CreditGold(Player*, std::uint64_t copper, std::string const& receipt = "");
    bool DebitMaterial(Player*, std::uint32_t entry, std::uint64_t amount);
    bool ReadSnapshot(Player const*, Snapshot&);
    // Raise the active account/mode ledger in one operation. Returns both
    // snapshots for the caller's audit log; no balance is ever decreased.
    bool TopUp(Player*, std::uint64_t goldCopper, std::uint64_t materialCount,
               Snapshot& before, Snapshot& after);
    bool ResolvePending(Player*);
    // After the stock first save, before login: same provenance and ledger
    // resolution, without online player enlistment or login finalization.
    bool ResolveCreation(Player*);
    // Commit the active account operation and supplied inventory/artisan statements.
    bool Commit(Player*, CharacterDatabaseTransaction const&);
    void RegisterScripts();
} // namespace DC::AccountEconomy
#endif
