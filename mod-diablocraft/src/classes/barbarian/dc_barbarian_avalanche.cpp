#include "dc_barbarian_avalanche.h"
#include "../../combat/dc_spell_numbers.h"
#include "Player.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "Unit.h"
#include <cmath>
#include "../../combat/dc_combat.h"

namespace DC::Combat::Abilities::Avalanche
{
    using namespace Shared;

    void OnCast(Player* p, uint32 id, Row const* r, Row const* b, std::vector<Unit*> const& targets, Position const* center, State& s)
    {
        if (Rune(*r, "Tectonic Rift"))
        {
            if (s.avalanche.count)
                --s.avalanche.count;
            if (s.avalanche.left <= 0)
                s.avalanche.left = s.avalanche.period = ReducedCooldownMilliseconds(
                    p, b->id, uint32(std::lround(Numbers::Num(b->id, "cooldown_seconds") * 1000)));
            SendSkillCooldown(p, id, s.avalanche.count ? 0 : uint32(std::ceil(s.avalanche.left)));
        }
        if (Rune(*r, "Glacier"))
            for (auto u : targets)
                Control(p, u, *r, Tune("avalanche_glacier_freeze_seconds"));
        if (Rune(*r, "Volcano") && center)
            ZoneStart(p, *r, *center, Numbers::Num(r->id, "dot_duration_seconds"), r->radius);
        if (Rune(*r, "Snow-Capped Mountain"))
            for (auto u : targets)
            {
                Mark(p, u, *r, Numbers::Num(r->id, "slow_duration_seconds"));
                if (center)
                    Pull(u, *center);
            }
    }

    void OnSpent(Player* p, State& s, double fury)
    {
        auto b = Base("Avalanche");
        auto r = Active(p, "Avalanche");
        double per = r && Rune(*r, "Lahar") ? Numbers::Num(r->id, "per_trigger_resource") : Numbers::Num(b->id, "per_trigger_resource");
        double reduction = r && Rune(*r, "Lahar") ? Numbers::Num(r->id, "cooldown_reduction_seconds") : Numbers::Num(b->id, "cooldown_reduction_seconds");
        s.avalancheSpent += fury;
        unsigned units = unsigned(s.avalancheSpent / per);
        s.avalancheSpent -= units * per;
        Reduce(p, "Avalanche", units * reduction * 1000);
        s.avalanche.left = std::max(0.0, s.avalanche.left - units * reduction * 1000);
    }

    void OnUpdate(Player* p, State& s, uint32 diff)
    {
        auto recharge = Recharger(diff);
        auto avalanche = Active(p, "Avalanche");
        if (avalanche && Rune(*avalanche, "Tectonic Rift"))
        {
            if (!s.avalanche.initialized)
            {
                s.avalanche.count = unsigned(Numbers::Num(avalanche->id, "charge_count"));
                s.avalanche.initialized = true;
            }
            auto avalancheCount = s.avalanche.count;
            recharge(s.avalanche, unsigned(Numbers::Num(avalanche->id, "charge_count")));
            if (s.avalanche.count != avalancheCount)
                SendSkillCooldown(p, avalanche->id, s.avalanche.count ? 0 : uint32(std::ceil(s.avalanche.left)));
        }
    }

    std::optional<bool> OnResolve(std::string const& skill, std::string const& rune)
    {
        if (skill == "Avalanche" && rune == "Volcano")
            return false;
        return std::nullopt;
    }
} // namespace DC::Combat::Abilities::Avalanche
