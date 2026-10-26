#include "dc_loot.h"
#include "dc_loot_internal.h"
#include "dc_ground_loot.h"
#include "dc_corpse_loot.h"
#include "dc_kadala_rule.h"
#include "dc_broken_crown_rule.h"
#include "dc_keystone_rule.h"
#include "dc_pick_rule.h"

#include "../rifts/dc_rifts.h"
#include "../rifts/dc_gr_rewards.h"

#include "../combat/dc_item_powers.h"
#include "../difficulty/dc_difficulty.h"
#include "../items/dc_items.h"
#include "../items/dc_roll_class.h"
#include "../items/dc_quality_rule.h"
#include "../stats/dc_stats.h"
#include "../common/dc_account_economy.h"
#include "../common/dc_economy.h"
#include "../common/dc_numeric_data.h"
#include "../common/dc_tiers.h"
#include "../common/dc_tunables.h"
#include "../combat/dc_item_powers.h"
#include "../crafting/dc_crafting.h"

#include "Chat.h"
#include "Bag.h"
#include "Map.h"
#include "TemporarySummon.h"
#include <functional>
#include "Creature.h"
#include "DatabaseEnv.h"
#include "DBCStores.h"
#include "GameObject.h"
#include "Group.h"
#include "Item.h"
#include "Log.h"
#include "LootMgr.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "PlayerEconomy.h"
#include "ScriptMgr.h"
#include "World.h"
#include "WorldSession.h"

#include <map>
#include <algorithm>
#include <cmath>
#include <array>
#include <memory>
#include <mutex>
#include <random>
#include <set>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>

// Literal audit (docs/research/literal-audit-claude.md): the numbers below are
// constants, not tunables - recorded here, nothing else changes.
// Constant (10): LaunchTiers, difficulty tiers at launch; 03-difficulty owns the tier list (section B); this is a row-count assertion, not a tuning value.
// Constant (102000–102004): crafting-material item entries; Identifiers.
// Constant (2, 5): unidentified-shell rarity codes for set and legendary; Identifiers.

