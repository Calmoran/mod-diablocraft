#include "dc_town_portal.h"
#include "dc_rifts.h"
#include "../combat/dc_item_powers.h"
#include "../common/dc_world.h"
#include "../common/dc_world_areas.h"
#include "../common/dc_tunables.h"
#include "Chat.h"
#include "DBCStores.h"
#include "GameObject.h"
#include "Group.h"
#include "InstanceSaveMgr.h"
#include "Map.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "Spell.h"
#include "SpellInfo.h"
#include "WorldSession.h"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <map>
#include <mutex>
#include <vector>

namespace DC::Rifts::TownPortal
{
    namespace
    {
        constexpr uint32 PORTAL_SPELL = 81167;                        // generated spell manifest
        constexpr uint32 SOURCE_OBJECT = 910012, HUB_OBJECT = 910013; // rifts_0007
        // tunables:rifts (09 section 2, the approved cast time). The
        // client's cast bar comes from Spell.dbc, so a change needs generate_spells.py
        // rerun and the patch rebuilt as well as `.dc tunables set`.
        inline int32 CastMs()
        {
            return static_cast<int32>(DC::Tunables::Get("rifts", "town_portal_cast_ms"));
        }
        struct Portal
        {
            uint64 token = 0;
            ObjectGuid owner, sourceObject, hubObject;
            WorldLocation source;
            uint32 instance = 0, sourcePhase = 1, hubPhase = 1;
            bool copy = false; // opened in an open-zone copy (map 751), not a rift
        };
        struct Removal
        {
            uint32 map, instance;
            ObjectGuid guid;
        };
        std::mutex portalMutex;
        std::map<ObjectGuid, Portal> portals;
        std::vector<Removal> removals;
        uint64 nextToken = 0;

        // Called with portalMutex held. Removal itself belongs to the object's map.
        void RemoveObjects(Portal const& portal)
        {
            if (portal.sourceObject)
                removals.push_back({portal.source.GetMapId(), portal.instance, portal.sourceObject});
            WorldLocation hub;
            if (portal.hubObject && World::HubPoint("town_portal", hub))
                removals.push_back({hub.GetMapId(), 0, portal.hubObject});
        }

        void RemoveOwner(ObjectGuid owner, uint64 token = 0)
        {
            std::lock_guard<std::mutex> lock(portalMutex);
            auto found = portals.find(owner);
            if (found == portals.end() || (token && found->second.token != token))
                return;
            RemoveObjects(found->second);
            portals.erase(found);
        }

        void ReplacePortal(Portal portal)
        {
            std::lock_guard<std::mutex> lock(portalMutex);
            auto found = portals.find(portal.owner);
            if (found != portals.end())
                RemoveObjects(found->second);
            portal.token = ++nextToken;
            portals[portal.owner] = std::move(portal);
        }

        bool FindPortal(ObjectGuid object, Portal& portal)
        {
            std::lock_guard<std::mutex> lock(portalMutex);
            for (auto const& [owner, value] : portals)
                if (value.sourceObject == object || value.hubObject == object)
                {
                    portal = value;
                    return true;
                }
            return false;
        }

        // A Town Portal is its caster's alone. The same test hides it
        // (PlaceOwned's claim: RiftHubObjectAI::CanBeSeen) and refuses it here, because the
        // core's use path (GetGameObjectIfCanInteractWith) checks distance and never
        // visibility, so a hidden portal is still clickable by a modified client.
        bool CanUse(Portal const& portal, Player* player)
        {
            return player && player->GetGUID() == portal.owner &&
                   player->GetPhaseMask() == (World::IsInHub(player) ? portal.hubPhase : portal.sourcePhase);
        }

