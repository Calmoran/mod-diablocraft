#include "dc_item_powers_internal.h"
#include "dc_control_immunity.h"
#include "../common/dc_numeric_data.h"

// The item powers' readers: the number a skill, player or passive row of the worn items adds to what a hit or a cast reads.

namespace DC::Combat::ItemPowers
{
    double SkillFactor(Player const* player, std::string const& skill, std::string const& stat)
    {
        if (!player)
            return 1.0;
        ItemPower::Situation seen = Seen(player);
        std::lock_guard<std::mutex> lock(mutex);
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        return ItemPower::SkillFactor(Data().rows, CountsOf(guid), skill, stat, SituationOf(guid, std::move(seen)));
    }

    double MissingResourceFactor(Player const* player, std::string const& skill)
    {
        if (!player)
            return 1.0;
        ItemPower::Situation seen = Seen(player);
        std::lock_guard<std::mutex> lock(mutex);
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        return ItemPower::MissingResourceFactor(Data().rows, CountsOf(guid), skill, SituationOf(guid, std::move(seen)));
    }

    double DerivedFactor(Player const* player, std::string const& skill, DC::StatSheet const& sheet)
    {
        // Each `damage_per_<stat>_pct` skill stat and the sheet stat it is a share of; a new one is a pair here and a stat in the generator.
        static constexpr std::pair<char const*, Stat> Derived[] = {{"damage_per_movement_speed_pct", Stat::MovementSpeed}};
        if (!player)
            return 1.0;
        ItemPower::Situation seen = Seen(player);
        std::lock_guard<std::mutex> lock(mutex);
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        ItemPower::Situation const situation = SituationOf(guid, std::move(seen));
        double factor = 1.0;
        for (auto const& [stat, sheetStat] : Derived)
            factor *= ItemPower::DerivedFactor(Data().rows, CountsOf(guid), skill, stat, sheet[sheetStat], situation);
        return factor;
    }

    double PerStackFactor(Player const* player, std::string const& skill, std::string const& stat, double stacks)
    {
        if (!player || stacks <= 0)
            return 1.0;
        ItemPower::Situation seen = Seen(player);
        std::lock_guard<std::mutex> lock(mutex);
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        return ItemPower::PerStackFactor(Data().rows, CountsOf(guid), skill, stat, stacks, SituationOf(guid, std::move(seen)));
    }

    double EnemyStacks(Player const* player, std::string const& skill)
    {
        if (!player || !Data().enemyStacks)
            return 0.0;
        std::lock_guard<std::mutex> lock(mutex);
        auto mine = clocks.find(player->GetGUID().GetRawValue());
        if (mine == clocks.end())
            return 0.0;
        auto found = mine->second.enemyStacks.find(skill);
        return found == mine->second.enemyStacks.end() ? 0.0 : static_cast<double>(found->second.riding);
    }

    double ResourceSpend(Player const* player, std::string const& skill, double have)
    {
        if (!player)
            return 0.0;
        ItemPower::Situation seen = Seen(player);
        std::lock_guard<std::mutex> lock(mutex);
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        return ItemPower::ResourceSpend(Data().rows, CountsOf(guid), skill, have, SituationOf(guid, std::move(seen)));
    }

    double SpentFactor(Player const* player, std::string const& skill, double spent)
    {
        if (!player)
            return 1.0;
        ItemPower::Situation seen = Seen(player);
        std::lock_guard<std::mutex> lock(mutex);
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        return ItemPower::ResourceSpentFactor(Data().rows, CountsOf(guid), skill, spent, SituationOf(guid, std::move(seen)));
    }

    double DurationSeconds(Player const* player, std::string const& skill, double base)
    {
        if (!player)
            return base;
        ItemPower::Situation seen = Seen(player);
        std::lock_guard<std::mutex> lock(mutex);
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        return ItemPower::DurationSeconds(Data().rows, CountsOf(guid), skill, base, SituationOf(guid, std::move(seen)));
    }

