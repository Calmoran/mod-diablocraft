/*
 * The Scoundrel's eight skills (Lyndon): Crippling Shot and Powered Shot, Hysteria and Anatomy, Piercing Shot and
 * Multishot, Vanish and Night's Veil, two to a tier. The picks, tiers, numbers, cooldowns, critical hits and holds are
 * the framework's (dc_follower_skills.cpp); the Scoundrel's dexterity is the number the skills scale with. The shots
 * need the bow or crossbow he wears; the hits are dealt as the player's under stock hunter spells that give the log its
 * name.
 */

#include "dc_follower_internal.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_damage_boost.h"
#include "../../combat/dc_enemy_effects.h"
#include "../../stats/dc_stats.h"
#include "Creature.h"
#include "Player.h"
#include "Unit.h"

#include <algorithm>
#include <cmath>
#include <mutex>
#include <unordered_map>
#include <vector>

namespace DC::Classes::Follower::Scoundrel
{
    namespace
    {
        // The stock spells the Scoundrel's hits are dealt under: "Concussive Shot", "Arcane Shot", "Aimed Shot" and
        // "Multi-Shot".
        constexpr std::uint32_t CripplingSpell = 5116;
        constexpr std::uint32_t PoweredSpell = 3044;
        constexpr std::uint32_t PiercingSpell = 19434;
        constexpr std::uint32_t MultishotSpell = 2643;

        // The keys of what the skills put on the player: Hysteria's damage boost, and Anatomy's critical hit chance on
        // the sheet.
        constexpr std::uint32_t HysteriaKey = 0xF2000001;
        constexpr std::uint64_t AnatomyId = 0xF2000002;

        struct Mine
        {
            double anatomy = 0;              // the critical hit chance Anatomy has put on the player's sheet
            std::uint64_t hysteriaUntil = 0; // game time
            double hysteriaPct = 0;
            std::uint32_t veilMap = 0; // Night's Veil: where (map and instance), how wide, until when
            std::uint32_t veilInstance = 0;
            float veilX = 0;
            float veilY = 0;
            double veilRadius = 0;
            std::uint64_t veilUntil = 0;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, Mine> mine; // by the player's guid

        std::uint64_t Key(Player const* player)
        {
            return player->GetGUID().GetRawValue();
        }

        // Anatomy: the critical hit chance on the player's sheet is `want` now (none takes it off).
        void SetAnatomy(Player* player, double want)
        {
            {
                std::lock_guard<std::mutex> guard(mutex);
                Mine& own = mine[Key(player)];
                if (std::fabs(own.anatomy - want) < 1e-9)
                    return;
                own.anatomy = want;
            }
            Stats::RemoveContribution(Key(player), Source::Passives, Stat::CritChance, AnatomyId);
            if (want > 0)
                Stats::AddContribution(Key(player),
                                       {Source::Passives, Stat::CritChance, AnatomyId, want, Bucket::Flat});
            Stats::Recompute(player);
        }

        bool NearEnough(Ctx const& c, char const* skill, char const* token)
        {
            return InRange(c.companion->GetDistance(c.player), Raw(c.follower, skill, token));
        }

        // A shot that needs the bow or crossbow he wears, at a target within reach, with its cooldown ready.
        bool CanShoot(Ctx const& c, Unit* target, char const* skill)
        {
            return c.stats.swingMax > 0 && On(c, skill) && Ready(c, skill) &&
                   InRange(c.companion->GetDistance(target), Raw(c.follower, skill, "cast_range_yards"));
        }

        // Multishot: the bolts go to the enemies near the target in turn, the target first.
        void Volley(Ctx const& c, Unit* target)
        {
            std::vector<Unit*> enemies = Combat::Enemies(c.player, MultishotSpell, c.companion->GetPosition(),
                                                         Raw(c.follower, "multishot", "cast_range_yards"));
            enemies.erase(std::remove(enemies.begin(), enemies.end(), target), enemies.end());
            std::sort(enemies.begin(), enemies.end(),
                      [target](Unit* a, Unit* b) { return target->GetExactDist(a) < target->GetExactDist(b); });
            enemies.insert(enemies.begin(), target);
            unsigned const bolts = 1 + unsigned(Raw(c.follower, "multishot", "extra_bolts"));
            for (unsigned bolt = 0; bolt < bolts; ++bolt)
                Strike(c, enemies[BoltTarget(bolt, enemies.size())], MultishotSpell,
                       Raw(c.follower, "multishot", "damage_pct"), SPELL_SCHOOL_MASK_NORMAL);
        }

