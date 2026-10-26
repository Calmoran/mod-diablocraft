// World of DiabloCraft - elite affixes: the unit script that runs every affix, and the elite scripts' registration.

#include "dc_affix_internal.h"
#include "../dc_family_ai.h"
#include "ABScriptMgr.h"
#include "../../rifts/dc_rift_pace.h"

#include "../../rifts/dc_rifts.h"
#include "../../common/dc_tunables.h"
#include "../dc_monster_ai.h"
#include "../../rifts/dc_gr_progress.h"
#include "../../rifts/dc_rifts_internal.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_pylons.h"
#include "../../combat/dc_spell_shells.h"
#include "../../stats/dc_movement_math.h"
#include "../../difficulty/dc_difficulty.h"
#include "../../common/dc_world.h"

#include "Chat.h"
#include "CombatAI.h"
#include "Creature.h"
#include "ScriptedCreature.h"
#include "SpellAuraEffects.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "ThreatManager.h"
#include "DatabaseEnv.h"
#include "GridNotifiers.h"
#include "Group.h"
#include "Log.h"
#include "Map.h"
#include "MapMgr.h"
#include "ObjectAccessor.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "PathGenerator.h"
#include "ScriptMgr.h"
#include "World.h"
#include "WorldSession.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <chrono>
#include <functional>
#include <list>
#include <iterator>
#include <map>
#include <memory>
#include <unordered_set>
#include <limits>
#include <mutex>
#include <random>
#include <set>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>


namespace DC::Rifts
{
// A single-target affix aims through the one picker the family abilities use, a random
// valid player within reach, never "whoever the AI is chasing" - so a pack's affixes do not all land on one
// player. The reach is the affix's own where it has one, else the targeting AI's candidate radius.
Player* AffixTick::Pick(float reach) const
{
    return Family::PickPlayer(elite, Family::Rule::Random, 0.0f, reach, false);
}
// A charmed elite is on the players' side: its single-target affixes aim at a former ally instead of a player.
Unit* AffixTick::Aim(float reach) const
{
    return elite->IsCharmed() ? PickFoe(elite, reach) : Pick(reach);
}
// Each affix keeps its own cadence. D3 publishes none except Mortar's
// volley, so most of these are tunables; an affix with no
// cast_interval row of its own falls back to _global/cast_interval.
bool AffixTick::Due(Affix const& affix) const
{
    std::uint32_t& next = state->nextCastFor[affix.behaviour];
    if (now < next)
        return false;
    next = now + std::max<std::uint32_t>(
        1, Ms(n.Get(affix.name + (affix.behaviour == "teleporter" ? "|interval" : "|cast_interval"),
                   n.castMs / 1000.0)));
    return true;
}

// Where this elite's affix work is queued. A promoted pack is in a live rift
// and uses that rift's row; a `.dc elite` harness pack stands in the open
// world, where its own map is the context and the tier is the one it was
// spawned with. Nothing but a harness pack carries EliteState outside a
// rift, so the fallback cannot claim anything else.
bool RiftOf(Creature* creature, Rift& rift)
{
    Map const* map = creature->GetMap();
    if (!map)
        return false;
    {
        // The run seen from the floor the creature stands on, so its queued work is that floor's.
        std::lock_guard<std::mutex> lock(riftMutex);
        if (live.View(map->GetInstanceId(), map->GetId(), rift))
            return true;
    }
    EliteState const* state = creature->CustomData.Get<EliteState>("DCRiftElite");
    if (!state)
        return false;
    rift = Rift();
    rift.instanceId = map->GetInstanceId();
    rift.mapId = map->GetId();
    rift.tier = state->tier;
    return true;
}

// The affixes that act on the update tick, each in its own dc_affix_<name>.cpp. An own-clock affix keeps its own
// timer; every other enabled affix, listed here or not, first waits on its cast cadence (AffixTick::Due).
struct TickAffix
{
    char const* behaviour;
    bool ownClock;
    void (*tick)(AffixTick const&, Affix const&);
};
constexpr TickAffix TICK_AFFIXES[] = {
    {"trail", true, MoltenTick}, {"pool", true, PlaguedTick}, {"cluster", true, FrozenTick},
    {"chains", true, FireChainsTick}, {"mortar", true, MortarTick}, {"jailer", true, JailerTick},
    {"poisonenchanted", true, PoisonEnchantedTick},
    {"beam", false, ArcaneEnchantedTick}, {"desecrator", false, DesecratorTick}, {"pulse", false, FrozenPulseTick},
    {"orbiter", false, OrbiterTick}, {"thunderstorm", false, ThunderstormTick}, {"vortex", false, VortexTick},
    {"teleporter", false, TeleporterTick}, {"shielding", false, ShieldingTick},
    {"reflectsdamage", false, ReflectsDamageTick},
};

// Every affix that dc_rift_affix gives a behaviour. A member runs the per-member
// affixes off its own EliteState (09 SS2 step 2); the six pack-level affixes
// stay on the leader, which is the only carrier that answers them.
class RiftAffixes final : public UnitScript
{
public:
    // This core pin has DealDamage but no corresponding selective-hook enum.
    // Enable all hooks to retain its DamageEffectType gate for landed attacks.
    RiftAffixes() : UnitScript("dc_rift_affixes") { }

