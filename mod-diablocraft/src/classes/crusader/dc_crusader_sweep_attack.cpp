/*
 * Sweep Attack and its five runes: the half circle in front, and what each rune does to the enemies it hit. The
 * dispatch is in dc_crusader.cpp.
 */

#include "dc_crusader_sweep_attack.h"
#include "../dc_level_heal.h"
#include "dc_crusader_common.h"
#include "dc_crusader_dot.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_movement_effects.h"
#include "SpellMgr.h"
#include "Util.h"

#include <algorithm>

namespace DC::Combat::Crusader::SweepAttack
{
    namespace
    {
        constexpr std::string_view Skill = "Sweep Attack";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        double Tune(char const* name)
        {
            return DC::Tunables::Get("crusader", name);
        }

        void Heal(Player* caster, std::uint32_t spellId, double amount)
        {
            if (!caster->IsAlive() || amount <= 0)
                return;
            if (SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId))
            {
                HealInfo heal(caster, caster, uint32(std::min(amount, double(UINT32_MAX))), info,
                              SPELL_SCHOOL_MASK_HOLY);
                caster->HealBySpell(heal);
            }
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
        return Numbers::Get(BaseId(Skill), "damage_pct");
    }

    bool WeaponWorn(Player* player)
    {
        Item const* mainHand = player->GetItemByPos(INVENTORY_SLOT_BAG_0, EQUIPMENT_SLOT_MAINHAND);
        return mainHand && mainHand->GetTemplate()->Class == ITEM_CLASS_WEAPON;
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        if (!player || !Is(spellId))
            return;
        // The cone the core resolved is narrower than the power file's half circle (SF_27 180 degrees, 18 yards, the
        // targeting sheet's reach): the enemies of the rest are struck here with the same hit.
        double const reach = Combat::TargetRadius(spellId);
        float const arc = float(ArcRadians(Tune("sweep_attack_arc_degrees")));
        std::vector<Unit*> hit = targets;
        for (Unit* enemy : Combat::Enemies(player, spellId, player->GetPosition(), reach))
            if (Swept(player->GetExactDist(enemy), reach, player->HasInArc(arc, enemy),
                      std::find(targets.begin(), targets.end(), enemy) != targets.end()) &&
                Combat::Strike(player, enemy, spellId))
                hit.push_back(enemy);
        // No enemy in the core's cone but one in the rest of the half circle: the swing still connected, once.
        if (targets.empty() && !hit.empty())
            Combat::Connected(player, spellId, unsigned(hit.size()));
        if (hit.empty())
            return;

        switch (RuneAt(spellId))
        {
            case Rune::GatheringSweep:
                // "Enemies caught in the sweep are pulled toward you."
                for (Unit* enemy : hit)
                    Abilities::PullToward(player, enemy, Tune("sweep_attack_pull_yards"));
                break;
            case Rune::BlazingSweep:
                // "Enemies hit by the attack will catch on fire for {damage_pct} weapon damage over
                // {dot_duration_seconds} seconds": the tick length is a tunable with no number yet, and without it
                // nothing burns.
                for (Unit* enemy : hit)
                    Dot::Burn(player, enemy, spellId, Numbers::Num(spellId, "damage_pct"),
                              Numbers::Num(spellId, "dot_duration_seconds"), Tune("sweep_attack_burn_tick_seconds"));
                break;
            case Rune::HolyShock:
                Heal(player, spellId, HealFor(Classes::HealAtLevel(Numbers::Num(spellId, "heal_per_hit_life"), player->GetLevel()), unsigned(hit.size())));
                break;
            case Rune::TripAttack:
            {
                // "have a {proc_chance_pct} chance to be tripped and Stunned for {stun_duration_seconds} seconds": a roll for each
                // enemy hit, the stun stretched by the worn stun duration powers.
                double const stun = Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player);
                for (Unit* enemy : hit)
                    if (roll_chance_f(float(Numbers::Num(spellId, "proc_chance_pct"))))
                        Stun(player, enemy, stun);
                break;
            }
            case Rune::InspiringSweep:
                Buffs::Stack(player, spellId, Stat::Armor, Bucket::Percent, Numbers::Num(spellId, "armor_pct"), 1,
                             Numbers::Num(spellId, "duration_seconds"));
                break;
            default:
                break;
        }
    }
} // namespace DC::Combat::Crusader::SweepAttack
