// War Cry: the armor shout, its runes and the allies it reaches.
#pragma once
#include "dc_barbarian_internal.h"
#include <optional>

namespace DC::Combat::Abilities::WarCry
{
    using Shared::Row;
    using Shared::State;

    // The buff's armor and its runes' contributions, a part of the player's refresh. `wrathSeconds` is what Hardened Wrath's extra armor has left.
    void OnRefresh(Player* p, std::optional<StatSheet> const& baseline, double& wrathSeconds);
    // Adds the dodge chance the buff gives.
    void OnDodge(Player const* p, double& chance);
    // The cast: the buff on each unit the shout reaches, Charge!'s Fury.
    void OnCast(Player* p, uint32 id, Row const* r, Row const* b, std::vector<Unit*> const& targets);
    // Mixes Hardened Wrath's armor window into the signature that tells the upkeep to refresh.
    void OnSignature(Player* p, uint64& signature);
} // namespace DC::Combat::Abilities::WarCry