    void OnUnitUpdate(Unit* unit, uint32) override
    {
        // The global unit hook fires for every creature on every map. One map
        // flag answers "does this map hold any elite pack at all", so a map with
        // none - every open-world continent, most of the time - leaves here
        // after an empty-container test and never pays for a cast, a CustomData
        // lookup or a rift lock.
        Creature* elite = unit ? unit->ToCreature() : nullptr;
        Map* map = elite ? elite->GetMap() : nullptr;
        if (!map || !map->CustomData.Get<AffixMapFlag>("DCRiftAffixMap"))
            return;
        if (IllusionLink* link = elite->CustomData.Get<IllusionLink>("DCRiftIllusionLink"))
        {
            IllusionistCopyUpdate(elite, map, link);
            return;
        }
        EliteState* state = elite->CustomData.Get<EliteState>("DCRiftElite");
        if (!state)
            return;
        std::shared_ptr<AffixNumbers const> const numbers = Numbers();
        if (!numbers)
            return;
        ShieldingUpdate(elite, state, *numbers);
        // A charmed elite's affixes keep running for the charmer, aimed at its former allies.
        if (!elite->IsAlive() || !elite->IsInCombat())
            return;
        AffixNumbers const& n = *numbers;
        Rift rift;
        if (!RiftOf(elite, rift))
            return;
        std::uint32_t const now = getMSTime();
        state->illusions.erase(std::remove_if(state->illusions.begin(), state->illusions.end(),
            [&](ObjectGuid guid) { return !map->GetCreature(guid); }), state->illusions.end());
        if (now < state->nextTick)
            return;
        std::uint32_t const updateMs = MoltenUpdateMs(*state, n);
        state->nextTick = now + updateMs;
        AffixTick const tick{elite, state, map, rift, n, now, AffixTargetReach()};
        for (Affix const& affix : state->affixes)
        {
            if (!n.Enabled(affix.name))
                continue;
            auto const entry = std::find_if(std::begin(TICK_AFFIXES), std::end(TICK_AFFIXES),
                [&](TickAffix const& candidate) { return affix.behaviour == candidate.behaviour; });
            // An affix with no tick action (Knockback, Electrified, Illusionist) has no cast cadence either: Due would
            // re-arm the nextCastFor slot its own cooldown uses, stretching that cooldown to the cast interval.
            if (entry == std::end(TICK_AFFIXES))
                continue;
            if (!entry->ownClock && !tick.Due(affix))
                continue;               // the rest are on a cast cadence
            entry->tick(tick, affix);
        }
    }

