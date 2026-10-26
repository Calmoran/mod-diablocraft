// Items: the item side of the Mystic's enchant (which line may become what, and the offers).
#include "dc_items_internal.h"

#include "dc_enchant_rule.h"
#include "dc_granted_passive_rule.h"
#include "dc_roll_class.h"

#include "Player.h"

#include <algorithm>
#include <mutex>
#include <random>
#include <string>
#include <vector>

namespace DC::Items
{
using namespace Detail;

namespace
{
// What dc_enchant_rule.h needs from this file - the item's base, the player's class,
// the pools and the draws. The caller holds dataMutex.
struct MysticCtx
{
    BaseItem const* base = nullptr;
    std::string mysticClass, weaponClass;
    bool atTop = false; // a Primal: every value the Mystic offers is the top of its range

    // The pool id a row belongs to: every main stat is "mainstat", a skill choice is its group.
    std::string PoolId(std::string const& id) const
    {
        if (id == "str" || id == "dex" || id == "int")
            return "mainstat";
        if (ElementalAffixOf(id))
            return ELEMENTAL_POOL_ID;
        if (ResistAffixOf(id))
            return RESIST_POOL_ID;
        for (auto const& [group, choices] : skillGroups)
            for (auto const& choice : choices)
                if (choice.id == id)
                    return group;
        return id;
    }
    // What a pool entry rolls as for this player and item. A shield's required block lines are the item
    // type, not a rolled affix, so the Mystic neither removes them nor puts one on a quiver (block.md
    // section 1); no main stat or no skill for the class is a data gap and the entry is not offered.
    std::vector<Enchant::Cand> Expand(Enchant::Cand const& c) const
    {
        bool const rollsBlock = DC::Relic::RollsBlock(Shield(*base), {base->relicPrimary, base->relicSecondary});
        if (RequiredShieldAffix(c.id) || (BlockAffix(c.id) && !rollsBlock) || OffhandDamageAffix(*base, c.id))
            return {};
        if (OffhandSpeedAffix(*base, c.id))
            return {};
        if (c.id == "mainstat")
        {
            std::string const stat = PrimaryStat(*base, mysticClass, classMainStats);
            if (stat.empty())
                return {};
            Enchant::Cand e = c;
            e.id = stat;
            return {e};
        }
        if (c.id == ELEMENTAL_POOL_ID)
        {
            std::vector<Enchant::Cand> out;
            for (ElementalAffix const& affix : ElementalAffixes)
            {
                Enchant::Cand e = c;
                e.id = affix.id;
                out.push_back(e);
            }
            return out;
        }
        if (c.id == RESIST_POOL_ID)
        {
            std::vector<Enchant::Cand> out;
            for (ElementalAffix const& affix : ResistAffixes)
            {
                Enchant::Cand e = c;
                e.id = affix.id;
                out.push_back(e);
            }
            return out;
        }
        if (skillGroups.count(c.id))
        {
            std::vector<Enchant::Cand> out;
            for (SkillAffix const& s : SkillChoices(skillGroups, c.id, mysticClass))
            {
                Enchant::Cand e = c;
                e.id = s.id;
                out.push_back(e);
            }
            return out;
        }
        return {c};
    }
    void Shuffle(std::vector<Enchant::Cand>& list) const
    {
        std::shuffle(list.begin(), list.end(), Engine());
    }
    std::size_t Index(std::size_t count) const
    {
        return std::uniform_int_distribution<std::size_t>(0, count - 1)(Engine());
    }
    // The same two draws the roller makes (RollValue, and for a row with a second range RollWeaponDelta); a Primal's
    // line is the top of its range, as the drop's valueOf has it.
    std::pair<double, double> Value(Enchant::Cand const& c) const
    {
        if (atTop)
            return {c.max, c.max2 > 0 ? c.max2 : 0.0};
        PoolEntry entry;
        entry.min = c.min;
        entry.max = c.max;
        entry.min2 = c.min2;
        entry.max2 = c.max2;
        entry.step = c.step;
        double const value = RollValue(entry);
        return {value, c.max2 > 0 ? value + RollWeaponDelta(entry) : 0.0};
    }
    std::string WeaponClass() const
    {
        return weaponClass;
    }
};

struct MysticInput
{
    MysticCtx ctx;
    std::vector<Enchant::Cand> pool;
    std::vector<Enchant::Row> rows;
    std::vector<Enchant::Pick> values;
};

// False when the item's base or its slot's pool is unknown: nothing on it can be enchanted.
// The caller holds dataMutex.
bool MysticInputs(Player* player, Instance const& instance, MysticInput& in)
{
    auto base = baseItems.find(instance.baseItem);
    if (base == baseItems.end())
        return false;
    std::vector<PoolEntry> const bracket = PoolFor(base->second, BracketFor(instance.rarity, instance.qualityTier));
    if (bracket.empty())
        return false;
    in.ctx.base = &base->second;
    in.ctx.atTop = DC::Quality::AtTop(instance.qualityTier);
    // Rule 5: the re-roller's class on an ordinary item, the item's own on a class-only one
    // (dc_roll_class.h rule 5).
    in.ctx.mysticClass = DC::RollClass::MysticClass(base->second.designatedClass,
                                                    player ? ClassKeyOfLocked(player->getClass()) : std::string());
    if (base->second.slot == "onehand" || base->second.slot == "twohand")
        if (auto found = weaponClassByType.find(base->second.type); found != weaponClassByType.end())
            in.ctx.weaponClass = found->second;
    for (PoolEntry const& p : bracket)
        in.pool.push_back({p.affixId, p.kind, p.min, p.max, p.min2, p.max2, p.step, p.weaponClass, p.order});
    for (Affix const& a : instance.affixes)
    {
        // A Source's, Mojo's or Phylactery's damage is the item type's line, like a shield's required lines below.
        if (OffhandDamageAffix(base->second, a.affixId))
            continue;
        // So is a Quiver's attack speed (mystic.csv:4: the unalterable affix of an item that rolls six).
        if (OffhandSpeedAffix(base->second, a.affixId))
            continue;
        // A shield's required lines belong to the item type, not to a property the player may replace; so does Caldesann's
        // augment (kind `augment`), which is the Cube's and sits beside the rolled lines.
        if (RequiredShieldAffix(a.affixId) || a.kind == "power" || a.kind == "augment" || a.kind == DC::GrantedPassive::Kind)
            continue;
        in.rows.push_back({a.seq, a.affixId, a.kind, a.rerolled});
        in.values.push_back(
            {a.seq, a.affixId, a.kind, a.value, a.value2, a.rangeMin, a.rangeMax, a.rangeMin2, a.rangeMax2});
    }
    return true;
}

Affix MysticAffix(Enchant::Pick const& p, bool rerolled)
{
    Affix a;
    a.seq = p.seq;
    a.affixId = p.id;
    a.kind = p.kind;
    a.value = p.value;
    a.value2 = p.value2;
    a.rangeMin = p.min;
    a.rangeMax = p.max;
    a.rangeMin2 = p.min2;
    a.rangeMax2 = p.max2;
    a.rerolled = rerolled;
    return a;
}

Enchant::Row const* MysticTarget(MysticInput const& in, unsigned seq)
{
    auto found = std::find_if(in.rows.begin(), in.rows.end(), [&](Enchant::Row const& r) { return r.seq == seq; });
    return found == in.rows.end() ? nullptr : &*found;
}
} // namespace

std::vector<EnchantLine> EnchantLines(Player* player, Instance const& instance)
{
    std::lock_guard<std::mutex> lock(dataMutex);
    MysticInput in;
    if (!MysticInputs(player, instance, in))
        return {};
    std::vector<EnchantLine> out;
    for (Enchant::Line const& line : Enchant::Lines(in.pool, in.rows, in.values, instance.enchantLocked, in.ctx))
        out.push_back({MysticAffix(line.pick, line.state == Enchant::State::Enchanted), static_cast<int>(line.state)});
    return out;
}

std::vector<Affix> EnchantOptions(Player* player, Instance const& instance, unsigned seq)
{
    std::lock_guard<std::mutex> lock(dataMutex);
    MysticInput in;
    if (!MysticInputs(player, instance, in))
        return {};
    auto const* target = MysticTarget(in, seq);
    if (!target)
        return {};
    std::vector<Affix> out;
    for (Enchant::Pick const& pick : Enchant::NewChoices(in.pool, *target, in.rows, in.ctx))
        out.push_back(MysticAffix(pick, true));
    return out;
}

std::vector<Affix> EnchantPreview(Player* player, Instance const& instance, unsigned seq)
{
    std::lock_guard<std::mutex> lock(dataMutex);
    MysticInput in;
    if (!MysticInputs(player, instance, in))
        return {};
    auto const* target = MysticTarget(in, seq);
    if (!target)
        return {};
    std::vector<Affix> out;
    for (Enchant::Pick pick : Enchant::Preview(in.pool, *target, in.rows, in.ctx))
    {
        // A Primal can only roll the top, so `?` shows a range of one value (the window words that as the value).
        if (in.ctx.atTop)
        {
            pick.min = pick.max;
            pick.min2 = pick.max2;
        }
        out.push_back(MysticAffix(pick, false));
    }
    return out;
}
}
