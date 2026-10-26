/*
 * World of DiabloCraft - the Shaman's Attunement: one of four elements, worn as one buff, moved by the last Secondary
 * or Primal skill cast, each element giving a small bonus (dc_shaman_attunement.h has the rule).
 */

#include "dc_shaman_common.h"
#include "dc_shaman_attunement.h"
#include "dc_shaman_passives.h"
#include "../../items/dc_inventory.h"
#include "../../stats/dc_stats.h"
#include "SharedDefines.h"
#include "SpellInfo.h"
#include "SpellMgr.h"

#include <array>
#include <mutex>
#include <unordered_map>

namespace DC::Combat::Shaman::Attunement
{
    namespace
    {
        constexpr std::array<Element, 4> Elements = {Element::Fire, Element::Cold, Element::Physical,
                                                     Element::Lightning};

        char const* BuffName(Element element)
        {
            switch (element)
            {
                case Element::Fire:
                    return "Attunement - Fire - buff";
                case Element::Cold:
                    return "Attunement - Cold - buff";
                case Element::Physical:
                    return "Attunement - Physical - buff";
                case Element::Lightning:
                    return "Attunement - Lightning - buff";
            }
            return "";
        }

        struct State
        {
            Element element = Start;
            bool applied = false;      // the sheet holds the current element's bonus
            double appliedMaxLife = 0; // the maximum Life a Cold bonus was worked out from
            double appliedTimes = 1;   // what the bonus was multiplied by (Elemental Harmony)
        };

        std::mutex mutex;
        std::unordered_map<std::uint64_t, State> states;

        std::uint64_t Key(Player const* player)
        {
            return player->GetGUID().GetRawValue();
        }

        Table TableNow()
        {
            return {Tunable("attunement_fire_damage_pct"), Tunable("attunement_cold_life_regen_pct"),
                    Tunable("attunement_physical_armor_pct"), Tunable("attunement_lightning_attack_speed_pct")};
        }

        // Every sheet number an element's bonus can put on the Shaman, taken off.
        void Strip(std::uint64_t guid)
        {
            for (Element element : Elements)
            {
                std::uint32_t const id = BuffId(BuffName(element));
                Stats::RemoveContribution(guid, Source::Temporary, Stat::AttackSpeed, id);
                Stats::RemoveContribution(guid, Source::Temporary, Stat::Armor, id);
                Stats::RemoveContribution(guid, Source::Temporary, Stat::LifeRegen, id);
            }
        }

        // The element's bonus on the sheet (Fire's is a damage multiplier of its own, not a sheet number); false when
        // the Shaman's sheet is not loaded yet.
        bool Apply(Player* player, Element element, double times, double& maxLife)
        {
            std::uint64_t const guid = Key(player);
            std::uint32_t const id = BuffId(BuffName(element));
            Bonus const bonus = BonusOf(element, TableNow(), times);
            maxLife = double(player->GetMaxHealth());
            Strip(guid);
            bool ok = true;
            if (bonus.attackSpeedPct != 0)
                ok = Stats::AddContribution(
                    guid, {Source::Temporary, Stat::AttackSpeed, id, bonus.attackSpeedPct, Bucket::Flat});
            if (bonus.armorPct != 0)
                ok =
                    Stats::AddContribution(guid, {Source::Temporary, Stat::Armor, id, bonus.armorPct, Bucket::Percent});
            if (bonus.lifeRegenPct != 0)
                ok = Stats::AddContribution(
                    guid, {Source::Temporary, Stat::LifeRegen, id, maxLife * bonus.lifeRegenPct / 100.0, Bucket::Flat});
            if (ok)
            {
                Stats::Recompute(player);
                Inventory::PushSheet(player);
            }
            return ok;
        }

        // The one buff of the current element on the bar, the other three off it.
        void Show(Player* player, Element current)
        {
            for (Element element : Elements)
                BuffValues::Show(player, BuffId(BuffName(element)), element == current ? 1 : 0);
        }
    } // namespace

