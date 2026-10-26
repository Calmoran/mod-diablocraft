/*
 * The Monk's class code: the dispatch the engine calls (dc_monk.h), and Fists of Thunder.
 */

#include "dc_monk_common.h"
#include "dc_monk_breath_of_heaven_cast.h"
#include "dc_monk_epiphany.h"
#include "dc_monk_deadly_reach_cast.h"
#include "dc_monk_crippling_wave.h"
#include "dc_monk_exploding_palm_cast.h"
#include "dc_monk_cyclone_strike_cast.h"
#include "dc_monk_blinding_flash_cast.h"
#include "dc_monk_fists.h"
#include "dc_monk_mantras_cast.h"
#include "dc_monk_passives_guardians_path_cast.h"
#include "dc_monk_passives_harmony_cast.h"
#include "dc_monk_tempest_rush_cast.h"
#include "dc_monk_lashing_tail_kick_cast.h"
#include "dc_monk_wave_of_light_cast.h"
#include "dc_monk_serenity_cast.h"
#include "dc_monk_seven_sided_strike.h"
#include "dc_monk_inner_sanctuary.h"
#include "dc_monk_spirit.h"
#include "dc_monk_sweeping_wind_cast.h"
#include "../../combat/dc_movement_effects.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_proc_math.h"
#include "ObjectAccessor.h"
#include "Util.h"

namespace DC::Combat::Monk
{
    void Connected(Player* player, std::uint32_t spellId)
    {
        if (!player)
            return;
        Retribution::Touch(player);
        PassivesHarmony::Connected(player, spellId);
        // monk_skill_values.csv: the four primaries' "Generate: N Spirit per attack".
        // A rune that restates it as a different rule (Crippling Wave - Rising Tide's
        // 2.5 per enemy hit) is that rune's own code, not this per-attack payment.
        // Crippling Wave - Rising Tide restates it as the per-enemy extra; the attack still pays the skill's own.
        auto const generated = Wave::Is(spellId) ? Wave::PerAttack(spellId) : Numbers::Get(spellId, "generated_resource");
        if (generated)
            Generate(player, Classes::ClassIdOf(player), spellId, *generated * SpiritFactor(player, spellId) * Passives242::GenerationFactor(player));
        // Sweeping Wind's stacks: every attack of a Spirit Generator.
        Wind::Attack(player, generated && *generated > 0);
        // Breath of Heaven - Infused with Light: extra Spirit from every Spirit generating attack inside its window.
        Breath::Attack(player, generated && *generated > 0);
    }

    // Band of Rue Chambers: a Spirit Generator's own pay is multiplied, and by the resource generation every class's powers raise (Hexing Pants of Mr. Yan). Infused with
    // Light's extra, Inner Storm and Strong Spirit are not Spirit Generators' own pay and are not multiplied.
    double SpiritFactor(Player* player, std::uint32_t spellId)
    {
        auto const* row = Shells::FindAbility(spellId);
        return (row ? ItemPowers::SkillFactor(player, row->skill, "resource_generation_pct") : 1.0) * ItemPowers::GenerationFactor(player);
    }

    namespace
    {
        constexpr std::string_view FistsOfThunder = "Fists of Thunder";
        // Stock "Ice Blast": one instant MOD_STUN effect, mechanic STUN, a frost icon - the freeze the rift elites hold
        // a player with (dc_rift_elites.cpp FREEZE_HOLD). Wind Blast "Freezes enemies": the same hold, for the sheet's
        // seconds.
        constexpr std::uint32_t FreezeHold = 15878;

        Shells::Ability const* FistsOf(std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && FistsOfThunder == row->skill ? row : nullptr;
        }

        bool IsRune(Shells::Ability const& row, std::string_view rune)
        {
            return rune == row.rune;
        }