        // One portal half, visible to its owner and nobody else from the very first create
        // packet. This builds the object instead of calling Map::SummonGameObject for the
        // reason dc_shatter.cpp Place gives: SummonGameObject runs Create and AddToMap in one
        // call, and AddToMap is when the create packet goes out, so there is no moment to make
        // the object private after it returns. The owner claim is live across Create (the
        // core builds the AI that answers CanBeSeen there, dc_rifts.cpp GetGameObjectAI) and
        // across AddToMap (the visibility notifier asks it there). The phase goes into Create
        // rather than SetPhaseMask afterwards, so the create packet already carries it, and
        // the object's display is the template's own, set by Create, before AddToMap - the
        // 3.3.5 client caches a model from the create packet.
        //
        // The other per-player routes were read in the pinned core and rejected: a phase bit
        // per player does not exist (tier phasing is a scalar, the TierPhase hook in dc_difficulty.cpp, and
        // DC::Areas rewrites the phase of registered spawns), a summon with an OWNER is shown
        // to the owner's friendly players by GameObject::IsAlwaysVisibleFor
        // (GameObject.cpp:1261), which runs before the AI is asked (Object.cpp:1818 vs 1839),
        // and GAMEOBJECT flags or conditions are per-entry, not per-object. The AI hook is
        // per-object and per-seer, and it is already how the rift's party-only hub objects
        // and the shatter preview are made.
        GameObject* PlaceOwned(Map* map, uint32 entry, WorldLocation const& at, uint32 phase, ObjectGuid owner)
        {
            if (!map || !sObjectMgr->GetGameObjectTemplate(entry))
                return nullptr;
            HubObjectClaim claim(owner);
            // The area filter refuses every object in an open-world area that is not on its open list; this
            // one the player opens on purpose, so it may stand there.
            DC::Areas::OwnPlacement placing;
            GameObject* object = new GameObject();
            float const o = at.GetOrientation();
            if (!object->Create(map->GenerateLowGuid<HighGuid::GameObject>(), entry, map, phase, at.GetPositionX(),
                                at.GetPositionY(), at.GetPositionZ(), o,
                                G3D::Quat(0, 0, std::sin(o / 2), std::cos(o / 2)), 100, GO_STATE_READY))
            {
                delete object;
                return nullptr;
            }
            // What Map::SummonGameObject does for a temporary object: not a spawn, so it must
            // never respawn itself.
            object->SetRespawnTime(0);
            object->SetSpawnedByDefault(false);
            map->AddToMap(object);
            return object;
        }

        bool ValidSource(Player* player)
        {
            if (!player || !player->IsAlive() || World::IsInHub(player) || player->IsBeingTeleported())
                return false;
            if (!player->GetInstanceId())
                return true;
            // A live rift keeps its own rules; the open-zone copy that bounty travel lands in is the open world.
            // Any other instance is refused.
            Rift rift;
            return Current(player, rift) || IsOpenZoneMap(player->GetMapId());
        }

        void CompleteCast(Player* player)
        {
            if (!ValidSource(player))
                return;
            WorldLocation hub;
            if (!World::HubPoint("town_portal", hub))
                return;
            if (!OpenPair(player))
            {
                ChatHandler(player->GetSession())
                    .SendSysMessage("Town Portal could not open. Your previous portal is unchanged.");
                return;
            }
            // The successful-cast hook runs after the spell's final checks. Do not
            // interrupt that same spell while it is unwinding its completion callback.
            if (!player->TeleportTo(hub, TELE_TO_SPELL))
            {
                RemoveOwner(player->GetGUID());
                ChatHandler(player->GetSession())
                    .SendSysMessage("Town Portal could not teleport you. Please try again.");
            }
        }

        class PortalSpellData final : public GlobalScript
        {
        public:
            PortalSpellData()
                : GlobalScript("dc_town_portal_data", {GLOBALHOOK_ON_LOAD_SPELL_CUSTOM_ATTR})
            {
            }
            void OnLoadSpellCustomAttr(SpellInfo* info) override
            {
                if (info->Id != PORTAL_SPELL)
                    return;
                info->Attributes &= ~SPELL_ATTR0_NOT_IN_COMBAT_ONLY_PEACEFUL;
                // No ABORT_ON_DMG: the core's per-spell flag cannot be skipped for one caster (Homing Pads), so PortalDamage below is the only damage interrupt.
                // The one change for everyone: a hit a shield absorbs in full (damage 0) no longer cancels the cast.
                info->InterruptFlags = SPELL_INTERRUPT_FLAG_MOVEMENT | SPELL_INTERRUPT_FLAG_INTERRUPT;
                for (uint32 id = 0; id < sSpellCastTimesStore.GetNumRows(); ++id)
                    if (auto* time = sSpellCastTimesStore.LookupEntry(id))
                        if (time->CastTime == CastMs())
                        {
                            info->CastTimeEntry = time;
                            break;
                        }
            }
        };

        class PortalCast final : public AllSpellScript
        {
        public:
            PortalCast()
                : AllSpellScript("dc_town_portal_cast", {ALLSPELLHOOK_ON_SPELL_CHECK_CAST, ALLSPELLHOOK_ON_CAST})
            {
            }
            void OnSpellCheckCast(Spell* spell, bool, SpellCastResult& result) override
            {
                if (spell->GetSpellInfo()->Id != PORTAL_SPELL)
                    return;
                Player* player = spell->GetCaster()->ToPlayer();
                if (!ValidSource(player))
                    result = SPELL_FAILED_NOT_HERE;
            }
            void OnSpellCast(Spell*, Unit* caster, SpellInfo const* info, bool) override
            {
                if (info->Id == PORTAL_SPELL)
                    if (Player* player = caster->ToPlayer())
                        CompleteCast(player);
            }
        };

