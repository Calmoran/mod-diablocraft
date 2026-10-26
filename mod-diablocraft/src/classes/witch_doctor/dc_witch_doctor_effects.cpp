/*
 * The Witch Doctor's holds on an enemy: fear, root, a slow, confusion and a stun, each a stock control aura set to the skill's
 * number; and the Life a skill gives back.
 */

#include "dc_witch_doctor_effects.h"
#include "Player.h"
#include "SpellAuraEffects.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>

namespace DC::Combat::WitchDoctor
{
    namespace
    {
        // Stock "Fear" (5782): a MOD_FEAR effect, mechanic Fear, with the fleeing creature's own run speed beside it: an enemy Feared runs from
        // the Witch Doctor.
        constexpr std::uint32_t FearHold = 5782;
        // Stock "Earthgrab": one MOD_ROOT effect, mechanic Root - the Immobilize.
        constexpr std::uint32_t RootHold = 64695;
        // Stock "Ice Blast": one instant MOD_STUN effect, mechanic STUN.
        constexpr std::uint32_t StunHold = 15878;
        // Stock "Dizzy" (9992): one MOD_CONFUSE effect, no other: the confusion of an enemy (it wanders and does not attack).
        constexpr std::uint32_t ConfuseHold = 9992;
        // Stock "Dazed" (50259): one MOD_DECREASE_SPEED effect, Snare mechanic; its amount is set to the slow.
        constexpr std::uint32_t SlowHold = 50259;

        // Stock "Polymorph: Chicken" (228): a TRANSFORM into the chicken, a MOD_SILENCE and a MOD_DAMAGE_PERCENT_DONE of -67%, no
        // interrupt flag (damage does not break it).
        constexpr std::uint32_t HexHold = 228;
        // Stock "Pacify" (10730): one MOD_PACIFY effect, no interrupt flag.
        constexpr std::uint32_t PacifyHold = 10730;
        // Stock "Chicken" (3245): one TRANSFORM effect into the chicken.
        constexpr std::uint32_t ChickenForm = 3245;

        // Stock "Power Word: Shield" (rank 1): one SCHOOL_ABSORB effect of every school; the amount and the time are set below.
        constexpr std::uint32_t ShieldHold = 17;

        // A stock aura of `seconds` on `target`, a second one restarting it; `amount` (when not 0) is the first effect's number.
        // True when the aura took hold.
        bool Hold(Player* player, Unit* target, std::uint32_t aura, double seconds, int amount = 0)
        {
            if (!player || !target || seconds <= 0 || !target->IsAlive())
                return false;
            target->RemoveAurasDueToSpell(aura, player->GetGUID());
            Aura* hold = player->AddAura(aura, target);
            if (!hold)
                return false;
            if (amount)
                if (AuraEffect* effect = hold->GetEffect(EFFECT_0))
                    effect->ChangeAmount(amount);
            hold->SetMaxDuration(int32(seconds * 1000));
            hold->SetDuration(int32(seconds * 1000));
            return true;
        }
    } // namespace

    bool Fear(Player* player, Unit* target, double seconds)
    {
        return Hold(player, target, FearHold, seconds);
    }

    bool Root(Player* player, Unit* target, double seconds)
    {
        return Hold(player, target, RootHold, seconds);
    }

    bool HexEnemy(Player* player, Unit* target, double seconds)
    {
        if (!Hold(player, target, HexHold, seconds))
            return false;
        Hold(player, target, PacifyHold, seconds);
        return true;
    }

    void TurnIntoChicken(Player* player, double seconds)
    {
        if (Hold(player, player, ChickenForm, seconds))
            Hold(player, player, PacifyHold, seconds);
    }

    void EndChicken(Player* player)
    {
        if (!player)
            return;
        player->RemoveAurasDueToSpell(ChickenForm, player->GetGUID());
        player->RemoveAurasDueToSpell(PacifyHold, player->GetGUID());
    }

    void Slow(Player* player, Unit* target, double pct, double seconds)
    {
        if (pct > 0)
            Hold(player, target, SlowHold, seconds, -static_cast<int>(std::lround(pct)));
    }

    void Confuse(Player* player, Unit* target, double seconds)
    {
        Hold(player, target, ConfuseHold, seconds);
    }

    void Stun(Player* player, Unit* target, double seconds)
    {
        Hold(player, target, StunHold, seconds);
    }

    void Heal(Player* player, std::uint32_t spellId, double amount)
    {
        if (!player || !player->IsAlive() || amount <= 0)
            return;
        if (SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId))
        {
            HealInfo heal(player, player, std::uint32_t(std::min(amount, double(UINT32_MAX))), info,
                          SPELL_SCHOOL_MASK_NORMAL);
            player->HealBySpell(heal);
        }
    }

    void Invulnerable(Player* player, double seconds)
    {
        if (!player || !player->IsAlive() || seconds <= 0)
            return;
        player->RemoveAurasDueToSpell(ShieldHold, player->GetGUID());
        if (Aura* shield = player->AddAura(ShieldHold, player))
        {
            shield->SetMaxDuration(int32(seconds * 1000));
            shield->SetDuration(int32(seconds * 1000));
            if (AuraEffect* effect = shield->GetEffect(EFFECT_0))
                effect->ChangeAmount(std::numeric_limits<std::int32_t>::max());
        }
    }
} // namespace DC::Combat::WitchDoctor
