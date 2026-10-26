#include "dc_item_powers_internal.h"

// The item powers' `element` kind: Tal Rasha's Elements, the set's element buffs, window and Meteor.

namespace DC::Combat::ItemPowers
{
    namespace
    {
        // The place of `element` among ItemPower::SetElements, 4 for a name that is none of them.
        std::size_t ElementIndex(std::string const& element)
        {
            for (std::size_t at = 0; at < 4; ++at)
                if (element == ItemPower::SetElements[at])
                    return at;
            return 4;
        }
    } // namespace
} // namespace DC::Combat::ItemPowers

namespace DC::Combat
{
    namespace Detail
    {
        // The element name of a hit's school mask for the set's four elements, null for any other school.
        char const* ElementOfSchool(unsigned school)
        {
            switch (school)
            {
                case SPELL_SCHOOL_MASK_ARCANE:
                    return "arcane";
                case SPELL_SCHOOL_MASK_FROST:
                    return "cold";
                case SPELL_SCHOOL_MASK_FIRE:
                    return "fire";
                case SPELL_SCHOOL_MASK_NATURE:
                    return "lightning";
                default:
                    return nullptr;
            }
        }
    } // namespace Detail
} // namespace DC::Combat

namespace DC::Combat::ItemPowers
{
    namespace
    {
        DC::Element SheetElement(std::string const& element)
        {
            return element == "arcane" ? DC::Element::Arcane : element == "cold" ? DC::Element::Cold : element == "fire" ? DC::Element::Fire : DC::Element::Lightning;
        }

        // One of the set's buffs on or off the sheet.
        void ElementSheet(Player* player, Stat stat, Bucket bucket, std::uint64_t id, double value, DC::Element element, bool on)
        {
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            if (on)
                Stats::AddContribution(guid, {Source::Temporary, stat, id, value, bucket, element});
            else
                Stats::RemoveContribution(guid, Source::Temporary, stat, id);
            Stats::Recompute(player);
            Inventory::PushSheet(player);
        }
    } // namespace
} // namespace DC::Combat::ItemPowers

namespace DC::Combat
{
    namespace Detail
    {
        // An element's buff of the set (4-piece: +value percent on every resistance; 2-piece: immunity to the element) for `ms` from now, started again by
        // each attack of that element. `ends` is its clock in ElementState. It goes on the sheet when it starts and comes off when the clock has run out.
        void ElementBuff(Player* player, std::string const& element, std::map<std::string, std::uint32_t> ItemPower::ElementState::* ends, Stat stat,
                         Bucket bucket, std::uint64_t base, double value, std::uint32_t ms)
        {
            std::size_t const index = ElementIndex(element);
            if (index >= 4 || !ms)
                return;
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            DC::Element const sheet = stat == Stat::ElementReduction ? SheetElement(element) : DC::Element::Physical;
            bool starts;
            {
                std::lock_guard<std::mutex> lock(mutex);
                starts = ItemPower::Touch(clocks[guid].elements.*ends, element, getMSTime(), ms);
            }
            if (starts)
                ElementSheet(player, stat, bucket, base + index, value, sheet, true);
            player->m_Events.AddEventAtOffset([player, guid, element, ends, stat, bucket, base, index, sheet]
            {
                bool over;
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    auto mine = clocks.find(guid);
                    over = mine == clocks.end() || !ItemPower::Before(getMSTime(), (mine->second.elements.*ends)[element]);
                }
                if (over)
                    ElementSheet(player, stat, bucket, base + index, 0, sheet, false);
            }, Milliseconds(ms + 1));
        }

        // The 6-piece: an attack of `element` moves the window (ItemPower::WindowAttack); its numbers are the set's rows.
        void ElementWindowHit(Player* player, std::string const& element, ItemPower::Row const& row)
        {
            double const extend = ItemPower::OwnerNumber(Data().rows, row.owner, "player", "element_extend_seconds"),
                         most = ItemPower::OwnerNumber(Data().rows, row.owner, "player", "element_extend_max_seconds");
            std::lock_guard<std::mutex> lock(mutex);
            ItemPower::WindowAttack(clocks[player->GetGUID().GetRawValue()].elements, element, getMSTime(), row.stackSeconds, row.stackMax, extend, most);
        }

        // The 2-piece: with Meteor on the bar, and not twice in a row, a Meteor of the element falls where the attack landed and the player is
        // immune to that element for the tunable's seconds (blank: no number yet, no immunity).
        void ElementMeteor(Player* player, Unit* target, std::string const& element)
        {
            if (!target)
                return;
            bool const onBar = Wizard::MeteorOnBar(player);
            {
                std::lock_guard<std::mutex> lock(mutex);
                ItemPower::ElementState& state = clocks[player->GetGUID().GetRawValue()].elements;
                if (!ItemPower::MeteorDrops(state, element, onBar))
                    return;
                state.lastMeteor = element;
            }
            Wizard::CastMeteor(player, target, ItemPower::MeteorRune(element));
            double const seconds = DC::Tunables::Has("wizard", "tal_rashas_elements_immunity_seconds")
                ? DC::Tunables::Get("wizard", "tal_rashas_elements_immunity_seconds") : 0.0;
            ElementBuff(player, element, &ItemPower::ElementState::immuneUntil, Stat::ElementReduction, Bucket::Flat, ElementImmuneId, 100.0,
                        static_cast<std::uint32_t>(std::max(0.0, seconds) * 1000.0));
        }
    } // namespace Detail
} // namespace DC::Combat

namespace DC::Combat::ItemPowers
{
    void Prevent(Player* player, unsigned schoolMask, std::uint32_t& damage)
    {
        if (!player || !damage || !Data().prevents)
            return;
        char const* element = Detail::ElementOfSchool(schoolMask);
        if (!element)
            return;
        ItemPower::Prevented result;
        ItemPower::Situation seen = Seen(player);
        {
            std::lock_guard<std::mutex> lock(mutex);
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            result = ItemPower::PreventFor(Data().rows, CountsOf(guid), element, damage, SituationOf(guid, std::move(seen)));
        }
        damage = result.taken;
        // The heal is a stock heal record's, so the log names it (Greater Heal, rank 1).
        if (result.healed && player->IsAlive())
            if (SpellInfo const* info = sSpellMgr->GetSpellInfo(2060))
            {
                HealInfo healing(player, player, result.healed, info, SpellSchoolMask(info->SchoolMask));
                player->HealBySpell(healing, false);
            }
    }

    double ElementBonus(Player const* player, std::string const& element)
    {
        if (!player)
            return 0.0;
        ItemPower::Situation seen = Seen(player);
        std::lock_guard<std::mutex> lock(mutex);
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        return ItemPower::ElementSum(Data().rows, CountsOf(guid), element, "damage_pct", SituationOf(guid, std::move(seen)));
    }
} // namespace DC::Combat::ItemPowers
