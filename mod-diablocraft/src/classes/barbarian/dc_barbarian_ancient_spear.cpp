#include "dc_barbarian_ancient_spear.h"
#include "../../combat/dc_spell_numbers.h"
#include "Player.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "Unit.h"
#include <cmath>

namespace DC::Combat::Abilities::AncientSpear
{
    using namespace Shared;

    void OnHit(Player* p, Unit* target, Row const* r)
    {
        if (Rune(*r, "Harpoon"))
        {
            Pull(target, p->GetPosition());
            Control(p, target, *r, Numbers::Num(r->id, "slow_duration_seconds"));
        }
        if (Rune(*r, "Rage Flip"))
        {
            Position behind = p->GetPosition();
            double distance = Tune("rage_flip_behind_yards");
            if (distance > 0)
            {
                behind.Relocate(behind.GetPositionX() - std::cos(p->GetOrientation()) * distance,
                                behind.GetPositionY() - std::sin(p->GetOrientation()) * distance,
                                behind.GetPositionZ());
                Pull(target, behind);
            }
            Control(p, target, *r, Numbers::Num(r->id, "slow_duration_seconds"));
        }
        if (Rune(*r, "Ranseur"))
            Knock(p, target, Numbers::Num(r->id, "knockback_yards"));
    }

    bool SpendsEveryPoint(std::string const& skill, std::string const& rune)
    {
        return skill == "Ancient Spear" && rune == "Boulder Toss";
    }

    void OnBegin(std::string const& skill, std::string const& rune, uint32 id, double fury, double& damagePct)
    {
        if(skill=="Ancient Spear"&&rune=="Boulder Toss")damagePct=fury*Numbers::Num(id, "damage_pct");
    }

    bool BurstsAtFirstImpact(std::string const& skill, std::string const& rune)
    {
        return skill == "Ancient Spear" && rune == "Boulder Toss";
    }
} // namespace DC::Combat::Abilities::AncientSpear
