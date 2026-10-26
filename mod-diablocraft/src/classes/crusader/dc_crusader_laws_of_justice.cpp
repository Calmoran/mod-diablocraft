/*
 * Laws of Justice and its five runes: the standing aura that hardens the Crusader and its group against every element,
 * the activation that empowers it, and what each rune adds to the empowered Law. The state and the pulse every Law
 * shares are dc_crusader_laws.h and .cpp; the dispatch is in dc_crusader.cpp.
 */

#include "dc_crusader_laws_of_justice.h"
#include "../dc_level_heal.h"
#include "dc_crusader_common.h"
#include "dc_crusader_laws.h"
#include "../../combat/dc_enemy_effects.h"

#include "Group.h"
#include "SpellAuraEffects.h"

#include <algorithm>
#include <limits>

namespace DC::Combat::Crusader::LawsOfJustice
{
    namespace
    {
        constexpr std::string_view Skill = "Laws of Justice";
        // Stock "Power Word: Shield" (rank 1): one SCHOOL_ABSORB effect of every school; the amount and the time are
        // set on the aura.
        constexpr std::uint32_t Shield = 17;
        // "Immunity to control impairing effects": the mechanics of the core's own "Immune Movement Impairment and Loss
        // of Control" (spell 42292), less the ones that only slow.
        constexpr Mechanics LossOfControl[] = {
            MECHANIC_CHARM,   MECHANIC_DISORIENTED, MECHANIC_FEAR,     MECHANIC_ROOT,      MECHANIC_SLEEP,
            MECHANIC_STUN,    MECHANIC_FREEZE,      MECHANIC_KNOCKOUT, MECHANIC_POLYMORPH, MECHANIC_BANISH,
            MECHANIC_SHACKLE, MECHANIC_TURN,        MECHANIC_HORROR,   MECHANIC_SAPPED};

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        std::uint64_t Millis(double seconds)
        {
            return seconds > 0 ? std::uint64_t(seconds * 1000.0 + 0.5) : 0;
        }

        void Immunity(Player* holder, std::uint32_t key, bool apply)
        {
            for (Mechanics mechanic : LossOfControl)
                holder->ApplySpellImmune(key, IMMUNITY_MECHANIC, mechanic, apply);
        }

        // The Crusaders in `member`'s group (and `member` itself when `includeSelf`) whose Law of Justice is the rune
        // `rune`, empowered now, and whose aura reaches `member`.
        std::vector<Player*> Covering(Player* member, Rune rune, bool includeSelf)
        {
            std::vector<Player*> found;
            if (!member)
                return found;
            std::uint64_t const now = Laws::Now();
            std::uint32_t const base = Laws::BaseId(Skill);
            auto consider = [&](Player* crusader)
            {
                if (!crusader || !crusader->IsAlive() || !crusader->IsInWorld() || (crusader == member && !includeSelf))
                    return;
                std::uint32_t const slotted = Laws::Slotted(crusader, Skill);
                if (!slotted || RuneAt(slotted) != rune || !Laws::Boosted(crusader->GetGUID().GetRawValue(), base, now))
                    return;
                std::vector<Player*> reached = Laws::InAura(crusader, Skill);
                if (std::find(reached.begin(), reached.end(), member) != reached.end())
                    found.push_back(crusader);
            };
            consider(member);
            if (Group* group = member->GetGroup())
                for (GroupReference* ref = group->GetFirstMember(); ref; ref = ref->next())
                    if (Player* other = ref->GetSource(); other && other != member)
                        consider(other);
            return found;
        }

        // One pulse of the aura. "Passive: Recite the Law, granting you and your allies {resistance_points:passive}
        // increased resistance to all elements", "Active: Empower the Law, granting you and your allies
        // {resistance_points:active} increased resistance to all elements for {duration_seconds} seconds": every holder
        // wears the number of the form the Law is in.
        void Pulse(Player* owner, std::uint32_t, bool boosted)
        {
            if (!owner->IsAlive())
                return;
            std::uint32_t const base = Laws::BaseId(Skill);
            std::uint64_t const id = Laws::Key(owner->GetGUID().GetRawValue(), base);
            double const points = Laws::Number(boosted, Numbers::Num(base, "resistance_points", "passive"),
                                               Numbers::Num(base, "resistance_points", "active"));
            for (Player* holder : Laws::InAura(owner, Skill))
                Laws::Hold(holder, Stat::AllResistance, Bucket::Flat, id, points, Laws::Now() + Laws::PulseHoldMs());
        }

