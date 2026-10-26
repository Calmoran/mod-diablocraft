/*
 * Grim Scythe and its five runes. The engine hits every enemy in the cone for the skill's weapon damage and the
 * dispatch pays the Essence for each; here: Blood Scythe heals for the enemies hit, Execution may kill the weak ones
 * outright, Frost Scythe speeds the Necromancer up for each enemy hit, Dual Scythes draws the enemies in to the line it
 * faces. Cursed Scythe's curse waits for the curses (the Curses category): it has the Poison the record gives and
 * nothing else yet.
 */

#include "dc_necromancer_grim_scythe.h"
#include "dc_necromancer_common.h"
#include "dc_necromancer_grim_scythe_math.h"
#include "../../combat/dc_movement_effects.h"

#include <cmath>

namespace DC::Combat::Necromancer::GrimScythe
{
    namespace
    {
        constexpr std::string_view Skill = "Grim Scythe";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        // The point level with `enemy` on the line the Necromancer faces.
        Position Level(Player* player, Unit* enemy)
        {
            double const fx = std::cos(player->GetOrientation()), fy = std::sin(player->GetOrientation());
            double const along = LevelWith(player->GetPositionX(), player->GetPositionY(), fx, fy,
                                           enemy->GetPositionX(), enemy->GetPositionY());
            return Position(player->GetPositionX() + fx * along, player->GetPositionY() + fy * along,
                            enemy->GetPositionZ());
        }
    } // namespace

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        if (!player || !RowOf(spellId, Skill) || targets.empty())
            return;
        unsigned const enemies = unsigned(targets.size());
        switch (RuneAt(spellId))
        {
            case Rune::BloodScythe:
                // "Heal for {heal_pct} of your health per enemy hit."
                Heal(player, spellId, HealOfHits(player->GetMaxHealth(), Numbers::Num(spellId, "heal_pct"), enemies));
                break;
            case Rune::Execution:
                // "Enemies below {life_threshold_pct} health have a {proc_chance_pct} chance to be decapitated and
                // instantly killed": a roll for each enemy struck.
                for (Unit* enemy : targets)
                    if (enemy->IsAlive() &&
                        Decapitated(enemy->GetHealthPct(), Numbers::Num(spellId, "life_threshold_pct"),
                                    frand(0.0f, 100.0f), Numbers::Num(spellId, "proc_chance_pct")))
                        Unit::Kill(player, enemy);
                break;
            case Rune::FrostScythe:
                // "Each enemy hit increases your attack speed by {attack_speed_pct} for {duration_seconds} seconds. Max
                // {max_stacks_count} stacks."
                Buffs::Stack(player, spellId, Stat::AttackSpeed, Bucket::Flat,
                             Numbers::Num(spellId, "attack_speed_pct"),
                             unsigned(Numbers::Num(spellId, "max_stacks_count")),
                             Numbers::Num(spellId, "duration_seconds"), enemies);
                break;
            case Rune::DualScythes:
                // "push enemies together".
                for (Unit* enemy : targets)
                    if (enemy->IsAlive())
                        Abilities::Pull(enemy, Level(player, enemy));
                break;
            default:
                break;
        }
    }
} // namespace DC::Combat::Necromancer::GrimScythe
