// The Wizard's upkeep: the tuning read at startup, and the scripts that run the timers, the sheet refresh, the kills and the clean-up on logout
// and map change.
#pragma once
#include "dc_wizard_internal.h"

namespace DC::Combat::Wizard::Upkeep
{
    void RegisterScripts();
} // namespace DC::Combat::Wizard::Upkeep
