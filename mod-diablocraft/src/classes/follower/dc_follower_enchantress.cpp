/*
 * The Enchantress' eight skills (Eirena): Charm and Temporal Pulse, Amplification and Prophetic Harmony, Powered Shield
 * and Erosion, Focused Mind and Fate's Lapse, two to a tier. The picks, tiers, numbers, cooldowns, holds and the stat
 * the framework keeps on the player are the framework's (dc_follower_skills.cpp); her intelligence is the number the
 * skills scale with. The hits are dealt as the player's under stock arcane spells that give the log its name.
 */

#include "dc_follower_internal.h"
#include "../../combat/dc_charm_effect.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_enemy_effects.h"
#include "../../stats/dc_stats.h"
#include "Creature.h"
#include "Player.h"
#include "Unit.h"

#include <array>
#include <mutex>
#include <unordered_map>

namespace DC::Classes::Follower::Enchantress
{
    namespace
    {
        // The stock spells her hits are dealt under (and her charm and her enemies are looked for under): "Mind
        // Control", "Arcane Missiles", "Arcane Explosion" and "Frost Nova".
        constexpr std::uint32_t CharmSpell = 605;
        constexpr std::uint32_t PulseSpell = 5143;
        constexpr std::uint32_t ErosionSpell = 1449;
        constexpr std::uint32_t LapseSpell = 122;

        // The keys of what the skills hold on the player's sheet.
        constexpr std::uint64_t HarmonyKey = 0xF3000001;
        constexpr std::uint64_t ArmorKey = 0xF3000002;
        constexpr std::uint64_t FocusKey = 0xF3000003;
        constexpr std::uint64_t AmplificationKey = 0xF3000004;

        struct Mine
        {
            double rangedPct = 0;  // Powered Shield: the share a ranged blow loses
            double sheetClock = 0; // ms toward the next look at the sheet (Amplification)
            bool pool = false;     // Erosion: where, how wide, how long, how it ticks
            std::uint32_t poolMap = 0;
            std::uint32_t poolInstance = 0;
            float poolX = 0;
            float poolY = 0;
            float poolZ = 0;
            double poolRadius = 0;
            double poolSeconds = 0;
            double poolClock = 0;
            std::uint64_t poolUntil = 0;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, Mine> mine; // by the player's guid

        std::uint64_t Key(Player const* player)
        {
            return player->GetGUID().GetRawValue();
        }

        // Amplification: "Increases your static elemental damage bonuses": the highest of them rises by a share of
        // itself. What this skill itself put on the sheet is taken off before the highest is looked for.
        void Amplify(Ctx const& c)
        {
            double want = 0;
            Element element = Element::Physical;
            if (On(c, "amplification"))
                if (auto sheet = Stats::Get(Key(c.player)))
                {
                    Element held = Element::Physical;
                    double const had = Standing(c.player, AmplificationKey, &held);
                    std::array<double, ElementCount> bonuses = sheet->elementalDamage;
                    if (had > 0)
                        bonuses[static_cast<unsigned>(held)] -= had;
                    std::size_t const top = Highest(bonuses.data(), bonuses.size());
                    element = static_cast<Element>(top);
                    want = Amplified(bonuses[top], Num(c, "amplification", "bonus_pct"));
                }
            Stand(c.player, AmplificationKey, Stat::ElementalDamage, Bucket::Flat, want, element);
        }

        // Erosion: the pool's ticks, each a share of the pool's damage on every enemy in it, and the weakness the pool
        // leaves.
        void Pool(Ctx const& c, std::uint32_t diffMs)
        {
            Mine own;
            unsigned ticks = 0;
            double const tick = Raw(c.follower, "erosion", "tick_seconds");
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto found = mine.find(Key(c.player));
                if (found == mine.end() || !found->second.pool)
                    return;
                Mine& state = found->second;
                // A pool ends with its time, and when the player is on another map or another run of it.
                if (!Holds(Now(), state.poolUntil) ||
                    !SamePlace(state.poolMap, state.poolInstance, c.player->GetMapId(), c.player->GetInstanceId()))
                {
                    state.pool = false;
                    return;
                }
                ticks = Pulses(state.poolClock, diffMs, tick * 1000.0);
                own = state;
            }
            if (!ticks)
                return;
            Position const center(own.poolX, own.poolY, own.poolZ);
            double const pct = PerTick(Raw(c.follower, "erosion", "damage_pct"), own.poolSeconds, tick),
                         weak = Raw(c.follower, "erosion", "vulnerability_pct");
            for (Unit* enemy : Combat::Enemies(c.player, ErosionSpell, center, own.poolRadius))
                for (unsigned i = 0; i < ticks; ++i)
                {
                    Strike(c, enemy, ErosionSpell, pct, SPELL_SCHOOL_MASK_ARCANE);
                    Combat::EnemyEffects::Taken(enemy, ErosionSpell, weak, tick + 0.75);
                }
        }
    } // namespace

