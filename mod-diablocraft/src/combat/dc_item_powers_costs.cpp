#include "dc_item_powers_internal.h"
#include "dc_cost_cut.h"

// The item powers' cost kinds: the hidden element and skill cost auras, and the window of free abilities.

namespace DC::Combat::ItemPowers
{
    namespace
    {
        // The end of a window of free abilities (OpenCostFree's event): the sheet's 100% comes off and the gear cost aura is rebuilt, unless a
        // later window moved the end (its own event closes it).
        void CloseCostFree(Player* player, std::uint32_t end)
        {
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            {
                std::lock_guard<std::mutex> lock(mutex);
                auto at = costFree.find(guid);
                if (at == costFree.end() || at->second != end)
                    return;
                costFree.erase(at);
            }
            Stats::RemoveContribution(guid, Source::Temporary, Stat::ResourceCostReduction, CostFreeId);
            Passives::RefreshModifiers(player);
        }
    } // namespace
} // namespace DC::Combat::ItemPowers

namespace DC::Combat
{
    namespace Detail
    {
        // N-COST (Kekegi's Unbreakable Spirit): a fired `cost_free_seconds` row, every ability costs nothing for `seconds`.
        // The core charges a skill's cost from its record through the class's gear cost aura, which is rebuilt from the sheet's Resource Cost
        // Reduction (Passives::RefreshModifiers), so the window is a Temporary 100% there (the Mantras, every rune; the sheet shows 100 while it
        // is open). A cost the module charges itself reads CostFree (Tempest Rush's ticks). The end runs on the player's own event queue.
        void OpenCostFree(Player* player, double seconds)
        {
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            std::uint32_t const now = getMSTime();
            std::uint32_t end = 0;
            bool opened = false;
            {
                std::lock_guard<std::mutex> lock(mutex);
                std::uint32_t& until = costFree[guid];
                opened = !ItemPower::CostFreeAt(until, now);
                end = until = ItemPower::CostFreeEnd(until, now, seconds);
            }
            if (opened)
            {
                Stats::AddContribution(guid, {Source::Temporary, Stat::ResourceCostReduction, CostFreeId, 100.0, Bucket::Flat});
                Passives::RefreshModifiers(player);
            }
            player->m_Events.AddEventAtOffset([player, end] { CloseCostFree(player, end); }, Milliseconds(end - now));
        }
    } // namespace Detail
} // namespace DC::Combat

namespace DC::Combat::ItemPowers
{
    void FreeAbilities(Player* player, double seconds)
    {
        if (player && seconds > 0)
            Detail::OpenCostFree(player, seconds);
    }

    namespace
    {
        // Puts each cost aura of one element the player's class has (Shells::ElementCostModifiers) at what the `element` rows of
        // `cost_reduction_pct` that are on add up to (Cindercoat): the core's SPELLMOD_COST over the records of that
        // element, so the core charges the cut, beside the other reductions. Those rows have no condition (the generator refuses one), so
        // only a change of the worn items or set counts changes it (Refresh).
        void PutCostAmount(Player* player, std::uint32_t id, std::int32_t amount);

        // One hidden cost aura at `pct` percent off: recast when its amount changes, removed at 0.
        void PutCostAura(Player* player, std::uint32_t id, double pct)
        {
            PutCostAmount(player, id, CostMath::ModifierAmount(pct));
        }

        // The same at `amount`, a negative whole percent (a reduction) or a flat cost added (N-COST, Aether Walker): recast when it changes, removed at 0.
        void PutCostAmount(Player* player, std::uint32_t id, std::int32_t amount)
        {
            Aura* current = player->GetAura(id);
            AuraEffect const* effect = current ? current->GetEffect(EFFECT_0) : nullptr;
            if (effect ? effect->GetAmount() == amount : amount == 0)
                return;
            if (current)
                player->RemoveAurasDueToSpell(id);
            if (amount != 0)
                player->CastCustomSpell(player, id, &amount, nullptr, nullptr, true);
        }
    } // namespace
} // namespace DC::Combat::ItemPowers

namespace DC::Combat
{
    namespace Detail
    {
        // The same for one skill (N-COST, Fury of the Vanished Peak): each skill cost aura (Shells::SkillCostModifiers, the skill's
        // own records in its class's family) at what the `skill` rows of `cost_reduction_pct` that are on add up to for it.
        void CostAuras(Player* player)
        {
            std::uint32_t const classId = Classes::ClassIdOf(player);
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            for (Shells::ElementCostModifier const& row : Shells::ElementCostModifiers)
            {
                if (row.classId != classId)
                    continue;
                double pct;
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    pct = ItemPower::ElementSum(Data().rows, CountsOf(guid), row.element, "cost_reduction_pct", SituationOf(guid));
                }
                PutCostAura(player, row.id, pct);
            }
            for (Shells::SkillCostModifier const& row : Shells::SkillCostModifiers)
            {
                double pct;
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    pct = ItemPower::SkillSum(Data().rows, CountsOf(guid), row.skill, "cost_reduction_pct", SituationOf(guid));
                }
                // The cuts a rune or a passive gives the skill for a time (CostCut) multiply with the worn items'.
                pct = CostCut::Combine(pct, CostCut::Pct(player, row.skill));
                PutCostAura(player, row.id, pct);
            }
            // N-COST (Aether Walker): a cost put on a skill that has none, the `cost_add_resource` rows that are on added up, in the units of the
            // wearer's class resource (a flat SPELLMOD_COST amount the core adds to the record's cost, so it charges it and refuses an unpaid cast).
            Resources::Resource const* resource = Resources::Of(classId);
            for (Shells::SkillCostAdder const& row : Shells::SkillCostAdders)
            {
                double points;
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    points = ItemPower::SkillSum(Data().rows, CountsOf(guid), row.skill, "cost_add_resource", SituationOf(guid));
                }
                PutCostAmount(player, row.id, resource ? CostMath::FlatAmount(points, resource->scale) : 0);
            }
        }
    } // namespace Detail
} // namespace DC::Combat

namespace DC::Combat::ItemPowers
{
    void RefreshCostAuras(Player* player)
    {
        if (player)
            Detail::CostAuras(player);
    }

    bool CostFree(Player const* player)
    {
        if (!player)
            return false;
        std::lock_guard<std::mutex> lock(mutex);
        auto at = costFree.find(player->GetGUID().GetRawValue());
        return at != costFree.end() && ItemPower::CostFreeAt(at->second, getMSTime());
    }
} // namespace DC::Combat::ItemPowers
