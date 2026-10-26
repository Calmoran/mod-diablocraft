#include "dc_wizard_passives.h"
#include "../../combat/dc_item_powers.h"
#include "SpellMgr.h"
#include <algorithm>
#include <iterator>

namespace DC::Combat::Wizard::Passive
{
    using namespace Shared;

    // Prodigy: "When you cast a Signature spell, you gain 5 Arcane Power" (wizard_passives.csv).
    void Prodigy(Player* player, std::uint32_t spellId)
    {
        if (Signature(spellId) && Has(player, "Prodigy"))
            if (uint32 id = PassiveId("Prodigy"))
                Combat::GainResource(player, id, Num(id, "gain_resource"));
    }

    void ArcaneDynamo(Player* player, State& state, std::uint32_t spellId)
    {
        // Arcane Dynamo (wizard.js:1265-1283): a Signature spell adds a
        // Flash of Insight; at the threshold the next of the ten listed
        // skills deals more, and the Flashes are spent.
        if (uint32 dynamo = PassiveId("Arcane Dynamo"); dynamo && Has(player, "Arcane Dynamo"))
        {
            static constexpr std::string_view listed[] = {
                "Ray of Frost",  "Arcane Orb",     "Arcane Torrent", "Disintegrate", "Hydra",
                "Wave of Force", "Energy Twister", "Meteor",         "Blizzard",     "Explosive Blast"};
            state.empowered = 0;
            unsigned const threshold = unsigned(Num(dynamo, "stack_threshold_count"));
            if (Signature(spellId))
                state.flashes = std::min(state.flashes + 1, threshold);
            else if (Row const* row = RowOf(spellId);
                     row && threshold && state.flashes >= threshold &&
                     std::find(std::begin(listed), std::end(listed), std::string_view(row->skill)) != std::end(listed))
            {
                state.empowered = spellId;
                state.flashes = 0;
            }
        }
    }

    void IllusionistBegin(Player* player, State& state, std::uint32_t spellId)
    {
        // Illusionist: "When you use Mirror Image, Slow Time, or Teleport,
        // your movement speed is increased".
        if (uint32 id = PassiveId("Illusionist");
            id && Has(player, "Illusionist") &&
            (IsSkill(spellId, "Mirror Image") || IsSkill(spellId, "Slow Time") || IsSkill(spellId, "Teleport")))
            state.illusionistSpeed = Now() + uint64(Num(id, "duration_seconds", "speed") * 1000);
    }

    bool UnstableAnomaly(Player* victim, State& state, uint64 now, std::uint32_t& damage)
    {
        // Unstable Anomaly: fatal damage becomes a shield, once every
        // internal_cooldown_seconds. Its shockwave is not built: it has
        // no sourced radius.
        if (uint32 id = PassiveId("Unstable Anomaly");
            id && Has(victim, "Unstable Anomaly") && damage >= victim->GetHealth() && now >= state.anomalyReady)
        {
            state.anomalyReady = now + uint64(Num(id, "internal_cooldown_seconds") * 1000);
            damage = 0;
            Shield(victim, "Unstable Anomaly - shield", Num(id, "absorb_capacity_life_pct"),
                   Num(id, "duration_seconds"));
            return true;
        }
        return false;
    }

    void Illusionist(Player* victim, State& state, uint64 now, double maxLife, std::uint32_t damage)
    {
        // Illusionist: "more than {damage_threshold_pct} of your maximum
        // Life in damage within {duration_seconds:window} second".
        if (uint32 id = PassiveId("Illusionist"); id && Has(victim, "Illusionist"))
        {
            uint64 const window = uint64(Num(id, "duration_seconds", "window") * 1000);
            std::erase_if(state.recentDamage, [now, window](auto const& hit) { return hit.first + window < now; });
            state.recentDamage.push_back({now, double(damage)});
            double total = 0;
            for (auto const& hit : state.recentDamage)
                total += hit.second;
            if (total > maxLife * Num(id, "damage_threshold_pct") / 100)
            {
                state.recentDamage.clear();
                for (Classes::Slot const& entry : Classes::Bar(victim))
                    if (IsSkill(entry.spellId, "Mirror Image") || IsSkill(entry.spellId, "Slow Time") ||
                        IsSkill(entry.spellId, "Teleport"))
                    {
                        victim->RemoveSpellCooldown(entry.spellId, true);
                        if (SpellInfo const* info = sSpellMgr->GetSpellInfo(entry.spellId);
                            info && info->GetCategory())
                            victim->RemoveCategoryCooldown(info->GetCategory());
                    }
            }
        }
    }

