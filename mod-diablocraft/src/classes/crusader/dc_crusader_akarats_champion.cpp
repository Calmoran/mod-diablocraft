/*
 * Akarat's Champion and its five runes: the Crusader's transformation. It lasts the sheet's 20 seconds and, while it
 * does, every hit of the Crusader deals more, and Wrath comes in faster; the runes add a burn, more Wrath, a cut to the
 * other cooldowns, Armor and one saved life, or attack speed. The skill deals no damage of its own. The dispatch is in
 * dc_crusader.cpp.
 */

#include "dc_crusader_akarats_champion.h"
#include "dc_crusader_common.h"
#include "dc_crusader_dot.h"

#include <chrono>
#include <cmath>
#include <mutex>
#include <unordered_map>

namespace DC::Combat::Crusader::AkaratsChampion
{
    namespace
    {
        constexpr std::string_view Skill = "Akarat's Champion";
        // The Wrath regeneration is paid once a second, the unit the sheet states it in.
        constexpr std::chrono::milliseconds PaymentEvery{1000};

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        double Tune(char const* name)
        {
            return DC::Tunables::Get("crusader", name);
        }

        // The transformation each Crusader wears now: the rune's spell, when its time is over, whether Prophet has used
        // its saved life, and when Fire Starter last burned each enemy.
        struct Form
        {
            std::uint32_t spellId = 0;
            std::uint64_t until = 0;
            bool saved = false;
            std::unordered_map<std::uint64_t, std::uint64_t> burned;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, Form> forms;

        // The form of `player` that is still on, copied out; nothing once its time is over.
        std::optional<Form> Current(Player* player)
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = forms.find(player->GetGUID().GetRawValue());
            if (found == forms.end())
                return std::nullopt;
            if (!Active(Now(), found->second.until))
            {
                forms.erase(found);
                return std::nullopt;
            }
            return found->second;
        }

        // One second's Wrath. The payments left bound the transformation by themselves.
        void Pay(Player* player, std::uint32_t spellId, unsigned left, double points)
        {
            if (!player->IsInWorld() || !player->IsAlive() || left == 0)
                return;
            GainWrath(player, spellId, points);
            if (left > 1)
                player->m_Events.AddEventAtOffset([player, spellId, left, points]
                                                  { Pay(player, spellId, left - 1, points); }, PaymentEvery);
        }

        // Rally: every other ability that is cooling down comes back sooner. The records of a skill's runes each hold
        // the cooldown the core installed, so each is cut.
        void Rally(Player* player, double seconds)
        {
            for (auto const& row : Shells::Abilities)
                if (Skill != row.skill)
                    if (std::uint32_t const left = player->GetSpellCooldownDelay(row.id))
                        player->ModifySpellCooldown(row.id, -static_cast<std::int32_t>(CutMs(left, seconds)));
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
        return 0.0;
    }

    void Cast(Player* player, std::uint32_t spellId)
    {
        if (!player || !Is(spellId))
            return;
        Rune const rune = RuneAt(spellId);
        double const seconds = Numbers::Num(spellId, "duration_seconds");
        {
            std::lock_guard<std::mutex> guard(mutex);
            Form form;
            form.spellId = spellId;
            form.until = Now() + static_cast<std::uint64_t>(std::llround(std::max(0.0, seconds) * 1000.0));
            forms[player->GetGUID().GetRawValue()] = std::move(form);
        }
        // "increasing your Wrath regeneration by {regen_per_second_resource}": the skill's 5, Embodiment of Power's 10.
        if (unsigned const payments = Payments(seconds))
        {
            double const regen = Numbers::Num(spellId, "regen_per_second_resource");
            player->m_Events.AddEventAtOffset([player, spellId, payments, regen]
                                              { Pay(player, spellId, payments, regen); }, PaymentEvery);
        }
        switch (rune)
        {
            case Rune::Prophet:
                // "Gain {armor_pct} additional Armor while Akarat's Champion is active."
                Buffs::Stack(player, spellId, Stat::Armor, Bucket::Percent, Numbers::Num(spellId, "armor_pct"), 1,
                             seconds);
                break;
            case Rune::Hasteful:
                // "Gain {attack_speed_pct} increased attack speed while Akarat's Champion is active."
                Buffs::Stack(player, spellId, Stat::AttackSpeed, Bucket::Flat,
                             Numbers::Num(spellId, "attack_speed_pct"), 1, seconds);
                break;
            case Rune::Rally:
                Rally(player, Numbers::Num(spellId, "cooldown_reduction_seconds"));
                break;
            default:
                break;
        }
    }

    void Landed(Player* player, Unit* target, std::uint32_t /*spellId*/)
    {
        if (!player || !target)
            return;
        auto const form = Current(player);
        if (!form || RuneAt(form->spellId) != Rune::FireStarter)
            return;
        std::uint64_t const now = Now();
        std::uint64_t const gap =
            BurnGapMs(Combat::AttacksPerSecond(player), Tune("akarats_champion_fire_starter_icd_factor"));
        std::uint64_t const enemy = target->GetGUID().GetRawValue();
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = forms.find(player->GetGUID().GetRawValue());
            if (found == forms.end() || found->second.spellId != form->spellId)
                return;
            auto last = found->second.burned.find(enemy);
            if (!BurnDue(last != found->second.burned.end(), now, last != found->second.burned.end() ? last->second : 0,
                         gap))
                return;
            found->second.burned[enemy] = now;
        }
        // "Dealing damage burns enemies with the power of Akarat, dealing {damage_pct} weapon damage as Fire over
        // {dot_duration_seconds} seconds." The tick length is a tunable with no number yet, and without it nothing
        // burns.
        Dot::Burn(player, target, form->spellId, Numbers::Num(form->spellId, "damage_pct"),
                  Numbers::Num(form->spellId, "dot_duration_seconds"),
                  Tune("akarats_champion_fire_starter_tick_seconds"));
    }

    void Multipliers(Player* player, DC::Combat::Factors& out)
    {
        if (!player)
            return;
        auto const form = Current(player);
        if (!form)
            return;
        // "increasing your damage by {damage_bonus_pct}": one multiplier of its own on every hit.
        if (double const bonus = DamageBonusPct(true, Numbers::Num(form->spellId, "damage_bonus_pct")))
            AddFactor(out, "Akarat's Champion", bonus);
    }

    void Fatal(Player* player, std::uint32_t& damage)
    {
        if (!player || !damage)
            return;
        std::lock_guard<std::mutex> guard(mutex);
        auto found = forms.find(player->GetGUID().GetRawValue());
        if (found == forms.end() || !Active(Now(), found->second.until))
            return;
        if (!Saves(RuneAt(found->second.spellId), found->second.saved, damage, player->GetHealth()))
            return;
        // The hook runs before the blow is dealt: the Life is full again and the blow is nothing.
        found->second.saved = true;
        player->SetHealth(player->GetMaxHealth());
        damage = 0;
    }
} // namespace DC::Combat::Crusader::AkaratsChampion