        double Tune(char const* name)
        {
            return DC::Tunables::Get("monk", name);
        }

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        // Per Monk: the combo, the stage of the punch in flight (the proc of a hit reads its coefficient), and the
        // enemies wearing Static Charge (target guid -> when it ends and the rune's spell, whose numbers the proc
        // deals).
        struct Charge
        {
            std::uint64_t until = 0;
            std::uint32_t spellId = 0;
        };
        struct State
        {
            Combo combo;
            unsigned stage = 0;
            bool proc = false; // inside Static Charge's own damage: it does not roll again
            std::unordered_map<std::uint64_t, Charge> charged;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, State> states;

        void Freeze(Player* player, Unit* target, double seconds)
        {
            if (seconds <= 0 || !target->IsAlive())
                return;
            target->RemoveAurasDueToSpell(FreezeHold, player->GetGUID());
            if (Aura* hold = player->AddAura(FreezeHold, target))
            {
                hold->SetMaxDuration(int32(seconds * 1000));
                hold->SetDuration(int32(seconds * 1000));
            }
        }
    } // namespace

    bool Toggle(Player* player, std::uint32_t spellId)
    {
        return TempestRush::Toggle(player, spellId);
    }

    bool Apply(Player* player, Unit* target, std::uint32_t spellId)
    {
        return ExplodingPalm::Apply(player, target, spellId);
    }

    void RegisterScripts()
    {
        ExplodingPalm::RegisterScripts();
        MysticAlly::RegisterScripts();
        Mantras::RegisterScripts();
        Epiphany::RegisterScripts();
        Passive::RegisterScripts();
        RegisterPassiveScripts();
        PassivesHarmony::RegisterScripts();
    }

    double MissChance(Unit const* attacker)
    {
        return BlindingFlash::MissChance(attacker);
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        if (DashingStrike::Is(spellId))
            return DashingStrike::BasePct(spellId);
        if (DeadlyReach::Is(spellId))
            return DeadlyReach::BasePct(spellId);
        if (HundredFists::Is(spellId))
            return HundredFists::BasePct(spellId);
        if (TempestRush::Is(spellId))
            return TempestRush::BasePct(spellId);
        if (Kick::Is(spellId))
            return Kick::BasePct(spellId);
        if (ExplodingPalm::Is(spellId))
            return ExplodingPalm::BasePct(spellId);
        if (Wind::Is(spellId))
            return Wind::BasePct(spellId);
        if (MysticAlly::Is(spellId))
            return MysticAlly::BasePct(spellId);
        if (SevenSided::Is(spellId))
            return SevenSided::BasePct(spellId);
        if (auto epiphany = Epiphany::BasePct(spellId))
            return epiphany;
        auto const* row = FistsOf(spellId);
        if (!row)
            return std::nullopt;
        // monk_skill_values.csv: the skill's "hit" (200%) is the punch of stages 1 and 2, and a rune inherits it.
        // Thunderclap alone replaces the punch: its three stages all deal 120% (Monk_FistsofThunder.pow SF_7-SF_9, the
        // rune's one damage_pct row), the shockwave around the target dealing the same.
        if (IsRune(*row, "Thunderclap"))
            return Numbers::Own(spellId, "damage_pct");
        return Numbers::Get(spellId, "damage_pct", "hit");
    }

    void Aim(Player* player, std::uint32_t spellId, std::vector<Unit*>& targets, Unit* aimed)
    {
        HundredFists::Aim(player, spellId, targets, aimed);
        CycloneStrike::Aim(player, spellId, targets);
    }

    void Critical(Player* player, std::uint32_t spellId)
    {
        HundredFists::Critical(player, spellId);
    }

    bool CanCast(Player* player, std::uint32_t spellId)
    {
        return SevenSided::CanCast(player, spellId);
    }

    bool Delayed(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets, Unit* aimed)
    {
        // The cast returns here before Cast: Mythic Rhythm's bonus is spent now, and the strikes carry it.
        if (SevenSided::Is(spellId))
            PassivesHarmony::Cast(player, spellId);
        return SevenSided::Start(player, spellId, targets, aimed);
    }

