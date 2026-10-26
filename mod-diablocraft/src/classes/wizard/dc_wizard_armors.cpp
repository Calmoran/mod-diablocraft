#include "dc_wizard_armors.h"
#include "../../combat/dc_item_powers.h"
#include <algorithm>
#include <random>

namespace DC::Combat::Wizard::Armors
{
    using namespace Shared;

    void ArmorsHit(Player* player, Unit* attacker, Attack kind)
    {
        bool const melee = kind == Attack::Melee, ranged = kind == Attack::Ranged;
        if (!melee && !ranged)
            return;
        ObjectGuid const guid = attacker->GetGUID();
        if (uint32 id = BuffOf(player, "Ice Armor"))
        {
            if (melee && IsRune(id, "Jagged Ice"))
                After(player, 0,
                      [guid, id](Player* p)
                      {
                          if (Unit* u = Find(p, guid))
                              Combat::Strike(p, u, id);
                      });
            if (melee && IsRune(id, "Crystallize"))
            {
                std::lock_guard<std::recursive_mutex> guard(mutex);
                State& state = StateOf(player);
                uint64 const now = Now();
                std::erase_if(state.crystallize, [now](uint64 until) { return until <= now; });
                if (state.crystallize.size() >= std::size_t(Num(id, "max_stacks_count")) &&
                    !state.crystallize.empty())
                    state.crystallize.erase(state.crystallize.begin());
                state.crystallize.push_back(now + uint64(Num(id, "duration_seconds") * 1000));
            }
            // "a Frost Nova centered on the attacker": the rune's own
            // radius and Freeze (wizard_skill_values.csv:794).
            if (melee && IsRune(id, "Ice Reflect") && Roll() < Num(id, "proc_chance_pct"))
                After(player, 0,
                      [guid, id](Player* p)
                      {
                          if (Unit* u = Find(p, guid))
                              for (Unit* hit : Combat::StrikeArea(p, id, u->GetPosition(), Num(id, "radius_yards")))
                                  Freeze(p, hit, Num(id, "freeze_duration_seconds"));
                      });
        }
        if (uint32 id = BuffOf(player, "Storm Armor"))
        {
            if (IsRune(id, "Reactive Armor"))
                After(player, 0,
                      [guid, id](Player* p)
                      {
                          if (Unit* u = Find(p, guid))
                              Combat::Strike(p, u, id);
                      });
            if (IsRune(id, "Scramble"))
            {
                std::lock_guard<std::recursive_mutex> guard(mutex);
                StateOf(player).scramble = Now() + uint64(Num(id, "duration_seconds") * 1000);
            }
        }
    }

    void ForceArmor(Player* victim, double maxLife, std::uint32_t& damage)
    {
        // Force Armor: a hit over the threshold is cut to the cap, and what
        // is cut away cannot exceed max_absorb_pct of maximum Life, scaled by the
        // shield potency (Ashnagarr's Blood Bracer) like every absorb.
        if (uint32 id = BuffOf(victim, "Energy Armor"); id && IsRune(id, "Force Armor"))
            if (damage > maxLife * Num(id, "damage_threshold_pct") / 100)
            {
                double const cut = std::min(damage - maxLife * Num(id, "damage_cap_pct") / 100,
                                            maxLife * Num(id, "max_absorb_pct") / 100 * ItemPowers::ShieldFactor(victim));
                damage -= uint32(std::max(0.0, cut));
            }
    }

    void ShockingAspect(Player* player, ObjectGuid guid, Hit const& hit, double proc)
    {
        // Storm Armor - Shocking Aspect: "Critical Hits have a chance to
        // electrocute a nearby enemy for {damage_pct} weapon damage as
        // Lightning": proc x crit chance, i.e. proc on a critical hit,
        // and the shock procs nothing (wizard.js:806). "Nearby" has no
        // sourced radius, so it strikes the enemy that was hit.
        if (uint32 armor = BuffOf(player, "Storm Armor");
            armor && IsRune(armor, "Shocking Aspect") && hit.critical && Roll() < 100 * proc)
            After(player, 0, [guid, armor](Player* p) {
                if (Unit* u = Find(p, guid))
                {
                    ProcAs shock(Num(armor, "proc_coefficient", "shock"));
                    Combat::Strike(p, u, armor, Num(armor, "damage_pct"));
                    ItemPowers::StormArmorShock(p, u);
                }
            });
    }

    void ChillingAura(Player* player, uint64 now)
    {
        // Chilling Aura: "Nearby enemies are chilled, slowing their
        // movement speed by {slow_pct}". The chill is renewed before
        // it lapses; "nearby" is ice_armor_chilling_aura_radius_yards,
        // a placeholder, so no one is chilled until it is filled.
        if (uint32 id = BuffOf(player, "Ice Armor"); id && IsRune(id, "Chilling Aura"))
        {
            double const radius = Tune("ice_armor_chilling_aura_radius_yards");
            double const seconds = Num(id, "chill_duration_seconds");
            bool renew = false;
            {
                std::lock_guard<std::recursive_mutex> guard(mutex);
                State& state = StateOf(player);
                if (radius > 0 && seconds > 0 && now >= state.chillingAura)
                {
                    state.chillingAura = now + uint64(seconds * 500);
                    renew = true;
                }
            }
            if (renew)
                for (Unit* enemy : Combat::Enemies(player, id, player->GetPosition(), radius))
                    Chill(player, enemy, seconds, Num(id, "slow_pct"));
        }
    }

    void StormArmorTick(Player* player, uint32 id)
    {
        // "periodically shocking a nearby enemy": one enemy
        // (wizard.js:812). "Nearby" has no sourced radius
        // (storm_armor_shock_radius_yards, a placeholder).
        double const radius = Tune("storm_armor_shock_radius_yards");
        auto enemies =
            radius > 0 ? Combat::Enemies(player, id, player->GetPosition(), radius) : std::vector<Unit*>{};
        if (!enemies.empty())
        {
            Unit* shocked = enemies[std::uniform_int_distribution<std::size_t>(0, enemies.size() - 1)(Engine())];
            Combat::Strike(player, shocked, id);
            // Halo of Karini reads how far the shocked enemy was.
            ItemPowers::StormArmorShock(player, shocked);
        }
    }

    void FrozenStormTick(Player* player, uint32 id, double seconds)
    {
        // "dealing {damage_pct} weapon damage as Cold every second".
        Combat::StrikeArea(player, id, player->GetPosition(), Num(id, "radius_yards"),
                           Num(id, "damage_pct") * seconds, true);
    }
} // namespace DC::Combat::Wizard::Armors
