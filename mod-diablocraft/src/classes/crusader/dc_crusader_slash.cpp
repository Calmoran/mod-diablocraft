/*
 * Slash and its five runes: the stacks Zeal and Guard give for each enemy hit, Electrify's stun, Crush's critical
 * chance and Carve's larger area. The dispatch is in dc_crusader.cpp.
 */

#include "dc_crusader_slash.h"
#include "dc_crusader_common.h"
#include "../../combat/dc_item_powers.h"
#include "Util.h"

#include <algorithm>

namespace DC::Combat::Crusader::Slash
{
    namespace
    {
        constexpr std::string_view Skill = "Slash";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        double Tune(char const* name)
        {
            return DC::Tunables::Get("crusader", name);
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    void Connected(Player* player, std::uint32_t spellId, unsigned enemies)
    {
        switch (RuneAt(spellId))
        {
            case Rune::Zeal:
                Buffs::Stack(player, spellId, Stat::AttackSpeed, Bucket::Flat,
                             Numbers::Num(spellId, "attack_speed_pct"),
                             unsigned(Numbers::Num(spellId, "max_stacks_count")),
                             Numbers::Num(spellId, "duration_seconds"), enemies);
                break;
            case Rune::Guard:
                // The sheet states the armor and the cap and no length; the length is a tunable with no number yet,
                // and the rune gives nothing until one is set.
                Buffs::Stack(player, spellId, Stat::Armor, Bucket::Percent, Numbers::Num(spellId, "armor_pct"),
                             unsigned(Numbers::Num(spellId, "max_stacks_count")), Tune("slash_guard_seconds"),
                             enemies);
                break;
            default:
                break;
        }
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        if (!player)
            return;
        switch (RuneAt(spellId))
        {
            case Rune::Electrify:
            {
                // "has a {proc_chance_pct} chance to stun enemies for {stun_duration_seconds} seconds": a roll for each
                // enemy struck. A stun is stretched by the worn stun duration powers.
                double const stun = Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player);
                for (Unit* enemy : targets)
                    if (enemy->IsAlive() && roll_chance_f(float(Numbers::Num(spellId, "proc_chance_pct"))))
                        Stun(player, enemy, stun);
                break;
            }
            case Rune::Carve:
            {
                // The core's cone took the enemies it took; the enemies of the larger reach in front that it did not take
                // are struck here with the same hit.
                double const base = Combat::TargetRadius(spellId), reach = Tune("slash_carve_radius_yards");
                float const arc = float(ArcRadians(Tune("slash_carve_arc_degrees")));
                std::vector<Unit*> struck;
                for (Unit* enemy : Combat::Enemies(player, spellId, player->GetPosition(), reach))
                    if (Carved(player->GetExactDist(enemy), reach, base,
                               std::find(targets.begin(), targets.end(), enemy) != targets.end()) &&
                        player->HasInArc(arc, enemy) && Combat::Strike(player, enemy, spellId))
                        struck.push_back(enemy);
                // No enemy in the core's cone but one in the larger reach: the swing still connected, once.
                if (targets.empty() && !struck.empty())
                    Combat::Connected(player, spellId, unsigned(struck.size()));
                break;
            }
            default:
                break;
        }
    }

    double CritBonus(Player*, std::uint32_t spellId)
    {
        // Read without a miss log: every hit of every spell asks.
        return CrushCrit(RuneAt(spellId), Numbers::Get(spellId, "crit_chance_pct").value_or(0.0));
    }
} // namespace DC::Combat::Crusader::Slash