namespace DC::Loot
{
using namespace Detail;

namespace
{
// Constant: the compile-time size of the tier-bonus array below, which is why
// it cannot be the runtime accessor. How many tiers are actually open is
// DC::LaunchTierCount() (tunables monsters/launch_tier_count, section B); the
// loader refuses a launch count larger than this, so the array can never be
// indexed past its end. Audit row 42, now a third copy of section B's number.
constexpr unsigned MaxLaunchTiers = 10;
// L10. In 3.3.5a a currency is an item whose entry appears in CurrencyTypes.dbc;
// the client then lists it in the Currency tab of the character window. The core
// strips the currency bag-family bit from any item missing from that DBC
// (ObjectMgr.cpp checks BAG_FAMILY_MASK_CURRENCY_TOKENS against the store), so
// the rows in client-patch/dbc/CurrencyTypes.dbc are load-bearing on both sides.
// Items: mod-diablocraft/data/sql/db-world/updates/loot_0003_currency_items.sql.
struct Currency { char const* name; std::uint32_t entry; };
constexpr std::array<Currency, 5> Currencies = {{
    {"Death's Breath", 102000},
    {"Reusable Parts", 102001},
    {"Arcane Dust",    102002},
    {"Veiled Crystal", 102003},
    {"Forgotten Soul", 102004},
}};
constexpr std::size_t DeathsBreath = 0;


// Legacy display only. With the account economy on, the login hook in
// dc_account_economy.cpp clears these bits and the account snapshot is the
// display, so nothing here may learn a retired currency back.
void LearnHeldCurrencies(Player* player)
{
    if (DC::AccountEconomy::Enabled())
        return;
    for (Currency const& currency : Currencies)
        if (player->GetItemCount(currency.entry, true) > 0)
            DC::Economy::KnowCurrency(player, currency.entry);
}

struct TierBonus { double goldPct = 0, legendaryPct = 0; };

struct BaseItem
{
    std::uint32_t entry = 0;
    unsigned itemLevel = 0;
    // What base_items.csv said, kept verbatim. Whether a given player may roll
    // this is a question about THAT player's class and is answered per roll -
    // it used to be baked in here as a Barbarian/other pair at load time.
    std::string usable;           // D3Planner ';' list, empty = no restriction
    std::string designation;      // whose item this is, empty = nobody's in particular
    std::string setClass;         // the class a set belongs to in the source; drop roll only, never wear
    // Only the unique pool fills these, and only a unique drop becomes a shell.
    // rarity is 'legendary' or 'set'; inventoryType
    // is the item_template slot, which is what picks the matching shell.
    std::string rarity;
    unsigned inventoryType = 0;
    // dc_base_item slot and type, for Kadala's slot filter (kadala.md 4.10); a drop ignores them.
    std::string slot, type;
    // dc_follower_relic_roll: the drop weight (0 for any other base, which weighs tunables loot/ordinary_drop_weight) and the
    // lowest tier it drops at.
    unsigned weight = 0, minTier = 0;
};

// The unidentified shells, keyed by (InventoryType, Quality). Read back from
// item_template rather than computed, so the generator owns the numbering and
// the module never has to agree with it a second time.
std::map<std::pair<unsigned, unsigned>, std::uint32_t> shells;
bool unidentifiedDrops = false;   // dc_loot_tuning identify row, the on/off switch

// dc_class_map, generated from class_map.csv: the D3 class a WoW class plays.
// It lists ONLY classes whose spells are generated, so a class with reference
// sheets and no shells is absent and rolls nothing - which is exactly what the
// hardcoded CLASS_WARRIOR check used to say, without the hardcoding.
std::unordered_map<unsigned, std::string> classMap;

}

namespace Detail
{
std::string D3Class(Player const* player)
{
    if (!player)
        return {};
    auto found = classMap.find(static_cast<unsigned>(player->getClass()));
    return found == classMap.end() ? std::string() : found->second;
}
}

namespace
{

// Every class a drop may roll for: the playable ones, in a fixed order so a
// seeded roll is reproducible (dc_roll_class.h rule 1).
std::vector<std::string> PlayableClasses()
{
    std::vector<std::string> keys;
    for (auto const& [wowClass, key] : classMap)
        keys.push_back(key);
    std::sort(keys.begin(), keys.end());
    return keys;
}

std::mutex dataMutex;
std::array<Tuning, static_cast<unsigned>(Source::Count)> tunings;
std::array<TierBonus, MaxLaunchTiers + 1> tierBonuses;
// rarity bucket -> eligible base items
std::vector<BaseItem> generics, uniques;
bool dataReady = false;

std::mt19937_64& Engine()
{
    static thread_local std::mt19937_64 engine{std::random_device{}()};
    return engine;
}

double Roll() { return std::uniform_real_distribution<double>(0.0, 1.0)(Engine()); }

std::optional<Source> ParseSource(std::string const& text)
{
    for (unsigned index = 0; index < static_cast<unsigned>(Source::Count); ++index)
        if (text == Name(static_cast<Source>(index)))
            return static_cast<Source>(index);
    return std::nullopt;
}

// The difficulty module puts a creature's tier in its phase mask (03-difficulty),
// so the kill hook reads the tier off the creature rather than calling into that
// module, which keeps the two independently buildable.
unsigned TierOf(Creature const* creature)
{
    unsigned phase = creature ? creature->GetPhaseMask() : 1;
    return (phase >= 1 && phase <= DC::LaunchTierCount()) ? phase : 1;
}

bool D3Source(WorldObject const* object, StockSource source)
{
    if (!object || !object->FindMap())
        return false;
    unsigned riftTier = 0, riftPlayers = 0;
    bool const inRift = DC::Rifts::ScalingContext(object->FindMap(), riftTier, riftPlayers);
    return SuppressStockLoot(source, !object->FindMap()->Instanceable(),
                             object->GetPhaseMask(), DC::LaunchTierCount(), inRift);
}

bool D3Creature(Creature const* creature)
{
    return creature && !creature->IsControlledByPlayer() && !creature->IsPet() &&
        D3Source(creature, StockSource::Creature);
}

bool OpenTreasureLock(std::uint32_t lockId)
{
    if (!lockId)
        return false;
    LockEntry const* lock = sLockStore.LookupEntry(lockId);
    if (!lock)
        return false;
    bool openTreasure = false;
    for (unsigned index = 0; index < MAX_LOCK_CASE; ++index)
    {
        if (lock->Type[index] != LOCK_KEY_SKILL)
            continue;
        // Refuse every other skill lock, including Herbalism, Mining,
        // Fishing, Inscription and Lockpicking. No profession node becomes a
        // D3 chest even if it also has a generic open case.
        if (lock->Index[index] != LOCKTYPE_OPEN && lock->Index[index] != LOCKTYPE_TREASURE)
            return false;
        openTreasure = true;
    }
    return openTreasure;
}

bool D3Chest(GameObject const* chest)
{
    if (!chest || chest->GetGoType() != GAMEOBJECT_TYPE_CHEST)
        return false;
    GameObjectTemplate const* info = chest->GetGOInfo();
    return info && D3ChestTemplate(info->chest.groupLootRules != 0, info->GetLootId() != 0,
                                   OpenTreasureLock(info->chest.lockId)) &&
        D3Source(chest, StockSource::Chest);
}

bool D3NativeLoot(Player const* player, ::Loot const* loot, StockSource source)
{
    if (!player || !loot)
        return false;
    ObjectGuid const guid = loot->sourceWorldObjectGUID;
    if (source == StockSource::Creature && guid.IsCreatureOrVehicle())
        return D3Creature(ObjectAccessor::GetCreature(*player, guid));
    if (source == StockSource::Chest && guid.IsGameObject())
        return D3Chest(ObjectAccessor::GetGameObject(*player, guid));
    return false;
}

double MagicFind(Player* player)
{
    if (auto sheet = DC::Stats::Get(player->GetGUID().GetRawValue()))
        return (*sheet)[Stat::MagicFind] / 100.0;
    return 0.0;
}

double GoldFind(Player* player)
{
    if (auto sheet = DC::Stats::Get(player->GetGUID().GetRawValue()))
        return (*sheet)[Stat::GoldFind] / 100.0;
    return 0.0;
}

}

// 06 §2 step 4. Everything eligible at its weight (dc_pick_rule.h: an ordinary base weighs the same as every other, so
// the pick is uniform among them; a follower relic weighs a third of one and drops from Torment I): slot weights are an
// open item (06 §6). tier is the difficulty tier id of the drop, 0 for a pick with none. 05 §3 pool rule 2 and
// class-roll rule 2: the roll class must be able to use the type and the item
// must be nobody's or that class's own - so an off-class roll can bring the
// other class's class-only items. A class set's pieces count as that class's own
// for the drop (DropEligible), never for wearing.
// filter: Kadala's gamble names the slot (and kinds) it sells (kadala.md 5 Part 5); a drop passes none.
std::uint32_t PickBaseItem(Rarity rarity, unsigned monsterLevel, std::string const& rollClass, unsigned tier,
                           Kadala::SlotFilter const* filter)
{
    std::lock_guard<std::mutex> lock(dataMutex);
    std::vector<BaseItem> const& pool = rarity == Rarity::Legendary ? uniques : generics;
    std::vector<Pick::Candidate> eligible;
    unsigned const ordinaryWeight = static_cast<unsigned>(std::lround(DC::Tunables::Get("loot", "ordinary_drop_weight")));
    for (BaseItem const& item : pool)
    {
        // L8: the item's own level must not exceed the monster's. Rows with no
        // level in base_items.csv are unrestricted, which is every generic base.
        if (item.itemLevel > monsterLevel)
            continue;
        if (!DC::RollClass::DropEligible(item.usable, item.designation, item.setClass, rollClass))
            continue;
        if (filter && !filter->Admits(item.slot, item.type))
            continue;
        Pick::Candidate const candidate{item.entry, item.weight ? item.weight : ordinaryWeight, item.minTier};
        if (!Pick::Open(candidate, tier))
            continue;
        eligible.push_back(candidate);
    }
    if (eligible.empty())
        return 0;
    return Pick::Choose(eligible, std::uniform_real_distribution<double>(0.0, 1.0)(Engine()));
}

// kadala.md 4.7: the buyer's level and class, a flat legendaryPct chance of a legendary or set base, else a rare
// generic one. A legendary roll with no unique base for the slot, class and level falls back to the generic roll.
std::uint32_t PickGamble(Kadala::SlotFilter const& filter, unsigned level, std::string const& rollClass,
                         double legendaryPct)
{
    if (Kadala::RollsLegendary(legendaryPct, Roll()))
        if (std::uint32_t const unique = PickBaseItem(Rarity::Legendary, level, rollClass, 0, &filter))
            return unique;
    return PickBaseItem(Rarity::Rare, level, rollClass, 0, &filter);
}

namespace Detail
{
// The unique base item this drop rolled, if it is one
// that must arrive unidentified. Empty rarity means an ordinary roll.
bool ShellFor(std::uint32_t baseItem, std::string& rarity, std::uint32_t& shellEntry)
{
    std::lock_guard<std::mutex> lock(dataMutex);
    if (!unidentifiedDrops)
        return false;
    for (BaseItem const& item : uniques)
    {
        if (item.entry != baseItem)
            continue;
        if (item.rarity != "legendary" && item.rarity != "set")
            return false;       // 'ethereal' and anything else rolls as before
        auto found = shells.find({item.inventoryType, item.rarity == "set" ? 2u : 5u});
        if (found == shells.end())
            return false;
        rarity = item.rarity;
        shellEntry = found->second;
        return true;
    }
    return false;
}
}

// Cain's Destiny 3-piece (dc_keystone_rule.h): the power table's chance, one roll.
unsigned ExtraKeystones(Player const* player)
{
    return Keystone::Extra(DC::Combat::ItemPowers::KeystoneFactor(player), Roll());
}

Result RollLoot(Player* player, Source source, unsigned monsterLevel, unsigned tier, bool inRift,
                std::string const& receipt, Creature* deathSource, Position const* dropOrigin,
                GreaterReward const* greater)
{
    Result result;
    if (!player || source >= Source::Count)
        return result;
    // Whose pool this roll draws from. Empty means a class this realm does not
    // play, which rolls nothing rather than falling back to somebody else's.
    std::string const d3 = D3Class(player);
    if (d3.empty())
        return result;

    // A durable reward source passes the same receipt it gives the keystone, and
    // the account economy writes that receipt in the same commit as the whole
    // reward (dc_account_economy_operation). Its presence therefore means this
    // reward already settled - most importantly after a restart, when a rift
    // whose completion row never persisted is re-run from its guardian state.
    // Re-rolling would pay the drops, gold and Death's Breath a second time; on
    // a duplicate nothing is rolled or granted at all (09 F7).
    if (!receipt.empty() && DC::AccountEconomy::Enabled() &&
        CharacterDatabase.Query("SELECT 1 FROM dc_account_economy_operation WHERE operation_id='{}'", receipt))
    {
        result.ok = true;
        result.duplicate = true;
        return result;
    }

    Tuning tuning;
    TierBonus bonus;
    std::vector<std::string> playable;
    {
        std::lock_guard<std::mutex> lock(dataMutex);
        if (!dataReady)
            return result;
        tuning = tunings[static_cast<unsigned>(source)];
        bonus = tierBonuses[std::clamp(tier, 1u, DC::LaunchTierCount())];
        playable = PlayableClasses();
    }
    // tunables:loot; the loot roll class (dc_roll_class.h rule 1).
    double const offClassPct = DC::Tunables::Get("loot", "smart_loot_off_class_pct");
    result.ok = true;

    double const magicFind = MagicFind(player);
    double const riftBonus = inRift ? RiftLegendaryBonusPct(tier) : 0.0;
    double const legendaryPct = LegendaryChancePct(tuning, bonus.legendaryPct, riftBonus, magicFind);

    // A durable reward source (the rift guardian) opens its account operation
    // before calling in. An ordinary kill has none, and delivers immediately.
    bool const shared = PlayerEconomy::Current() != nullptr;
    bool const ground = GroundDeliveryEnabled();
    bool const corpse = !ground && source != Source::Chest && deathSource && CorpseCanHold(deathSource);
    Position const dropPosition = dropOrigin ? *dropOrigin :
        (deathSource ? deathSource->GetPosition() : player->GetPosition());

    unsigned const drops = DropCount(tuning, source, Roll());
    // A Greater Rift Guardian has no guaranteed legendary: its legendaries are the level's
    // curve, a whole part and the fraction as the chance of one more, dropped after the ordinary
    // drops, which then roll no legendary of their own (the curve's start is that chance already).
    unsigned const legendaries = greater ? DC::Rifts::Gr::LegendaryCount(greater->legendaries, Roll()) : 0;
    for (unsigned index = 0; index < drops + legendaries; ++index)
    {
        // A rift guardian's first drop is the guaranteed legendary (L1); the rest
        // roll as normal drops at the guardian's own legendary chance.
        bool const guaranteed = source == Source::RiftGuardian && index == 0 && !greater;
        Rarity rarity = (guaranteed || index >= drops || (!greater && Roll() * 100.0 < legendaryPct))
            ? Rarity::Legendary
            : PickNonLegendary(tuning, magicFind, Roll());

        // L7 smart loot, class-roll rule 1: the looter's class, or with
        // loot/smart_loot_off_class_pct (15%) another playable class. The roll
        // class then picks the base (rule 2) and every class-bound affix (rule 3).
        std::string rollClass = DC::RollClass::Pick(d3, playable, offClassPct, Roll(), Roll());
        std::uint32_t base = PickBaseItem(rarity, monsterLevel, rollClass, tier);
        // No base for the other class at this rarity and level: the drop is the
        // looter's own rather than lost, as before this rule.
        if (!base && rollClass != d3)
        {
            rollClass = d3;
            base = PickBaseItem(rarity, monsterLevel, rollClass, tier);
        }
        if (!base)
            continue;

        // Ancient / Primal is decided here, once, and travels with the drop.
        std::string const quality = DC::Items::RollQuality(player, base, monsterLevel, tier);
        ++result.rolled;
        switch (rarity)
        {
            case Rarity::Legendary: ++result.legendary; break;
            case Rarity::Rare:      ++result.rare;      break;
            case Rarity::Magic:     ++result.magic;     break;
            default:                ++result.normal;    break;
        }
        if (corpse)
        {
            std::string corpseRarity = Name(rarity), uniqueRarity;
            uint32 shell = 0;
            if (ShellFor(base,uniqueRarity,shell)) corpseRarity = uniqueRarity;
            if (!DropCorpseLoot(player,deathSource,base,monsterLevel,corpseRarity,Name(source),tier,"rolled",1,rollClass,quality))
            {
                PlayerEconomy::Fail(); result.ok = false;
                LOG_ERROR("server", "[DC loot] Corpse row refused for {}.",player->GetName());
                return result;
            }
            ++result.oncorpse;
            continue;
        }
        if (ground)
        {
            std::string groundRarity = Name(rarity), uniqueRarity;
            uint32 shell = 0;
            if (ShellFor(base,uniqueRarity,shell)) groundRarity = uniqueRarity;
            if (!DropGroundLoot(player,base,monsterLevel,groundRarity,Name(source),tier,"rolled",1,dropPosition,rollClass,quality))
            {
                PlayerEconomy::Fail(); result.ok = false;
                LOG_ERROR("server", "[DC loot] Ground descriptor refused for {}.",player->GetName());
                return result;
            }
            ++result.grounded;
            continue;
        }
        // L8: item level is the monster's level. The 05-items roller creates the
        // item and writes its rows; a null return means the bags are full (L5).
        if (!shared)
        {
            if (DeliverItem(player, base, monsterLevel, Name(source), tier, rollClass, quality))
                ++result.delivered;
            else
            {
                Buffer(player, base, monsterLevel, Name(source), tier, rollClass, quality);
                ++result.buffered;
            }
            continue;
        }
        // EVERY legendary and set drop
        // is a shell, the rift guardian's included. This path used to go
        // straight to StageRoll, so the one drop players care about most - the
        // guaranteed guardian legendary - arrived already rolled while every
        // other legendary arrived unidentified.
        //
        // A shell needs no staging: it carries no roll, so there is nothing for
        // a failed reward to hand over unpaid-for. It is delivered directly and
        // buffered on a full bag like any other.
        {
            std::string shellRarity;
            std::uint32_t shellEntry = 0;
            if (ShellFor(base, shellRarity, shellEntry))
            {
                if (DeliverShell(player, base, monsterLevel, shellRarity, shellEntry, Name(source), tier, rollClass, quality))
                    ++result.delivered;
                else
                {
                    Buffer(player, base, monsterLevel, Name(source), tier, rollClass, quality);
                    ++result.buffered;
                }
                continue;
            }
        }
        // Inside a durable source's operation the drop is staged into that
        // operation's transaction and published by its commit, so a failed
        // reward leaves no item behind and no item is handed over unpaid-for.
        std::shared_ptr<DC::Items::StagedRoll> staged(
            DC::Items::StageRoll(player, base, monsterLevel, "", PlayerEconomy::BeginTransaction(), rollClass, quality).release());
        if (!staged)
        {
            Buffer(player, base, monsterLevel, Name(source), tier, rollClass, quality);
            ++result.buffered;
            continue;
        }
        PlayerEconomy::AfterCommit([player, staged]()
        {
            if (Item* item = staged->Publish())
                player->SendNewItem(item, 1, false, false, false, true);
        });
        ++result.delivered;
    }

    // The Guardian's legendary gem, one the character does not own yet, at rank 0 (a gem item
    // with no rank row is rank 0), whether or not the kill beat the clock.
    if (greater)
        if (std::uint32_t const gem = DC::Rifts::Gr::PickGem(greater->gems, Roll()))
            DeliverGemDrop(player, gem, monsterLevel, Name(source), tier, deathSource, corpse, ground, dropPosition);

    // A guardian also reaches the ordinary creature-kill hook. Its one salvage
    // carrier belongs to the receipted F7 reward, not that generic boss roll.
    if (source == Source::RiftGuardian || (source == Source::Boss && !inRift))
    {
        unsigned const count = BossMaterialCount();
        if (count)
        {
            auto rows = WorldDatabase.Query("SELECT entry,rarity FROM dc_ground_loot_material ORDER BY entry");
            if (!rows) { PlayerEconomy::Fail(); result.ok = false; return result; }
            std::vector<std::pair<uint32,std::string>> choices;
            do
            {
                auto* fields = rows->Fetch();
                choices.emplace_back(fields[0].Get<uint32>(),fields[1].Get<std::string>());
            } while (rows->NextRow());
            auto const& material = choices[std::uniform_int_distribution<std::size_t>(0,choices.size()-1)(Engine())];
            bool const granted = corpse
                ? DropCorpseLoot(player,deathSource,material.first,monsterLevel,material.second,Name(source),tier,"material",count)
                : ground
                ? DropGroundLoot(player,material.first,monsterLevel,material.second,Name(source),tier,"material",count,dropPosition)
                : GrantMaterial(player,material.first,count);
            if (!granted) { PlayerEconomy::Fail(); result.ok = false; return result; }
        }
    }

    // L10 gold: our roll scaled by the tier's gold bonus and the player's Gold Find.
    if (source != Source::Chest)
    {
        double const base = 1.0 + monsterLevel * 2.0;
        double const gold = base * (0.5 + Roll()) * (1.0 + bonus.goldPct / 100.0) * (1.0 + GoldFind(player))
            * (greater ? greater->goldFactor : 1.0);
        result.gold = static_cast<std::uint32_t>(std::clamp(gold, 0.0, 4.0e9));
    }

    // L10 Death's Breath: elites only, and the published figure is gated on
    // level 61+ monsters. Audit row 46: that level is difficulty_tiers.csv's
    // Normal row, which section B made numeric and generates as the
    // dc_numeric_rule deaths_breath_min_monster_level; it is read
    // here rather than repeated.
    unsigned const deathsBreathLevel =
        static_cast<unsigned>(DC::NumericData::Rule("deaths_breath_min_monster_level"));
    bool const deathsBreath = tuning.deathsBreathPct > 0 && monsterLevel >= deathsBreathLevel
        && Roll() * 100.0 < tuning.deathsBreathPct;
    // Sage's Journey 3-piece: the drop pays 1 x the worn powers' factor (2 doubles it); never fewer than the one.
    unsigned const deathsBreathCount = deathsBreath
        ? std::max(1u, static_cast<unsigned>(std::lround(DC::Combat::ItemPowers::DeathsBreathFactor(player)))) : 0;

    // Gold and material together in one account operation. Nothing is reported
    // as delivered until that operation has committed; nested inside a durable
    // source's operation, Finish() reports its health and the source commits.
    PlayerEconomy::Scope rewards(player);
    bool credited = true;
    if (result.gold)
        credited = DC::Economy::Credit(player, DC::Economy::GoldCost(result.gold));
    if (credited && deathsBreath)
        credited = GrantMaterial(player, Currencies[DeathsBreath].entry, deathsBreathCount);
    if (!credited)
        PlayerEconomy::Fail();
    if (!rewards.Finish() || !credited)
    {
        LOG_ERROR("server", "[DC loot] Reward delivery refused for {}: {} gold, {} material",
                  player->GetName(), result.gold, deathsBreathCount);
        result.gold = 0;
        result.ok = false;
        return result;
    }
    if (deathsBreath)
        result.deathsBreath = deathsBreathCount;
    return result;
}

namespace
{
class LootWorld final : public WorldScript
{
public:
    LootWorld() : WorldScript("dc_loot_world", {WORLDHOOK_ON_STARTUP}) { }
    void OnStartup() override
    {
        try
        {
            std::array<Tuning, static_cast<unsigned>(Source::Count)> loaded{};
            std::array<bool, static_cast<unsigned>(Source::Count)> seen{};
            QueryResult result = WorldDatabase.Query(
                "SELECT source, drops_min, drops_max, legendary_base_pct, normal_pct, magic_pct, rare_pct, "
                // 'gem' and 'identify' are pseudo-sources: rows that carry a
                // feature's tunables in this table without being a drop source.
                // They have no drop counts and no rarity split, so the drop
                // loader skips them; their own readers ask for them by name.
                "chest_multiplier, deaths_breath_pct FROM dc_loot_tuning "
                "WHERE source NOT IN ('gem','identify')");
            if (!result)
                throw std::runtime_error("dc_loot_tuning is missing or empty");
            do
            {
                Field* fields = result->Fetch();
                auto source = ParseSource(fields[0].Get<std::string>());
                if (!source)
                    throw std::runtime_error("dc_loot_tuning has an unknown source");
                Tuning tuning;
                tuning.dropsMin = static_cast<unsigned>(fields[1].Get<int64>());
                tuning.dropsMax = static_cast<unsigned>(fields[2].Get<int64>());
                tuning.legendaryBasePct = fields[3].Get<double>();
                tuning.normalPct = fields[4].Get<double>();
                tuning.magicPct = fields[5].Get<double>();
                tuning.rarePct = fields[6].Get<double>();
                tuning.chestMultiplier = fields[7].Get<double>();
                tuning.deathsBreathPct = fields[8].Get<double>();
                loaded[static_cast<unsigned>(*source)] = tuning;
                seen[static_cast<unsigned>(*source)] = true;
            } while (result->NextRow());
            for (bool present : seen)
                if (!present)
                    throw std::runtime_error("dc_loot_tuning is missing a source row");

            // dc_tier_phase is the difficulty module's tier_id -> tier_name map
            // (03-difficulty); it is the only ordering the tier table has.
            if (DC::LaunchTierCount() > MaxLaunchTiers)
                throw std::runtime_error("launch_tier_count is larger than this build's tier array; "
                                         "raise MaxLaunchTiers in dc_loot.cpp and rebuild");
            std::array<TierBonus, MaxLaunchTiers + 1> bonuses{};
            QueryResult tiers = WorldDatabase.Query(
                "SELECT p.tier_id, t.gold_bonus_pct, t.legendary_drop_bonus_pct "
                "FROM dc_tier_phase p JOIN dc_difficulty_tiers t ON t.tier=p.tier_name ORDER BY p.tier_id");
            if (!tiers || tiers->GetRowCount() != DC::LaunchTierCount())
                throw std::runtime_error("dc_tier_phase is missing; apply the 03-difficulty migration first");
            do
            {
                Field* fields = tiers->Fetch();
                unsigned const id = static_cast<unsigned>(fields[0].Get<uint32>());
                if (id < 1 || id > DC::LaunchTierCount())
                    throw std::runtime_error("dc_tier_phase has a tier outside the launch range");
                bonuses[id].goldPct = static_cast<double>(fields[1].Get<int64>());
                bonuses[id].legendaryPct = static_cast<double>(fields[2].Get<int64>());
            } while (tiers->NextRow());

            std::unordered_map<unsigned, std::string> loadedClasses;
            if (QueryResult mapped = WorldDatabase.Query(
                    // class_key, never d3_class: the key is what usable_by and
                    // designated_class are written in, and the predicates below
                    // compare tokens exactly. d3_class is a display label.
                    "SELECT wow_class_id, class_key FROM dc_class_map"))
                do
                {
                    Field* f = mapped->Fetch();
                    loadedClasses[static_cast<unsigned>(f[0].Get<uint32>())] =
                        f[1].Get<std::string>();
                } while (mapped->NextRow());
            if (loadedClasses.empty())
                throw std::runtime_error(
                    "dc_class_map is missing or empty; apply the class catalogue migration");

            std::vector<BaseItem> loadedGenerics, loadedUniques;
            // 05 §3 pool rule 1: base_items.csv keeps every D3Planner patch
            // version of a name and only the latest one may drop.
            // Blacksmith crafted sets never drop, so
            // they are excluded here for every roll (05 §3 craft_only marker), and
            // so are Ethereals and the Horadric Cache's legendaries:
            // DC::RollClass::InDropPool decides.
            QueryResult items = WorldDatabase.Query(
                "SELECT b.entry, b.rarity, b.usable_by, b.item_level, b.designated_class, "
                "COALESCE(t.InventoryType,0), COALESCE(sc.class_key,''), b.pool_version, b.craft_only, b.slot, b.type, "
                "IF(c.item_entry IS NULL,'no','yes') "
                "FROM dc_base_item b "
                "LEFT JOIN item_template t ON t.entry=b.entry "
                "LEFT JOIN dc_set_class sc ON sc.set_name=b.set_name "
                "LEFT JOIN (SELECT DISTINCT item_entry FROM dc_bounties_cache_legendary) c ON c.item_entry=b.entry");
            if (!items)
                throw std::runtime_error("dc_base_item or dc_bounties_cache_legendary is missing; apply the 05-items "
                                         "migration and bounties_0003_caches.sql first");
            do
            {
                Field* fields = items->Fetch();
                BaseItem item;
                item.entry = fields[0].Get<uint32>();
                std::string const rarity = fields[1].Get<std::string>();
                // The one place a row is kept out of every drop (Ethereals and the cache's legendaries included).
                if (!DC::RollClass::InDropPool(rarity, fields[7].Get<std::string>(), fields[8].Get<std::string>(),
                                               fields[11].Get<std::string>()))
                    continue;
                std::string const usable = fields[2].Get<std::string>();
                item.itemLevel = static_cast<unsigned>(fields[3].Get<int64>());
                std::string const designation = fields[4].Get<std::string>();
                // Stored as the sheet wrote them; DC::RollClass::Eligible
                // is where pool rule 2 is applied, per roll class.
                item.usable = usable;
                item.designation = designation;
                item.setClass = fields[6].Get<std::string>();
                item.rarity = rarity;
                item.inventoryType = static_cast<unsigned>(fields[5].Get<uint32>());
                item.slot = fields[9].Get<std::string>();
                item.type = fields[10].Get<std::string>();
                (rarity.empty() ? loadedGenerics : loadedUniques).push_back(item);
            } while (items->NextRow());

            // The weight and the lowest tier of a base that has its own (the follower relics, followers_0006_relic_rolls.sql);
            // every other base weighs tunables loot/ordinary_drop_weight and drops at any tier.
            QueryResult weights = WorldDatabase.Query("SELECT item_entry, drop_weight, min_tier FROM dc_follower_relic_roll");
            if (!weights)
                throw std::runtime_error("dc_follower_relic_roll is missing or empty; apply followers_0006_relic_rolls.sql");
            do
            {
                Field* fields = weights->Fetch();
                for (BaseItem& item : loadedUniques)
                    if (item.entry == fields[0].Get<uint32>())
                    {
                        item.weight = fields[1].Get<uint32>();
                        item.minTier = fields[2].Get<uint32>();
                    }
            } while (weights->NextRow());

            if (!CharacterDatabase.Query("SELECT COUNT(*) FROM dc_loot_buffer") ||
                !CharacterDatabase.Query("SELECT COUNT(*) FROM dc_character_flags"))
                throw std::runtime_error("dc_loot_buffer/dc_character_flags migrations have not been applied");
            if (!CharacterDatabase.Query("SELECT COUNT(rarity) FROM dc_loot_buffer"))
                throw std::runtime_error("dc_loot_buffer is missing its shell columns; apply loot_0004_buffer_shell.sql");
            if (!CharacterDatabase.Query("SELECT COUNT(*) FROM dc_item_unidentified"))
                throw std::runtime_error("dc_item_unidentified is missing; apply items_0003_unidentified.sql");
            if (!CharacterDatabase.Query("SELECT COUNT(quality_tier) FROM dc_loot_buffer"))
                throw std::runtime_error("dc_loot_buffer has no quality_tier; apply loot_0011_quality_tier.sql");
            if (!CharacterDatabase.Query("SELECT COUNT(roll_class) FROM dc_loot_buffer") ||
                !CharacterDatabase.Query("SELECT COUNT(roll_class) FROM dc_item_unidentified"))
                throw std::runtime_error("dc_loot_buffer/dc_item_unidentified have no roll_class; "
                                         "apply loot_0007_roll_class.sql");

            // The shells, and the on/off switch for the whole feature.
            std::map<std::pair<unsigned, unsigned>, std::uint32_t> loadedShells;
            if (QueryResult shellRows = WorldDatabase.Query(
                    "SELECT entry, InventoryType, Quality FROM item_template WHERE spellid_1={}",
                    DC::Items::IdentifyItemSpell()))
                do
                {
                    Field* f = shellRows->Fetch();
                    loadedShells[{f[1].Get<uint32>(), f[2].Get<uint32>()}] = f[0].Get<uint32>();
                } while (shellRows->NextRow());
            bool loadedSwitch = false;
            if (QueryResult toggle = WorldDatabase.Query(
                    "SELECT unidentified_drops FROM dc_loot_tuning WHERE source='identify'"))
                loadedSwitch = (*toggle)[0].Get<double>() > 0.0;
            if (loadedSwitch && loadedShells.empty())
                throw std::runtime_error("unidentified_drops is on but no shell templates exist; "
                                         "apply items_0007_unidentified_shells.sql");

            std::lock_guard<std::mutex> lock(dataMutex);
            shells = std::move(loadedShells);
            unidentifiedDrops = loadedSwitch;
            tunings = loaded;
            tierBonuses = bonuses;
            generics = std::move(loadedGenerics);
            uniques = std::move(loadedUniques);
            classMap = std::move(loadedClasses);
            dataReady = true;
            LOG_INFO("server.loading", "[DC loot] Loaded {} tuning rows, {} tiers, {} generic and {} unique base items, {} playable class(es)",
                     tunings.size(), DC::LaunchTierCount(), generics.size(), uniques.size(), classMap.size());
        }
        catch (std::exception const& error)
        {
            LOG_ERROR("server", "D3 loot startup failed: {}. Loot rolling is disabled.", error.what());
        }
    }
};

class LootPlayer final : public PlayerScript
{
public:
    LootPlayer() : PlayerScript("dc_loot_player", {
        PLAYERHOOK_ON_CREATURE_KILL, PLAYERHOOK_ON_LOGIN,
        PLAYERHOOK_ON_AFTER_MOVE_ITEM_FROM_INVENTORY, PLAYERHOOK_ON_BEFORE_LOOT_MONEY}) { }

