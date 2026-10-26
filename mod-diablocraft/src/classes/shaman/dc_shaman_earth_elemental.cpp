/*
 * Earth Elemental and its five runes: the stomps at the place it rose, the damage reduction the Shaman wears while it
 * stands, Bedrock's larger one, Primal Earth Elemental's small Earthquakes, Magma Colossus' lava pools, Thunder
 * Colossus' stun and arcs and Glacial Colossus' freeze and mark. The elemental is skill damage of the Shaman, shown by an
 * untargetable creature that deals nothing; it holds enemies by hitting them. One at a time, a new cast moves it; the Fire
 * Elemental stands beside it. The cast is the engine's ground spell and deals nothing at once (the record states a duration); the
 * dispatch is in dc_shaman.cpp.
 */

#include "dc_shaman_earth_elemental.h"
#include "dc_shaman_common.h"
#include "dc_shaman_damage_mark.h"
#include "dc_shaman_effects.h"
#include "dc_shaman_passives.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_minions.h"
#include "../../items/dc_inventory.h"
#include "../../stats/dc_stats.h"
#include "Map.h"
#include "Position.h"
#include "Unit.h"

#include <algorithm>
#include <chrono>
#include <mutex>
#include <unordered_map>
#include <vector>

namespace DC::Combat::Shaman::EarthElemental
{
    namespace
    {
        constexpr std::string_view Skill = "Earth Elemental";
        // The creature the elemental shows as (data/d3/shaman_elemental_summons.csv): untargetable, it stands where it rose and deals
        // nothing itself.
        constexpr std::uint32_t Entry = 900191;
        constexpr char const* Group = "earth_elemental";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && std::string_view(row->skill) == Skill ? RuneOf(row->rune) : Rune::None;
        }

        // The record of the skill itself: the numbers a rune takes from it are stated there.
        std::uint32_t BaseId()
        {
            for (auto const& row : Shells::Abilities)
                if (Skill == row.skill && !*row.rune)
                    return row.id;
            return 0;
        }

        double Tune(char const* name)
        {
            return Tunables::Get("combat", name);
        }

        // The Earth Elemental a Shaman has up: where it rose, the record of the cast, and the stamp its stomps answer
        // to (a new cast takes a new stamp and the old stomps find theirs gone and stop).
        struct Standing
        {
            std::uint32_t spellId = 0;
            Rune rune = Rune::None;
            Position center;
            std::uint64_t stamp = 0;
            Map const* map = nullptr;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, Standing> standing; // by the Shaman
        std::uint64_t stamps = 0;

        // "While it is active, you take {damage_reduction_pct} less damage": the Shaman's Specific Reduction, put on
        // and taken off.
        void PutReduction(Player* player, double pct)
        {
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            Stats::RemoveContribution(guid, Source::Temporary, Stat::SpecificReduction, BaseId());
            if (pct > 0)
                Stats::AddContribution(guid, {Source::Temporary, Stat::SpecificReduction, BaseId(), pct, Bucket::Flat});
            Stats::Recompute(player);
            Inventory::PushSheet(player);
        }

        void End(Player* player, std::uint64_t key, std::uint64_t stamp)
        {
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto found = standing.find(key);
                if (found == standing.end() || found->second.stamp != stamp)
                    return;
                standing.erase(found);
            }
            PutReduction(player, 0);
            Minions::Dismiss(player, Group);
        }

        // A small Earthquake or a lava pool a stomp leaves: ticks of `pct` on every enemy within `radius` of `at` for
        // `left` ticks. It finishes after the elemental is gone; it stops only with the Shaman.
        void Zone(Player* player, std::uint32_t spellId, Position at, double radius, unsigned left, double pct,
                  std::uint32_t intervalMs)
        {
            if (!left || !player->IsInWorld() || !player->IsAlive())
                return;
            for (Unit* enemy : Combat::Enemies(player, spellId, at, radius))
                Combat::Strike(player, enemy, spellId, pct, true);
            if (left > 1)
                player->m_Events.AddEventAtOffset([player, spellId, at, radius, left, pct, intervalMs]
                                                  { Zone(player, spellId, at, radius, left - 1, pct, intervalMs); },
                                                  std::chrono::milliseconds(intervalMs));
        }

        void StartZone(Player* player, Standing const& elemental, double perSecondPct, double seconds)
        {
            double const tick = Tune("earth_elemental_zone_tick_seconds");
            unsigned const ticks = PeriodicStrike::Ticks(seconds, tick);
            auto const interval = std::uint32_t(tick * 1000.0 + 0.5);
            double const pct = ZoneTickPct(perSecondPct, tick);
            if (!ticks || pct <= 0)
                return;
            Position const at = elemental.center;
            std::uint32_t const spellId = elemental.spellId;
            double const radius = Numbers::Num(spellId, "radius_yards");
            player->m_Events.AddEventAtOffset([player, spellId, at, radius, ticks, pct, interval]
                                              { Zone(player, spellId, at, radius, ticks, pct, interval); },
                                              std::chrono::milliseconds(interval));
        }

