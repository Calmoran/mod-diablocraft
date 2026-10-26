#include "dc_wizard_frost_nova.h"

namespace DC::Combat::Wizard::FrostNova
{
    using namespace Shared;

    void Cast(Player* player, uint32 id, std::vector<Unit*> const& targets)
    {
        if (IsRune(id, "Frozen Mist"))
        {
            // "leaves behind a mist of frost": it stays where it was cast.
            std::lock_guard<std::recursive_mutex> guard(mutex);
            StateOf(player).mist = player->GetPosition();
        }
        else
        {
            double const seconds = Num(id, "freeze_duration_seconds");
            for (Unit* target : targets)
            {
                // Bone Chill's mark is written only when the freeze landed (row 8).
                if (Freeze(player, target, seconds) && IsRune(id, "Bone Chill"))
                {
                    std::lock_guard<std::recursive_mutex> guard(mutex);
                    StateOf(player).marks[target->GetGUID().GetRawValue()].boneChill =
                        Now() + uint64(seconds * 1000);
                }
            }
            if (IsRune(id, "Deep Freeze") && targets.size() >= std::size_t(Num(id, "target_count")))
            {
                std::lock_guard<std::recursive_mutex> guard(mutex);
                StateOf(player).deepFreeze = Now() + uint64(Num(id, "duration_seconds") * 1000);
            }
        }
    }

    void MistTick(Player* player, uint32 id, double seconds)
    {
        // "{damage_pct} weapon damage as Cold over
        // {dot_duration_seconds} seconds", every interval_seconds.
        Position mist;
        {
            std::lock_guard<std::recursive_mutex> guard(mutex);
            mist = StateOf(player).mist;
        }
        double const total = Num(id, "dot_duration_seconds");
        if (total <= 0)
            return;
        for (Unit* target : Combat::StrikeArea(player, id, mist, Combat::TargetRadius(id),
                                               Num(id, "damage_pct") * seconds / total, true))
            Chill(player, target, Num(id, "chill_duration_seconds"));
    }

    void Shatter(Player* player, Unit* killed)
    {
        // Shatter: "A frozen enemy that is killed has a
        // {proc_chance_pct} chance of releasing another Frost Nova".
        for (Classes::Slot const& entry : Classes::Bar(player))
            if (IsSkill(entry.spellId, "Frost Nova") && IsRune(entry.spellId, "Shatter") &&
                Roll() < Num(entry.spellId, "proc_chance_pct"))
            {
                uint32 const id = entry.spellId;
                Position const at = killed->GetPosition();
                After(player, 0,
                      [id, at](Player* p)
                      {
                          for (Unit* enemy : Combat::Enemies(p, id, at, Combat::TargetRadius(id)))
                              Freeze(p, enemy, Num(id, "freeze_duration_seconds"));
                      });
            }
    }
} // namespace DC::Combat::Wizard::FrostNova
