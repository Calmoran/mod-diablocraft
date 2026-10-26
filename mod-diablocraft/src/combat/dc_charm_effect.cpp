/*
 * A monster charmed to fight for a player (dc_charm_effect.h). The core gives a player one charm (Unit::SetCharmedBy
 * ends the player's earlier one), so the charm is not the player's: each charm gets an invisible holder summoned for
 * it, on the player's side, and the core's own charm aura goes from the holder onto the monster. A creature holds any
 * number of charms in the core, a holder holds one, and so the player's charms are as many as the roll gives. The aura
 * owns the length and the swap of side; the holder is kept only to give the aura a caster and goes with it.
 */

#include "dc_charm_effect.h"
#include "dc_charm_effect_math.h"
#include "dc_combat.h"
#include "../rifts/dc_rifts.h"
#include "CharmInfo.h"
#include "Creature.h"
#include "MotionMaster.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "SpellAuras.h"
#include "TemporarySummon.h"

#include <algorithm>
#include <atomic>
#include <mutex>
#include <unordered_map>
#include <vector>

namespace DC::Combat::CharmEffect
{
    namespace
    {
        // Stock "Gnomish Mind Control Cap" (26740): one SPELL_AURA_AOE_CHARM effect and the Charm mechanic, so the
        // Juggernaut and the Guardian refuse it through the core's own immunity check. The aura converts the monster
        // (no pet bar, defensive), and it fights only what it is sent at and what attacks it or its holder.
        constexpr std::uint32_t CharmHold = 26740;
        // Stock "World Invisible Trigger" (12999), the holder: summoned for one charm, its faction the player's.
        constexpr std::uint32_t Holder = 12999;
        // How long past the charm the holder stays if nothing ends it first, and how often the module looks at the
        // charmed monster. Guards, not tuning numbers: the aura ends the charm, the look keeps it fighting.
        constexpr std::uint32_t GraceMs = 2000;
        constexpr std::uint32_t LookMs = 1000;

        // The monsters each master has charmed through a holder, by the master's guid. Read through CharmedBy, which keeps
        // only what is still held, so an entry the holder's death left behind is dropped at the next read. `charms`
        // counts the entries so a read with none charmed takes no lock.
        std::mutex registryMutex;
        std::unordered_map<std::uint64_t, std::vector<ObjectGuid>> registry;
        std::atomic<std::size_t> charms{0};

        void Remember(Player* master, ObjectGuid charmed)
        {
            std::lock_guard<std::mutex> lock(registryMutex);
            registry[master->GetGUID().GetRawValue()].push_back(charmed);
            ++charms;
        }

        void Forget(ObjectGuid master, ObjectGuid charmed)
        {
            std::lock_guard<std::mutex> lock(registryMutex);
            auto it = registry.find(master.GetRawValue());
            if (it == registry.end())
                return;
            auto& guids = it->second;
            auto gone = std::remove(guids.begin(), guids.end(), charmed);
            charms -= std::size_t(guids.end() - gone);
            guids.erase(gone, guids.end());
            if (guids.empty())
                registry.erase(it);
        }

        Target Describe(Player* master, Creature* creature)
        {
            Target target;
            target.creature = true;
            target.alive = creature->IsAlive();
            target.hostile = master->IsValidAttackTarget(creature);
            target.alreadyCharmed = creature->IsCharmed();
            target.controlledByPlayer = creature->IsControlledByPlayer();
            target.boss = creature->isWorldBoss() || creature->IsDungeonBoss() ||
                          DC::Rifts::IsGuardianEntry(creature->GetEntry());
            return target;
        }

        // The charmed monster is sent at the nearest enemy of its master within what it can see: the core's visibility
        // range, with no radius of its own. False when there is none.
        bool Send(Player* master, Creature* creature, std::uint32_t spellId)
        {
            std::vector<Unit*> foes =
                Combat::Enemies(master, spellId, creature->GetPosition(), creature->GetVisibilityRange());
            foes.erase(std::remove(foes.begin(), foes.end(), creature), foes.end());
            std::vector<double> distances;
            for (Unit* foe : foes)
                distances.push_back(creature->GetExactDist(foe));
            auto const nearest = NearestFoe(distances);
            if (!nearest || !creature->GetCharmInfo())
                return false;
            creature->GetCharmInfo()->SetIsCommandAttack(true);
            creature->Attack(foes[*nearest], true);
            creature->GetMotionMaster()->MoveChase(foes[*nearest]);
            return true;
        }

