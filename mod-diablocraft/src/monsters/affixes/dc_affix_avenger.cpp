// World of DiabloCraft - the Avenger elite affix: a pack member's death makes the survivors bigger, faster and harder-hitting.

#include "dc_affix_internal.h"

#include "Creature.h"
#include "Map.h"

namespace DC::Rifts
{
// Any pack member died: Avenger makes the survivors hit harder. Both the
// companions and the pack leader count - a champion pack has no companions,
// so before this only its clones triggered and killing the leader first gave
// the survivors no stack (13-elite-affixes §10).
void Avenge(Creature* dead)
{
    Map* map = dead->GetMap();
    if (!map)
        return;
    Creature* leader = nullptr;
    if (MinionState* member = dead->CustomData.Get<MinionState>("DCRiftMinion"))
        leader = map->GetCreature(member->leader);
    else if (EliteState* own = dead->CustomData.Get<EliteState>("DCRiftElite"))
        if (!own->member)
            leader = dead;          // the leader is itself a member of the pack
    EliteState* pack = leader ? leader->CustomData.Get<EliteState>("DCRiftElite") : nullptr;
    if (!pack || !HasAffix(*pack, "avenger"))
        return;
    std::shared_ptr<AffixNumbers const> const numbers = Numbers();
    if (!numbers || !numbers->Enabled("Avenger"))
        return;
    ++pack->avengerStacks;
    // Damage DEALT only. Each application adds the
    // table's bonus to the original value, rather than compounding bonuses.
    unsigned const previous = pack->avengerStacks - 1;
    auto ratio = [&](double bonus)
    {
        return static_cast<float>((1.0 + pack->avengerStacks * bonus)
                                  / (1.0 + previous * bonus));
    };
    float const bonus = ratio(numbers->avengerDamage);
    float const attack = ratio(numbers->Parameter("Avenger|attack_speed_bonus") / 100.0);
    float const movement = ratio(numbers->Parameter("Avenger|move_speed_bonus") / 100.0);
    float const size = ratio(numbers->Parameter("Avenger|model_size_bonus") / 100.0);
    for (Creature* survivor : PackMembers(leader, *pack))
    {
        if (EliteState* own = survivor->CustomData.Get<EliteState>("DCRiftElite"))
            own->avengerDamageFactor *= bonus;
        AddPace(survivor, movement, attack);
        survivor->SetObjectScale(survivor->GetObjectScale() * size);
        survivor->SetFloatValue(UNIT_FIELD_MINDAMAGE,
                                survivor->GetFloatValue(UNIT_FIELD_MINDAMAGE) * bonus);
        survivor->SetFloatValue(UNIT_FIELD_MAXDAMAGE,
                                survivor->GetFloatValue(UNIT_FIELD_MAXDAMAGE) * bonus);
    }
}

double EliteDamageMultiplier(Unit const* source)
{
    Creature const* creature = source ? source->ToCreature() : nullptr;
    EliteState const* state = creature ? creature->CustomData.Get<EliteState>("DCRiftElite") : nullptr;
    return state ? state->avengerDamageFactor : 1.0;
}
}