        // Piercing Shot: along the line from the Scoundrel through the target, as far as his reach.
        void Pierce(Ctx const& c, Unit* target)
        {
            Position const from = c.companion->GetPosition();
            double const reach = Raw(c.follower, "piercing-shot", "cast_range_yards"),
                         width = Raw(c.follower, "piercing-shot", "line_width_yards");
            double dx = target->GetPositionX() - from.GetPositionX(), dy = target->GetPositionY() - from.GetPositionY();
            double const length = std::sqrt(dx * dx + dy * dy);
            if (length > 0)
            {
                dx /= length;
                dy /= length;
            }
            double const toX = from.GetPositionX() + dx * reach, toY = from.GetPositionY() + dy * reach;
            double const pct = Raw(c.follower, "piercing-shot", "vulnerability_pct"),
                         seconds = Num(c, "piercing-shot", "vulnerability_seconds");
            for (Unit* enemy : Combat::Enemies(c.player, PiercingSpell, from, reach))
                if (enemy == target || OnLine(from.GetPositionX(), from.GetPositionY(), toX, toY, enemy->GetPositionX(),
                                              enemy->GetPositionY(), width / 2))
                {
                    Strike(c, enemy, PiercingSpell, Raw(c.follower, "piercing-shot", "damage_pct"),
                           SPELL_SCHOOL_MASK_NORMAL);
                    Combat::EnemyEffects::Taken(enemy, PiercingSpell, pct, seconds);
                }
        }
    } // namespace

    void Tick(Ctx& c, Unit* target, std::uint32_t)
    {
        Player* player = c.player;
        Creature* scoundrel = c.companion;
        // Anatomy: "Increases Critical Hit Chance for you and the Scoundrel" within the aura.
        SetAnatomy(player, On(c, "anatomy") && NearEnough(c, "anatomy", "aura_radius_yards")
                               ? Num(c, "anatomy", "crit_chance_pct")
                               : 0.0);
        if (!target || !target->IsAlive())
            return;
        // The special attacks: each on its own cooldown.
        bool special = false;
        if (CanShoot(c, target, "crippling-shot"))
        {
            Strike(c, target, CripplingSpell, Raw(c.follower, "crippling-shot", "damage_pct"),
                   SPELL_SCHOOL_MASK_NORMAL);
            Slow(scoundrel, target, Raw(c.follower, "crippling-shot", "slow_pct"),
                 Num(c, "crippling-shot", "slow_seconds"));
            Spend(c, "crippling-shot");
            special = true;
        }
        if (CanShoot(c, target, "powered-shot"))
        {
            double const seconds = Num(c, "powered-shot", "stun_seconds");
            for (Unit* enemy : Combat::Enemies(player, PoweredSpell, target->GetPosition(),
                                               Raw(c.follower, "powered-shot", "radius_yards")))
            {
                Strike(c, enemy, PoweredSpell, Raw(c.follower, "powered-shot", "damage_pct"), SPELL_SCHOOL_MASK_ARCANE);
                if (Rolls(frand(0.0f, 1.0f), Raw(c.follower, "powered-shot", "stun_chance_pct")))
                    Stun(scoundrel, enemy, seconds);
            }
            Spend(c, "powered-shot");
            special = true;
        }
        if (CanShoot(c, target, "piercing-shot"))
        {
            Pierce(c, target);
            Spend(c, "piercing-shot");
            special = true;
        }
        // Multishot: the active volley, and the chance of the volley after a special attack.
        if (CanShoot(c, target, "multishot"))
        {
            Volley(c, target);
            Spend(c, "multishot");
        }
        else if (special && c.stats.swingMax > 0 && On(c, "multishot") &&
                 Rolls(frand(0.0f, 1.0f), Num(c, "multishot", "passive_chance_pct")))
            Volley(c, target);
        // Night's Veil: a cloud where he shoots; every attack on an enemy inside it is a critical hit.
        if (On(c, "nights-veil") && Ready(c, "nights-veil") &&
            InRange(scoundrel->GetDistance(target), Raw(c.follower, "nights-veil", "cast_range_yards")))
        {
            {
                std::lock_guard<std::mutex> guard(mutex);
                Mine& own = mine[Key(player)];
                own.veilMap = target->GetMapId();
                own.veilInstance = target->GetInstanceId();
                own.veilX = target->GetPositionX();
                own.veilY = target->GetPositionY();
                own.veilRadius = Raw(c.follower, "nights-veil", "radius_yards");
                own.veilUntil = Now() + std::uint64_t(Num(c, "nights-veil", "seconds") * 1000.0);
            }
            Spend(c, "nights-veil");
        }
    }

