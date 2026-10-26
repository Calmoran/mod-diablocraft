/*
 * Corpse Spiders and its five runes. The cast is the engine's ground throw (a spell record and the sheet's numbers:
 * free to cast, the jar's tiny impact, each rune's school); here: the spiders that bite the enemies near the jar for
 * their short lives, Blazing Spiders' Mana (the class's Connected seam, once a bite), Spider Queen's pulses, Leaping
 * Spiders' reach, Medusa Spiders' slow.
 */

#include "dc_witch_doctor_corpse_spiders.h"
#include "dc_witch_doctor_common.h"
#include "dc_witch_doctor_effects.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_spell_numbers.h"
#include "Player.h"
#include "Position.h"
#include "Random.h"
#include "Unit.h"

#include <chrono>
#include <mutex>
#include <unordered_map>

namespace DC::Combat::WitchDoctor::CorpseSpiders
{
    namespace
    {
        constexpr std::string_view Skill = "Corpse Spiders";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        // The queen each Witch Doctor has out, by the stamp of the throw: "You may have one spider queen summoned at a
        // time", so a later throw takes the place of an earlier and the earlier one's pulses find their stamp gone.
        std::mutex mutex;
        std::unordered_map<std::uint64_t, std::uint64_t> queens;
        std::uint64_t stamps = 0;

        // Work that comes due `ms` after the throw, on the player's own queue, if the Witch Doctor is still there.
        template<typename Work>
        void After(Player* player, std::uint32_t ms, Work work)
        {
            player->m_Events.AddEventAtOffset(
                [player, work]
                {
                    if (player->IsAlive() && player->IsInWorld())
                        work();
                },
                std::chrono::milliseconds(ms));
        }

        // One bite: at a random enemy within `reach` of the jar, its share of the rune's damage; Medusa Spiders' slow
        // with it; Blazing Spiders' Mana is the class's Connected seam.
        void Bite(Player* player, std::uint32_t spellId, Position const& jar, double reach, double pct)
        {
            auto const enemies = Combat::Enemies(player, spellId, jar, reach);
            if (enemies.empty())
                return;
            Unit* target = enemies[PickAt(frand(0.0f, 1.0f), enemies.size())];
            if (!Combat::Strike(player, target, spellId, pct))
                return;
            if (RuneAt(spellId) == Rune::MedusaSpiders &&
                Slows(frand(0.0f, 100.0f), Numbers::Num(spellId, "proc_chance_pct")))
                Slow(player, target, Numbers::Num(spellId, "slow_pct"), Tune("corpse_spiders_slow_seconds"));
            Combat::Connected(player, spellId, 1);
        }

        // The spiders: `spawn_count` of them, each biting `corpse_spiders_hits_per_spider` times inside its life.
        void Swarm(Player* player, std::uint32_t spellId, Position const& jar)
        {
            unsigned const spiders = unsigned(Numbers::Num(spellId, "spawn_count")),
                           bites = unsigned(Tune("corpse_spiders_hits_per_spider"));
            double const pct = BiteShare(Numbers::Num(spellId, "damage_pct"), spiders, bites);
            // Leaping Spiders "leap up to {radius_yards} yards to reach their enemy"; the rest stay where the jar
            // broke.
            double const reach = RuneAt(spellId) == Rune::LeapingSpiders ? Numbers::Num(spellId, "radius_yards")
                                                                         : Tune("corpse_spiders_reach_yards");
            for (unsigned spider = 0; spider < spiders; ++spider)
                for (unsigned bite = 0; bite < bites; ++bite)
                    After(player, BiteMs(bite, bites, Tune("corpse_spiders_lifetime_seconds")),
                          [=] { Bite(player, spellId, jar, reach, pct); });
        }

        // Spider Queen: a pulse on every enemy within her area every interval for the rune's seconds, an even share of
        // its total.
        void Queen(Player* player, std::uint32_t spellId, Position const& jar)
        {
            std::uint64_t stamp;
            {
                std::lock_guard<std::mutex> guard(mutex);
                stamp = ++stamps;
                queens[player->GetGUID().GetRawValue()] = stamp;
            }
            unsigned const pulses = PeriodicStrike::Ticks(Numbers::Num(spellId, "dot_duration_seconds"),
                                                          Tune("corpse_spiders_queen_pulse_seconds"));
            double const pct = PeriodicStrike::TickPct(Numbers::Num(spellId, "damage_pct"), pulses);
            for (unsigned pulse = 0; pulse < pulses; ++pulse)
                After(player, PulseMs(pulse, Tune("corpse_spiders_queen_pulse_seconds")),
                      [=]
                      {
                          {
                              std::lock_guard<std::mutex> guard(mutex);
                              auto const found = queens.find(player->GetGUID().GetRawValue());
                              if (found == queens.end() || found->second != stamp)
                                  return;
                          }
                          for (Unit* enemy :
                               Combat::Enemies(player, spellId, jar, Tune("corpse_spiders_queen_area_yards")))
                              Combat::Strike(player, enemy, spellId, pct, true);
                      });
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        return Is(spellId) ? std::optional<double>(Tune("corpse_spiders_impact_pct")) : std::nullopt;
    }

    void Ground(Player* player, std::uint32_t spellId, Position const& center)
    {
        if (!player || !Is(spellId))
            return;
        if (RuneAt(spellId) == Rune::SpiderQueen)
            Queen(player, spellId, center);
        else
            Swarm(player, spellId, center);
    }
} // namespace DC::Combat::WitchDoctor::CorpseSpiders