    // The element of the school a record deals: the picker's colour and the engine's one source for it.
    Element ElementOf(std::uint32_t spellId)
    {
        SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId);
        switch (info ? info->SchoolMask : 0u)
        {
            case SPELL_SCHOOL_MASK_FIRE:
                return Element::Fire;
            case SPELL_SCHOOL_MASK_FROST:
                return Element::Cold;
            case SPELL_SCHOOL_MASK_NATURE:
                return Element::Lightning;
            default:
                return Element::Physical;
        }
    }

    void Cast(Player* player, std::uint32_t spellId)
    {
        auto const* row = Shells::FindAbility(spellId);
        if (!IsShaman(player) || !row || !Sets(Classes::CategoryOf(spellId), row->skill, row->rune))
            return;
        Element const cast = ElementOf(spellId);
        std::lock_guard<std::mutex> guard(mutex);
        State& state = states[Key(player)];
        if (state.element == cast)
            return;
        state.element = cast;
        state.applied = false; // the next upkeep puts the new bonus on the sheet and the new buff on the bar
    }

    void Multipliers(Player* player, DC::Combat::Factors& out)
    {
        if (!IsShaman(player))
            return;
        Element element = Start;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = states.find(Key(player));
            if (found != states.end())
                element = found->second.element;
        }
        if (double const pct = BonusOf(element, TableNow(), Passive::HarmonyFor(player)).damagePct)
            AddFactor(out, "Attunement", pct);
    }

    void MoveTo(Player* player, std::string_view element)
    {
        if (!IsShaman(player))
            return;
        Element cast;
        if (element == "fire")
            cast = Element::Fire;
        else if (element == "cold")
            cast = Element::Cold;
        else if (element == "physical")
            cast = Element::Physical;
        else if (element == "lightning")
            cast = Element::Lightning;
        else
            return;
        std::lock_guard<std::mutex> guard(mutex);
        State& state = states[Key(player)];
        if (state.element == cast)
            return;
        state.element = cast;
        state.applied = false; // the next upkeep puts the new bonus on the sheet and the new buff on the bar
    }

    char const* Current(Player* player)
    {
        if (!IsShaman(player))
            return "";
        Element element = Start;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = states.find(Key(player));
            if (found != states.end())
                element = found->second.element;
        }
        switch (element)
        {
            case Element::Fire:
                return "fire";
            case Element::Cold:
                return "cold";
            case Element::Physical:
                return "physical";
            default:
                return "lightning";
        }
    }

    void Upkeep(Player* player)
    {
        if (!IsShaman(player))
            return;
        Element element;
        bool applied;
        double appliedMaxLife;
        double appliedTimes;
        double const times = Passive::HarmonyFor(player);
        {
            std::lock_guard<std::mutex> guard(mutex);
            State const& state = states[Key(player)];
            element = state.element;
            applied = state.applied;
            appliedMaxLife = state.appliedMaxLife;
            appliedTimes = state.appliedTimes;
        }
        // Cold's regeneration is a share of the maximum Life, so a maximum that moved needs the number worked out
        // again.
        bool const stale = element == Element::Cold && appliedMaxLife != double(player->GetMaxHealth());
        // The bonus is worked out again when Elemental Harmony came or went.
        if (!applied || stale || appliedTimes != times)
        {
            double maxLife = 0;
            bool const done = Apply(player, element, times, maxLife);
            std::lock_guard<std::mutex> guard(mutex);
            State& state = states[Key(player)];
            if (state.element == element)
            {
                state.applied = done;
                state.appliedMaxLife = maxLife;
                state.appliedTimes = times;
            }
        }
        Show(player, element);
    }

    void Forget(Player* player)
    {
        Strip(Key(player));
        std::lock_guard<std::mutex> guard(mutex);
        states.erase(Key(player));
    }
} // namespace DC::Combat::Shaman::Attunement
