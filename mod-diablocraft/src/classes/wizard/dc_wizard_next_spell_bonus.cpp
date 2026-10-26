#include "dc_wizard_next_spell_bonus.h"
#include "SpellMgr.h"
#include <algorithm>

namespace DC::Combat::Wizard::NextSpellBonus
{
    using namespace Shared;

    void Cast(State& state, uint32 id, std::vector<Unit*> const& targets)
    {
        // "increases the damage of your next Arcane (Lightning) spell": the
        // cast that just resolved spent it, and then the rune sets it anew.
        if (SpellInfo const* info = sSpellMgr->GetSpellInfo(id))
        {
            if (info->SchoolMask == SPELL_SCHOOL_MASK_ARCANE)
                state.attunement = 0, state.attunementHits = 0;
            if (info->SchoolMask == SPELL_SCHOOL_MASK_NATURE)
                state.spark = 0, state.sparkHits = 0;
        }
        if (IsRune(id, "Arcane Attunement"))
        {
            state.attunementHits = unsigned(targets.size());
            state.attunement = Num(id, "damage_bonus_pct") * double(targets.size());
        }
        if (IsRune(id, "Spark"))
        {
            state.sparkHits = unsigned(std::min(targets.size(), std::size_t(Num(id, "max_count"))));
            state.spark = Num(id, "damage_bonus_pct") * double(state.sparkHits);
        }
    }
} // namespace DC::Combat::Wizard::NextSpellBonus

namespace DC::Combat::Wizard
{
    using namespace Shared;

    void Multipliers(Player* player, std::uint32_t spellId, Factors& out)
    {
        if (!player)
            return;
        std::lock_guard<std::recursive_mutex> guard(mutex);
        State& state = StateOf(player);
        if (SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId))
        {
            if (info->SchoolMask == SPELL_SCHOOL_MASK_ARCANE && !IsRune(spellId, "Arcane Attunement") && state.attunement)
                AddFactor(out, "Arcane Attunement", state.attunement);
            if (info->SchoolMask == SPELL_SCHOOL_MASK_NATURE && !IsRune(spellId, "Spark") && state.spark)
                AddFactor(out, "Spark", state.spark);
        }
    }
} // namespace DC::Combat::Wizard
