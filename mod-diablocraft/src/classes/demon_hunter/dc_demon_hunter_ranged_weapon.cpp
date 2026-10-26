/*
 * 'Requires Bow': the skills whose sheet rows carry the requires_ranged_weapon token are cast only with a bow, a
 * crossbow or a hand crossbow wielded. The weapon kind is the item template's own subclass.
 */

#include "dc_demon_hunter_ranged_weapon.h"
#include "../../combat/dc_spell_numbers.h"
#include "Item.h"
#include "ItemTemplate.h"
#include "Player.h"

namespace DC::Combat::DemonHunter::RangedWeapon
{
    static_assert(Bow == ITEM_SUBCLASS_WEAPON_BOW && Crossbow == ITEM_SUBCLASS_WEAPON_CROSSBOW,
                  "the ranged subclasses are the core's");

    namespace
    {
        // The weapon subclass of what is worn in a slot, NoWeapon for an empty slot or a worn thing that is not a
        // weapon.
        std::uint32_t SubclassIn(Player* player, std::uint8_t slot)
        {
            Item const* item = player->GetItemByPos(INVENTORY_SLOT_BAG_0, slot);
            ItemTemplate const* worn = item ? item->GetTemplate() : nullptr;
            return worn && worn->Class == ITEM_CLASS_WEAPON ? worn->SubClass : NoWeapon;
        }
    } // namespace

    bool Permitted(Player* player, std::uint32_t spellId)
    {
        if (!player || !Numbers::Has(spellId, "requires_ranged_weapon"))
            return true;
        return Allowed(true, SubclassIn(player, EQUIPMENT_SLOT_MAINHAND), SubclassIn(player, EQUIPMENT_SLOT_OFFHAND));
    }
} // namespace DC::Combat::DemonHunter::RangedWeapon
