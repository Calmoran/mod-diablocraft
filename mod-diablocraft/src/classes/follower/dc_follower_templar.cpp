/*
 * The Templar's eight skills (Kormac): Heal and Intervene, Loyalty and Intimidate, Charge and Onslaught, Inspire and
 * Guardian, two to a tier. The picks, tiers, numbers and cooldowns are the framework's (dc_follower_skills.cpp); the
 * Templar's strength is the number the skills scale with. The hits and heals are dealt as the player's under stock
 * spells that give the log its name.
 */

#include "dc_follower_internal.h"
#include "../dc_classes.h"
#include "../dc_resources.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_enemy_effects.h"
#include "../../combat/dc_healing_table.h"
#include "../../combat/dc_movement_effects.h"
#include "../../stats/dc_resource_pulse.h"
#include "Creature.h"
#include "Player.h"
#include "Unit.h"

#include <mutex>
#include <unordered_map>

namespace DC::Classes::Follower::Templar
{
    namespace
    {
        // The stock spells the Templar's hits and heals are dealt under: "Charge", "Slam", "Greater Heal",
        // "Rejuvenation" and "Challenging Shout" (the spell the taunt's targets are looked for under).
        constexpr std::uint32_t ChargeSpell = 100;
        constexpr std::uint32_t OnslaughtSpell = 1464;
        constexpr std::uint32_t HealSpell = 2060;
        constexpr std::uint32_t RegenerationSpell = 774;
        constexpr std::uint32_t TauntSpell = 1161;

        constexpr Resources::Resource const& Wrath = *Resources::Find("Crusader", "wrath");
        constexpr Resources::Resource const& Essence = *Resources::Find("Necromancer", "essence");

        struct Clocks
        {
            double loyalty = 0;
            double inspire = 0;
        };
        // Inspire's "N% generated" while the Templar stands: Fury, Spirit and Essence, by the player's guid.
        struct Generated
        {
            double fury = 0;
            double spirit = 0;
            double essence = 0;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, Clocks> clocks; // by the player's guid
        std::unordered_map<std::uint64_t, Generated> generated;

        double Table(Ctx const& c)
        {
            return Combat::Healing::At(c.level);
        }

        // Inspire: the resource a player's class has, paid a second at a time while the Templar stands beside them.
        void Inspire(Ctx const& c, unsigned pulses)
        {
            struct Gain
            {
                Resources::Resource const& resource;
                char const* token;
            };
            Gain const gains[] = {{Resources::Mana, "mana_per_second"},
                                  {Resources::Hatred, "hatred_per_second"},
                                  {Wrath, "wrath_per_second"},
                                  {Resources::ArcanePower, "arcane_power_per_second"}};
            for (Gain const& gain : gains)
                if (ClassIdOf(c.player) == gain.resource.classId && Resources::Displayed(c.player, gain.resource))
                    Resources::Flow(c.player, gain.resource, Raw(c.follower, "inspire", gain.token) * pulses,
                                    1000 * pulses);
        }

        // Inspire: "Fury: 10% generated", "Spirit: 10% generated", "Essence: 10% generated". The percents stand while the pick is on and the Templar is
        // out; Generation hands them to the resource layer (Resources::Generated), which scales what the player's skills generate.
        void Generating(Ctx const& c)
        {
            std::uint64_t const guid = c.player->GetGUID().GetRawValue();
            if (!On(c, "inspire"))
            {
                std::lock_guard<std::mutex> guard(mutex);
                generated.erase(guid);
                return;
            }
            Generated const now{Raw(c.follower, "inspire", "fury_generated_pct"), Raw(c.follower, "inspire", "spirit_generated_pct"),
                                Raw(c.follower, "inspire", "essence_generated_pct")};
            std::lock_guard<std::mutex> guard(mutex);
            generated[guid] = now;
        }
    } // namespace

    double Generation(Player const* player, Resources::Resource const& resource)
    {
        std::lock_guard<std::mutex> guard(mutex);
        auto found = generated.find(player->GetGUID().GetRawValue());
        if (found == generated.end())
            return 1.0;
        if (&resource == &Resources::Fury)
            return GeneratedFactor(found->second.fury);
        if (&resource == &Resources::Spirit)
            return GeneratedFactor(found->second.spirit);
        if (&resource == &Essence)
            return GeneratedFactor(found->second.essence);
        return 1.0;
    }

    void Away(Player* player)
    {
        std::lock_guard<std::mutex> guard(mutex);
        generated.erase(player->GetGUID().GetRawValue());
    }