    // L12 personal loot: every party member in loot range rolls independently.
    void OnPlayerCreatureKill(Player* killer, Creature* killed) override
    {
        if (!killer || !D3Creature(killed))
            return;
        // An Illusionist duplicate is not a real kill: no loot, and the rift
        // kill hook already refuses it for progress (13-elite-affixes §10).
        if (DC::Rifts::IsIllusion(killed))
            return;
        // Greater Rift rule 1: only the Guardian drops loot - no item, gold or gem roll
        // for any other monster of the run.
        if (DC::Rifts::GreaterRiftNoLoot(killed))
            return;
        // A rift pack is an elite kill even though its template rank cannot say
        // so: promotion swaps the spawn for a generated clone entry, and the
        // rift is what knows it did (09 §2 step 2).
        unsigned riftTier = 0;
        bool const inRift = DC::Rifts::InRift(killed, riftTier);
        Source const source = killed->IsDungeonBoss() || killed->isWorldBoss()
            ? Source::Boss
            : ((killed->isElite() || DC::Rifts::IsPromotedElite(killed)) ? Source::Elite
                                                                        : Source::Normal);
        unsigned const level = killed->GetLevel();
        unsigned const tier = inRift ? riftTier : TierOf(killed);
        std::uint32_t const entry = killed->GetEntry();

        auto rollFor = [&](Player* member)
        {
            if (D3Class(member).empty())
                return;
            RollLoot(member, source, level, tier, inRift,"",killed);
            if (std::uint32_t gem = DC::Crafting::RollGemEntry(level, tier))
            {
                DeliverGemDrop(member, gem, level, Name(source), tier, killed, CorpseDelivery(killed),
                               GroundDeliveryEnabled(), killed->GetPosition());
                if (std::uint32_t const extra = BrokenCrownGem(member, gem))
                    DeliverGemDrop(member, extra, level, Name(source), tier, killed, CorpseDelivery(killed),
                                   GroundDeliveryEnabled(), killed->GetPosition());
            }
            // L11: the first time a character kills an act boss, one legendary
            // is guaranteed on top of the normal roll.
            if (source == Source::Boss)
                FirstBossKill(member, entry, level,killed);
        };

        if (Group* group = killer->GetGroup())
        {
            for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
            {
                Player* member = itr->GetSource();
                if (member && member->IsInMap(killed) && member->IsAtGroupRewardDistance(killed))
                    rollFor(member);
            }
        }
        else
            rollFor(killer);
    }

