/*
 * Blinding Flash and its five runes.
 */

#include "dc_monk_blinding_flash_cast.h"
#include "dc_monk_blinding_flash.h"
#include "../dc_resources.h"
#include "dc_monk_common.h"
#include "../../rifts/dc_rifts.h"
#include "ObjectAccessor.h"
#include "SpellAuraEffects.h"

#include <chrono>

namespace DC::Combat::Monk::BlindingFlash
{
    namespace
    {
        constexpr std::string_view Skill = "Blinding Flash";
        // Stock "Dizzy" (9992): one MOD_CONFUSE effect, no other: the blind of an ordinary enemy (it wanders and does
        // not attack). Stock "Blind" (2094) also slows, which only Mystifying Light does.
        constexpr std::uint32_t Dizzy = 9992;
        // Stock "Dazed" (50259): one MOD_DECREASE_SPEED effect; Mystifying Light's slow.
        constexpr std::uint32_t Slowed = 50259;

        Shells::Ability const* Row(std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && Skill == row->skill ? row : nullptr;
        }

        bool IsRune(std::uint32_t spellId, std::string_view rune)
        {
            auto const* row = Row(spellId);
            return row && rune == row->rune;
        }

        double Tune(char const* name)
        {
            return DC::Tunables::Get("monk", name);
        }

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        bool Elite(Unit* enemy)
        {
            Creature* creature = enemy->ToCreature();
            return creature && (creature->isElite() || DC::Rifts::IsPromotedElite(creature));
        }

        // A stock aura of `seconds` on `target`, its first effect set to `amount` (0 keeps the record's). Control
        // immunity answers nothing.
        void Hold(Player* player, Unit* target, std::uint32_t aura, int amount, double seconds)
        {
            if (seconds <= 0 || !target->IsAlive())
                return;
            target->RemoveAurasDueToSpell(aura, player->GetGUID());
            if (Aura* held = player->AddAura(aura, target))
            {
                if (amount)
                    if (AuraEffect* effect = held->GetEffect(EFFECT_0))
                        effect->ChangeAmount(amount);
                held->SetMaxDuration(int32(seconds * 1000));
                held->SetDuration(int32(seconds * 1000));
            }
        }

        std::mutex mutex;
        Blind blind;
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return Row(spellId) != nullptr;
    }

    double MissChance(Unit const* attacker)
    {
        if (!attacker)
            return 0.0;
        std::lock_guard<std::mutex> guard(mutex);
        return blind.Chance(attacker->GetGUID().GetRawValue(), Now());
    }

    void Cast(Player* player, std::uint32_t spellId)
    {
        if (!player || !Row(spellId))
            return;
        double const seconds = Numbers::Num(spellId, "blind_duration_seconds");
        double const missPct = Numbers::Num(spellId, "miss_chance_pct");
        // "You deal {damage_bonus_pct} increased damage for {duration_seconds} seconds after using Blinding Flash."
        if (IsRune(spellId, "Faith in the Light"))
            Effects::Dealt(player, spellId, Numbers::Num(spellId, "damage_bonus_pct"),
                           Numbers::Num(spellId, "duration_seconds"));

        // "blinds all enemies within {radius_yards} yards for {blind_duration_seconds} seconds" (Self Reflection: 6).
        unsigned blinded = 0;
        for (Unit* enemy :
             Combat::Enemies(player, spellId, player->GetPosition(), Numbers::Num(spellId, "radius_yards")))
        {
            if (!enemy->IsAlive())
                continue;
            ++blinded;
            // "Elite enemies recover faster, but suffer a {miss_chance_pct} chance to miss with attacks": an elite
            // misses for the whole blind and is disoriented only as long as the elite tunable says (blank: not at all).
            bool const elite = Elite(enemy);
            double const eliteSeconds = DC::Tunables::Has("monk", "blinding_flash_elite_disorient_seconds")
                                            ? Tune("blinding_flash_elite_disorient_seconds")
                                            : 0.0;
            Hold(player, enemy, Dizzy, 0, DisorientSeconds(elite, seconds, eliteSeconds));
            {
                std::lock_guard<std::mutex> guard(mutex);
                blind.Set(enemy->GetGUID().GetRawValue(), Now() + std::uint64_t(seconds * 1000.0),
                          MissPct(elite, missPct));
            }
            // Mystifying Light: "Blinded enemies are also slowed by {slow_pct} for {slow_duration_seconds} seconds."
            if (IsRune(spellId, "Mystifying Light"))
                Hold(player, enemy, Slowed, -int(Numbers::Num(spellId, "slow_pct") + 0.5),
                     Numbers::Num(spellId, "slow_duration_seconds"));
            // Crippling Light: "... deal {enemy_damage_pct} reduced damage for {duration_seconds} seconds after the
            // Blind wears off."
            if (IsRune(spellId, "Crippling Light"))
            {
                double const pct = Numbers::Num(spellId, "enemy_damage_pct"),
                             lasts = Numbers::Num(spellId, "duration_seconds");
                player->m_Events.AddEventAtOffset(
                    [player, guid = enemy->GetGUID(), spellId, pct, lasts]
                    {
                        if (Unit* later = ObjectAccessor::GetUnit(*player, guid); later && later->IsAlive())
                            Effects::Weaken(later, spellId, pct, lasts);
                    },
                    std::chrono::milliseconds(WeakenAfterMs(seconds)));
            }
        }
        // Replenishing Light: "Each enemy you Blind restores {gain_resource} Spirit."
        if (IsRune(spellId, "Replenishing Light") && blinded)
            Resources::Energize(player, Resources::Spirit, spellId, Numbers::Num(spellId, "gain_resource") * blinded);
    }
} // namespace DC::Combat::Monk::BlindingFlash
