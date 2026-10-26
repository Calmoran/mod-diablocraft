/*
 * Skeletal Mage and its five runes. The cast hits nothing; it raises a mage (dc_necromancer_pets.cpp) beside the
 * Necromancer. Life Support takes 10% of the Life when the cast begins, Singularity takes the rest of the Essence and
 * the mage hits harder for each point.
 */

#include "dc_necromancer_skeletal_mage.h"
#include "dc_necromancer_common.h"
#include "dc_necromancer_pets.h"
#include "dc_necromancer_skeletal_mage_math.h"

#include <mutex>
#include <unordered_map>

namespace DC::Combat::Necromancer::SkeletalMage
{
    namespace
    {
        constexpr std::string_view Skill = "Skeletal Mage";
        constexpr Resources::Resource const& Essence = *Resources::Find("Necromancer", "essence");

        double Tune(char const* name)
        {
            return DC::Tunables::Get("necromancer", name);
        }

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        // The place the mage rises: a share of the way from the Necromancer to the enemy aimed at, the Necromancer's own place
        // when it has none.
        Position RisePlace(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
        {
            if (targets.empty())
                return player->GetPosition();
            double const share = Tune(RuneAt(spellId) == Rune::Contamination ? "contamination_mage_rise_share"
                                                                                : "skeletal_mage_rise_share");
            Unit const* enemy = targets.front();
            return Position(float(Along(player->GetPositionX(), enemy->GetPositionX(), share)),
                            float(Along(player->GetPositionY(), enemy->GetPositionY(), share)),
                            float(Along(player->GetPositionZ(), enemy->GetPositionZ(), share)));
        }

        // The Essence a Singularity cast consumed, for the mage the same cast raises (the cast resolves at once).
        std::mutex mutex;
        std::unordered_map<std::uint64_t, double> consumed;
    } // namespace

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) ? std::optional<double>(0.0) : std::nullopt;
    }

    void Casting(Player* player, std::uint32_t spellId)
    {
        if (!player)
            return;
        switch (RuneAt(spellId))
        {
            case Rune::LifeSupport:
                // "Risen mages cost 10% health to cast."
                SpendLife(player, Tune("life_support_life_cost_pct"));
                break;
            case Rune::Singularity:
            {
                // "Consumes all Essence": the pool whole, before the core takes the cost; the module takes the rest.
                double const points = Resources::ToPoints(Essence, Resources::Units(player, Essence));
                double const beyond = EssenceBeyondCost(points, Numbers::Num(spellId, "cost_resource"));
                if (beyond > 0)
                    Resources::SpendUnits(player, Essence, int32(std::llround(Resources::ToUnits(Essence, beyond))));
                std::lock_guard<std::mutex> guard(mutex);
                consumed[player->GetGUID().GetRawValue()] = points;
                break;
            }
            default:
                break;
        }
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        if (!player || !RowOf(spellId, Skill))
            return;
        double bonus = 0;
        if (RuneAt(spellId) == Rune::Singularity)
        {
            double points = 0;
            {
                std::lock_guard<std::mutex> guard(mutex);
                points = consumed[player->GetGUID().GetRawValue()];
                consumed.erase(player->GetGUID().GetRawValue());
            }
            // "The minion's damage is increased by {damage_bonus_pct} for every point of Essence consumed."
            bonus = SingularityBonusPct(Numbers::Num(spellId, "damage_bonus_pct"), points);
        }
        Pets::RaiseMage(player, RisePlace(player, spellId, targets), spellId, bonus);
    }
} // namespace DC::Combat::Necromancer::SkeletalMage
