/*
 * Serenity. The sheets: monk_skills.csv, monk_runes.csv, monk_skill_values.csv; Power/Monk_Serenity.pow for the
 * pulse interval. The shield is a stock absorb aura (the Wizard's shields are the same carrier) and the control
 * immunity is the core's own mechanic immunity, both lasting the sheet's seconds and taken off by an event on the
 * Monk.
 */

#include "dc_monk_serenity.h"
#include "dc_monk_serenity_cast.h"
#include "dc_monk_common.h"
#include "../dc_level_heal.h"
#include "Group.h"
#include "GroupReference.h"
#include "SpellAuraEffects.h"
#include "SpellMgr.h"
#include "Util.h"

namespace DC::Combat::Monk::Serenity
{
    namespace
    {
        constexpr std::string_view Skill = "Serenity";
        // Stock "Power Word: Shield" (rank 1): one SCHOOL_ABSORB effect of every school; the amount and the time are
        // set below.
        constexpr std::uint32_t Shield = 17;

        // "Immunity to all control impairing effects": the mechanics of the core's own "Immune Movement Impairment and
        // Loss of Control" (spell 42292), less the ones that only slow. Instant Karma ("your movement is unhindered")
        // adds those.
        constexpr Mechanics LossOfControl[] = {
            MECHANIC_CHARM,   MECHANIC_DISORIENTED, MECHANIC_FEAR,     MECHANIC_ROOT,      MECHANIC_SLEEP,
            MECHANIC_STUN,    MECHANIC_FREEZE,      MECHANIC_KNOCKOUT, MECHANIC_POLYMORPH, MECHANIC_BANISH,
            MECHANIC_SHACKLE, MECHANIC_TURN,        MECHANIC_HORROR,   MECHANIC_SAPPED};
        constexpr Mechanics Movement[] = {MECHANIC_SNARE, MECHANIC_DAZE};

        Shells::Ability const* Row(std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && Skill == row->skill ? row : nullptr;
        }

        double Tune(char const* name)
        {
            return DC::Tunables::Get("monk", name);
        }

        std::uint64_t Millis(double seconds)
        {
            return std::uint64_t(seconds * 1000.0 + 0.5);
        }

        // Take the control effects off `unit` now ("removes control impairing effects").
        void Cleanse(Unit* unit, bool movement)
        {
            std::uint64_t mask = 0;
            for (Mechanics mechanic : LossOfControl)
                mask |= 1ULL << mechanic;
            if (movement)
                for (Mechanics mechanic : Movement)
                    mask |= 1ULL << mechanic;
            unit->RemoveAurasWithMechanic(mask);
        }

        void Immunity(Player* player, std::uint32_t key, bool movement, bool apply)
        {
            for (Mechanics mechanic : LossOfControl)
                player->ApplySpellImmune(key, IMMUNITY_MECHANIC, mechanic, apply);
            if (movement)
                for (Mechanics mechanic : Movement)
                    player->ApplySpellImmune(key, IMMUNITY_MECHANIC, mechanic, apply);
        }

        // The absorb on `target`: `amount` of damage of any school for `seconds`.
        void Absorb(Player* player, Unit* target, double seconds, std::int32_t amount)
        {
            if (Aura* aura = player->AddAura(Shield, target))
            {
                aura->SetMaxDuration(int32(seconds * 1000));
                aura->SetDuration(int32(seconds * 1000));
                if (AuraEffect* effect = aura->GetEffect(EFFECT_0))
                    effect->ChangeAmount(amount);
            }
        }

        void Heal(Player* player, std::uint32_t spellId, double amount)
        {
            auto const* info = sSpellMgr->GetSpellInfo(spellId);
            if (!info || !player->IsAlive() || amount <= 0)
                return;
            HealInfo heal(player, player, uint32(std::min(amount, double(UINT32_MAX))), info, SPELL_SCHOOL_MASK_HOLY);
            player->HealBySpell(heal);
        }