        class PortalDamage final : public UnitScript
        {
        public:
            PortalDamage()
                : UnitScript("dc_town_portal_damage", true, {UNITHOOK_ON_DAMAGE, UNITHOOK_MODIFY_EXACT_DAMAGE})
            {
            }
            static bool PreparingPortal(Unit* victim)
            {
                if (!victim || !victim->IsPlayer())
                    return false;
                Spell* cast = victim->GetCurrentSpell(CURRENT_GENERIC_SPELL);
                return cast && cast->GetSpellInfo()->Id == PORTAL_SPELL && cast->getState() == SPELL_STATE_PREPARING;
            }
            // Homing Pads: the wearer's cast goes on and takes 1 - N/100 of the damage. The share comes off the exact hit, in whole
            // numbers rounded to the nearest: a 32-bit view saturates a hit past 4,294,967,295, and a view this hook changed would
            // replace the exact hit with the smaller number (core patch 0028's ApplyThroughView).
            void ModifyExactDamage(Unit*, Unit* victim, uint64& damage, DamageEffectType) override
            {
                if (!damage || !PreparingPortal(victim))
                    return;
                double const bubble = DC::Combat::ItemPowers::TownPortalFactor(victim->ToPlayer());
                if (bubble < 1.0)
                {
                    constexpr std::uint64_t scale = 1000000000;
                    unsigned __int128 const product = static_cast<unsigned __int128>(damage) *
                        static_cast<std::uint64_t>(std::llround(std::max(bubble, 0.0) * scale));
                    damage = static_cast<std::uint64_t>((product + scale / 2) / scale);
                }
            }
            void OnDamage(Unit*, Unit* victim, uint32& damage) override
            {
                // Also catches periodic/Diablocraft damage which bypasses stock pushback.
                if (!damage || !PreparingPortal(victim))
                    return;
                // Everyone else's cast is cancelled; the wearer's goes on, and ModifyExactDamage took its share.
                if (DC::Combat::ItemPowers::TownPortalFactor(victim->ToPlayer()) >= 1.0)
                    victim->InterruptNonMeleeSpells(false, PORTAL_SPELL);
            }
        };

        class PortalObjects final : public AllGameObjectScript
        {
        public:
            PortalObjects()
                : AllGameObjectScript("dc_town_portal_objects")
            {
            }
            bool CanGameObjectGossipHello(Player* player, GameObject* object) override
            {
                if (!player || !object || (object->GetEntry() != SOURCE_OBJECT && object->GetEntry() != HUB_OBJECT))
                    return false;
                ChatHandler chat(player->GetSession());
                Portal portal;
                if (!FindPortal(object->GetGUID(), portal) || !CanUse(portal, player))
                {
                    chat.SendSysMessage("That portal is unavailable or belongs to another player.");
                    return true;
                }
                if (player->IsInCombat() || !player->IsAlive())
                {
                    chat.SendSysMessage("Use portal objects out of combat. You can cast Town Portal in combat; a hit "
                                        "cancels the cast.");
                    return true;
                }
                if (object->GetEntry() == SOURCE_OBJECT)
                {
                    WorldLocation hub;
                    if (player->GetMapId() == portal.source.GetMapId() && player->GetInstanceId() == portal.instance &&
                        World::HubPoint("town_portal", hub))
                        player->TeleportTo(hub);
                    return true;
                }
                if (!World::IsInHub(player))
                    return true;
                if (portal.copy)
                {
                    // The core sends the player to the copy it picks (PlayerGetDestinationInstanceId, the party
                    // leader's bind), so the way back goes only while that is still this copy. The copy's map
                    // going away removes the pair (OnDestroyMap).
                    if (sInstanceSaveMgr->PlayerGetDestinationInstanceId(player, portal.source.GetMapId(),
                                                                         player->GetDifficulty(false)) != portal.instance)
                    {
                        chat.SendSysMessage("Your party is in another copy of that zone now.");
                        return true;
                    }
                }
                else if (portal.instance)
                {
                    if (!IsLiveInstance(portal.source.GetMapId(), portal.instance))
                    {
                        chat.SendSysMessage("That rift has closed.");
                        RemoveOwner(portal.owner, portal.token);
                        return true;
                    }
                    auto* bind = sInstanceSaveMgr->PlayerGetBoundInstance(player->GetGUID(), portal.source.GetMapId(),
                                                                          DUNGEON_DIFFICULTY_NORMAL);
                    if (!bind || !bind->save || bind->save->GetInstanceId() != portal.instance)
                    {
                        chat.SendSysMessage("You are no longer bound to that rift.");
                        return true;
                    }
                }
                // Keep both ends usable after returning. Only replacement, logout or
                // source closure removes the pair; a round trip does not consume it.
                if (!player->TeleportTo(portal.source))
                    chat.SendSysMessage("Town Portal could not return you. The portal is still available.");
                return true;
            }
        };

