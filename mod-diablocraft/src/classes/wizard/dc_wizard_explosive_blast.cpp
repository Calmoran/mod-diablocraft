#include "dc_wizard_explosive_blast.h"
#include <cmath>

namespace DC::Combat::Wizard::ExplosiveBlast
{
    using namespace Shared;

    namespace
    {
        void Explode(Player* player, uint32 id, bool dynamo)
        {
            {
                std::lock_guard<std::recursive_mutex> guard(mutex);
                StateOf(player).empoweredNow = dynamo ? id : 0;
            }
            Combat::StrikeArea(player, id, player->GetPosition(), Num(id, "radius_yards"));
            std::lock_guard<std::recursive_mutex> guard(mutex);
            StateOf(player).empoweredNow = 0;
        }
    } // namespace

    bool Delayed(Player* player, uint32 id, bool dynamo)
    {
        // "explodes after {duration_seconds} seconds" (90 frames,
        // Short Fuse 6: wizard.js:965); Chain Reaction's explosions
        // floor(60 / attack speed) frames apart (:969).
        double const fuse = Num(id, "duration_seconds");
        unsigned const count = IsRune(id, "Chain Reaction") ? unsigned(Num(id, "spawn_count")) : 1;
        double const aps = Combat::AttacksPerSecond(player, id);
        double const gap =
            IsRune(id, "Chain Reaction") && aps > 0 ? std::floor(Num(id, "attack_frames_count") / aps) / 60 : 0;
        for (unsigned i = 0; i < count; ++i)
            After(player, fuse + i * gap, [id, dynamo](Player* p) { Explode(p, id, dynamo); });
        return true;
    }
} // namespace DC::Combat::Wizard::ExplosiveBlast
