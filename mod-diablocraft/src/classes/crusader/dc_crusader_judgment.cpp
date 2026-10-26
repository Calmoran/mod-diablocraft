/*
 * Judgment and its five runes: the judgment passed on the enemies around a place, Immobilizing them, and what each rune
 * does with the judged. The dispatch is in dc_crusader.cpp.
 */

#include "dc_crusader_judgment.h"
#include "../dc_level_heal.h"
#include "dc_crusader_common.h"
#include "dc_crusader_dot.h"
#include "../../combat/dc_enemy_effects.h"

#include <algorithm>

namespace DC::Combat::Crusader::Judgment
{
    namespace
    {
        constexpr std::string_view Skill = "Judgment";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        double Tune(char const* name)
        {
            return DC::Tunables::Get("crusader", name);
        }

        // The enemies judged now, per Crusader and enemy: when each stops being judged.
        struct Mark
        {
            std::uint64_t player, enemy;
            bool operator==(Mark const& other) const
            {
                return player == other.player && enemy == other.enemy;
            }
        };
        struct MarkHash
        {
            std::size_t operator()(Mark const& mark) const
            {
                return std::hash<std::uint64_t>()(mark.player) ^ (std::hash<std::uint64_t>()(mark.enemy) << 1);
            }
        };
        std::mutex mutex;
        std::unordered_map<Mark, std::uint64_t, MarkHash> judged;

        // Penitence: one second's heal for the enemies judged; the ticks left bound the heal by themselves.
        void Mend(Player* player, std::uint32_t spellId, double amount, unsigned left, std::uint32_t intervalMs)
        {
            if (!player->IsInWorld() || left == 0)
                return;
            Heal(player, player, spellId, amount);
            if (left > 1)
                player->m_Events.AddEventAtOffset([player, spellId, amount, left, intervalMs]
                                                  { Mend(player, spellId, amount, left - 1, intervalMs); },
                                                  std::chrono::milliseconds(intervalMs));
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

    void Ground(Player* player, std::uint32_t spellId, Position const& center)
    {
        if (!player || !Is(spellId))
            return;
        Rune const rune = RuneAt(spellId);
        std::vector<Unit*> enemies = Combat::Enemies(player, spellId, center, Numbers::Num(spellId, "radius_yards"));
        // "All enemies are drawn toward the center of the judged area": all the way to it, before they are held.
        if (rune == Rune::MassVerdict)
            for (Unit* enemy : enemies)
            {
                float z = center.GetPositionZ();
                enemy->UpdateGroundPositionZ(center.GetPositionX(), center.GetPositionY(), z);
                enemy->NearTeleportTo(center.GetPositionX(), center.GetPositionY(), z, enemy->GetOrientation());
            }
        // "Immobilizing them in place for {immobilize_duration_seconds} seconds" (Deliberation's own number is the
        // rune's).
        double const seconds = Numbers::Num(spellId, "immobilize_duration_seconds");
        std::uint64_t const until = Now() + std::uint64_t(seconds * 1000.0);
        {
            std::lock_guard<std::mutex> guard(mutex);
            for (auto mark = judged.begin(); mark != judged.end();)
                mark = Judged(Now(), mark->second) ? std::next(mark) : judged.erase(mark);
        }
        for (Unit* enemy : enemies)
        {
            Root(player, enemy, seconds);
            std::lock_guard<std::mutex> guard(mutex);
            judged[{player->GetGUID().GetRawValue(), enemy->GetGUID().GetRawValue()}] = until;
        }
        switch (rune)
        {
            case Rune::Penitence:
            {
                // "you heal for {heal_per_second_life} Life per second for {duration_seconds} seconds."
                double const tick = Tune("judgment_penitence_tick_seconds");
                unsigned const ticks = Dot::Ticks(Numbers::Num(spellId, "duration_seconds"), tick);
                double const amount =
                    HealPerTick(Classes::HealAtLevel(Numbers::Num(spellId, "heal_per_second_life"), player->GetLevel()), unsigned(enemies.size()));
                if (ticks && amount > 0)
                {
                    auto const interval = std::uint32_t(tick * 1000 + 0.5);
                    player->m_Events.AddEventAtOffset([player, spellId, amount, ticks, interval]
                                                      { Mend(player, spellId, amount, ticks, interval); },
                                                      std::chrono::milliseconds(interval));
                }
                break;
            }
            case Rune::Debilitate:
                // "Enemies in the judged area deal {enemy_damage_pct} reduced damage for {duration_seconds} seconds."
                for (Unit* enemy : enemies)
                    EnemyEffects::Weaken(enemy, spellId, Numbers::Num(spellId, "enemy_damage_pct"),
                                         Numbers::Num(spellId, "duration_seconds"));
                break;
            default:
                break;
        }
    }

    double CritBonus(Player* player, Unit* target)
    {
        if (!player || !target)
            return 0.0;
        std::uint32_t const spellId = Slotted(player, Skill);
        if (RuneAt(spellId) != Rune::Resolved)
            return 0.0;
        bool onJudged = false;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = judged.find({player->GetGUID().GetRawValue(), target->GetGUID().GetRawValue()});
            onJudged = found != judged.end() && Judged(Now(), found->second);
        }
        return CritFor(Rune::Resolved, onJudged, Numbers::Num(spellId, "crit_chance_pct"));
    }
} // namespace DC::Combat::Crusader::Judgment
