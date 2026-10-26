/*
 * The Necromancer's kill hook (dc_necromancer_corpses.h). A monster that dies leaves a corpse for every Necromancer in
 * the party of whoever killed it, the killer's own minions counted as the killer; a death by anything with no player
 * behind it leaves none. The corpse is the monster's own dead body (its guid goes in the record). The piles are the
 * owners' own (combat/dc_corpses.h), so each Necromancer spends only its own.
 */

#include "dc_necromancer_corpses.h"
#include "../dc_classes.h"
#include "../dc_resources.h"
#include "../../combat/dc_charm_effect.h"
#include "../../combat/dc_corpses.h"
#include "Creature.h"
#include "Group.h"
#include "Player.h"
#include "ScriptMgr.h"

#include <vector>

namespace DC::Combat::Necromancer::KillCorpses
{
    namespace
    {
        bool IsNecromancer(Player* player)
        {
            static constexpr auto const& essence = *Resources::Find("Necromancer", "essence");
            return Classes::ClassIdOf(player) == essence.classId;
        }

        // The player a kill is credited to: the killer, or the player whose minion or charmed monster it was.
        Player* PlayerBehind(Unit* killer)
        {
            if (!killer)
                return nullptr;
            if (Player* player = killer->GetCharmerOrOwnerPlayerOrPlayerItself())
                return player;
            return CharmEffect::MasterOf(killer);
        }

        // The killer and its party that can hold the corpse: on the dead monster's map, alive and in the world.
        std::vector<Player*> Party(Player* killer, Unit* victim)
        {
            std::vector<Player*> party{killer};
            if (Group* group = killer->GetGroup())
                for (GroupReference* ref = group->GetFirstMember(); ref; ref = ref->next())
                    if (Player* member = ref->GetSource(); member && member != killer)
                        party.push_back(member);
            std::vector<Player*> present;
            for (Player* member : party)
                if (member->IsAlive() && member->IsInWorld() && member->GetMap() == victim->GetMap())
                    present.push_back(member);
            return present;
        }

        class Kills final : public UnitScript
        {
        public:
            Kills()
                : UnitScript("dc_necromancer_corpses", true, {UNITHOOK_ON_UNIT_DEATH})
            {
            }

            void OnUnitDeath(Unit* victim, Unit* killer) override
            {
                Creature* creature = victim ? victim->ToCreature() : nullptr;
                Player* credited = PlayerBehind(killer);
                if (!creature || !credited)
                    return;
                // The dead body a skill's corpse is made with dies by itself: it is not a kill.
                if (creature->GetGUID().GetRawValue() == Corpses::BodyBeingMade())
                    return;
                Corpses::Victim death;
                death.creature = true;
                death.controlledByPlayer = creature->IsControlledByPlayer();
                if (!Corpses::Leaves(death))
                    return;
                for (Player* member : Party(credited, creature))
                    if (IsNecromancer(member))
                        Corpses::Leave(member, creature->GetPosition(), creature->GetEntry(),
                                       creature->GetGUID().GetRawValue());
            }
        };
    } // namespace

    void RegisterScripts()
    {
        new Kills();
    }
} // namespace DC::Combat::Necromancer::KillCorpses
