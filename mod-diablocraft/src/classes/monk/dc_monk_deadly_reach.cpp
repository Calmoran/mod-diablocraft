/*
 * Deadly Reach and its five runes.
 */

#include "dc_monk_deadly_reach_cast.h"
#include "dc_monk_deadly_reach.h"
#include "dc_monk_fists.h"
#include "../dc_resources.h"
#include "dc_monk_common.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Util.h"

namespace DC::Combat::Monk::DeadlyReach
{
    namespace
    {
        constexpr std::string_view Skill = "Deadly Reach";

        Shells::Ability const* RowOf(std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && Skill == row->skill ? row : nullptr;
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

        // The skill's own spell id (the record of the skill without a rune): a rune's numbers that are not the punch's
        // (Scattered Blows' 215% belongs to its fists) leave the punch at the skill's.
        std::uint32_t SkillId()
        {
            for (auto const& row : Shells::Abilities)
                if (Skill == row.skill && !*row.rune)
                    return row.id;
            return 0;
        }

        struct State
        {
            Combo combo;
            NextSpender next; // Strike from Beyond's discount waiting for a spender
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, State> states;
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        auto const* row = RowOf(spellId);
        if (!row)
            return std::nullopt;
        // Scattered Blows' damage_pct (215%) is what each fist deals; the punch stays the skill's 150%.
        if (IsRune(*row, "Scattered Blows"))
            return Numbers::Own(SkillId(), "damage_pct");
        return Numbers::Get(spellId, "damage_pct");
    }

    Punch Begin(Player* player, std::uint32_t spellId, Unit* primary)
    {
        Punch punch;
        if (!player || !RowOf(spellId) || !primary)
            return punch;
        // One counter for the skill and its runes, the planner's shared GenSequence
        // (docs/research/monk/fists-of-thunder-rules.md sections 1, 4 and 6.1), with Fists of Thunder's window
        // tunables: the rule is one for all four primaries.
        auto const window = ComboWindowMs(DC::Tunables::Get("monk", "fists_combo_window_frames"),
                                          DC::Tunables::Get("monk", "fists_combo_frames_per_second"),
                                          Combat::AttacksPerSecond(player, spellId));
        {
            std::lock_guard<std::mutex> guard(mutex);
            punch.stage = states[player->GetGUID().GetRawValue()].combo.Advance(Now(), window);
        }
        // The third hit "reaches 25" (Power/Monk_DeadlyReach.pow SF_20): the cast's own line struck the first 12 yards,
        // so the ones between 12 and 25 yards ahead of the Monk, inside the same width, are struck here.
        // Piercing Trident widens the line of the second and third hits: the enemies the wider strip holds beyond the
        // cast's own (narrower) line are struck too.
        bool const trident = IsRune(*RowOf(spellId), "Piercing Trident");
        double const width = WidenedWidth(Tune("deadly_reach_width_yards"), Tune("deadly_reach_piercing_trident_area_pct"),
                                          punch.stage, trident);
        if (punch.stage == 3 || (trident && punch.stage == 2))
        {
            double const direction = player->GetAbsoluteAngle(primary);
            double const line = Tune("deadly_reach_line_yards");
            // the third hit's extra enemies lie between the line's end and its reach; a widened strip also holds the
            // ones beside the line itself, so it is read from the Monk
            double const from = trident ? 0.0 : line;
            double const to = punch.stage == 3 ? Tune("deadly_reach_stage3_reach_yards") : line;
            for (Unit* enemy : Combat::Enemies(player, spellId, player->GetPosition(), to))
                if (InCapsule(player->GetPositionX(), player->GetPositionY(), direction, from, to, width,
                              enemy->GetPositionX(), enemy->GetPositionY()))
                    punch.others.push_back(enemy);
        }
        return punch;
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets, Punch const& punch)
    {
        auto const* row = RowOf(spellId);
        if (!player || !row || targets.empty() || (punch.stage != 3 && !(punch.stage == 2 && IsRune(*row, "Piercing Trident"))))
            return;
        std::vector<Unit*> struck = targets;
        for (Unit* enemy : punch.others)
            if (std::find(struck.begin(), struck.end(), enemy) == struck.end() &&
                Combat::Strike(player, enemy, spellId))
                struck.push_back(enemy);
        // Piercing Trident's second hit only widens the line: the third hit's effects below are the third hit's own.
        if (punch.stage != 3)
            return;

        // "Every third hit has a {proc_chance_pct} chance to knock enemies up into the air": each enemy the hit struck
        // is its own roll. Piercing Trident's own row raises the chance to 100.
        if (auto chance = Numbers::Get(spellId, "proc_chance_pct"))
            for (Unit* enemy : struck)
                if (roll_chance_f(float(*chance)))
                    player->CastSpell(enemy, Shells::PylonSpeedThrow, true);

        if (IsRune(*row, "Foresight"))
            Effects::Dealt(player, spellId, Numbers::Num(spellId, "damage_bonus_pct"),
                           Numbers::Num(spellId, "duration_seconds"));

        if (IsRune(*row, "Strike from Beyond"))
        {
            std::lock_guard<std::mutex> guard(mutex);
            states[player->GetGUID().GetRawValue()].next.Add(Numbers::Num(spellId, "cost_reduction_pct") *
                                                             double(struck.size()));
        }

        if (IsRune(*row, "Scattered Blows"))
        {
            // "Every third hit randomly damages enemies within {radius_yards} yards for {damage_pct} weapon damage":
            // the fists (Power/Monk_DeadlyReach.pow SF_8) each land on an enemy picked at random.
            auto enemies =
                Combat::Enemies(player, spellId, player->GetPosition(), Numbers::Num(spellId, "radius_yards"));
            auto const pct = Numbers::Get(spellId, "damage_pct");
            for (std::size_t index : ScatterFists(enemies.size(), unsigned(Tune("deadly_reach_scattered_fists")),
                                                  [](std::size_t n) { return std::size_t(urand(0, uint32(n - 1))); }))
                Combat::Strike(player, enemies[index], spellId, pct);
        }
    }

    void Spent(Player* player, std::uint32_t spellId)
    {
        if (!player)
            return;
        SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId);
        if (!info || info->PowerType != std::uint32_t(Resources::Slot(Resources::Spirit)) || !info->ManaCost)
            return;
        double pct = 0;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = states.find(player->GetGUID().GetRawValue());
            if (found == states.end())
                return;
            pct = found->second.next.Take();
        }
        if (double const back = Refund(Resources::ToPoints(Resources::Spirit, double(info->ManaCost)), pct); back > 0)
            Resources::Energize(player, Resources::Spirit, spellId, back, false);
    }
} // namespace DC::Combat::Monk::DeadlyReach