    double ActiveCount(Player const* player, std::string const& skill, double base)
    {
        if (!player)
            return base;
        ItemPower::Situation seen = Seen(player);
        std::lock_guard<std::mutex> lock(mutex);
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        return ItemPower::ActiveCount(Data().rows, CountsOf(guid), skill, base, SituationOf(guid, std::move(seen)));
    }

    double SkillSetTo(Player const* player, std::string const& skill, std::string const& stat, double base)
    {
        if (!player)
            return base;
        ItemPower::Situation seen = Seen(player);
        std::lock_guard<std::mutex> lock(mutex);
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        return ItemPower::SkillSetTo(Data().rows, CountsOf(guid), skill, stat, base, SituationOf(guid, std::move(seen)));
    }

    double CooldownFactor(Player const* player, std::string const& skill)
    {
        if (!player)
            return 1.0;
        std::lock_guard<std::mutex> lock(mutex);
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        return ItemPower::CooldownFactor(Data().rows, CountsOf(guid), skill, SituationOf(guid));
    }

    double PassiveSetTo(Player const* player, std::string const& passive, std::string const& token, double base)
    {
        if (!player)
            return base;
        ItemPower::Situation seen = Seen(player);
        std::lock_guard<std::mutex> lock(mutex);
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        return ItemPower::PassiveSetTo(Data().rows, CountsOf(guid), passive, token, base, SituationOf(guid, std::move(seen)));
    }

    double SkillLowest(Player const* player, std::string const& skill, std::string const& stat, double base)
    {
        if (!player)
            return base;
        ItemPower::Situation seen = Seen(player);
        std::lock_guard<std::mutex> lock(mutex);
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        return ItemPower::SkillLowest(Data().rows, CountsOf(guid), skill, stat, base, SituationOf(guid, std::move(seen)));
    }

    bool GrantsRune(Player const* player, std::string const& skill, std::string const& rune)
    {
        if (!player)
            return false;
        ItemPower::Situation seen = Seen(player);
        std::lock_guard<std::mutex> lock(mutex);
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        return ItemPower::GrantsRune(Data().rows, CountsOf(guid), skill, rune, SituationOf(guid, std::move(seen)));
    }

    double PlayerFactor(Player const* player, std::string const& stat)
    {
        if (!player)
            return 1.0;
        ItemPower::Situation seen = Seen(player);
        std::lock_guard<std::mutex> lock(mutex);
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        return ItemPower::PlayerFactor(Data().rows, CountsOf(guid), stat, SituationOf(guid, std::move(seen)));
    }

    // N-STACKBUFF: the stacks of each owner's buff records on the player (the most of its records), read before the lock.
    std::map<std::string, unsigned> BuffStacks(Player const* player)
    {
        std::map<std::string, unsigned> out;
        for (Shells::PowerBuff const& buff : Shells::PowerBuffs)
            if (Aura const* aura = player->GetAura(buff.id))
                out[buff.owner] = std::max<unsigned>(out[buff.owner], aura->GetStackAmount());
        return out;
    }

    // N-DERIVED (Justice Lantern): the Block Chance a hit on the player meets now, in percent: the sheet's with what the worn items add, under the same total
    // cap Mitigate rolls it with. 0 for a player with no sheet. Read before the lock, as BlockBonus takes it.
    double BlockChanceNow(Player const* player)
    {
        auto const sheet = Stats::Get(player->GetGUID().GetRawValue());
        if (!sheet)
            return 0.0;
        double const bonus = BlockBonus(player);
        return ItemBlock::Chance((*sheet)[Stat::BlockChance], bonus, bonus > 0 ? NumericData::Block().totalChanceCap : 0.0);
    }

    double IncomingFactor(Player const* player)
    {
        if (!player)
            return 1.0;
        double const block = Data().blockReduction ? BlockChanceNow(player) : 0.0;
        std::map<std::string, unsigned> const stacks = BuffStacks(player);
        ItemPower::Situation seen = Seen(player);
        std::lock_guard<std::mutex> lock(mutex);
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        ItemPower::Situation const situation = SituationOf(guid, std::move(seen));
        return ItemPower::PlayerFactor(Data().rows, CountsOf(guid), "damage_taken_pct", situation) *
               ItemPower::ReductionFactor(Data().rows, CountsOf(guid), situation) *
               ItemPower::StackedFactor(Data().rows, CountsOf(guid), stacks, "damage_reduction_pct", -1.0, situation) *
               ItemPower::StunnedReduction(Data().rows, CountsOf(guid), situation) *
               ItemPower::BlockReductionFactor(Data().rows, CountsOf(guid), situation, block);
    }

