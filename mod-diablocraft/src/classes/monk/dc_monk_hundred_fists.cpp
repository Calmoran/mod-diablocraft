/*
 * Way of the Hundred Fists. The sheets: monk_skills.csv, monk_runes.csv, monk_skill_values.csv; the shape of
 * each stage is Power/Monk_WayOfTheHundredFists.pow (stage 1 one target, stage 2 a 90 degree cone of 10 yards with 7
 * punches, stage 3 an area of 10 yards centred 5 yards ahead).
 */

#include "dc_monk_common.h"
#include "dc_monk_fists.h"
#include "dc_monk_hundred_fists.h"
#include "../../stats/dc_stats.h"
#include "ObjectAccessor.h"

#include <limits>

namespace DC::Combat::Monk::HundredFists
{
    namespace
    {
        constexpr std::string_view Skill = "Way of the Hundred Fists";

        struct Fury
        {
            FuryStacks stacks;
            std::uint64_t last = 0; // ms of the last tick (or of the first stack)
            bool running = false;   // a tick is scheduled
        };
        // Per Monk, this skill's own state: its combo counter (not Fists of Thunder's), the stage Aim decided for the
        // punch about to be thrown, Blazing Fists' stacks and the Fists of Fury stacks on each enemy.
        struct State
        {
            Combo combo;
            unsigned stage = 0;
            bool pending = false;
            Stacked blazing;
            std::unordered_map<std::uint64_t, Fury> fury;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, State> states;

        Shells::Ability const* Row(std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && Skill == row->skill ? row : nullptr;
        }

        bool IsRune(Shells::Ability const& row, std::string_view rune)
        {
            return rune == row.rune;
        }

        // The spell id of the skill itself (rune "") or of one of its runes.
        std::uint32_t IdOf(std::string_view rune)
        {
            for (auto const& ability : Shells::Abilities)
                if (Skill == ability.skill && rune == ability.rune)
                    return ability.id;
            return 0;
        }

        // Whether `spellId` is on one of the player's skill buttons (slotted on the bar).
        bool Slotted(Player* player, std::uint32_t spellId)
        {
            for (unsigned slot = 0; slot < Classes::ActiveSlots(); ++slot)
                if (ActionButton const* button = player->GetActionButton(uint8(slot)))
                    if (button->GetType() == ACTION_BUTTON_SPELL && button->GetAction() == spellId)
                        return true;
            return false;
        }

        double Tune(char const* name)
        {
            return DC::Tunables::Get("monk", name);
        }

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        std::uint64_t Millis(double seconds)
        {
            return std::uint64_t(seconds * 1000.0 + 0.5);
        }

        Point PointOf(Position const& position)
        {
            return {position.GetPositionX(), position.GetPositionY()};
        }

        // Fists of Fury's damage over time: one tick, then the next while a stack runs. The tick pays every stack the
        // share of its total that fell since the last tick.
        void Tick(Player* player, ObjectGuid enemy, std::uint32_t spellId)
        {
            double pct = 0;
            bool done = false;
            Unit* target = ObjectAccessor::GetUnit(*player, enemy);
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto stateFound = states.find(player->GetGUID().GetRawValue());
                if (stateFound == states.end())
                    return;
                auto furyFound = stateFound->second.fury.find(enemy.GetRawValue());
                if (furyFound == stateFound->second.fury.end())
                    return;
                Fury& fury = furyFound->second;
                auto const now = Now();
                pct = fury.stacks.Pay(fury.last, now, Numbers::Num(spellId, "damage_pct"),
                                      Millis(Numbers::Num(spellId, "dot_duration_seconds")));
                fury.last = now;
                done = !target || !target->IsAlive() || !player->IsAlive() || fury.stacks.ends.empty();
                if (done)
                    stateFound->second.fury.erase(furyFound);
            }
            if (pct > 0 && target && target->IsAlive() && player->IsAlive())
                Combat::Strike(player, target, spellId, pct, true);
            if (!done)
                player->m_Events.AddEventAtOffset([player, enemy, spellId] { Tick(player, enemy, spellId); },
                                                  Milliseconds(Millis(Tune("hundred_fists_fury_tick_seconds"))));
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return Row(spellId) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        if (!Row(spellId))
            return std::nullopt;
        // The skill's one damage_pct (190%) is the punch of stages 1 and 3 whatever the rune: a rune's own damage_pct
        // is its damage over time (Fists of Fury 60%), its second strike (Hands of Lightning 423%) or its wave
        // (Windforce Flurry 500%), dealt by the code below.
        return Numbers::Get(IdOf(""), "damage_pct");
    }

