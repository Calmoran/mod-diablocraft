#include "dc_barbarian_ground_stomp.h"
#include "../../combat/dc_spell_numbers.h"
#include "Player.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "Unit.h"
#include <cmath>
#include "../../combat/dc_item_powers.h"

namespace DC::Combat::Abilities::GroundStomp
{
    using namespace Shared;

    void OnCast(Player* p, Row const* r, Row const* b, std::vector<Unit*> const& targets)
    {
        if (Rune(*r, "Foot of the Mountain"))
            Fury(p, Numbers::Num(r->id, "generated_resource") - Numbers::Num(b->id, "generated_resource"));
        for (auto u : targets)
        {
            if (Rune(*r, "Wrenching Smash"))
                Pull(u, p->GetPosition());
            Control(p, u, *r, Numbers::Num(b->id, "stun_duration_seconds") * ItemPowers::StunFactor(p));
        }
    }
} // namespace DC::Combat::Abilities::GroundStomp
