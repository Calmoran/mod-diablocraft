// Mirror Image: the Images the cast summons, their mind, and the copy of a killed Image.
#pragma once
#include "dc_wizard_internal.h"

class TempSummon;

namespace DC::Combat::Wizard::MirrorImage
{
    // One Mirror Image of cast `id` at `at` for `ms` milliseconds with `life` Life, copying its owner's look and taunting as the cast does.
    // SummonImages makes the cast's and Wizard::MultiplyImage the copy of a killed one; the caller keeps the guid.
    TempSummon* SummonImage(Player* player, uint32 id, Position const& at, uint32 ms, double life);
    // The cast's Images, replacing the ones already up.
    void SummonImages(Player* player, uint32 id);
    void RegisterScripts();
} // namespace DC::Combat::Wizard::MirrorImage
