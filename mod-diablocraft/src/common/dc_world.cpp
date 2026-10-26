// Constant (102100): Starter Satchel item identity; Content identifier; keep tied to CSV.
// Constant (0.01f): Hub positional float tolerance; Explicitly round-off tolerance, not gameplay radius.
// Constant (0.0001f): Hub orientation float tolerance; Round-off tolerance.
// Constant (8690): Hearthstone spell removed from characters; Stock spell identity.
// Constant (6948): Hearthstone item removed from inventory; Stock item identity, repeated on same line.
#include "dc_world.h"
#include "dc_world_outfits.h"
#include "dc_account_economy.h"
#include "dc_economy.h"
#include "dc_tunables.h"
#include "dc_numeric_data.h"
#include "../classes/dc_classes.h"
#include "../difficulty/dc_difficulty.h"
#include "../hardcore/dc_hardcore.h"
#include "../items/dc_items.h"
#include "../stats/dc_stats.h"
#include "../paragon/dc_paragon.h"
#include "Chat.h"
#include "Config.h"
#include "DatabaseEnv.h"
#include "DBCStores.h"
#include "Item.h"
#include "Log.h"
#include "Mail.h"
#include "Map.h"
#include "MapMgr.h"
#include "ObjectMgr.h"
#include "Opcodes.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "ScriptedGossip.h"
#include "Spell.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "WorldPacket.h"
#include "WorldSession.h"
#include <algorithm>
#include <cmath>
#include <map>
#include <limits>
#include <mutex>
#include <random>
#include <sstream>
#include <set>
#include <stdexcept>
#include <vector>