    void Tick(Ctx& c, Unit* target, std::uint32_t diffMs)
    {
        Player* player = c.player;
        Creature* her = c.companion;
        // The standing skills: Prophetic Harmony, Powered Shield and Focused Mind (within the aura), and Amplification
        // once a second.
        Stand(player, HarmonyKey, Stat::CooldownReduction, Bucket::Flat,
              On(c, "prophetic-harmony") ? Num(c, "prophetic-harmony", "cooldown_reduction_pct") : 0.0);
        bool const shield = On(c, "powered-shield");
        Stand(player, ArmorKey, Stat::Armor, Bucket::Percent,
              shield ? Raw(c.follower, "powered-shield", "armor_pct") : 0.0);
        bool const focused = On(c, "focused-mind") &&
                             InRange(her->GetDistance(player), Raw(c.follower, "focused-mind", "aura_radius_yards"));
        Stand(player, FocusKey, Stat::AttackSpeed, Bucket::Flat,
              focused ? Num(c, "focused-mind", "attack_speed_pct") : 0.0);
        bool look = false;
        {
            std::lock_guard<std::mutex> guard(mutex);
            Mine& own = mine[Key(player)];
            own.rangedPct = shield ? Raw(c.follower, "powered-shield", "ranged_reduction_pct") : 0.0;
            look = Pulses(own.sheetClock, diffMs, 1000.0) > 0;
        }
        if (look)
            Amplify(c);
        Pool(c, diffMs);
        if (!target || !target->IsAlive())
            return;
        // Charm: an enemy fights for the player for a while.
        if (On(c, "charm") && Ready(c, "charm") &&
            InRange(her->GetDistance(target), Raw(c.follower, "charm", "cast_range_yards")) &&
            Combat::CharmEffect::Apply(player, target, CharmSpell, Raw(c.follower, "charm", "duration_seconds")))
            Spend(c, "charm");
        // Temporal Pulse: an orb that hurts and slows the enemies round the target.
        if (On(c, "temporal-pulse") && Ready(c, "temporal-pulse") &&
            InRange(her->GetDistance(target), Raw(c.follower, "temporal-pulse", "cast_range_yards")))
        {
            double const seconds = Num(c, "temporal-pulse", "slow_seconds");
            for (Unit* enemy : Combat::Enemies(player, PulseSpell, target->GetPosition(),
                                               Raw(c.follower, "temporal-pulse", "radius_yards")))
            {
                Strike(c, enemy, PulseSpell, Raw(c.follower, "temporal-pulse", "damage_pct"), SPELL_SCHOOL_MASK_ARCANE);
                Slow(her, enemy, Raw(c.follower, "temporal-pulse", "slow_pct"), seconds);
            }
            Spend(c, "temporal-pulse");
        }
        // Erosion: a pool of energy where she aims.
        if (On(c, "erosion") && Ready(c, "erosion") &&
            InRange(her->GetDistance(target), Raw(c.follower, "erosion", "cast_range_yards")))
        {
            {
                std::lock_guard<std::mutex> guard(mutex);
                Mine& own = mine[Key(player)];
                own.pool = true;
                own.poolMap = target->GetMapId();
                own.poolInstance = target->GetInstanceId();
                own.poolX = target->GetPositionX();
                own.poolY = target->GetPositionY();
                own.poolZ = target->GetPositionZ();
                own.poolRadius = Raw(c.follower, "erosion", "radius_yards");
                own.poolSeconds = Num(c, "erosion", "seconds");
                own.poolClock = 0;
                own.poolUntil = Now() + std::uint64_t(own.poolSeconds * 1000.0);
            }
            Spend(c, "erosion");
        }
    }

    // Fate's Lapse: "When you take fatal damage, the Enchantress empowers you to move through time, slowing enemies'
    // movement and attack speed, to avoid death": the blow is nothing and the enemies about the player slow.
    bool Fatal(Ctx& c, std::uint32_t& damage)
    {
        if (!On(c, "fates-lapse") || !Ready(c, "fates-lapse") ||
            !DC::Classes::Follower::Fatal(c.player->GetHealth(), damage))
            return false;
        damage = 0;
        double const pct = Raw(c.follower, "fates-lapse", "slow_pct"), seconds = Num(c, "fates-lapse", "slow_seconds");
        for (Unit* enemy : Combat::Enemies(c.player, LapseSpell, c.player->GetPosition(),
                                           Raw(c.follower, "fates-lapse", "radius_yards")))
        {
            Slow(c.companion, enemy, pct, seconds);
            Weary(c.companion, enemy, pct, seconds);
        }
        Spend(c, "fates-lapse");
        return true;
    }

    // Powered Shield: "slows melee attackers" of the player and of her.
    void Struck(Ctx& c, Unit* attacker)
    {
        if (On(c, "powered-shield"))
            Slow(c.companion, attacker, Raw(c.follower, "powered-shield", "slow_pct"),
                 Num(c, "powered-shield", "slow_seconds"));
    }

    double Taken(Player const* player, bool melee)
    {
        std::lock_guard<std::mutex> guard(mutex);
        auto found = mine.find(Key(player));
        return found == mine.end() ? 1.0 : RangedFactor(found->second.rangedPct, melee);
    }

    void Away(Player* player)
    {
        std::lock_guard<std::mutex> guard(mutex);
        mine.erase(Key(player));
    }
} // namespace DC::Classes::Follower::Enchantress
