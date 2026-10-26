// Wizard: Electrocute's jumps, the walk from the first enemy to the ones the bolt arcs to (the rules are dc_wizard_chain.h).
#include "dc_wizard_internal.h"
#include "dc_wizard_chain.h"
#include "../../combat/dc_item_powers.h"
#include "../../common/dc_tunables.h"

namespace DC::Combat::Wizard
{
    using namespace Shared;

    bool Chains(std::uint32_t spellId)
    {
        auto const* row = Shells::FindAbility(spellId);
        return row && std::string_view(row->skill) == "Electrocute";
    }

    std::vector<Unit*> Jumps(Player* player, std::uint32_t spellId, Unit* first)
    {
        auto const* row = Shells::FindAbility(spellId);
        if (!player || !first || !row || std::string_view(row->skill) != "Electrocute" ||
            !DC::Tunables::Has("wizard", "electrocute_jump_radius_yards"))
            return {};
        double const radius = DC::Tunables::Get("wizard", "electrocute_jump_radius_yards");
        // Velvet Camaral: "Double the number of enemies your Electrocute jumps to", the worn hat's `jump_count_factor`
        // (1 without it; 0 jumps stay 0).
        unsigned const jumps = Chain::JumpCount(row->rune, Num(spellId, "target_count")) *
                               unsigned(ItemPowers::SkillSetTo(player, "Electrocute", "jump_count_factor", 1));
        // Myken's Ball of Hate: "Electrocute can chain to enemies that have already been hit", while a `jump_rehit` source is
        // worn (0 without it): the nearest enemy not hit yet first, the nearest one already hit only when none is left, never the
        // one the bolt is on (Chain::Next).
        bool const mayRehit = ItemPowers::SkillSetTo(player, "Electrocute", "jump_rehit", 0) > 0;
        return Chain::Walk(
            first, jumps, mayRehit,
            [&](Unit* on) { return Combat::Enemies(player, spellId, on->GetPosition(), radius); },
            [](Unit* a, Unit* b) { return double(a->GetExactDist(b)); });
    }
} // namespace DC::Combat::Wizard
