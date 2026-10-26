/*
 * Punish and its five runes: Hardened Senses, and what each rune does when the Crusader blocks with it active. The
 * dispatch is in dc_crusader.cpp.
 */

#include "dc_crusader_punish.h"
#include "dc_crusader_common.h"
#include "../dc_level_heal.h"

namespace DC::Combat::Crusader::Punish
{
    namespace
    {
        constexpr std::string_view Skill = "Punish";

        // Per Crusader: Fury waiting for the next attack.
        std::mutex mutex;
        std::unordered_map<std::uint64_t, std::uint32_t> furyArmed; // guid -> the Fury rune's spell
        // The answer a block gives is itself a hit that lands on the attacker; it must not answer a block again.
        thread_local bool answering = false;

        // Hardened Senses is held by the skill's own record: its block_pct for its duration_seconds, one stack.
        std::uint32_t SensesId()
        {
            return BaseId(Skill);
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        if (!Is(spellId))
            return std::nullopt;
        return Numbers::Get(SensesId(), "damage_pct");
    }

    void Connected(Player* player, std::uint32_t spellId)
    {
        if (!player)
            return;
        // Fury is for the next attack, whichever skill throws it: the hit it was added to has been dealt.
        {
            std::lock_guard<std::mutex> guard(mutex);
            furyArmed.erase(player->GetGUID().GetRawValue());
        }
        if (!Is(spellId))
            return;
        std::uint32_t const base = SensesId();
        Buffs::Stack(player, base, Stat::BlockChance, Bucket::Flat, Numbers::Num(base, "block_pct"), 1,
                     Numbers::Num(base, "duration_seconds"));
    }

    void Blocked(Player* player, Unit* attacker)
    {
        if (answering || !player)
            return;
        std::uint32_t const spellId = Slotted(player, Skill);
        if (!spellId || !Buffs::Stacks(player, SensesId(), Stat::BlockChance))
            return;
        switch (AnswerOf(Shells::FindAbility(spellId)->rune))
        {
            case Answer::Retaliate:
                if (attacker && attacker != player && attacker->IsAlive())
                {
                    answering = true;
                    Combat::Strike(player, attacker, spellId, Numbers::Own(spellId, "damage_pct"));
                    answering = false;
                }
                break;
            case Answer::Celerity:
                Buffs::Stack(player, spellId, Stat::AttackSpeed, Bucket::Flat, Numbers::Num(spellId, "attack_speed_pct"),
                             1, Numbers::Num(spellId, "duration_seconds"));
                break;
            case Answer::Rebirth:
                // The Life regeneration is D3's Healing table at the Crusader's level, as the power file builds it.
                Buffs::Stack(player, spellId, Stat::LifeRegen, Bucket::Flat,
                             Classes::HealAtLevel(Numbers::Num(spellId, "heal_per_second_life"), player->GetLevel()), 1,
                             Numbers::Num(spellId, "duration_seconds"));
                break;
            case Answer::Roar:
            {
                answering = true;
                auto const pct = Numbers::Own(spellId, "damage_pct");
                for (Unit* enemy : Combat::Enemies(player, spellId, player->GetPosition(),
                                                   Numbers::Num(spellId, "radius_yards")))
                    Combat::Strike(player, enemy, spellId, pct);
                answering = false;
                break;
            }
            case Answer::Fury:
            {
                std::lock_guard<std::mutex> guard(mutex);
                furyArmed[player->GetGUID().GetRawValue()] = spellId;
                break;
            }
            case Answer::None:
                break;
        }
    }

    double CritBonus(Player* player, std::uint32_t)
    {
        if (!player)
            return 0.0;
        std::uint32_t armedBy = 0;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = furyArmed.find(player->GetGUID().GetRawValue());
            if (found != furyArmed.end())
                armedBy = found->second;
        }
        return FuryCrit(armedBy != 0, armedBy ? Numbers::Num(armedBy, "crit_chance_pct") : 0.0);
    }
} // namespace DC::Combat::Crusader::Punish
