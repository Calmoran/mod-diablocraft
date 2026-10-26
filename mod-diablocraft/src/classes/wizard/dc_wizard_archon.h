// Archon form: the transformation, its bar of five abilities, and what makes an Archon ability different from the Wizard's own.
#pragma once
#include "dc_wizard_internal.h"

namespace DC::Combat::Wizard::Archon
{
    // The abilities the form offers: Teleport and Slow Time only with their runes.
    std::vector<Classes::Slot> ArchonBar(uint32 form);
    // The form's aura went on: the Archon look, the abilities learned and put on the bar.
    void EnterArchon(Player* player, uint32 form);
    // The form's aura came off, however it ended: the look and the bar come back.
    void LeaveArchon(Player* player);
} // namespace DC::Combat::Wizard::Archon