    double TownPortalFactor(Player const* player)
    {
        if (!player)
            return 1.0;
        ItemPower::Situation seen = Seen(player);
        std::lock_guard<std::mutex> lock(mutex);
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        return ItemPower::PortalBubbleFactor(Data().rows, CountsOf(guid), SituationOf(guid, std::move(seen)));
    }

    double DealtFactor(Player const* player)
    {
        if (!player)
            return 1.0;
        std::map<std::string, unsigned> const stacks = BuffStacks(player);
        ItemPower::Situation seen = Seen(player);
        std::lock_guard<std::mutex> lock(mutex);
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        ItemPower::Situation const situation = SituationOf(guid, std::move(seen));
        return ItemPower::PlayerFactor(Data().rows, CountsOf(guid), "damage_dealt_pct", situation) *
               ItemPower::StackedFactor(Data().rows, CountsOf(guid), stacks, "damage_dealt_pct", 1.0, situation);
    }

    double DamageBonus(Player const* player)
    {
        if (!player)
            return 0.0;
        ItemPower::Situation seen = Seen(player);
        std::lock_guard<std::mutex> lock(mutex);
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        return ItemPower::GenerationDamagePct(Data().rows, CountsOf(guid), SituationOf(guid, std::move(seen)));
    }

    double GenerationFactor(Player const* player)
    {
        if (!player)
            return 1.0;
        ItemPower::Situation seen = Seen(player);
        std::lock_guard<std::mutex> lock(mutex);
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        return ItemPower::GenerationFactor(Data().rows, CountsOf(guid), SituationOf(guid, std::move(seen)));
    }

    double StackedSkillFactor(Player const* player, std::string const& skill)
    {
        if (!player)
            return 1.0;
        std::map<std::string, unsigned> const stacks = BuffStacks(player);
        ItemPower::Situation seen = Seen(player);
        std::lock_guard<std::mutex> lock(mutex);
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        return ItemPower::StackedFactor(Data().rows, CountsOf(guid), stacks, "skill_damage_pct", 1.0, SituationOf(guid, std::move(seen)), skill);
    }

    double ShrineSeconds(Player const* player, double base)
    {
        if (!player)
            return base;
        ItemPower::Situation seen = Seen(player);
        std::lock_guard<std::mutex> lock(mutex);
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        return ItemPower::PlayerSetTo(Data().rows, CountsOf(guid), "shrine_seconds", base, SituationOf(guid, std::move(seen)));
    }

    double PetSpeedFactor(Player const* player)
    {
        return PlayerFactor(player, "pet_attack_speed_pct");
    }

    double StunFactor(Player const* player)
    {
        return PlayerFactor(player, "stun_duration_pct");
    }

    double ShieldFactor(Player const* player)
    {
        return PlayerFactor(player, "shield_potency_pct");
    }

    double DeathsBreathFactor(Player const* player)
    {
        return PlayerFactor(player, "deaths_breath_pct");
    }

    double KeystoneFactor(Player const* player)
    {
        return PlayerFactor(player, "extra_keystone_pct");
    }

    double CritBonus(Player const* player, Unit const* target)
    {
        if (!player || !target)
            return 0.0;
        // The target's Life is read before the lock, as DistanceFactor reads the yards; a target with no maximum gives no percent (-1: no row holds).
        double const life = target->GetMaxHealth() ? 100.0 * target->GetHealth() / target->GetMaxHealth() : -1.0;
        ItemPower::Situation seen = Seen(player);
        std::lock_guard<std::mutex> lock(mutex);
        seen.targetLifePct = life;
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        return ItemPower::PlayerSum(Data().rows, CountsOf(guid), "crit_chance_pct", SituationOf(guid, std::move(seen)));
    }

