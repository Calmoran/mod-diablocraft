#include "dc_wizard_magic_weapon.h"

namespace DC::Combat::Wizard::MagicWeapon
{
    using namespace Shared;

    void Cast(Player* player, std::vector<Unit*> const& targets)
    {
        // Magic Weapon - Conduit: gain_resource for each enemy hit, once a
        // cast (wizard.js Conduit: 3 per target per cast).
        if (uint32 weapon = BuffOf(player, "Magic Weapon"))
        {
            if (IsRune(weapon, "Conduit") && !targets.empty())
                Combat::GainResource(player, weapon, Num(weapon, "gain_resource") * double(targets.size()));
            // Deflection: "When you perform an attack, gain a protective shield".
            if (IsRune(weapon, "Deflection") && !targets.empty())
                Shield(player, "Magic Weapon - Deflection - shield", Num(weapon, "absorb_capacity_life_pct"),
                       Num(weapon, "absorb_duration_seconds"));
        }
    }

    void Ignite(Player* player, ObjectGuid guid, double proc)
    {
        // Magic Weapon - Ignite: "Attacks burn enemies for {damage_pct}
        // weapon damage as Fire over {dot_duration_seconds} seconds":
        // chance = proc, one hit of 300% (wizard.js:864); the "over 3
        // seconds" has no sourced tick, so it lands at once. Damage a
        // proc deals carries no proc of its own (the cast's proc goes
        // to its first damage only, damage.js:375-378).
        if (uint32 weapon = BuffOf(player, "Magic Weapon");
            weapon && IsRune(weapon, "Ignite") && Roll() < 100 * proc)
            After(player, 0, [guid, weapon](Player* p) {
                if (Unit* u = Find(p, guid))
                {
                    ProcAs ignite(0);
                    Combat::Strike(p, u, weapon, Num(weapon, "damage_pct"));
                }
            });
    }
} // namespace DC::Combat::Wizard::MagicWeapon
