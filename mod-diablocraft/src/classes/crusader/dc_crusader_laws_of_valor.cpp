/*
 * Laws of Valor and its five runes: the standing aura that quickens the Crusader and its group, the activation that
 * empowers it, and what each rune adds to the empowered Law. The state and the pulse every Law shares are
 * dc_crusader_laws.h and .cpp; the dispatch is in dc_crusader.cpp.
 */

#include "dc_crusader_laws_of_valor.h"
#include "../dc_level_heal.h"
#include "dc_crusader_common.h"
#include "dc_crusader_laws.h"
#include "../../combat/dc_item_powers.h"
#include "Random.h"

#include <algorithm>

namespace DC::Combat::Crusader::LawsOfValor
{
    namespace
    {
        constexpr std::string_view Skill = "Laws of Valor";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        std::uint64_t Millis(double seconds)
        {
            return seconds > 0 ? std::uint64_t(seconds * 1000.0 + 0.5) : 0;
        }

        // One pulse of the aura. "Passive: Recite the Law, granting you and your allies {attack_speed_pct:passive}
        // increased Attack Speed", "Active: Empower the Law, granting you and your allies {attack_speed_pct:active}
        // increased Attack Speed for {duration_seconds} seconds": every holder wears the number of the form the Law is
        // in. While empowered the Crusader's own rune numbers ride along, up to the end of the window.
        void Pulse(Player* owner, std::uint32_t slotted, bool boosted)
        {
            if (!owner->IsAlive())
                return;
            std::uint32_t const base = Laws::BaseId(Skill);
            std::uint64_t const id = Laws::Key(owner->GetGUID().GetRawValue(), base);
            std::uint64_t const now = Laws::Now();
            double const speed = Laws::Number(boosted, Numbers::Num(base, "attack_speed_pct", "passive"),
                                              Numbers::Num(base, "attack_speed_pct", "active"));
            for (Player* holder : Laws::InAura(owner, Skill))
                Laws::Hold(holder, Stat::AttackSpeed, Bucket::Flat, id, speed, now + Laws::PulseHoldMs());
            if (!boosted)
                return;
            std::uint64_t const until =
                std::min(now + Laws::PulseHoldMs(), Laws::BoostEnd(owner->GetGUID().GetRawValue(), base));
            switch (RuneAt(slotted))
            {
                case Rune::Invincible:
                    // "Empowering the Law also increases your Life on Hit by {heal_per_hit_life}."
                    Laws::Hold(owner, Stat::LifePerHit, Bucket::Flat, id, Classes::HealAtLevel(Numbers::Num(slotted, "heal_per_hit_life"), owner->GetLevel()),
                               until);
                    break;
                case Rune::Critical:
                    // "Empowering the Law also increases your Critical Hit Damage by {crit_damage_pct}."
                    Laws::Hold(owner, Stat::CritDamage, Bucket::Flat, id, Numbers::Num(slotted, "crit_damage_pct"),
                               until);
                    break;
                default:
                    break;
            }
        }

        // What the press itself does: the runes whose effect happens once, as the Law is empowered.
        void Activate(Player* player, std::uint32_t spellId, std::vector<Unit*> const&)
        {
            switch (RuneAt(spellId))
            {
                case Rune::FrozenInTerror:
                    // "Empowering the Law also grants you a {proc_chance_pct} chance to Stun all enemies within
                    // {radius_yards} yards for {stun_duration_seconds} seconds."
                    if (Stuns(rand_chance(), Numbers::Num(spellId, "proc_chance_pct")))
                    {
                        double const seconds =
                            Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player);
                        for (Unit* enemy : Combat::Enemies(player, spellId, player->GetPosition(),
                                                           Numbers::Num(spellId, "radius_yards")))
                            Stun(player, enemy, seconds);
                    }
                    break;
                case Rune::UnstoppableForce:
                    // "Empowering the law also reduces the Wrath cost of all skills by {cost_reduction_pct} for
                    // {duration_seconds} seconds": its own time, from the press.
                    Laws::Hold(player, Stat::ResourceCostReduction, Bucket::Flat,
                               Laws::Key(player->GetGUID().GetRawValue(), spellId),
                               Numbers::Num(spellId, "cost_reduction_pct"),
                               Laws::Now() + Millis(Laws::ActiveSeconds(player, Numbers::Num(spellId, "duration_seconds"))));
                    break;
                default:
                    break;
            }
        }

        // Answered Prayer: "While the Law is empowered, each enemy killed increases the duration by
        // {duration_seconds:per_kill} second, up to a maximum of {duration_seconds:max} seconds of increased time."
        void Killed(Player* player)
        {
            std::uint32_t const slotted = Laws::Slotted(player, Skill);
            if (!slotted || RuneAt(slotted) != Rune::AnsweredPrayer)
                return;
            Laws::Extend(player->GetGUID().GetRawValue(), Laws::BaseId(Skill), Laws::Now(),
                         Millis(Numbers::Num(slotted, "duration_seconds", "per_kill")),
                         Millis(Numbers::Num(slotted, "duration_seconds", "max")));
        }

        Laws::Flavour const flavour{.skill = Skill, .pulse = Pulse, .activate = Activate, .killed = Killed};
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
        Laws::Press(flavour, player, spellId, targets);
        // The empowered numbers reach the Crusader and its group now, not at the next pulse.
        Pulse(player, spellId, true);
    }

    void Register()
    {
        Laws::Add(flavour);
    }
} // namespace DC::Combat::Crusader::LawsOfValor