    // Vanish: "When you take fatal damage, the Scoundrel conceals you from enemies, allowing you to escape your death."
    bool Fatal(Ctx& c, std::uint32_t& damage)
    {
        if (!On(c, "vanish") || !Ready(c, "vanish") || !DC::Classes::Follower::Fatal(c.player->GetHealth(), damage))
            return false;
        damage = 0;
        Conceal(c.player, Num(c, "vanish", "conceal_seconds"));
        Spend(c, "vanish");
        return true;
    }

    // Hysteria: "Whenever you or the Scoundrel land a Critical Hit, you both will go into hysterics, increasing all
    // damage done".
    void Crit(Ctx const& c)
    {
        if (!On(c, "hysteria"))
            return;
        double const pct = Raw(c.follower, "hysteria", "damage_bonus_pct"),
                     seconds = Num(c, "hysteria", "bonus_seconds");
        {
            std::lock_guard<std::mutex> guard(mutex);
            Mine& own = mine[Key(c.player)];
            own.hysteriaUntil = Now() + std::uint64_t(seconds * 1000.0);
            own.hysteriaPct = pct;
        }
        Combat::DamageBoost::Hold(c.player, HysteriaKey, pct, seconds);
    }

    double DamageFactor(Ctx const& c)
    {
        std::lock_guard<std::mutex> guard(mutex);
        auto found = mine.find(Key(c.player));
        return found != mine.end() && Holds(Now(), found->second.hysteriaUntil) ? MoreDamage(found->second.hysteriaPct)
                                                                                : 1.0;
    }

    double CritBonus(Ctx const& c, Unit* target)
    {
        double const anatomy = On(c, "anatomy") && NearEnough(c, "anatomy", "aura_radius_yards")
                                   ? Num(c, "anatomy", "crit_chance_pct")
                                   : 0.0;
        return anatomy + CloudBonus(c.player, target);
    }

    double CloudBonus(Player const* player, Unit const* target)
    {
        if (!player || !target)
            return 0.0;
        std::lock_guard<std::mutex> guard(mutex);
        auto found = mine.find(Key(player));
        if (found == mine.end() || !Holds(Now(), found->second.veilUntil) ||
            found->second.veilMap != target->GetMapId() || found->second.veilInstance != target->GetInstanceId())
            return 0.0;
        double const dx = target->GetPositionX() - found->second.veilX,
                     dy = target->GetPositionY() - found->second.veilY;
        return InRange(std::sqrt(dx * dx + dy * dy), found->second.veilRadius) ? 100.0 : 0.0;
    }

    void Away(Player* player)
    {
        double anatomy = 0;
        bool boosted = false;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = mine.find(Key(player));
            if (found == mine.end())
                return;
            anatomy = found->second.anatomy;
            boosted = found->second.hysteriaPct > 0;
            mine.erase(found);
        }
        if (boosted)
            Combat::DamageBoost::Hold(player, HysteriaKey, 0, 0);
        if (anatomy > 0)
        {
            Stats::RemoveContribution(Key(player), Source::Passives, Stat::CritChance, AnatomyId);
            Stats::Recompute(player);
        }
    }
} // namespace DC::Classes::Follower::Scoundrel
