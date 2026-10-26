#include "dc_ground_loot.h"

#include "../common/dc_tunables.h"
#include "../items/dc_quality_rule.h"
#include "../rifts/dc_rifts.h"
#include "Chat.h"
#include "CreatureAI.h"
#include "DatabaseEnv.h"
#include "Log.h"
#include "Map.h"
#include "Player.h"
#include "PlayerEconomy.h"
#include "ScriptMgr.h"
#include "SpellAuras.h"
#include "TemporarySummon.h"
#include "WorldPacket.h"
#include "WorldSession.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <vector>

// Literal audit (docs/research/literal-audit-claude.md): the numbers below are
// constants, not tunables - recorded here, nothing else changes.
// Constant (160): chat line width before wrapping; Output formatting.

namespace DC::Loot
{
namespace
{
using Clock = std::chrono::steady_clock;
struct Visual { uint8 level = 0; uint32 spell = 0; };
struct Preview
{
    ObjectGuid carrier, owner;
    Clock::time_point deadline;
    bool inRift = false;
    bool ground = false;
};
std::mutex mutex;
std::map<uint32, uint32> carriers;
std::map<std::string, Visual> visuals;
std::map<Map*, std::vector<Preview>> previews;
float scale = 0;
uint32 expirySeconds = 0;
bool ready = false;

// ---------------------------------------------- the label's identity channel
// A 3.3.5a nameplate carries no guid and no unit token
// (docs/research/ground-loot-client.md C3), so the addon cannot tell a drop's
// plate from a monster's on its own. It is told: DCGROUND carries the set of
// carriers this player owns right now, one level|rarity|name triple each. That
// set is authoritative for "this plate is a drop" and for its rarity; the level
// digit the client draws is the addon's cross-check, not its only channel.
//
// Same wire as DCSHEET and DCPARAGON (dc_inventory.cpp, dc_paragon.cpp): B
// clears, V carries values well inside one chat packet, E commits, so a
// half-received push never draws a label.
struct Pushed
{
    Map* map = nullptr;
    std::string payload;
    Clock::time_point at;
};
std::map<uint64, Pushed> pushed;
// A /reload empties the addon's copy without the server knowing, so a set that
// has not moved is repeated this often. Nothing else needs it: every real
// change is pushed the tick it happens.
// tunables:ui.
std::chrono::seconds RepeatAfter()
{
    return std::chrono::seconds(
        static_cast<long long>(DC::Tunables::Get("ui", "ground_loot_repeat_seconds")));
}

// Caller holds the mutex. visuals is validated 1-5 at startup, so this is the
// same mapping read backwards rather than a second table to keep in step.
char const* RarityForLevel(uint8 level)
{
    for (auto const& [rarity, visual] : visuals)
        if (visual.level == level)
            return rarity.c_str();
    return nullptr;
}

// The drawn label, as the addon and DCGROUND both spell it: the carrier's name
// with the field separator blanked.
std::string LabelName(Creature const* carrier)
{
    std::string name = carrier->GetName();
    std::replace(name.begin(), name.end(), '|', ' ');
    return name;
}

void Wire(Player* player, std::string const& body)
{
    WorldPacket packet;
    ChatHandler::BuildChatPacket(packet, CHAT_MSG_WHISPER, LANG_ADDON, player, player, "DCGROUND\t" + body);
    player->GetSession()->SendPacket(&packet);
}

void SendLabels(Player* player, std::vector<std::string> const& labels)
{
    Wire(player, "B");
    std::string line;
    for (std::string const& label : labels)
    {
        if (!line.empty() && line.size() + label.size() + 1 > 160)
        {
            Wire(player, "V|" + line);
            line.clear();
        }
        if (!line.empty())
            line += "|";
        line += label;
    }
    if (!line.empty())
        Wire(player, "V|" + line);
    Wire(player, "E");
}

// Runs at the end of the map tick that already walks every live carrier, so one
// call site covers the drop, the pickup, the expiry, the rift close and the
// logout. A player who leaves the map needs no push: the addon empties its own
// set on PLAYER_ENTERING_WORLD, because a carrier never follows anyone across a
// map boundary.
void PushCarrierLabels(Map* map)
{
    std::map<uint64, std::vector<std::string>> current;
    std::vector<uint64> departed;
    {
        std::lock_guard<std::mutex> lock(mutex);
        auto found = previews.find(map);
        if (found != previews.end())
            for (Preview const& drop : found->second)
            {
                // A GM preview carrier gets a label too: it is the same creature
                // wearing the same beam, and `.dc ground` is the only way to look
                // at a rarity on demand. Only the CLICK differs between the two.
                //
                // Map objects on this map's own thread, exactly as the sweep
                // above reads them.
                Creature* carrier = map->GetCreature(drop.carrier);
                if (!carrier)
                    continue;
                char const* rarity = RarityForLevel(carrier->GetLevel());
                if (!rarity)
                    continue;
                current[drop.owner.GetRawValue()].push_back(
                    std::to_string(unsigned(carrier->GetLevel())) + "|" + rarity + "|" + LabelName(carrier));
            }
        for (auto const& [owner, held] : pushed)
            if (held.map == map && !current.count(owner))
                departed.push_back(owner);
    }
    if (current.empty() && departed.empty())
        return;

    std::vector<std::string> const none;
    Map::PlayerList const& players = map->GetPlayers();
    for (Map::PlayerList::const_iterator itr = players.begin(); itr != players.end(); ++itr)
    {
        Player* player = itr->GetSource();
        if (!player || !player->IsInWorld() || !player->GetSession())
            continue;
        uint64 const owner = player->GetGUID().GetRawValue();
        auto entry = current.find(owner);
        std::vector<std::string> const& labels = entry == current.end() ? none : entry->second;
        std::string signature;
        for (std::string const& label : labels)
            signature += label + "\n";
        {
            std::lock_guard<std::mutex> lock(mutex);
            auto held = pushed.find(owner);
            bool const same = held != pushed.end() && held->second.map == map &&
                              held->second.payload == signature &&
                              Clock::now() - held->second.at < RepeatAfter();
            if (same)
                continue;
            // An owner with nothing left is dropped from the table, but the
            // empty push still goes out: that is what clears the last label
            // after a pickup or an expiry.
            if (signature.empty() && held == pushed.end())
                continue;
            if (signature.empty())
                pushed.erase(held);
            else
                pushed[owner] = {map, signature, Clock::now()};
        }
        SendLabels(player, labels);
    }
    // Owners whose carriers are gone and who are no longer on this map: their
    // addon cleared itself, so only the bookkeeping has to catch up.
    std::lock_guard<std::mutex> lock(mutex);
    for (uint64 owner : departed)
    {
        auto held = pushed.find(owner);
        if (held != pushed.end() && held->second.map == map)
            pushed.erase(held);
    }
}

std::unique_ptr<TempSummon> PrepareCarrier(Player* player, uint32 entry, Visual visual,
                                           float carrierScale, Position const& position)
{
        Map* map = player->GetMap();
        map->LoadGrid(position.GetPositionX(), position.GetPositionY());
        auto summon = std::make_unique<TempSummon>(nullptr, player->GetGUID());
        if (!summon->Create(map->GenerateLowGuid<HighGuid::Unit>(), map, player->GetPhaseMask(), entry, 0,
                            position.GetPositionX(), position.GetPositionY(), position.GetPositionZ(), position.GetOrientation()))
            return nullptr;
        summon->SetHomePosition(position);
        summon->InitStats(0);
        summon->SetTempSummonType(TEMPSUMMON_MANUAL_DESPAWN);
        summon->SetVisibleBySummonerOnly(true);
        summon->RemoveUnitFlag(UNIT_FLAG_NOT_SELECTABLE);
        summon->SetUnitFlag(UNIT_FLAG_NON_ATTACKABLE | UNIT_FLAG_IMMUNE_TO_PC | UNIT_FLAG_IMMUNE_TO_NPC);
        summon->SetReactState(REACT_PASSIVE);
        summon->SetIsCombatDisallowed(true);
        summon->SetLevel(visual.level, false);
        summon->SetObjectScale(carrierScale);
        // Ground drops must survive walking away before expiry. Active objects
        // keep their grids loaded until pickup/loss; set this before insertion.
        summon->setActive(true);
        // beam_spell 0 is the sheet's explicit "no beam" (white drops):
        // the label alone marks the drop, so no aura is added.
        if (visual.spell)
        {
            Aura* aura = summon->AddAura(visual.spell, summon.get());
            if (!aura)
            {
                ChatHandler(player->GetSession()).SendSysMessage("Carrier beam failed; marker was not added to the map.");
                return nullptr;
            }
            aura->SetMaxDuration(-1);
            aura->SetDuration(-1);
        }
        if (summon->GetOwnerGUID())
        {
            ChatHandler(player->GetSession()).SendSysMessage("Carrier unexpectedly owned; marker was not added to the map.");
            return nullptr;
        }
        return summon;
}

// Whether the map tracks this carrier and, if it does, whether it pays (a real
// drop) or only dismisses (a GM preview). Caller does not hold the mutex.
std::optional<bool> Tracked(Map* map, ObjectGuid carrier)
{
    std::lock_guard<std::mutex> lock(mutex);
    auto found = previews.find(map);
    if (found != previews.end())
        for (auto const& drop : found->second)
            if (drop.carrier == carrier) return drop.ground;
    return std::nullopt;
}

// The carrier's summoner, alive, on its map and phase. Reach is checked apart,
// because only the label click answers "too far".
bool OwnedBy(TempSummon* summon, Player* player)
{
    return player && summon && summon->IsVisibleBySummonerOnly() &&
        summon->GetSummonType() != TEMPSUMMON_DESPAWNED &&
        summon->GetSummonerGUID() == player->GetGUID() && player->IsAlive() &&
        player->IsInMap(summon) && player->InSamePhase(summon);
}

// Both ways of taking a drop - the right-click on the carrier and the click on
// its label - end here, so a real drop only ever pays through ClaimGroundLoot
// (one dc_loot_buffer row, deleted in the paying transaction) and a preview is
// dismissed the same way whichever was used. Returns true when the carrier is
// gone: claimed or dismissed.
bool Take(Player* player, TempSummon* summon, bool ground, std::uint8_t& storeError)
{
    storeError = 0;
    if (ground)
        return ClaimGroundLoot(player, summon, &storeError);
    ChatHandler(player->GetSession()).SendSysMessage("Ground-loot preview dismissed; no item was granted.");
    summon->UnSummon();
    return true;
}

// A clicked label names only what a 3.3.5a plate draws: its level digit and
// its name. Two of the player's drops can draw the same label - the same base
// item at the same rarity, though their item level may differ - and the
// nearest of them is the one taken.
ObjectGuid NearestLabelled(Player* player, uint8 level, std::string const& name)
{
    Map* map = player->GetMap();
    std::vector<ObjectGuid> mine;
    {
        std::lock_guard<std::mutex> lock(mutex);
        auto found = previews.find(map);
        if (found != previews.end())
            for (auto const& drop : found->second)
                if (drop.owner == player->GetGUID()) mine.push_back(drop.carrier);
    }
    ObjectGuid nearest;
    float best = std::numeric_limits<float>::max();
    for (ObjectGuid const& guid : mine)
    {
        Creature* carrier = map->GetCreature(guid);
        if (!carrier || carrier->GetLevel() != level || LabelName(carrier) != name ||
            !OwnedBy(carrier->ToTempSummon(), player))
            continue;
        float const distance = player->GetExactDist(carrier);
        if (distance < best) { best = distance; nearest = guid; }
    }
    return nearest;
}

// "DCPICKUP<tab>0x..." is the targeted carrier's GUID as UnitGUID prints it;
// "DCPICKUP<tab>level<tab>name" is a clicked label. Anything else is nothing.
ObjectGuid Requested(Player* player, std::string const& text)
{
    std::size_t const tab = text.find('\t');
    std::string const number = text.substr(0, tab);
    uint64 value = 0;
    try
    {
        std::size_t used = 0;
        value = std::stoull(number, &used, tab == std::string::npos ? 16 : 10);
        if (used != number.size()) return ObjectGuid::Empty;
    }
    catch (std::exception const&) { return ObjectGuid::Empty; }
    if (tab == std::string::npos)
        return ObjectGuid(value).IsCreature() ? ObjectGuid(value) : ObjectGuid::Empty;
    if (!value || value > std::numeric_limits<uint8>::max())
        return ObjectGuid::Empty;
    return NearestLabelled(player, static_cast<uint8>(value), text.substr(tab + 1));
}

class GroundCarrierAI final : public CreatureAI
{
public:
    explicit GroundCarrierAI(Creature* creature) : CreatureAI(creature) { }
    void Reset() override
    {
        me->SetReactState(REACT_PASSIVE);
        me->SetIsCombatDisallowed(true);
        me->RemoveUnitFlag(UNIT_FLAG_NOT_SELECTABLE);
    }
    void UpdateAI(uint32) override { }
    void AttackStart(Unit*) override { }
    void MoveInLineOfSight(Unit*) override { }
    void JustStartedThreateningMe(Unit*) override { }
    void DamageTaken(Unit*, uint32& damage, DamageEffectType, SpellSchoolMask) override { damage = 0; }
    bool CanBeSeen(Player const* seer) override
    {
        TempSummon* summon = me->ToTempSummon();
        return seer && summon && summon->IsVisibleBySummonerOnly() &&
            summon->GetSummonerGUID() == seer->GetGUID();
    }
    bool BeforeSpellClick(Unit* clicker) override
    {
        // Production clicks claim descriptors; preview clicks only dismiss.
        // There is no dummy spell row and no gossip menu.
        // The stock spell-click path (SpellHandler.cpp:721, Unit.cpp:15521)
        // checks no distance, so reach is checked here, with the same
        // INTERACTION_DISTANCE the label click uses.
        Player* player = clicker ? clicker->ToPlayer() : nullptr;
        TempSummon* summon = me->ToTempSummon();
        if (OwnedBy(summon, player) && player->IsWithinDistInMap(me, INTERACTION_DISTANCE))
        {
            std::uint8_t storeError = 0;
            if (!Take(player, summon, Tracked(me->GetMap(), me->GetGUID()).value_or(false), storeError) && storeError)
                player->SendEquipError(static_cast<InventoryResult>(storeError), nullptr, nullptr);
        }
        return false;
    }
};
class GroundCarrierScript final : public CreatureScript
{
public:
    GroundCarrierScript() : CreatureScript("dc_ground_loot_carrier") { }
    CreatureAI* GetAI(Creature* creature) const override { return new GroundCarrierAI(creature); }
};
class GroundLootWorld final : public WorldScript
{
public:
    GroundLootWorld() : WorldScript("dc_ground_loot_world", {WORLDHOOK_ON_STARTUP}) { }
    void OnStartup() override
    {
        auto parameters = WorldDatabase.Query("SELECT parameter,tuned_value FROM dc_ground_loot_parameter");
        auto mapping = WorldDatabase.Query("SELECT base_item,creature_entry FROM dc_ground_loot_carrier");
        auto beams = WorldDatabase.Query("SELECT rarity,plate_level,beam_spell FROM dc_ground_loot_visual");
        if (!parameters || !mapping || !beams)
        {
            LOG_ERROR("server", "[DC ground loot] Preview disabled: apply WORLD loot_0005_ground_carriers.sql.");
            return;
        }
        double loadedScale = 0, loadedExpiry = 0;
        do
        {
            auto* fields = parameters->Fetch();
            auto name = fields[0].Get<std::string>();
            if (name == "carrier_scale") loadedScale = fields[1].Get<double>();
            if (name == "open_world_expiry_seconds") loadedExpiry = fields[1].Get<double>();
        } while (parameters->NextRow());
        if (!std::isfinite(loadedScale) || loadedScale <= 0 || loadedScale > std::numeric_limits<float>::max() ||
            !std::isfinite(loadedExpiry) || loadedExpiry <= 0 || std::floor(loadedExpiry) != loadedExpiry ||
            loadedExpiry > std::numeric_limits<uint32>::max())
        {
            LOG_ERROR("server", "[DC ground loot] Preview disabled: invalid scale or expiry.");
            return;
        }
        std::map<uint32, uint32> loadedCarriers;
        do
        {
            auto* fields = mapping->Fetch();
            loadedCarriers.emplace(fields[0].Get<uint32>(), fields[1].Get<uint32>());
        } while (mapping->NextRow());
        std::map<std::string, Visual> loadedVisuals;
        do
        {
            auto* fields = beams->Fetch();
            loadedVisuals.emplace(fields[0].Get<std::string>(), Visual{fields[1].Get<uint8>(), fields[2].Get<uint32>()});
        } while (beams->NextRow());
        uint8 expectedLevel = 0;
        for (char const* rarity : {"normal", "magic", "rare", "legendary", "set"})
            if (!loadedVisuals.count(rarity) || loadedVisuals[rarity].level != ++expectedLevel)
            {
                LOG_ERROR("server", "[DC ground loot] Preview disabled: invalid rarity {}.", rarity);
                return;
            }
        if (!CharacterDatabase.Query("SELECT COUNT(carrier_guid) FROM dc_loot_buffer") ||
            !CharacterDatabase.Query("SELECT COUNT(*) FROM dc_loot_claim_check"))
        {
            LOG_ERROR("server", "[DC ground loot] Apply CHARACTERS loot_0006_ground_descriptor.sql.");
            return;
        }
        // Runtime carriers cannot survive a server restart; stale descriptors
        // are losses, never automatic deliveries at next login.
        CharacterDatabase.DirectExecute("DELETE FROM dc_loot_buffer WHERE kind='ground'");
        std::lock_guard<std::mutex> lock(mutex);
        carriers = std::move(loadedCarriers);
        visuals = std::move(loadedVisuals);
        scale = static_cast<float>(loadedScale);
        expirySeconds = static_cast<uint32>(loadedExpiry);
        ready = true;
        LOG_INFO("server.loading", "[DC ground loot] {} templates ready for descriptor delivery and GM previews.", carriers.size());
    }
};
class GroundLootMaps final : public AllMapScript
{
public:
    GroundLootMaps() : AllMapScript("dc_ground_loot_maps", {ALLMAPHOOK_ON_MAP_UPDATE, ALLMAPHOOK_ON_DESTROY_MAP}) { }
    void OnMapUpdate(Map* map, uint32) override
    {
        std::vector<Preview> remove;
        {
            std::lock_guard<std::mutex> lock(mutex);
            auto found = previews.find(map);
            if (found != previews.end())
            {
                bool const live = DC::Rifts::IsLiveInstance(map->GetId(), map->GetInstanceId());
                auto& drops = found->second;
                for (auto it = drops.begin(); it != drops.end();)
                {
                    if ((it->inRift ? !live : Clock::now() >= it->deadline) || !map->GetCreature(it->carrier))
                    {
                        remove.push_back(*it);
                        it = drops.erase(it);
                    }
                    else ++it;
                }
                if (drops.empty()) previews.erase(found);
            }
        }
        // Map objects are only accessed on this map's thread.
        for (auto const& drop : remove)
        {
            if (drop.ground) LoseGroundLoot(drop.carrier.GetRawValue(),map->GetId(),map->GetInstanceId());
            if (Creature* creature = map->GetCreature(drop.carrier))
                if (TempSummon* summon = creature->ToTempSummon()) summon->UnSummon();
        }
        // The label set the owner's addon holds, after every removal this tick
        // made and every carrier this tick published.
        PushCarrierLabels(map);
    }
    void OnDestroyMap(Map* map) override
    {
        std::vector<Preview> lost;
        {
            std::lock_guard<std::mutex> lock(mutex);
            auto found = previews.find(map);
            if (found != previews.end()) { lost = std::move(found->second); previews.erase(found); }
        }
        for (auto const& drop : lost)
            if (drop.ground) LoseGroundLoot(drop.carrier.GetRawValue(),map->GetId(),map->GetInstanceId());
    }
};
class GroundLootPlayers final : public PlayerScript
{
public:
    GroundLootPlayers() : PlayerScript("dc_ground_loot_players",
        {PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_BEFORE_SEND_CHAT_MESSAGE}) { }
    void OnPlayerLogout(Player* player) override
    {
        LosePlayerGroundLoot(player);
        std::lock_guard<std::mutex> lock(mutex);
        // No foreign-map access during logout. Poison deadlines, including
        // rift drops; a quick relog must never revive a pending removal.
        for (auto& [map, drops] : previews)
            for (auto& drop : drops)
                if (drop.owner == player->GetGUID()) { drop.inRift = false; drop.deadline = Clock::time_point::min(); }
    }

