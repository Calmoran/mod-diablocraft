#include "dc_item_powers_internal.h"

// The item powers' `buff` kind: the stacking and marking buff records, the armed next attack, and what goes when the item does.

namespace DC::Combat::ItemPowers
{
    namespace
    {
        // The sheet's Armor from the stacking buffs (Stone Gauntlets): each `armor_pct` buff record on the player
        // gives its `buff` row's number per stack, a Percent of Armor beside the other armor percents (docs/research/stone-gauntlets.md
        // section 2b). `leaving` is a record going off now (the remove hook runs while the unit still holds it): it counts none.
        void StackSheet(Player* player, std::uint32_t leaving = 0)
        {
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            for (Shells::PowerBuff const& buff : Shells::PowerBuffs)
            {
                if (std::string(buff.stat) != "armor_pct")
                    continue;
                Aura const* aura = buff.id == leaving ? nullptr : player->GetAura(buff.id);
                double const pct = aura ? aura->GetStackAmount() * ItemPower::BuffValue(Data().rows, buff.owner, buff.stat) : 0;
                Stats::RemoveContribution(guid, Source::Temporary, Stat::Armor, buff.id);
                if (pct > 0)
                    Stats::AddContribution(guid, {Source::Temporary, Stat::Armor, buff.id, pct, Bucket::Percent});
            }
            Stats::Recompute(player);
            Inventory::PushSheet(player);
        }

        // A `stack_buff` row fired: each buff record of its owner gains `add` stacks, at most the row's stack_max, and all start their
        // stack_seconds again, one timer. The slow is refused while the player is immune to control (AddAura answers nothing) and
        // control immunity coming on takes it off (its Snare mechanic): the armor stays. The sheet is only redone when
        // the armor's stacks changed.
        // Binding of the Lost: its cap is the tunable monk.binding_of_the_lost_max_stacks, the row's stack_max while it is unset; every
        // other stacking power's cap is its row's. An aura holds at most 255 stacks.
        unsigned StackCap(ItemPower::Row const& row)
        {
            if (row.owner == "P61_Unique_Belt_03" && DC::Tunables::Has("monk", "binding_of_the_lost_max_stacks"))
                return static_cast<unsigned>(std::clamp(DC::Tunables::Get("monk", "binding_of_the_lost_max_stacks"), 0.0, 255.0));
            return row.stackMax;
        }
    } // namespace
} // namespace DC::Combat::ItemPowers

namespace DC::Combat
{
    namespace Detail
    {
        void StackBuff(Player* player, ItemPower::Row const& row, double add)
        {
            std::int32_t const ms = static_cast<std::int32_t>(row.stackSeconds * 1000.0);
            bool armor = false;
            for (Shells::PowerBuff const& buff : Shells::PowerBuffs)
            {
                if (row.owner != buff.owner)
                    continue;
                Aura* aura = player->GetAura(buff.id);
                unsigned const held = aura ? aura->GetStackAmount() : 0;
                if (!aura)
                    aura = player->AddAura(buff.id, player);
                if (!aura)
                    continue;
                unsigned const stacks = ItemPower::Stacked(held, add, StackCap(row));
                if (aura->GetStackAmount() != stacks)
                    aura->SetStackAmount(static_cast<std::uint8_t>(stacks));
                aura->SetMaxDuration(ms);
                aura->SetDuration(ms);
                armor = armor || (std::string(buff.stat) == "armor_pct" && held != stacks);
            }
            if (armor)
                StackSheet(player);
        }

