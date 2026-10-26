/*
 * Thunderstorm and its five runes. The skill is the engine's self-centred cast (a record and the sheet's numbers) that
 * strikes every enemy within its radius; here: the slow, the knockback, Gale Force's stun, Frost Storm's freeze,
 * Sandstorm's blind, Eye of the Storm's storm around the Shaman and Volcanic Gale's ring of fire.
 */

#include "dc_shaman_thunderstorm.h"
#include "dc_shaman_common.h"
#include "dc_shaman_effects.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_ground_device.h"
#include "../../combat/dc_movement_effects.h"

#include <chrono>
#include <mutex>

namespace DC::Combat::Shaman::Thunderstorm
{
    namespace
    {
        constexpr std::string_view Skill = "Thunderstorm";

        Shells::Ability const* RowOf(std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && Skill == row->skill ? row : nullptr;
        }

        // The skill's own record: the one that states the numbers its runes inherit.
        std::uint32_t BaseId()
        {
            for (auto const& row : Shells::Abilities)
                if (Skill == row.skill && !*row.rune)
                    return row.id;
            return 0;
        }

        std::uint32_t Millis(double seconds)
        {
            return std::uint32_t(seconds * 1000.0 + 0.5);
        }

        std::mutex mutex;
        Blind blind;

        // The storm around the Shaman: each tick strikes everything within `radius` of where the Shaman stands now.
        void Storm(Player* player, std::uint32_t spellId, unsigned left, double pct, double radius, double tickSeconds)
        {
            if (!left || !player->IsAlive() || !player->IsInWorld())
                return;
            Combat::StrikeArea(player, spellId, player->GetPosition(), radius, pct, true);
            player->m_Events.AddEventAtOffset([player, spellId, left, pct, radius, tickSeconds]
                                              { Storm(player, spellId, left - 1, pct, radius, tickSeconds); },
                                              std::chrono::milliseconds(Millis(tickSeconds)));
        }

        // The ring of fire where the Shaman stood: a periodic device that strikes what stands in it for its seconds.
        void Ring(Player* player, std::uint32_t spellId, Position const& at)
        {
            double const seconds = Numbers::Num(spellId, "duration_seconds"),
                         tick = Tunable("thunderstorm_ring_tick_seconds");
            double const pct = TickPct(Numbers::Num(spellId, "damage_pct"), tick);
            GroundDevice::Setup ring;
            ring.kind = BaseId();
            ring.record = spellId;
            ring.spec.mode = GroundDevice::Mode::Periodic;
            ring.spec.radiusYards = Numbers::Num(spellId, "radius_yards");
            ring.spec.lifetimeMs = seconds * 1000.0;
            ring.spec.intervalMs = tick * 1000.0;
            ring.spec.most = 1;
            ring.fire = [spellId, pct](Player* owner, Position const&, std::vector<Unit*> const& enemies)
            {
                for (Unit* enemy : enemies)
                    Combat::Strike(owner, enemy, spellId, pct, true);
            };
            GroundDevice::Place(player, ring, at);
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        auto const* row = RowOf(spellId);
        if (!row)
            return std::nullopt;
        // Eye of the Storm's and Volcanic Gale's `damage_pct` is what their storm and ring deal each second; the
        // thunderclap itself still hits for the skill's.
        Rune const rune = RuneOf(row->rune);
        if (rune == Rune::EyeOfTheStorm || rune == Rune::VolcanicGale)
            return Numbers::Num(BaseId(), "damage_pct");
        return std::nullopt;
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        auto const* row = RowOf(spellId);
        if (!player || !row)
            return;
        Rune const rune = RuneOf(row->rune);
        // A stun or a freeze is stretched by the worn powers that lengthen stuns, as at every other class's stun site.
        double const stun = Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player);
        double const freeze = Numbers::Num(spellId, "freeze_duration_seconds") * ItemPowers::StunFactor(player);
        Hold const hold = HoldOf(rune, Tunable("thunderstorm_knockback_yards"),
                                 Tunable("thunderstorm_gale_force_knockback_factor"), stun, freeze);
        double const slowPct = Numbers::Num(spellId, "slow_pct"),
                     slowSeconds = Numbers::Num(spellId, "slow_duration_seconds");
        double const blindSeconds = Numbers::Num(spellId, "blind_duration_seconds"),
                     missPct = Numbers::Num(spellId, "miss_chance_pct");
        for (Unit* enemy : targets)
        {
            if (!enemy->IsAlive())
                continue;
            Shaman::Slow(player, enemy, slowPct, slowSeconds);
            if (hold.knockYards > 0)
                Abilities::Knock(player, enemy, hold.knockYards);
            Shaman::Stun(player, enemy, hold.stunSeconds);
            Shaman::Freeze(player, enemy, hold.freezeSeconds);
            if (Blinds(hold, IsElite(enemy)))
            {
                std::lock_guard<std::mutex> guard(mutex);
                blind.Set(enemy->GetGUID().GetRawValue(), Now(), Now() + std::uint64_t(blindSeconds * 1000.0), missPct);
            }
        }
        if (rune == Rune::EyeOfTheStorm)
        {
            double const tick = Tunable("thunderstorm_storm_tick_seconds");
            unsigned const ticks = Ticks(Numbers::Num(spellId, "duration_seconds"), tick);
            double const pct = TickPct(Numbers::Num(spellId, "damage_pct"), tick), radius = Numbers::Num(spellId, "radius_yards");
            // The thunderclap is the cast's own hit; the storm's first tick is one tick later.
            player->m_Events.AddEventAtOffset([player, spellId, ticks, pct, radius, tick] { Storm(player, spellId, ticks, pct, radius, tick); },
                                              std::chrono::milliseconds(Millis(tick)));
        }
        else if (rune == Rune::VolcanicGale)
            Ring(player, spellId, player->GetPosition());
    }

    double MissChance(Unit const* attacker)
    {
        if (!attacker)
            return 0.0;
        std::lock_guard<std::mutex> guard(mutex);
        return blind.Chance(attacker->GetGUID().GetRawValue(), Now());
    }
} // namespace DC::Combat::Shaman::Thunderstorm