        class PortalMaps final : public AllMapScript
        {
        public:
            PortalMaps()
                : AllMapScript("dc_town_portal_maps", {ALLMAPHOOK_ON_MAP_UPDATE, ALLMAPHOOK_ON_DESTROY_MAP})
            {
            }
            void OnMapUpdate(Map* map, uint32) override
            {
                std::vector<ObjectGuid> mine;
                std::vector<Portal> pending;
                WorldLocation hub;
                bool const isHub =
                    World::HubPoint("town_portal", hub) && map->GetId() == hub.GetMapId() && !map->GetInstanceId();
                {
                    std::lock_guard<std::mutex> lock(portalMutex);
                    for (auto it = removals.begin(); it != removals.end();)
                        if (it->map == map->GetId() && it->instance == map->GetInstanceId())
                        {
                            mine.push_back(it->guid);
                            it = removals.erase(it);
                        }
                        else
                            ++it;
                    if (isHub)
                        for (auto const& [owner, portal] : portals)
                            if (!portal.hubObject)
                                pending.push_back(portal);
                }
                for (ObjectGuid guid : mine)
                    if (auto* object = map->GetGameObject(guid))
                        object->Delete();
                for (Portal const& portal : pending)
                {
                    GameObject* object = PlaceOwned(map, HUB_OBJECT, hub, portal.hubPhase, portal.owner);
                    if (!object)
                        continue;
                    bool keep = false;
                    {
                        std::lock_guard<std::mutex> lock(portalMutex);
                        auto found = portals.find(portal.owner);
                        if (found != portals.end() && found->second.token == portal.token && !found->second.hubObject)
                        {
                            found->second.hubObject = object->GetGUID();
                            keep = true;
                        }
                    }
                    if (!keep)
                        object->Delete(); // Replaced/closed while this map spawned it.
                }
            }
            void OnDestroyMap(Map* map) override
            {
                std::lock_guard<std::mutex> lock(portalMutex);
                for (auto it = portals.begin(); it != portals.end();)
                    if (it->second.source.GetMapId() == map->GetId() && it->second.instance == map->GetInstanceId())
                    {
                        RemoveObjects(it->second);
                        it = portals.erase(it);
                    }
                    else
                        ++it;
                removals.erase(std::remove_if(removals.begin(), removals.end(), [&](Removal const& r)
                                              { return r.map == map->GetId() && r.instance == map->GetInstanceId(); }),
                               removals.end());
            }
        };

        class PortalPlayer final : public PlayerScript
        {
        public:
            PortalPlayer()
                : PlayerScript("dc_town_portal_player", {PLAYERHOOK_ON_LOGOUT})
            {
            }
            void OnPlayerLogout(Player* player) override
            {
                RemoveOwner(player->GetGUID());
            }
        };
    } // namespace

    // The pair as a cast opens it, without the cast's move: the source half where the player stands, the
    // hub half on the hub map's next update, the caster's old pair replaced. Revive in town (11 §3) opens
    // it where a character fell, then moves it. False when it could not open; the old pair stays.
    bool OpenPair(Player* player)
    {
        if (!ValidSource(player))
            return false;
        Portal portal;
        portal.owner = player->GetGUID();
        portal.source = WorldLocation(player->GetMapId(), player->GetPositionX(), player->GetPositionY(),
                                      player->GetPositionZ(), player->GetOrientation());
        portal.instance = player->GetInstanceId();
        portal.sourcePhase = player->GetPhaseMask();
        Rift rift;
        portal.copy = portal.instance && !Current(player, rift);
        // The Sanctum is one phase for every tier, so the hub half is always placed there.
        portal.hubPhase = World::SanctumPhase;
        GameObject* object =
            PlaceOwned(player->GetMap(), SOURCE_OBJECT, portal.source, portal.sourcePhase, portal.owner);
        if (!object)
            return false;
        portal.sourceObject = object->GetGUID();
        ReplacePortal(portal);
        return true;
    }

    void CloseInstance(std::uint32_t instanceId)
    {
        std::lock_guard<std::mutex> lock(portalMutex);
        for (auto it = portals.begin(); it != portals.end();)
            if (it->second.instance == instanceId)
            {
                RemoveObjects(it->second);
                it = portals.erase(it);
            }
            else
                ++it;
    }

    void RegisterScripts()
    {
        new PortalSpellData();
        new PortalCast();
        new PortalDamage();
        new PortalObjects();
        new PortalMaps();
        new PortalPlayer();
    }
} // namespace DC::Rifts::TownPortal
