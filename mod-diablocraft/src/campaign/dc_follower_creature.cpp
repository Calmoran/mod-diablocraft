/*
 * World of DiabloCraft - the follower creature: its AI beside the player, and the talk that hires it or opens its window.
 *
 * One creature entry per follower serves both parts. Standing in the hub it is a service NPC: talking to it offers Hire
 * (the only way to hire) beside the Follower window;
 * summoned for a player (dc_followers.cpp) it walks beside them, fights what they fight, jumps to them when left
 * behind, and goes down when it falls. Contract: docs/contracts/followers.md.
 */

#include "dc_follower_internal.h"
#include "../common/dc_world.h"
#include "../classes/barbarian/dc_barbarian_call_of_the_ancients.h"
#include "../classes/follower/dc_follower_skills.h"
#include "../items/dc_items.h"

#include "Chat.h"
#include "Creature.h"
#include "MotionMaster.h"
#include "ObjectAccessor.h"
#include "PetDefines.h"
#include "Player.h"
#include "ScriptedCreature.h"
#include "ScriptedGossip.h"
#include "ScriptMgr.h"
#include "TemporarySummon.h"

#include <string>

namespace DC::Campaign::Followers
{
    namespace
    {
        constexpr std::uint32_t HireAction = 1, WindowAction = 2;

        // The level the next follower summoned on this thread takes (its owner's); 0 outside Appear.
        thread_local std::uint8_t nextSummonLevel = 0;

        Player* Online(ObjectGuid owner, Creature const* me)
        {
            Player* player = ObjectAccessor::FindConnectedPlayer(owner);
            return player && player->IsAlive() && player->IsInMap(me) && player->InSamePhase(me) ? player : nullptr;
        }

        void Leave(Creature* me)
        {
            if (TempSummon* summon = me->ToTempSummon())
                summon->UnSummon();
        }

        class FollowerAI final : public ScriptedAI
        {
            ObjectGuid owner;
            std::uint32_t farMs = 0;

        public:
            explicit FollowerAI(Creature* creature)
                : ScriptedAI(creature)
            {
            }

            void IsSummonedBy(WorldObject* summoner) override
            {
                Player* player = summoner ? summoner->ToPlayer() : nullptr;
                if (!player)
                {
                    Leave(me);
                    return;
                }
                owner = player->GetGUID();
                me->SetOwnerGUID(owner);
                me->SetCreatorGUID(owner);
                me->SetFaction(player->GetFaction());
                // A rift switches regeneration off for everything that enters it; a companion heals between fights.
                me->SetRegeneratingHealth(true);
                me->GetMotionMaster()->MoveFollow(player, PET_FOLLOW_DIST, FollowAngle);
                // Its life, armor, resistances and swing are its own gear's.
                if (Row const* row = ByEntry(me->GetEntry()))
                    Items::FollowerGear::OnCompanionSummoned(player, me, unsigned(row->id));
            }

            // A relic that keeps the follower from dying takes the blow.
            void DamageTaken(Unit*, uint32& damage, DamageEffectType, SpellSchoolMask) override
            {
                if (!owner)
                    return;
                Player* player = ObjectAccessor::FindConnectedPlayer(owner);
                if (player && Items::FollowerGear::CannotDie(player))
                    damage = 0;
            }

            // The hub copy is hidden from the player who has this follower out beside them, and only from them; a
            // companion (it has an owner) is seen by everyone.
            bool CanBeSeen(Player const* seer) override
            {
                return owner || !OutFor(seer, me->GetEntry());
            }

            void JustDied(Unit*) override
            {
                if (owner)
                    OnCompanionFell(owner);
            }