    void Aim(Player* player, std::uint32_t spellId, std::vector<Unit*>& targets, Unit* aimed)
    {
        if (!player || !Row(spellId) || targets.empty())
            return;
        // The primary enemy is the one aimed at, else the nearest in the cone; it is first in the list.
        auto primary = aimed ? std::find(targets.begin(), targets.end(), aimed) : targets.end();
        if (primary == targets.end())
            primary = std::min_element(targets.begin(), targets.end(), [player](Unit* a, Unit* b)
                                       { return player->GetExactDistSq(a) < player->GetExactDistSq(b); });
        std::iter_swap(targets.begin(), primary);
        unsigned stage = 0;
        {
            std::lock_guard<std::mutex> guard(mutex);
            State& state = states[player->GetGUID().GetRawValue()];
            // The shared combo window (fists_combo_*): the same d3planner GenSequence as every Monk primary, one
            // counter for this skill and all its runes.
            auto const window = ComboWindowMs(Tune("fists_combo_window_frames"), Tune("fists_combo_frames_per_second"),
                                              Combat::AttacksPerSecond(player, spellId));
            stage = state.stage = state.combo.Advance(Now(), window);
            state.pending = true;
        }
        if (stage == 1)
            targets.resize(1);
        else if (stage == 3)
        {
            // "AoE radius 10" centred 5 yards in front of the Monk (SF_30, SF_31): every enemy in it takes the hit.
            Point const centre = AoeCentre(PointOf(player->GetPosition()), player->GetOrientation(),
                                           Tune("hundred_fists_stage3_offset_yards"));
            Position const where(float(centre.x), float(centre.y), player->GetPositionZ());
            Unit* first = targets.front();
            std::vector<Unit*> area{first};
            for (Unit* enemy : Combat::Enemies(player, spellId, where, Tune("hundred_fists_stage3_radius_yards")))
                if (enemy != first)
                    area.push_back(enemy);
            targets = std::move(area);
        }
    }

    Punch Begin(Player* player, std::uint32_t spellId, Unit* primary)
    {
        Punch punch;
        auto const* row = Row(spellId);
        if (!player || !row || !primary)
            return punch;
        {
            std::lock_guard<std::mutex> guard(mutex);
            State& state = states[player->GetGUID().GetRawValue()];
            if (!state.pending)
                return punch;
            state.pending = false;
            punch.stage = state.stage;
        }
        if (punch.stage == 2)
        {
            // The second strike's damage is a total shared by its punches (SF_1 x SF_27 = 190%; SF_12 x 10 = 423%).
            bool const lightning = IsRune(*row, "Hands of Lightning");
            auto const total = lightning ? Numbers::Own(spellId, "damage_pct") : Numbers::Get(IdOf(""), "damage_pct");
            punch.pct = HitPct(2, total.value_or(0), Hits(spellId, 2));
        }
        return punch;
    }

