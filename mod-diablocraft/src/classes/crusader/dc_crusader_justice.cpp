/*
 * Justice and its five runes: the hammer is a projectile, so each rune acts where the hammer lands on an enemy. The
 * dispatch is in dc_crusader.cpp.
 */

#include "dc_crusader_justice.h"
#include "dc_crusader_common.h"
#include "../dc_level_heal.h"
#include "../../combat/dc_item_powers.h"
#include "Group.h"
#include "SpellMgr.h"
#include "Util.h"

namespace DC::Combat::Crusader::Justice
{
    namespace
    {
        constexpr std::string_view Skill = "Justice";

        // The follow-on strikes of a rune are hits of the same spell and land too; they must not start the rune again.
        thread_local bool answering = false;

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
        auto const* row = RowOf(spellId, Skill);
        if (!row)
            return std::nullopt;
        return HitPct(RuneOf(row->rune), Numbers::Num(BaseId(Skill), "damage_pct"),
                      Numbers::Get(spellId, "damage_pct").value_or(0.0));
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId)
    {
        if (answering || !player || !target || !Is(spellId))
            return;
        switch (RuneAt(spellId))
        {
            case Rune::SwordOfJustice:
                // "gain {movement_speed_pct} increased movement speed for {duration_seconds} seconds. This effect
                // stacks up to {max_stacks_count} times."
                Buffs::Stack(
                    player, spellId, Stat::MovementSpeed, Bucket::Flat, Numbers::Num(spellId, "movement_speed_pct"),
                    unsigned(Numbers::Num(spellId, "max_stacks_count")), Numbers::Num(spellId, "duration_seconds"));
                break;
            case Rune::Crack:
            {
                // "there is an {proc_chance_pct}% chance it will crack into {spawn_count} smaller hammers that fly out
                // and deal {damage_pct} weapon damage": each flies to one of the nearest other enemies around the one
                // hit.
                if (!roll_chance_f(float(Numbers::Num(spellId, "proc_chance_pct"))))
                    break;
                double const radius = Tune("justice_crack_radius_yards");
                std::vector<Unit*> others;
                std::vector<double> distances;
                for (Unit* enemy : Combat::Enemies(player, spellId, target->GetPosition(), radius))
                    if (enemy != target)
                    {
                        others.push_back(enemy);
                        distances.push_back(target->GetExactDist(enemy));
                    }
                answering = true;
                for (std::size_t index : Nearest(distances, radius, std::size_t(Numbers::Num(spellId, "spawn_count"))))
                    Combat::Strike(player, others[index], spellId, Numbers::Own(spellId, "damage_pct"));
                answering = false;
                break;
            }
            case Rune::Burst:
            {
                // "explodes on impact, dealing {damage_pct} weapon damage as Lightning to all enemies within
                // {radius_yards} yards. Enemies caught in the explosion have a {proc_chance_pct}% chance to be
                // stunned."
                auto const pct = Numbers::Own(spellId, "damage_pct");
                double const stun = Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player);
                answering = true;
                for (Unit* enemy :
                     Combat::Enemies(player, spellId, target->GetPosition(), Numbers::Num(spellId, "radius_yards")))
                {
                    Combat::Strike(player, enemy, spellId, pct);
                    if (roll_chance_f(float(Numbers::Num(spellId, "proc_chance_pct"))))
                        Stun(player, enemy, stun);
                }
                answering = false;
                break;
            }
            case Rune::HolyBolt:
            {
                // "heals you and your allies for {heal_min_life} - {heal_max_life} Life when it hits an enemy": the
                // Crusader and the group members within reach, each by its own roll.
                double const reach = Tune("justice_holy_bolt_radius_yards");
                std::vector<Player*> healed{player};
                if (Group* group = player->GetGroup())
                    for (GroupReference* ref = group->GetFirstMember(); ref; ref = ref->next())
                        if (Player* member = ref->GetSource();
                            member && member != player && member->IsAlive() && player->IsWithinDistInMap(member, reach))
                            healed.push_back(member);
                // D3 scales the heal by the Healing table at the caster's level, whoever is healed.
                double const minLife = Classes::HealAtLevel(Numbers::Num(spellId, "heal_min_life"), player->GetLevel()),
                             maxLife = Classes::HealAtLevel(Numbers::Num(spellId, "heal_max_life"), player->GetLevel());
                for (Player* ally : healed)
                    Heal(player, ally, spellId, HealAmount(minLife, maxLife, rand_norm()));
                break;
            }
            default:
                break;
        }
    }
} // namespace DC::Combat::Crusader::Justice