    bool Approach(Player* player, std::uint32_t spellId, Unit* selected)
    {
        return Epiphany::Dash(player, spellId, selected);
    }

    Punch Begin(Player* player, std::uint32_t spellId, Unit* primary)
    {
        Epiphany::Dash(player, spellId, primary);
        if (DeadlyReach::Is(spellId))
            return DeadlyReach::Begin(player, spellId, primary);
        if (HundredFists::Is(spellId))
            return HundredFists::Begin(player, spellId, primary);
        if (TempestRush::Is(spellId))
            return TempestRush::Begin(player, spellId);
        Punch punch;
        if (player && Wave::Is(spellId))
        {
            // Crippling Wave's own counter (dc_monk_crippling_wave.cpp); it changes nobody's percentage.
            punch.stage = Wave::Begin(player, spellId);
            return punch;
        }
        auto const* row = FistsOf(spellId);
        if (!player || !row || !primary)
            return punch;
        // One counter for the skill and all its runes (docs/research/monk/fists-of-thunder-rules.md section 4). It is
        // kept alive by a window after each punch, whatever the target (sections 1 and 6.1); a window of 0 (an open
        // tunable) leaves every punch at stage 1.
        auto const window = ComboWindowMs(Tune("fists_combo_window_frames"), Tune("fists_combo_frames_per_second"),
                                          Combat::AttacksPerSecond(player, spellId));
        {
            std::lock_guard<std::mutex> guard(mutex);
            State& state = states[player->GetGUID().GetRawValue()];
            punch.stage = state.stage = state.combo.Advance(Now(), window);
        }
        // The third hit: "{damage_pct:third_hit} weapon damage as Lightning split between all enemies in front of you"
        // - the enemies inside a sphere centred on the primary target (section 6.2). Thunderclap's third hit is its
        // 120% shockwave with a knockback, not this.
        if (punch.stage == 3 && !IsRune(*row, "Thunderclap"))
            if (auto total = Numbers::Get(spellId, "damage_pct", "third_hit"))
            {
                for (Unit* enemy :
                     Combat::Enemies(player, spellId, primary->GetPosition(), Tune("fists_stage3_radius_yards")))
                    if (enemy != primary)
                        punch.others.push_back(enemy);
                punch.pct = SplitPct(*total, 1 + unsigned(punch.others.size()));
            }
        return punch;
    }

