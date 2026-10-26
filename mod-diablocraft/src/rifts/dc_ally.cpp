/*
 * World of DiabloCraft - the allies a legendary item summons (N-SUMMON).
 *
 * Summoned by `Player::SummonCreature(entry, position, TEMPSUMMON_TIMED_DESPAWN, lifetimeMs)`; nothing else is
 * needed from the power. The AI takes the owner, faction and level from the summoner, follows, fights what the
 * owner fights (the pick Call of the Ancients uses), and leaves with its owner. It never melees: a swing is the
 * power's registered callback (Ally::OnSwing). The pawn only stands where it was put (the Charging Wolf).
 */

#include "dc_ally.h"
#include "../classes/barbarian/dc_barbarian_call_of_the_ancients.h"
#include "Creature.h"
#include "CreatureAI.h"
#include "MotionMaster.h"
#include "ObjectAccessor.h"
#include "PetDefines.h"
#include "Player.h"
#include "ScriptedCreature.h"
#include "ScriptMgr.h"
#include "TemporarySummon.h"

#include "Random.h"

#include <numbers>
#include <unordered_map>

namespace DC::Rifts::Ally
{
    namespace
    {
        struct Strike
        {
            std::uint32_t interval = 0;
            Swing swing;
        };

        std::unordered_map<std::uint32_t, Strike>& Table()
        {
            static std::unordered_map<std::uint32_t, Strike> table;
            return table;
        }

        Player* Online(ObjectGuid owner, Creature const* me)
        {
            Player* player = ObjectAccessor::FindConnectedPlayer(owner);
            return player && player->IsAlive() && player->IsInMap(me) && player->InSamePhase(me) ? player : nullptr;
        }

        // The owner, the faction, the level and the guid links of any ally; false when the summoner is not a player.
        bool Bind(Creature* me, WorldObject* summoner, ObjectGuid& owner)
        {
            Player* player = summoner ? summoner->ToPlayer() : nullptr;
            if (!player)
            {
                if (TempSummon* summon = me->ToTempSummon())
                    summon->UnSummon();
                return false;
            }
            owner = player->GetGUID();
            me->SetOwnerGUID(owner);
            me->SetCreatorGUID(owner);
            me->SetFaction(player->GetFaction());
            me->SetLevel(player->GetLevel());
            return true;
        }

        void Leave(Creature* me)
        {
            if (TempSummon* summon = me->ToTempSummon())
                summon->UnSummon();
        }

        class FightingAI final : public ScriptedAI
        {
            ObjectGuid owner;
            std::uint32_t clock = 0;

        public:
            explicit FightingAI(Creature* creature)
                : ScriptedAI(creature)
            {
            }

            void IsSummonedBy(WorldObject* summoner) override
            {
                if (Bind(me, summoner, owner))
                    // A spot of its own beside the owner, so a herd does not stand in one place.
                    me->GetMotionMaster()->MoveFollow(summoner->ToUnit(), PET_FOLLOW_DIST,
                                                      frand(0.0f, 2.0f * float(std::numbers::pi)));
            }

            void UpdateAI(uint32 diff) override
            {
                Player* player = Online(owner, me);
                if (!player)
                {
                    Leave(me);
                    return;
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
                if (!target)
                {
                    if (me->GetVictim())
                        me->AttackStop();
                    if (me->GetMotionMaster()->GetCurrentMovementGeneratorType() != FOLLOW_MOTION_TYPE)
                        me->GetMotionMaster()->MoveFollow(player, PET_FOLLOW_DIST, frand(0.0f, 2.0f * float(std::numbers::pi)));
                    return;
                }
                if (me->GetVictim() != target)
                    AttackStart(target);
                clock += diff;
                auto const found = Table().find(me->GetEntry());
                if (found == Table().end() || !found->second.swing || found->second.interval == 0 ||
                    clock < found->second.interval || !me->IsWithinMeleeRange(target))
                    return;
                clock = 0;
                found->second.swing(*me, *player, *target);
            }
        };

        // Stands where the power puts it (it moves it, as the Charging Wolf's line), never follows or fights, and
        // leaves with its owner.
        class PawnAI final : public ScriptedAI
        {
            ObjectGuid owner;

        public:
            explicit PawnAI(Creature* creature)
                : ScriptedAI(creature)
            {
            }

            void IsSummonedBy(WorldObject* summoner) override
            {
                if (Bind(me, summoner, owner))
                    me->SetReactState(REACT_PASSIVE);
            }

            void UpdateAI(uint32) override
            {
                if (!Online(owner, me))
                    Leave(me);
            }
        };

        template <class AI>
        class Script final : public CreatureScript
        {
        public:
            explicit Script(std::string_view name)
                : CreatureScript(std::string(name).c_str())
            {
            }

            CreatureAI* GetAI(Creature* creature) const override
            {
                return new AI(creature);
            }
        };
    } // namespace

    void OnSwing(std::uint32_t entry, std::uint32_t intervalMs, Swing swing)
    {
        Table()[entry] = {intervalMs, std::move(swing)};
    }

    void RegisterScripts()
    {
        new Script<FightingAI>(Fighting);
        new Script<PawnAI>(Pawn);
    }
} // namespace DC::Rifts::Ally
