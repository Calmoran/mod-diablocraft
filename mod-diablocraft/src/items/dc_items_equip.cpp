// Items: what a worn item puts on the stat sheet (Apply, the cubed and set stats) and the equip rules.
// Literal audit (docs/research/literal-audit-claude.md): the numbers below are
// constants, not tunables - recorded here, nothing else changes.
#include "dc_items_internal.h"

#include "dc_granted_passive_rule.h"
#include "dc_made_rule.h"

#include "../combat/dc_gem_powers.h"
#include "../combat/dc_item_powers.h"
#include "../combat/dc_passives.h"
#include "../classes/dc_classes.h"
#include "../common/dc_tunables.h"

#include "Chat.h"
#include "DatabaseEnv.h"
#include "Item.h"
#include "Player.h"
#include "WorldSession.h"

#include <mutex>
#include <optional>
#include <string>
#include <vector>

namespace DC::Items
{
using namespace Detail;

namespace
{
// Items feed the sheet of every class that has one.
bool Sheeted(Player const* player) { return player && DC::Classes::Playable(player); }

// Unique Equipped: an item that holds a legendary gem cannot be worn while the same gem is
// socketed in another worn item. What leaves with this equip does not count: the item itself when it only moves,
// the item in the slot it takes when the slot is named, and a two-hander's main and off hand. An auto-equip names
// no slot, so a replaced ring or weapon holding the same gem is refused there and works by dragging it on.
// What leaves the worn set with this equip: the item itself, the item in the slot it takes, a two-hander's both hands.
// Unique Equipped and the made-by rule (dc_made_rule.h) count what stays.
std::vector<std::uint64_t> Leaving(Player* player, uint8 slot, Item* item)
{
    std::vector<std::uint64_t> leaving = {item->GetGUID().GetCounter()};
    auto leave = [&](uint8 position)
    {
        if (Item* worn = player->GetItemByPos(INVENTORY_SLOT_BAG_0, position))
            leaving.push_back(worn->GetGUID().GetCounter());
    };
    if (slot < EQUIPMENT_SLOT_END)
        leave(slot);
    if (item->GetTemplate()->InventoryType == INVTYPE_2HWEAPON)
    {
        leave(EQUIPMENT_SLOT_MAINHAND);
        leave(EQUIPMENT_SLOT_OFFHAND);
    }
    return leaving;
}

// A Primal Ancient with a maker (dc_made_rule.h). The creator field is read first, so an item without one costs no query.
bool Made(Item* item)
{
    if (!item || !item->GetGuidValue(ITEM_FIELD_CREATOR))
        return false;
    std::optional<Instance> instance = Get(item->GetGUID().GetCounter());
    return instance && MadePrimal(true, instance->qualityTier);
}
}

// External linkage on purpose (declared in dc_items.h, called from dc_cube.cpp), so outside the anonymous namespaces.
// A cubed power that is an item affix (Sun Keeper's and The Furnace's elite damage, the item-owned `stat` rows
// of dc_legendary_power) reaches the sheet through Mappings() like the worn item's roll, at the top of its range (the Cube reads
// the top), keyed by ItemPower::CubeContributionId so no item's unequip removes it. Only the powers
// ItemPowers::ActivePowers holds as the Cube's count: a copy that is also worn counts once, worn. Run after every change of the
// Cube list and of the worn items (Apply).
void RefreshCubedStats(Player* player)
{
    if (!Sheeted(player))
        return;
    std::uint64_t const playerGuid = player->GetGUID().GetRawValue();
    std::vector<Contribution> wanted;
    unsigned ordinal = 0; // the contribution's slot field: the power's place among the cubed ones, unique per power
    for (auto const& power : DC::Combat::ItemPowers::ActivePowers(player))
    {
        if (power.source != DC::Combat::ItemPower::Source::Cube)
            continue;
        ++ordinal;
        unsigned seq = 0;
        for (auto const& row : DC::Combat::ItemPowers::ItemStats(power.id))
        {
            auto mapping = Mappings().find(row.stat);
            std::uint32_t const id = DC::Combat::ItemPower::CubeContributionId(ordinal, seq++);
            if (mapping == Mappings().end() || id == 0)
                continue;
            Contribution contribution;
            contribution.source = Source::Items;
            contribution.stat = mapping->second.stat;
            contribution.bucket = mapping->second.bucket;
            contribution.element = mapping->second.element;
            contribution.id = id;
            contribution.value = row.max;
            wanted.push_back(contribution);
        }
    }
    // N-SETSTAT: a set level's plain stats (Asheara's Vestments 2-piece's Resistance to All Elements) while the worn count
    // reaches it, through the same affix map, keyed by ItemPower::SetStatContributionId.
    for (auto const& [index, row] : DC::Combat::ItemPowers::SetStats(player))
    {
        auto mapping = Mappings().find(row.stat);
        std::uint32_t const id = DC::Combat::ItemPower::SetStatContributionId(index);
        if (mapping == Mappings().end() || id == 0)
            continue;
        wanted.push_back({Source::Items, mapping->second.stat, id, row.min, mapping->second.bucket, mapping->second.element});
    }
    std::vector<std::pair<Stat, std::uint64_t>> had;
    bool known;
    {
        std::lock_guard<std::mutex> lock(bonusMutex);
        auto found = cubedStats.find(playerGuid);
        known = found != cubedStats.end();
        if (known)
            had = found->second;
    }
    // The first refresh since the login (OnPlayerLogin forgets the list): the loaded sheet holds what was saved, so a cubed or set stat the
    // character no longer has (a power gone from the Cube, a crash between writes) is taken as placed and removed below.
    if (!known)
        for (Contribution const& saved : DC::Stats::Contributions(playerGuid))
            if (saved.source == Source::Items && DC::Combat::ItemPower::CubedStatId(saved.id))
                had.push_back({saved.stat, saved.id});
    if (had.empty() && wanted.empty())
    {
        std::lock_guard<std::mutex> lock(bonusMutex);
        cubedStats[playerGuid]; // swept: the next refresh need not read the sheet again
        return; // every equip comes through here
    }
    bool changed = false;
    for (auto const& [stat, id] : had)
        changed = DC::Stats::RemoveContribution(playerGuid, Source::Items, stat, id) || changed;
    std::vector<std::pair<Stat, std::uint64_t>> placed;
    for (Contribution const& contribution : wanted)
    {
        changed = DC::Stats::AddContribution(playerGuid, contribution) || changed;
        placed.push_back({contribution.stat, contribution.id});
    }
    {
        std::lock_guard<std::mutex> lock(bonusMutex);
        cubedStats[playerGuid] = placed; // kept when empty: an entry means the login sweep has run
    }
    if (changed)
        DC::Stats::Recompute(player);
}

namespace Detail
{
// --- stat sheet contribution (05 §4) ---------------------------------------
void Apply(Player* player, Item* item, bool equipping)
{
    if (!Sheeted(player) || !item)
        return;
    if (equipping && item->IsBroken())
        equipping = false;
    std::uint64_t const itemGuid = item->GetGUID().GetCounter();
    std::optional<Instance> instance = Load(itemGuid);
    if (!instance)
        return;
    std::uint64_t const playerGuid = player->GetGUID().GetRawValue();
    auto const& mappings = Mappings();
    bool changed = false;
    double weaponDamage=0;
    // G1: the weapon's rolled elemental range (value to low, value2 to high).
    double elementLow=0, elementHigh=0;
    bool const weapon = item->GetTemplate()->Class == ITEM_CLASS_WEAPON;
    for (Affix const& affix : instance->affixes)
    {
        if (affix.kind == "socket" || affix.kind == "power" || affix.kind == DC::GrantedPassive::Kind) continue;
        std::string statId=affix.affixId;
        double value=affix.value;
        Source source=Source::Items;
        if(affix.kind=="gem")
        {
            std::lock_guard<std::mutex> lock(dataMutex);
            auto base=baseItems.find(instance->baseItem);
            if(base==baseItems.end()) continue;
            std::string slot=base->second.slot=="head"?"head":(base->second.slot=="onehand"||base->second.slot=="twohand")?"weapon":"other";
            auto gem=gemEffects.find(affix.gemEntry);
            if(gem==gemEffects.end() || !gem->second.count(slot)) continue;
            auto const& effect=gem->second.at(slot); statId=effect.stat; value=effect.value; source=Source::Gems;
            // A weapon gem's flat damage is that weapon's own (D3's Ruby): the per-item cache carries it into
            // the swing, so it never reaches the sheet's WeaponFlatDamage, which the hit adds again.
            if(statId=="wpnphy") { weaponDamage+=value; continue; }
        }
        // G1: on a weapon a two-part wpn* row is its elemental damage, not jewelry's flat
        // damage - it is added to that weapon's swing low/high and never goes through Mappings.
        // Jewelry's two-part wpnphy goes through Mappings below, for either hand.
        if (affix.kind != "gem" && affix.value2 > 0 && weapon && WeaponDamageAffix(affix.affixId))
        {
            elementLow += affix.value;
            elementHigh += affix.value2;
            continue;
        }
        std::uint32_t skillId = 0;
        {
            std::lock_guard<std::mutex> lock(dataMutex);
            if (auto found = skillAffixes.find(affix.affixId); found != skillAffixes.end())
                skillId = found->second.skillId;
        }
        if (skillId)
        {
            std::lock_guard<std::mutex> lock(bonusMutex);
            auto& bonuses = skillBonuses[playerGuid];
            if (equipping) bonuses.Set(ContributionId(itemGuid, affix.seq), skillId, affix.value);
            else bonuses.Remove(ContributionId(itemGuid, affix.seq));
            continue;
        }
        auto mapping = mappings.find(statId);
        if (mapping == mappings.end() || !Applies(mapping->second, player))
            continue;
        // A weapon's own attack speed belongs to the hand it is worn in: D3
        // reads `weaponias` off that weapon (stats_full.js:331), and the
        // Whirlwind channel charges and schedules each tick on the hand that
        // swings it. The other hand's version of
        // this contribution is always cleared, so a weapon that moves hands -
        // or leaves one without the slot still reading true - cannot leave its
        // attack speed behind on the hand it left.
        bool const handed = mapping->second.bucket == Bucket::WeaponLocal;
        Stat stat = mapping->second.stat;
        if (handed)
        {
            bool const offhand = item->GetBagSlot() == INVENTORY_SLOT_BAG_0 &&
                                 item->GetSlot() == EQUIPMENT_SLOT_OFFHAND;
            stat = offhand ? Stat::OffhandWeaponIAS : Stat::AttackSpeed;
            Stat const other = offhand ? Stat::AttackSpeed : Stat::OffhandWeaponIAS;
            changed = DC::Stats::RemoveContribution(playerGuid, source, other,
                                                    ContributionId(itemGuid, affix.seq)) || changed;
        }
        if (equipping)
        {
            Contribution contribution;
            contribution.source = source;
            contribution.stat = stat;
            contribution.bucket = mapping->second.bucket;
            contribution.element = mapping->second.element;
            contribution.id = ContributionId(itemGuid, affix.seq);
            contribution.value = Signed(mapping->second, value);
            changed = DC::Stats::AddContribution(playerGuid, contribution) || changed;
        }
        else
        {
            changed = DC::Stats::RemoveContribution(playerGuid, source, stat,
                                                    ContributionId(itemGuid, affix.seq)) || changed;
        }
        // Jewelry's +X-Y Physical Damage is D3's Min + Delta: X went to WeaponFlatDamage (low
        // and high), Y - X goes to WeaponFlatDamageDelta (high only). A one-number flat damage
        // (a gem's, an old one-part roll) has no delta.
        if (stat == Stat::WeaponFlatDamage && affix.value2 > 0)
        {
            if (equipping)
            {
                Contribution delta;
                delta.source = source;
                delta.stat = Stat::WeaponFlatDamageDelta;
                delta.bucket = mapping->second.bucket;
                delta.element = mapping->second.element;
                delta.id = ContributionId(itemGuid, affix.seq);
                delta.value = affix.value2 - affix.value;
                changed = DC::Stats::AddContribution(playerGuid, delta) || changed;
            }
            else
            {
                changed = DC::Stats::RemoveContribution(playerGuid, source, Stat::WeaponFlatDamageDelta,
                                                        ContributionId(itemGuid, affix.seq)) || changed;
            }
        }
    }
    // A legendary gem's always-on power follows the gems that count, rebuilt here for
    // equip, unequip, socket and swap alike (a legendary gem has no dc_gem_effect row, so `changed`
    // above does not see it).
    DC::Combat::GemPowers::Refresh(player, item, equipping, *instance);
    // Legendary powers P0: the worn pieces of the item's set, on the same events.
    DC::Combat::ItemPowers::Refresh(player, item, equipping, *instance);
    // The class passive the worn item grants (an unequipped or broken item grants none).
    {
        std::string const granted = equipping ? DC::GrantedPassive::Granted(instance->affixes) : std::string();
        bool differs;
        {
            std::lock_guard<std::mutex> lock(bonusMutex);
            auto& mine = grantedPassive[playerGuid];
            auto had = mine.find(itemGuid);
            differs = (had == mine.end() ? std::string() : had->second) != granted;
            if (granted.empty())
                mine.erase(itemGuid);
            else
                mine[itemGuid] = granted;
        }
        if (differs)
            DC::Combat::Passives::Invalidate(player);
    }
    {
        std::lock_guard<std::mutex> lock(bonusMutex);
        if(equipping) weaponExtra[playerGuid][itemGuid]={weaponDamage+elementLow,weaponDamage+elementHigh};
        else weaponExtra[playerGuid].erase(itemGuid);
    }
    if (changed)
    {
        DC::Stats::Recompute(player);
        // The Fury cost reductions are charged by an aura, not read off the
        // sheet, so a ring that carries Resource Cost Reduction has to reach
        // that aura too. Equip, unequip and socket
        // all come through here.
        DC::Combat::Passives::RefreshModifiers(player);
    }
    // A worn copy of a cubed power takes its place on the sheet (the worn side wins), and taking it off gives the cubed one back.
    RefreshCubedStats(player);
}

bool UniqueEquippedAllows(Player* player, uint8 slot, Item* item)
{
    std::optional<Instance> instance = Get(item->GetGUID().GetCounter());
    if (!instance)
        return true;
    std::vector<std::uint64_t> const leaving = Leaving(player, slot, item);
    for (Affix const& affix : instance->affixes)
    {
        if (affix.kind != "gem" || !affix.legendaryRank)
            continue;
        if (Item* holder = WornLegendaryGem(player, affix.affixId, leaving))
        {
            if (player->GetSession())
                ChatHandler(player->GetSession())
                    .SendSysMessage((std::string(item->GetTemplate()->Name1) + " holds " + LegendaryGemName(affix.affixId) +
                                     ", which is already socketed in your " + holder->GetTemplate()->Name1 +
                                     ". A legendary gem can be worn only once (Unique Equipped): take one off first.")
                                        .c_str());
            return false;
        }
    }
    return true;
}

// The one-worn rule (dc_made_rule.h): a made Primal goes on only while fewer than the limit stay worn.
bool MadeEquipAllows(Player* player, uint8 slot, Item* item)
{
    if (!Made(item))
        return true;
    std::vector<WornMade> worn;
    for (uint8 position = EQUIPMENT_SLOT_START; position < EQUIPMENT_SLOT_END; ++position)
        if (Item* other = player->GetItemByPos(INVENTORY_SLOT_BAG_0, position))
            worn.push_back({other->GetGUID().GetCounter(), Made(other)});
    double const limit = DC::Tunables::Get("crafting", "made_primal_worn_limit");
    if (MadeAllows(true, worn, Leaving(player, slot, item), limit))
        return true;
    if (player->GetSession())
        ChatHandler(player->GetSession())
            .PSendSysMessage("You can wear {} Primal Ancient item(s) made in Kanai's Cube at a time: take one off first.",
                             limit);
    return false;
}
}

// Declared in dc_items.h and called from dc_cube.cpp, so it needs external linkage: outside the anonymous namespace.
void MarkMade(Player* owner, Item* item, Player* maker, CharacterDatabaseTransaction const& transaction)
{
    item->SetGuidValue(ITEM_FIELD_CREATOR, maker->GetGUID());
    item->SetState(ITEM_CHANGED, owner);
    std::string name = maker->GetName();
    CharacterDatabase.EscapeString(name);
    transaction->Append("UPDATE dc_item_instance SET made_by='{}' WHERE item_guid={}", name, item->GetGUID().GetCounter());
}

void RemoveContributions(Player* player, Item* item) { if(item && item->IsEquipped()) Apply(player,item,false); }
void RefreshContributions(Player* player, Item* item) { if(item && item->IsEquipped()) Apply(player,item,true); }
}