    void OnPlayerLogin(Player* player) override { LearnHeldCurrencies(player); DeliverBuffered(player); }
    // A slot may have freed; L5 says the buffer delivers as soon as one does.
    void OnPlayerAfterMoveItemFromInventory(Player* player, Item*, uint8, uint8, bool) override
    {
        DeliverBuffered(player);
    }
    // L10: WoW's own creature gold is replaced by our roll.
    void OnPlayerBeforeLootMoney(Player* player, ::Loot* loot) override
    {
        if (loot && loot->loot_type == LOOT_CORPSE &&
            (D3NativeLoot(player, loot, StockSource::Creature) ||
             D3NativeLoot(player, loot, StockSource::Chest)))
            loot->gold = 0;
    }
};

// The native death path generates gold after FillLoot, so clear it after that
// path finishes and before any corpse loot window can be shown.
class LootDeath final : public UnitScript
{
public:
    LootDeath() : UnitScript("dc_loot_death", true, {UNITHOOK_ON_UNIT_DEATH}) { }
    void OnUnitDeath(Unit* unit, Unit*) override
    {
        Creature* creature = unit ? unit->ToCreature() : nullptr;
        if (D3Creature(creature))
        {
            // A corpse that holds drops keeps its placeholder: it is the stock window.
            if (CorpseHoldsRows(creature))
            {
                KeepCorpseLootable(creature);
                return;
            }
            creature->loot.gold = 0;
            if (creature->loot.isLooted() && creature->HasDynamicFlag(UNIT_DYNFLAG_LOOTABLE))
            {
                creature->RemoveDynamicFlag(UNIT_DYNFLAG_LOOTABLE);
                creature->AllLootRemovedFromCorpse();
            }
        }
    }
};

// Player::SendLoot has filled native chest loot immediately before changing
// GO_READY to GO_ACTIVATED. Claim that activation once, including party rolls,
// before the core sends the window. GO_READY starts a fresh chest lifecycle.
class LootChest final : public AllGameObjectScript
{
public:
    LootChest() : AllGameObjectScript("dc_loot_chest") { }
    void OnGameObjectRemoveWorld(GameObject* go) override
    {
        if (!go)
            return;
        std::lock_guard<std::mutex> lock(mutex);
        claimed.erase(go->GetGUID());
    }
    void OnGameObjectLootStateChanged(GameObject* go, uint32 state, Unit* user) override
    {
        if (!go)
            return;
        if (state == GO_READY)
        {
            std::lock_guard<std::mutex> lock(mutex);
            claimed.erase(go->GetGUID());
            return;
        }
        if (state != GO_ACTIVATED || !D3Chest(go))
            return;
        go->loot.gold = 0;
        Player* opener = user ? user->ToPlayer() : nullptr;
        if (!opener)
            return;
        {
            std::lock_guard<std::mutex> lock(mutex);
            if (!claimed.insert(go->GetGUID()).second)
                return;
        }
        unsigned riftTier = 0, riftPlayers = 0;
        bool const inRift = DC::Rifts::ScalingContext(go->FindMap(), riftTier, riftPlayers);
        unsigned const tier = inRift ? riftTier : go->GetPhaseMask();
        Position const dropOrigin = go->GetPosition();
        auto rollFor = [&](Player* member)
        {
            if (!D3Class(member).empty())
                RollLoot(member, Source::Chest, member->GetLevel(), tier, inRift, "", nullptr, &dropOrigin);
        };
        if (Group* group = opener->GetGroup())
        {
            for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
            {
                Player* member = itr->GetSource();
                if (member && member->IsInMap(go) && member->IsAtGroupRewardDistance(go))
                    rollFor(member);
            }
        }
        else
            rollFor(opener);
    }
private:
    std::mutex mutex;
    std::set<ObjectGuid> claimed;
};

// A parent creature/chest row is refused before it can enter a reference store.
// Other stores, including skinning and pickpocketing on the same creature, keep
// stock rolls. Equal-chance groups bypass OnItemRoll and need their own gate.
class LootSuppression final : public GlobalScript
{
public:
    LootSuppression() : GlobalScript("dc_loot_suppression", {
        GLOBALHOOK_ON_ITEM_ROLL, GLOBALHOOK_ON_BEFORE_LOOT_EQUAL_CHANCED}) { }
    bool OnItemRoll(Player const* player, LootStoreItem const*, float&, ::Loot& loot, LootStore const& store) override
    {
        return !Suppress(player, loot, store);
    }
    bool OnBeforeLootEqualChanced(Player const* player, LootStoreItemList, ::Loot& loot,
                                   LootStore const& store) override
    {
        return !Suppress(player, loot, store);
    }
private:
    static bool Suppress(Player const* player, ::Loot const& loot, LootStore const& store)
    {
        if (&store == &LootTemplates_Creature)
            return D3NativeLoot(player, &loot, StockSource::Creature);
        if (&store == &LootTemplates_Gameobject)
            return D3NativeLoot(player, &loot, StockSource::Chest);
        return false;
    }
};

class LootCommand final : public CommandScript
{
public:
    LootCommand() : CommandScript("dc_loot_command") { }
    Acore::ChatCommands::ChatCommandTable GetCommands() const override
    {
        using namespace Acore::ChatCommands;
        static ChatCommandTable loot = {
            {"loot", HandleLoot, SEC_ADMINISTRATOR, Console::No},
            {"buffer", HandleBuffer, SEC_ADMINISTRATOR, Console::No},
        };
        static ChatCommandTable root = {{"dc", loot}};
        return root;
    }

