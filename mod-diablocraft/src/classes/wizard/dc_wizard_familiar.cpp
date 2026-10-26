#include "dc_wizard_familiar.h"
#include "ObjectAccessor.h"
#include "PetDefines.h"
#include "ScriptedCreature.h"
#include "TemporarySummon.h"
#include <cmath>

namespace DC::Combat::Wizard::Familiar
{
    using namespace Shared;

    namespace
    {
        // wizard_summons.csv: the creature template generate_wizard_summon_templates() writes for the Familiar.
        constexpr uint32 FAMILIAR_ENTRY = 900111;
    } // namespace

    Creature* FamiliarOf(Player* player)
    {
        Creature* creature = ObjectAccessor::GetCreature(*player, StateOf(player).familiar);
        return creature && creature->IsAlive() ? creature : nullptr;
    }

    void SummonFamiliar(Player* player)
    {
        std::lock_guard<std::recursive_mutex> guard(mutex);
        State& state = StateOf(player);
        Despawn(player, state.familiar);
        state.familiar.Clear();
        if (TempSummon* summon =
                player->SummonCreature(FAMILIAR_ENTRY, player->GetPosition(), TEMPSUMMON_MANUAL_DESPAWN))
        {
            summon->SetOwnerGUID(player->GetGUID());
            summon->SetCreatorGUID(player->GetGUID());
            summon->SetFaction(player->GetFaction());
            summon->SetLevel(player->GetLevel());
            // "This companion cannot be targeted or damaged by enemies."
            summon->SetUnitFlag(UNIT_FLAG_NON_ATTACKABLE);
            summon->SetReactState(REACT_PASSIVE);
            summon->GetMotionMaster()->MoveFollow(player, PET_FOLLOW_DIST, PET_FOLLOW_ANGLE);
            state.familiar = summon->GetGUID();
        }
    }

    void Begin(Player* player, State& state, std::uint32_t spellId, Unit* explicitTarget)
    {
        // The Familiar attacks when you cast, at most once every 54 frames
        // of attack speed (wizard.js:920; attack_frames_count).
        uint32 const familiar = BuffOf(player, "Familiar");
        Creature* pet = familiar ? FamiliarOf(player) : nullptr;
        if (pet && !IsSkill(spellId, "Familiar") && Now() >= state.familiarReady)
        {
            Unit* target = explicitTarget && player->IsValidAttackTarget(explicitTarget) ? explicitTarget : nullptr;
            if (!target)
                if (Unit* selected = player->GetSelectedUnit(); selected && player->IsValidAttackTarget(selected))
                    target = selected;
            double const aps = Combat::AttacksPerSecond(player, familiar);
            if (target && aps > 0)
            {
                state.familiarReady =
                    Now() + uint64(std::floor(Num(familiar, "attack_frames_count") / aps) / 60 * 1000);
                ObjectGuid const guid = target->GetGUID();
                After(player, 0,
                      [guid, familiar](Player* p)
                      {
                          Unit* u = Find(p, guid);
                          if (!u)
                              return;
                          if (IsRune(familiar, "Cannoneer"))
                              Combat::StrikeArea(p, familiar, u->GetPosition(), Num(familiar, "radius_yards"));
                          else
                              Combat::Strike(p, u, familiar);
                      });
            }
        }
    }

    // Called with the module lock held: the Familiar takes the attack that is about to land on `victim`, and the damage goes to zero.
    bool Guardian(Player* victim, State& state, uint64 now, std::uint32_t& damage)
    {
        // Ancient Guardian: below the Life threshold the Familiar takes
        // one attack every interval_seconds.
        if (uint32 id = BuffOf(victim, "Familiar"); id && IsRune(id, "Ancient Guardian") && FamiliarOf(victim) &&
                                                    victim->GetHealthPct() < Num(id, "life_threshold_pct") &&
                                                    now >= state.guardianReady)
        {
            state.guardianReady = now + uint64(Num(id, "interval_seconds") * 1000);
            damage = 0;
            return true;
        }
        return false;
    }

    namespace
    {
        // Its attacks are the Wizard's casts (Begin); this only follows and
        // leaves with its owner.
        class FamiliarAI final : public ScriptedAI
        {
        public:
            explicit FamiliarAI(Creature* creature)
                : ScriptedAI(creature)
            {
            }

            void UpdateAI(uint32) override
            {
                Player* owner = OwnerOf(me);
                if (!owner || !owner->IsAlive() || !owner->IsInMap(me))
                    if (TempSummon* summon = me->ToTempSummon())
                        summon->UnSummon();
            }
        };
    } // namespace

    void RegisterScripts()
    {
        new Summon<FamiliarAI>("dc_wizard_familiar");
    }
} // namespace DC::Combat::Wizard::Familiar