    // The label click (docs/contracts/ground-loot-messages.md).
    // dc_ground_plates.lua sends a self-addressed DCPICKUP addon message, which
    // this hook sees before the chat handler's type switch - the dc_classes.cpp
    // DCSLOT bridge. It is C++ rather than AIO because the claim is C++ and ALE
    // cannot call into it. Two forms (Requested): the label's own click names
    // the label; a click on the client's plate that targeted the carrier
    // names its GUID.
    //
    // Nothing from the client is trusted: the carrier must be one this map
    // tracks, summoned for this player, alive and in reach, and the claim is
    // the same Take() the right-click uses.
    void OnPlayerBeforeSendChatMessage(Player* player, uint32& /*type*/, uint32& lang, std::string& msg) override
    {
        static std::string const prefix = "DCPICKUP\t";
        if (lang != LANG_ADDON || !player || !player->IsInWorld() || msg.compare(0, prefix.size(), prefix) != 0)
            return;
        ObjectGuid const guid = Requested(player, msg.substr(prefix.size()));
        if (!guid)
            return;
        Map* map = player->GetMap();
        std::optional<bool> const ground = Tracked(map, guid);
        Creature* carrier = ground ? map->GetCreature(guid) : nullptr;
        TempSummon* summon = carrier ? carrier->ToTempSummon() : nullptr;
        if (!OwnedBy(summon, player))
            return;
        if (!player->IsWithinDistInMap(carrier, INTERACTION_DISTANCE))
        {
            // The addon shows the stock ERR_USE_TOO_FAR in the UI error frame.
            // Stock SMSG_LOOT_RESPONSE LOOT_ERROR_TOO_FAR was tried first and
            // the client shows nothing for it without a loot window.
            Wire(player, "F");
            return;
        }
        // The carrier despawns on success, which drops the client's target
        // with it; the server-side selection is cleared to match. A refusal is
        // the core's own result, sent as it is - the gift of a wrong message is
        // what this path used to give.
        std::uint8_t storeError = 0;
        bool const taken = Take(player, summon, *ground, storeError);
        if (taken && player->GetTarget() == guid)
            player->SetSelection(ObjectGuid::Empty);
        else if (!taken && storeError)
            player->SendEquipError(static_cast<InventoryResult>(storeError), nullptr, nullptr);
    }
};
class GroundLootCommand final : public CommandScript
{
public:
    GroundLootCommand() : CommandScript("dc_ground_loot_command") { }
    Acore::ChatCommands::ChatCommandTable GetCommands() const override
    {
        using namespace Acore::ChatCommands;
        static ChatCommandTable commands = {{"ground", HandlePreview, SEC_ADMINISTRATOR, Console::No}};
        static ChatCommandTable root = {{"dc", commands}};
        return root;
    }
    static bool HandlePreview(ChatHandler* handler, uint32 baseItem, std::string rarity)
    {
        Player* player = handler->GetSession()->GetPlayer();
        uint32 entry, lifetime;
        float carrierScale;
        Visual visual;
        {
            std::lock_guard<std::mutex> lock(mutex);
            if (!ready || !carriers.count(baseItem) || !visuals.count(rarity))
            {
                handler->SendSysMessage("Usage: .dc ground <base item entry> <normal|magic|rare|legendary|set|primal>; requires WORLD loot_0005 and rebuild. Preview only.");
                return false;
            }
            entry = carriers.at(baseItem); visual = visuals.at(rarity);
            carrierScale = scale; lifetime = expirySeconds;
        }
        Map* map = player->GetMap();
        Position const position = player->GetPosition();
        auto summon = PrepareCarrier(player, entry, visual, carrierScale, position);
        if (!summon) return false;
        // All private/visual/interaction properties are set BEFORE insertion.
        // Match the core summon path: AddToMap is instantiated for Creature,
        // not TempSummon. The same configured object is inserted via its base.
        if (!map->AddToMap(summon->ToCreature())) return false;
        TempSummon* published = summon.release();
        published->InitSummon();
        bool const inRift = DC::Rifts::IsLiveInstance(map->GetId(), map->GetInstanceId());
        {
            std::lock_guard<std::mutex> lock(mutex);
            previews[map].push_back({published->GetGUID(), player->GetGUID(), Clock::now() + std::chrono::seconds(lifetime), inRift});
        }
        handler->PSendSysMessage("Preview carrier {}: level {}, beam {}, scale {}; click dismisses, no loot granted.",
                                 entry, unsigned(visual.level), visual.spell ? std::to_string(visual.spell) : "none",
                                 carrierScale);
        return true;
    }
};
}
bool GroundDeliveryEnabled()
{
    auto row = WorldDatabase.Query("SELECT tuned_value FROM dc_ground_loot_parameter WHERE parameter='ground_delivery_enabled'");
    return row && (*row)[0].Get<double>() == 1.0;
}
unsigned BossMaterialCount()
{
    auto row = WorldDatabase.Query("SELECT tuned_value FROM dc_ground_loot_parameter WHERE parameter='boss_material_count'");
    if (!row) return 0;
    double value = (*row)[0].Get<double>();
    return std::isfinite(value) && value >= 0 && value <= std::numeric_limits<uint32>::max() && std::floor(value) == value
        ? static_cast<unsigned>(value) : 0;
}
bool DropGroundLoot(Player* player, uint32 entry, unsigned itemLevel, std::string const& rarity,
                    char const* source, unsigned tier, char const* contentKind, unsigned count,
                    Position const& position, std::string const& rollClass, std::string const& quality)
{
    uint32 creatureEntry, lifetime;
    float carrierScale;
    Visual visual;
    {
        std::lock_guard<std::mutex> lock(mutex);
        // A Primal has its own beam row (ground_loot_visuals.csv "primal"); an Ancient keeps
        // its rarity's beam, and so does a Primal on a sheet that has no primal row (a drop is never refused
        // for its look). The descriptor's rarity column stays the item's own rarity.
        auto look = quality == "primal" ? visuals.find("primal") : visuals.end();
        if (look == visuals.end()) look = visuals.find(rarity);
        if (!ready || !player || !carriers.count(entry) || look == visuals.end()) return false;
        creatureEntry = carriers.at(entry); visual = look->second;
        carrierScale = scale; lifetime = expirySeconds;
    }
    auto prepared = PrepareCarrier(player, creatureEntry, visual, carrierScale, position);
    if (!prepared) return false;
    auto held = std::make_shared<std::unique_ptr<TempSummon>>(std::move(prepared));
    Map* map = player->GetMap();
    bool const inRift = DC::Rifts::IsLiveInstance(map->GetId(), map->GetInstanceId());
    uint64 const guid = (*held)->GetGUID().GetRawValue();
    auto transaction = PlayerEconomy::BeginTransaction();
    // roll_class: the class a rolled descriptor rolls for at pickup
    // (dc_roll_class.h rule 4); empty for gems and materials.
    std::string safeRarity = rarity, safeSource = source, safeKind = contentKind, safeClass = rollClass;
    CharacterDatabase.EscapeString(safeRarity); CharacterDatabase.EscapeString(safeSource); CharacterDatabase.EscapeString(safeKind);
    CharacterDatabase.EscapeString(safeClass);
    transaction->Append(
        "INSERT INTO dc_loot_buffer (guid,base_item,item_level,rarity,drop_source,tier,kind,content_kind,carrier_guid,"
        "map_id,instance_id,phase_mask,drop_x,drop_y,drop_z,drop_o,in_rift,drop_count,expires_at,roll_class,quality_tier) "
        "VALUES ({},{},{},'{}','{}',{},'ground','{}',{},{},{},{},{},{},{},{},{},{},"
        "IF({},'2038-01-01 00:00:00',DATE_ADD(NOW(),INTERVAL {} SECOND)),'{}','{}')",
        player->GetGUID().GetRawValue(), entry, itemLevel, safeRarity, safeSource, tier, safeKind, guid,
        map->GetId(),map->GetInstanceId(),player->GetPhaseMask(),position.GetPositionX(),position.GetPositionY(),
        position.GetPositionZ(),position.GetOrientation(),inRift ? 1 : 0,count,inRift ? 1 : 0,lifetime,safeClass,
        DC::Quality::Clean(quality));
    auto publish = [held,map,player,lifetime,inRift,guid]()
    {
        // The prepared object already carries every private/visual property.
        if (!player->IsInWorld() || player->GetMap() != map || !map->AddToMap((*held)->ToCreature()))
        {
            LoseGroundLoot(guid,map->GetId(),map->GetInstanceId());
            return;
        }
        TempSummon* summon = held->release();
        summon->InitSummon();
        std::lock_guard<std::mutex> lock(mutex);
        previews[map].push_back({summon->GetGUID(),player->GetGUID(),Clock::now()+std::chrono::seconds(lifetime),inRift,true});
    };
    if (PlayerEconomy::Current()) PlayerEconomy::AfterCommit(publish);
    else
    {
        if (!CharacterDatabase.AsyncCommitTransaction(transaction).m_future.get()) return false;
        publish();
    }
    return true;
}

void RegisterGroundLootScripts()
{
    new GroundCarrierScript();
    new GroundLootWorld();
    new GroundLootMaps();
    new GroundLootPlayers();
    new GroundLootCommand();
}
}