    static bool HandleLoot(ChatHandler* handler, std::string sourceName, Optional<uint32> monsterLevel,
                           Optional<uint32> tier)
    {
        Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
        if (!player)
            return false;
        auto source = ParseSource(sourceName);
        if (!source)
        {
            handler->SendSysMessage("Usage: .dc loot <normal|elite|boss|rift_guardian|chest> [level] [tier]");
            return false;
        }
        Result result = RollLoot(player, *source, monsterLevel.value_or(70), tier.value_or(1), false);
        if (!result.ok)
        {
            handler->SendSysMessage("Loot data is not loaded, or a reward was refused; see the server log.");
            return false;
        }
        std::ostringstream line;
        line.imbue(std::locale::classic());
        line << Name(*source) << ": " << result.rolled << " item(s) - "
             << result.normal << " normal, " << result.magic << " magic, " << result.rare << " rare, "
             << result.legendary << " legendary; " << result.delivered << " to bag, "
             << result.buffered << " buffered, " << result.grounded << " on ground, " << result.oncorpse << " on corpse; " << result.gold << " gold";
        if (result.deathsBreath)
            line << "; +" << result.deathsBreath << " Death's Breath";
        handler->SendSysMessage(line.str());
        LOG_INFO("server.loading", "[DC loot output] {}", line.str());
        return true;
    }

