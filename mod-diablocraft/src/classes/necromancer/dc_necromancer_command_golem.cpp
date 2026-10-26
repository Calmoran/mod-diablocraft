/*
 * Command Golem and its five runes. The cast commands the Golem to the place aimed at. The skill and Flesh Golem collapse it
 * into corpses there and it comes back after the power's seconds. Bone Golem is a tornado that carries the enemies near it
 * to the place, pulsing on the way and where it stops, and stuns them; Blood Golem is sacrificed for a heal and rebuilt at
 * the place with veins that strike the enemies around it and a knockback as it forms; Decay Golem eats the corpses there for a
 * timed damage boost and grows with them; Ice Golem freezes the enemies around the place and makes them likelier to be crit.
 */

#include "dc_necromancer_command_golem.h"
#include "dc_necromancer_command_golem_math.h"
#include "dc_necromancer_common.h"
#include "../../combat/dc_corpses.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_minions.h"

#include "Creature.h"
#include "GameTime.h"
#include "ObjectAccessor.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <mutex>
#include <unordered_map>

namespace DC::Combat::Necromancer::CommandGolem
{
    namespace
    {
        constexpr std::string_view Skill = "Command Golem";
        // The creature of necromancer_summons.csv a pile of corpses is left as.
        constexpr std::uint32_t GolemEntry = 900152;

        double Tune(char const* name)
        {
            return DC::Tunables::Get("necromancer", name);
        }

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        std::uint32_t Millis(double seconds)
        {
            return seconds > 0 ? std::uint32_t(seconds * 1000.0 + 0.5) : 0;
        }

        Creature* Golem(Player* player)
        {
            auto const golems = Minions::Standing(player, "golem");
            return golems.empty() ? nullptr : golems.front();
        }

        // Runs `act` on the player `seconds` from now.
        template <class Act>
        void After(Player* player, double seconds, Act act)
        {
            if (seconds <= 0)
                act();
            else
                player->m_Events.AddEventAtOffset(std::move(act), std::chrono::milliseconds(Millis(seconds)));
        }

        // The enemies Ice Golem froze: each is likelier to be crit until its mark ends.
        struct Mark
        {
            double pct = 0;
            std::uint64_t until = 0;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, std::unordered_map<std::uint64_t, Mark>> marks;
        // The meal each grown Golem's size is held for (a second meal takes the next number, and the first meal's event gives
        // nothing back).
        std::unordered_map<std::uint64_t, std::uint64_t> grownAs;
        std::uint64_t meals = 0;

        // The enemies within `radius` yards of `at`, struck for `pct` by the spell.
        unsigned Pulse(Player* player, std::uint32_t spellId, Position const& at, double radius, double pct)
        {
            unsigned hit = 0;
            for (Unit* enemy : Combat::Enemies(player, spellId, at, radius))
                if (enemy->IsAlive() && Combat::Strike(player, enemy, spellId, pct))
                    ++hit;
            return hit;
        }

        // "collapses into a pile of {target_count} corpses": at the place, and the Golem is gone until it returns.
        void Collapse(Player* player, std::uint32_t spellId, Position const& center)
        {
            unsigned const corpses = unsigned(Numbers::Num(spellId, "target_count"));
            for (unsigned i = 0; i < corpses; ++i)
                Corpses::LeaveMade(player, center, GolemEntry, GolemEntry);
            Minions::Dismiss(player, "golem", Millis(Tune("minion_golem_return_seconds")));
        }

