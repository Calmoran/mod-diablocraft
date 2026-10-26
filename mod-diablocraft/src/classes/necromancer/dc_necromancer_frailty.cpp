/*
 * Frailty and its five runes. The cast curses every enemy within the power's radius of the place aimed at for the skill's seconds (Aura
 * of Frailty curses everything around the Necromancer instead, every tick, for as long as the cast lasts). A check every quarter second
 * kills the cursed enemies whose Life is under the threshold; the death of a cursed enemy pays Essence (Harvest Essence) or explodes
 * (Volatile Death); Scent of Blood is read by the minions as a bonus against the cursed.
 */

#include "dc_necromancer_frailty.h"
#include "dc_necromancer_frailty_math.h"
#include "dc_necromancer_common.h"
#include "dc_necromancer_curses.h"
#include "dc_necromancer_passives.h"
#include "dc_necromancer_devour_math.h"
#include "../../stats/dc_stats.h"

#include "ScriptMgr.h"

#include <chrono>
#include <map>
#include <mutex>

namespace DC::Combat::Necromancer::Frailty
{
    namespace
    {
        constexpr std::string_view Skill = "Frailty";

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

        // One checker for each Necromancer; a new cast takes a new stamp, so an old chain finds its own gone and stops.
        std::mutex mutex;
        std::map<std::uint64_t, std::uint64_t> checkers;
        std::uint64_t stamps = 0;

        // Kills the enemies the Necromancer's Frailty holds whose Life is under the curse's threshold, every check, while any is held.
        void Reap(Player* player, std::uint64_t stamp)
        {
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto const found = checkers.find(player->GetGUID().GetRawValue());
                if (found == checkers.end() || found->second != stamp)
                    return;
            }
            if (!player->IsInWorld())
                return;
            bool held = false;
            for (auto const& [enemy, curse] : Curses::CursedBy(player))
            {
                if (!RowOf(curse, Skill))
                    continue;
                held = true;
                if (Executes(enemy->GetHealthPct(), Numbers::Num(curse, "life_threshold_pct")))
                    Unit::Kill(player, enemy);
            }
            if (!held)
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto const found = checkers.find(player->GetGUID().GetRawValue());
                if (found != checkers.end() && found->second == stamp)
                    checkers.erase(found);
                return;
            }
            player->m_Events.AddEventAtOffset([player, stamp] { Reap(player, stamp); },
                                              std::chrono::milliseconds(Millis(Tune("frailty_check_seconds"))));
        }

        // Aura of Frailty: every tick the enemies within the radius (the power's, longer by a share of the gold pickup radius) are cursed
        // for as long as the next tick, so the curse lapses when they leave.
        void Aura(Player* player, std::uint32_t spellId, unsigned left)
        {
            if (left == 0 || !player->IsInWorld() || !player->IsAlive())
                return;
            auto const sheet = Stats::Get(player->GetGUID().GetRawValue());
            double const radius = Devour::AuraRadius(Numbers::Num(spellId, "radius_yards"), Numbers::Num(spellId, "radius_share_pct"),
                                                     sheet ? (*sheet)[Stat::GoldPickupRange] : 0.0, Tune("frailty_aura_max_increase_yards"));
            double const tick = Tune("frailty_aura_tick_seconds");
            for (Unit* enemy : Combat::Enemies(player, spellId, player->GetPosition(), radius))
                Curses::Put(player, enemy, spellId, tick * 2);
            player->m_Events.AddEventAtOffset([player, spellId, left] { Aura(player, spellId, left - 1); },
                                              std::chrono::milliseconds(Millis(tick)));
        }

        void StartReaping(Player* player)
        {
            std::uint64_t stamp;
            {
                std::lock_guard<std::mutex> guard(mutex);
                checkers[player->GetGUID().GetRawValue()] = stamp = ++stamps;
            }
            Reap(player, stamp);
        }

        // The runes that answer the death of a cursed enemy.
        class Deaths final : public UnitScript
        {
        public:
            Deaths()
                : UnitScript("dc_necromancer_frailty", true, {UNITHOOK_ON_UNIT_DEATH})
            {
            }

            void OnUnitDeath(Unit* victim, Unit*) override
            {
                for (auto const& [player, curse] : Curses::Cursers(victim))
                    switch (RuneAt(curse))
                    {
                        case Rune::HarvestEssence:
                            // "Gain {gain_resource} Essence when a cursed enemy dies."
                            PayEssence(player, curse, Numbers::Num(curse, "gain_resource"));
                            break;
                        case Rune::VolatileDeath:
                            // "Cursed enemies explode for {damage_pct} weapon damage on death": on the enemies around the dead one.
                            for (Unit* enemy : Combat::Enemies(player, curse, victim->GetPosition(), Tune("volatile_death_radius_yards")))
                                if (enemy != victim)
                                    Combat::Strike(player, enemy, curse, Numbers::Num(curse, "damage_pct"));
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

    void Casting(Player* player, std::uint32_t spellId)
    {
        // "Triggers at {life_threshold_pct} life but costs 10% of your life." (Early Grave)
        if (player && RuneAt(spellId) == Rune::EarlyGrave)
            SpendLife(player, Tune("early_grave_life_cost_pct"));
    }

    void Ground(Player* player, std::uint32_t spellId, Position const& center)
    {
        if (!player || !RowOf(spellId, Skill))
            return;
        double const seconds = Combat::ModifiedDurationSeconds(player, spellId, Numbers::Num(BaseId(Skill), "duration_seconds"));
        if (RuneAt(spellId) == Rune::AuraOfFrailty)
        {
            double const tick = Tune("frailty_aura_tick_seconds");
            Aura(player, spellId, tick > 0 ? unsigned(seconds / tick + 1e-9) : 0u);
        }
        else
            for (Unit* enemy : Combat::Enemies(player, spellId, center, Tune("frailty_radius_yards")))
                Curses::Put(player, enemy, spellId, Passive::CurseSeconds(player, seconds));
        StartReaping(player);
    }

    double MinionBonus(Player* player, Unit* enemy)
    {
        std::uint32_t const curse = Curses::On(player, enemy, Skill);
        return curse && RuneAt(curse) == Rune::ScentOfBlood ? Numbers::Num(curse, "damage_taken_pct") : 0.0;
    }

    void RegisterScripts()
    {
        new Deaths();
    }
} // namespace DC::Combat::Necromancer::Frailty
