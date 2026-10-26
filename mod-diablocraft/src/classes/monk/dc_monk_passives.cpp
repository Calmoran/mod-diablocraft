/*
 * The Monk's passives Resolve, Fleet Footed, Exalted Soul, Transcendence, Chant of Resonance and Seize the
 * Initiative. Numbers: monk_passive_values.csv, through each passive's record. "Has" is Combat::Passives::Has: the
 * chosen passives plus the ones a worn item grants (the Hellfire Amulet), the Wizard's way.
 *
 * The stat rows are kept by a tick, the Wizard's way (dc_wizard_buffs.cpp Wanted): every look adds what is wanted and
 * removes what is not, and the first look after a login removes all three whatever the save held (a Temporary row is
 * saved with the character).
 */

#include "dc_monk_common.h"
#include "../dc_level_heal.h"
#include "dc_monk_passives.h"
#include "dc_monk_spirit.h"
#include "../dc_resources.h"
#include "../../combat/dc_passives.h"
#include "../../stats/dc_resource_pulse.h"
#include "../../stats/dc_stats.h"
#include "ScriptMgr.h"
#include "SpellInfo.h"
#include "SpellMgr.h"

namespace DC::Combat::Monk::Passive
{
    namespace
    {
        // How often the stat rows are looked at (not a game number: how soon a chosen passive shows on the sheet).
        constexpr std::uint64_t PollMs = 250;

        struct State
        {
            bool looked = false;  // the first look clears what a save left
            unsigned applied = 0; // Bit
            std::uint64_t nextPoll = 0;
            std::uint64_t spiritClock = 0;
            std::uint64_t seizeUntil = 0;
            SpendMeter spent;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, State> states;

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        std::uint32_t IdOf(std::string_view name)
        {
            for (auto const& passive : Shells::Passives)
                if (name == passive.name)
                    return passive.id;
            return 0;
        }

        bool Has(Player* player, char const* name)
        {
            return Combat::Passives::Has(player, name);
        }

        // "when you have a Mantra learned": a skill of the Mantras category on the skill buttons.
        bool MantraSlotted(Player* player)
        {
            for (unsigned slot = 0; slot < Classes::ActiveSlots(); ++slot)
                if (ActionButton const* button = player->GetActionButton(uint8(slot)))
                    if (button->GetType() == ACTION_BUTTON_SPELL &&
                        Classes::CategoryOf(button->GetAction()) == "Mantras")
                        return true;
            return false;
        }

        struct Row
        {
            unsigned bit;
            char const* passive;
            Stat stat;
            char const* token;
            Bucket bucket;
        };
        // Fleet Footed: "Increase movement speed by {movement_speed_pct}" (uncapped, as the Barbarian's Sprint);
        // Exalted Soul: "Increase maximum Spirit by {max_pool_resource}" (the resource maximum Paragon raises);
        // Seize the Initiative: "increases your attack speed by {attack_speed_pct} for {duration_seconds} seconds".
        constexpr Row Rows[] = {
            {FleetFooted, "Fleet Footed", Stat::MovementSpeed, "movement_speed_pct", Bucket::Uncapped},
            {ExaltedSoul, "Exalted Soul", Stat::MaxFury, "max_pool_resource", Bucket::Flat},
            {Seize, "Seize the Initiative", Stat::AttackSpeed, "attack_speed_pct", Bucket::Flat},
        };

