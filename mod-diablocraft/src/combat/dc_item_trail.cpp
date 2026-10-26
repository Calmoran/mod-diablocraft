/*
 * World of DiabloCraft - an item's burning trail, Combat's side (N-AREA; Fire Walkers). See dc_item_trail.h.
 */

#include "dc_item_trail.h"
#include "dc_combat.h"
#include "dc_item_trail_math.h"
#include "dc_spell_shells.h"
#include "../common/dc_tunables.h"
#include "Player.h"
#include "Timer.h"

#include <mutex>
#include <unordered_map>
#include <vector>

namespace DC::Combat::ItemTrail
{
    namespace
    {
        // One wearer's fire: the patches still burning and the clock time of the last pulse (0: none yet).
        struct Trail
        {
            std::vector<Patch> patches;
            std::uint32_t last = 0;
        };

        std::mutex mutex;
        std::unordered_map<std::uint64_t, Trail> trails;

        // A combat tunable; a blank one reads 0.
        double Tune(char const* name)
        {
            return DC::Tunables::Has("combat", name) ? DC::Tunables::Get("combat", name) : 0.0;
        }
    } // namespace

    void Burn(Player* player, std::string const& owner, double perSecondPct, double periodSeconds)
    {
        if (!player || !player->IsAlive())
            return;
        std::uint32_t const now = getMSTime();
        double const radius = Tune("fire_walkers_radius_yards");
        std::uint32_t const patchMs = static_cast<std::uint32_t>(Tune("fire_walkers_patch_seconds") * 1000.0);
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        std::vector<Patch> patches;
        double seconds;
        {
            std::lock_guard<std::mutex> lock(mutex);
            Trail& trail = trails[guid];
            Drop(trail.patches, now, patchMs, player->isMoving(), player->GetMapId(), player->GetPositionX(), player->GetPositionY(),
                 player->GetPositionZ());
            seconds = PulseSeconds(trail.last, now, periodSeconds);
            trail.last = now;
            patches = trail.patches;
        }
        double const pct = PulsePct(perSecondPct, seconds);
        double const reach = Reach(patches, now, player->GetMapId(), player->GetPositionX(), player->GetPositionY(), player->GetPositionZ(), radius);
        std::uint32_t const record = Shells::PowerBuffFor(owner.c_str(), "burn_trail");
        if (!record || pct <= 0 || reach <= 0)
            return;
        // Dealt as the wearer's: ComputeHit and DealHit and not Strike, so the fire is no hit of a skill and fires no `hit`
        // (the power's proc coefficient is 0). A damage-over-time tick: average critical, never a roll. One search of the
        // trail's reach, then each enemy burns once however many patches cover it.
        for (Unit* enemy : Enemies(player, record, player->GetPosition(), reach))
        {
            if (!enemy->IsAlive() || !Burns(patches, now, enemy->GetMapId(), enemy->GetPositionX(), enemy->GetPositionY(), enemy->GetPositionZ(), radius))
                continue;
            Hit hit;
            if (ComputeHit(player, enemy, record, hit, pct, true))
                DealHit(player, enemy, record, hit);
        }
    }

    void Clear(std::uint64_t guid)
    {
        std::lock_guard<std::mutex> lock(mutex);
        trails.erase(guid);
    }
} // namespace DC::Combat::ItemTrail
