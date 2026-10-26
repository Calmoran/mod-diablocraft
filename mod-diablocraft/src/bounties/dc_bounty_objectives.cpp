/*
 * World of DiabloCraft - bounties W2: the named Unique and the Click objectives (docs/research/bounties.md 5.6 and the Click row of docs/research/bounty-types.csv).
 *
 * A player in a bounty's zone copy (dc_bounties map and zone) gets their board's open bounties of that zone put there,
 * owned by the board's owner (their party, else themselves; OwnerKey): a Kill's named Unique on its spot, or a Click's
 * objectives still to do, one gameobject a spot, each with its guard pack (the survey's own pack at that anchor). Each
 * is summoned inside a claim, so the AI the core builds during the summon is already the owner's (the HubObjectClaim
 * reason, dc_rifts.h): only the owner's players see it, the monsters pick and take damage only from them
 * (Rifts::NewOwnedMonsterAI), and several parties can share one copy later with no rework.
 *
 * The Unique's death completes the bounty, and only on the board of the party that owns it. A Click objective starts a
 * channel (the town portal's cast shape, dc_town_portal.cpp): damage interrupts it unless the player is immune to crowd
 * control (D3: maxroll bounties); when it finishes the objective is done and goes, and the last one completes the
 * bounty.
 *
 * When to look: on a player's update, only when their map is a bounty map and their board epoch, instance, zone or area
 * moved since their last look. A look puts back only what is missing (a Unique alive, an objective standing are left).
 */

#include "dc_bounties.h"

#include "../combat/dc_spell_shells.h"
#include "../common/dc_tunables.h"
#include "../rifts/dc_rifts.h"

#include "Chat.h"
#include "CreatureAI.h"
#include "DBCStores.h"
#include "GameObject.h"
#include "GameObjectAI.h"
#include "Log.h"
#include "Map.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "Spell.h"
#include "SpellAuraEffects.h"
#include "SpellInfo.h"
#include "TemporarySummon.h"

#include <cmath>
#include <functional>
#include <iterator>
#include <map>
#include <mutex>
#include <tuple>
#include <unordered_map>

namespace DC::Bounties
{
    namespace
    {
        // The channel's spell shell, 'Activating' (generate_spells.py): its cast bar.
        constexpr uint32 CHANNEL_SPELL = DC::Combat::Shells::BountyClick;

        // --- the claim: what a summon call is building belongs to `owner` (the HubObjectClaim pattern) ---

        struct Claim
        {
            std::uint64_t owner = 0;
            std::uint32_t bounty = 0; // a Unique's bounty, whose kill completes it; 0 for a guard
            int spot = -1;            // a Click objective's spot
        };
        thread_local Claim claiming;

        class Claimed
        {
        public:
            explicit Claimed(Claim claim)
            {
                claiming = claim;
            }
            ~Claimed()
            {
                claiming = Claim{};
            }
            Claimed(Claimed const&) = delete;
            Claimed& operator=(Claimed const&) = delete;
        };

        bool OwnedBy(Unit const* unit, std::uint64_t owner)
        {
            Player const* player = unit ? unit->GetCharmerOrOwnerPlayerOrPlayerItself() : nullptr;
            return player && OwnerKey(player) == owner;
        }

        // --- what stands where: (instance, owner, bounty, spot) -> the Unique or the objective ---

        using Key = std::tuple<std::uint32_t, std::uint64_t, std::uint32_t, unsigned>;
        std::mutex placedMutex;
        std::map<Key, ObjectGuid> placed;

        struct Look
        {
            std::uint64_t epoch = 0;
            std::uint32_t instance = 0, zone = 0, area = 0;
            bool operator==(Look const& o) const
            {
                return epoch == o.epoch && instance == o.instance && zone == o.zone && area == o.area;
            }
        };
        std::unordered_map<ObjectGuid, Look> looked; // placedMutex

