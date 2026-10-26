/*
 * The Demon Hunter's passives that need code: Thrill of the Hunt, Tactical Advantage, Blood Vengeance, Steady Aim, Cull
 * the Weak and Night Stalker; Brooding, Hot Pursuit, Archery, Numbing Traps, Perfectionist and Custom Engineering. The
 * numbers are demon_hunter_passive_values.csv (the passive's name is its skill) and the passives' power files, read
 * through each passive's record.
 *
 * A passive is on when it sits in one of the Demon Hunter's passive slots, or a worn item grants it (Passives::Has).
 * Thrill of the Hunt, Hot Pursuit and Numbing Traps ride the hit (Landed) and the class's slow; Tactical Advantage
 * rides the cast of Vault, Shadow Power and Smoke Screen and Evasive Fire's backflip; Night Stalker adds to a Primary's
 * generation; Steady Aim, Cull the Weak and Archery's bow ride the hit's multipliers; Blood Vengeance's pool,
 * Perfectionist's armor and resistance and Archery's critical bonuses are sheet contributions a small update script
 * keeps; Brooding and Archery's Hatred tick on the same script; Perfectionist's cut stands on the Discipline skills'
 * hidden cost auras (CostCut), so the core charges the lower cost; Custom Engineering gives the skills that ask their
 * longer seconds and larger numbers. Blood Vengeance's globe pay waits for the globes' pickup call.
 */

#include "dc_demon_hunter_passives.h"
#include "dc_demon_hunter_clock.h"
#include "dc_demon_hunter_common.h"
#include "dc_demon_hunter_effects.h"
#include "dc_demon_hunter_hatred.h"
#include "../dc_classes.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_cost_cut.h"
#include "../../combat/dc_enemy_effects.h"
#include "../../combat/dc_healing_table.h"
#include "../../combat/dc_movement_effects.h"
#include "../../combat/dc_passives.h"
#include "../../combat/dc_spell_numbers.h"
#include "../../stats/dc_stats.h"
#include "GameTime.h"
#include "Item.h"
#include "ItemTemplate.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "Spell.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"
#include "Util.h"

#include <map>
#include <mutex>
#include <tuple>
#include <unordered_map>
#include <unordered_set>

namespace DC::Combat::DemonHunter::Passive
{
    namespace
    {
        std::uint32_t Id(std::string_view name)
        {
            for (auto const& passive : Shells::Passives)
                if (name == passive.name)
                    return passive.id;
            return 0;
        }

        bool IsDemonHunter(Player const* player)
        {
            return player && Classes::ClassIdOf(player) == Resources::Hatred.classId;
        }

        bool On(Player* player, char const* name)
        {
            return IsDemonHunter(player) && Combat::Passives::Has(player, name);
        }

        double Num(char const* name, char const* token, char const* qualifier = "")
        {
            return Numbers::Num(Id(name), token, qualifier);
        }

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        bool IsPrimary(std::uint32_t spellId)
        {
            return Classes::CategoryOf(spellId) == "Primary";
        }

        // A skill that costs Hatred: the record's Energy cost, or the start the module pays (Rapid Fire).
        bool SpendsHatredNow(std::uint32_t spellId)
        {
            SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId);
            bool const recorded = info && info->PowerType == POWER_ENERGY && info->ManaCost > 0;
            bool const module = Numbers::Get(spellId, "cost_resource", "initial").value_or(0) > 0;
            return !Classes::CategoryOf(spellId).empty() && SpendsHatred(IsPrimary(spellId), recorded, module);
        }

        // Grenadier's grenades: the Grenade skill, Rapid Fire's Bombardment, Vengeance's Personal Mortar and the giant grenade.
        bool IsGrenade(std::uint32_t spellId)
        {
            if (spellId == Shells::HelperFor(GrenadierBlast))
                return true;
            auto const* row = Shells::FindAbility(spellId);
            return row && GrenadeSkill(row->skill, row->rune);
        }