    void OnDamage(Unit* attacker, Unit* victim, uint32& damage) override
    {
        if (!attacker || !victim || !damage)
            return;
        if (Creature* elite = victim->ToCreature())
            if (EliteState* state = elite->CustomData.Get<EliteState>("DCRiftElite"))
                if (Player* player = attacker->ToPlayer())
                    if (elite->IsAlive())
                        EliteStruck(elite, state, player, damage);
    }

    // The exact hit, asked before any 32-bit consumer sees it: Juggernaut's +30% and then Health Link's split, both on the whole
    // of it (a 32-bit view would saturate it, and a view a consumer changes replaces the exact hit). The guard is OnDamage's: a
    // player's hit on a living elite that carries the state.
    void ModifyExactDamage(Unit* attacker, Unit* victim, uint64& damage, DamageEffectType) override
    {
        if (!attacker || !victim || !damage)
            return;
        if (Creature* elite = victim->ToCreature())
            if (EliteState* state = elite->CustomData.Get<EliteState>("DCRiftElite"))
                if (attacker->ToPlayer() && elite->IsAlive())
                    if (std::shared_ptr<AffixNumbers const> const numbers = Numbers())
                    {
                        JuggernautStruck(state, *numbers, damage);
                        HealthLinkStruck(elite, state, *numbers, damage);
                    }
    }

    uint32 DealDamage(Unit* attacker, Unit* victim, uint32 damage, DamageEffectType type) override
    {
        // DIRECT_DAMAGE is the core's landed auto-attack route. Affix shells,
        // spells and periodic damage use other types and cannot trigger CC.
        if (attacker && victim && damage && type == DIRECT_DAMAGE)
            if (Creature* elite = attacker->ToCreature())
                if (EliteState* state = elite->CustomData.Get<EliteState>("DCRiftElite"))
                    if (Player* player = victim->ToPlayer())
                        if (player->IsAlive())
                            EliteHits(elite, state, player);
        return damage;
    }

    void OnUnitDeath(Unit* unit, Unit* killer) override
    {
        Creature* elite = unit ? unit->ToCreature() : nullptr;
        if (!elite)
            return;
        // Fires after the player-kill hook, and does nothing when that already
        // completed the rift.
        CompleteGuardianKill(elite, killer);
        // Resolve the pack while the dead leader's state is still available.
        Creature* leader = PackLeaderOf(elite);
        if (!leader)
            leader = elite;
        if (EliteState* pack = leader->CustomData.Get<EliteState>("DCRiftElite"))
        {
            ReflectsDamageDeath(elite, pack);
            ShieldingDeath(elite, leader, pack);
        }
        // A pack's progress orbs fall once, in both rift modes (Gr::OrbsFall: the last of the pack).
        // The count is the pack's own, so it holds whichever order they fall in
        // and whether or not the leader's corpse is still on the map.
        DropGreaterOrbs(elite);
        {
            std::lock_guard<std::mutex> lock(workMutex);
            auto found = hazardMaps.find(MapWorkKey(elite->GetMap()));
            if (found != hazardMaps.end())
            {
                auto& hazards = found->second;
                hazards.erase(std::remove_if(hazards.begin(), hazards.end(),
                    [&](Hazard const& h) { return h.tag == TAG_POOL && h.caster == elite->GetGUID(); }),
                    hazards.end());
                if (hazards.empty())
                    hazardMaps.erase(found);
            }
        }
        Avenge(elite);
        // 13 S10 visuals: a dead endpoint's beams go with it, including the
        // outgoing one that would otherwise hang between the corpse and a
        // surviving champion.
        TearDownBeams(elite);
        EliteState* state = elite->CustomData.Get<EliteState>("DCRiftElite");
        if (!state)
            return;
        Rift rift;
        if (!RiftOf(elite, rift))
            return;
        // The pack is dead, so its affix line goes with it. Only the leader has
        // a line; a member's death leaves the pack's alone.
        if (!state->member)
            UnpublishElite(rift.instanceId, elite->GetGUID().GetCounter());
        std::shared_ptr<AffixNumbers const> const numbers = Numbers();
        if (!numbers)
            return;
        MoltenDeath(elite, rift, state, *numbers);
    }

private:
    // A player hit this elite.
    static void EliteStruck(Creature* elite, EliteState* state, Player* player, uint32& damage)
    {
        std::shared_ptr<AffixNumbers const> const numbers = Numbers();
        if (!numbers)
            return;
        AffixNumbers const& n = *numbers;
        std::uint32_t const now = getMSTime();
        auto const preCrit = DC::Combat::ConsumePreCritHit(player, elite);
        // The shield window is the pack's, not the monster's, and only the
        // monster that claimed it is immune - maxroll's "one monster at a time".
        EliteState* pack = PackStateOf(elite, state);
        if (ShieldingAbsorbs(elite, state, pack, now, damage))
            return;
        for (Affix const& affix : state->affixes)
        {
            if (!n.Enabled(affix.name))
                continue;
            if (affix.behaviour == "reflect")
                ElectrifiedStruck(elite, state, n, now, affix);
            else if (affix.behaviour == "reflectsdamage")
                ReflectsDamageStruck(elite, state, pack, player, n, now, affix, preCrit ? &*preCrit : nullptr);
        }
        IllusionistStruck(elite, state, n, now);
    }

