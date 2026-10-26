/*
 * Blood Rush and its five runes. The engine moves the Necromancer to the point aimed at (up to the skill's distance); here: the Life the
 * cast takes (none for Hemostasis, twice for Metabolism), Metabolism's two charges in place of the cooldown, Transfusion's heal for each
 * enemy passed through, Potency's armor for a time, Molting's corpse where the rush began.
 */

#include "dc_necromancer_blood_rush.h"
#include "dc_necromancer_blood_rush_math.h"
#include "dc_necromancer_common.h"
#include "../../combat/dc_charge_store.h"
#include "../../combat/dc_corpses.h"

#include "GameTime.h"

#include <algorithm>
#include <cmath>
#include <mutex>
#include <unordered_map>

namespace DC::Combat::Necromancer::BloodRush
{
    namespace
    {
        constexpr std::string_view Skill = "Blood Rush";

        double Tune(char const* name)
        {
            return DC::Tunables::Get("necromancer", name);
        }

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        std::mutex mutex;
        std::unordered_map<std::uint64_t, ChargeStore> charges; // Metabolism's, by Necromancer
    } // namespace

    void Casting(Player* player, std::uint32_t spellId)
    {
        if (!player || !RowOf(spellId, Skill))
            return;
        // "Cost: 5% Health", none for Hemostasis, doubled for Metabolism.
        SpendLife(player, LifeCostPct(RuneAt(spellId), Tune("blood_rush_life_cost_pct"), Tune("metabolism_life_cost_pct")));
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const&)
    {
        if (!player || !RowOf(spellId, Skill))
            return;
        switch (RuneAt(spellId))
        {
            case Rune::Metabolism:
            {
                // "Provides an additional charge": two charges recharge a period each, in place of the cooldown.
                unsigned const cap = unsigned(Tune("metabolism_charges"));
                std::uint64_t const period = ReducedCooldownMilliseconds(
                    player, spellId, std::uint32_t(std::max(0.0, Tune("blood_rush_recharge_seconds")) * 1000.0 + 0.5));
                std::uint64_t wait;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    wait = charges[player->GetGUID().GetRawValue()].Spend(Now(), cap, period);
                }
                // The core put the record's cooldown on the button; a charge left clears it, none left holds it until the next lands.
                SendSkillCooldown(player, spellId, std::uint32_t(wait));
                break;
            }
            case Rune::Potency:
                // "Increases your armor by {armor_pct} for {duration_seconds} seconds after casting."
                Buffs::Stack(player, spellId, Stat::Armor, Bucket::Percent, Numbers::Num(spellId, "armor_pct"), 1,
                             Numbers::Num(spellId, "duration_seconds"));
                break;
            default:
                break;
        }
    }

    void Ground(Player* player, std::uint32_t spellId, Position const& destination)
    {
        if (!player || !RowOf(spellId, Skill))
            return;
        Position const start = player->GetPosition();
        switch (RuneAt(spellId))
        {
            case Rune::Transfusion:
            {
                // The rush stops where the engine's charge does: at most the skill's distance toward the point aimed at.
                double const reach = std::min(double(start.GetExactDist2d(destination)), Numbers::Num(spellId, "distance_yards"));
                double const angle = start.GetAbsoluteAngle(&destination);
                Position const end(start.GetPositionX() + float(std::cos(angle) * reach), start.GetPositionY() + float(std::sin(angle) * reach),
                                   start.GetPositionZ());
                double const radius = Tune("blood_rush_collision_yards");
                unsigned passed = 0;
                for (Unit* enemy : Combat::Enemies(player, spellId, start, reach + radius))
                    if (PassedThrough(start.GetPositionX(), start.GetPositionY(), end.GetPositionX(), end.GetPositionY(), enemy->GetPositionX(),
                                      enemy->GetPositionY(), radius))
                        ++passed;
                Heal(player, spellId, TransfusionHeal(player->GetMaxHealth(), Numbers::Num(spellId, "heal_pct"), passed));
                break;
            }
            case Rune::Molting:
                // "Leaves a corpse at your original location when used."
                Corpses::LeaveMade(player, start, 0);
                break;
            default:
                break;
        }
    }
} // namespace DC::Combat::Necromancer::BloodRush
