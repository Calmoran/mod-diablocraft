#pragma once
// Lashing Tail Kick: what dc_monk.cpp dispatches to. The pure rules are in
// dc_monk_lashing_tail_kick.h.
#include <cstdint>
#include <optional>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Monk::Kick
{
    // Whether `spellId` is Lashing Tail Kick or one of its runes.
    bool Is(std::uint32_t spellId);
    // The weapon damage of the kick itself (Vulture Claw Kick's own rows are "hit" and "dot"); nullopt for any other
    // spell.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The enemies the kick strikes that the core's cone (`targets`) does not hold: the rest of the half circle, all
    // around for Vulture Claw Kick and Sweeping Armada, and Spinning Flame Kick's column. Read before the hits (Combat's
    // ResolveCast counts them into the cast's places and its enemy count, N-NHIT) and again by Cast.
    std::vector<Unit*> Beside(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    // The kick resolved: `targets` are the enemies the core's cone struck.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
} // namespace DC::Combat::Monk::Kick
