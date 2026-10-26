// World of DiabloCraft - elite affixes: the moving hazards, ground effects and the map-tick drains.

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
HazardKey MapWorkKey(unsigned map, unsigned instance)
{
    return (static_cast<HazardKey>(instance) << 32) | map;
}
HazardKey MapWorkKey(Map const* map)
{
    return MapWorkKey(map->GetId(), map->GetInstanceId());
}
std::unordered_map<HazardKey, std::vector<Hazard>> hazardMaps;
std::unordered_map<HazardKey, HazardPerf> hazardPerf;
std::string AffixPerformance(Map const* map)
{
    std::lock_guard<std::mutex> lock(workMutex);
    auto found = hazardPerf.find(MapWorkKey(map));
    if (found == hazardPerf.end())
        return "No hazard ticks recorded on this map.";
    HazardPerf const& p = found->second;
    std::ostringstream text;
    text << "Hazards: " << p.live << "; ticks: " << p.ticks
         << "; last: " << p.lastUs << " us; peak: " << p.peakUs << " us.";
    return text.str();
}
void ClearPackAffixWork(Map* map, HarnessPack const& pack)
{
    auto owned = [&](ObjectGuid guid)
    {
        return guid == pack.leader || std::find(pack.members.begin(), pack.members.end(), guid) != pack.members.end();
    };
    std::vector<ObjectGuid> members = pack.members;
    members.push_back(pack.leader);
    for (ObjectGuid guid : members)
        if (Creature* creature = map->GetCreature(guid))
            if (EliteState* state = creature->CustomData.Get<EliteState>("DCRiftElite"))
                for (ObjectGuid copy : state->illusions)
                    if (Creature* illusion = map->GetCreature(copy))
                        illusion->DespawnOrUnsummon();
    std::lock_guard<std::mutex> lock(workMutex);
    auto found = hazardMaps.find(MapWorkKey(map));
    if (found != hazardMaps.end())
    {
        auto& hazards = found->second;
        hazards.erase(std::remove_if(hazards.begin(), hazards.end(),
            [&](Hazard const& h) { return owned(h.caster); }), hazards.end());
        if (hazards.empty())
            hazardMaps.erase(found);
    }
    bursts.erase(std::remove_if(bursts.begin(), bursts.end(),
        [&](Burst const& b) { return b.mapId == pack.mapId && b.instanceId == pack.instanceId
                                      && owned(b.caster); }), bursts.end());
}

