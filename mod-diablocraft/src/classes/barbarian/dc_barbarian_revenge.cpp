#include "dc_barbarian_revenge.h"
#include "../../combat/dc_spell_numbers.h"
#include "Player.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "Unit.h"
#include <cmath>

namespace DC::Combat::Abilities::Revenge
{
    using namespace Shared;

    void OnRefresh(Player* p)
    {
        if (auto r = Buff(p, "Revenge"); r && Rune(*r, "Best Served Cold"))
            Add(p, AuraId(r->id), Stat::CritChance, Numbers::Num(r->id, "crit_chance_pct"));
    }

    void OnCast(Player* p, uint32 id, Row const* r, Row const* b, std::vector<Unit*> const& targets, State& s)
    {
        if (s.revenge.count)
            --s.revenge.count;
        double healing = Rune(*r, "Blood Law") ? Numbers::Num(r->id, "heal_pct") : Numbers::Num(b->id, "heal_pct");
        Heal(p, p, id, p->GetMaxHealth() * healing / 100 * targets.size());
        if (Rune(*r, "Best Served Cold"))
            Mark(p, p, *r, Numbers::Num(r->id, "duration_seconds"));
        if (Rune(*r, "Grudge"))
            for (auto u : targets)
                Knock(p, u, Numbers::Num(r->id, "radius_yards"));
    }

    void OnTaken(Player* p, Unit* attacker, uint32 damage)
    {
        if (!damage)
            return;
        std::lock_guard<std::recursive_mutex> lock(mutex);
        auto& s = states[p->GetGUID().GetRawValue()];
        auto b = Base("Revenge");
        auto r = Active(p, "Revenge");
        unsigned cap = r && Rune(*r, "Provocation") ? unsigned(Numbers::Num(r->id, "charge_count")) : unsigned(Numbers::Num(b->id, "charge_count"));
        if (roll_chance_f(float(Numbers::Num(b->id, "proc_chance_pct"))))
            s.revenge.count = std::min(cap, s.revenge.count + 1);
        (void) attacker;
    }
} // namespace DC::Combat::Abilities::Revenge