        // Unwelcome Disturbance: every pulse strikes the enemies around the Monk then.
        void Pulse(Player* player, std::uint32_t spellId, unsigned remaining, std::uint64_t gapMs)
        {
            if (!remaining || !player->IsAlive())
                return;
            for (Unit* enemy :
                 Combat::Enemies(player, spellId, player->GetPosition(), Numbers::Num(spellId, "radius_yards")))
                Combat::Strike(player, enemy, spellId, Numbers::Own(spellId, "damage_pct"));
            if (remaining > 1)
                player->m_Events.AddEventAtOffset([player, spellId, remaining, gapMs]
                                                  { Pulse(player, spellId, remaining - 1, gapMs); },
                                                  Milliseconds(gapMs));
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return Row(spellId) != nullptr;
    }

    void Cast(Player* player, std::uint32_t spellId)
    {
        auto const* row = Row(spellId);
        if (!player || !row)
            return;
        std::string_view const rune = row->rune;
        // The shield's seconds: the skill's absorb_duration_seconds, Ascension's duration_seconds.
        double const seconds = rune == "Ascension" ? Numbers::Num(spellId, "duration_seconds")
                                                   : Numbers::Num(spellId, "absorb_duration_seconds");
        bool const movement = rune == "Instant Karma";

        // "A protective shield that absorbs all incoming damage ... and grants immunity to all control impairing
        // effects."
        Cleanse(player, movement);
        Immunity(player, spellId, movement, true);
        Absorb(player, player, seconds, std::numeric_limits<std::int32_t>::max());
        player->m_Events.AddEventAtOffset([player, spellId, movement] { Immunity(player, spellId, movement, false); },
                                          Milliseconds(Millis(seconds)));

        if (rune == "Peaceful Repose")
            Heal(player, spellId,
                 HealRoll(Classes::HealAtLevel(Numbers::Num(spellId, "heal_min_life"), player->GetLevel()),
                          Classes::HealAtLevel(Numbers::Num(spellId, "heal_max_life"), player->GetLevel()),
                          frand(0.0f, 1.0f)));

        if (rune == "Tranquility")
            // "Protect allies within {radius_yards} yards with a shield that removes control impairing effects and ...
            // {absorb_life} damage ... for {absorb_duration_seconds} seconds": the group, the redirect to the Monk is
            // not built.
            if (Group* group = player->GetGroup())
                for (GroupReference* ref = group->GetFirstMember(); ref; ref = ref->next())
                    if (Player* ally = ref->GetSource();
                        ally && ally != player && ally->IsAlive() &&
                        player->IsWithinDistInMap(ally, Numbers::Num(spellId, "radius_yards")))
                    {
                        Cleanse(ally, false);
                        Absorb(player, ally, Numbers::Num(spellId, "absorb_duration_seconds"),
                               std::int32_t(std::min(Classes::HealAtLevel(Numbers::Num(spellId, "absorb_life"), player->GetLevel()),
                                                     double(std::numeric_limits<std::int32_t>::max()))));
                    }

        if (rune == "Unwelcome Disturbance")
        {
            double const interval = Tune("serenity_pulse_seconds");
            unsigned const pulses = Pulses(seconds, interval);
            if (pulses)
                player->m_Events.AddEventAtOffset([player, spellId, pulses, gap = Millis(interval)]
                                                  { Pulse(player, spellId, pulses, gap); },
                                                  Milliseconds(Millis(interval)));
        }

        // "This ability does not start its cooldown until after its effects expire": the cooldown the core just
        // installed is pushed back by the shield's seconds, on every rune (they share it).
        for (auto const& ability : Shells::Abilities)
            if (Skill == ability.skill && player->GetSpellCooldownDelay(ability.id))
                player->ModifySpellCooldown(ability.id, int32(CooldownDelayMs(seconds)));
    }
} // namespace DC::Combat::Monk::Serenity
