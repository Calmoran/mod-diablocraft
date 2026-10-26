/*
 * Grasp of the Dead and its five runes. The cast is the engine's ground cast (a spell record and the sheet's numbers:
 * the Mana cost, the cooldown, Unbreakable Grasp's free cast, Desperate Grasp's shorter cooldown, each rune's school);
 * here: the hands' pulses that hurt and slow every enemy in their area, Rain of Corpses' corpses, and Death Is Life's
 * Zombie Dog for an enemy that dies in the area.
 */

#include "dc_witch_doctor_grasp_of_the_dead.h"
#include "dc_witch_doctor_common.h"
#include "dc_witch_doctor_effects.h"
#include "dc_witch_doctor_pets.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_spell_numbers.h"
#include "Creature.h"
#include "GameTime.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Position.h"
#include "Random.h"
#include "ScriptMgr.h"
#include "Unit.h"

#include <chrono>
#include <functional>
#include <mutex>
#include <unordered_map>
#include <utility>
#include <vector>

namespace DC::Combat::WitchDoctor::GraspOfTheDead
{
    namespace
    {
        constexpr std::string_view Skill = "Grasp of the Dead";

        // Death Is Life's area: where the hands rose, the record that cast them and until when they catch a death.
        struct Area
        {
            std::uint32_t spellId = 0;
            std::uint32_t map = 0, instance = 0;
            float x = 0, y = 0;
            double radius = 0;
            std::uint64_t until = 0;
        };

        std::mutex mutex;
        std::unordered_map<std::uint64_t, std::vector<Area>> areas; // by Witch Doctor, one for each cast still on

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        // Work that comes due `ms` after the cast, on the player's own queue, if the Witch Doctor is still there.
        void After(Player* player, std::uint32_t ms, std::function<void()> work)
        {
            player->m_Events.AddEventAtOffset(
                [player, work = std::move(work)]
                {
                    if (player->IsAlive() && player->IsInWorld())
                        work();
                },
                std::chrono::milliseconds(ms));
        }

        // The hands: "slowing enemy movement by {slow_pct} and dealing {damage_pct} weapon damage as Physical over
        // {dot_duration_seconds} seconds": every pulse each enemy within the area takes an even share and is slowed
        // again.
        void Hands(Player* player, std::uint32_t spellId, Position const& center)
        {
            unsigned const pulses = PeriodicStrike::Ticks(Numbers::Num(BaseId(Skill), "dot_duration_seconds"),
                                                          Tune("grasp_of_the_dead_pulse_seconds"));
            // Rain of Corpses states its corpses' damage as its own: the hands deal the skill's.
            double const total = RuneAt(spellId) == Rune::RainOfCorpses ? Numbers::Num(BaseId(Skill), "damage_pct") : Numbers::Num(spellId, "damage_pct");
            double const pct = PeriodicStrike::TickPct(total, pulses);
            double const slow =
                SlowSeconds(Tune("grasp_of_the_dead_pulse_seconds"), Tune("grasp_of_the_dead_slow_extra_seconds"));
            for (unsigned pulse = 0; pulse < pulses; ++pulse)
                After(player, PulseMs(pulse, Tune("grasp_of_the_dead_pulse_seconds")),
                      [=]
                      {
                          for (Unit* enemy :
                               Combat::Enemies(player, spellId, center, Tune("grasp_of_the_dead_radius_yards")))
                          {
                              Combat::Strike(player, enemy, spellId, pct, true);
                              Slow(player, enemy, Numbers::Num(spellId, "slow_pct"), slow);
                          }
                      });
        }

        // Rain of Corpses: "Corpses also fall from the sky, dealing {damage_pct} weapon damage over
        // {dot_duration_seconds} seconds to nearby enemies": a corpse every corpse tick on a random enemy within the
        // file's search radius, striking all within its attack radius.
        void Corpses(Player* player, std::uint32_t spellId, Position const& center)
        {
            unsigned const falls = PeriodicStrike::Ticks(Numbers::Num(spellId, "dot_duration_seconds"),
                                                         Tune("grasp_of_the_dead_corpse_seconds"));
            double const pct = PeriodicStrike::TickPct(Numbers::Num(spellId, "damage_pct"), falls);
            for (unsigned fall = 0; fall < falls; ++fall)
                After(player, PulseMs(fall, Tune("grasp_of_the_dead_corpse_seconds")),
                      [=]
                      {
                          auto const enemies =
                              Combat::Enemies(player, spellId, center, Tune("grasp_of_the_dead_corpse_search_yards"));
                          if (enemies.empty())
                              return;
                          Position const where = enemies[PickAt(frand(0.0f, 1.0f), enemies.size())]->GetPosition();
                          for (Unit* enemy :
                               Combat::Enemies(player, spellId, where, Tune("grasp_of_the_dead_corpse_radius_yards")))
                              Combat::Strike(player, enemy, spellId, pct, true);
                      });
        }

