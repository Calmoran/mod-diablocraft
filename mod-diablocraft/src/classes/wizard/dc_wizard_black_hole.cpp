#include "dc_wizard_black_hole.h"
#include "MotionMaster.h"

namespace DC::Combat::Wizard::BlackHole
{
    using namespace Shared;

    namespace
    {
        // Black Hole draws enemies to it with the Barbarian's knockback
        // speeds (ability_knockback_speed_xy/z): the same stock MoveJump,
        // the same two tunables.
        void Pull(Unit* target, Position const& center)
        {
            double xy = Tune("ability_knockback_speed_xy"), z = Tune("ability_knockback_speed_z");
            if (xy <= 0 || z <= 0 || target->HasUnitState(UNIT_STATE_ROOT))
                return;
            target->GetMotionMaster()->MoveJump(center, float(xy), float(z));
        }
    } // namespace

    void Cast(Player* player, uint32 id, std::vector<Unit*> const& targets, Position const& center)
    {
        double const seconds = Num(id, "dot_duration_seconds");
        for (Unit* target : targets)
            Pull(target, center);
        if (IsRune(id, "Blazar"))
            After(player, seconds,
                  [id, center](Player* p) {
                      // The explosion procs nothing (wizard.js:1180 proc 0).
                      ProcAs explosion(Num(id, "proc_coefficient", "explosion"));
                      Combat::StrikeArea(p, id, center, Num(id, "radius_yards", "explosion"),
                                         Num(id, "damage_pct", "explosion"));
                  });
        std::lock_guard<std::recursive_mutex> guard(mutex);
        State& state = StateOf(player);
        uint64 const now = Now();
        for (Unit* target : targets)
        {
            if (IsRune(id, "Spellsteal"))
            {
                Weaken(target, id, Num(id, "enemy_damage_pct"), Num(id, "duration_seconds", "debuff"));
                state.spellsteal.push_back(
                    {now + uint64(Num(id, "duration_seconds", "buff") * 1000), Num(id, "damage_bonus_pct")});
            }
            if (IsRune(id, "Absolute Zero"))
                state.absoluteZero.push_back(
                    {now + uint64(Num(id, "duration_seconds") * 1000), Num(id, "damage_bonus_pct")});
        }
    }
} // namespace DC::Combat::Wizard::BlackHole
