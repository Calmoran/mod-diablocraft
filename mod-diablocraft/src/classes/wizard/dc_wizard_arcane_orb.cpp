#include "dc_wizard_arcane_orb.h"
#include "SpellAuras.h"
#include <algorithm>
#include <cmath>

namespace DC::Combat::Wizard::ArcaneOrb
{
    using namespace Shared;

    void Cast(Player* player, Position const& center)
    {
        // Scorch: "The orb leaves behind a wall of Fire". The wall starts
        // where the orb set off and runs the way it flew, one yard further
        // each frame (wizard.js:217); a new cast lays a new wall.
        if (uint32 wall = Shells::HelperFor("Arcane Orb - Scorch - wall"))
        {
            {
                std::lock_guard<std::recursive_mutex> guard(mutex);
                State& state = StateOf(player);
                state.wallOrigin = player->GetPosition();
                state.wallDirection = player->GetExactDist2d(&center) > 0.1f ? player->GetAbsoluteAngle(&center)
                                                                             : player->GetOrientation();
                state.wallStart = Now();
            }
            player->RemoveAurasDueToSpell(wall);
            player->AddAura(wall, player);
        }
    }

    void WallTick(Player* player, uint32 id, double seconds)
    {
        // "a wall of Fire that deals {damage_pct:wall} weapon
        // damage as Fire over {dot_duration_seconds} seconds": each
        // tick hits the line from where the orb set off, as far as
        // it has flown, radius_yards:wall to either side
        // (wizard.js:217).
        uint32 const source = GroundSource(id);
        Position origin;
        float direction;
        uint64 start;
        {
            std::lock_guard<std::recursive_mutex> guard(mutex);
            State& state = StateOf(player);
            origin = state.wallOrigin;
            direction = state.wallDirection;
            start = state.wallStart;
        }
        double const total = Num(source, "dot_duration_seconds");
        double const length =
            std::min(Num(source, "range_yards", "wall"), Num(source, "travel_speed_yards_per_second") *
                                                             double(Now() - std::min(Now(), start)) / 1000);
        double const half = Num(source, "radius_yards", "wall");
        if (total <= 0 || length <= 0 || half <= 0)
            return;
        double const pct = Num(source, "damage_pct", "wall") * seconds / total;
        ProcAs wall(Num(source, "proc_coefficient", "wall"));
        for (Unit* enemy : Combat::Enemies(player, source, origin, length + half))
        {
            double const dx = enemy->GetPositionX() - origin.GetPositionX();
            double const dy = enemy->GetPositionY() - origin.GetPositionY();
            double const along = dx * std::cos(direction) + dy * std::sin(direction);
            double const across = -dx * std::sin(direction) + dy * std::cos(direction);
            if (along >= 0 && along <= length && std::abs(across) <= half)
                Combat::Strike(player, enemy, source, pct, true);
        }
    }
} // namespace DC::Combat::Wizard::ArcaneOrb
