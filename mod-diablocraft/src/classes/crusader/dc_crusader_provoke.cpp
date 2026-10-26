/*
 * Provoke and its five runes: the shout that makes the enemies around attack the Crusader (or flee, for Flee Fool), the
 * Wrath it pays for each, and what each rune does with the enemies it took hold of. The dispatch is in dc_crusader.cpp.
 */

#include "dc_crusader_provoke.h"
#include "../dc_level_heal.h"
#include "dc_crusader_common.h"

#include <algorithm>

namespace DC::Combat::Crusader::Provoke
{
    namespace
    {
        constexpr std::string_view Skill = "Provoke";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        // The Charged Up each Crusader wears now: the rune's spell and when its time is over.
        struct Charge
        {
            std::uint32_t spellId;
            std::uint64_t until;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, Charge> charged;
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        if (!Is(spellId))
            return std::nullopt;
        return 0.0;
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        if (!player || !Is(spellId))
            return;
        Rune const rune = RuneAt(spellId);
        // "Taunted enemies will focus their attention on you for {duration_seconds} seconds": the skill's number, which
        // a rune's own `duration_seconds` (the time of its bonus) does not replace.
        double const taunt = Numbers::Num(BaseId(Skill), "duration_seconds");
        std::vector<Unit*> held;
        for (Unit* enemy : targets)
            if (enemy->IsAlive() && (Frightens(rune) ? Fear(player, enemy, Numbers::Num(spellId, "fear_duration_seconds"))
                                                     : Taunt(player, enemy, taunt)))
                held.push_back(enemy);
        PayWrath(player, spellId,
                 WrathFor(Numbers::Num(spellId, "generated_resource", "base"),
                          Numbers::Num(spellId, "generated_resource", "per_enemy"), unsigned(held.size())));

        switch (rune)
        {
            case Rune::Cleanse:
                if (unsigned const stacks = CleanseStacks(rune, unsigned(held.size())))
                    Buffs::Stack(player, spellId, Stat::LifePerHit, Bucket::Flat,
                                 Classes::HealAtLevel(Numbers::Num(spellId, "heal_per_hit_life"), player->GetLevel()), stacks,
                                 Numbers::Num(spellId, "duration_seconds"), stacks);
                break;
            case Rune::TooScaredToRun:
                // "attack speed reduced by {attack_speed_pct} and movement speed Slowed by {slow_pct} for
                // {slow_duration_seconds} seconds."
                for (Unit* enemy : held)
                {
                    Slow(player, enemy, Numbers::Num(spellId, "slow_pct"),
                         Numbers::Num(spellId, "slow_duration_seconds"));
                    Weary(player, enemy, Numbers::Num(spellId, "attack_speed_pct"),
                          Numbers::Num(spellId, "slow_duration_seconds"));
                }
                break;
            case Rune::ChargedUp:
            {
                std::uint64_t const until = Now() + std::uint64_t(Numbers::Num(spellId, "duration_seconds") * 1000.0);
                std::lock_guard<std::mutex> guard(mutex);
                charged[player->GetGUID().GetRawValue()] = {spellId, until};
                break;
            }
            case Rune::HitMe:
                // "Gain {block_pct} increased Block Chance for {duration_seconds} seconds."
                Buffs::Stack(player, spellId, Stat::BlockChance, Bucket::Flat, Numbers::Num(spellId, "block_pct"), 1,
                             Numbers::Num(spellId, "duration_seconds"));
                break;
            default:
                break;
        }
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId)
    {
        if (!player || !target)
            return;
        std::uint32_t rider = 0;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = charged.find(player->GetGUID().GetRawValue());
            if (found == charged.end())
                return;
            if (!Charged(Now(), found->second.until))
            {
                charged.erase(found);
                return;
            }
            rider = found->second.spellId;
        }
        // "any damage you deal will also deal {damage_pct} weapon damage as Lightning": the rune's own shell, which is
        // the Lightning one; its own hit lands here too and owes nothing.
        double const pct = RiderPct(RuneAt(rider), true, Is(spellId), Numbers::Own(rider, "damage_pct").value_or(0.0));
        if (pct > 0)
            Combat::Strike(player, target, rider, pct);
    }
} // namespace DC::Combat::Crusader::Provoke