        // "Stomps Stun for {stun_duration_seconds} second; each stomp also arcs to {target_count} enemies outside the
        // radius."
        void Arcs(Player* player, Standing const& elemental)
        {
            std::uint32_t const spellId = elemental.spellId;
            double const radius = Numbers::Num(spellId, "radius_yards");
            std::vector<Unit*> far =
                Combat::Enemies(player, spellId, elemental.center, Tune("earth_elemental_arc_radius_yards"));
            far.erase(std::remove_if(far.begin(), far.end(),
                                     [&](Unit* enemy)
                                     {
                                         return !Outside(elemental.center.GetPositionX(),
                                                         elemental.center.GetPositionY(), enemy->GetPositionX(),
                                                         enemy->GetPositionY(), radius);
                                     }),
                      far.end());
            std::sort(far.begin(), far.end(), [&](Unit* a, Unit* b)
                      { return elemental.center.GetExactDist(a) < elemental.center.GetExactDist(b); });
            auto const count = std::size_t(Numbers::Num(spellId, "target_count"));
            if (far.size() > count)
                far.resize(count);
            for (Unit* enemy : far)
                Combat::Strike(player, enemy, spellId, Tune("earth_elemental_arc_damage_pct"));
        }

        void Stomp(Player* player, std::uint64_t key, std::uint64_t stamp, unsigned left, std::uint32_t intervalMs)
        {
            Standing elemental;
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto found = standing.find(key);
                if (found == standing.end() || found->second.stamp != stamp)
                    return;
                elemental = found->second;
            }
            // The Shaman is gone, dead or on another floor: the elemental ends.
            if (!player->IsInWorld() || !player->IsAlive() || player->GetMap() != elemental.map)
            {
                End(player, key, stamp);
                return;
            }
            std::uint32_t const spellId = elemental.spellId;
            // "It stomps every {interval_seconds} seconds for {damage_pct} weapon damage as Physical within
            // {radius_yards} yards."
            for (Unit* enemy :
                 Combat::Enemies(player, spellId, elemental.center, Numbers::Num(spellId, "radius_yards")))
            {
                Combat::Strike(player, enemy, spellId, Numbers::Num(BaseId(), "damage_pct"));
                if (!enemy->IsAlive())
                    continue;
                switch (elemental.rune)
                {
                    case Rune::ThunderColossus:
                        Stun(player, enemy, Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player));
                        break;
                    case Rune::GlacialColossus:
                        // "Stomps Freeze for {freeze_duration_seconds} second and enemies take {damage_taken_pct} more
                        // damage from you."
                        Freeze(player, enemy, Numbers::Num(spellId, "freeze_duration_seconds"));
                        DamageMark::Set(player, enemy, Numbers::Num(spellId, "damage_taken_pct"),
                                        Tune("earth_elemental_glacial_mark_seconds"));
                        break;
                    default:
                        break;
                }
            }
            if (elemental.rune == Rune::ThunderColossus)
                Arcs(player, elemental);
            // "Each stomp creates a small Earthquake for {duration_seconds} seconds that deals {damage_pct} weapon
            // damage as Physical per second." / "Stomps leave lava pools that deal {damage_pct} weapon damage as Fire
            // per second for {duration_seconds} seconds."
            if (elemental.rune == Rune::PrimalEarthElemental || elemental.rune == Rune::MagmaColossus)
                StartZone(player, elemental, Numbers::Num(spellId, "damage_pct"),
                          Numbers::Num(spellId, "duration_seconds"));
            if (left > 1)
            {
                player->m_Events.AddEventAtOffset([player, key, stamp, left, intervalMs]
                                                  { Stomp(player, key, stamp, left - 1, intervalMs); },
                                                  std::chrono::milliseconds(intervalMs));
                return;
            }
            End(player, key, stamp);
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        auto const* row = Shells::FindAbility(spellId);
        return row && std::string_view(row->skill) == Skill;
    }

    void Ground(Player* player, std::uint32_t spellId, Position const& center)
    {
        if (!player || !Is(spellId))
            return;
        Rune const rune = RuneAt(spellId);
        double const seconds = Passive::ElementalLasts(
                         player, Skill, Combat::ModifiedDurationSeconds(player, spellId, Numbers::Num(BaseId(), "duration_seconds"))),
                     interval = Numbers::Num(BaseId(), "interval_seconds");
        unsigned const stomps = Stomps(seconds, interval);
        if (!stomps)
            return;
        std::uint64_t const key = player->GetGUID().GetRawValue();
        std::uint64_t stamp;
        {
            std::lock_guard<std::mutex> guard(mutex);
            // One at a time: a new cast moves the elemental.
            Standing& elemental = standing[key];
            stamp = elemental.stamp = ++stamps;
            elemental.spellId = spellId;
            elemental.rune = rune;
            elemental.center = center;
            elemental.map = player->GetMap();
        }
        // The look: where it rose, one at a time as the stomps are.
        Minions::Dismiss(player, Group);
        Minions::Raise(player, Group, center);
        PutReduction(player, Numbers::Num(spellId, "damage_reduction_pct", ReductionQualifier(rune)));
        auto const ms = std::uint32_t(interval * 1000.0 + 0.5);
        player->m_Events.AddEventAtOffset([player, key, stamp, stomps, ms] { Stomp(player, key, stamp, stomps, ms); },
                                          std::chrono::milliseconds(ms));
    }

    void RegisterScripts()
    {
        // "A towering Earth Elemental rises at the target location. It is invulnerable and stays in place": the creature is the look; the
        // stomps are the Shaman's own strikes.
        Minions::Define(Group,
                        [](Player*)
                        {
                            Minions::Kind kind;
                            kind.group = Group;
                            kind.entry = Entry;
                            kind.record = BaseId();
                            kind.cap = 1;
                            kind.staysPut = true;
                            return kind;
                        });
    }
} // namespace DC::Combat::Shaman::EarthElemental