        // One look at a charmed monster, on its holder's clock: the charm is over with its master (dead or gone) or
        // with the aura, and the holder goes; a monster with no fight is sent at the next enemy, or waits at its
        // master.
        void Look(Creature* holder, ObjectGuid master, ObjectGuid charmed, std::uint32_t spellId)
        {
            Player* player = ObjectAccessor::GetPlayer(*holder, master);
            Creature* creature = ObjectAccessor::GetCreature(*holder, charmed);
            if (!player || !player->IsAlive() || !creature || !creature->IsAlive() ||
                creature->GetCharmerGUID() != holder->GetGUID())
            {
                Forget(master, charmed);
                holder->DespawnOrUnsummon();
                return;
            }
            Unit* victim = creature->GetVictim();
            if (Retarget(victim != nullptr, victim && victim->IsAlive()) && !Send(player, creature, spellId))
                holder->NearTeleportTo(player->GetPositionX(), player->GetPositionY(), player->GetPositionZ(),
                                       player->GetOrientation());
            holder->m_Events.AddEventAtOffset([holder, master, charmed, spellId]
                                              { Look(holder, master, charmed, spellId); },
                                              std::chrono::milliseconds(LookMs));
        }
    } // namespace

    bool Apply(Player* master, Unit* target, std::uint32_t spellId, double seconds)
    {
        Creature* creature = target ? target->ToCreature() : nullptr;
        if (!master || !master->IsInWorld() || !creature || !creature->IsInWorld() ||
            !CanCharm(Describe(master, creature), seconds))
            return false;
        auto const ms = std::uint32_t(seconds * 1000);
        TempSummon* holder =
            master->SummonCreature(Holder, master->GetPosition(), TEMPSUMMON_TIMED_DESPAWN, ms + GraceMs);
        if (!holder)
            return false;
        holder->SetFaction(master->GetFaction());
        Aura* charm = holder->AddAura(CharmHold, creature);
        // The aura can take hold and the core still not charm: then the aura and the holder go.
        if (!charm || creature->GetCharmerGUID() != holder->GetGUID())
        {
            if (charm)
                creature->RemoveAura(charm);
            holder->DespawnOrUnsummon();
            return false;
        }
        charm->SetMaxDuration(int32(ms));
        charm->SetDuration(int32(ms));
        Remember(master, creature->GetGUID());
        Send(master, creature, spellId);
        holder->m_Events.AddEventAtOffset([holder, master = master->GetGUID(), charmed = creature->GetGUID(), spellId]
                                          { Look(holder, master, charmed, spellId); },
                                          std::chrono::milliseconds(LookMs));
        return true;
    }

    Player* MasterOf(Unit const* charmed)
    {
        Unit* charmer = charmed ? charmed->GetCharmer() : nullptr;
        if (!charmer)
            return nullptr;
        Creature* holder = charmer->ToCreature();
        TempSummon* summon = holder ? holder->ToTempSummon() : nullptr;
        Unit* summoner = summon ? summon->GetSummonerUnit() : nullptr;
        Charmer who;
        who.player = charmer->IsPlayer();
        who.holder = holder && holder->GetEntry() == Holder;
        who.summonerPlayer = summoner && summoner->IsPlayer();
        switch (MasterKindOf(who))
        {
            case Master::Charmer:
                return charmer->ToPlayer();
            case Master::HoldersSummoner:
                return summoner->ToPlayer();
            default:
                return nullptr;
        }
    }

    std::vector<Creature*> CharmedBy(Player* master)
    {
        std::vector<Creature*> held;
        if (!master || charms.load() == 0)
            return held;
        std::lock_guard<std::mutex> lock(registryMutex);
        auto it = registry.find(master->GetGUID().GetRawValue());
        if (it == registry.end())
            return held;
        auto& guids = it->second;
        auto gone = std::remove_if(guids.begin(), guids.end(),
                                   [&](ObjectGuid guid)
                                   {
                                       Creature* creature = ObjectAccessor::GetCreature(*master, guid);
                                       if (creature && creature->IsAlive() && creature->IsInWorld() &&
                                           MasterOf(creature) == master)
                                       {
                                           held.push_back(creature);
                                           return false;
                                       }
                                       return true;
                                   });
        charms -= std::size_t(guids.end() - gone);
        guids.erase(gone, guids.end());
        if (guids.empty())
            registry.erase(it);
        return held;
    }
} // namespace DC::Combat::CharmEffect