    // This elite hit a player.
    static void EliteHits(Creature* elite, EliteState* state, Player* player)
    {
        std::shared_ptr<AffixNumbers const> const numbers = Numbers();
        if (!numbers)
            return;
        AffixNumbers const& n = *numbers;
        Rift rift;
        if (!RiftOf(elite, rift))
            return;
        for (Affix const& affix : state->affixes)
        {
            if (!n.Enabled(affix.name))
                continue;
            // The chance is the affix's own row when it has one and _global's
            // otherwise; both are tunables, because the wiki gives a
            // chance per landed attack with no value for either affix.
            double const chance = n.Get(affix.name + "|proc_chance", n.procPct);
            if (affix.behaviour == "knockback" && Roll() * 100.0 < chance)
                KnockbackHit(elite, state, player, n);
            else if (affix.behaviour == "nightmarish" && Roll() * 100.0 < chance)
                NightmarishHit(elite, player, n);
        }
    }
};
// A new queue has to be torn down with its instance like bursts, zones and
// timed are; that purge is dc_rifts.cpp's EraseInstanceWork, which the elite
// file never opens (split rule). This is the elite half's own map
// hook, so a destroyed map takes its hazards with it.
class AffixWorkMap final : public AllMapScript
{
public:
    AffixWorkMap() : AllMapScript("dc_affix_work_map", {ALLMAPHOOK_ON_DESTROY_MAP}) { }

    void OnDestroyMap(Map* map) override
    {
        if (!map)
            return;
        std::lock_guard<std::mutex> lock(workMutex);
        hazardMaps.erase(MapWorkKey(map));
        hazardPerf.erase(MapWorkKey(map));
    }
};

// The elite half of RiftMap::OnMapUpdate, moved here whole.
// dc_rifts.cpp keeps the hook - DrainClosures is the run's work - and calls
// this; everything a tick does to elites is decided in this file.
void DrainEliteWork(Map* map, bool rift, unsigned tier)
{
    if (rift)
        DrainPromotions(map, tier);
    if (!rift && !HarnessOnMap(map))
    {
        if (GroundEffectsOnMap(map))
            DrainHazards(map); // a family monster's pool on a dev or open-world map
        return;
    }
    DrainBursts(map);
    DrainZones(map);
    DrainHazards(map);
}

void RegisterEliteScripts()
{
    new RiftAffixes();
    new AffixWorkMap();
}
}