    double BlockBonus(Player const* player)
    {
        if (!player)
            return 0.0;
        ItemPower::Situation seen = Seen(player);
        std::lock_guard<std::mutex> lock(mutex);
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        return ItemPower::PlayerSum(Data().rows, CountsOf(guid), "block_chance_pct", SituationOf(guid, std::move(seen)));
    }

    double BlockedFactor(Player const* player)
    {
        if (!player)
            return 1.0;
        ItemPower::Situation seen = Seen(player);
        std::lock_guard<std::mutex> lock(mutex);
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        return ItemPower::CutFactor(Data().rows, CountsOf(guid), "blocked_damage_cut_pct", SituationOf(guid, std::move(seen)));
    }

    double NextAttackFactor(Player const* player, std::string const& skill)
    {
        if (!player)
            return 1.0;
        // Every hit of every player passes here: nothing to look at unless some row arms an attack.
        if (!Data().events.count("block"))
            return 1.0;
        double const armed = ArmedPct(player);
        std::lock_guard<std::mutex> lock(mutex);
        auto mine = clocks.find(player->GetGUID().GetRawValue());
        return ItemBlock::NextAttackFactor(armed, mine == clocks.end() ? ItemBlock::Spent{} : mine->second.nextSpent, skill);
    }

    double DistanceFactor(Player const* player, Unit const* target, std::string const& element)
    {
        if (!player || !target)
            return 1.0;
        // The distance is read the way Power Hungry reads it (Wizard::Standalone), before the lock.
        double const distance = player->GetDistance(target);
        ItemPower::Situation seen = Seen(player);
        std::lock_guard<std::mutex> lock(mutex);
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        return ItemPower::DistanceFactor(Data().rows, CountsOf(guid), element, distance, SituationOf(guid, std::move(seen)));
    }

    double TargetFactor(Player const* player, Unit const* target, std::string const& skill)
    {
        if (!player || !target)
            return 1.0;
        // The target's states, read before the lock. A Chill here is a slow aura (Wizard::Chill, the gems' Iceblink: no slow, no Chill), so the
        // strongest slow on the target below 0 holds both "Slowed" and "Chilled".
        unsigned const states = target->GetMaxNegativeAuraModifier(SPELL_AURA_MOD_DECREASE_SPEED) < 0 ? ItemPower::TargetSlowed : 0u;
        ItemPower::Situation seen = Seen(player);
        std::lock_guard<std::mutex> lock(mutex);
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        ItemPower::Situation situation = SituationOf(guid, std::move(seen));
        situation.targetControl = states;
        return ItemPower::TargetFactor(Data().rows, CountsOf(guid), skill, situation);
    }

    double ImpairedFactor(Player const* player, Unit const* target)
    {
        // Every hit of every player passes here: nothing to look at unless some row cuts by the target's control state.
        if (!player || !target || !Data().impaired)
            return 1.0;
        // The target's states, read before the lock: a slow is the strongest slow aura below 0 (a Chill is one), and any other control-impairing
        // mechanic is the one the bonus is tripled against.
        unsigned held = target->GetMaxNegativeAuraModifier(SPELL_AURA_MOD_DECREASE_SPEED) != 0.0f ? ItemPower::TargetSlowed : 0u;
        if (ControlImmunity::ImpairedBesidesSlow(target))
            held |= ItemPower::TargetControlled;
        ItemPower::Situation seen = Seen(player);
        std::lock_guard<std::mutex> lock(mutex);
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        ItemPower::Situation situation = SituationOf(guid, std::move(seen));
        situation.targetControl = held;
        return ItemPower::ImpairedFactor(Data().rows, CountsOf(guid), situation);
    }

    double AttackSpeedFactor(Player* player)
    {
        double factor = 1.0;
        if (player)
            for (Shells::PowerBuff const& buff : Shells::PowerBuffs)
                if (std::string(buff.stat) == "movement_speed_pct")
                    if (Aura const* slow = player->GetAura(buff.id))
                        factor *= ItemPower::StackedSpeedFactor(Data().rows, buff.owner, slow->GetStackAmount());
        return factor;
    }
} // namespace DC::Combat::ItemPowers