    std::vector<Unit*> Beside(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        if (Kick::Is(spellId))
            return Kick::Beside(player, spellId, targets);
        return {};
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets, Punch const& punch)
    {
        if (Healing::Is(spellId))
            return Healing::Cast(player, spellId, targets);
        Healing::Touch(player);
        DeadlyReach::Spent(player, spellId);
        Passive::Cast(player, spellId);
        PassivesHarmony::Cast(player, spellId);
        if (DashingStrike::Is(spellId))
            return DashingStrike::Cast(player, spellId, targets);
        if (Sanctuary::Is(spellId))
            return Sanctuary::Cast(player, spellId);
        if (DeadlyReach::Is(spellId))
            return DeadlyReach::Cast(player, spellId, targets, punch);
        if (HundredFists::Is(spellId))
            return HundredFists::Cast(player, spellId, targets, punch);
        if (TempestRush::Is(spellId))
            return TempestRush::Cast(player, spellId);
        if (player && Wave::Is(spellId))
        {
            Wave::Cast(player, spellId, targets, punch.stage);
            return;
        }
        if (Kick::Is(spellId))
            return Kick::Cast(player, spellId, targets);
        if (ExplodingPalm::Is(spellId))
            return ExplodingPalm::Cast(player, spellId, targets);
        if (Wind::Is(spellId))
            return Wind::Cast(player, spellId);
        CycloneStrike::Cast(player, spellId);
        if (Breath::Is(spellId))
            return Breath::Cast(player, spellId, targets);
        if (MysticAlly::Is(spellId))
            return MysticAlly::Cast(player, spellId);
        if (BlindingFlash::Is(spellId))
            return BlindingFlash::Cast(player, spellId);
        if (Serenity::Is(spellId))
            return Serenity::Cast(player, spellId);
        if (Salvation::Is(spellId))
            return Salvation::Cast(player, spellId, targets);
        Salvation::Touch(player);
        if (Retribution::Is(spellId))
            return Retribution::Cast(player, spellId, targets);
        if (Conviction::Is(spellId))
            return Conviction::Cast(player, spellId, targets);
        Epiphany::Cast(player, spellId);
        auto const* row = FistsOf(spellId);
        if (!player || !row || targets.empty())
            return;
        Unit* primary = targets.front();
        bool const third = punch.stage == 3;
        std::vector<Unit*> struck{primary};

        if (IsRune(*row, "Thunderclap"))
        {
            // "an electric shockwave with every punch that hits all enemies within {radius_yards} yards of your primary
            // enemy". The primary took the punch itself (the same 120%), so the shockwave is the others. Each is a
            // Strike, not a StrikeArea: the cast path calls Connected once for the whole attack, and Spirit is paid per
            // attack.
            for (Unit* enemy :
                 Combat::Enemies(player, spellId, primary->GetPosition(), Numbers::Num(spellId, "radius_yards")))
                if (enemy != primary && Combat::Strike(player, enemy, spellId))
                    struck.push_back(enemy);
            // "... and causes knockback with every third hit": the distance is the power file's SF_21.
            if (third)
                for (Unit* enemy : struck)
                    Abilities::Knockback(player, enemy, Tune("fists_knockback_yards"));
        }
        else if (third)
        {
            // The rest of the third hit's share (the primary's was dealt with the cast).
            for (Unit* enemy : punch.others)
                if (Combat::Strike(player, enemy, spellId, punch.pct))
                    struck.push_back(enemy);
        }

        if (third && IsRune(*row, "Bounding Light"))
        {
            // "Every third hit also releases arcs of holy power, dealing {damage_pct} weapon damage as Holy to up to
            // {target_count} additional enemies": the nearest to the enemy punched that the hit has not struck.
            std::vector<Unit*> candidates;
            for (Unit* enemy :
                 Combat::Enemies(player, spellId, primary->GetPosition(), Tune("fists_arc_search_radius_yards")))
                if (std::find(struck.begin(), struck.end(), enemy) == struck.end())
                    candidates.push_back(enemy);
            std::sort(candidates.begin(), candidates.end(),
                      [primary](Unit* a, Unit* b) { return primary->GetExactDistSq(a) < primary->GetExactDistSq(b); });
            auto const pct = Numbers::Get(spellId, "damage_pct");
            std::size_t const count = std::size_t(Numbers::Num(spellId, "target_count"));
            for (std::size_t i = 0; i < candidates.size() && i < count; ++i)
                Combat::Strike(player, candidates[i], spellId, pct);
        }

        if (third && IsRune(*row, "Wind Blast"))
            for (Unit* enemy : struck)
                Freeze(player, enemy, Numbers::Num(spellId, "freeze_duration_seconds"));

        if (IsRune(*row, "Static Charge"))
        {
            // "applies Static Charge to enemies hit for {duration_seconds} seconds"
            auto const until = Now() + std::uint64_t(Numbers::Num(spellId, "duration_seconds") * 1000);
            std::lock_guard<std::mutex> guard(mutex);
            State& state = states[player->GetGUID().GetRawValue()];
            for (Unit* enemy : struck)
                state.charged[enemy->GetGUID().GetRawValue()] = {until, spellId};
        }
    }

    void Taken(Unit* victim, Unit* attacker)
    {
        Retribution::Taken(victim, attacker);
    }