Hazard BaseHazard(Creature* source, Rift const& rift, std::uint32_t shell)
{
    Hazard h;
    h.instanceId = rift.instanceId;
    h.mapId = rift.mapId;
    h.caster = source->GetGUID();
    h.shell = shell;
    h.tier = rift.tier;
    h.grLevel = rift.mode == "gr" ? rift.grRank : 0;
    if (EliteState const* state = source->CustomData.Get<EliteState>("DCRiftElite"))
        for (Affix const& affix : state->affixes)
            if (affix.shell == shell)
                h.affixName = affix.name;
    h.startAt = getMSTime();
    h.lastMove = h.startAt;
    return h;
}
void SpawnHazard(Hazard h)
{
    std::lock_guard<std::mutex> lock(workMutex);
    hazardMaps[MapWorkKey(h.mapId, h.instanceId)].push_back(std::move(h));
}
// Family ground effects (dc_family_ai.cpp) outside a rift or a harness: the map tick only drains hazards on a map that
// has one, so it asks. A raw count first keeps every map to one atomic read until the first pool exists.
// ponytail: the count only grows, so after the first pool each map update takes the lock once; a per-map count if
// that ever shows in the profile.
std::atomic<unsigned> groundEffectCount{0};
bool GroundEffectsOnMap(Map const* map)
{
    if (!groundEffectCount.load(std::memory_order_relaxed))
        return false;
    std::lock_guard<std::mutex> lock(workMutex);
    return hazardMaps.count(MapWorkKey(map)) > 0;
}
void SpawnGroundEffect(Creature* source, GroundEffect const& effect)
{
    Map* map = source ? source->GetMap() : nullptr;
    if (!map || effect.durationMs == 0 || effect.radius <= 0.0f)
        return;
    Hazard h;
    h.instanceId = map->GetInstanceId();
    h.mapId = map->GetId();
    h.caster = source->GetGUID();
    h.shell = effect.shell;
    h.path = HazardPath::Static;
    h.x = h.originX = effect.x;
    h.y = h.originY = effect.y;
    h.z = h.originZ = effect.z;
    h.radius = effect.radius;
    h.damage = effect.damage;
    h.tickMs = std::max<std::uint32_t>(1, effect.tickMs);
    h.startAt = getMSTime();
    h.lastMove = h.startAt;
    h.armUntil = h.startAt + effect.armMs;
    h.nextTick = h.armUntil;
    h.endsAt = h.armUntil + effect.durationMs;
    groundEffectCount.fetch_add(1, std::memory_order_relaxed);
    SpawnHazard(std::move(h));
}
// Hazard geometry is the ground plane: z is decoration, and a hazard on the
// floor must catch a player standing at either end of a slope.
float Dist2D(float ax, float ay, float bx, float by)
{
    float const dx = ax - bx, dy = ay - by;
    return std::sqrt(dx * dx + dy * dy);
}
// Distance from a point to the segment (ax,ay)-(bx,by); the whole of Fire
// Chains and Poison Enchanted is this one function: the
// midpoint blob has to become perpendicular distance to the segment.
float PointSegmentDistance(float px, float py, float ax, float ay, float bx, float by)
{
    float const dx = bx - ax, dy = by - ay;
    float const len2 = dx * dx + dy * dy;
    if (len2 <= 0.0001f)
        return Dist2D(px, py, ax, ay);
    float t = ((px - ax) * dx + (py - ay) * dy) / len2;
    t = std::clamp(t, 0.0f, 1.0f);
    return Dist2D(px, py, ax + dx * t, ay + dy * t);
}
// Smallest signed difference between two angles, in (-pi, pi].
float AngleDiff(float a, float b)
{
    float d = std::fmod(a - b + float(M_PI), 2.0f * float(M_PI));
    if (d < 0)
        d += 2.0f * float(M_PI);
    return d - float(M_PI);
}
// How many stacks this player has earned in a stacking pool. Re-entering inside
// stackResetMs keeps the count; staying out longer starts again at one.
unsigned EscalatedStacks(Hazard& h, ObjectGuid guid, std::uint32_t now)
{
    for (HazardStack& stack : h.stackState)
        if (stack.guid == guid)
        {
            if (!stack.inside && now - stack.lastSeenAt >= h.stackResetMs)
            {
                stack.enteredAt = now;
                stack.exposureMs = 0;
            }
            else if (stack.inside)
                stack.exposureMs += now - stack.lastSeenAt;
            if (h.stackIntervalMs > 0.0)
            {
                std::uint32_t const activeMs = stack.exposureMs > h.stackEntryMs
                    ? stack.exposureMs - h.stackEntryMs : 0;
                unsigned const steps = static_cast<unsigned>(double(activeMs) / h.stackIntervalMs);
                stack.count = std::min(h.stackMax, 1u + steps);
            }
            stack.inside = true;
            stack.lastSeenAt = now;
            return stack.count;
        }
    HazardStack stack;
    stack.guid = guid;
    stack.enteredAt = now;
    stack.lastSeenAt = now;
    stack.count = 1;
    stack.inside = true;
    h.stackState.push_back(stack);
    return 1;
}

