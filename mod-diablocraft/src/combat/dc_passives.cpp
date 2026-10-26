// Which passives a player has, any class's, and the gear and paragon cost and cooldown auras rebuilt from the sheet.
// A class's own passive code answers the engine's other calls (dc_passives.h) and keeps its own state.
#include "dc_passives.h"
#include "dc_gem_powers.h"
#include "dc_item_powers.h"
#include "dc_spell_shells.h"
#include "dc_cost_math.h"
#include "dc_combat.h"
#include "../classes/barbarian/dc_barbarian_passives.h"
#include "../classes/dc_classes.h"
#include "../stats/dc_stats.h"
#include "../items/dc_items.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "SpellAuraEffects.h"
#include "SpellAuras.h"
#include <algorithm>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

namespace DC::Combat::Passives
{
    namespace
    {
        // A class's passive code holds its own lock while it calls Has, so nothing here calls into a class while
        // this one is held.
        std::recursive_mutex mutex;
        struct State
        {
            std::vector<std::string> selected;
            bool loaded = false;
        };
        std::unordered_map<uint64, State> states;
    } // namespace

    namespace
    {
        // One gear-and-paragon aura, rebuilt from the sheet and then measured
        // back out of the core. The two reductions are the same shape - a
        // hidden spell modifier whose amount is whole percent - so they are
        // the same six steps, and the only difference is which modifier is
        // asked and what a reduction of it is measured on.
        //
        // The sheet has to be the gear and paragon contributions alone before
        // it can say what they are: the measured number is published into it,
        // so it is taken out and the sheet rebuilt first. That is also why
        // this never reads its own output.
        template <class Measure>
        void RebuildGearModifier(Player* p, uint32 gearId, Stat stat, Measure&& measure)
        {
            auto guid = p->GetGUID().GetRawValue();
            Stats::RemoveContribution(guid, Source::Temporary, stat, gearId);
            Stats::Recompute(p);
            auto sheet = Stats::Get(guid);
            double const gear = sheet ? (*sheet)[stat] : 0.0;
            int32 const amount = CostMath::ModifierAmount(gear);
            Aura* current = p->GetAura(gearId);
            AuraEffect const* effect = current ? current->GetEffect(EFFECT_0) : nullptr;
            if (!effect || effect->GetAmount() != amount)
            {
                if (current)
                    p->RemoveAurasDueToSpell(gearId);
                if (amount != 0)
                {
                    int32 value = amount;
                    p->CastCustomSpell(p, gearId, &value, nullptr, nullptr, true);
                }
            }

            // What the core does with the player's own modifiers on, asked of
            // the core itself. That number is the display: not the sheet's own
            // product, and not a correction to it, because a whole-percent
            // aura on a fractional gear number reduces by less than the
            // sheet's contributions say and no additional factor can bring a
            // product back up. Gear 33.4 pays 33 and shows 33.
            Stats::AddContribution(guid, {Source::Temporary, stat, gearId, measure(),
                                          Bucket::Derived});
            Stats::Recompute(p);
        }
    } // namespace

    // The one place the gear and paragon reductions are rebuilt.
    // Moving the payment onto an aura is what made this
    // necessary: the core charges the cost and installs the cooldown from what
    // the auras say, so an item, a gem or a paragon point that changes
    // Resource Cost Reduction or Cooldown Reduction has to reach the aura, not
    // just the sheet. Every caller that can change one calls this.
    void RefreshModifiers(Player* p)
    {
        if (!p)
            return;
        // Issue #61: a modifier reaches only its own record's family, so each
        // class has its own pair of gear auras and its own probes, looked up
        // by class_map.csv's class_id. A class with no generated records has
        // no row and nothing to rebuild.
        Shells::GearModifier const* gear = Shells::GearModifierFor(Classes::ClassIdOf(p));
        if (!gear)
            return;
        RebuildGearModifier(p, gear->cost, Stat::ResourceCostReduction, [&]
        { return 100.0 * (1.0 - CostReductionFactor(p, gear->costProbe)); });
        // Step 6: the same for the cooldown. The percentage is measured on a
        // record that carries a real RecoveryTime and every skill's mask bit,
        // so this aura reaches it; Boon of Bul-Kathos names its own three
        // skills and is not part of a gear number.
        RebuildGearModifier(p, gear->cooldown, Stat::CooldownReduction, [&]
        { return CooldownReductionPercent(p, gear->cooldownProbe); });
    }

    namespace
    {
        class Update final : public PlayerScript
        {
        public:
            Update()
                : PlayerScript("dc_passives_update", {PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_MAP_CHANGED})
            {
            }
            void OnPlayerLogout(Player* p) override
            {
                std::lock_guard<std::recursive_mutex> guard(mutex);
                states.erase(p->GetGUID().GetRawValue());
            }
            void OnPlayerMapChanged(Player* p) override
            {
                Invalidate(p);
            }
        };
    } // namespace
    bool Has(Player* p, char const* name)
    {
        // Any class's slotted passives (Prodigy).
        // Names are unique across classes (generate_spells.py refuses a shared
        // one), so a Barbarian passive never answers for a Wizard.
        if (!p || !Classes::Playable(p))
            return false;
        std::lock_guard<std::recursive_mutex> guard(mutex);
        auto& s = states[p->GetGUID().GetRawValue()];
        if (!s.loaded)
        {
            s.selected = Items::WithGrantedPassives(p, Classes::Passives(p)); // the chosen passives plus the ones worn items grant
            s.loaded = true;
        }
        return std::find(s.selected.begin(), s.selected.end(), name) != s.selected.end();
    }
    void Invalidate(Player* p)
    {
        if (!p)
            return;
        {
            std::lock_guard<std::recursive_mutex> guard(mutex);
            auto& s = states[p->GetGUID().GetRawValue()];
            s.loaded = false;
        }
        Barbarian::Changed(p);
    }
    void Hit(Player* p, Unit* target, uint32 spellId, unsigned school)
    {
        GemPowers::Hit(p, target, spellId, school);
        ItemPowers::Hit(p, target, spellId);
        Barbarian::Hit(p, target);
        ItemPowers::HitElement(p, target, school);
    }
    void Taken(Player* p, unsigned school, bool ranged, double damage)
    {
        ItemPowers::Taken(p);
        ItemPowers::TakenElement(p, school, damage);
        Barbarian::Taken(p, school, ranged);
    }
    void RegisterScripts()
    {
        Barbarian::RegisterScripts();
        new Update();
    }
} // namespace DC::Combat::Passives
