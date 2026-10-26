/*
 * Zombie Charger and its five runes. The skill is the engine's line throw (a spell record and the sheet's numbers) that
 * hits every enemy along its path; here: Zombie Bears' bears, Lumbering Cold's zombies in every direction and their
 * slow, Pile On's tower that falls on a place, Undeath's reanimation and Explosive Beast's explosion. The shapes are
 * the power file's: a zombie is a path of the file's length, and what stands on it takes the rune's hit.
 */

#include "dc_witch_doctor_zombie_charger.h"
#include "dc_witch_doctor_common.h"
#include "dc_witch_doctor_effects.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_spell_numbers.h"
#include "Player.h"
#include "Position.h"
#include "Unit.h"

#include <algorithm>
#include <cmath>

namespace DC::Combat::WitchDoctor::ZombieCharger
{
    namespace
    {
        constexpr std::string_view Skill = "Zombie Charger";

        // The reanimated zombies' strikes land through the engine's hooks too; they reanimate nothing of their own.
        thread_local bool reanimating = false;

        // Holds a flag set for as long as it lives.
        struct Holding
        {
            explicit Holding(bool& flag) : flag_(flag)
            {
                flag_ = true;
            }
            ~Holding()
            {
                flag_ = false;
            }
            Holding(Holding const&) = delete;
            Holding& operator=(Holding const&) = delete;
            bool& flag_;
        };

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        // The enemy a cast is aimed at within `range`: the one the player has selected, else the nearest the cast
        // reached, else the nearest enemy at all; nullptr when there is none.
        Unit* AimedAt(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets, double range)
        {
            auto const near = Combat::Enemies(player, spellId, player->GetPosition(), range);
            if (Unit* selected = player->GetSelectedUnit();
                selected && std::find(near.begin(), near.end(), selected) != near.end())
                return selected;
            Unit* aimed = nullptr;
            for (Unit* enemy : targets.empty() ? near : targets)
                if (!aimed || player->GetExactDist(enemy) < player->GetExactDist(aimed))
                    aimed = enemy;
            return aimed;
        }

        // Every enemy on the path of a zombie that starts at (`x`, `y`) and runs `length` yards along `heading`, hit
        // for `pct`. Returns the enemies struck.
        std::vector<Unit*> RunPath(Player* player, std::uint32_t spellId, double x, double y, double heading,
                                   double length, double pct)
        {
            std::vector<Unit*> struck;
            Position const here(float(x), float(y), player->GetPositionZ());
            for (Unit* enemy : Combat::Enemies(player, spellId, here, length + Tune("zombie_charger_path_width_yards")))
                if (OnPath(enemy->GetPositionX() - x, enemy->GetPositionY() - y, heading, length,
                           Tune("zombie_charger_path_width_yards")) &&
                    Combat::Strike(player, enemy, spellId, pct))
                    struck.push_back(enemy);
            return struck;
        }