// One affix by name OR by behaviour, case-insensitively, with the list of the
// ones that do something for a caller who got it wrong. Both are accepted
// because 13-elite-affixes §10 writes its test lines as `.dc elite affix arcane`
// and `.dc elite affix chains` - the behaviour - while `.dc rift affixes` and
// the nameplate show "Arcane Enchanted" and "Fire Chains".
bool FindAffix(std::string const& wanted, Affix& chosen, std::string& names)
{
    auto lower = [](std::string text)
    {
        std::transform(text.begin(), text.end(), text.begin(),
                       [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
        return text;
    };
    auto const numbers = Numbers();
    bool found = false;
    std::lock_guard<std::mutex> lock(dataMutex);
    for (Affix const& affix : affixPool)
    {
        if (!affix.behaviour.empty())
            names += (names.empty() ? "" : ", ") + affix.name;
        if (!found && (lower(affix.name) == lower(wanted)
                       || (!affix.behaviour.empty() && affix.behaviour == lower(wanted))))
        {
            chosen = affix;
            found = true;
        }
    }
    if (found && (chosen.behaviour.empty() || !numbers || !numbers->Enabled(chosen.name)))
    {
        names = chosen.name + " disabled";
        if (numbers && numbers->unconfigured.count(chosen.name))
            for (auto const& parameter : numbers->unconfigured.at(chosen.name))
                names += "; the designer sets " + parameter;
        else
            names += "; mechanic not implemented";
        return false;
    }
    return found;
}
// A zone hurts whoever is standing in it each tick until it expires.
void DrainZones(Map* map)
{
    std::uint32_t const now = getMSTime();
    std::vector<Zone> mine;
    {
        std::lock_guard<std::mutex> lock(workMutex);
        if (zones.empty())
            return;
        // Map id as well as instance id: every continent shares instance 0,
        // so a harness pack's work would otherwise be drained by whichever
        // open-world map updated first.
        auto split = std::stable_partition(zones.begin(), zones.end(),
            [&](Zone const& z) { return z.instanceId != map->GetInstanceId()
                                     || z.mapId != map->GetId(); });
        mine = decltype(mine)(split, zones.end());
        zones.erase(split, zones.end());
    }
    std::vector<Zone> keep;
    for (Zone& zone : mine)
    {
        if (now >= zone.endsAt)
            continue;
        if (now >= zone.nextTick)
        {
            zone.nextTick = now + zone.tickMs;
            // The zone outlives nothing: BlastPlayers needs a source for the
            // attack check and the combat log, so a zone whose caster is
            // already gone stops ticking.
            if (Creature* caster = map->GetCreature(zone.caster))
            {
                BlastPlayers(caster, map, zone.x, zone.y, zone.z, zone.radius,
                             zone.shell, zone.damage);
                if (zone.slow > 0)
                    map->DoForAllPlayers([&](Player* player)
                    {
                        if (player && player->IsAlive() &&
                            player->IsWithinDist3d(zone.x, zone.y, zone.z, zone.radius))
                        {
                            ApplySlow(caster, player, zone.slowSpell, zone.slow, zone.tickMs * 2);
                        }
                    });
            }
        }
        keep.push_back(zone);
    }
    if (keep.empty())
        return;
    std::lock_guard<std::mutex> lock(workMutex);
    zones.insert(zones.end(), keep.begin(), keep.end());
}

void DrainBursts(Map* map)
{
    std::uint32_t const now = getMSTime();
    std::vector<Burst> due;
    {
        std::lock_guard<std::mutex> lock(workMutex);
        if (bursts.empty())
            return;
        auto split = std::stable_partition(bursts.begin(), bursts.end(),
            [&](Burst const& b) { return b.instanceId != map->GetInstanceId()
                                      || b.mapId != map->GetId() || now < b.at; });
        due = decltype(due)(split, bursts.end());
        bursts.erase(split, bursts.end());
    }
    auto const numbers = Numbers();
    for (Burst const& burst : due)
    {
        if (!numbers || !numbers->Enabled(burst.affixName))
            continue;
        // Molten's core outlives the elite that dropped it, but a corpse is
        // still in the map and still the source of the damage. Once the
        // body is gone there is nothing to credit and the blast is skipped.
        Creature* source = map->GetCreature(burst.caster);
        if (!source)
            continue;
        BlastPlayers(source, map, burst.x, burst.y, burst.z, burst.radius,
                     burst.shell, AffixDamage(*numbers, burst.tier, burst.grLevel, burst.affixName, "base_explosion_damage"));
    }
}

void DrainPromotions(Map* map, unsigned tier)
{
    std::vector<Promotion> mine;
    {
        std::lock_guard<std::mutex> lock(workMutex);
        if (promotions.empty())
            return;
        auto split = std::stable_partition(promotions.begin(), promotions.end(),
            [&](Promotion const& p) { return p.instanceId != map->GetInstanceId(); });
        mine = decltype(mine)(split, promotions.end());
        promotions.erase(split, promotions.end());
    }
    for (Promotion const& promotion : mine)
        Promote(map, promotion, tier);
}

// Does the hazard touch this point? The shape follows the path: a wedge for
// Arcane Enchanted's sweep, perpendicular distance to a segment for Poison
// Enchanted and Fire Chains, a point radius for everything else.
bool HazardTouches(Hazard const& h, float px, float py)
{
    switch (h.path)
    {
        case HazardPath::Sweep:
        {
            if (Dist2D(px, py, h.originX, h.originY) > h.length)
                return false;
            float const bearing = std::atan2(py - h.originY, px - h.originX);
            float const swept = std::max(0.0f, h.angle - h.sweepFrom);
            return std::fabs(AngleDiff(bearing, (h.angle + h.sweepFrom) * 0.5f))
                   <= h.wedge + swept * 0.5f;
        }
        case HazardPath::GrowLine:
        case HazardPath::Link:
            return PointSegmentDistance(px, py, h.originX, h.originY, h.x, h.y) <= h.halfWidth;
        case HazardPath::Linear:
            return PointSegmentDistance(px, py, h.contactX, h.contactY, h.x, h.y) <= h.radius;
        default:
            return Dist2D(px, py, h.x, h.y) <= h.radius;
    }
}
// One tick of a hazard's path. Movement is dt-scaled off the map clock so a
// hazard travels the same distance whatever the map update rate is.
void MoveHazard(Hazard& h, Map* map, std::uint32_t now)
{
    std::uint32_t const activeFrom = std::max(h.lastMove, h.armUntil);
    float const dt = now > activeFrom ? float(now - activeFrom) / 1000.0f : 0.0f;
    h.lastMove = now;
    // An arming hazard shows but does not do: the beam does not sweep, the
    // sphere does not chase and the gas does not grow until its delay is up.
    if (h.path == HazardPath::Ballistic)
    {
        std::uint32_t const flightMs = h.armUntil > h.startAt ? h.armUntil - h.startAt : 1;
        float const f = std::clamp(float(now - h.startAt) / flightMs, 0.0f, 1.0f);
        float const flight = flightMs / 1000.0f;
        h.x = h.originX + (h.impactX - h.originX) * f;
        h.y = h.originY + (h.impactY - h.originY) * f;
        h.z = h.originZ + (h.impactZ - h.originZ) * f
              + KNOCKBACK_GRAVITY * flight * flight * 0.5f * f * (1.0f - f);
        return;
    }
    if (now < h.armUntil)
        return;
    switch (h.path)
    {
        case HazardPath::Linear:
        {
            float const step = std::min(h.speed * dt, std::max(0.0f, h.maxLength - h.travelled));
            h.x += h.dirX * step;
            h.y += h.dirY * step;
            h.travelled += step;
            if (h.maxLength > 0.0f && h.travelled >= h.maxLength)
                h.endsAt = now;
            break;
        }
        case HazardPath::GrowLine:
        {
            std::uint32_t const life = h.endsAt > h.armUntil ? h.endsAt - h.armUntil : 1;
            float const f = std::min(1.0f, float(now - h.armUntil) / float(life));
            h.length = h.maxLength * f;
            h.x = h.originX + h.dirX * h.length;
            h.y = h.originY + h.dirY * h.length;
            break;
        }
        case HazardPath::Orbital:
        {
            h.angle += h.orbitSpeed * dt;
            std::uint32_t const life = h.endsAt > h.armUntil ? h.endsAt - h.armUntil : 1;
            float const f = std::min(1.0f, float(now - h.armUntil) / float(life));
            h.orbitRadius = h.orbitStart + (h.orbitMax - h.orbitStart) * f;
            h.x = h.originX + h.orbitRadius * std::cos(h.angle);
            h.y = h.originY + h.orbitRadius * std::sin(h.angle);
            break;
        }
        case HazardPath::Following:
        case HazardPath::Tracking:
        {
            Unit* target = HazardTarget(map, h.target);
            if (!target || !target->IsAlive() || target->GetMap() != map)
            {
                if (h.path == HazardPath::Following)
                    h.endsAt = now;
                else
                    h.path = HazardPath::Static;   // lost him: pulse where it stands
                break;
            }
            float const dx = target->GetPositionX() - h.x;
            float const dy = target->GetPositionY() - h.y;
            float const dist = std::sqrt(dx * dx + dy * dy);
            if (dist <= h.speed * dt)
            {
                if (h.path == HazardPath::Tracking)
                    h.path = HazardPath::Static;   // reached him once, then settles
                h.x = target->GetPositionX();
                h.y = target->GetPositionY();
                h.z = target->GetPositionZ();
                break;
            }
            float const step = std::min(h.speed * dt, dist);
            h.x += dx / dist * step;
            h.y += dy / dist * step;
            h.z = target->GetPositionZ();
            break;
        }
        case HazardPath::Sweep:
            h.sweepFrom = h.angle;
            h.angle += h.sweepRate * dt;
            break;
        case HazardPath::Link:
        {
            Creature* a = map->GetCreature(h.linkA);
            Creature* b = map->GetCreature(h.linkB);
            if (!a || !b || !a->IsAlive() || !b->IsAlive())
            {
                h.endsAt = now;                // a dead end tears the chain down
                break;
            }
            h.originX = a->GetPositionX(); h.originY = a->GetPositionY();
            h.originZ = a->GetPositionZ();
            h.x = b->GetPositionX(); h.y = b->GetPositionY(); h.z = b->GetPositionZ();
            break;
        }
        case HazardPath::Static:
        default:
            break;
    }
}
// Blackthorne's Battlegear 4-piece. Combat marks the wearer; the three ground-effect affixes then pass
// them by. docs/contracts/legendary-world-pieces.md says what is skipped. The set is read on the map tick and written from
// the item refresh, so it has a lock of its own.
std::mutex groundImmuneMutex;
std::unordered_set<ObjectGuid> groundImmune;
void SetGroundEffectImmune(Player const* player, bool immune)
{
    if (!player)
        return;
    std::lock_guard<std::mutex> lock(groundImmuneMutex);
    if (immune)
        groundImmune.insert(player->GetGUID());
    else
        groundImmune.erase(player->GetGUID());
}
bool PassesGroundEffect(Hazard const& h, Player const* player)
{
    if (h.affixName != "Desecrator" && h.affixName != "Molten" && h.affixName != "Plagued")
        return false;
    std::lock_guard<std::mutex> lock(groundImmuneMutex);
    return groundImmune.count(player->GetGUID()) > 0;
}
// The monster half of ObservePoolContact and ApplyHazard, run for a charmed source, whose foes are its
// former allies. Same rules as the player half: stacks grow while a foe stands in the pool, one tick's damage is the base
// (or the ring's inner number) times the stacking factor, a piercing hazard hits each foe once.
void ObservePoolContactFoes(Creature* source, Hazard& h, std::uint32_t now)
{
    for (Unit* foe : AffixFoesOf(source))
    {
        ObjectGuid const guid = foe->GetGUID();
        if (HazardTouches(h, foe->GetPositionX(), foe->GetPositionY()))
            EscalatedStacks(h, guid, now);
        else
            for (HazardStack& stack : h.stackState)
                if (stack.guid == guid && stack.inside)
                {
                    stack.inside = false;
                    stack.lastSeenAt = now;
                }
    }
}
void ApplyHazardToFoes(Creature* source, Hazard& h)
{
    for (Unit* foe : AffixFoesOf(source))
    {
        if (!HazardTouches(h, foe->GetPositionX(), foe->GetPositionY()))
            continue;
        ObjectGuid const guid = foe->GetGUID();
        if (h.oncePerTarget && std::find(h.struck.begin(), h.struck.end(), guid) != h.struck.end())
            continue;
        double damage = h.damage;
        if (h.innerRadius > 0.0f)
            damage = Dist2D(h.x, h.y, foe->GetPositionX(), foe->GetPositionY()) <= h.innerRadius ? h.innerDamage : h.damage;
        if (h.escalating)
        {
            unsigned const stacks = EscalatedStacks(h, guid, getMSTime());
            auto const contact = std::find_if(h.stackState.begin(), h.stackState.end(),
                [&](HazardStack const& stack) { return stack.guid == guid; });
            if (contact != h.stackState.end() && contact->exposureMs < h.stackEntryMs)
                continue;
            damage *= std::pow(h.stackMultiplier, double(stacks) - 1.0);
        }
        if (damage <= 0.0 && !h.freezeMs && h.slow <= 0.0f)
            continue;
        if (h.oncePerTarget)
            h.struck.push_back(guid);
        HitFoe(source, foe, h.shell, damage);
        if (h.freezeMs && foe->IsAlive() && HoldFoe(source, foe, FREEZE_HOLD, h.freezeMs))
            foe->InterruptNonMeleeSpells(false);
        if (h.slow > 0.0f)
            SlowFoe(source, foe, h.slowSpell, h.slow, h.tickMs * 2);
    }
}
// Contact is observed on every map frame, including arming. Time outside a
// pool does not earn stacks; the grace period retains earned exposure only.
void ObservePoolContact(Creature* source, Map* map, Hazard& h, std::uint32_t now)
{
    map->DoForAllPlayers([&](Player* player)
    {
        if (!player)
            return;
        ObjectGuid const guid = player->GetGUID();
        if (player->IsAlive() && !PassesGroundEffect(h, player) && source->IsValidAttackTarget(player)
            && HazardTouches(h, player->GetPositionX(), player->GetPositionY()))
            EscalatedStacks(h, guid, now);
        else
            for (HazardStack& stack : h.stackState)
                if (stack.guid == guid && stack.inside)
                {
                    stack.inside = false;
                    stack.lastSeenAt = now;
                }
    });
    if (source->IsCharmed())
        ObservePoolContactFoes(source, h, now);
}
// Hurt everyone the hazard is touching this tick. A ring (innerRadius set)
// takes the direct number inside and the splash number outside; a piercing
// hazard hits each player at most once.
void ApplyHazard(Creature* source, Map* map, Hazard& h)
{
    map->DoForAllPlayers([&](Player* player)
    {
        if (!player || !player->IsAlive() || !source->IsValidAttackTarget(player))
            return;
        if (PassesGroundEffect(h, player))
            return;
        if (!HazardTouches(h, player->GetPositionX(), player->GetPositionY()))
            return;
        ObjectGuid const guid = player->GetGUID();
        if (h.oncePerTarget)
        {
            if (std::find(h.struck.begin(), h.struck.end(), guid) != h.struck.end())
                return;
        }
        double damage = h.damage;
        if (h.innerRadius > 0.0f)
            damage = Dist2D(h.x, h.y, player->GetPositionX(), player->GetPositionY())
                         <= h.innerRadius
                     ? h.innerDamage : h.damage;
        if (h.escalating)
        {
            unsigned const stacks = EscalatedStacks(h, guid, getMSTime());
            auto const contact = std::find_if(h.stackState.begin(), h.stackState.end(),
                [&](HazardStack const& stack) { return stack.guid == guid; });
            if (contact != h.stackState.end() && contact->exposureMs < h.stackEntryMs)
                return;
            damage *= std::pow(h.stackMultiplier, double(stacks) - 1.0);
        }
        if (damage <= 0.0 && !h.freezeMs && h.slow <= 0.0f)
            return;
        if (h.oncePerTarget)
            h.struck.push_back(guid);
        DC::Combat::DealMonsterHit(source, player, h.shell, damage);
        if (h.freezeMs && player->IsAlive())
        {
            if (ApplyHold(source, player, FREEZE_HOLD, h.freezeMs))
                player->InterruptNonMeleeSpells(false);
        }
        if (h.slow > 0.0f)
        {
            ApplySlow(source, player, h.slowSpell, h.slow, h.tickMs * 2);
        }
    });
    if (source->IsCharmed())
        ApplyHazardToFoes(source, h);
    if (h.path == HazardPath::Linear)
    {
        h.contactX = h.x;
        h.contactY = h.y;
    }
}
// The map tick for the moving-hazard subsystem: move every live hazard, then
// hurt whoever is standing in one that is armed and due. Like zones and bursts,
// a hazard whose caster is gone stops: the damage needs a source for the attack
// check and the combat log.
void DrainHazards(Map* map)
{
    auto const started = std::chrono::steady_clock::now();
    std::uint32_t const now = getMSTime();
    HazardKey const key = MapWorkKey(map);
    auto const numbers = Numbers();
    std::vector<Hazard> mine;
    {
        std::lock_guard<std::mutex> lock(workMutex);
        auto found = hazardMaps.find(key);
        if (found == hazardMaps.end())
            return;
        mine.swap(found->second);
        hazardMaps.erase(found);
    }
    std::vector<Hazard> keep;
    keep.reserve(mine.size());
    for (Hazard& h : mine)
    {
        if (!h.affixName.empty())
        {
            if (!numbers || !numbers->Enabled(h.affixName))
                continue;
            h.damage = AffixDamage(*numbers, h.tier, h.grLevel, h.affixName,
                h.tag == TAG_MORTAR ? "base_collateral_damage" : "base_damage");
            if (h.tag == TAG_MORTAR)
                h.innerDamage = AffixDamage(*numbers, h.tier, h.grLevel, h.affixName);
        }
        if (now >= h.endsAt && !h.oneShot)
            continue;
        Creature* source = nullptr;
        if (h.path == HazardPath::Link)
        {
            // A chain outlives its caster: when the pack leader falls, the link
            // between two surviving champions still burns, so credit a living
            // endpoint rather than the (possibly dead) spawner.
            Creature* a = map->GetCreature(h.linkA);
            Creature* b = map->GetCreature(h.linkB);
            source = (a && a->IsAlive()) ? a : ((b && b->IsAlive()) ? b : nullptr);
            // A link with a charmed end serves the charmer: it burns the former allies, not the players.
            if (a && b && a->IsAlive() && b->IsAlive() && b->IsCharmed() && !a->IsCharmed())
                source = b;
        }
        else
            source = map->GetCreature(h.caster);
        if (!source || (h.tag == TAG_POOL && !source->IsAlive()))
            continue;
        MoveHazard(h, map, now);
        if (h.escalating)
            ObservePoolContact(source, map, h, now);
        if ((h.path == HazardPath::Link || h.path == HazardPath::Following) && now >= h.endsAt)
            continue;
        bool const boltFinished = h.path == HazardPath::Linear && now >= h.endsAt;
        if (now >= h.armUntil && (now >= h.nextTick || boltFinished))
        {
            h.nextTick = now + std::max<std::uint32_t>(1, h.tickMs);
            ApplyHazard(source, map, h);
            bool const stormFinished = h.strikesRemaining && --h.strikesRemaining == 0;
            if (h.oneShot || boltFinished || stormFinished)
                continue;                  // its damage is spent
        }
        keep.push_back(std::move(h));
    }
    std::lock_guard<std::mutex> lock(workMutex);
    if (!keep.empty())
    {
        auto& pending = hazardMaps[key];
        if (pending.empty())
            pending.swap(keep);
        else
            pending.insert(pending.end(), std::make_move_iterator(keep.begin()),
                           std::make_move_iterator(keep.end()));
    }
    HazardPerf& perf = hazardPerf[key];
    ++perf.ticks;
    perf.live = hazardMaps.count(key) ? hazardMaps.at(key).size() : 0;
    perf.lastUs = std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::steady_clock::now() - started).count();
    perf.peakUs = std::max(perf.peakUs, perf.lastUs);
}
}