        // What the press itself does to the Crusader and its group within the aura.
        void Activate(Player* player, std::uint32_t spellId, std::vector<Unit*> const&)
        {
            std::uint64_t const now = Laws::Now();
            std::uint64_t const id = Laws::Key(player->GetGUID().GetRawValue(), spellId);
            switch (RuneAt(spellId))
            {
                case Rune::ImmovableObject:
                    // "Empowering the Law also increases Armor for you and your allies by {armor_points} for
                    // {duration_seconds} seconds."
                    for (Player* holder : Laws::InAura(player, Skill))
                        Laws::Hold(holder, Stat::Armor, Bucket::Flat, id, Numbers::Num(spellId, "armor_points"),
                                   now + Millis(Laws::ActiveSeconds(player, Numbers::Num(spellId, "duration_seconds"))));
                    break;
                case Rune::FaithsArmor:
                    // "Empowering the Law also surrounds you and your allies with shields of faith for
                    // {absorb_duration_seconds} seconds. The shields absorb up to {absorb_life} damage."
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
                    break;
                case Rune::Bravery:
                    // "Empowering the Law also grants immunity to control impairing effects to you and your allies for
                    // {duration_seconds} seconds."
                    for (Player* holder : Laws::InAura(player, Skill))
                    {
                        Immunity(holder, spellId, true);
                        holder->m_Events.AddEventAtOffset(
                            [holder, spellId] { Immunity(holder, spellId, false); },
                            std::chrono::milliseconds(
                                Millis(Laws::ActiveSeconds(player, Numbers::Num(spellId, "duration_seconds")))));
                    }
                    break;
                default:
                    break;
            }
        }

        Laws::Flavour const flavour{.skill = Skill, .pulse = Pulse, .activate = Activate, .killed = nullptr};
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

    void Taken(Player* victim, Unit* attacker)
    {
        if (!victim || !attacker || !attacker->IsHostileTo(victim))
            return;
        // "While the Law is empowered, any enemy who attacks you or your allies will have their damage reduced by
        // {enemy_damage_pct} for {duration_seconds} seconds, stacking up to a maximum of {max_bonus_pct}."
        for (Player* crusader : Covering(victim, Rune::DecayingStrength, true))
        {
            std::uint32_t const spellId = Laws::Slotted(crusader, Skill);
            double const each = Numbers::Num(spellId, "enemy_damage_pct");
            EnemyEffects::Weaken(attacker, spellId, each, Numbers::Num(spellId, "duration_seconds"),
                                 MaxStacks(Numbers::Num(spellId, "max_bonus_pct"), each));
        }
    }

    double Redirect(Unit* victim, double damage)
    {
        Player* ally = victim ? victim->ToPlayer() : nullptr;
        if (!ally || damage <= 0)
            return damage;
        // "Empowering the Law also redirects {damage_share_pct} of the damage taken by your allies to you."
        for (Player* crusader : Covering(ally, Rune::ProtectTheInnocent, false))
        {
            std::uint32_t const spellId = Laws::Slotted(crusader, Skill);
            double const share = Redirected(damage, Numbers::Num(spellId, "damage_share_pct"));
            if (share < 1.0)
                return damage;
            Unit::DealDamage(nullptr, crusader,
                             std::uint32_t(std::min(share, double(std::numeric_limits<std::uint32_t>::max()))), nullptr,
                             DIRECT_DAMAGE, SPELL_SCHOOL_MASK_NORMAL, nullptr, false);
            return damage - share;
        }
        return damage;
    }

    void Register()
    {
        Laws::Add(flavour);
    }
} // namespace DC::Combat::Crusader::LawsOfJustice
