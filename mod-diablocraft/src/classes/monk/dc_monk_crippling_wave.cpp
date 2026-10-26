/*
 * Crippling Wave and its five runes; the dispatch is in dc_monk.cpp.
 */

#include "dc_monk_crippling_wave.h"
#include "dc_monk_common.h"
#include "dc_monk_fists.h"
#include "dc_monk_spirit.h"
#include "SpellAuraEffects.h"

namespace DC::Combat::Monk::Wave
{
    namespace
    {
        // Stock "Ice Blast", the freeze Fists of Thunder - Wind Blast holds with (dc_monk.cpp): one MOD_STUN, mechanic
        // STUN.
        constexpr std::uint32_t FreezeHold = 15878;
        // Stock "Dazed" (50259): one MOD_DECREASE_SPEED effect, Snare mechanic. The daze's movement half; the amount
        // is set to the sheet's slow_pct below.
        constexpr std::uint32_t DazeMovement = 50259;
        // Stock "Slow" (10371): one MOD_MELEE_HASTE effect on an enemy. The daze's attack-speed half, at
        // attack_speed_pct.
        constexpr std::uint32_t DazeAttacks = 10371;

        Shells::Ability const* Row(std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && std::string_view("Crippling Wave") == row->skill ? row : nullptr;
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

        // The skill's own counter per Monk, its window Fists of Thunder's (one rule for the four primaries).
        std::mutex mutex;
        std::unordered_map<std::uint64_t, Combo> combos;

        // A stock aura of `seconds` on `target`, its first effect set to `amount`. Control immunity answers nothing.
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
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return Row(spellId) != nullptr;
    }

    std::optional<double> PerAttack(std::uint32_t spellId)
    {
        // Rising Tide states generated_resource 2.5 "additional" per enemy: Numbers::Get would answer that for the
        // attack's pay. The attack pays what the skill's row says; the rune's number is paid in Cast.
        if (auto skill = Numbers::Inherited(spellId, "generated_resource"))
            return skill;
        return Numbers::Get(spellId, "generated_resource");
    }

    unsigned Begin(Player* player, std::uint32_t spellId)
    {
        if (!player || !Row(spellId))
            return 0;
        // The same window rule as Fists of Thunder's, its tunables (the planner's GenSequence is shared by the four
        // primaries), a counter of this skill's own.
        auto const window = ComboWindowMs(Tune("fists_combo_window_frames"), Tune("fists_combo_frames_per_second"),
                                          Combat::AttacksPerSecond(player, spellId));
        std::lock_guard<std::mutex> guard(mutex);
        return combos[player->GetGUID().GetRawValue()].Advance(Now(), window);
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets, unsigned stage)
    {
        if (!player || !Row(spellId))
            return;
        // "all enemies in front of you": the cone the cast resolved is the core's stock one (90 degrees); D3's is 180
        // and Tsunami's third attack reaches further, so the enemies of the half-circle the cone did not take are
        // struck here.
        double const base = Combat::TargetRadius(spellId);
        double const reach = Reach(stage, base, Numbers::Own(spellId, "radius_yards").value_or(0));
        float const arc = float(ArcRadians(Tune("crippling_wave_cone_degrees")));
        auto const pct = Numbers::Get(spellId, "damage_pct");
        std::vector<Unit*> struck = targets;
        for (Unit* enemy : Combat::Enemies(player, spellId, player->GetPosition(), reach))
            if (std::find(targets.begin(), targets.end(), enemy) == targets.end() && player->HasInArc(arc, enemy))
                if (Combat::Strike(player, enemy, spellId, pct))
                    struck.push_back(enemy);
        // No enemy in the core's cone but one beside you: the swing still connected, once.
        if (targets.empty() && !struck.empty())
            Combat::Connected(player, spellId, unsigned(struck.size()));

        // Rising Tide: "Each enemy hit generates {generated_resource} additional Spirit", one pay for the whole swing.
        if (IsRune(spellId, "Rising Tide"))
            Generate(
                player, Classes::ClassIdOf(player), spellId,
                RisingTideSpirit(Numbers::Own(spellId, "generated_resource").value_or(0), unsigned(struck.size())) *
                    SpiritFactor(player, spellId));

        // Concussion: "Enemies hit by Crippling Wave deal {enemy_damage_pct} less damage for {duration_seconds}
        // seconds". Breaking Wave: "... take {damage_taken_pct} additional damage from all attacks for
        // {duration_seconds} seconds". Every swing, not only the third; the key is the rune's spell id, so a new swing
        // refreshes it.
        if (IsRune(spellId, "Concussion"))
            for (Unit* enemy : struck)
                Effects::Weaken(enemy, spellId, Numbers::Num(spellId, "enemy_damage_pct"),
                                Numbers::Num(spellId, "duration_seconds"));
        if (IsRune(spellId, "Breaking Wave"))
            for (Unit* enemy : struck)
                Effects::Taken(enemy, spellId, Numbers::Num(spellId, "damage_taken_pct"),
                               Numbers::Num(spellId, "duration_seconds"));

        if (!IsThird(stage))
            return;
        // "Every third hit also dazes enemies within {radius_yards} yards, slowing their movement speed by {slow_pct}
        // and attack speed by {attack_speed_pct} for {duration_seconds} seconds": every enemy inside the radius, in
        // front or not (the sheet's words differ from the damage's "in front of you").
        double const seconds = Numbers::Num(spellId, "duration_seconds");
        for (Unit* enemy : Combat::Enemies(player, spellId, player->GetPosition(), reach))
        {
            Hold(player, enemy, DazeMovement, SlowAmount(Numbers::Num(spellId, "slow_pct")), seconds);
            Hold(player, enemy, DazeAttacks, SlowAmount(Numbers::Num(spellId, "attack_speed_pct")), seconds);
        }
        // Tsunami: "... and Freezes enemies for {freeze_duration_seconds} second": the enemies the third attack struck.
        if (IsRune(spellId, "Tsunami"))
            for (Unit* enemy : struck)
                Hold(player, enemy, FreezeHold, 0, Numbers::Num(spellId, "freeze_duration_seconds"));
    }
} // namespace DC::Combat::Monk::Wave
