/*
 * Ghost Wolf and its five runes. The skill is the form of the stock "Ghost Wolf" aura on the Shaman: here, its seconds,
 * the movement speed, the immunity to slows and roots while it stands, the end that casting any other skill gives it,
 * and each rune's part (Spirit Walk's longer form and stripped control effects, Wind Rush's two charges, Thunderous
 * Paws' trail of lightning, Spectral Recovery's heal and Blazing Spirit's explosion at the end).
 */

#include "dc_shaman_ghost_wolf.h"
#include "dc_shaman_common.h"
#include "dc_shaman_effects.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_control_immunity.h"
#include "../../combat/dc_ground_device.h"
#include "SpellAuraEffects.h"
#include "SpellDefines.h"

#include <algorithm>
#include <chrono>
#include <map>
#include <mutex>

namespace DC::Combat::Shaman::GhostWolf
{
    namespace
    {
        constexpr std::string_view Skill = "Ghost Wolf";
        // Stock "Ghost Wolf" (2645): the shapeshift into the wolf and a movement speed effect; the module sets the
        // speed to the sheet's and the seconds to the form's.
        constexpr std::uint32_t FormAura = 2645;
        // The mechanics a wolf is immune to: slows and roots.
        constexpr std::uint64_t Impairing = (1ull << MECHANIC_ROOT) | (1ull << MECHANIC_SNARE);

        Shells::Ability const* RowOf(std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && Skill == row->skill ? row : nullptr;
        }

        std::uint32_t BaseId()
        {
            for (auto const& row : Shells::Abilities)
                if (Skill == row.skill && !*row.rune)
                    return row.id;
            return 0;
        }

        std::uint32_t Millis(double seconds)
        {
            return std::uint32_t(seconds * 1000.0 + 0.5);
        }

        struct Form
        {
            std::uint32_t spellId = 0;
            Rune rune = Rune::None;
            std::uint64_t until = 0;
            std::uint64_t stamp = 0;
            bool active = false;
        };
        std::mutex mutex;
        std::map<std::uint64_t, Form> forms;
        std::map<std::uint64_t, ChargeStore> charges;
        std::uint64_t stamps = 0;

        std::uint64_t Key(Player const* player)
        {
            return player->GetGUID().GetRawValue();
        }

        void Immune(Player* player, std::uint32_t key, bool on)
        {
            for (unsigned mechanic : {unsigned(MECHANIC_ROOT), unsigned(MECHANIC_SNARE)})
                player->ApplySpellImmune(key, IMMUNITY_MECHANIC, mechanic, on);
            for (AuraType aura : {SPELL_AURA_MOD_ROOT, SPELL_AURA_MOD_DECREASE_SPEED})
                player->ApplySpellImmune(key, IMMUNITY_STATE, aura, on);
            if (on)
                player->RemoveAurasWithMechanic(Impairing);
        }

        // The form ends: the aura and the immunity come off, and the rune does its part at the end.
        void End(Player* player, std::uint64_t stamp)
        {
            Form form;
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto const found = forms.find(Key(player));
                if (found == forms.end() || !found->second.active || (stamp && found->second.stamp != stamp))
                    return;
                form = found->second;
                found->second.active = false;
            }
            player->RemoveAurasDueToSpell(FormAura);
            Immune(player, form.spellId, false);
            if (!player->IsAlive() || !player->IsInWorld())
                return;
            if (HealsAtEnd(form.rune))
                Shaman::Heal(player, form.spellId,
                             HealOf(player->GetMaxHealth(), Numbers::Num(form.spellId, "heal_pct")));
            if (ExplodesAtEnd(form.rune))
                Combat::StrikeArea(player, form.spellId, player->GetPosition(),
                                   Numbers::Num(form.spellId, "radius_yards"),
                                   Numbers::Num(form.spellId, "damage_pct"));
        }