        // Death Is Life: "Enemies who die while in the area of Grasp of the Dead have a {proc_chance_pct} chance to
        // summon a Zombie Dog": every cast whose hands still stand where an enemy died rolls once.
        class Deaths final : public UnitScript
        {
        public:
            Deaths()
                : UnitScript("dc_witch_doctor_death_is_life", true, {UNITHOOK_ON_UNIT_DEATH})
            {
            }

            void OnUnitDeath(Unit* victim, Unit*) override
            {
                Creature* creature = victim ? victim->ToCreature() : nullptr;
                if (!creature || creature->IsControlledByPlayer())
                    return;
                std::vector<std::pair<ObjectGuid, std::uint32_t>> casts;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    std::uint64_t const now = Now();
                    for (auto owner = areas.begin(); owner != areas.end();)
                    {
                        std::erase_if(owner->second, [now](Area const& area) { return now >= area.until; });
                        if (owner->second.empty())
                        {
                            owner = areas.erase(owner);
                            continue;
                        }
                        for (Area const& area : owner->second)
                            if (creature->GetMapId() == area.map && creature->GetInstanceId() == area.instance &&
                                InArea(now, area.until, creature->GetExactDist2d(area.x, area.y), area.radius))
                                casts.emplace_back(ObjectGuid(owner->first), area.spellId);
                        ++owner;
                    }
                }
                Position const at = creature->GetPosition();
                for (auto const& [guid, spellId] : casts)
                {
                    Player* witchDoctor = ObjectAccessor::FindPlayer(guid);
                    if (!witchDoctor || creature->IsFriendlyTo(witchDoctor) ||
                        !Rises(frand(0.0f, 100.0f), Numbers::Num(spellId, "proc_chance_pct")))
                        continue;
                    // Not inside the kill: the dog rises a moment after, on the Witch Doctor's own queue, when it has room.
                    witchDoctor->m_Events.AddEventAtOffset([witchDoctor, at] { Pets::RaiseDogAt(witchDoctor, at); },
                                                           std::chrono::milliseconds(100));
                }
            }
        };

        // The hands rose at `center`: Death Is Life's area stands for the hands' seconds and the slow's extra.
        void Watch(Player* player, std::uint32_t spellId, Position const& center)
        {
            Area area;
            area.spellId = spellId;
            area.map = player->GetMapId();
            area.instance = player->GetInstanceId();
            area.x = center.GetPositionX();
            area.y = center.GetPositionY();
            area.radius = Tune("grasp_of_the_dead_radius_yards");
            std::uint64_t const now = Now();
            area.until = now + AreaMs(Numbers::Num(BaseId(Skill), "dot_duration_seconds"),
                                      Tune("grasp_of_the_dead_slow_extra_seconds"));
            std::lock_guard<std::mutex> guard(mutex);
            std::vector<Area>& held = areas[player->GetGUID().GetRawValue()];
            std::erase_if(held, [now](Area const& old) { return now >= old.until; });
            held.push_back(area);
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        return Is(spellId) ? std::optional<double>(0.0) : std::nullopt;
    }

    void Ground(Player* player, std::uint32_t spellId, Position const& center)
    {
        if (!player || !Is(spellId))
            return;
        Hands(player, spellId, center);
        if (RuneAt(spellId) == Rune::RainOfCorpses)
            Corpses(player, spellId, center);
        if (RuneAt(spellId) == Rune::DeathIsLife)
            Watch(player, spellId, center);
    }

    void SpawnGlobe(Player* /*player*/, Position const& /*at*/) {}

    void RegisterScripts()
    {
        new Deaths();
    }
} // namespace DC::Combat::WitchDoctor::GraspOfTheDead