        void Tick(Player* player, uint32 diff)
        {
            std::uint64_t const now = Now();
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            unsigned wanted = 0;
            bool first = false;
            Change change;
            double spentPoints = 0;
            unsigned seconds = 0;
            bool const exalted = Has(player, "Exalted Soul");
            bool const chant = Has(player, "Chant of Resonance") && MantraSlotted(player);
            bool const transcendence = Has(player, "Transcendence");
            {
                std::lock_guard<std::mutex> guard(mutex);
                State& state = states[guid];
                if (transcendence && Resources::Displayed(player, Resources::Spirit))
                    spentPoints = state.spent.Look(Resources::Get(player, Resources::Spirit),
                                                   Resources::Max(player, Resources::Spirit));
                else
                    state.spent = SpendMeter{};
                if (exalted || chant)
                    seconds = WholeSeconds(state.spiritClock, diff);
                else
                    state.spiritClock = 0;
                if (now < state.nextPoll)
                    wanted = state.applied;
                else
                {
                    state.nextPoll = now + PollMs;
                    wanted = (Has(player, "Fleet Footed") ? FleetFooted : 0) | (exalted ? ExaltedSoul : 0) |
                             (now < state.seizeUntil && Has(player, "Seize the Initiative") ? Seize : 0);
                    first = !state.looked;
                    state.looked = true;
                    change = Reconcile(first ? (FleetFooted | ExaltedSoul | Seize) : state.applied, wanted);
                    state.applied = wanted;
                }
            }
            if (change.add || change.remove)
            {
                for (Row const& row : Rows)
                {
                    std::uint32_t const id = IdOf(row.passive);
                    if (change.remove & row.bit)
                        Stats::RemoveContribution(guid, Source::Temporary, row.stat, id);
                    if (change.add & row.bit)
                        Stats::AddContribution(
                            guid, {Source::Temporary, row.stat, id, Numbers::Num(id, row.token), row.bucket});
                }
                Stats::Recompute(player);
            }
            // "Every point of Spirit spent heals you for {heal_per_hit_life} Life. Heal amount is increased by
            // {healing_bonus_share_pct} of your Health Globe Healing Bonus." Torment has no Health Globe Healing Bonus
            // stat yet, so the share adds nothing until it has one.
            // ponytail: a spend and a gain inside one server update net out (a primary's Spirit landing in the same
            // update as a spender's cost); exact needs a hook where the core takes the cost.
            if (spentPoints > 0 && player->IsAlive())
                if (std::uint32_t const id = IdOf("Transcendence"))
                {
                    HealInfo heal(player, player, uint32(spentPoints * Classes::HealAtLevel(Numbers::Num(id, "heal_per_hit_life"), player->GetLevel())),
                                  sSpellMgr->GetSpellInfo(id), SPELL_SCHOOL_MASK_NORMAL);
                    player->HealBySpell(heal);
                }
            // Exalted Soul: "increase Spirit Regeneration by {regen_per_second_resource} per second"; Chant of
            // Resonance: "you gain {regen_per_second_resource} Spirit every second when you have a Mantra learned".
            if (seconds)
            {
                double points = 0;
                if (exalted)
                    points += Numbers::Num(IdOf("Exalted Soul"), "regen_per_second_resource");
                if (chant)
                    points += Numbers::Num(IdOf("Chant of Resonance"), "regen_per_second_resource");
                // Paid as a flow over the seconds it is for, so the pool climbs smoothly;
                // a gain is no spend to the meter, which only counts drops.
                Resources::Flow(player, Resources::Spirit, points * seconds, seconds * 1000);
            }
        }

        class Keeper final : public PlayerScript
        {
        public:
            Keeper()
                : PlayerScript("dc_monk_passives", {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT})
            {
            }
            void OnPlayerUpdate(Player* player, uint32 diff) override
            {
                if (Classes::Playable(player))
                    Tick(player, diff);
            }
            void OnPlayerLogout(Player* player) override
            {
                std::lock_guard<std::mutex> guard(mutex);
                states.erase(player->GetGUID().GetRawValue());
            }
        };
    } // namespace

    void Landed(Player* player, Unit* target, std::uint32_t /*spellId*/)
    {
        if (!player || !target)
            return;
        // Resolve: "Damage you deal reduces enemy damage by {enemy_damage_pct} for {duration_seconds} seconds."
        if (Has(player, "Resolve"))
            if (std::uint32_t const id = IdOf("Resolve"))
                Effects::Weaken(target, id, Numbers::Num(id, "enemy_damage_pct"), Numbers::Num(id, "duration_seconds"));
        // Seize the Initiative: the hit on an enemy above the threshold starts (or renews) the attack speed; the tick
        // puts it on the sheet.
        if (Has(player, "Seize the Initiative"))
            if (std::uint32_t const id = IdOf("Seize the Initiative");
                id && Above(target->GetHealthPct(), Numbers::Num(id, "life_threshold_pct")))
            {
                std::lock_guard<std::mutex> guard(mutex);
                states[player->GetGUID().GetRawValue()].seizeUntil =
                    Now() + std::uint64_t(Numbers::Num(id, "duration_seconds") * 1000);
            }
    }

    void Cast(Player* player, std::uint32_t spellId)
    {
        // Chant of Resonance: a mantra's activation pays back the reduced share of the Spirit it paid (Strike from
        // Beyond's way): the record's cost after the player's own reductions.
        if (!player || Classes::CategoryOf(spellId) != "Mantras" || !Has(player, "Chant of Resonance"))
            return;
        SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId);
        std::uint32_t const id = IdOf("Chant of Resonance");
        if (!info || !id || Powers(info->PowerType) != Resources::Slot(Resources::Spirit))
            return;
        double const paid = Resources::ToPoints(Resources::Spirit, info->CalcPowerCost(player, info->GetSchoolMask()));
        Generate(player, Classes::ClassIdOf(player), id, PaidBack(paid, Numbers::Num(id, "cost_reduction_pct")), false);
    }

    void RegisterScripts()
    {
        new Keeper();
    }
} // namespace DC::Combat::Monk::Passive