        // A Click channel in flight: who, at what, for which bounty and spot. One a player (a cast replaces the last).
        struct Channel
        {
            ObjectGuid object;
            std::uint32_t bounty = 0;
            unsigned spot = 0;
        };
        std::unordered_map<ObjectGuid, Channel> channels; // placedMutex

        Position At(Spot const& spot)
        {
            return Position(spot.x, spot.y, spot.z, spot.o);
        }

        void Guards(Map* map, std::uint64_t owner, Spot const& spot)
        {
            if (!spot.guardEntry || !spot.guardCount)
                return;
            Claimed claim({owner, 0, -1});
            // ponytail: the pack stands on its anchor, as the survey found it; they spread when they move.
            for (std::uint32_t n = 0; n < spot.guardCount; ++n)
                if (!map->SummonCreature(spot.guardEntry, At(spot)))
                    LOG_ERROR("server", "[DC bounties] guard {} was not summoned at anchor {}", spot.guardEntry,
                              spot.anchor);
        }

        ObjectGuid PutUnique(Map* map, std::uint64_t owner, Open const& open, Spot const& spot)
        {
            Claimed claim({owner, open.bounty, -1});
            if (Creature* unique = map->SummonCreature(open.uniqueEntry, At(spot)))
                return unique->GetGUID();
            LOG_ERROR("server", "[DC bounties] bounty {}: its Unique {} was not summoned", open.bounty,
                      open.uniqueEntry);
            return ObjectGuid::Empty;
        }

        ObjectGuid PutObjective(Map* map, std::uint64_t owner, Open const& open, unsigned number, Spot const& spot)
        {
            if (!open.objectiveEntry)
                return ObjectGuid::Empty;
            GameObject* object = nullptr;
            {
                Claimed claim({owner, open.bounty, static_cast<int>(number)});
                object = map->SummonGameObject(open.objectiveEntry, spot.x, spot.y, spot.z, spot.o, 0, 0,
                                               std::sin(spot.o / 2), std::cos(spot.o / 2), 0);
            }
            if (!object)
            {
                LOG_ERROR("server", "[DC bounties] bounty {}: objective {} was not placed", open.bounty, number + 1);
                return ObjectGuid::Empty;
            }
            Guards(map, owner, spot);
            return object->GetGUID();
        }

        // Puts what `player`'s board has open in this zone and is not standing here yet.
        void Refresh(Player* player)
        {
            Map* map = player->GetMap();
            std::uint64_t const owner = OwnerKey(player);
            for (Open const& open : OpenIn(player, map->GetId(), player->GetZoneId()))
                for (auto const& [number, spot] : open.spots)
                {
                    Key const key{map->GetInstanceId(), owner, open.bounty, number};
                    ObjectGuid have;
                    {
                        std::lock_guard<std::mutex> lock(placedMutex);
                        if (auto found = placed.find(key); found != placed.end())
                            have = found->second;
                    }
                    if (open.uniqueEntry)
                    {
                        Creature* unique = have ? map->GetCreature(have) : nullptr;
                        if (unique && unique->IsAlive())
                            continue;
                    }
                    else if (have && map->GetGameObject(have))
                        continue;
                    ObjectGuid made = open.uniqueEntry ? PutUnique(map, owner, open, spot)
                                                       : PutObjective(map, owner, open, number, spot);
                    if (made)
                    {
                        std::lock_guard<std::mutex> lock(placedMutex);
                        placed[key] = made;
                    }
                }
        }

        // --- the objective ---

        bool ControlImmune(Unit const* unit)
        {
            // Stun stands for crowd control: the Invigorating Gemstone's immunity covers it (dc_gem_powers.cpp
            // SetControlImmunity), and so does any mechanic-immunity aura that covers it.
            return unit->m_spellImmune[IMMUNITY_MECHANIC].count(MECHANIC_STUN) ||
                   unit->HasAuraTypeWithMiscvalue(SPELL_AURA_MECHANIC_IMMUNITY, MECHANIC_STUN);
        }