        // Undeath: a zombie that killed charges on from where the enemy fell, at the nearest enemy within the file's
        // search range, for the rune's damage; and if it kills again it repeats, up to the rune's most.
        void Reanimate(Player* player, std::uint32_t spellId, Position const& fell, unsigned depth)
        {
            if (!Reanimates(true, depth, unsigned(Numbers::Num(spellId, "max_count"))))
                return;
            auto const enemies = Combat::Enemies(player, spellId, fell, Tune("zombie_charger_undeath_search_yards"));
            std::vector<double> distances;
            for (Unit* enemy : enemies)
                distances.push_back(enemy->GetExactDist(&fell));
            auto const nearest = NearestWithin(distances, Tune("zombie_charger_undeath_search_yards"));
            if (!nearest)
                return;
            double const heading = std::atan2(enemies[*nearest]->GetPositionY() - fell.GetPositionY(),
                                              enemies[*nearest]->GetPositionX() - fell.GetPositionX());
            bool killed = false;
            Position next = fell;
            for (Unit* enemy : RunPath(player, spellId, fell.GetPositionX(), fell.GetPositionY(), heading,
                                       Tune("zombie_charger_undeath_path_yards"), Numbers::Num(spellId, "damage_pct")))
                if (!enemy->IsAlive())
                {
                    killed = true;
                    next = enemy->GetPosition();
                }
            if (killed)
                Reanimate(player, spellId, next, depth + 1);
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        if (!Is(spellId))
            return std::nullopt;
        // Undeath's first zombie hits for the skill's damage; its own number is the zombies it reanimates. Every other
        // rune strikes for itself (Cast), so the engine's line hits nothing.
        return RuneAt(spellId) == Rune::Undeath ? std::optional<double>(Numbers::Num(BaseId(Skill), "damage_pct"))
               : RuneAt(spellId) == Rune::None  ? std::nullopt
                                                : std::optional<double>(0.0);
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        Rune const rune = RuneAt(spellId);
        if (!player || rune == Rune::None || rune == Rune::Undeath)
            return;
        double const pct = Numbers::Num(spellId, "damage_pct");
        double const length = Tune("zombie_charger_path_yards");
        Unit* aimed =
            AimedAt(player, spellId, targets,
                    rune == Rune::ExplosiveBeast ? length + Tune("zombie_charger_beast_extra_yards") : length);
        double const aim = aimed ? player->GetAngle(aimed) : player->GetOrientation();
        double const x = player->GetPositionX(), y = player->GetPositionY();
        switch (rune)
        {
            case Rune::ZombieBears:
                // "Summon zombie bears that stampede towards your enemy. Each bear deals {damage_pct} weapon damage as
                // Poison to enemies in the area": the bears run side by side along the aim.
                for (double side : BearOffsets(unsigned(Tune("zombie_charger_bear_count")),
                                               Tune("zombie_charger_bear_spacing_yards")))
                    RunPath(player, spellId, x + std::cos(aim + M_PI / 2) * side, y + std::sin(aim + M_PI / 2) * side,
                            aim, Tune("zombie_charger_bear_yards"), pct);
                break;
            case Rune::LumberingCold:
                // "Zombie winter bears crawl out of the ground and run in all directions, dealing {damage_pct} weapon
                // damage as Cold": each enemy struck is slowed.
                for (double heading : RunningHeadings(unsigned(Tune("zombie_charger_cold_zombies")), aim))
                    for (Unit* enemy : RunPath(player, spellId, x, y, heading, length, pct))
                        Slow(player, enemy, Tune("zombie_charger_cold_slow_pct"),
                             Tune("zombie_charger_cold_slow_seconds"));
                break;
            case Rune::PileOn:
            {
                // "Summon a tower of zombies that falls over, dealing {damage_pct} weapon damage as Physical to any
                // enemies it hits": on the enemy aimed at within the file's reach, else the file's distance ahead.
                double const distance = TowerDistance(
                    aimed ? std::optional<double>(player->GetExactDist(aimed)) : std::nullopt,
                    Tune("zombie_charger_tower_reach_yards"), Tune("zombie_charger_tower_distance_yards"));
                Position const where(float(x + std::cos(aim) * distance), float(y + std::sin(aim) * distance),
                                     player->GetPositionZ());
                for (Unit* enemy : Combat::Enemies(player, spellId, where, Tune("zombie_charger_tower_radius_yards")))
                    Combat::Strike(player, enemy, spellId, pct);
                break;
            }
            case Rune::ExplosiveBeast:
                // "Summon an explosive Zombie Dog that streaks toward the enemy before exploding, dealing {damage_pct}
                // weapon damage as Fire to all enemies within {radius_yards} yards": where the enemy aimed at stands.
                if (aimed)
                    for (Unit* enemy :
                         Combat::Enemies(player, spellId, aimed->GetPosition(), Numbers::Num(spellId, "radius_yards")))
                        Combat::Strike(player, enemy, spellId, pct);
                break;
            default:
                break;
        }
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId)
    {
        if (reanimating || !player || !target || RuneAt(spellId) != Rune::Undeath || target->IsAlive())
            return;
        Holding holding(reanimating);
        Reanimate(player, spellId, target->GetPosition(), 0);
    }
} // namespace DC::Combat::WitchDoctor::ZombieCharger
