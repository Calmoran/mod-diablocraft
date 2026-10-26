#include "dc_difficulty.h"
#include "dc_gr_scaling.h"
#include "dc_tier_gate.h"
#include "../common/dc_tunables.h"
#include "../common/dc_world.h"
#include "../common/dc_world_areas.h"
#include "../rifts/dc_rifts.h"
#include "../rifts/dc_ally.h"
#include "../campaign/dc_campaign.h"
#include "ABModuleScript.h"
#include "ABScriptMgr.h"
#include "ABCreatureInfo.h"
#include "Chat.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "Group.h"
#include "GameObject.h"
#include "GameTime.h"
#include "Log.h"
#include "Map.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "WorldSession.h"
#include <algorithm>
#include <map>
#include <limits>
#include <mutex>
#include <set>
#include <vector>

namespace DC::Difficulty
{
namespace
{
std::vector<Tier> tiers;
std::vector<PartyScaling> parties;
unsigned PartyLimit() { return parties.empty() ? 0 : parties.size() - 1; }
bool ready = false;
std::mutex stateMutex;
std::map<uint64, unsigned> playerTiers;
std::map<uint64, uint64> lastTierChangeMs;
std::map<Map*, std::set<Creature*>> creatures;
std::set<Map*> dirtyMaps;
struct Engagement { uint64 leader = 0; unsigned players = 1; };
std::map<Creature*, Engagement> engagements;
struct AppliedScaling : DataMap::Base { unsigned tier = 0, players = 0; };

bool OpenWorld(Map const* map) { return map && !map->Instanceable(); }
void ApplyPhase(WorldObject* object, uint32 phase, bool update)
{
    // Unit's same-number fast path skips the WorldObject hook which changes
    // combined bit masks into literal tier IDs. Normal starts at phase 1.
    // Keep Unit's veto/controlled-unit handling for actual number changes.
    if (object->GetPhaseMask() == phase)
        object->WorldObject::SetPhaseMask(phase, update);
    else
        object->SetPhaseMask(phase, update);
}
// The one place a player's phase is decided: the Sanctum's shared phase in the hub, the tier's own
// phase in the open world. Picking a tier in the hub changes the saved tier and no phase.
uint32 PlayerPhase(Player const* player)
{
    return DC::World::IsInHub(player) ? DC::World::SanctumPhase : tiers[CurrentTier(player)].phase;
}
unsigned SavedTier(ObjectGuid guid)
{
    if (auto row = CharacterDatabase.Query("SELECT tier, phase FROM dc_character_tier WHERE guid={}", guid.GetRawValue()))
    {
        unsigned tier = (*row)[0].Get<uint8>();
        if (tier < 1 || tier > LaunchTierCount() || (*row)[1].Get<uint32>() != tiers[tier].phase)
            throw std::runtime_error("Invalid saved tier/phase for GUID " + std::to_string(guid.GetRawValue()));
        return tier;
    }
    return 1;
}
void StoreTier(ObjectGuid guid, unsigned tier)
{
    CharacterDatabase.DirectExecute("INSERT INTO dc_character_tier (guid,tier,phase) VALUES ({},{},{}) "
        "ON DUPLICATE KEY UPDATE tier=VALUES(tier),phase=VALUES(phase)", guid.GetRawValue(), tier, tiers[tier].phase);
}
void Apply(Player* player, unsigned tier, bool notify = true)
{
    {
        std::lock_guard<std::mutex> lock(stateMutex);
        playerTiers[player->GetGUID().GetRawValue()] = tier;
    }
    StoreTier(player->GetGUID(), tier);
    if (OpenWorld(player->FindMap())) ApplyPhase(player, PlayerPhase(player), true);
    RequestRefresh(player->FindMap());
    if (notify) ChatHandler(player->GetSession()).PSendSysMessage("Difficulty: {} (tier {}, phase {}).", tiers[tier].name, tier, PlayerPhase(player));
}
unsigned LeaderTier(Group* group)
{
    {
        std::lock_guard<std::mutex> lock(stateMutex);
        auto found = playerTiers.find(group->GetLeaderGUID().GetRawValue());
        if (found != playerTiers.end()) return found->second;
    }
    return SavedTier(group->GetLeaderGUID());
}
void SyncGroup(Group* group, unsigned tier)
{
    for (auto const& slot : group->GetMemberSlots())
    {
        if (auto* player = ObjectAccessor::FindConnectedPlayer(slot.guid)) Apply(player, tier);
        else StoreTier(slot.guid, tier);
    }
}
unsigned PartySize(Creature const* creature)
{
    std::lock_guard<std::mutex> lock(stateMutex);
    auto found = engagements.find(const_cast<Creature*>(creature));
    return found == engagements.end() ? 1 : found->second.players;
}
bool CreatureContext(Creature const* creature, unsigned& tier, unsigned& players)
{
    if (!creature || creature->IsControlledByPlayer() || creature->IsPet() ||
        creature->GetScriptName() == "npc_training_dummy" || Rifts::Ally::IsAllyScript(creature->GetScriptName()) ||
        Campaign::Followers::IsFollowerScript(creature->GetScriptName())) return false;
    if (Rifts::ScalingContext(creature->FindMap(), tier, players))
        return tier >= 1 && tier <= LaunchTierCount() && players >= 1 && players <= PartyLimit();
    if (!OpenWorld(creature->FindMap())) return false;
    tier = creature->GetPhaseMask();
    players = PartySize(creature);
    return tier >= 1 && tier <= LaunchTierCount();
}
void LogCreature(Creature* creature)
{
    auto* info = creature->CustomData.GetDefault<AutoBalanceCreatureInfo>("AutoBalanceCreatureInfo");
    unsigned tier = 0, players = 0;
    CreatureContext(creature, tier, players);
    LOG_DEBUG("module.dc.combat", "[DC tier creature] entry={} spawn={} level={} phase={} baseLife={} Life={} damageMultiplier={} players={} tier={} instance={} claimed={}",
        creature->GetEntry(), creature->GetSpawnId(), creature->GetLevel(), creature->GetPhaseMask(), info->moduleBaseHealth,
        creature->GetMaxHealth(), info->moduleDamageMultiplier, players, tier, creature->GetInstanceId(), sABScriptMgr->IsModuleScaled(creature));
}

class TierWorld final : public WorldScript
{
public:
    TierWorld() : WorldScript("dc_tier_world", {WORLDHOOK_ON_LOAD_CUSTOM_DATABASE_TABLE}) { }
    void OnLoadCustomDatabaseTable() override
    {
        try
        {
            auto result = WorldDatabase.Query("SELECT p.tier_id,p.phase,p.tier_name,t.monster_health_multiplier_pct,"
                "t.monster_damage_multiplier_pct,t.xp_bonus_pct,t.gold_bonus_pct,t.unlock_requirement "
                "FROM dc_tier_phase p JOIN dc_difficulty_tiers t ON t.tier=p.tier_name ORDER BY p.tier_id");
            if (!result || !LaunchTierCount() || result->GetRowCount() < LaunchTierCount()) throw std::runtime_error("Missing configured launch tier rows");
            tiers.resize(result->GetRowCount() + 1);
            unsigned expected = 1;
            do
            {
                auto* f = result->Fetch();
                unsigned id = f[0].Get<uint8>();
                if (id != expected++ || f[1].Get<uint32>() != id) throw std::runtime_error("Tier/phase mapping must be contiguous from one");
                Tier& tier = tiers[id];
                tier.id = id; tier.phase = id; tier.name = f[2].Get<std::string>();
                tier.health = f[3].Get<int64>() / 100.0; tier.damage = f[4].Get<int64>() / 100.0;
                tier.xpPct = static_cast<double>(f[5].Get<int64>()); tier.goldPct = static_cast<double>(f[6].Get<int64>());
                tier.unlock = f[7].Get<std::string>();
                if (tier.health < 1 || tier.damage < 1) throw std::runtime_error("Invalid tier multipliers");
            } while (result->NextRow());
            result = WorldDatabase.Query("SELECT players,monster_life_multiplier_pct,monster_damage_multiplier_pct FROM dc_party_scaling WHERE context='open_world' ORDER BY players");
            if (!result) throw std::runtime_error("Missing open-world party rows");
            parties.resize(result->GetRowCount() + 1);
            expected = 1;
            do
            {
                auto* f = result->Fetch();
                unsigned count = static_cast<unsigned>(f[0].Get<int64>());
                if (count != expected++) throw std::runtime_error("Party rows must be contiguous from one");
                parties[count] = {std::stod(f[1].Get<std::string>()) / 100.0, f[2].Get<int64>() / 100.0};
                if (!std::isfinite(parties[count].health) || parties[count].health < 1 || parties[count].damage < 1)
                    throw std::runtime_error("Invalid party multiplier");
            } while (result->NextRow());
            if (!CharacterDatabase.Query("SELECT COUNT(*) FROM dc_character_tier")) throw std::runtime_error("Character tier migration missing");
            ready = true;
            LOG_INFO("server.loading", "[DC tiers] Loaded {} tier rows ({} active) and {} open-world party rows", tiers.size() - 1, LaunchTierCount(), PartyLimit());
        }
        catch (std::exception const& error) { LOG_ERROR("server", "[DC tiers] Startup validation failed: {}", error.what()); }
    }
};

// Greater Rift: the rifts tunables as numbers, and the multipliers a level of that run
// gives, in the two slots (tier, party) the open-world path fills. False, with `error` saying
// which number, when they cannot be used.
bool GreaterNumbers(GrNumbers& n, unsigned& baseTier, std::string& error)
{
    n.lifePerLevel = Tunables::Get("rifts", "gr_life_per_level");
    n.damageLow = Tunables::Get("rifts", "gr_damage_per_level_low");
    n.damageMid = Tunables::Get("rifts", "gr_damage_per_level_mid");
    n.damageHigh = Tunables::Get("rifts", "gr_damage_per_level_high");
    n.lowLast = static_cast<unsigned>(Tunables::Get("rifts", "gr_damage_low_last_level"));
    n.midLast = static_cast<unsigned>(Tunables::Get("rifts", "gr_damage_mid_last_level"));
    n.partyLifePctPerExtraMember = Tunables::Get("rifts", "gr_party_life_pct_per_extra_member");
    baseTier = static_cast<unsigned>(Tunables::Get("rifts", "gr_level_one_tier"));
    if (!GrNumbersValid(n)) { error = "the rifts gr_* scaling tunables are missing or out of order"; return false; }
    if (baseTier < 1 || baseTier >= tiers.size()) { error = "rifts gr_level_one_tier is not a loaded tier"; return false; }
    return true;
}
bool GreaterScaling(unsigned level, unsigned players, double& tierHealth, double& partyHealth, double& tierDamage,
                    double& partyDamage, std::string& error)
{
    GrNumbers n;
    unsigned base = 0;
    if (!GreaterNumbers(n, base, error)) return false;
    tierHealth = tiers[base].health * GrLifeFactor(n, level);
    tierDamage = tiers[base].damage * GrDamageFactor(n, level);
    partyHealth = GrPartyLifeFactor(n, players);
    partyDamage = 1.0; // greater_rifts.csv multiplayer_life_scaling: monster damage unchanged
    return true;
}

class TierBalance final : public ABModuleScript
{
public:
    TierBalance() : ABModuleScript("dc_tier_balance") { }
    bool OnModuleCreatureScaling(Creature* creature, double& health, double& damage) override
    {
        // Rift context exists before instance scripts/grid loads. Returning true
        // selects patch 0003's exclusive module path before native level scaling.
        unsigned tier = 0, count = 0;
        if (!CreatureContext(creature, tier, count)) return false;
        if (!ready) return true; // retain exclusive ownership until startup data is ready
        auto* info = creature->CustomData.GetDefault<AutoBalanceCreatureInfo>("AutoBalanceCreatureInfo");
        double tierHealth = tiers[tier].health, partyHealth = parties[count].health;
        double tierDamage = tiers[tier].damage, partyDamage = parties[count].damage;
        // A Greater Rift's monsters take their multipliers from the run's level, not from the
        // opener's difficulty tier or the open-world party rows.
        if (unsigned const level = Rifts::GreaterRiftLevel(creature->FindMap()))
        {
            std::string error;
            if (!GreaterScaling(level, count, tierHealth, partyHealth, tierDamage, partyDamage, error))
            {
                LOG_ERROR("server", "[DC tiers] Greater Rift scaling refused for entry {}: {}", creature->GetEntry(), error);
                health = std::numeric_limits<double>::quiet_NaN();
                return true;
            }
        }
        tierHealth *= Rifts::EliteLifeFactor(creature); // A4: Juggernaut's and an Illusionist copy's Life
        if (info->moduleBaseHealth)
        {
            // Every Guardian has the one D3-style Guardian Life instead of its stock template's.
            double const base = Rifts::IsGuardianEntry(creature->GetEntry()) ? Tunables::Get("rifts", "guardian_base_life")
                                                                              : info->moduleBaseHealth;
            try
            {
                // 64-bit Life: AutoBalance is handed the multiplier that makes the core's max the real Life.
                CreatureScaling const scaling = ScaleCreatureLife(info->moduleBaseHealth, base, tierHealth, partyHealth, health);
                health = scaling.health;
            }
            catch (std::exception const& error)
            {
                LOG_ERROR("server", "[DC tiers] Scaling refused for entry {}: {}", creature->GetEntry(), error.what());
                health = std::numeric_limits<double>::quiet_NaN();
                return true; // AutoBalance rejects invalid input without changing ownership.
            }
        }
        else health *= tierHealth * partyHealth;
        damage *= tierDamage * partyDamage;
        if (info->moduleBaseHealth)
        {
            auto* applied = creature->CustomData.GetDefault<AppliedScaling>("DCTierScaling");
            applied->tier = tier; applied->players = count;
        }
        return true;
    }
};

class TierPlayer final : public PlayerScript
{
public:
    TierPlayer() : PlayerScript("dc_tier_player", {PLAYERHOOK_ON_LOGIN,PLAYERHOOK_ON_LOGOUT,PLAYERHOOK_ON_MAP_CHANGED,PLAYERHOOK_ON_DELETE_FROM_DB,PLAYERHOOK_CAN_GROUP_ACCEPT}) { }
    bool OnPlayerCanGroupAccept(Player* player, Group* group) override
    {
        if (OpenWorld(player->FindMap()) && group->GetMembersCount() >= PartyLimit())
        {
            ChatHandler(player->GetSession()).SendSysMessage("Party exceeds the sourced open-world size limit.");
            return false;
        }
        return true;
    }
    void OnPlayerLogin(Player* player) override
    {
        try
        {
            if (!ready || !Areas::Ready()) throw std::runtime_error("Tier/area data is not ready");
            unsigned tier = player->GetGroup() ? LeaderTier(player->GetGroup()) : SavedTier(player->GetGUID());
            Apply(player, tier, false);
            LOG_INFO("server.loading", "[DC tiers] Loaded {}: tier={} phase={}", player->GetName(), tier, tiers[tier].phase);
        }
        catch (std::exception const& error)
        {
            LOG_ERROR("server", "[DC tiers] Login failed for {}: {}", player->GetName(), error.what());
            player->GetSession()->KickPlayer(std::string("Invalid tier data"));
        }
    }
    void OnPlayerLogout(Player* player) override
    {
        RequestRefresh(player->FindMap());
        std::lock_guard<std::mutex> lock(stateMutex);
        playerTiers.erase(player->GetGUID().GetRawValue());
    }
    void OnPlayerMapChanged(Player* player) override
    {
        if (ready && OpenWorld(player->FindMap())) ApplyPhase(player, PlayerPhase(player), true);
        else if (player->FindMap()) ApplyPhase(player, PHASEMASK_NORMAL, true);
        RequestRefresh(player->FindMap());
    }
    void OnPlayerDeleteFromDB(CharacterDatabaseTransaction trans, uint32 guid) override { trans->Append("DELETE FROM dc_character_tier WHERE guid={}", guid); }
};

class TierGroup final : public GroupScript
{
public:
    TierGroup() : GroupScript("dc_tier_group", {GROUPHOOK_ON_ADD_MEMBER,GROUPHOOK_ON_REMOVE_MEMBER,GROUPHOOK_ON_CHANGE_LEADER,GROUPHOOK_ON_DISBAND}) { }
    void OnAddMember(Group* group, ObjectGuid) override { if (ready) SyncGroup(group, LeaderTier(group)); }
    void OnChangeLeader(Group* group, ObjectGuid newLeader, ObjectGuid) override
    {
        if (!ready) return;
        auto* leader = ObjectAccessor::FindConnectedPlayer(newLeader);
        SyncGroup(group, leader ? CurrentTier(leader) : SavedTier(newLeader));
    }
    static void RefreshGroup(Group* group)
    {
        for (auto const& slot : group->GetMemberSlots())
            if (auto* player = ObjectAccessor::FindConnectedPlayer(slot.guid)) RequestRefresh(player->FindMap());
    }
    void OnRemoveMember(Group* group, ObjectGuid guid, RemoveMethod, ObjectGuid, char const*) override
    {
        RefreshGroup(group);
        if (auto* player = ObjectAccessor::FindConnectedPlayer(guid)) RequestRefresh(player->FindMap());
    }
    void OnDisband(Group* group) override { RefreshGroup(group); }
};

class TierPhase final : public GlobalScript
{
public:
    TierPhase() : GlobalScript("dc_tier_phase", {GLOBALHOOK_ON_BEFORE_WORLDOBJECT_SET_PHASEMASK}) { }
    void OnBeforeWorldObjectSetPhaseMask(WorldObject const* object, uint32& oldPhase, uint32& phase, bool& combined, bool&) override
    {
        bool wasCombined = combined;
        if (OpenWorld(object->FindMap())) phase = Areas::SpawnPhase(object,phase);
        if (ready && OpenWorld(object->FindMap()))
        {
            if (auto* player = object->ToPlayer()) phase = PlayerPhase(player);
        }
        if (OpenWorld(object->FindMap()) && phase >= 1 && phase <= LaunchTierCount())
        {
            combined = false; // IDs, not overlapping bit masks (3 must not overlap 1 or 2).
            if (oldPhase != phase || wasCombined != combined) RequestRefresh(object->FindMap());
        }
    }
};

class TierCreature final : public AllCreatureScript
{
public:
    TierCreature() : AllCreatureScript("dc_tier_creature") { }
    void OnCreatureAddWorld(Creature* creature) override
    {
        unsigned tier = 0, players = 0;
        if (!CreatureContext(creature, tier, players)) return;
        if (OpenWorld(creature->FindMap())) ApplyPhase(creature, creature->GetPhaseMask(), false);
        std::lock_guard<std::mutex> lock(stateMutex);
        creatures[creature->GetMap()].insert(creature);
        dirtyMaps.insert(creature->GetMap());
    }
    void OnCreatureRemoveWorld(Creature* creature) override
    {
        std::lock_guard<std::mutex> lock(stateMutex);
        auto found = creatures.find(creature->FindMap());
        if (found != creatures.end()) found->second.erase(creature);
        engagements.erase(creature);
    }
};

class TierGameObject final : public AllGameObjectScript
{
public:
    TierGameObject() : AllGameObjectScript("dc_tier_gameobject") { }
    void OnGameObjectAddWorld(GameObject* object) override
    {
        if (OpenWorld(object->FindMap())) ApplyPhase(object, object->GetPhaseMask(), false);
    }
};

class TierMap final : public AllMapScript
{
public:
    TierMap() : AllMapScript("dc_tier_map", {ALLMAPHOOK_ON_MAP_UPDATE,ALLMAPHOOK_ON_PLAYER_ENTER_ALL,ALLMAPHOOK_ON_PLAYER_LEAVE_ALL,ALLMAPHOOK_ON_DESTROY_MAP}) { }
    void OnPlayerEnterAll(Map* map, Player*) override { RequestRefresh(map); }
    void OnPlayerLeaveAll(Map* map, Player*) override { RequestRefresh(map); }
    void OnDestroyMap(Map* map) override
    {
        std::lock_guard<std::mutex> lock(stateMutex);
        creatures.erase(map); dirtyMaps.erase(map);
    }
    void OnMapUpdate(Map* map, uint32) override
    {
        if (!ready) return;
        std::vector<Creature*> refresh;
        {
            std::lock_guard<std::mutex> lock(stateMutex);
            if (!dirtyMaps.erase(map)) return;
            auto found = creatures.find(map);
            if (found != creatures.end()) refresh.assign(found->second.begin(), found->second.end());
        }
        for (Creature* creature : refresh)
        {
            if (!creature->IsInWorld() || !sABScriptMgr->IsModuleScaled(creature)) continue;
            auto* applied = creature->CustomData.GetDefault<AppliedScaling>("DCTierScaling");
            unsigned tier = 0, players = 0;
            if (!CreatureContext(creature, tier, players)) continue;
            if (applied->tier == tier && applied->players == players) continue;
            try
            {
                uint64 previous = creature->GetMaxHealth();
                if (sABScriptMgr->RefreshCreatureScaling(creature) && previous != creature->GetMaxHealth()) LogCreature(creature);
            }
            catch (std::exception const& error) { LOG_ERROR("server", "[DC tiers] Scaling refused for entry {}: {}", creature->GetEntry(), error.what()); }
        }
    }
};

class TierCombat final : public UnitScript
{
public:
    TierCombat() : UnitScript("dc_tier_engagement", true, {UNITHOOK_ON_UNIT_ENTER_COMBAT,UNITHOOK_ON_UNIT_EXIT_COMBAT}) { }
    void OnUnitEnterCombat(Unit* unit, Unit* victim) override
    {
        Creature* creature = unit->ToCreature();
        Player* player = victim ? victim->GetCharmerOrOwnerPlayerOrPlayerItself() : nullptr;
        if (!creature || !player || !OpenWorld(creature->FindMap()) || !sABScriptMgr->IsModuleScaled(creature)) return;
        unsigned count = 1;
        uint64 leader = player->GetGUID().GetRawValue();
        if (Group* group = player->GetGroup())
        {
            leader = group->GetLeaderGUID().GetRawValue();
            count = 0;
            for (auto const& slot : group->GetMemberSlots())
                if (auto* member = ObjectAccessor::FindConnectedPlayer(slot.guid))
                    if (member->IsInWorld() && member->FindMap() == creature->FindMap() && member->GetPhaseMask() == creature->GetPhaseMask()) ++count;
            count = std::clamp(count, 1u, PartyLimit());
        }
        {
            std::lock_guard<std::mutex> lock(stateMutex);
            if (!engagements.emplace(creature, Engagement{leader,count}).second) return;
        }
        // A combat transition is an event, not a damage hook. The first party's
        // size remains fixed even if another party tags it or membership changes.
        if (sABScriptMgr->RefreshCreatureScaling(creature)) LogCreature(creature);
    }
    void OnUnitExitCombat(Unit* unit) override
    {
        Creature* creature = unit->ToCreature();
        if (!creature) return;
        {
            std::lock_guard<std::mutex> lock(stateMutex);
            if (!engagements.erase(creature)) return;
        }
        RequestRefresh(creature->FindMap());
    }
};

class TierCommands final : public CommandScript
{
public:
    TierCommands() : CommandScript("dc_tier_commands") { }
    Acore::ChatCommands::ChatCommandTable GetCommands() const override
    {
        using namespace Acore::ChatCommands;
        static ChatCommandTable children = {{"tier",HandleTier,SEC_ADMINISTRATOR,Console::No}, {"tierselect",HandleChoose,SEC_PLAYER,Console::No}};
        static ChatCommandTable root = {{"dc",children}};
        return root;
    }
    static bool HandleSelect(ChatHandler* handler, uint32 id)
    {
        std::string error;
        if (SelectTier(handler->GetPlayer(), id, error)) return true;
        handler->SendSysMessage(error); handler->SetSentErrorMessage(true); return false;
    }
    static bool HandleChoose(ChatHandler* handler, uint32 id)
    {
        std::string error;
        if (ChooseTier(handler->GetPlayer(), id, error)) return true;
        handler->SendSysMessage(error); handler->SetSentErrorMessage(true); return false;
    }
    static bool HandleTier(ChatHandler* handler, Optional<uint32> id)
    {
        if (id) return HandleSelect(handler, *id);
        auto* player = handler->GetPlayer();
        unsigned current = CurrentTier(player);
        handler->PSendSysMessage("Tier {}: {}; phase {}; Life x{}; damage x{}.", current, tiers[current].name,
            player->GetPhaseMask(), tiers[current].health, tiers[current].damage);
        if (auto* creature = handler->getSelectedCreature())
        {
            handler->PSendSysMessage("Creature {}: phase {}; Life {}.", creature->GetEntry(), creature->GetPhaseMask(), creature->GetMaxHealth());
            LogCreature(creature);
        }
        return true;
    }
};
}

unsigned CurrentTier(Player const* player)
{
    std::lock_guard<std::mutex> lock(stateMutex);
    auto found = playerTiers.find(player->GetGUID().GetRawValue());
    if (found != playerTiers.end()) return found->second;
    // Login stores the tier before anything in the hub reads it, so a miss there is a bug, not tier 1.
    if (DC::World::IsInHub(player))
        LOG_ERROR("server", "[DC tiers] No tier in memory for {} in the Sanctum; using tier 1", player->GetName());
    return 1;
}
void RequestRefresh(Map* map)
{
    unsigned tier = 0, players = 0;
    if (!OpenWorld(map) && !Rifts::ScalingContext(map, tier, players)) return;
    std::lock_guard<std::mutex> lock(stateMutex);
    dirtyMaps.insert(map);
}
double GreaterRiftDamage(unsigned level)
{
    GrNumbers n;
    unsigned base = 0;
    std::string error;
    if (!ready || !GreaterNumbers(n, base, error)) return 0.0;
    return tiers[base].damage * GrDamageFactor(n, level);
}
bool BypassCreatureMitigation(Creature const* creature)
{
    unsigned tier = 0, players = 0;
    return CreatureContext(creature, tier, players);
}
bool SelectTier(Player* player, unsigned id, std::string& error)
{
    if (!ready || id < 1 || id > LaunchTierCount()) { error = "Choose a configured launch tier."; return false; }
    if (!OpenWorld(player->FindMap()) || player->IsInCombat()) { error = "Choose difficulty outside instances and out of combat."; return false; }
    Group* group = player->GetGroup();
    if (group && !group->IsLeader(player->GetGUID())) { error = "Only the party leader may choose difficulty."; return false; }
    if (group && group->GetMembersCount() > PartyLimit()) { error = "Party exceeds the sourced open-world size limit."; return false; }
    unsigned accountLevel = player->GetLevel();
    auto const& unlock = TierUnlock(id);
    if (unlock.accountLevel && accountLevel < unlock.accountLevel)
        if (auto row = CharacterDatabase.Query("SELECT MAX(level) FROM characters WHERE account={}", player->GetSession()->GetAccountId()))
            accountLevel = (*row)[0].Get<uint8>();
    // Torment VII to XVI: a Greater Rift beaten in time alone; read only where the tier asks for one.
    unsigned const beatenSolo = unlock.soloGreaterRift ? Rifts::GreaterRiftBeatenSolo(player->GetGUID().GetCounter()) : 0;
    if (!TierUnlocked(id, player->GetLevel(), accountLevel, beatenSolo)) { error = "That difficulty is locked for this character/account."; return false; }
    if (group)
    {
        for (auto const& slot : group->GetMemberSlots())
            if (auto* member = ObjectAccessor::FindConnectedPlayer(slot.guid))
                if (!PartyMemberReady(DC::World::IsInHub(member), member->IsInCombat(), error)) return false;
        SyncGroup(group, id);
    }
    else Apply(player, id);
    LOG_INFO("server.loading", "[DC tiers] {} selected tier={} phase={}", player->GetName(), id, tiers[id].phase);
    return true;
}
// G10: the player-facing path. The hub and the cooldown are checked before
// SelectTier touches anything; the start kit and the GM `tier` command call
// SelectTier directly and are not gated.
bool ChooseTier(Player* player, unsigned id, std::string& error)
{
    bool inHub = DC::World::IsInHub(player);
    bool hasLast = false;
    uint64 last = 0;
    {
        std::lock_guard<std::mutex> lock(stateMutex);
        auto found = lastTierChangeMs.find(player->GetGUID().GetRawValue());
        if (found != lastTierChangeMs.end()) { hasLast = true; last = found->second; }
    }
    uint64 cooldownMs = uint64(std::max(0.0, Tunables::Get("monsters", "tier_change_cooldown_seconds")) * 1000.0);
    if (!TierChangeAllowed(inHub, hasLast, last, uint64(GameTime::GetGameTimeMS().count()), cooldownMs, error))
        return false;
    if (!SelectTier(player, id, error)) return false;
    {
        std::lock_guard<std::mutex> lock(stateMutex);
        lastTierChangeMs[player->GetGUID().GetRawValue()] = uint64(GameTime::GetGameTimeMS().count());
    }
    return true;
}
void RegisterScripts()
{
    new TierWorld(); new TierBalance(); new TierPlayer(); new TierGroup(); new TierPhase(); new TierCreature(); new TierGameObject(); new TierMap(); new TierCombat(); new TierCommands();
}
}