    void Evocation(Player* player)
    {
        // Evocation's SPELLMOD_COOLDOWN is on while it is slotted.
        if (uint32 id = PassiveId("Evocation"))
        {
            bool const slotted = Has(player, "Evocation");
            if (slotted && !player->HasAura(id))
                player->AddAura(id, player);
            else if (!slotted && player->HasAura(id))
                player->RemoveAurasDueToSpell(id);
        }
    }

    void GalvanizingWard(Player* player, uint64 now)
    {
        // Galvanizing Ward: "As long as you have not taken damage in
        // the last {duration_seconds} seconds you gain a shield".
        if (uint32 id = PassiveId("Galvanizing Ward"); id && Has(player, "Galvanizing Ward"))
        {
            uint64 last;
            {
                std::lock_guard<std::recursive_mutex> guard(mutex);
                last = StateOf(player).lastDamaged;
            }
            uint32 const shield = Shells::HelperFor("Galvanizing Ward - shield");
            if (shield && !player->HasAura(shield) && now >= last + uint64(Num(id, "duration_seconds") * 1000))
                Shield(player, "Galvanizing Ward - shield", Num(id, "absorb_capacity_life_pct"), -1);
        }
    }

    void Dominance(Player* player)
    {
        // Dominance: each kill a stack, up to max_stacks_count; the
        // shield is refreshed to its full potency and each stack
        // adds duration_seconds (wizard.js:1263-1268: 180 + 30 x
        // min(stacks + 1, 10) frames).
        if (uint32 id = PassiveId("Dominance"); id && Has(player, "Dominance"))
        {
            uint32 const shield = Shells::HelperFor("Dominance - shield");
            unsigned stacks;
            {
                std::lock_guard<std::recursive_mutex> guard(mutex);
                State& state = StateOf(player);
                if (!player->HasAura(shield))
                    state.dominance = 0;
                state.dominance = std::min(state.dominance + 1, unsigned(Num(id, "max_stacks_count")));
                stacks = state.dominance;
            }
            Shield(player, "Dominance - shield", Num(id, "absorb_capacity_life_pct") * stacks,
                   Num(id, "absorb_duration_seconds") + Num(id, "duration_seconds") * stacks);
        }
    }
} // namespace DC::Combat::Wizard::Passive

namespace DC::Combat::Wizard
{
    using namespace Shared;

    double TargetFactor(Player* player, Unit* target)
    {
        uint32 const id = PassiveId("Elemental Exposure");
        if (!player || !target || !id || !Has(player, "Elemental Exposure"))
            return 1.0;
        // Primordial Soul raises the number per stack (kind `passive`); taken before the lock, the item powers take their own.
        double const perStack = ItemPowers::PassiveSetTo(player, "Elemental Exposure", "damage_taken_pct", Num(id, "damage_taken_pct"));
        std::lock_guard<std::recursive_mutex> guard(mutex);
        auto found = StateOf(player).marks.find(target->GetGUID().GetRawValue());
        if (found == StateOf(player).marks.end())
            return 1.0;
        uint64 const now = Now();
        auto stacks = std::count_if(found->second.exposure.begin(), found->second.exposure.end(),
                                    [now](auto const& entry) { return entry.second > now; });
        return 1 + perStack *
                       double(std::min<std::ptrdiff_t>(stacks, std::ptrdiff_t(Num(id, "max_stacks_count")))) / 100;
    }

    double TargetFactor(Player* player, Unit* target, Factors& out)
    {
        double const factor = TargetFactor(player, target);
        if (factor != 1.0)
            out.emplace_back("Elemental Exposure", factor);
        return factor;
    }
} // namespace DC::Combat::Wizard