            void UpdateAI(uint32 diff) override
            {
                // In the hub, as a service NPC, there is nothing to do.
                if (!owner)
                    return;
                Player* player = Online(owner, me);
                if (!player || !IsCompanionOf(owner, me->GetGUID()))
                {
                    Leave(me);
                    return;
                }
                if (CatchUp(farMs, diff, me->GetDistance2d(player), CurrentRules()))
                {
                    float x, y, z;
                    player->GetClosePoint(x, y, z, me->GetCombatReach(), PET_FOLLOW_DIST, FollowAngle);
                    me->NearTeleportTo(x, y, z, player->GetOrientation());
                }
                Unit* victim = player->GetVictim();
                Unit* selected = player->GetSelectedUnit();
                auto usable = [&](Unit* unit) { return unit && unit->IsAlive() && player->IsValidAttackTarget(unit); };
                Unit* target = nullptr;
                switch (Classes::Ancients::PickTarget(usable(victim), player->IsInCombat(), usable(selected)))
                {
                    case Classes::Ancients::Pick::Victim:
                        target = victim;
                        break;
                    case Classes::Ancients::Pick::Selected:
                        target = selected;
                        break;
                    case Classes::Ancients::Pick::None:
                        break;
                }
                // The skills it casts and the buffs it gives, fighting or not.
                Classes::Follower::Tick(player, me, target, diff);
                if (!target)
                {
                    if (me->GetVictim())
                        me->AttackStop();
                    if (me->GetMotionMaster()->GetCurrentMovementGeneratorType() != FOLLOW_MOTION_TYPE)
                        me->GetMotionMaster()->MoveFollow(player, PET_FOLLOW_DIST, FollowAngle);
                    return;
                }
                if (me->GetVictim() != target)
                    AttackStart(target);
                DoMeleeAttackIfReady();
            }
        };

        void Say(Player* player, std::string const& text)
        {
            ChatHandler(player->GetSession()).SendSysMessage(text.c_str());
        }

        class FollowerScript final : public CreatureScript
        {
        public:
            FollowerScript()
                : CreatureScript(std::string(Script).c_str())
            {
            }

            CreatureAI* GetAI(Creature* creature) const override
            {
                return new FollowerAI(creature);
            }

            // A companion answers its own player only; the hub's follower answers anyone. In the hub a follower that is
            // not the hired one offers Hire beside its window; with no Hire to offer, talking opens the Follower window
            // (the DCFOLLOWER records, pushed with no request). Dismissing is the window's button.
            bool OnGossipHello(Player* player, Creature* creature) override
            {
                Row const* row = ByEntry(creature->GetEntry());
                if (!row || (creature->GetOwnerGUID() && creature->GetOwnerGUID() != player->GetGUID()))
                    return false;
                if (!OffersHire(World::IsInHub(player), Hired(player), row->id))
                {
                    CloseGossipMenuFor(player);
                    Items::FollowerGear::OpenWindow(player, unsigned(row->id));
                    return true;
                }
                ClearGossipMenuFor(player);
                AddGossipItemFor(player, GOSSIP_ICON_CHAT, "Hire " + row->name + ".", GOSSIP_SENDER_MAIN, HireAction);
                AddGossipItemFor(player, GOSSIP_ICON_CHAT, "Show " + row->name + "'s gear and skills.", GOSSIP_SENDER_MAIN,
                                 WindowAction);
                SendGossipMenuFor(player, 1, creature->GetGUID());
                return true;
            }

            bool OnGossipSelect(Player* player, Creature* creature, uint32 sender, uint32 action) override
            {
                ClearGossipMenuFor(player);
                CloseGossipMenuFor(player);
                Row const* row = ByEntry(creature->GetEntry());
                if (!row || sender != GOSSIP_SENDER_MAIN ||
                    (creature->GetOwnerGUID() && creature->GetOwnerGUID() != player->GetGUID()))
                    return true;
                if (action == HireAction && OffersHire(World::IsInHub(player), Hired(player), row->id))
                {
                    if (Hire(player, row->id))
                        Say(player, row->name + " will walk beside you.");
                    else
                        Say(player, "Followers are not available right now.");
                }
                else if (action == WindowAction)
                    Items::FollowerGear::OpenWindow(player, unsigned(row->id));
                return true;
            }
        };

        // A follower summoned for a player takes that player's level, so its life and mana are the stock numbers of
        // that level and not of the template's.
        class Levels final : public AllCreatureScript
        {
        public:
            Levels()
                : AllCreatureScript("dc_follower_level")
            {
            }

            void OnBeforeCreatureSelectLevel(CreatureTemplate const* info, Creature*, uint8& level) override
            {
                if (nextSummonLevel && info && ByEntry(info->Entry))
                    level = nextSummonLevel;
            }
        };
    } // namespace

    void SetNextSummonLevel(std::uint8_t level)
    {
        nextSummonLevel = level;
    }

    void RegisterCreatureScripts()
    {
        new FollowerScript();
        new Levels();
    }
} // namespace DC::Campaign::Followers