        // The weapon kind in a slot: a bow, a crossbow or a hand crossbow, none for anything else or nothing.
        Weapon WeaponIn(Player* player, std::uint8_t slot)
        {
            Item const* item = player->GetItemByPos(INVENTORY_SLOT_BAG_0, slot);
            ItemTemplate const* worn = item ? item->GetTemplate() : nullptr;
            if (!worn || worn->Class != ITEM_CLASS_WEAPON)
                return Weapon::None;
            bool const oneHanded = worn->InventoryType == INVTYPE_WEAPON ||
                                   worn->InventoryType == INVTYPE_WEAPONMAINHAND ||
                                   worn->InventoryType == INVTYPE_WEAPONOFFHAND;
            return WeaponOf(worn->SubClass, oneHanded);
        }

        Archery ArcheryHeld(Player* player)
        {
            return ArcheryOf(WeaponIn(player, EQUIPMENT_SLOT_MAINHAND), WeaponIn(player, EQUIPMENT_SLOT_OFFHAND));
        }

        // What each Demon Hunter has: Steady Aim's bonus until, the clocks, the sheet contributions held, Brooding's
        // stacks.
        std::mutex mutex;
        std::unordered_map<std::uint64_t, std::uint64_t> steadyUntil;
        std::unordered_map<std::uint64_t, double> steadyClock;
        std::unordered_map<std::uint64_t, double> refreshClock;
        std::unordered_map<std::uint64_t, double> broodingClock;
        std::unordered_map<std::uint64_t, double> archeryClock;
        std::unordered_map<std::uint64_t, Still> brooding;
        std::unordered_map<std::uint64_t, double> sharpClock;
        std::unordered_map<std::uint64_t, Sharp> sharp;
        std::unordered_map<std::uint64_t, double> singleClock;
        // The Demon Hunters whose Perfectionist cut stands now (PerfectionistCut).
        std::unordered_set<std::uint64_t> perfecting;
        // The enemies Single Out found alone at its last look, for each Demon Hunter.
        std::unordered_map<std::uint64_t, std::unordered_set<std::uint64_t>> singled;
        // The contribution a passive holds on a sheet: (player, stat, passive's id) -> the value, so a changed value or
        // a passive taken out is put right.
        std::map<std::tuple<std::uint64_t, Stat, std::uint32_t>, double> held;