    void Tick(Ctx& c, Unit* target, std::uint32_t diffMs)
    {
        Player* player = c.player;
        Creature* templar = c.companion;
        unsigned loyal = 0, inspired = 0;
        {
            std::lock_guard<std::mutex> guard(mutex);
            Clocks& clock = clocks[player->GetGUID().GetRawValue()];
            loyal = Pulses(clock.loyalty, diffMs, 1000.0);
            inspired = Pulses(clock.inspire, diffMs, 1000.0);
        }
        // Heal: "Heals you and the Templar" when either is hurt.
        if (On(c, "heal") && Ready(c, "heal"))
        {
            double const below = Raw(c.follower, "heal", "life_below_pct");
            if (Below(player->GetHealth(), player->GetMaxHealth(), below) ||
                Below(templar->GetHealth(), templar->GetMaxHealth(), below))
            {
                double const amount = TableHeal(Raw(c.follower, "heal", "heal_table_share"), Table(c));
                Heal(player, player, HealSpell, amount);
                Heal(player, templar, HealSpell, amount);
                Spend(c, "heal");
            }
        }
        // Loyalty: "Regenerates Life per second for you and the Templar" within the aura.
        if (loyal && On(c, "loyalty") &&
            InRange(templar->GetDistance(player), Raw(c.follower, "loyalty", "aura_radius_yards")))
        {
            double const amount =
                TableHeal(Raw(c.follower, "loyalty", "heal_table_share_per_second"), Table(c)) * loyal;
            Heal(player, player, RegenerationSpell, amount);
            Heal(player, templar, RegenerationSpell, amount);
        }
        Generating(c);
        if (inspired && On(c, "inspire"))
            Inspire(c, inspired);
        if (!target || !target->IsAlive())
            return;
        // Charge: the Templar rushes the target, hits it and stuns the enemies round it.
        if (On(c, "charge") && Ready(c, "charge") &&
            InRange(templar->GetDistance(target), Raw(c.follower, "charge", "cast_range_yards")))
        {
            templar->GetMotionMaster()->MoveCharge(target->GetPositionX(), target->GetPositionY(),
                                                   target->GetPositionZ());
            Strike(c, target, ChargeSpell, Raw(c.follower, "charge", "damage_pct"), SPELL_SCHOOL_MASK_NORMAL);
            double const seconds = Num(c, "charge", "stun_seconds");
            for (Unit* enemy : Combat::Enemies(player, ChargeSpell, target->GetPosition(),
                                               Raw(c.follower, "charge", "stun_radius_yards")))
                Stun(templar, enemy, seconds);
            Spend(c, "charge");
        }
        // Onslaught: a massive blow; the target and the enemies near it take more damage for a while.
        if (On(c, "onslaught") && Ready(c, "onslaught") &&
            InRange(templar->GetDistance(target), Raw(c.follower, "onslaught", "cast_range_yards")))
        {
            Strike(c, target, OnslaughtSpell, Raw(c.follower, "onslaught", "damage_pct"), SPELL_SCHOOL_MASK_NORMAL);
            double const pct = Raw(c.follower, "onslaught", "vulnerability_pct"),
                         seconds = Num(c, "onslaught", "vulnerability_seconds");
            for (Unit* enemy : Combat::Enemies(player, OnslaughtSpell, target->GetPosition(),
                                               Raw(c.follower, "onslaught", "radius_yards")))
                Combat::EnemyEffects::Taken(enemy, OnslaughtSpell, pct, seconds);
            Spend(c, "onslaught");
        }
    }

    // Intervene: "Taunt enemies within 10 yards of you when you are hit": the Templar draws them.
    void Hurt(Ctx& c, Unit* attacker)
    {
        if (!c.player->IsValidAttackTarget(attacker) || !On(c, "intervene") || !Ready(c, "intervene"))
            return;
        double const seconds = Num(c, "intervene", "taunt_seconds");
        for (Unit* enemy : Combat::Enemies(c.player, TauntSpell, c.player->GetPosition(),
                                           Raw(c.follower, "intervene", "radius_yards")))
            Taunt(c.companion, enemy, seconds);
        Spend(c, "intervene");
    }

    // Intimidate: "Enemies that hit or are hit by the Templar are slowed".
    void Fought(Ctx& c, Unit* enemy)
    {
        if (On(c, "intimidate"))
            Slow(c.companion, enemy, Raw(c.follower, "intimidate", "slow_pct"), Num(c, "intimidate", "slow_seconds"));
    }

    // Guardian: "When you take fatal damage, the Templar rushes to your aid, knocking back enemies, healing you and
    // shielding you from all damage": the blow is nothing, the shield holds the blows after it.
    bool Fatal(Ctx& c, std::uint32_t& damage)
    {
        if (!On(c, "guardian") || !Ready(c, "guardian") || !DC::Classes::Follower::Fatal(c.player->GetHealth(), damage))
            return false;
        damage = 0;
        for (Unit* enemy : Combat::Enemies(c.player, ChargeSpell, c.player->GetPosition(),
                                           Raw(c.follower, "guardian", "knockback_yards")))
            Combat::Abilities::Knockback(c.player, enemy, Raw(c.follower, "guardian", "knockback_push_yards"));
        Heal(c.player, c.player, HealSpell, LifeHeal(c.player->GetMaxHealth(), Num(c, "guardian", "heal_life_pct")));
        Shield(c.player, Now() + std::uint64_t(Raw(c.follower, "guardian", "shield_seconds") * 1000.0));
        Spend(c, "guardian");
        return true;
    }
} // namespace DC::Classes::Follower::Templar
