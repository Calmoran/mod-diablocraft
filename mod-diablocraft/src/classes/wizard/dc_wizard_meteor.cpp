#include "dc_wizard_meteor.h"
#include "../dc_resources.h"
#include "../../combat/dc_item_powers.h"
#include "SpellMgr.h"
#include <cmath>
#include <numbers>
#include <random>

namespace DC::Combat::Wizard::Meteor
{
    using namespace Shared;

    namespace
    {
        // The Meteor Shower row a Meteor cast is worked out as: the cast's own row when the Shower is the chosen rune, else the Shower's row when a power gives the
        // rune without choosing it (kind `rune`, Mempo of Twilight), else 0. Chosen and given, it counts once.
        uint32 ShowerOf(Player* player, uint32 id)
        {
            if (IsRune(id, "Meteor Shower"))
                return id;
            if (!ItemPowers::GrantsRune(player, "Meteor", "Meteor Shower"))
                return 0;
            for (Row const& row : Shells::Abilities)
                if (std::string_view("Meteor") == row.skill && std::string_view("Meteor Shower") == row.rune)
                    return row.id;
            return 0;
        }

        void Impact(Player* player, uint32 id, Position const& at, double pct, bool dynamo)
        {
            {
                std::lock_guard<std::recursive_mutex> guard(mutex);
                StateOf(player).empoweredNow = dynamo ? id : 0;
            }
            auto hit = Combat::StrikeArea(player, id, at, Combat::TargetRadius(id), pct);
            {
                std::lock_guard<std::recursive_mutex> guard(mutex);
                StateOf(player).empoweredNow = 0;
            }
            // Comet: "freezes chilled enemies ... upon impact".
            if (IsRune(id, "Comet"))
                for (Unit* target : hit)
                    if (Chilled(player, target))
                        Freeze(player, target, Num(id, "freeze_duration_seconds"));
            for (auto const& helper : Shells::Helpers)
                if (helper.owner == id && std::string_view(helper.identity).ends_with("molten ground"))
                    player->CastSpell(at.GetPositionX(), at.GetPositionY(), at.GetPositionZ(), helper.id, true);
        }
    } // namespace

    bool Delayed(Player* player, uint32 id, Position const& center, bool dynamo)
    {
        uint32 const shower = ShowerOf(player, id);
        double const delay = Num(shower ? shower : id, "delay_seconds");
        if (shower)
        {
            // Ruling (b): each of the spawn_count meteors lands at a
            // uniform random point of the 25-yard spread
            // (wizard.js:723), delay_seconds + i x the interval
            // (:732), for damage_pct each.
            unsigned const count = unsigned(Num(shower, "spawn_count"));
            double const spread = Num(shower, "radius_yards", "spread"), step = Num(shower, "delay_seconds", "interval");
            for (unsigned i = 0; i < count; ++i)
            {
                double const r = spread * std::sqrt(std::uniform_real_distribution<double>(0, 1)(Engine()));
                double const a = std::uniform_real_distribution<double>(0, 2 * std::numbers::pi)(Engine());
                Position at = center;
                float z = center.GetPositionZ();
                float const x = float(center.GetPositionX() + r * std::cos(a));
                float const y = float(center.GetPositionY() + r * std::sin(a));
                player->UpdateGroundPositionZ(x, y, z);
                at.Relocate(x, y, z);
                After(player, delay + i * step,
                      [shower, at, dynamo](Player* p) { Impact(p, shower, at, Num(shower, "damage_pct"), dynamo); });
            }
            return true;
        }
        double pct = Num(id, "damage_pct", "impact");
        // Star Pact: "Expend all remaining Arcane Power. Each point ...
        // increases the impact damage by {damage_pct}".
        if (IsRune(id, "Star Pact") && Resources::Displayed(player, Resources::ArcanePower))
        {
            double const extra = Resources::Get(player, Resources::ArcanePower);
            Resources::Empty(player, Resources::ArcanePower);
            pct += Num(id, "damage_pct") * extra;
        }
        After(player, delay, [id, center, pct, dynamo](Player* p) { Impact(p, id, center, pct, dynamo); });
        return true;
    }
} // namespace DC::Combat::Wizard::Meteor

namespace DC::Combat::Wizard
{
    using namespace Shared;

    bool LandsApart(std::string const& skill, std::string const& rune)
    {
        return skill == "Meteor" && rune == "Meteor Shower";
    }

    bool MeteorOnBar(Player* player)
    {
        for (Classes::Slot const& slot : Classes::Bar(player))
            if (IsSkill(slot.spellId, "Meteor"))
                return true;
        return false;
    }

    void CastMeteor(Player* player, Unit* target, std::string const& rune)
    {
        for (Shells::Ability const& ability : Shells::Abilities)
            if (std::string_view("Meteor") == ability.skill && rune == ability.rune)
            {
                player->CastSpell(target, ability.id, true);
                return;
            }
    }
} // namespace DC::Combat::Wizard