        // A `mark_enemy` row fired (Bindings of the Lesser Gods): the hit's target takes the owner's mark record, cast by the
        // player, for the row's stack_seconds, holding the rolled percent in its effect amount (a mark of this player's already there is
        // renewed). Unit::AddAura makes the player the caster, which MarkFactor reads.
        void MarkEnemy(Player* player, Unit* target, ItemPower::Row const& row, double pct)
        {
            std::uint32_t const id = Shells::PowerBuffFor(row.owner.c_str(), row.stat.c_str());
            if (!id || !target->IsAlive())
                return;
            Aura* aura = target->GetAura(id, player->GetGUID());
            if (!aura)
                aura = player->AddAura(id, target);
            if (!aura)
                return;
            if (AuraEffect* effect = aura->GetEffect(0))
                effect->ChangeAmount(static_cast<std::int32_t>(pct));
            std::int32_t const ms = static_cast<std::int32_t>(row.stackSeconds * 1000.0);
            aura->SetMaxDuration(ms);
            aura->SetDuration(ms);
        }

        // Blood Brother, a `next_attack_pct` row fired by a block: the owner's record goes on the player holding the item's percent in its
        // effect amount, until the next attack that connects spends it (NextAttackConnected). The record is the player's state: a bonus already
        // armed keeps the larger of the two (ItemBlock::Arm), and death or a GM's unaura takes it off.
        void ArmNextAttack(Player* player, std::string const& owner, double pct)
        {
            std::uint32_t const id = Shells::PowerBuffFor(owner.c_str(), "next_attack_pct");
            if (!id || pct <= 0)
                return;
            Aura* aura = player->GetAura(id);
            if (!aura)
                aura = player->AddAura(id, player);
            AuraEffect* effect = aura ? aura->GetEffect(0) : nullptr;
            if (!effect)
                return;
            effect->ChangeAmount(static_cast<std::int32_t>(ItemBlock::Arm(std::max(0, effect->GetAmount()), pct)));
        }

        // The percent the player's armed next-attack record holds now, 0 when none is up.
        double ArmedPct(Player const* player)
        {
            for (Shells::PowerBuff const& buff : Shells::PowerBuffs)
                if (std::string(buff.stat) == "next_attack_pct")
                    if (Aura const* aura = player->GetAura(buff.id))
                        if (AuraEffect const* effect = aura->GetEffect(0))
                            return effect->GetAmount() > 0 ? effect->GetAmount() : 0.0;
            return 0.0;
        }
    } // namespace Detail
} // namespace DC::Combat

namespace DC::Combat::ItemPowers
{
    namespace
    {
        // Takes the armed record off the player (the attack spent it, or the item that owns it is no longer worn).
        void DisarmNextAttack(Player* player)
        {
            for (Shells::PowerBuff const& buff : Shells::PowerBuffs)
                if (std::string(buff.stat) == "next_attack_pct")
                    player->RemoveAurasDueToSpell(buff.id);
        }
    } // namespace
} // namespace DC::Combat::ItemPowers

namespace DC::Combat
{
    namespace Detail
    {
        // An attack of `spellId` connected (Combat::Connected, ItemPowers::Attack): an armed bonus is spent on it and rides the rest of that
        // cast, the hits that come after this first one connected (ItemBlock::Connect). Nothing armed: the cast keeps what it had.
        void NextAttackConnected(Player* player, std::uint32_t spellId)
        {
            // Every connected attack of every player passes here: nothing to spend unless some row arms an attack.
            if (!Data().events.count("block"))
                return;
            auto const skill = Shells::FindAbility(spellId);
            double const armed = skill ? ArmedPct(player) : 0.0;
            if (armed <= 0)
                return;
            {
                std::lock_guard<std::mutex> lock(mutex);
                ItemBlock::Spent& spent = clocks[player->GetGUID().GetRawValue()].nextSpent;
                spent = ItemBlock::Connect(armed, spent, skill->skill);
            }
            DisarmNextAttack(player);
        }

        // A skill was pressed (ItemPowers::Cast): the attack before it is over, so the bonus that attack spent is gone (ItemBlock::Press).
        void NextAttackPressed(Player* player)
        {
            std::lock_guard<std::mutex> lock(mutex);
            if (auto mine = clocks.find(player->GetGUID().GetRawValue()); mine != clocks.end())
                mine->second.nextSpent = ItemBlock::Press(mine->second.nextSpent);
        }

