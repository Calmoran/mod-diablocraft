/*
 * Shield Glare and its five runes: the cone of light that blinds, and what each rune does about the enemies it blinded.
 * The dispatch is in dc_crusader.cpp.
 */

#include "dc_crusader_shield_glare.h"
#include "dc_crusader_common.h"
#include "../../combat/dc_charm_effect.h"
#include "../../combat/dc_charm_effect_math.h"
#include "../../combat/dc_enemy_effects.h"
#include "Util.h"

#include <algorithm>

namespace DC::Combat::Crusader::ShieldGlare
{
    namespace
    {
        constexpr std::string_view Skill = "Shield Glare";

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

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        if (!Is(spellId))
            return std::nullopt;
        return 0.0;
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        if (!player || !Is(spellId))
            return;
        // The cone the core resolved is narrower than the power file's 120 degrees (SF_3) over 30 yards: the enemies of
        // the rest are blinded here too.
        double const reach = Combat::TargetRadius(spellId);
        float const arc = float(ArcRadians(Tune("shield_glare_arc_degrees")));
        std::vector<Unit*> blinded;
        for (Unit* enemy : targets)
            if (enemy->IsAlive())
                blinded.push_back(enemy);
        for (Unit* enemy : Combat::Enemies(player, spellId, player->GetPosition(), reach))
            if (Caught(player->GetExactDist(enemy), reach, player->HasInArc(arc, enemy),
                       std::find(targets.begin(), targets.end(), enemy) != targets.end()) &&
                enemy->IsAlive())
                blinded.push_back(enemy);
        // "Blinding all enemies ... for {blind_duration_seconds} seconds".
        for (Unit* enemy : blinded)
            Blind(player, enemy, Numbers::Num(spellId, "blind_duration_seconds"));

        switch (RuneAt(spellId))
        {
            case Rune::DivineVerdict:
                // "Blinded enemies take {damage_taken_pct} more damage for {duration_seconds} seconds."
                for (Unit* enemy : blinded)
                    EnemyEffects::Taken(enemy, spellId, Numbers::Num(spellId, "damage_taken_pct"),
                                        Numbers::Num(spellId, "duration_seconds"));
                break;
            case Rune::Uncertainty:
                // "Enemies caught in the glare have a {proc_chance_pct} chance to be charmed and fight for you for
                // {charm_duration_seconds} seconds": the charm takes the blind's place.
                for (Unit* enemy : blinded)
                    if (CharmEffect::Rolls(rand_chance(), Numbers::Num(spellId, "proc_chance_pct")) &&
                        CharmEffect::Apply(player, enemy, spellId, Numbers::Num(spellId, "charm_duration_seconds")))
                        Unblind(player, enemy);
                break;
            case Rune::EmblazonedShield:
                // "Enemies with health lower than {life_threshold_pct} have a {proc_chance_pct} chance to explode when
                // Blinded, dealing {damage_pct} weapon damage to enemies within {radius_yards} yards."
                for (Unit* enemy : blinded)
                    if (Low(enemy->GetHealthPct(), Numbers::Num(spellId, "life_threshold_pct")) &&
                        roll_chance_f(float(Numbers::Num(spellId, "proc_chance_pct"))))
                        for (Unit* near : Combat::Enemies(player, spellId, enemy->GetPosition(),
                                                          Numbers::Num(spellId, "radius_yards")))
                            Combat::Strike(player, near, spellId, Numbers::Own(spellId, "damage_pct"));
                break;
            case Rune::ZealousGlare:
                GainWrath(player, spellId, WrathFor(Numbers::Num(spellId, "gain_resource"), unsigned(blinded.size())));
                break;
            case Rune::Subdue:
                // "Enemies hit by the glare are Slowed by {slow_pct} for {slow_duration_seconds} seconds."
                for (Unit* enemy : blinded)
                    Slow(player, enemy, Numbers::Num(spellId, "slow_pct"),
                         Numbers::Num(spellId, "slow_duration_seconds"));
                break;
            default:
                break;
        }
    }
} // namespace DC::Combat::Crusader::ShieldGlare