        // Bone Golem: the tornado carries the enemies near the Golem to the place, pulsing on the way, then stops and stuns
        // them and pulses where it stands; the Golem is whole again at the place.
        void Tornado(Player* player, std::uint32_t spellId, Creature* golem, Position const& center)
        {
            Position const start = golem->GetPosition();
            double const radius = Tune("bone_golem_pulse_radius_yards");
            double const travel = TravelSeconds(start.GetExactDist2d(center), golem->GetSpeed(MOVE_RUN),
                                                Tune("bone_golem_move_speed_scalar"));
            double const stun = Tune("bone_golem_stun_seconds");
            double const destInterval = Tune("bone_golem_dest_pulse_seconds");
            std::vector<ObjectGuid> carried;
            for (Unit* enemy : Combat::Enemies(player, spellId, start, radius))
                carried.push_back(enemy->GetGUID());
            Minions::Dismiss(player, "golem", Millis(travel + stun) + 1000);
            double const step = Tune("bone_golem_move_pulse_seconds");
            for (unsigned i = 1; i <= Pulses(travel, step); ++i)
                After(player, i * step,
                      [player, spellId, start, center, i, step, travel, radius]
                      {
                          Position const at(float(Along(start.GetPositionX(), center.GetPositionX(), i * step / travel)),
                                            float(Along(start.GetPositionY(), center.GetPositionY(), i * step / travel)),
                                            float(Along(start.GetPositionZ(), center.GetPositionZ(), i * step / travel)));
                          Pulse(player, spellId, at, radius, Tune("bone_golem_move_pulse_pct"));
                      });
            After(player, travel,
                  [player, spellId, center, carried, stun, radius]
                  {
                      for (ObjectGuid guid : carried)
                          if (Unit* enemy = ObjectAccessor::GetUnit(*player, guid); enemy && enemy->IsAlive())
                              enemy->NearTeleportTo(center.GetPositionX(), center.GetPositionY(), center.GetPositionZ(),
                                                    enemy->GetOrientation());
                      Minions::Raise(player, "command_golem", center);
                      for (Unit* enemy : Combat::Enemies(player, spellId, center, radius))
                          Stun(player, enemy, stun * ItemPowers::StunFactor(player));
                  });
            for (unsigned j = 1; j <= Pulses(stun, destInterval); ++j)
                After(player, travel + j * destInterval,
                      [player, spellId, center, radius] { Pulse(player, spellId, center, radius, Tune("bone_golem_dest_pulse_pct")); });
        }

        // Blood Golem: as the Golem forms, the enemies within the power's knockback radius of the place are pushed out to its edge.
        void Knockback(Player* player, std::uint32_t spellId, Position const& center)
        {
            double const radius = Tune("blood_golem_knockback_yards");
            for (Unit* enemy : Combat::Enemies(player, spellId, center, radius))
            {
                double dx = enemy->GetPositionX() - center.GetPositionX(), dy = enemy->GetPositionY() - center.GetPositionY();
                double distance = std::sqrt(dx * dx + dy * dy);
                if (distance < 0.01)
                {
                    dx = std::cos(enemy->GetOrientation());
                    dy = std::sin(enemy->GetOrientation());
                    distance = 1.0;
                }
                double const share = PushedTo(distance, radius) / distance;
                enemy->NearTeleportTo(float(center.GetPositionX() + dx * share), float(center.GetPositionY() + dy * share),
                                      enemy->GetPositionZ(), enemy->GetOrientation());
            }
        }

        // Blood Golem: sacrificed for a heal, rebuilt at the place; its veins strike the nearest enemies around the place, one
        // after another, each for the vein's blow and then the rip.
        void Sacrifice(Player* player, std::uint32_t spellId, Position const& center)
        {
            double const vein = Tune("blood_golem_vein_seconds");
            Minions::Dismiss(player, "golem", Millis(vein) + 1000);
            After(player, Tune("blood_golem_heal_delay_seconds"),
                  [player, spellId]
                  {
                      if (player->IsAlive())
                          Heal(player, spellId, player->GetMaxHealth() * Numbers::Num(spellId, "heal_pct") / 100.0);
                  });
            auto enemies = Combat::Enemies(player, spellId, center, Tune("blood_golem_vein_radius_yards"));
            std::stable_sort(enemies.begin(), enemies.end(),
                             [&center](Unit* a, Unit* b) { return a->GetExactDist(&center) < b->GetExactDist(&center); });
            if (enemies.size() > std::size_t(Tune("blood_golem_vein_targets")))
                enemies.resize(std::size_t(Tune("blood_golem_vein_targets")));
            unsigned index = 0;
            for (Unit* enemy : enemies)
            {
                double const at = VeinAt(index++, Tune("blood_golem_vein_gap_seconds"));
                for (auto const& [delay, pct] : {std::pair<double, double>{at, Tune("blood_golem_vein_pct")},
                                                 std::pair<double, double>{at + vein, Tune("blood_golem_rip_pct")}})
                    After(player, delay,
                          [player, spellId, guid = enemy->GetGUID(), pct = pct]
                          {
                              if (Unit* target = ObjectAccessor::GetUnit(*player, guid); target && target->IsAlive())
                                  Combat::Strike(player, target, spellId, pct);
                          });
            }
            After(player, vein,
                  [player, spellId, center]
                  {
                      Knockback(player, spellId, center);
                      Minions::Raise(player, "command_golem", center);
                  });
        }

