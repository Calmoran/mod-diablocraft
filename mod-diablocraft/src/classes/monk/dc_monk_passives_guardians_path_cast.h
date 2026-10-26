#pragma once
// Six Monk passives: what the Monk's files dispatch to. The pure rules are in
// dc_monk_passives_guardians_path.h.
#include "../../combat/dc_damage_buckets.h"

#include <cstdint>

class Player;
class Unit;

namespace DC::Combat::Monk::Passives242
{
    // The Guardian's Path: the dodge chance in percent it gives `unit` (Monk::Dodge); 0 for anyone else.
    double Dodge(Unit const* unit);
    // The Guardian's Path: the factor a Monk's Spirit generation is multiplied by (Monk::Connected).
    double GenerationFactor(Player* player);
    // Determination and Relentless Assault are damage multipliers of their own: Monk::Multipliers puts them on the
    // hit's factors; `target` is the hit's victim.
    void Multipliers(Player* player, Unit* target, DC::Combat::Factors& out);
} // namespace DC::Combat::Monk::Passives242