        class ObjectiveAI final : public GameObjectAI
        {
        public:
            ObjectiveAI(GameObject* go, std::uint64_t owner, std::uint32_t bounty, unsigned spot)
                : GameObjectAI(go)
                , _owner(owner)
                , _bounty(bounty)
                , _spot(spot)
            {
            }
            bool CanBeSeen(Player const* seer) override
            {
                return !seer || OwnedBy(seer, _owner);
            }
            // The click: the channel starts. A stranger's click (no stranger sees it) does nothing.
            bool GossipHello(Player* player, bool /*reportUse*/) override
            {
                if (!player || !OwnedBy(player, _owner))
                    return true;
                {
                    std::lock_guard<std::mutex> lock(placedMutex);
                    channels[player->GetGUID()] = {me->GetGUID(), _bounty, _spot};
                }
                player->CastSpell(player, CHANNEL_SPELL, false);
                return true;
            }

        private:
            std::uint64_t _owner;
            std::uint32_t _bounty;
            unsigned _spot;
        };

        // The channel finished: the objective is done if the player still stands at it.
        void Finish(Player* player)
        {
            Channel channel;
            {
                std::lock_guard<std::mutex> lock(placedMutex);
                auto found = channels.find(player->GetGUID());
                if (found == channels.end())
                    return;
                channel = found->second;
                channels.erase(found);
            }
            GameObject* object = player->GetMap()->GetGameObject(channel.object);
            if (!object || !player->IsWithinDistInMap(object, INTERACTION_DISTANCE))
                return;
            if (!Click(player, channel.bounty, channel.spot))
                return;
            object->DespawnOrUnsummon();
            std::lock_guard<std::mutex> lock(placedMutex);
            placed.erase(Key{player->GetMap()->GetInstanceId(), OwnerKey(player), channel.bounty, channel.spot});
        }

        // --- scripts ---

        class ObjectiveCreatures final : public AllCreatureScript
        {
        public:
            ObjectiveCreatures()
                : AllCreatureScript("dc_bounty_creatures")
            {
            }
            // Only inside a claim, and only for a creature with no spawn id: the one our own summon call is building.
            CreatureAI* GetCreatureAI(Creature* creature) const override
            {
                if (!claiming.owner || !creature || creature->GetSpawnId())
                    return nullptr;
                std::uint64_t const owner = claiming.owner;
                std::uint32_t const bounty = claiming.bounty;
                std::function<void(Unit*)> died;
                if (bounty) // the Unique: its kill completes the bounty, on the owner's board only
                    died = [owner, bounty](Unit* killer)
                    {
                        Player* player = killer ? killer->GetCharmerOrOwnerPlayerOrPlayerItself() : nullptr;
                        if (player && OwnerKey(player) == owner)
                            Complete(player, bounty);
                    };
                return Rifts::NewOwnedMonsterAI(
                    creature, [owner](Unit const* unit) { return OwnedBy(unit, owner); }, died);
            }
        };

        class ObjectiveObjects final : public AllGameObjectScript
        {
        public:
            ObjectiveObjects()
                : AllGameObjectScript("dc_bounty_objects")
            {
            }
            GameObjectAI* GetGameObjectAI(GameObject* go) const override
            {
                if (!claiming.owner || claiming.spot < 0 || !go || go->GetSpawnId())
                    return nullptr;
                return new ObjectiveAI(go, claiming.owner, claiming.bounty, static_cast<unsigned>(claiming.spot));
            }
        };