        // A passive's sheet contribution: `wanted` (0 for none) in place of what was held. True when it changed.
        bool Hold(Player* player, Stat stat, Bucket bucket, char const* passive, double wanted)
        {
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            std::uint32_t const id = Id(passive);
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto found = held.find({guid, stat, id});
                double const had = found == held.end() ? 0.0 : found->second;
                if (had == wanted)
                    return false;
                if (wanted == 0.0)
                    held.erase({guid, stat, id});
                else
                    held[{guid, stat, id}] = wanted;
            }
            Stats::RemoveContribution(guid, Source::Passives, stat, id);
            if (wanted != 0.0)
                Stats::AddContribution(guid, {Source::Passives, stat, id, wanted, bucket});
            return true;
        }

        // The Life per Kill on the Demon Hunter's sheet now.
        double LifePerKill(Player* player)
        {
            auto const sheet = Stats::Get(player->GetGUID().GetRawValue());
            return sheet ? (*sheet)[Stat::LifePerKill] : 0.0;
        }

        // Sharpshooter: the stacks gone once a critical hit's reset has passed, and what they are worth on the sheet.
        bool SharpSync(Player* player)
        {
            double worth = 0.0;
            if (On(player, "Sharpshooter"))
            {
                std::lock_guard<std::mutex> guard(mutex);
                Sharp& state = sharp[player->GetGUID().GetRawValue()];
                if (state.resetAtMs && Now() >= state.resetAtMs)
                    state = Sharp{};
                worth = SharpWorth(state, Now(), Num("Sharpshooter", "crit_chance_pct"));
            }
            else
            {
                std::lock_guard<std::mutex> guard(mutex);
                sharp.erase(player->GetGUID().GetRawValue());
            }
            return Hold(player, Stat::CritChance, Bucket::Flat, "Sharpshooter", worth);
        }

        // The skills that cost Discipline (demon_hunter_skills.csv): each has the hidden cost aura Perfectionist's cut stands on.
        constexpr std::string_view DisciplineSkills[] = {"Caltrops", "Smoke Screen", "Shadow Power", "Vault", "Marked for Death"};

        // Perfectionist: "Reduce the Discipline cost of all skills by {cost_reduction_pct}": the cost the core charges is lower BEFORE the
        // cast, through each Discipline skill's hidden cost aura (CostCut), for as long as the passive is slotted or worn. Kept to what the
        // passive is now: a change puts the cut on or takes it off.
        void PerfectionistCut(Player* player, bool perfect)
        {
            {
                std::lock_guard<std::mutex> guard(mutex);
                std::uint64_t const guid = player->GetGUID().GetRawValue();
                if (perfect == (perfecting.count(guid) > 0))
                    return;
                if (perfect)
                    perfecting.insert(guid);
                else
                    perfecting.erase(guid);
            }
            for (std::string_view skill : DisciplineSkills)
                CostCut::Stand(player, skill, Id("Perfectionist"), perfect ? Num("Perfectionist", "cost_reduction_pct") : 0.0);
        }

        // The sheet contributions of the passives that only change the sheet: Blood Vengeance's "maximum Hatred is
        // increased by {max_pool_resource}", Perfectionist's armor and resistance to all damage types by
        // {resistance_pct}, Archery's Crossbow
        // "{crit_damage_pct} Critical Hit Damage" and Hand Crossbow "{crit_chance_pct} Critical Hit Chance".
        void Sync(Player* player)
        {
            Archery const bow = On(player, "Archery") ? ArcheryHeld(player) : Archery{};
            bool changed = false;
            changed |= Hold(player, Stat::MaxFury, Bucket::Flat, "Blood Vengeance",
                            On(player, "Blood Vengeance") ? Num("Blood Vengeance", "max_pool_resource") : 0.0);
            bool const perfect = On(player, "Perfectionist");
            PerfectionistCut(player, perfect);
            changed |= Hold(player, Stat::Armor, Bucket::Percent, "Perfectionist",
                            perfect ? Num("Perfectionist", "resistance_pct") : 0.0);
            changed |= Hold(player, Stat::AllResistance, Bucket::Percent, "Perfectionist",
                            perfect ? Num("Perfectionist", "resistance_pct") : 0.0);
            changed |= Hold(player, Stat::CritDamage, Bucket::Flat, "Archery",
                            bow.crossbow ? Num("Archery", "crit_damage_pct") : 0.0);
            changed |= Hold(player, Stat::CritChance, Bucket::Flat, "Archery",
                            bow.hand ? Num("Archery", "crit_chance_pct") : 0.0);
            // Leech: "Gain {heal_per_hit_life} Life per Hit", the power file's share of the Healing table at the level, and a share of
            // the Life per Kill on top.
            changed |= Hold(player, Stat::LifePerHit, Bucket::Flat, "Leech (Demon Hunter)",
                            On(player, "Leech (Demon Hunter)")
                                ? LeechLifePerHit(Tune("leech_life_on_hit_healing_share"), Healing::At(player->GetLevel()),
                                                  Num("Leech (Demon Hunter)", "life_per_kill_share_pct"), LifePerKill(player))
                                : 0.0);
            changed |= SharpSync(player);
            if (changed)
                Stats::Recompute(player);
        }

        // Steady Aim: "As long as there are no enemies within {radius_yards} yards, all damage is increased by
        // {damage_bonus_pct}": checked every `steady_aim_check_seconds`, and a clear check holds the bonus for the
        // power file's duration, which outlasts the next check.
        void CheckSteadyAim(Player* player)
        {
            if (!On(player, "Steady Aim"))
                return;
            std::vector<double> distances;
            for (Unit* enemy :
                 Combat::Enemies(player, Id("Steady Aim"), player->GetPosition(), Num("Steady Aim", "radius_yards")))
                distances.push_back(player->GetExactDist(enemy));
            if (!Clear(distances, Num("Steady Aim", "radius_yards")))
                return;
            std::lock_guard<std::mutex> guard(mutex);
            steadyUntil[player->GetGUID().GetRawValue()] = Until(Now(), Tune("steady_aim_duration_seconds"));
        }

        // Brooding: the stacks of a second standing still, looked at every `brooding_check_seconds`; the Life
        // regeneration they give is one buff on the sheet.
        void StepBrooding(Player* player, double diff)
        {
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            unsigned stacks = 0;
            if (On(player, "Brooding"))
            {
                std::lock_guard<std::mutex> guard(mutex);
                Still& state = brooding[guid];
                state = BroodingStep(state, player->isMoving(), diff, unsigned(Num("Brooding", "max_stacks_count")),
                                     Num("Brooding", "duration_seconds"));
                stacks = state.stacks;
            }
            else
            {
                std::lock_guard<std::mutex> guard(mutex);
                brooding.erase(guid);
            }
            if (Hold(player, Stat::LifeRegen, Bucket::Percent, "Brooding", stacks * Num("Brooding", "life_regen_pct")))
                Stats::Recompute(player);
        }

        // Sharpshooter: "Gain {crit_chance_pct} Critical Hit Chance every second": a stack for each tick.
        void TickSharpshooter(Player* player)
        {
            if (!On(player, "Sharpshooter"))
                return;
            {
                std::lock_guard<std::mutex> guard(mutex);
                Sharp& state = sharp[player->GetGUID().GetRawValue()];
                state = SharpTick(state, Now());
            }
            if (SharpSync(player))
                Stats::Recompute(player);
        }

        // Single Out: looked at every `single_out_check_seconds`, the enemies within the power file's search radius that no other enemy is
        // within `radius_yards` of.
        void LookForSingles(Player* player)
        {
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            std::unordered_set<std::uint64_t> alone;
            if (On(player, "Single Out"))
            {
                auto const enemies = Combat::Enemies(player, Id("Single Out"), player->GetPosition(), Tune("single_out_search_yards"));
                for (Unit* enemy : enemies)
                {
                    std::vector<double> others;
                    for (Unit* other : enemies)
                        if (other != enemy)
                            others.push_back(enemy->GetExactDist(other));
                    if (Isolated(others, Num("Single Out", "radius_yards")))
                        alone.insert(enemy->GetGUID().GetRawValue());
                }
            }
            std::lock_guard<std::mutex> guard(mutex);
            singled[guid] = std::move(alone);
        }

        class Update final : public PlayerScript
        {
        public:
            Update()
                : PlayerScript("dc_demon_hunter_passives",
                               {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_MAP_CHANGED})
            {
            }

            void OnPlayerUpdate(Player* player, uint32 diff) override
            {
                if (!IsDemonHunter(player))
                    return;
                std::uint64_t const guid = player->GetGUID().GetRawValue();
                unsigned refresh = 0, checks = 0, still = 0, tick = 0, sharpTicks = 0, looks = 0;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    refresh = Due(refreshClock[guid], diff, Tune("passive_refresh_seconds") * 1000.0);
                    checks = Due(steadyClock[guid], diff, Tune("steady_aim_check_seconds") * 1000.0);
                    still = Due(broodingClock[guid], diff, Tune("brooding_check_seconds") * 1000.0);
                    tick = Due(archeryClock[guid], diff, Tune("archery_hatred_tick_seconds") * 1000.0);
                    sharpTicks = Due(sharpClock[guid], diff, Tune("sharpshooter_tick_seconds") * 1000.0);
                    looks = Due(singleClock[guid], diff, Tune("single_out_check_seconds") * 1000.0);
                }
                if (refresh)
                    Sync(player);
                if (checks)
                    CheckSteadyAim(player);
                for (unsigned i = 0; i < sharpTicks; ++i)
                    TickSharpshooter(player);
                if (looks)
                    LookForSingles(player);
                // Brooding is told how long since its last look, so a late update keeps the time.
                if (still)
                    StepBrooding(player, still * Tune("brooding_check_seconds") * 1000.0);
                // Archery: a second hand crossbow gives "{regen_per_second_resource} Hatred per Second", a tick at a
                // time.
                if (tick && On(player, "Archery") && ArcheryHeld(player).second)
                    for (unsigned i = 0; i < tick; ++i)
                        Generate(player, Classes::ClassIdOf(player), Id("Archery"),
                                 Num("Archery", "regen_per_second_resource") * Tune("archery_hatred_tick_seconds"));
            }

            void OnPlayerLogout(Player* player) override
            {
                Forget(player);
            }

            void OnPlayerMapChanged(Player* player) override
            {
                std::lock_guard<std::mutex> guard(mutex);
                steadyUntil.erase(player->GetGUID().GetRawValue());
            }

            static void Forget(Player* player)
            {
                std::lock_guard<std::mutex> guard(mutex);
                std::uint64_t const guid = player->GetGUID().GetRawValue();
                steadyUntil.erase(guid);
                steadyClock.erase(guid);
                refreshClock.erase(guid);
                broodingClock.erase(guid);
                archeryClock.erase(guid);
                brooding.erase(guid);
                sharpClock.erase(guid);
                sharp.erase(guid);
                singleClock.erase(guid);
                perfecting.erase(guid);
                singled.erase(guid);
                for (auto it = held.begin(); it != held.end();)
                    it = std::get<0>(it->first) == guid ? held.erase(it) : std::next(it);
            }
        };

        // Grenadier's giant grenade where the Demon Hunter falls: every enemy within the file's radius (15 times the grenades'
        // larger explosion) takes the passive's percent as Fire, and is thrown out by the file's knockback.
        void DropGrenade(Player* player)
        {
            std::uint32_t const blast = Shells::HelperFor(GrenadierBlast);
            if (!blast)
                return;
            double const radius = Tune("grenadier_death_radius_yards") * RadiusFactor(true, true, Tune("grenadier_radius_increase_pct"));
            for (Unit* enemy : Combat::Enemies(player, blast, player->GetPosition(), radius))
            {
                Combat::Strike(player, enemy, blast, Num("Grenadier", "damage_pct"));
                Abilities::Knockback(player, enemy, Tune("grenadier_death_knockback_yards"));
            }
        }

        // Tactical Advantage: "you gain {movement_speed_pct} movement speed for {duration_seconds} seconds".
        void Hasten(Player* player)
        {
            if (On(player, "Tactical Advantage"))
                Buffs::Stack(player, Id("Tactical Advantage"), Stat::MovementSpeed, Bucket::Uncapped,
                             Num("Tactical Advantage", "movement_speed_pct"), 1,
                             Num("Tactical Advantage", "duration_seconds"));
        }

        // Numbing Traps: "have their damage reduced by {enemy_damage_pct} for {duration_seconds} seconds".
        void Numb(Player* player, Unit* enemy)
        {
            if (On(player, "Numbing Traps"))
                EnemyEffects::Weaken(enemy, Id("Numbing Traps"), Num("Numbing Traps", "enemy_damage_pct"),
                                     Num("Numbing Traps", "duration_seconds"));
        }
    } // namespace

    void Landed(Player* player, Unit* target, std::uint32_t spellId, bool critical)
    {
        if (!player || !target || !IsDemonHunter(player))
            return;
        // Thrill of the Hunt: "Enemies hit by your Hatred spenders are Slowed by {slow_pct} for {slow_duration_seconds}
        // seconds."
        if (On(player, "Thrill of the Hunt") && SpendsHatredNow(spellId))
            Slow(player, target, Num("Thrill of the Hunt", "slow_pct"),
                 Num("Thrill of the Hunt", "slow_duration_seconds"));
        // Hot Pursuit: "Increase movement speed by {movement_speed_pct} for {duration_seconds} seconds when you hit an
        // enemy."
        if (On(player, "Hot Pursuit"))
            Buffs::Stack(player, Id("Hot Pursuit"), Stat::MovementSpeed, Bucket::Uncapped,
                         Num("Hot Pursuit", "movement_speed_pct"), 1, Num("Hot Pursuit", "duration_seconds"));
        // Sharpshooter: "This bonus is reset {duration_seconds} second after you successfully critically hit."
        if (critical && On(player, "Sharpshooter"))
        {
            std::lock_guard<std::mutex> guard(mutex);
            Sharp& state = sharp[player->GetGUID().GetRawValue()];
            state = SharpCrit(state, Now(), Tune("sharpshooter_reset_delay_seconds"));
        }
        // Numbing Traps: an enemy hit by the traps' and devices' skills.
        if (auto const* row = Shells::FindAbility(spellId); row && NumbingTrapsSkill(row->skill))
            Numb(player, target);
    }

    void Slowed(Player* player, Unit* enemy)
    {
        if (player && enemy)
            Numb(player, enemy);
    }

    void Cast(Player* player, std::uint32_t spellId)
    {
        auto const* row = Shells::FindAbility(spellId);
        if (player && row && TacticalAdvantageSkill(row->skill))
            Hasten(player);
    }

    void Backflipped(Player* player)
    {
        Hasten(player);
    }

    double Generated(Player* player, std::uint32_t spellId, double generated)
    {
        // "Your primary skills generate an additional {generated_resource} Hatred."
        return On(player, "Night Stalker")
                   ? GeneratedWith(IsPrimary(spellId), generated, Num("Night Stalker", "generated_resource"))
                   : generated;
    }

    double DurationFactor(Player* player, std::string_view skill)
    {
        return DurationFactorOf(On(player, "Custom Engineering"), skill,
                                Num("Custom Engineering", "duration_bonus_pct"));
    }

    unsigned MostStanding(Player* player, char const* kind, unsigned base)
    {
        return MostStandingOf(On(player, "Custom Engineering"), base, Num("Custom Engineering", "max_count", kind));
    }

    void GlobePicked(Player* player)
    {
        if (!On(player, "Blood Vengeance"))
            return;
        // "gain {gain_resource:hatred} Hatred and {gain_resource:discipline} Discipline when you are healed by a health
        // globe."
        std::uint32_t const id = Id("Blood Vengeance");
        Resources::Energize(player, Resources::Hatred, id, Num("Blood Vengeance", "gain_resource", "hatred"));
        Resources::Energize(player, Resources::Discipline, id, Num("Blood Vengeance", "gain_resource", "discipline"));
    }

    void Multipliers(Player* player, Unit* target, std::uint32_t spellId, DC::Combat::Factors& out)
    {
        if (!IsDemonHunter(player))
            return;
        // Steady Aim: "all damage is increased by {damage_bonus_pct}" while the check holds.
        bool steady = false;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = steadyUntil.find(player->GetGUID().GetRawValue());
            steady = found != steadyUntil.end() && Now() < found->second;
        }
        if (steady && On(player, "Steady Aim"))
            AddFactor(out, "Steady Aim", Num("Steady Aim", "damage_bonus_pct"));
        // Cull the Weak: "Increase damage against Slowed or Chilled enemies by {damage_bonus_pct}."
        if (target && On(player, "Cull the Weak"))
            if (double const pct = CullPct(target->HasAuraType(SPELL_AURA_MOD_DECREASE_SPEED),
                                           Num("Cull the Weak", "damage_bonus_pct")))
                AddFactor(out, "Cull the Weak", pct);
        // Ambush: "You deal {damage_bonus_pct} additional damage to enemies above {life_threshold_pct} health."
        if (target && On(player, "Ambush"))
            if (double const pct = AmbushPct(target->GetHealthPct(), Num("Ambush", "life_threshold_pct"), Num("Ambush", "damage_bonus_pct")))
                AddFactor(out, "Ambush", pct);
        // Grenadier: "Increase the damage of grenades by {damage_bonus_pct}."
        if (On(player, "Grenadier") && IsGrenade(spellId))
            AddFactor(out, "Grenadier", Num("Grenadier", "damage_bonus_pct"));
        // Archery: "Bow: {damage_bonus_pct} increased damage".
        if (On(player, "Archery") && ArcheryHeld(player).bow)
            AddFactor(out, "Archery", Num("Archery", "damage_bonus_pct"));
    }

    void Attack(Player* player, std::uint32_t spellId)
    {
        if (!player || !On(player, "Ballistics") || Shells::FindAbility(spellId) == nullptr)
            return;
        // Ballistics: "a {proc_chance_pct} chance to fire a homing rocket for {damage_pct} weapon damage when you attack": a rocket
        // homes on the nearest enemy within the file's search radius.
        if (!Procs(frand(0.0f, 1.0f), Num("Ballistics", "proc_chance_pct")))
            return;
        Unit* nearest = nullptr;
        for (Unit* enemy : Combat::Enemies(player, Id("Ballistics"), player->GetPosition(), Tune("ballistics_rocket_range_yards")))
            if (!nearest || player->GetExactDist(enemy) < player->GetExactDist(nearest))
                nearest = enemy;
        if (nearest)
            Combat::Strike(player, nearest, Id("Ballistics"), Num("Ballistics", "damage_pct"));
    }

    double RocketFactor(Player* player)
    {
        return RocketFactorOf(On(player, "Ballistics"), Num("Ballistics", "damage_bonus_pct"));
    }

    double GrenadierFactor(Player* player)
    {
        return GrenadierFactorOf(On(player, "Grenadier"), Num("Grenadier", "damage_bonus_pct"));
    }

    double GrenadeRadius(Player* player, std::uint32_t spellId, double radius)
    {
        auto const* row = Shells::FindAbility(spellId);
        return radius * RadiusFactor(row && On(player, "Grenadier"), row && GrenadeRadiusSkill(row->skill, row->rune), Tune("grenadier_radius_increase_pct"));
    }

    void Ground(Player* player, std::uint32_t spellId, Position const& center)
    {
        auto const* row = Shells::FindAbility(spellId);
        // Grenadier's larger explosion: the ring beyond the engine's own radius is hit as the explosion was. Cluster Grenades reaches its
        // own larger radius itself (it asks GrenadeRadius).
        if (!player || !row || std::string_view(row->skill) != "Grenade" || std::string_view(row->rune) == "Cluster Grenades" ||
            !On(player, "Grenadier"))
            return;
        double const base = Combat::TargetRadius(spellId), grown = GrenadeRadius(player, spellId, base);
        auto const enemies = Combat::Enemies(player, spellId, center, grown);
        std::vector<double> distances;
        for (Unit* enemy : enemies)
            distances.push_back(enemy->GetExactDist(&center));
        for (std::size_t index : Ring(distances, base, grown))
            Combat::Strike(player, enemies[index], spellId, Numbers::Num(spellId, "damage_pct"));
    }

    double CritBonus(Player* player, Unit* target)
    {
        if (!player || !target || !On(player, "Single Out"))
            return 0.0;
        std::lock_guard<std::mutex> guard(mutex);
        auto found = singled.find(player->GetGUID().GetRawValue());
        return found != singled.end() && found->second.count(target->GetGUID().GetRawValue()) ? Num("Single Out", "crit_chance_pct") : 0.0;
    }

    void Fatal(Player* player, std::uint32_t& damage)
    {
        if (!player || !damage)
            return;
        if (On(player, "Awareness"))
        {
            std::uint32_t const id = Id("Awareness");
            if (Saves(player->GetHealth(), damage, !player->HasSpellCooldown(id)))
            {
                // "When you receive fatal damage, you instead vanish for {duration_seconds} seconds and regenerate {heal_pct} of
                // maximum Life. This effect may occur once every {internal_cooldown_seconds} seconds."
                player->AddSpellCooldown(id, 0, std::uint32_t(Num("Awareness", "internal_cooldown_seconds") * 1000.0), true);
                damage = 0;
                double const seconds = Num("Awareness", "duration_seconds"), tick = Tune("awareness_regen_tick_seconds");
                Vanish(player, seconds);
                double const each = AwarenessPerTick(player->GetMaxHealth(), Num("Awareness", "heal_pct"), seconds, tick);
                for (unsigned step = 1; tick > 0 && step * tick <= seconds + 1e-9; ++step)
                    player->m_Events.AddEventAtOffset(
                        [player, id, each]
                        {
                            if (player->IsAlive() && player->IsInWorld())
                                Heal(player, id, each);
                        },
                        std::chrono::milliseconds(std::uint32_t(step * tick * 1000.0)));
                return;
            }
        }
        // Grenadier: "Upon death, you drop a giant grenade that explodes for {damage_pct} weapon damage as Fire": the blow that
        // kills, no save having taken it. The power file's radius grows with the grenades' and its knockback throws the enemies out.
        if (On(player, "Grenadier") && damage >= player->GetHealth())
            DropGrenade(player);
    }

    void RegisterScripts()
    {
        new Update();
    }
} // namespace DC::Combat::DemonHunter::Passive
