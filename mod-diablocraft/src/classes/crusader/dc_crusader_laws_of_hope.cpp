/*
 * Laws of Hope and its five runes: the standing aura that heals the Crusader and its group, the activation that shields
 * them, and what each rune adds to the empowered Law. The state and the pulse every Law shares are dc_crusader_laws.h
 * and .cpp; the dispatch is in dc_crusader.cpp.
 */

#include "dc_crusader_laws_of_hope.h"
#include "../dc_level_heal.h"
#include "dc_crusader_common.h"
#include "dc_crusader_laws.h"

#include "SpellAuraEffects.h"

#include <algorithm>
#include <limits>

namespace DC::Combat::Crusader::LawsOfHope
{
    namespace
    {
        constexpr std::string_view Skill = "Laws of Hope";
        // Stock "Power Word: Shield" (rank 1): one SCHOOL_ABSORB effect of every school; the amount and the time are
        // set on the aura.
        constexpr std::uint32_t Shield = 17;

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        std::uint64_t Millis(double seconds)
        {
            return seconds > 0 ? std::uint64_t(seconds * 1000.0 + 0.5) : 0;
        }

        // The numbers the empowered Law adds, on the Crusader and its group up to the end of the window.
        void Empower(Player* owner, std::uint32_t slotted)
        {
            std::uint32_t const base = Laws::BaseId(Skill);
            std::uint64_t const guid = owner->GetGUID().GetRawValue();
            std::uint64_t const until = std::min(Laws::Now() + Laws::PulseHoldMs(), Laws::BoostEnd(guid, base));
            Rune const rune = RuneAt(slotted);
            for (Player* holder : Laws::InAura(owner, Skill))
                switch (rune)
                {
                    case Rune::WingsOfAngels:
                        // "Empowering the Law also increases movement speed for you and your allies by
                        // {movement_speed_pct}": the speed is built, running through enemies is not.
                        Laws::Hold(holder, Stat::MovementSpeed, Bucket::Uncapped, Laws::Key(guid, slotted),
                                   Numbers::Num(slotted, "movement_speed_pct"), until);
                        break;
                    case Rune::EternalHope:
                        // "Empowering the Law also increases the maximum Life of you and your allies by
                        // {max_life_pct}."
                        Laws::Hold(holder, Stat::LifePercent, Bucket::Flat, Laws::Key(guid, slotted),
                                   Numbers::Num(slotted, "max_life_pct"), until);
                        break;
                    case Rune::HopefulCry:
                    case Rune::PromiseOfFaith:
                        // "Empowering the Law also reduces all Physical (non-Physical) damage taken by
                        // {damage_reduction_pct}": one number per element, each its own contribution.
                        for (unsigned e = 0; e < ElementCount; ++e)
                            if (ReducesElement(rune, Element(e)))
                                Laws::Hold(holder, Stat::ElementReduction, Bucket::Flat,
                                           Laws::Key(guid, slotted + 0x20000u * (e + 1)),
                                           Numbers::Num(slotted, "damage_reduction_pct"), until, Element(e));
                        break;
                    default:
                        break;
                }
        }

        // One pulse of the aura. "Passive: Recite the Law, healing you and your allies for {heal_per_second_life} Life
        // per second": the Crusader and its group within the aura, whether or not the Law is empowered.
        void Pulse(Player* owner, std::uint32_t slotted, bool boosted)
        {
            if (!owner->IsAlive())
                return;
            std::uint32_t const base = Laws::BaseId(Skill);
            double const heal = HealPerPulse(Classes::HealAtLevel(Numbers::Num(base, "heal_per_second_life"), owner->GetLevel()), Laws::PulseSeconds());
            for (Player* holder : Laws::InAura(owner, Skill))
                Heal(owner, holder, slotted, heal);
            if (boosted)
                Empower(owner, slotted);
        }

        // What the press itself does. "Active: Empower the Law, surrounding you and your allies in a shield for
        // {absorb_duration_seconds} seconds that absorbs up to {absorb_life} damage."
        void Activate(Player* player, std::uint32_t spellId, std::vector<Unit*> const&)
        {
            for (Player* holder : Laws::InAura(player, Skill))
                if (holder->IsAlive())
                    if (Aura* aura = player->AddAura(Shield, holder))
                    {
                        int32 const seconds =
                            int32(Millis(Laws::ActiveSeconds(player, Numbers::Num(spellId, "absorb_duration_seconds"))));
                        aura->SetMaxDuration(seconds);
                        aura->SetDuration(seconds);
                        if (AuraEffect* effect = aura->GetEffect(EFFECT_0))
                            effect->ChangeAmount(
                                std::int32_t(std::min(Classes::HealAtLevel(Numbers::Num(spellId, "absorb_life"), player->GetLevel()),
                                                      double(std::numeric_limits<std::int32_t>::max()))));
                    }
        }

        // Faith's Reward: "While empowered ... heals you and your allies for {heal_per_hit_life} Life for every point
        // of Wrath that you spend."
        void Spent(Player* player, double wrath)
        {
            std::uint32_t const slotted = Laws::Slotted(player, Skill);
            if (!slotted || RuneAt(slotted) != Rune::FaithsReward ||
                !Laws::Boosted(player->GetGUID().GetRawValue(), Laws::BaseId(Skill), Laws::Now()))
                return;
            double const heal = HealForWrath(Classes::HealAtLevel(Numbers::Num(slotted, "heal_per_hit_life"), player->GetLevel()), wrath);
            for (Player* holder : Laws::InAura(player, Skill))
                Heal(player, holder, slotted, heal);
        }

        Laws::Flavour const flavour{
            .skill = Skill, .pulse = Pulse, .activate = Activate, .killed = nullptr, .spent = Spent,
                                       .window = "absorb_duration_seconds"};
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
        Empower(player, spellId);
    }

    void Register()
    {
        Laws::Add(flavour);
    }
} // namespace DC::Combat::Crusader::LawsOfHope