        // The channel's cast time is the tunable (the town portal's way: the server's cast time is the one the cast bar
        // shows, from a SpellCastTimes row of that length); movement or an interrupt stops it, damage is ChannelDamage.
        class ChannelSpellData final : public GlobalScript
        {
        public:
            ChannelSpellData()
                : GlobalScript("dc_bounty_channel_data", {GLOBALHOOK_ON_LOAD_SPELL_CUSTOM_ATTR})
            {
            }
            void OnLoadSpellCustomAttr(SpellInfo* info) override
            {
                if (info->Id != CHANNEL_SPELL)
                    return;
                info->InterruptFlags = SPELL_INTERRUPT_FLAG_MOVEMENT | SPELL_INTERRUPT_FLAG_INTERRUPT;
                auto const ms = static_cast<int32>(DC::Tunables::Get("rifts", "bounty_click_channel_ms"));
                for (uint32 id = 0; id < sSpellCastTimesStore.GetNumRows(); ++id)
                    if (auto* time = sSpellCastTimesStore.LookupEntry(id))
                        if (time->CastTime == ms)
                        {
                            info->CastTimeEntry = time;
                            return;
                        }
                LOG_ERROR("server",
                          "[DC bounties] no cast time of {} ms (rifts bounty_click_channel_ms); the channel "
                          "keeps its spell's",
                          ms);
            }
        };

        class ChannelCast final : public AllSpellScript
        {
        public:
            ChannelCast()
                : AllSpellScript("dc_bounty_channel_cast", {ALLSPELLHOOK_ON_CAST})
            {
            }
            void OnSpellCast(Spell*, Unit* caster, SpellInfo const* info, bool) override
            {
                if (info->Id == CHANNEL_SPELL && caster)
                    if (Player* player = caster->ToPlayer())
                        Finish(player);
            }
        };

        class ChannelDamage final : public UnitScript
        {
        public:
            ChannelDamage()
                : UnitScript("dc_bounty_channel_damage", true, {UNITHOOK_ON_DAMAGE})
            {
            }
            void OnDamage(Unit*, Unit* victim, uint32& damage) override
            {
                if (!victim || !victim->IsPlayer() || !damage)
                    return;
                Spell* cast = victim->GetCurrentSpell(CURRENT_GENERIC_SPELL);
                if (cast && cast->GetSpellInfo()->Id == CHANNEL_SPELL && cast->getState() == SPELL_STATE_PREPARING &&
                    !ControlImmune(victim))
                    victim->InterruptNonMeleeSpells(false, CHANNEL_SPELL);
            }
        };

        class ObjectivePlayer final : public PlayerScript
        {
        public:
            ObjectivePlayer()
                : PlayerScript("dc_bounty_objectives_player", {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT})
            {
            }
            void OnPlayerUpdate(Player* player, uint32 /*diff*/) override
            {
                if (!IsBountyMap(player->GetMapId()) || player->IsBeingTeleported() || !player->IsInWorld())
                    return;
                Look const now{Epoch(), player->GetInstanceId(), player->GetZoneId(), player->GetAreaId()};
                {
                    std::lock_guard<std::mutex> lock(placedMutex);
                    Look& last = looked[player->GetGUID()];
                    if (last == now)
                        return;
                    last = now;
                }
                Refresh(player);
            }
            void OnPlayerLogout(Player* player) override
            {
                std::lock_guard<std::mutex> lock(placedMutex);
                looked.erase(player->GetGUID());
                channels.erase(player->GetGUID());
            }
        };

        // A copy that closes takes its objects with it; so does its part of the list.
        class ObjectiveMaps final : public AllMapScript
        {
        public:
            ObjectiveMaps()
                : AllMapScript("dc_bounty_objectives_maps", {ALLMAPHOOK_ON_DESTROY_INSTANCE})
            {
            }
            void OnDestroyInstance(MapInstanced*, Map* map) override
            {
                std::lock_guard<std::mutex> lock(placedMutex);
                for (auto it = placed.begin(); it != placed.end();)
                    it = std::get<0>(it->first) == map->GetInstanceId() ? placed.erase(it) : std::next(it);
            }
        };
    } // namespace

    void RegisterObjectiveScripts()
    {
        new ObjectiveCreatures();
        new ObjectiveObjects();
        new ChannelSpellData();
        new ChannelCast();
        new ChannelDamage();
        new ObjectivePlayer();
        new ObjectiveMaps();
    }
} // namespace DC::Bounties