        // Takes off the stacking buffs of an item no longer worn or broken (Stone Gauntlets): its armor and slow end with it (the remove
        // hook takes the armor off the sheet).
        void DropStacks(Player* player)
        {
            std::set<std::string> on;
            {
                std::lock_guard<std::mutex> lock(mutex);
                for (auto const& [id, since] : clocks[player->GetGUID().GetRawValue()].wornSince)
                    on.insert(id);
                for (ItemPower::Cubed const& one : CubedOf(player->GetGUID().GetRawValue()))
                    on.insert(one.id);
            }
            for (Shells::PowerBuff const& buff : Shells::PowerBuffs)
                if (!on.count(buff.owner) && ItemPower::BuffValue(Data().rows, buff.owner, buff.stat) != 0)
                    player->RemoveAurasDueToSpell(buff.id);
            // Blood Brother: the armed next attack, and the cast still carrying a spent one, go with the item (worn or cubed).
            bool arms = false;
            for (ItemPower::Row const& row : Data().rows)
                arms = arms || (row.stat == "next_attack_pct" && on.count(row.owner));
            if (!arms)
            {
                DisarmNextAttack(player);
                std::lock_guard<std::mutex> lock(mutex);
                clocks[player->GetGUID().GetRawValue()].nextSpent = {};
            }
            // Arreat's Law: the extra resource maximum goes with the item (worn or cubed).
            bool owned = false;
            for (ItemPower::Row const& row : Data().rows)
                owned = owned || (row.stat == "resource_over_cap" && on.count(row.owner));
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            bool off;
            {
                std::lock_guard<std::mutex> lock(mutex);
                off = !owned && raised.erase(guid) != 0;
            }
            if (off)
            {
                Stats::RemoveContribution(guid, Source::Temporary, Stat::MaxFury, OverCapId);
                Stats::Recompute(player);
            }
        }
    } // namespace Detail
} // namespace DC::Combat

namespace DC::Combat::ItemPowers
{
    namespace
    {
        // A stacking buff's armor record going off (its seconds ran out, death, DropStacks, a GM's unaura) takes its Armor off the sheet.
        class StackEnds final : public UnitScript
        {
        public:
            StackEnds() : UnitScript("dc_item_power_stack_ends", true, {UNITHOOK_ON_AURA_REMOVE}) { }
            void OnAuraRemove(Unit* unit, AuraApplication* application, AuraRemoveMode) override
            {
                Player* player = unit ? unit->ToPlayer() : nullptr;
                if (!player || !application)
                    return;
                std::uint32_t const id = application->GetBase()->GetId();
                for (Shells::PowerBuff const& buff : Shells::PowerBuffs)
                    if (buff.id == id && std::string(buff.stat) == "armor_pct")
                        StackSheet(player, id);
            }
        };
    } // namespace
} // namespace DC::Combat::ItemPowers

namespace DC::Combat::ItemPowers
{
    double MarkFactor(Player const* player, Unit const* target, std::string const& skill, bool split)
    {
        if (!player || !target)
            return 1.0;
        double factor = 1.0;
        for (Shells::PowerBuff const& buff : Shells::PowerBuffs)
        {
            if (std::string(buff.stat) != "mark_enemy")
                continue;
            Aura const* mark = target->GetAura(buff.id, player->GetGUID());
            AuraEffect const* effect = mark ? mark->GetEffect(0) : nullptr;
            if (!effect)
                continue;
            bool marked = false;
            for (ItemPower::Row const& row : Data().rows)
                marked = marked || (row.kind == "effect" && row.stat == "mark_enemy" && row.owner == buff.owner && row.skill == skill);
            double const times = split ? SkillSetTo(player, skill, "mark_split_factor", 1.0) : 1.0;
            if (marked)
                factor *= ItemPower::MarkFactor(effect->GetAmount(), times);
        }
        return factor;
    }
} // namespace DC::Combat::ItemPowers

namespace DC::Combat
{
    namespace Detail
    {
        void RegisterBuffScripts()
        {
            new StackEnds();
        }
    } // namespace Detail
} // namespace DC::Combat
