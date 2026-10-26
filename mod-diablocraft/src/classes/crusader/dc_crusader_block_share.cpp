/*
 * The Block Chance share of the Crusader's shield skills: the multiplier the engine's own hit takes and the percentage
 * the Crusader's own strikes carry.
 */

#include "dc_crusader_block_share.h"
#include "dc_crusader_blessed_shield.h"
#include "dc_crusader_common.h"
#include "dc_crusader_shield_bash.h"
#include "../../stats/dc_stats.h"

namespace DC::Combat::Crusader::BlockShare
{
    namespace
    {
        // How many scopes of the Crusader's own strikes are open on this thread.
        thread_local unsigned own = 0;

        double BlockChance(Player* player)
        {
            auto const sheet = Stats::Get(player->GetGUID().GetRawValue());
            return sheet ? (*sheet)[Stat::BlockChance] : 0.0;
        }
    } // namespace

    OwnStrikes::OwnStrikes()
    {
        ++own;
    }

    OwnStrikes::~OwnStrikes()
    {
        --own;
    }

    double PctNow(Player* player, double damagePct, double sharePct)
    {
        return Pct(damagePct, sharePct, BlockChance(player));
    }

    void Multipliers(Player* player, std::uint32_t spellId, DC::Combat::Factors& out)
    {
        if (own || !player)
            return;
        auto main = ShieldBash::Main(spellId);
        if (!main)
            main = BlessedShield::Main(spellId);
        if (!main)
            return;
        double const factor = Factor(main->first, main->second, BlockChance(player));
        if (factor != 1.0)
            out.emplace_back("Block Chance share", factor);
    }
} // namespace DC::Combat::Crusader::BlockShare
