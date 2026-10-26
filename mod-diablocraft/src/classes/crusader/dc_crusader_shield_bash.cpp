/*
 * Shield Bash and its five runes: the charge, the enemies the bash reaches around the one aimed at, and what each rune
 * adds. The dispatch is in dc_crusader.cpp; the Block Chance share is dc_crusader_block_share.cpp's.
 */

#include "dc_crusader_shield_bash.h"
#include "dc_crusader_block_share.h"
#include "dc_crusader_common.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_movement_effects.h"

#include <algorithm>

namespace DC::Combat::Crusader::ShieldBash
{
    namespace
    {
        constexpr std::string_view Skill = "Shield Bash";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        double Tune(char const* name)
        {
            return DC::Tunables::Get("crusader", name);
        }

        // The area the bash reaches: the larger area of the power file (17 yards, 30 degrees) and Pound's short narrow
        // one (the sheet's 8 yards, the power file's 5 degrees).
        double Radius(std::uint32_t spellId)
        {
            return RuneAt(spellId) == Rune::Pound ? Numbers::Num(spellId, "radius_yards")
                                                  : Tune("shield_bash_area_yards");
        }

        double Arc(std::uint32_t spellId)
        {
            return ArcRadians(
                Tune(RuneAt(spellId) == Rune::Pound ? "shield_bash_pound_arc_degrees" : "shield_bash_arc_degrees"));
        }

        // The hit's weapon damage and share of Block Chance, from the rune that replaces them or the skill.
        std::pair<double, double> HitNumbers(std::uint32_t spellId)
        {
            std::uint32_t const base = BaseId(Skill);
            if (ReplacesHit(RuneAt(spellId)))
                return {Numbers::Num(spellId, "damage_pct"), Numbers::Num(spellId, "block_chance_share_pct")};
            return {Numbers::Num(base, "damage_pct"), Numbers::Num(base, "block_chance_share_pct")};
        }

        // One extra strike of the Crusader's own: `damage` and `share` are the rune's numbers; the share is added here.
        void ExtraStrike(Player* player, Unit* enemy, std::uint32_t spellId, double damage, double share)
        {
            BlockShare::OwnStrikes scope;
            Combat::Strike(player, enemy, spellId, BlockShare::PctNow(player, damage, share));
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
        return HitNumbers(spellId).first;
    }

    std::optional<std::pair<double, double>> Main(std::uint32_t spellId)
    {
        if (!Is(spellId))
            return std::nullopt;
        return HitNumbers(spellId);
    }

    void Approach(Player* player, std::uint32_t spellId, Unit* target)
    {
        if (!player || !target || target == player || !Is(spellId))
            return;
        Point const to = Landing({player->GetPositionX(), player->GetPositionY()},
                                 {target->GetPositionX(), target->GetPositionY()}, Tune("shield_bash_stop_yards"));
        if (to.x != player->GetPositionX() || to.y != player->GetPositionY())
        {
            float z = target->GetPositionZ();
            player->UpdateAllowedPositionZ(float(to.x), float(to.y), z);
            player->NearTeleportTo(float(to.x), float(to.y), z,
                                   float(std::atan2(target->GetPositionY() - to.y, target->GetPositionX() - to.x)),
                                   true);
        }
        else
            player->SetFacingToObject(target);
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        if (!player || !Is(spellId) || targets.empty())
            return;
        Unit* aimed = targets.front();
        Rune const rune = RuneAt(spellId);
        double const heading = player->GetAngle(aimed), radius = Radius(spellId), arc = Arc(spellId);
        auto const [damage, share] = HitNumbers(spellId);

        // "bashing him and all nearby foes": the enemies in the cone along the line to the one aimed at, each with the
        // bash's own hit (the aimed one took it from the engine).
        std::vector<Unit*> hit{aimed};
        std::vector<Unit*> fragments;
        double const extraRadius = Tune("shield_bash_fragment_extra_yards"),
                     extraArc = ArcRadians(Tune("shield_bash_fragment_extra_degrees"));
        double const reach = rune == Rune::ShatteredShield ? radius + extraRadius : radius;
        for (Unit* enemy : Combat::Enemies(player, spellId, player->GetPosition(), reach))
        {
            if (enemy == aimed)
                continue;
            double const distance = player->GetExactDist(enemy), off = AngleOff(player->GetAngle(enemy), heading);
            if (InCone(distance, off, radius, arc))
            {
                BlockShare::OwnStrikes scope;
                if (Combat::Strike(player, enemy, spellId, BlockShare::PctNow(player, damage, share)))
                    hit.push_back(enemy);
            }
            else if (rune == Rune::ShatteredShield && Fragment(distance, off, radius, arc, extraRadius, extraArc))
                fragments.push_back(enemy);
        }

        switch (rune)
        {
            case Rune::ShatteredShield:
                for (Unit* enemy : fragments)
                    ExtraStrike(player, enemy, spellId, Numbers::Num(spellId, "damage_pct"),
                        Numbers::Num(spellId, "block_chance_share_pct"));
                break;
            case Rune::ShieldCross:
            {
                // "Additional shields erupt from you in a cross formation": an enemy on any arm takes one extra hit.
                // The arms' length and width have no source yet; with none the rune adds nothing.
                double const length = Tune("shield_bash_cross_length_yards"),
                             width = Tune("shield_bash_cross_width_yards");
                if (length <= 0 || width <= 0)
                    break;
                for (Unit* enemy : Combat::Enemies(player, spellId, player->GetPosition(), std::max(length, width)))
                    if (OnCross(enemy->GetPositionX() - player->GetPositionX(),
                                enemy->GetPositionY() - player->GetPositionY(), player->GetOrientation(), length,
                                width))
                        ExtraStrike(player, enemy, spellId, Numbers::Num(spellId, "damage_pct"),
                            Numbers::Num(spellId, "block_chance_share_pct"));
                break;
            }
            case Rune::OneOnOne:
                // "The targeted monster is stunned for {stun_duration_seconds} seconds. All other monsters hit are
                // knocked back."
                Stun(player, aimed, Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player));
                for (Unit* enemy : hit)
                    if (enemy != aimed)
                        Abilities::Knockback(player, enemy, Tune("shield_bash_knockback_yards"));
                break;
            default:
                break;
        }
    }
} // namespace DC::Combat::Crusader::ShieldBash