    unsigned Hits(std::uint32_t spellId, unsigned stage)
    {
        auto const* row = Row(spellId);
        if (!row)
            return 1;
        // The base skill's 7 is stated only as Hands of Lightning's "from" (monk_skill_values.csv).
        std::uint32_t const hands = IdOf("Hands of Lightning");
        return StageHits(stage, IsRune(*row, "Hands of Lightning"), unsigned(Numbers::Num(hands, "hit_count", "from")),
                         unsigned(Numbers::Num(hands, "hit_count", "to")));
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets, Punch const& punch)
    {
        auto const* row = Row(spellId);
        if (!player || !row || targets.empty() || !punch.stage)
            return;
        if (punch.stage == 2 && punch.pct)
        {
            // The cast path dealt each enemy its first punch at the stage's percentage; the rest of the series follows.
            unsigned const hits = Hits(spellId, 2);
            for (unsigned hit = 1; hit < hits; ++hit)
                for (Unit* enemy : targets)
                    Combat::Strike(player, enemy, spellId, punch.pct);
        }
        if (punch.stage != 3)
            return;
        if (IsRune(*row, "Windforce Flurry") && DC::Tunables::Has("monk", "hundred_fists_wave_width_yards"))
        {
            // "Every third hit also generates a wave of wind ... to enemies directly ahead of you."
            double const length = Tune("hundred_fists_wave_range_yards"),
                         width = Tune("hundred_fists_wave_width_yards");
            Point const from = PointOf(player->GetPosition());
            auto const pct = Numbers::Own(spellId, "damage_pct");
            for (Unit* enemy : Combat::Enemies(player, spellId, player->GetPosition(), length))
                if (InStrip(from, player->GetOrientation(), length, width, PointOf(enemy->GetPosition())))
                    Combat::Strike(player, enemy, spellId, pct);
        }
        if (IsRune(*row, "Assimilation"))
        {
            // "Each enemy hit with the third hit increases your damage by {damage_bonus_pct} for {duration_seconds}
            // seconds": one stack per enemy, the cap a tunable the sheets do not give (blank: none).
            unsigned const cap = DC::Tunables::Has("monk", "hundred_fists_assimilation_max_stacks")
                                     ? unsigned(Tune("hundred_fists_assimilation_max_stacks"))
                                     : std::numeric_limits<unsigned>::max();
            for (std::size_t i = 0; i < targets.size(); ++i)
                Effects::Dealt(player, spellId, Numbers::Num(spellId, "damage_bonus_pct"),
                               Numbers::Num(spellId, "duration_seconds"), cap);
        }
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId)
    {
        auto const* row = Row(spellId);
        if (!player || !target || !row || !IsRune(*row, "Fists of Fury"))
            return;
        bool start = false;
        {
            std::lock_guard<std::mutex> guard(mutex);
            Fury& fury = states[player->GetGUID().GetRawValue()].fury[target->GetGUID().GetRawValue()];
            auto const now = Now();
            fury.stacks.Add(now, Millis(Numbers::Num(spellId, "dot_duration_seconds")),
                            unsigned(Tune("hundred_fists_fury_max_stacks")));
            if (!fury.running)
            {
                fury.running = start = true;
                fury.last = now;
            }
        }
        if (start)
        {
            ObjectGuid const enemy = target->GetGUID();
            player->m_Events.AddEventAtOffset([player, enemy, spellId] { Tick(player, enemy, spellId); },
                                              Milliseconds(Millis(Tune("hundred_fists_fury_tick_seconds"))));
        }
    }

    void Critical(Player* player, std::uint32_t /*hitSpellId*/)
    {
        // "Critical Hits increase your attack speed ...": any critical hit of the Monk's, while Blazing Fists is the
        // rune slotted for the skill (the spell on one of the player's action buttons, as Classes::WriteActionBar puts
        // it).
        std::uint32_t const spellId = IdOf("Blazing Fists");
        if (!player || !spellId || !Slotted(player, spellId))
            return;
        auto const duration = Millis(Numbers::Num(spellId, "duration_seconds"));
        unsigned stacks = 0;
        {
            std::lock_guard<std::mutex> guard(mutex);
            stacks = states[player->GetGUID().GetRawValue()].blazing.Add(
                Now(), duration, unsigned(Numbers::Num(spellId, "max_stacks_count")));
        }
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        double const each = Numbers::Num(spellId, "attack_speed_pct");
        Stats::AddContribution(guid, {Source::Temporary, Stat::AttackSpeed, spellId, each * stacks, Bucket::Flat});
        Stats::AddContribution(guid,
                               {Source::Temporary, Stat::MovementSpeed, spellId, each * stacks, Bucket::Uncapped});
        Stats::Recompute(player);
        // The removal for this crit; a later crit renewed the time, so an early one finds the buff still running.
        player->m_Events.AddEventAtOffset(
            [player, spellId]
            {
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    if (!states[player->GetGUID().GetRawValue()].blazing.Over(Now()))
                        return;
                    states[player->GetGUID().GetRawValue()].blazing = Stacked{};
                }
                std::uint64_t const id = player->GetGUID().GetRawValue();
                Stats::RemoveContribution(id, Source::Temporary, Stat::AttackSpeed, spellId);
                Stats::RemoveContribution(id, Source::Temporary, Stat::MovementSpeed, spellId);
                Stats::Recompute(player);
            },
            Milliseconds(duration + 50));
    }
} // namespace DC::Combat::Monk::HundredFists
