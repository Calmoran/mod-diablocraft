/*
 * World of DiabloCraft - Cain's Destiny 3-piece (D3: "When a Greater Rift Keystone drops, there is a
 * 25% chance for an extra one to drop."). The chance is the power table's row (`extra_keystone_pct`, read as the factor
 * 1 + N/100 by ItemPowers::KeystoneFactor, 1 with the bonus off); the roll is one per keystone dropped, and the extra
 * is one keystone. Pure, so scripts/tests/classes/test_cain_destiny.py compiles it.
 */
#ifndef DC_KEYSTONE_RULE_H
#define DC_KEYSTONE_RULE_H

namespace DC::Loot::Keystone
{
    // The extra keystones for one keystone drop: 1 when `roll` (uniform in [0, 1)) falls inside the chance, else 0.
    inline unsigned Extra(double factor, double roll)
    {
        return roll * 100.0 < (factor - 1.0) * 100.0 ? 1u : 0u;
    }
} // namespace DC::Loot::Keystone

#endif // DC_KEYSTONE_RULE_H
