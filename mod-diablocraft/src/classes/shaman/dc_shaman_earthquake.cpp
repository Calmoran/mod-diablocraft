/*
 * The Shaman's Earthquake and its five runes: the area that strikes what stands in it each tick for its seconds, the
 * knock down a tick may give, Aftershock's eruption when it ends, Rolling Quake moving with the Shaman, Magma Chamber's
 * bonus to Lava Burst, Frozen Tundra's chill and freeze and Thundering Earth's strikes on a few enemies. The cast is
 * the engine's ground spell and deals nothing at once (the record states a duration); the Maelstrom it costs is the
 * core's. The dispatch is in dc_shaman.cpp.
 */

#include "dc_shaman_earthquake.h"
#include "dc_shaman_chill.h"
#include "dc_shaman_common.h"
#include "dc_shaman_effects.h"
#include "../../combat/dc_combat.h"
#include "Map.h"
#include "Random.h"
#include "Unit.h"

#include <chrono>
#include <mutex>
#include <unordered_map>
#include <vector>

namespace DC::Combat::Shaman::Earthquake
{
    namespace
    {
        constexpr std::string_view Skill = "Earthquake (Shaman)";

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

        // The one Earthquake a Shaman has: where it is, how big, and the stamp its ticks answer to (a new cast takes a
        // new stamp and the old ticks find theirs gone and stop).
        struct Quake
        {
            std::uint64_t stamp = 0;
            std::uint32_t spellId = 0;
            Rune rune = Rune::None;
            float x = 0, y = 0;
            double radius = 0;
            std::uint64_t lastFreeze = 0;
            Map const* map = nullptr;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, Quake> quakes; // by the Shaman
        std::uint64_t stamps = 0;

        // Where the area is now: the Shaman's own place for Rolling Quake, where it was cast for the rest.
        void Centre(Player* player, Quake const& quake, float& x, float& y)
        {
            if (Follows(quake.rune))
            {
                x = player->GetPositionX();
                y = player->GetPositionY();
                return;
            }
            x = quake.x;
            y = quake.y;
        }

        // "Aftershock: When Earthquake ends, the ground erupts for {damage_pct} weapon damage as Physical."
        void Erupt(Player* player, Quake const& quake)
        {
            float x, y;
            Centre(player, quake, x, y);
            Position at = player->GetPosition();
            at.Relocate(x, y);
            for (Unit* enemy : Combat::Enemies(player, quake.spellId, at, quake.radius))
                Combat::Strike(player, enemy, quake.spellId, Numbers::Num(quake.spellId, "damage_pct"));
        }

