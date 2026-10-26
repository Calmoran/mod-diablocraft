/*
 * Bone Spirit and its five runes. The engine hits the enemy aimed at; here: the skill stores charges (the cast spends one, a charge is
 * regained every period, and each corpse a skill consumes shortens the recharge), Possession charms the target at the cost of Life,
 * Panic Attack frightens the enemies around it, Unfinished Business explodes around it on top of the hit, Astral Projection adds damage for
 * each enemy on the spirit's way.
 */

#include "dc_necromancer_bone_spirit.h"
#include "dc_necromancer_bone_spirit_math.h"
#include "dc_necromancer_common.h"
#include "../../combat/dc_charge_store.h"
#include "../../combat/dc_charm_effect.h"
#include "../../combat/dc_corpses.h"

#include "GameTime.h"

#include <cmath>
#include <mutex>
#include <unordered_map>

namespace DC::Combat::Necromancer::BoneSpirit
{
    namespace
    {
        constexpr std::string_view Skill = "Bone Spirit";
        // A line attack is 3 yards wide (the standing default, AGENTS.md Numbers): the spirit's way.
        constexpr char const* WayWidth = "bone_spirit_way_yards";

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

        std::uint64_t Millis(double seconds)
        {
            return seconds > 0 ? std::uint64_t(seconds * 1000.0 + 0.5) : 0;
        }

        std::mutex mutex;
        std::unordered_map<std::uint64_t, ChargeStore> charges; // by Necromancer
        std::unordered_map<std::uint64_t, unsigned> passed;     // the enemies on the way of the spirit being cast, by Necromancer

        // The cap and the recharge of the record: Poltergeist's own cap, the rest inherit; the recharge is reduced as a cooldown is.
        unsigned Cap(std::uint32_t spellId)
        {
            return unsigned(Numbers::Num(spellId, "charge_count"));
        }

        std::uint64_t Period(Player* player, std::uint32_t spellId)
        {
            return ReducedCooldownMilliseconds(player, spellId, std::uint32_t(Millis(Numbers::Num(spellId, "charge_recharge_seconds"))));
        }

        // "Recharge time is reduced by {charge_recharge_reduction_seconds} second for each corpse you consume."
        void CorpsesConsumed(Player* owner, std::vector<Corpses::Spot> const& taken)
        {
            std::uint32_t const spellId = Slotted(owner, Skill);
            if (!spellId || taken.empty())
                return;
            std::uint64_t wait;
            {
                std::lock_guard<std::mutex> guard(mutex);
                wait = charges[owner->GetGUID().GetRawValue()].Shorten(
                    Now(), Cap(spellId), Period(owner, spellId),
                    Millis(Numbers::Num(spellId, "charge_recharge_reduction_seconds")) * taken.size());
            }
            SendSkillCooldown(owner, spellId, std::uint32_t(wait));
        }
    } // namespace

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        if (!RowOf(spellId, Skill))
            return std::nullopt;
        return KeepsTheSkillsHit(RuneAt(spellId)) ? std::optional<double>(Numbers::Get(BaseId(Skill), "damage_pct")) : std::nullopt;
    }

    void Casting(Player* player, std::uint32_t spellId)
    {
        if (!player || !RowOf(spellId, Skill))
            return;
        Rune const rune = RuneAt(spellId);
        // "at the cost of 5% health" (Possession).
        if (rune == Rune::Possession)
            SpendLife(player, Tune("possession_life_cost_pct"));
        if (rune != Rune::AstralProjection)
            return;
        unsigned count = 0;
        if (Unit* target = player->GetSelectedUnit())
            for (Unit* enemy : Combat::Enemies(player, spellId, player->GetPosition(), player->GetExactDist(target)))
                if (enemy != target && PassedThrough(player->GetPositionX(), player->GetPositionY(), target->GetPositionX(),
                                                     target->GetPositionY(), enemy->GetPositionX(), enemy->GetPositionY(), Tune(WayWidth)))
                    ++count;
        std::lock_guard<std::mutex> guard(mutex);
        passed[player->GetGUID().GetRawValue()] = count;
    }

    void Multipliers(Player* player, std::uint32_t spellId, DC::Combat::Factors& out)
    {
        if (!player || RuneAt(spellId) != Rune::AstralProjection)
            return;
        unsigned count;
        {
            std::lock_guard<std::mutex> guard(mutex);
            count = passed[player->GetGUID().GetRawValue()];
        }
        if (double const bonus = PassBonusPct(count, Numbers::Num(spellId, "damage_bonus_pct")))
            AddFactor(out, "Astral Projection", bonus);
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        if (!player || !RowOf(spellId, Skill))
            return;
        std::uint64_t wait;
        {
            std::lock_guard<std::mutex> guard(mutex);
            wait = charges[player->GetGUID().GetRawValue()].Spend(Now(), Cap(spellId), Period(player, spellId));
        }
        // The core put the record's cooldown on the button; a charge left clears it, none left holds it until the next lands.
        SendSkillCooldown(player, spellId, std::uint32_t(wait));
        if (targets.empty() || !targets.front())
            return;
        Unit* target = targets.front();
        switch (RuneAt(spellId))
        {
            case Rune::Possession:
                // "Bone Spirit will now charm the target for {charm_duration_seconds} seconds".
                CharmEffect::Apply(player, target, spellId, Numbers::Num(spellId, "charm_duration_seconds"));
                break;
            case Rune::PanicAttack:
                // "Enemies within {radius_yards} yards are feared for {fear_duration_seconds} seconds when Bone Spirit detonates."
                for (Unit* enemy : Combat::Enemies(player, spellId, target->GetPosition(), Numbers::Num(spellId, "radius_yards")))
                    Fear(player, enemy, Numbers::Num(spellId, "fear_duration_seconds"));
                break;
            case Rune::UnfinishedBusiness:
                // "explodes dealing {damage_pct} weapon damage as Cold to all enemies within {radius_yards} yards".
                for (Unit* enemy : Combat::Enemies(player, spellId, target->GetPosition(), Numbers::Num(spellId, "radius_yards")))
                    Combat::Strike(player, enemy, spellId, Numbers::Num(spellId, "damage_pct"));
                break;
            default:
                break;
        }
    }

    void RegisterScripts()
    {
        Corpses::OnConsumed(CorpsesConsumed);
    }
} // namespace DC::Combat::Necromancer::BoneSpirit