        // Thunderous Paws: a patch of lightning where the wolf is, every drop, for the form's seconds.
        void Trail(Player* player, std::uint64_t stamp, unsigned left)
        {
            std::uint32_t spellId;
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto const found = forms.find(Key(player));
                if (found == forms.end() || !found->second.active || found->second.stamp != stamp)
                    return;
                spellId = found->second.spellId;
            }
            if (!left || !player->IsAlive() || !player->IsInWorld())
                return;
            double const tick = Tunable("ghost_wolf_trail_tick_seconds"),
                         drop = Tunable("ghost_wolf_trail_drop_seconds");
            double const pct = PulsePct(Numbers::Num(spellId, "damage_pct"), tick);
            GroundDevice::Setup patch;
            patch.kind = BaseId();
            patch.record = spellId;
            patch.spec.mode = GroundDevice::Mode::Periodic;
            patch.spec.radiusYards = Tunable("ghost_wolf_trail_radius_yards");
            patch.spec.lifetimeMs = Numbers::Num(spellId, "duration_seconds") * 1000.0;
            patch.spec.intervalMs = tick * 1000.0;
            patch.spec.most = std::size_t(Tunable("ghost_wolf_trail_most"));
            patch.fire = [spellId, pct](Player* owner, Position const&, std::vector<Unit*> const& enemies)
            {
                for (Unit* enemy : enemies)
                    Combat::Strike(owner, enemy, spellId, pct, true);
            };
            GroundDevice::Place(player, patch, player->GetPosition());
            player->m_Events.AddEventAtOffset([player, stamp, left] { Trail(player, stamp, left - 1); },
                                              std::chrono::milliseconds(Millis(drop)));
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        // The skill is a form: its runes' `damage_pct` is their trail's and their explosion's, never a hit of the cast.
        return RowOf(spellId) ? std::optional<double>(0.0) : std::nullopt;
    }

    void Casting(Player* player, std::uint32_t spellId)
    {
        auto const* row = RowOf(spellId);
        bool standing;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto const found = forms.find(Key(player));
            standing = found != forms.end() && found->second.active;
        }
        if (EndsForm(standing, row != nullptr))
            End(player, 0);
        if (!row)
            return;
        // A new Ghost Wolf over a standing one: the old form ends first, its rune's end included.
        if (standing)
            End(player, 0);
        Rune const rune = RuneOf(row->rune);
        double const seconds =
            FormSeconds(rune, Numbers::Num(BaseId(), "duration_seconds"), Numbers::Num(spellId, "duration_seconds"));
        std::uint64_t stamp;
        {
            std::lock_guard<std::mutex> guard(mutex);
            Form& form = forms[Key(player)];
            form = {spellId, rune, Now() + Millis(seconds), stamp = ++stamps, true};
        }
        player->RemoveAurasDueToSpell(FormAura);
        if (Aura* aura = player->AddAura(FormAura, player))
        {
            for (uint8 slot = 0; slot < MAX_SPELL_EFFECTS; ++slot)
                if (AuraEffect* effect = aura->GetEffect(slot))
                {
                    if (effect->GetAuraType() == SPELL_AURA_MOD_INCREASE_SPEED)
                        effect->ChangeAmount(int32(Numbers::Num(spellId, "movement_speed_pct")));
                    else if (effect->GetAuraType() != SPELL_AURA_MOD_SHAPESHIFT)
                        effect->ChangeAmount(0);
                }
            aura->SetMaxDuration(int32(Millis(seconds)));
            aura->SetDuration(int32(Millis(seconds)));
        }
        Immune(player, spellId, true);
        if (StripsControl(rune))
            ControlImmunity::Strip(player);
        if (LaysTrail(rune))
            Trail(player, stamp, Patches(seconds, Tunable("ghost_wolf_trail_drop_seconds")));
        player->m_Events.AddEventAtOffset([player, stamp] { End(player, stamp); },
                                          std::chrono::milliseconds(Millis(seconds) + 1));
    }

    void Cast(Player* player, std::uint32_t spellId)
    {
        auto const* row = RowOf(spellId);
        if (!player || !row || RuneOf(row->rune) != Rune::WindRush)
            return;
        // "Has {charge_count} charges. You gain a charge every {charge_recharge_seconds} seconds": the charges in place
        // of the cooldown. The core put the record's cooldown on the button; a charge left clears it, none left holds
        // it until the next lands.
        unsigned const cap = unsigned(Numbers::Num(spellId, "charge_count"));
        std::uint64_t const period =
            ReducedCooldownMilliseconds(player, spellId, Millis(Numbers::Num(spellId, "charge_recharge_seconds")));
        std::uint64_t wait;
        {
            std::lock_guard<std::mutex> guard(mutex);
            wait = charges[Key(player)].Spend(Now(), cap, period);
        }
        SendSkillCooldown(player, spellId, std::uint32_t(wait));
    }

    void Upkeep(Player* player)
    {
        std::uint64_t stamp = 0;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto const found = forms.find(Key(player));
            if (found == forms.end() || !found->second.active)
                return;
            // The wolf ends at its time, or when the aura is gone (the Shaman cancelled it).
            if (found->second.until > Now() && player->HasAura(FormAura))
                return;
            stamp = found->second.stamp;
        }
        End(player, stamp);
    }

    void Forget(Player* player)
    {
        End(player, 0);
        std::lock_guard<std::mutex> guard(mutex);
        forms.erase(Key(player));
        charges.erase(Key(player));
    }
} // namespace DC::Combat::Shaman::GhostWolf