namespace DC::World
{
namespace
{
// data/tunables/bags.csv owns the Horadric Satchel template. Starter bags
// are a separate step from the CSV-owned equipment kit in the same grant path.
constexpr uint32 SatchelEntry = 102100;
constexpr uint32 TesterCofferEntry = 910018; // generated hub creature template identity
uint32 StarterNumber(char const* category, char const* name, uint32 minimum, uint32 maximum)
{
    double const value = Tunables::Get(category, name);
    if (!std::isfinite(value) || std::floor(value) != value || value < minimum || value > maximum)
        throw std::runtime_error(std::string("Invalid starter setting: ") + category + "/" + name);
    return static_cast<uint32>(value);
}

uint32 SatchelsPerCharacter()
{
    return StarterNumber("economy", "starter_satchel_count", 0,
                         INVENTORY_SLOT_BAG_END - INVENTORY_SLOT_BAG_START);
}

struct KitSlot { uint8 slot; std::string rarity; std::vector<uint32> candidates; };
struct ClassStart
{
    std::string key, name;
    std::vector<KitSlot> kit;
    std::map<uint32, uint32> skills;
};
std::map<uint8, ClassStart> classStarts;
// The WoW classes an account may create: every row of dc_class_start (class_starts.csv). Read before the kit data
// so that a start that cannot load still leaves a character login can resume (see CanAccountCreateCharacter).
std::set<uint8> creatableClasses;
WorldLocation hub;
std::map<std::string, WorldLocation> hubPoints;
uint32 hubArea = 0;
bool ready = false;

bool AtHubSpawn(Player const* player)
{
    // Tolerance only absorbs float storage round-off, not a gameplay radius.
    return player->GetMapId() == hub.GetMapId() && !player->GetInstanceId() &&
        player->GetExactDist(&hub) < 0.01f &&
        std::abs(player->GetOrientation() - hub.GetOrientation()) < 0.0001f;
}

void MoveToHubSpawn(Player* player, char const* reason)
{
    if (!ready) return;
    player->SetHomebind(hub, hubArea);
    if (!AtHubSpawn(player) && !player->TeleportTo(hub))
    {
        LOG_ERROR("server", "[DC world {}] Hub teleport failed for {}", reason, player->GetName());
        if (!player->GetSession()->PlayerLogout())
            ChatHandler(player->GetSession()).SendSysMessage("Could not move you to the hub. Contact the GM.");
    }
}

void CommitCharacterSave(CharacterDatabaseTransaction const& transaction)
{
    // Player::SaveToDB uses prepared statements registered on async connections.
    // Wait once during setup so inventory and the recovery marker are durable
    // before granting the next slot. This never runs per update or per hit.
    if (!CharacterDatabase.AsyncCommitTransaction(transaction).m_future.get())
        throw std::runtime_error("Character inventory transaction failed");
}

void SaveStart(Player* player, CharacterDatabaseTransaction const& transaction)
{
    if (player->GetSession()->EconomyAborted() || player->IsBeingTeleportedFar())
        throw std::runtime_error("Character save is unavailable; start deferred");
    player->SaveToDB(transaction, false, false);
    auto* bind = CharacterDatabase.GetPreparedStatement(CHAR_UPD_PLAYER_HOMEBIND);
    bind->SetData(0, hub.GetMapId());
    bind->SetData(1, hubArea);
    bind->SetData(2, hub.GetPositionX());
    bind->SetData(3, hub.GetPositionY());
    bind->SetData(4, hub.GetPositionZ());
    bind->SetData(5, player->GetGUID().GetCounter());
    transaction->Append(bind);
}

bool BagsGranted(uint32 guid)
{
    return bool(CharacterDatabase.Query("SELECT granted FROM dc_character_bag_grant WHERE guid={}", guid));
}

// The bags are their own step in the starter path, not kit rows: two Satchels
// placed straight into bag slots 1 and 2, so a new character opens with
// 22+22+16 cells. An occupied slot is skipped, never displaced.
void GrantStarterBags(Player* player, uint32 guid)
{
    if (BagsGranted(guid)) return;
    uint32 const target = SatchelsPerCharacter();
    uint32 granted = 0;
    for (uint32 n = 0; n < target; ++n)
    {
        uint8 const slot = uint8(INVENTORY_SLOT_BAG_START + n);
        if (player->GetItemByPos(INVENTORY_SLOT_BAG_0, slot)) continue;
        uint16 dest;
        auto result = player->CanEquipNewItem(slot, dest, SatchelEntry, false);
        if (result != EQUIP_ERR_OK)
            throw std::runtime_error("Cannot equip starter bag slot " + std::to_string(slot) + ": " + std::to_string(result));
        if (!player->EquipNewItem(dest, SatchelEntry, true))
            throw std::runtime_error("Starter bag creation failed for slot " + std::to_string(slot));
        ++granted;
    }
    // Same rule as a kit slot: the inventory and the record that stops a second
    // grant are committed together, so a reconnect can never hand out a third.
    auto trans = CharacterDatabase.BeginTransaction();
    SaveStart(player, trans);
    trans->Append("INSERT INTO dc_character_bag_grant(guid,granted) VALUES({},{})",guid,granted);
    CommitCharacterSave(trans);
    LOG_INFO("server.loading","[DC world bags] {} starter bags granted={} entry={}",player->GetName(),granted,SatchelEntry);
}

// One-time sweep for a character that finished its start before the bags
// existed. It only ever adds: no other bag is touched, moved
// or deleted, and the Satchels arrive loose in the bags, because the
// old 24-slot bags are cleared by hand and these are equipped by hand.
void SweepBags(Player* player)
{
    auto guid = player->GetGUID().GetCounter();
    if (BagsGranted(guid)) return;
    try
    {
        // Bank included: a Satchel parked there is still one the character has,
        // so the sweep tops up to the configured count without duplicate grants.
        uint32 const held = player->GetItemCount(SatchelEntry, true);
        uint32 const target = SatchelsPerCharacter();
        uint32 granted = 0;
        while (held + granted < target)
        {
            ItemPosCountVec destination;
            if (player->CanStoreNewItem(NULL_BAG, NULL_SLOT, destination, SatchelEntry, 1) != EQUIP_ERR_OK) break;
            Item* bag = player->StoreNewItem(destination, SatchelEntry, true);
            if (!bag) break;
            player->SendNewItem(bag, 1, false, false, false, true);
            ++granted;
        }
        if (held + granted < target)
        {
            // Nothing is recorded, so the next login tries again; the recount
            // above is what stops that retry exceeding the configured count.
            ChatHandler(player->GetSession()).SendSysMessage("Free a bag slot and log in again to receive your Horadric Satchels.");
            LOG_INFO("server","[DC world bags] {} sweep deferred: held={} granted={}",player->GetName(),held,granted);
            return;
        }
        auto trans = CharacterDatabase.BeginTransaction();
        player->SaveToDB(trans,false,false);
        trans->Append("INSERT INTO dc_character_bag_grant(guid,granted) VALUES({},{})",guid,granted);
        CommitCharacterSave(trans);
        if (granted)
            ChatHandler(player->GetSession()).PSendSysMessage("You have received {} Horadric Satchel(s).",granted);
        LOG_INFO("server","[DC world bags] {} sweep held={} granted={}",player->GetName(),held,granted);
    }
    catch (std::exception const& error)
    {
        LOG_ERROR("server","[DC world bags] {} sweep stopped: {}",player->GetName(),error.what());
    }
}

bool Usable(std::string const& value, std::string const& classKey)
{
    if (value.empty()) return true;
    std::istringstream input(value);
    std::string token;
    while (std::getline(input, token, ';')) if (token == classKey) return true;
    return false;
}

bool RemovedSpell(SpellInfo const* info)
{
    return info && (info->Id == 8690 || info->HasAura(SPELL_AURA_MOUNTED) ||
        info->HasAura(SPELL_AURA_FLY) || info->HasAura(SPELL_AURA_MOD_INCREASE_MOUNTED_FLIGHT_SPEED) ||
        info->HasEffect(SPELL_EFFECT_SEND_TAXI) || info->HasEffect(SPELL_EFFECT_STUCK));
}

void RemoveTravel(Player* player)
{
    std::vector<uint32> remove;
    for (auto const& [id, state] : player->GetSpellMap())
        if (state && state->State != PLAYERSPELL_REMOVED && RemovedSpell(sSpellMgr->GetSpellInfo(id))) remove.push_back(id);
    for (auto id : remove) player->removeSpell(id, SPEC_MASK_ALL, false);
    player->RemoveAurasByType(SPELL_AURA_MOUNTED);
    player->RemoveAurasByType(SPELL_AURA_FLY);
    player->RemoveAurasByType(SPELL_AURA_MOD_INCREASE_MOUNTED_FLIGHT_SPEED);
    player->SetCanFly(false);
    player->SetTaxiCheater(false);
    player->DestroyItemCount(6948, player->GetItemCount(6948, true), true);
    player->UpdatePvP(false, true);
}

// The class's start profile (class_starts.csv), or null. A class without one
// gets no starter kit and no proficiency repair, and says so once in the log
// rather than silently; its mode and account
// setup run regardless (Start).
ClassStart const* ProfileFor(Player const* player)
{
    auto profile = classStarts.find(player->getClass());
    if (profile != classStarts.end())
        return &profile->second;
    static std::mutex namedMutex;
    static std::set<unsigned> named;
    unsigned const wowClass = player->getClass();
    std::lock_guard<std::mutex> lock(namedMutex);
    if (named.insert(wowClass).second)
        LOG_WARN("server", "[DC world] WoW class {} has no dc_class_start profile: no starter kit and no "
                           "equipment proficiency repair; mode and account setup still run", wowClass);
    return nullptr;
}

void GrantEquipmentSkills(Player* player)
{
    if (!ready) return;
    auto const* profile = ProfileFor(player);
    if (!profile) return;
    // Native proficiency repair also covers existing characters on login.
    for (auto const& [spell, skill] : profile->skills)
    {
        player->learnSpell(spell);
        player->LearnDefaultSkill(skill, 0);
    }
}

// Which logins still owe this character its start (08 §5).
//
// A completed row is done. An incomplete one resumes, which is the reconnect
// case Start's per-slot record was built for. No row at all is the one the
// creation or first-login path can leave behind: Start returns before inserting it if
// Hardcore::EnsureMode's write does not land, and by then the core has already
// cleared AT_LOGIN_FIRST - it does that at CharacterHandler.cpp:1139, between
// OnPlayerLogin (:1136) and OnPlayerFirstLogin (:1141) - so OnPlayerFirstLogin
// will never fire for this character again and nothing else would retry. The
// flag is still set while this hook runs on a genuine first login, which is
// what keeps the retry from running the start twice, once here and once from
// OnPlayerFirstLogin a few lines later.
bool StartOwed(Player* player, QueryResult const& state)
{
    if (state) return !(*state)[0].Get<uint8>();
    return !player->HasAtLoginFlag(AT_LOGIN_FIRST);
}

// The part of a start every class gets, with or without a start profile
// (GitHub #69). It used to sit behind Start's
// profile lookup, so a class with no profile - the Wizard - never had a mode
// written and its account economy stayed "pending": no shared gold, no shared
// materials. A character that already has a mode needs nothing here: the
// economy's own login hook (dc_account_economy.cpp OnPlayerLogin) resolved it
// on this login, before any of this ran.
bool Setup(Player* player, bool creation = false)
{
    // A failed resolution there aborts the session's economy, and the start
    // still waits for a login where the account resolved, as it always has.
    if (creation)
        return Hardcore::EnsureMode(player) && AccountEconomy::ResolveCreation(player);
    if (Hardcore::ModeOf(player) != Hardcore::Mode::Unchosen)
        return !player->GetSession()->EconomyAborted();
    // 11 H4: Normal and Hardcore are separate realms, so the
    // mode is written here from Diablocraft.Hardcore.Enable instead of being
    // asked. Nothing waits: the row and the level-70 kit are the same call, and
    // there is no prompt to answer. The row is still permanent, so a character
    // that has one keeps it and EnsureMode writes nothing.
    if (!Hardcore::EnsureMode(player))
        return false;
    // ...and then the account is resolved again, because the first resolution
    // of this login happened before the mode existed. Every OnPlayerLogin hook
    // runs at CharacterHandler.cpp:1136, before OnPlayerFirstLogin at :1141, so
    // AccountEconomy's own resolution (dc_account_economy.cpp:740-749) saw an
    // Unchosen character: that path names the contribution "pending"
    // (:866-867), ClaimPending returns without crediting it (:500-501), the
    // money mirror is left at 0 and FinalizeLoad is skipped (:905-907). The
    // prompt used to pay for this by resolving again from HandleChoose before
    // it called StartCharacter, and this is that call, now that the mode is
    // durable and before the character has been given anything. A failure
    // leaves no dc_character_start row, so StartOwed retries it next login.
    if (!AccountEconomy::ResolvePending(player))
    {
        LOG_ERROR("server", "[DC world kit] {} (guid {}): account resolution failed after the mode was written; "
                            "the start is deferred to the next login",
                  player->GetName(), player->GetGUID().GetCounter());
        return false;
    }
    return true;
}

struct StartResume : DataMap::Base { bool waitingForMap = false; };

void Start(Player* player, bool creation = false)
{
    if (!ready)
        return;
    auto guid = player->GetGUID().GetCounter();
    auto state = CharacterDatabase.Query("SELECT complete FROM dc_character_start WHERE guid={}", guid);
    if (state && (*state)[0].Get<uint8>()) return;
    // Mode and account first, for every class; only the kit below needs a profile.
    if (!Setup(player, creation))
        return;
    // A far transfer must finish before native SaveToDB can append a save.
    if (player->IsBeingTeleportedFar())
    {
        player->CustomData.GetDefault<StartResume>("DCStartResume")->waitingForMap = true;
        return;
    }
    auto const* profile = ProfileFor(player);
    if (!profile)
        return;
    auto const& kit = profile->kit;
    try
    {
        uint32 const startingLevel = StarterNumber("monsters", "starting_character_level", 1, NumericData::MaximumLevel());
        uint32 const itemLevel = StarterNumber("crafting", "starter_item_level", 1, NumericData::MaximumLevel());
        // Validate tunables before removing the stock outfit or writing progress.
        SatchelsPerCharacter();
        if (!state)
        {
            // Only called for creation, first login, or an incomplete start.
            // Remove the stock outfit before rolling, never an existing kit.
            for (uint8 slot = EQUIPMENT_SLOT_START; slot < INVENTORY_SLOT_ITEM_END; ++slot)
                if (player->GetItemByPos(INVENTORY_SLOT_BAG_0, slot)) player->DestroyItem(INVENTORY_SLOT_BAG_0, slot, true);
            auto trans = CharacterDatabase.BeginTransaction();
            trans->Append("INSERT INTO dc_character_start(guid,complete) VALUES({},0)", guid);
            SaveStart(player, trans);
            CommitCharacterSave(trans);
        }
        if (creation)
        {
            // Player::Create already owns a map, but is not in world. Reuse its
            // native initialization sequence; GiveLevel invokes login-only stat
            // hooks and TeleportTo would wait for a client transfer acknowledgement.
            player->SetLevel(startingLevel);
            // SetLevel never touches the reach-level criteria (only GiveLevel does), and Player::Create
            // checked them at level 1, so a new character had no achievement and the client kept the
            // achievements window shut. The start's own SaveToDB stores what this earns.
            player->UpdateAchievementCriteria(ACHIEVEMENT_CRITERIA_TYPE_REACH_LEVEL);
            player->InitStatsForLevel();
            player->InitTalentForLevel();
            player->InitTaxiNodesForLevel();
            player->InitGlyphsForLevel();
            player->UpdateAllStats();
            Map* map = sMapMgr->CreateMap(hub.GetMapId(), player);
            if (!map) throw std::runtime_error("Hub map is unavailable");
            if (player->FindMap()) player->ResetMap();
            player->SetMap(map);
            player->Relocate(hub);
            player->setCinematic(1);
        }
        else
        {
            player->GiveLevel(startingLevel);
            if (!AtHubSpawn(player) && !player->TeleportTo(hub))
                throw std::runtime_error("Hub teleport failed");
            if (player->IsBeingTeleportedFar())
            {
                player->CustomData.GetDefault<StartResume>("DCStartResume")->waitingForMap = true;
                return;
            }
        }
        if (player->GetLevel() != startingLevel) throw std::runtime_error("Starting level was refused");
        player->SetHomebind(hub, hubArea);
        std::string error;
        if (!Difficulty::SelectTier(player, 1, error)) throw std::runtime_error(error);
        auto savedTier = CharacterDatabase.Query("SELECT tier FROM dc_character_tier WHERE guid={}", guid);
        if (!savedTier || (*savedTier)[0].Get<uint8>() != 1)
            throw std::runtime_error("Starting tier did not persist");
        uint32 const paragon = StarterNumber("paragon", "starting_paragon_level", 0, UINT32_MAX);
        if (!Paragon::EnsureStartingLevel(player, paragon, error)) throw std::runtime_error(error);
        // A class with no skills yet is not Playable and has no bar to write.
        if (Classes::Playable(player))
        {
            if (!Classes::InitializeStarterBar(player, error)) throw std::runtime_error(error);
            if (Classes::Bar(player).size() != Classes::ActiveSlots())
                throw std::runtime_error("Starter bar did not persist");
        }
        RemoveTravel(player);
        // Proficiencies remain ordinary core skills and auto-max through conf.
        GrantEquipmentSkills(player);
        static thread_local std::mt19937 engine{std::random_device{}()};
        for (auto const& entry : kit)
        {
            if (CharacterDatabase.Query("SELECT item_guid FROM dc_character_starter_item WHERE guid={} AND slot={}", guid, entry.slot)) continue;
            uint32 base = entry.candidates[std::uniform_int_distribution<std::size_t>(0,entry.candidates.size()-1)(engine)];
            auto trans = CharacterDatabase.BeginTransaction();
            auto staged = Items::StageRoll(player, base, itemLevel, entry.rarity, trans);
            Item* item = staged ? staged->GetItem() : nullptr;
            if (!item) throw std::runtime_error("Starter item roll failed for slot " + std::to_string(entry.slot));
            bool baggedOffhand = entry.slot == EQUIPMENT_SLOT_OFFHAND && player->GetItemByPos(INVENTORY_SLOT_BAG_0,EQUIPMENT_SLOT_MAINHAND) &&
                player->GetItemByPos(INVENTORY_SLOT_BAG_0,EQUIPMENT_SLOT_MAINHAND)->GetTemplate()->InventoryType == INVTYPE_2HWEAPON;
            if (!baggedOffhand)
            {
                uint16 dest;
                auto result = player->CanEquipItem(entry.slot, dest, item, false);
                if (result != EQUIP_ERR_OK)
                {
                    throw std::runtime_error("Cannot equip starter slot " + std::to_string(entry.slot) + ": " + std::to_string(result));
                }
                // StageRoll publishes the native item update only after commit.
                player->RemoveItem(item->GetBagSlot(),item->GetSlot(),false);
                player->EquipItem(dest,item,false);
            }
            // Save the item/inventory and progress together. A reconnect resumes
            // incomplete slots without giving the completed slots twice.
            SaveStart(player, trans);
            trans->Append("INSERT INTO dc_character_starter_item(guid,slot,item_guid) VALUES({},{},{})",guid,entry.slot,item->GetGUID().GetCounter());
            CommitCharacterSave(trans);
            staged->Publish();
            if (!creation) Items::RefreshContributions(player, item);
            LOG_INFO("server.loading","[DC world kit] {} slot={} entry={} item={} equipped={}",player->GetName(),entry.slot,base,item->GetGUID().GetCounter(),!baggedOffhand);
        }
        GrantStarterBags(player, guid);
        if (!creation) Stats::Recompute(player);
        player->SetHealth(player->GetMaxHealth());
        auto trans = CharacterDatabase.BeginTransaction();
        SaveStart(player, trans);
        trans->Append("UPDATE dc_character_start SET complete=1 WHERE guid={}",guid);
        CommitCharacterSave(trans);
        if (!creation) ChatHandler(player->GetSession()).PSendSysMessage("Welcome to the Sanctum of Torment. Your level-{} {} and starter kit are ready.", startingLevel, profile->name);
        LOG_INFO("server.loading","[DC world start] {} level={} map={} tier=1 kit={} complete",player->GetName(),player->GetLevel(),hub.GetMapId(),kit.size());
    }
    catch (std::exception const& error)
    {
        LOG_ERROR("server","[DC world start] {} stopped: {}",player->GetName(),error.what());
        if (!creation) ChatHandler(player->GetSession()).SendSysMessage("Character setup stopped; contact the GM. Your completed starter slots are saved.");
    }
}

class HubWorld final : public WorldScript
{
public:
    HubWorld() : WorldScript("dc_hub_world",{WORLDHOOK_ON_STARTUP}) { }
    void OnStartup() override
    {
        try
        {
            auto position=WorldDatabase.Query("SELECT map_id,area_id,x,y,z,o FROM dc_world_hub_point WHERE name='spawn'");
            if (!position) throw std::runtime_error("Missing named hub spawn point");
            auto* p=position->Fetch();
            hub=WorldLocation(p[0].Get<uint32>(),p[2].Get<float>(),p[3].Get<float>(),p[4].Get<float>(),p[5].Get<float>());
            hubArea=p[1].Get<uint32>();
            hubPoints.emplace("spawn", hub);
            for (std::string const name : {"town_portal", "rift_exit"})
            {
                auto row = WorldDatabase.Query("SELECT map_id,area_id,x,y,z,o FROM dc_world_hub_point WHERE name='{}'", name);
                if (!row) throw std::runtime_error("Missing named hub point: " + name);
                auto* f = row->Fetch();
                if (f[0].Get<uint32>() != hub.GetMapId() || f[1].Get<uint32>() != hubArea)
                    throw std::runtime_error("Hub points must share their map and area");
                hubPoints.emplace(name, WorldLocation(f[0].Get<uint32>(), f[2].Get<float>(), f[3].Get<float>(), f[4].Get<float>(), f[5].Get<float>()));
            }
            std::map<uint8, ClassStart> profiles;
            auto classes = WorldDatabase.Query("SELECT class_id,class_key,class_name FROM dc_class_start ORDER BY class_id");
            if (!classes) throw std::runtime_error("Missing class start profiles");
            std::set<std::string> classKeys;
            do
            {
                auto* f = classes->Fetch();
                uint32 cid = f[0].Get<uint32>();
                std::string key = f[1].Get<std::string>(), name = f[2].Get<std::string>();
                if (cid > UINT8_MAX || !sChrClassesStore.LookupEntry(cid) || key.empty() || name.empty() ||
                    !classKeys.insert(key).second || !profiles.emplace(uint8(cid), ClassStart{key,name,{}, {}}).second)
                    throw std::runtime_error("Invalid or duplicate class start profile");
            } while (classes->NextRow());
            for (auto const& profile : profiles)
                creatableClasses.insert(profile.first);
            auto skills = WorldDatabase.Query("SELECT class_id,spell_id,skill_id FROM dc_class_start_skill ORDER BY class_id,spell_id");
            if (!skills) throw std::runtime_error("Missing class start proficiencies");
            std::map<uint8, std::set<uint32>> skillIds;
            do
            {
                auto* f = skills->Fetch();
                uint32 cid = f[0].Get<uint32>(), spell = f[1].Get<uint32>(), skill = f[2].Get<uint32>();
                if (cid > UINT8_MAX || !profiles.count(uint8(cid)) || !sSpellMgr->GetSpellInfo(spell) ||
                    !sSkillLineStore.LookupEntry(skill) || !skillIds[uint8(cid)].insert(skill).second ||
                    !profiles.at(uint8(cid)).skills.emplace(spell, skill).second)
                    throw std::runtime_error("Invalid or duplicate class start proficiency");
            } while (skills->NextRow());
            struct Base { uint32 entry; std::string slot,rarity,usable,designation,type,setClass; };
            std::vector<Base> bases;
            // Only latest pool versions; class eligibility comes from the profile. A class set's pieces are worn by
            // that set's class only: dc_set_class is the key generate_sql.py reads for
            // AllowableClass, so the kit and the wear mask follow one rule.
            auto rows=WorldDatabase.Query("SELECT b.entry,b.slot,b.rarity,b.usable_by,b.designated_class,b.type,COALESCE(sc.class_key,'') "
                "FROM dc_base_item b LEFT JOIN dc_set_class sc ON sc.set_name=b.set_name WHERE b.pool_version='yes' ORDER BY b.entry");
            if (!rows) throw std::runtime_error("Missing base items");
            do
            {
                auto* f=rows->Fetch();
                bases.push_back({f[0].Get<uint32>(),f[1].Get<std::string>(),f[2].Get<std::string>(),
                                 f[3].Get<std::string>(),f[4].Get<std::string>(),f[5].Get<std::string>(),f[6].Get<std::string>()});
            } while(rows->NextRow());
            std::map<std::string,uint8> slots={{"mainhand",EQUIPMENT_SLOT_MAINHAND},{"head",EQUIPMENT_SLOT_HEAD},{"neck",EQUIPMENT_SLOT_NECK},{"shoulders",EQUIPMENT_SLOT_SHOULDERS},{"torso",EQUIPMENT_SLOT_CHEST},{"waist",EQUIPMENT_SLOT_WAIST},{"legs",EQUIPMENT_SLOT_LEGS},{"feet",EQUIPMENT_SLOT_FEET},{"wrists",EQUIPMENT_SLOT_WRISTS},{"hands",EQUIPMENT_SLOT_HANDS},{"finger",EQUIPMENT_SLOT_FINGER1},{"offhand",EQUIPMENT_SLOT_OFFHAND}};
            auto list=WorldDatabase.Query("SELECT class_id,slot,rarity,count,base_type,base_slot,designated_class FROM dc_class_starter_kit ORDER BY class_id,slot='mainhand' DESC,slot");
            if (!list) throw std::runtime_error("Missing class starter kits");
            std::map<uint8, std::set<uint8>> occupiedSlots;
            std::set<std::pair<uint8, std::string>> kitRows;
            do
            {
                auto* f=list->Fetch(); uint32 cid=f[0].Get<uint32>();
                auto name=f[1].Get<std::string>(); auto rarity=f[2].Get<std::string>(); auto count=f[3].Get<uint32>();
                if (cid > UINT8_MAX || !profiles.count(uint8(cid)) || !slots.count(name) || rarity.empty() ||
                    count>(name=="finger" ? EQUIPMENT_SLOT_FINGER2 - EQUIPMENT_SLOT_FINGER1 + 1u : 1u) ||
                    !kitRows.emplace(uint8(cid),name).second)
                    throw std::runtime_error("Invalid class starter kit row: " + name);
                if (!count) continue;
                auto type = f[4].Get<std::string>();
                auto baseSlot = f[5].Get<std::string>();
                auto designation = f[6].Get<std::string>();
                auto& profile = profiles.at(uint8(cid));
                KitSlot entry{slots[name],rarity,{}};
                for (auto const& base:bases)
                    if ((type.empty() || base.type == type) &&
                        (baseSlot.empty() || base.slot == baseSlot) &&
                        (designation.empty() || base.designation == designation) &&
                        Usable(base.usable,profile.key) && (base.designation.empty() || base.designation==profile.key) &&
                        (base.setClass.empty() || base.setClass==profile.key) &&
                        (name=="mainhand" ? (base.slot=="onehand"||base.slot=="twohand") : base.slot==(name=="offhand"&&baseSlot=="onehand" ? "onehand" : name)) &&
                        (rarity=="rare" ? base.rarity.empty() : base.rarity==rarity))
                    {
                        auto* item=sObjectMgr->GetItemTemplate(base.entry);
                        if (!item || !item->DisplayInfoID) throw std::runtime_error("Missing item template/display: " + std::to_string(base.entry));
                        entry.candidates.push_back(base.entry);
                    }
                if (entry.candidates.empty()) throw std::runtime_error("Empty starter item pool: " + profile.key + " " + name);
                for (uint32 n=0;n<count;++n)
                {
                    entry.slot=slots[name]+n;
                    if (!occupiedSlots[uint8(cid)].insert(entry.slot).second)
                        throw std::runtime_error("Duplicate starter equipment slot: " + name);
                    profile.kit.push_back(entry);
                }
            } while(list->NextRow());
            for (auto const& [cid, profile] : profiles)
                if (profile.kit.empty() || profile.skills.empty())
                    throw std::runtime_error("Class start requires kit and proficiencies: " + std::to_string(cid));
            auto* satchel=sObjectMgr->GetItemTemplate(SatchelEntry);
            if (!satchel || satchel->Class!=ITEM_CLASS_CONTAINER || !satchel->ContainerSlots)
                throw std::runtime_error("Missing container template " + std::to_string(SatchelEntry) + "; apply the bags migration");
            classStarts=std::move(profiles); ready=true;
            LOG_INFO("server.loading","[DC world] Hub ready; {} class start profiles",classStarts.size());
        }
        catch(std::exception const& error) { LOG_ERROR("server","[DC world] Startup refused: {}",error.what()); }
    }
};

class HubAccount final : public AccountScript
{
public:
    HubAccount() : AccountScript("dc_hub_account",{ACCOUNTHOOK_CAN_ACCOUNT_CREATE_CHARACTER}) { }
    bool CanAccountCreateCharacter(uint32, uint8, uint8 type) override
    {
        // The classes with a start profile (dc_class_start), read before the kit data so the gate stays
        // independent of starter-data readiness: a failed start must leave a created character that login
        // can resume. A new class is a class_starts.csv profile, never an edit here.
        return creatableClasses.count(type) > 0;
    }
};

class HubPlayer final : public PlayerScript
{
public:
    HubPlayer() : PlayerScript("dc_hub_player",{PLAYERHOOK_ON_CREATE,PLAYERHOOK_ON_MAP_CHANGED,PLAYERHOOK_ON_FIRST_LOGIN,PLAYERHOOK_ON_LOGIN,PLAYERHOOK_ON_BEFORE_LOGOUT,PLAYERHOOK_ON_LEARN_SPELL,
        PLAYERHOOK_CAN_LEARN_TALENT,PLAYERHOOK_ON_BEFORE_INIT_TALENT_FOR_LEVEL,PLAYERHOOK_CAN_JOIN_LFG,PLAYERHOOK_ON_CAN_PLAYER_FLY_IN_ZONE,PLAYERHOOK_ON_DELETE_FROM_DB}) { }
    void OnPlayerCreate(Player* player) override
    {
        // The core already committed the character and will still return create
        // success when a start step fails. Login resumes the durable slot journal.
        try { Start(player, true); }
        catch (std::exception const& error)
        {
            LOG_ERROR("server", "[DC world start] {} creation deferred: {}", player->GetName(), error.what());
        }
    }
    void OnPlayerFirstLogin(Player* player) override { Start(player); }
    void OnPlayerMapChanged(Player* player) override
    {
        // Enter-map also runs before login hooks. Resume only a transfer that
        // Start explicitly deferred, after the normal login setup has run.
        auto* resume = player->CustomData.GetDefault<StartResume>("DCStartResume");
        if (!resume->waitingForMap) return;
        resume->waitingForMap = false;
        Start(player);
    }
    void OnPlayerLogin(Player* player) override
    {
        // A character made before this check existed earned no reach-level achievement. Re-checked on every
        // login, a second after it like the core's own AT_LOGIN_CHECK_ACHIEVS, so the client is told.
        player->m_Events.AddEventAtOffset([player] { player->UpdateAchievementCriteria(ACHIEVEMENT_CRITERIA_TYPE_REACH_LEVEL); }, 1s);
        RemoveTravel(player);
        GrantEquipmentSkills(player);
        // Fallback for older saves or an unclean server stop. Ordinary logout
        // already saved spawn, so login does not perform another transfer.
        MoveToHubSpawn(player, "login");
        // Mode and account on every login, for every class (#69): a character
        // whose start is already recorded - including one made before its class
        // had a start profile, which the class-start legacy migration records
        // as complete with no kit - still gets
        // them, and nothing else. Start calls it again; the second call is a
        // no-op once the mode exists.
        Setup(player);
        auto row=CharacterDatabase.Query("SELECT complete FROM dc_character_start WHERE guid={}",player->GetGUID().GetCounter());
        if(StartOwed(player,row)) Start(player);
        else if(row) SweepBags(player);
    }
    void OnPlayerBeforeLogout(Player* player) override
    {
        // WorldSession has set PlayerLogout: TeleportTo suppresses transfer
        // packets. It completes far transfers before the final SaveToDB; a
        // same-map transfer is saved from GetTeleportDest by _SaveCharacter.
        // Use that core path, not an UPDATE racing the queued character save.
        MoveToHubSpawn(player, "logout");
    }
    void OnPlayerLearnSpell(Player* player,uint32 id) override
    {
        if(RemovedSpell(sSpellMgr->GetSpellInfo(id))) player->removeSpell(id,SPEC_MASK_ALL,false);
    }
    bool OnPlayerCanLearnTalent(Player*,TalentEntry const*,uint32) override { return false; }
    void OnPlayerBeforeInitTalentForLevel(Player*,uint8&,uint32& points) override { points=0; }
    bool OnPlayerCanJoinLfg(Player*,uint8,std::set<uint32>&,std::string const&) override { return false; }
    bool OnPlayerCanFlyInZone(Player*,uint32,uint32,SpellInfo const*) override { return false; }
    void OnPlayerDeleteFromDB(CharacterDatabaseTransaction trans,uint32 guid) override
    {
        trans->Append("DELETE FROM dc_character_starter_item WHERE guid={}",guid);
        trans->Append("DELETE FROM dc_character_start WHERE guid={}",guid);
        trans->Append("DELETE FROM dc_character_bag_grant WHERE guid={}",guid);
    }
};

class HubTravel final : public AllSpellScript
{
public:
    HubTravel() : AllSpellScript("dc_hub_travel",{ALLSPELLHOOK_ON_SPELL_CHECK_CAST}) { }
    void OnSpellCheckCast(Spell* spell,bool,SpellCastResult& result) override
    {
        if(spell->GetCaster()->IsPlayer() && RemovedSpell(spell->GetSpellInfo())) result=SPELL_FAILED_NOT_HERE;
    }
};

class HubPackets final : public ServerScript
{
public:
    HubPackets() : ServerScript("dc_hub_packets",{SERVERHOOK_CAN_PACKET_RECEIVE}) { }
    bool CanPacketReceive(WorldSession* session,WorldPacket const& packet) override
    {
        if(!session || !session->GetPlayer()) return true;
        switch(packet.GetOpcode())
        {
            case CMSG_ACTIVATETAXI: case CMSG_ACTIVATETAXIEXPRESS:
                session->SendActivateTaxiReply(ERR_TAXIUNSPECIFIEDSERVERERROR);
                ChatHandler(session).SendSysMessage("Taxis are disabled."); return false;
            case CMSG_TOGGLE_PVP: return false;
            default: return true;
        }
    }
};

class HubArtisan final : public CreatureScript
{
public:
    HubArtisan() : CreatureScript("dc_hub_blacksmith") { }
    bool OnGossipHello(Player* player,Creature* creature) override
    {
        AddGossipItemFor(player,GOSSIP_ICON_VENDOR,"Repair equipment",GOSSIP_SENDER_MAIN,1);
        SendGossipMenuFor(player,1,creature->GetGUID()); return true;
    }
    bool OnGossipSelect(Player* player,Creature* creature,uint32,uint32 action) override
    {
        ClearGossipMenuFor(player); CloseGossipMenuFor(player);
        if(action==1) player->GetSession()->SendListInventory(creature->GetGUID());
        return true;
    }
};

// The test-realm service uses the same account ledger, native inventory/mail,
// and Paragon level-up path that ordinary player actions use.
class TesterCoffer final : public CreatureScript
{
public:
    TesterCoffer() : CreatureScript("dc_tester_coffer") { }