        // Decay Golem: the Golem goes to the place and eats the corpses lying there; each makes its blows hit harder for a time.
        void Feed(Player* player, std::uint32_t spellId, Creature* golem, Position const& center)
        {
            golem->NearTeleportTo(center.GetPositionX(), center.GetPositionY(), center.GetPositionZ(), golem->GetOrientation());
            auto const eaten = Corpses::Consume(player, center, float(Tune("decay_golem_corpse_radius_yards")),
                                                std::size_t(Tune("decay_golem_max_corpses")));
            if (eaten.empty())
                return;
            unsigned const most = unsigned(Tune("decay_golem_max_corpses"));
            std::uint32_t const ms = Millis(Tune("decay_golem_buff_seconds"));
            Minions::Boost(player, "golem", CorpseBonusPct(unsigned(eaten.size()), Numbers::Num(spellId, "damage_bonus_pct"), most), ms);
            // It grows with its meal for as long as the boost lasts (the power's Max Scale Bonus), and is its own size again after.
            golem->SetObjectScale(golem->GetNativeObjectScale() *
                                  float(1.0 + ScaleBonusPct(unsigned(eaten.size()), most, Tune("decay_golem_max_scale_pct")) / 100.0));
            ObjectGuid const guid = golem->GetGUID();
            std::uint64_t meal;
            {
                std::lock_guard<std::mutex> guard(mutex);
                meal = meals = NextMeal(meals);
                grownAs[guid.GetRawValue()] = meal;
            }
            After(player, Tune("decay_golem_buff_seconds"),
                  [player, guid, meal]
                  {
                      {
                          std::lock_guard<std::mutex> guard(mutex);
                          auto const found = grownAs.find(guid.GetRawValue());
                          if (found == grownAs.end() || !ResetDue(found->second, meal))
                              return;
                          grownAs.erase(found);
                      }
                      if (Creature* golem = ObjectAccessor::GetCreature(*player, guid))
                          golem->SetObjectScale(golem->GetNativeObjectScale());
                  });
        }

        // Ice Golem: the enemies around the place are frozen, and likelier to be crit for a time.
        void Freeze(Player* player, std::uint32_t spellId, Position const& center)
        {
            double const seconds = Numbers::Num(spellId, "duration_seconds");
            for (Unit* enemy : Combat::Enemies(player, spellId, center, Tune("ice_golem_radius_yards")))
            {
                Stun(player, enemy, Numbers::Num(spellId, "freeze_duration_seconds") * ItemPowers::StunFactor(player));
                std::lock_guard<std::mutex> guard(mutex);
                marks[player->GetGUID().GetRawValue()][enemy->GetGUID().GetRawValue()] = {
                    Numbers::Num(spellId, "crit_taken_pct"), Now() + Millis(seconds)};
            }
        }
    } // namespace

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) ? std::optional<double>(0.0) : std::nullopt;
    }

    SpellCastResult CanCast(Player* player, std::uint32_t spellId, Position const* aim)
    {
        if (!RowOf(spellId, Skill))
            return SPELL_CAST_OK;
        return player && aim && Golem(player) ? SPELL_CAST_OK : SPELL_FAILED_NO_VALID_TARGETS;
    }

    void Ground(Player* player, std::uint32_t spellId, Position const& center)
    {
        if (!player || !RowOf(spellId, Skill))
            return;
        Creature* golem = Golem(player);
        if (!golem)
            return;
        switch (RuneAt(spellId))
        {
            case Rune::BoneGolem:
                Tornado(player, spellId, golem, center);
                break;
            case Rune::BloodGolem:
                Sacrifice(player, spellId, center);
                break;
            case Rune::DecayGolem:
                Feed(player, spellId, golem, center);
                break;
            case Rune::IceGolem:
                Freeze(player, spellId, center);
                break;
            default:
                Collapse(player, spellId, center);
                break;
        }
    }

    double CritBonus(Player* player, Unit* target)
    {
        if (!player || !target)
            return 0.0;
        std::lock_guard<std::mutex> guard(mutex);
        auto const owner = marks.find(player->GetGUID().GetRawValue());
        if (owner == marks.end())
            return 0.0;
        auto const found = owner->second.find(target->GetGUID().GetRawValue());
        return found != owner->second.end() && Now() < found->second.until ? found->second.pct : 0.0;
    }
} // namespace DC::Combat::Necromancer::CommandGolem
