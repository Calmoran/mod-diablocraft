#include "dc_barbarian_collisions.h"
#include "../../combat/dc_spell_numbers.h"
#include "Player.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "Unit.h"
#include <cmath>

namespace DC::Combat::Abilities::Collisions
{
    using namespace Shared;

    void OnUpdate(Player* p, State& s)
    {
        Row const* collision = Buff(p, "Sprint");
        bool gangway = collision && Rune(*collision, "Gangway");
        if (!gangway)
        {
            collision = Buff(p, "Ignore Pain");
            if (collision && !Rune(*collision, "Bravado"))
                collision = nullptr;
        }
        if (collision && p->isMoving())
        {
            double radius = Tune(gangway ? "sprint_gangway_radius_yards" : "ignore_pain_bravado_radius_yards");
            std::vector<uint64> inside;
            for (auto u : At(p, p->GetPosition(), radius))
            {
                auto guid = u->GetGUID().GetRawValue();
                inside.push_back(guid);
                if (std::find(s.collisions.begin(), s.collisions.end(), guid) == s.collisions.end())
                {
                    Knock(p, u,
                          Tune(gangway ? "sprint_gangway_knockback_yards"
                                       : "ignore_pain_bravado_knockback_yards"));
                    if (gangway)
                    {
                        Hit h;
                        if (ComputeHit(p, u, collision->id, h))
                        {
                            h.areaDamage = 0;
                            DealHit(p, u, collision->id, h);
                        }
                    }
                }
            }
            s.collisions = std::move(inside);
        }
        else
            s.collisions.clear();
    }
} // namespace DC::Combat::Abilities::Collisions
