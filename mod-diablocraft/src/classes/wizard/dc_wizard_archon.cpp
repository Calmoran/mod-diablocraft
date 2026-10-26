#include "dc_wizard_archon.h"
#include "dc_wizard_teleport.h"
#include "../../combat/dc_item_powers.h"
#include "../dc_resources.h"
#include "Player.h"
#include "SpellMgr.h"
#include "WorldSession.h"

namespace DC::Combat::Wizard::Archon
{
    using namespace Shared;

    std::vector<Classes::Slot> ArchonBar(uint32 form)
    {
        std::vector<Classes::Slot> bar;
        unsigned slot = 0;
        for (auto const& ability : Shells::ArchonAbilities)
        {
            std::string_view const name = ability.name;
            // wizard.js:1128-1131: the Teleport ability only with the
            // Teleport rune; the Slow Time one only with Slow Time's
            // (the runes' own sentences: "Archon form can cast ...").
            if (name == "Teleport" && !IsRune(form, "Teleport"))
                continue;
            if (name == "Slow Time" && !IsRune(form, "Slow Time"))
                continue;
            Classes::Slot entry;
            entry.slot = slot++;
            entry.skill = ARCHON_FORM;
            entry.rune = ability.name;
            entry.spellId = ability.id;
            bar.push_back(entry);
        }
        return bar;
    }

    void EnterArchon(Player* player, uint32 form)
    {
        // Teleport is replaced by Archon's own: Reversal's window ends.
        Teleport::ReversalEnd(player);
        // "You automatically start with N Archon stacks when entering Archon form", the worn item's `start_stacks`, 0 with
        // none. Asked before the lock, as every item-power reader.
        unsigned const start = static_cast<unsigned>(std::lround(ItemPowers::SkillSetTo(player, "Archon", "start_stacks", 0)));
        {
            std::lock_guard<std::recursive_mutex> guard(mutex);
            StateOf(player).archonStacks = start;
        }
        // Algalon the Observer: the form's own display row, its size baked into the row's display scale
        // (client-patch/dbc/build_creaturedisplayinfo.py), so only the display id changes and the object scale stays 1: the
        // client tweens a scale change, it loads a display at its own size.
        player->SetDisplayId(uint32(Num(form, "form_display_id")));
        auto bar = ArchonBar(form);
        for (Classes::Slot const& entry : bar)
            if (!player->HasSpell(entry.spellId))
                player->learnSpell(entry.spellId, true);
        Classes::WriteActionBar(player, bar);
        // Combustion: "An explosion erupts around you when you transform"
        // (wizard.js:1008-1010).
        if (IsRune(form, "Combustion"))
            Combat::StrikeArea(player, form, player->GetPosition(), Num(form, "radius_yards"));
    }

    void LeaveArchon(Player* player)
    {
        {
            std::lock_guard<std::recursive_mutex> guard(mutex);
            StateOf(player).archonStacks = 0;
        }
        // The aura's removal (it ends, is cancelled, or the player dies) brings the player's own look back, or a transform or
        // shapeshift still running (Unit::RestoreDisplayId).
        player->RestoreDisplayId();
        for (auto const& ability : Shells::ArchonAbilities)
            if (player->HasSpell(ability.id))
                player->removeSpell(ability.id, SPEC_MASK_ALL, true);
        if (player->IsInWorld() && player->GetSession() && !player->GetSession()->PlayerLogout())
            Classes::WriteActionBar(player);
    }
} // namespace DC::Combat::Wizard::Archon

namespace DC::Combat::Wizard
{
    using namespace Shared;

    bool CanCast(Player* player, std::uint32_t spellId)
    {
        uint32 const form = BuffOf(player, "Archon");
        if (ArchonAbilityName(spellId))
        {
            if (!form)
                return false;
            for (Classes::Slot const& entry : Archon::ArchonBar(form))
                if (entry.spellId == spellId)
                    return true;
            return false;
        }
        // "your normal abilities are replaced by powerful Archon abilities".
        return !form || !RowOf(spellId);
    }

    double SkillFactor(Player* player, std::uint32_t spellId)
    {
        if (!ArchonAbilityName(spellId))
            return 1.0;
        uint32 const form = BuffOf(player, "Archon");
        return form && IsRune(form, "Improved Archon") ? 1 + Num(form, "damage_bonus_pct") / 100 : 1.0;
    }

    std::optional<std::string> Element(Player* player, std::uint32_t spellId)
    {
        if (!ArchonAbilityName(spellId))
            return std::nullopt;
        uint32 const form = BuffOf(player, "Archon");
        SpellInfo const* info = form ? sSpellMgr->GetSpellInfo(form) : nullptr;
        if (!info)
            return std::nullopt;
        // The rune record's school is its wizard_runes.csv element, the
        // same table as wizard.js:1039's default_elem.
        std::string_view element = ElementOf(info->SchoolMask);
        return element.empty() ? std::nullopt : std::optional<std::string>(std::string(element));
    }
} // namespace DC::Combat::Wizard