    void Casting(Player* player, std::uint32_t spellId)
    {
        Epiphany::Casting(player, spellId);
    }

    double Dodge(Unit const* unit)
    {
        return DashingStrike::Dodge(unit) + Salvation::Dodge(unit) + Passives242::Dodge(unit);
    }

    void Multipliers(Player* player, Unit* target, std::uint32_t spellId, DC::Combat::Factors& out)
    {
        PassivesHarmony::Multipliers(player, spellId, out);
        Passives242::Multipliers(player, target, out);
    }

    void Ground(Player* player, std::uint32_t spellId, Position const& aimed)
    {
        if (WaveOfLight::Is(spellId))
            WaveOfLight::Cast(player, spellId, aimed);
    }

    void Mimic(Player* player, std::uint32_t spellId, Unit* target)
    {
        if (!player || !target)
            return;
        if (ExplodingPalm::Is(spellId))
            return ExplodingPalm::Cast(player, spellId, {target});
        if (auto const pct = BasePct(spellId); pct && *pct > 0)
            Combat::Strike(player, target, spellId, pct);
    }

    unsigned WindStacks(Player const* player)
    {
        return Wind::Stacks(player);
    }

    bool SkillActive(Player const* player, std::string const& skill)
    {
        return skill == "Sweeping Wind" && Wind::Active(player);
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId)
    {
        Healing::Landed(player, spellId);
        HundredFists::Landed(player, target, spellId);
        MysticAlly::Landed(player, target, spellId);
        Passive::Landed(player, target, spellId);
        if (!player || !target)
            return;
        Wind::Landed(player);
        Wind::Struck(player, target);
        Conviction::Landed(player, target, spellId);
        Epiphany::Landed(player, target, spellId);
        std::uint32_t rune = 0;
        unsigned stage = 0;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = states.find(player->GetGUID().GetRawValue());
            if (found == states.end() || found->second.proc)
                return;
            State& state = found->second;
            auto const now = Now();
            std::erase_if(state.charged, [now](auto const& entry) { return entry.second.until <= now; });
            auto mark = state.charged.find(target->GetGUID().GetRawValue());
            if (mark == state.charged.end())
                return;
            rune = mark->second.spellId;
            stage = state.stage;
        }
        // "Each time an enemy with Static Charge gets hit by you, there is a chance that every other enemy with Static
        // Charge ... takes {damage_pct} weapon damage". The chance is the proc coefficient of the skill that landed the
        // hit (docs/research/monk/fists-of-thunder-rules.md sections 3 and 6.3); a hit whose spell states none cannot
        // proc. Fists of Thunder states one per stage: 0.427 for the first two punches, 0.308 for the third.
        auto const coefficient = FistsOf(spellId)
                                     ? Numbers::Get(spellId, "proc_coefficient", stage == 3 ? "third_hit" : "hit")
                                     : Numbers::Get(spellId, "proc_coefficient");
        if (!Proc::Rolls(coefficient, [](float pct) { return roll_chance_f(pct); }))
            return;
        std::vector<Unit*> others;
        {
            std::lock_guard<std::mutex> guard(mutex);
            State& state = states[player->GetGUID().GetRawValue()];
            state.proc = true;
            for (auto const& entry : state.charged)
                if (entry.first != target->GetGUID().GetRawValue())
                    if (Unit* other = ObjectAccessor::GetUnit(*player, ObjectGuid(entry.first)))
                        if (other->IsAlive() && target->GetExactDist(other) <= Numbers::Num(rune, "radius_yards"))
                            others.push_back(other);
        }
        for (Unit* other : others)
            Combat::Strike(player, other, rune, Numbers::Get(rune, "damage_pct"));
        std::lock_guard<std::mutex> guard(mutex);
        states[player->GetGUID().GetRawValue()].proc = false;
    }
} // namespace DC::Combat::Monk