        void Tick(Player* player, std::uint64_t key, std::uint64_t stamp, unsigned left, double pct,
                  std::uint32_t intervalMs)
        {
            Quake quake;
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto found = quakes.find(key);
                if (found == quakes.end() || found->second.stamp != stamp)
                    return;
                quake = found->second;
            }
            // The Shaman is gone, dead or on another floor: the area ends with nothing more.
            if (!player->IsInWorld() || !player->IsAlive() || player->GetMap() != quake.map)
            {
                std::lock_guard<std::mutex> guard(mutex);
                if (auto found = quakes.find(key); found != quakes.end() && found->second.stamp == stamp)
                    quakes.erase(found);
                return;
            }
            float x, y;
            Centre(player, quake, x, y);
            Position at = player->GetPosition();
            at.Relocate(x, y);
            std::vector<Unit*> inside = Combat::Enemies(player, quake.spellId, at, quake.radius);
            // Thundering Earth: "Lightning bolts strike random enemies inside the area ... focused on fewer targets."
            std::size_t const struck =
                Struck(quake.rune, inside.size(), std::size_t(Tune("earthquake_thundering_strikes_per_tick")));
            for (std::size_t picked = 0; picked < struck; ++picked)
            {
                std::size_t const pick =
                    picked + (inside.size() - picked > 1 ? urand(0, uint32(inside.size() - picked - 1)) : 0);
                std::swap(inside[picked], inside[pick]);
            }
            inside.resize(struck);
            bool const freeze = quake.rune == Rune::FrozenTundra &&
                                FreezeDue(Now(), quake.lastFreeze, Numbers::Num(quake.spellId, "interval_seconds"));
            for (Unit* enemy : inside)
            {
                Combat::Strike(player, enemy, quake.spellId, pct, true);
                if (!enemy->IsAlive())
                    continue;
                // "Each tick has a {proc_chance_pct} chance to Knock Down enemies for {duration_seconds} second."
                if (frand(0.0f, 100.0f) < Numbers::Num(quake.spellId, "proc_chance_pct"))
                    Stun(player, enemy, Numbers::Num(quake.spellId, "duration_seconds"));
                if (quake.rune == Rune::FrozenTundra)
                {
                    // "Enemies inside are Chilled by {chill_pct} and are Frozen for {freeze_duration_seconds} second
                    // every {interval_seconds} seconds."
                    Chill(player, enemy, Numbers::Num(quake.spellId, "chill_pct"), ChillSeconds(intervalMs / 1000.0));
                    if (freeze)
                        Freeze(player, enemy, Numbers::Num(quake.spellId, "freeze_duration_seconds"));
                }
            }
            if (freeze)
            {
                std::lock_guard<std::mutex> guard(mutex);
                if (auto found = quakes.find(key); found != quakes.end() && found->second.stamp == stamp)
                    found->second.lastFreeze = Now();
            }
            if (left > 1)
            {
                player->m_Events.AddEventAtOffset([player, key, stamp, left, pct, intervalMs]
                                                  { Tick(player, key, stamp, left - 1, pct, intervalMs); },
                                                  std::chrono::milliseconds(intervalMs));
                return;
            }
            if (quake.rune == Rune::Aftershock)
                Erupt(player, quake);
            std::lock_guard<std::mutex> guard(mutex);
            if (auto found = quakes.find(key); found != quakes.end() && found->second.stamp == stamp)
                quakes.erase(found);
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
        double const tick = Tune("earthquake_tick_seconds"), seconds = Numbers::Num(spellId, "dot_duration_seconds");
        unsigned const ticks = PeriodicStrike::Ticks(seconds, tick);
        if (!ticks)
            return;
        // "Deals {damage_pct} weapon damage as Physical over {dot_duration_seconds} seconds": the skill's number for
        // the ticks, Thundering Earth's own for its strikes.
        double const pct =
            PeriodicStrike::TickPct(Numbers::Num(OwnsTickDamage(rune) ? spellId : BaseId(), "damage_pct"), ticks);
        std::uint64_t const key = player->GetGUID().GetRawValue();
        std::uint64_t stamp;
        {
            std::lock_guard<std::mutex> guard(mutex);
            // "Only one Earthquake can be active at a time; casting another moves it and refreshes the duration."
            Quake& quake = quakes[key];
            stamp = quake.stamp = ++stamps;
            quake.spellId = spellId;
            quake.rune = rune;
            quake.x = center.GetPositionX();
            quake.y = center.GetPositionY();
            quake.radius = Numbers::Num(spellId, "radius_yards");
            quake.lastFreeze = 0;
            quake.map = player->GetMap();
        }
        auto const interval = std::uint32_t(tick * 1000.0 + 0.5);
        player->m_Events.AddEventAtOffset([player, key, stamp, ticks, pct, interval]
                                          { Tick(player, key, stamp, ticks, pct, interval); },
                                          std::chrono::milliseconds(interval));
    }

    bool Inside(Player* player, Unit const* target)
    {
        if (!player || !target)
            return false;
        std::lock_guard<std::mutex> guard(mutex);
        auto found = quakes.find(player->GetGUID().GetRawValue());
        if (found == quakes.end() || found->second.map != target->GetMap())
            return false;
        float x, y;
        Centre(player, found->second, x, y);
        return Earthquake::Inside(x, y, target->GetPositionX(), target->GetPositionY(), found->second.radius);
    }

    void Multipliers(Player* player, Unit* target, std::uint32_t spellId, DC::Combat::Factors& out)
    {
        auto const* row = Shells::FindAbility(spellId);
        if (!player || !target || !row || std::string_view(row->skill) != "Lava Burst")
            return;
        Rune rune = Rune::None;
        std::uint32_t id = 0;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = quakes.find(player->GetGUID().GetRawValue());
            if (found == quakes.end())
                return;
            rune = found->second.rune;
            id = found->second.spellId;
        }
        // "Magma Chamber: Enemies inside take {damage_taken_pct} more damage from Lava Burst."
        if (double const bonus = MagmaBonus(rune, Inside(player, target), Numbers::Num(id, "damage_taken_pct")))
            AddFactor(out, "Magma Chamber", bonus);
    }
} // namespace DC::Combat::Shaman::Earthquake
