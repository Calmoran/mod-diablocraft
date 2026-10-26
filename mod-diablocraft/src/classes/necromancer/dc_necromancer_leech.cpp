/*
 * Leech and its five runes. The cast curses every enemy within the power's radius of the place aimed at for the skill's seconds
 * (Cursed Ground curses the ground instead: a patch that heals every second for each enemy in it). A cursed enemy that is struck
 * heals the Necromancer; Osmosis adds life regeneration for the enemies cursed; when a cursed enemy dies, Transmittable spreads the
 * curse, Sanguine End heals with the Life per Kill and Blood Flask shortens the potion cooldown.
 */

#include "dc_necromancer_leech.h"
#include "dc_necromancer_leech_math.h"
#include "dc_necromancer_common.h"
#include "dc_necromancer_curses.h"
#include "dc_necromancer_passives.h"
#include "../dc_classes.h"
#include "../../combat/dc_healing_table.h"
#include "../../stats/dc_stats.h"

#include "ScriptMgr.h"

#include <chrono>
#include <cmath>

namespace DC::Combat::Necromancer::Leech
{
    namespace
    {
        constexpr std::string_view Skill = "Leech";

        double Tune(char const* name)
        {
            return DC::Tunables::Get("necromancer", name);
        }

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        std::uint32_t Millis(double seconds)
        {
            return seconds > 0 ? std::uint32_t(seconds * 1000.0 + 0.5) : 0;
        }

        // Osmosis: the Life per second for the enemies cursed, up to the rune's number of them, on the sheet (0 takes it off). One enemy
        // gives the power's share of the Healing table at the Necromancer's level (the tooltip's 751 is level 70).
        void Regen(Player* player, std::uint32_t spellId, unsigned cursed)
        {
            double const perEnemy = OsmosisPerEnemy(Tune("osmosis_healing_share"), Healing::At(player->GetLevel()));
            Buffs::Set(player, spellId, Stat::LifeRegen, Bucket::Flat,
                       OsmosisRegen(cursed, perEnemy, unsigned(Numbers::Num(spellId, "target_count"))));
        }

        // Cursed Ground: every period, the Necromancer is healed for its share of the Life for each enemy in the patch.
        void Patch(Player* player, std::uint32_t spellId, Position const& center, unsigned left)
        {
            if (left == 0 || !player->IsInWorld() || !player->IsAlive())
                return;
            unsigned const enemies = unsigned(Combat::Enemies(player, spellId, center, Tune("cursed_ground_radius_yards")).size());
            Heal(player, spellId, GroundHeal(player->GetMaxHealth(), Numbers::Num(spellId, "heal_pct"), enemies));
            player->m_Events.AddEventAtOffset([player, spellId, center, left] { Patch(player, spellId, center, left - 1); },
                                              std::chrono::milliseconds(Millis(Tune("cursed_ground_period_seconds"))));
        }

        // Transmittable: "enemies that die while cursed will spread the curse to a nearby unaffected target", for what the dead one had left.
        void Spread(Player* player, std::uint32_t spellId, Unit* dead, double seconds)
        {
            Unit* next = nullptr;
            for (Unit* enemy : Combat::Enemies(player, spellId, dead->GetPosition(), Tune("transmittable_radius_yards")))
                if (enemy != dead && enemy->IsAlive() && !Curses::On(player, enemy) &&
                    (!next || dead->GetExactDist(enemy) < dead->GetExactDist(next)))
                    next = enemy;
            if (next)
                Curses::Put(player, next, spellId, seconds);
        }

        // The runes that answer the death of a cursed enemy.
        class Deaths final : public UnitScript
        {
        public:
            Deaths()
                : UnitScript("dc_necromancer_leech", true, {UNITHOOK_ON_UNIT_DEATH})
            {
            }

            void OnUnitDeath(Unit* victim, Unit*) override
            {
                for (auto const& [player, curse] : Curses::Cursers(victim))
                    switch (RuneAt(curse))
                    {
                        case Rune::Transmittable:
                            Spread(player, curse, victim, Curses::Left(player, victim, Skill));
                            break;
                        case Rune::SanguineEnd:
                            if (auto const sheet = Stats::Get(player->GetGUID().GetRawValue()))
                                Heal(player, curse, KillHeal((*sheet)[Stat::LifePerKill], Numbers::Num(curse, "life_per_kill_share_pct")));
                            break;
                        case Rune::BloodFlask:
                            Classes::ReducePotionCooldown(player, Millis(Numbers::Num(curse, "cooldown_reduction_seconds")));
                            break;
                        default:
                            break;
                    }
            }
        };
    } // namespace

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) ? std::optional<double>(0.0) : std::nullopt;
    }

    void Ground(Player* player, std::uint32_t spellId, Position const& center)
    {
        if (!player || !RowOf(spellId, Skill))
            return;
        Rune const rune = RuneAt(spellId);
        double const seconds = Combat::ModifiedDurationSeconds(player, spellId, Numbers::Num(BaseId(Skill), "duration_seconds"));
        if (!CursesEnemies(rune))
        {
            // "curses the ground": a patch that lasts the skill's seconds.
            double const period = Tune("cursed_ground_period_seconds");
            Patch(player, spellId, center, period > 0 ? unsigned(seconds / period + 1e-9) : 0u);
        }
        else
            for (Unit* enemy : Combat::Enemies(player, spellId, center, Tune("leech_radius_yards")))
                Curses::Put(player, enemy, spellId, Passive::CurseSeconds(player, seconds));
        if (rune == Rune::Osmosis)
            Curses::Follow(player, Skill, spellId, Regen);
        else
            Curses::Unfollow(player, Skill);
    }

    void Landed(Player* player, Unit* target, std::uint32_t)
    {
        std::uint32_t const curse = Curses::On(player, target, Skill);
        if (!curse || !HealsWhenStruck(RuneAt(curse)))
            return;
        // "Cursed enemies heal the attacker for {heal_pct} of their total health when they are struck."
        Heal(player, curse, StruckHeal(player->GetMaxHealth(), Numbers::Num(BaseId(Skill), "heal_pct")));
    }

    void RegisterScripts()
    {
        new Deaths();
    }
} // namespace DC::Combat::Necromancer::Leech