    bool OnGossipHello(Player* player, Creature* creature) override
    {
        if (!Enabled())
        {
            CloseGossipMenuFor(player);
            return true;
        }
        AddGossipItemFor(player, GOSSIP_ICON_CHAT, "Fill my coffers.", GOSSIP_SENDER_MAIN, 1);
        SendGossipMenuFor(player, 1, creature->GetGUID());
        return true;
    }

    bool OnGossipSelect(Player* player, Creature* creature, uint32 sender, uint32 action) override
    {
        ClearGossipMenuFor(player);
        CloseGossipMenuFor(player);
        if (!player || !creature || sender != GOSSIP_SENDER_MAIN || action != 1)
            return true;
        uint32 const account = player->GetSession()->GetAccountId();
        uint32 const guid = player->GetGUID().GetCounter();
        if (!Enabled() || !AccountEconomy::Eligible(player))
        {
            LOG_WARN("server", "[DC tester coffer] account={} character={} raised=none refused: disabled or ledger unavailable", account, guid);
            ChatHandler(player->GetSession()).SendSysMessage("Tester's Coffer is unavailable.");
            return true;
        }
        std::ostringstream changes;
        try
        {
            auto const gold = Target("tester_coffer_gold", std::numeric_limits<uint64>::max() / Economy::CopperPerGold);
            auto const materials = Target("tester_coffer_materials", std::numeric_limits<uint64>::max());

            auto paragonLevels = WorldDatabase.Query("SELECT MAX(level) FROM dc_paragon_xp");
            if (!paragonLevels || !(*paragonLevels)[0].Get<uint32>())
                throw std::runtime_error("Paragon XP table is unavailable");
            auto const paragon = Target("tester_coffer_paragon", (*paragonLevels)[0].Get<uint32>());

            struct Gem { uint32 entry; std::string colour; uint64 held; };
            std::vector<Gem> gemRows;
            uint32 gemStackMaximum = std::numeric_limits<uint32>::max();
            auto rows = WorldDatabase.Query(
                "SELECT entry,colour FROM dc_gem_item WHERE tier='Flawless Royal' ORDER BY colour");
            if (!rows || rows->GetRowCount() != 5)
                throw std::runtime_error("Flawless Royal gem catalogue is incomplete");
            do
            {
                auto const entry = (*rows)[0].Get<uint32>();
                ItemTemplate const* item = sObjectMgr->GetItemTemplate(entry);
                if (!item || !item->GetMaxStackSize())
                    throw std::runtime_error("Flawless Royal gem item template is missing");
                gemStackMaximum = std::min(gemStackMaximum, item->GetMaxStackSize());
                gemRows.push_back({entry, (*rows)[1].Get<std::string>(), 0});
            } while (rows->NextRow());
            auto const gems = Target("tester_coffer_gems", gemStackMaximum);

            AccountEconomy::Snapshot before, after;
            if (!AccountEconomy::TopUp(player, Economy::GoldCost(gold), materials, before, after))
                throw std::runtime_error("account ledger top-up failed");

            changes << "gold=" << before.gold << "->" << after.gold << " copper";
            for (auto const& [entry, oldAmount] : before.materials)
                changes << " material[" << entry << "]=" << oldAmount << "->" << after.materials.at(entry);

            CharacterDatabaseTransaction mailTransaction;
            for (auto& gem : gemRows)
            {
                gem.held = TopUpGem(player, guid, gem.entry, uint32(gems), mailTransaction);
            }
            if (mailTransaction && !CharacterDatabase.AsyncCommitTransaction(mailTransaction).m_future.get())
                throw std::runtime_error("gem mail commit failed");
            for (auto const& gem : gemRows)
            {
                uint64 const now = CountOwned(player, guid, gem.entry);
                if (now < gems)
                    throw std::runtime_error("gem top-up did not persist in inventory or mail");
                changes << " gem[" << gem.colour << "]=" << gem.held << "->" << now;
            }

            // The Paragon subsystem owns pool selection, XP/level progression,
            // point availability, stats, and the client XP bar.
            uint32 oldLevel = 0, newLevel = 0;
            std::string error;
            if (!Paragon::TopUpLevel(player, uint32(paragon), oldLevel, newLevel, error))
                throw std::runtime_error("Paragon top-up failed: " + error);
            changes << " paragon=" << oldLevel << "->" << newLevel;
            LOG_INFO("server", "[DC tester coffer] account={} character={} {}", account, guid, changes.str());
            ChatHandler(player->GetSession()).SendSysMessage("Your coffers are filled.");
        }
        catch (std::exception const& error)
        {
            LOG_ERROR("server", "[DC tester coffer] account={} character={} raised={} failed: {}", account, guid, changes.str(), error.what());
            ChatHandler(player->GetSession()).SendSysMessage("Tester's Coffer could not finish. Please try again or contact a GM.");
        }
        return true;
    }

private:
    static bool Enabled()
    {
        return sConfigMgr->GetOption<bool>("Diablocraft.TesterCoffer.Enable", false);
    }
    static uint64 Target(char const* name, uint64 limit)
    {
        double const value = Tunables::Get("economy", name);
        // Tunables are doubles; cap at the last exactly representable integer.
        if (!std::isfinite(value) || std::floor(value) != value || value <= 0 ||
            value > double(std::min<uint64>(limit, uint64(1) << 53)))
            throw std::runtime_error(std::string("Invalid tester coffer target: ") + name);
        return uint64(value);
    }
    static uint64 MailedCount(uint32 guid, uint32 entry)
    {
        auto row = CharacterDatabase.Query(
            "SELECT COALESCE(SUM(i.count),0) FROM mail_items mi JOIN item_instance i ON i.guid=mi.item_guid "
            "JOIN mail m ON m.id=mi.mail_id WHERE mi.receiver={} AND m.receiver={} AND i.itemEntry={} "
            "AND m.expire_time>UNIX_TIMESTAMP()", guid, guid, entry);
        if (!row)
            throw std::runtime_error("gem mail read failed");
        return (*row)[0].Get<uint64>();
    }
    static uint64 CountOwned(Player* player, uint32 guid, uint32 entry)
    {
        uint64 const bagsAndBank = player->GetItemCount(entry, true);
        uint64 const mail = MailedCount(guid, entry);
        return mail > std::numeric_limits<uint64>::max() - bagsAndBank
                   ? std::numeric_limits<uint64>::max()
                   : bagsAndBank + mail;
    }
    static uint64 TopUpGem(Player* player, uint32 guid, uint32 entry, uint32 target,
                           CharacterDatabaseTransaction& mailTransaction)
    {
        uint64 const held = CountOwned(player, guid, entry);
        uint32 const missing = target > held ? uint32(target - held) : 0;
        if (missing)
        {
            ItemPosCountVec destinations;
            uint32 noSpace = 0;
            player->CanStoreNewItem(NULL_BAG, NULL_SLOT, destinations, entry, missing, &noSpace);
            if (noSpace > missing)
                throw std::runtime_error("invalid gem inventory capacity result");
            uint32 stored = missing - noSpace;
            if (stored && !destinations.empty())
            {
                Item* added = player->StoreNewItem(destinations, entry, true);
                if (!added)
                    throw std::runtime_error("gem inventory grant failed");
                player->SendNewItem(added, stored, true, false);
            }
            else
                stored = 0;
            uint32 const mailed = missing - stored;
            if (mailed)
                SendGemMail(player, entry, mailed, mailTransaction);
        }
        return held;
    }
    static void SendGemMail(Player* player, uint32 entry, uint32 amount,
                            CharacterDatabaseTransaction& transaction)
    {
        ItemTemplate const* proto = sObjectMgr->GetItemTemplate(entry);
        if (!proto || !proto->GetMaxStackSize())
            throw std::runtime_error("gem mail item template is missing");
        if (!transaction)
            transaction = CharacterDatabase.BeginTransaction();
        uint32 remaining = amount;
        while (remaining)
        {
            MailDraft draft("Tester's Coffer", "Your Flawless Royal gems did not fit in your bags.");
            for (uint32 slot = 0; slot < MAX_MAIL_ITEMS && remaining; ++slot)
            {
                uint32 const stack = std::min(remaining, proto->GetMaxStackSize());
                Item* item = Item::CreateItem(entry, stack, player);
                if (!item)
                    throw std::runtime_error("gem mail item creation failed");
                item->SaveToDB(transaction);
                draft.AddItem(item);
                remaining -= stack;
            }
            draft.SendMailTo(transaction, MailReceiver(player, player->GetGUID().GetCounter()),
                             MailSender(MAIL_CREATURE, TesterCofferEntry));
        }
    }
};
}
void StartCharacter(Player* player) { if (player) Start(player); }

bool HubLocation(WorldLocation& location)
{
    if (!ready) return false;
    location = hub;
    return true;
}

bool HubPoint(std::string const& name, WorldLocation& location)
{
    if (!ready) return false;
    auto found = hubPoints.find(name);
    if (found == hubPoints.end()) return false;
    location = found->second;
    return true;
}

bool IsInHub(Player const* player)
{
    return ready && player && !player->GetInstanceId() &&
        player->GetMapId() == hub.GetMapId() && player->GetAreaId() == hubArea;
}

void RegisterScripts() { new HubWorld(); new HubAccount(); new HubPlayer(); new HubTravel(); new HubPackets(); new HubArtisan(); new TesterCoffer(); Outfits::RegisterScripts(); }
}
