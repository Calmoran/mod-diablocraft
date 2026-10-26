#include "dc_barbarian_threatening_shout.h"
#include "../../combat/dc_spell_numbers.h"
#include "Player.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "Unit.h"
#include <cmath>

namespace DC::Combat::Abilities::ThreateningShout
{
    using namespace Shared;

    double OnTargetBonus(Unit* u)
    {
        auto r = Buff(u, "Threatening Shout");
        return r && Rune(*r, "Falter") ? Numbers::Num(r->id, "damage_taken_pct") : 0;
    }

    double OnIncomingFactor(Unit* attacker)
    {
        auto r = Buff(attacker, "Threatening Shout");
        return r && !Rune(*r, "Falter") ? 1 - Numbers::Num(Base("Threatening Shout")->id, "enemy_damage_pct") / 100 : 1;
    }

    void OnCast(Player* p, uint32 id, Row const* r, Row const* b, std::vector<Unit*> const& targets)
    {
        double duration = 0;
        duration = Combat::ModifiedDurationSeconds(
            p, id, Rune(*r, "Falter") ? Numbers::Num(r->id, "duration_seconds")
                                      : Numbers::Num(b->id, "duration_seconds"));
        for (auto u : targets)
        {
            Mark(p, u, *r, duration);
            if (Rune(*r, "Demoralize"))
                Control(p, u, *r, Numbers::Num(r->id, "duration_seconds"));
            if (Rune(*r, "Terrify"))
                Control(p, u, *r, Numbers::Num(r->id, "fear_duration_seconds"));
        }
    }
} // namespace DC::Combat::Abilities::ThreateningShout