    static bool HandleBuffer(ChatHandler* handler)
    {
        Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
        if (!player)
            return false;
        QueryResult result = CharacterDatabase.Query(
            "SELECT base_item, item_level, TIMESTAMPDIFF(SECOND, NOW(), expires_at),id,kind,content_kind,COALESCE(carrier_guid,0) FROM dc_loot_buffer "
            "WHERE guid={} ORDER BY id", player->GetGUID().GetRawValue());
        if (!result)
        {
            handler->SendSysMessage("Loot buffer is empty.");
            return true;
        }
        do
        {
            Field* fields = result->Fetch();
            handler->PSendSysMessage("row {}: {} / {}, base item {}, ilvl {}, {} s left, carrier {}",
                                     fields[3].Get<uint64>(),fields[4].Get<std::string>(),fields[5].Get<std::string>(),
                                     fields[0].Get<uint32>(),fields[1].Get<uint16>(),fields[2].Get<int32>(),fields[6].Get<uint64>());
        } while (result->NextRow());
        return true;
    }
};
}

void RegisterScripts()
{
    RegisterGroundLootScripts();
    RegisterCorpseLootScripts();
    RegisterKadalaScripts();
    new LootWorld();
    new LootPlayer();
    new LootDeath();
    new LootChest();
    new LootSuppression();
    new LootCommand();
}
}