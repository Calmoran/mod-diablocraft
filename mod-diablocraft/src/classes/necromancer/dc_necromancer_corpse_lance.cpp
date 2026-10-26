/*
 * Corpse Lance and its five runes. The engine sends the lance at the targeted enemy and hits it for the skill's weapon
 * damage; here the lance takes a corpse (from near the target, else from near the Necromancer), and the runes add:
 * Ricochet a second lance at a nearby enemy, Brittle Touch a chance to be crit on the enemy hit, Blood Lance an
 * additional lance for Life, Visceral Impact a stun, Shredding Splinters a stacking slow and weakness.
 */

#include "dc_necromancer_corpse_lance.h"
#include "dc_necromancer_buffs.h"
#include "dc_necromancer_common.h"
#include "dc_necromancer_corpse_lance_math.h"
#include "../../combat/dc_corpses.h"
#include "../../combat/dc_enemy_effects.h"
#include "../../combat/dc_item_powers.h"

#include "GameTime.h"

#include <algorithm>
#include <mutex>
#include <unordered_map>
#include <utility>

namespace DC::Combat::Necromancer::CorpseLance
{
    namespace
    {
        constexpr std::string_view Skill = "Corpse Lance";
        // The lances a press takes corpses for: one.
        constexpr std::size_t CorpsesPerLance = 1;

        double Tune(char const* name)
        {
            return DC::Tunables::Get("necromancer", name);
        }

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        float NearCaster()
        {
            return float(Tune("corpse_lance_reach_near_caster_yards"));
        }

        float NearTarget()
        {
            return float(Tune("corpse_lance_reach_near_target_yards"));
        }

        using Key = std::pair<std::uint64_t, std::uint64_t>;
        struct KeyHash
        {
            std::size_t operator()(Key const& key) const
            {
                return std::hash<std::uint64_t>()(key.first) ^ (std::hash<std::uint64_t>()(key.second) << 1);
            }
        };

        // The enemies Brittle Touch marked (the crit chance and the end), and Shredding Splinters' stacks on each.
        struct Mark
        {
            double pct = 0; // the crit chance of one stack
            Buffs::Held held;
        };
        std::mutex mutex;
        std::unordered_map<Key, Mark, KeyHash> brittle;
        std::unordered_map<Key, Buffs::Held, KeyHash> splinters;

        Key KeyOf(Player* player, Unit* enemy)
        {
            return {player->GetGUID().GetRawValue(), enemy->GetGUID().GetRawValue()};
        }

        // A ricochet's own lance does not ricochet.
        bool ricocheting = false;
    } // namespace

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        if (!RowOf(spellId, Skill))
            return std::nullopt;
        return KeepsTheSkillsHit(RuneAt(spellId)) ? Numbers::Get(BaseId(Skill), "damage_pct") : std::nullopt;
    }

    SpellCastResult CanCast(Player* player, std::uint32_t spellId, Unit* target)
    {
        if (!player || !RowOf(spellId, Skill))
            return SPELL_CAST_OK;
        std::size_t const nearTarget = target ? Corpses::Count(player, target->GetPosition(), NearTarget()) : 0;
        return CorpseInReach(Corpses::Count(player, player->GetPosition(), NearCaster()), nearTarget)
                   ? SPELL_CAST_OK
                   : SPELL_FAILED_NO_VALID_TARGETS;
    }

    void Casting(Player* player, std::uint32_t spellId)
    {
        // "Spend 2% of your total health to launch an additional lance."
        if (player && RuneAt(spellId) == Rune::BloodLance)
            SpendLife(player, Tune("blood_lance_life_cost_pct"));
    }

    bool Impact(Player* player, Unit* target, std::uint32_t spellId, unsigned index)
    {
        if (!player || !target || !RowOf(spellId, Skill) || index != 0)
            return false;
        // The lance flies from a corpse: from near the target when one lies there, else from near the Necromancer.
        bool const fromTarget = TakeNearTheTarget(Corpses::Count(player, target->GetPosition(), NearTarget()));
        auto const taken = fromTarget ? Corpses::Consume(player, target->GetPosition(), NearTarget(), CorpsesPerLance)
                                      : Corpses::Consume(player, player->GetPosition(), NearCaster(), CorpsesPerLance);
        return taken.empty();
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId)
    {
        if (!player || !target || !RowOf(spellId, Skill))
            return;
        switch (RuneAt(spellId))
        {
            case Rune::Ricochet:
            {
                // "has a {proc_chance_pct} chance to ricochet to one additional target."
                double const reach = Tune("corpse_lance_ricochet_yards");
                if (ricocheting || !Ricochets(frand(0.0f, 100.0f), Numbers::Num(spellId, "proc_chance_pct"), reach))
                    break;
                Unit* next = nullptr;
                for (Unit* enemy : Combat::Enemies(player, spellId, target->GetPosition(), reach))
                    if (enemy != target && enemy->IsAlive() &&
                        (!next || target->GetExactDist(enemy) < target->GetExactDist(next)))
                        next = enemy;
                if (next)
                {
                    ricocheting = true;
                    Combat::Strike(player, next, spellId, Numbers::Num(BaseId(Skill), "damage_pct"));
                    ricocheting = false;
                }
                break;
            }
            case Rune::BrittleTouch:
            {
                // "Enemies become brittle increasing their chance to be crit by {crit_taken_pct} for {duration_seconds}
                // seconds each time they are hit": a stack for each hit, the time starting over.
                std::lock_guard<std::mutex> guard(mutex);
                Mark& mark = brittle[KeyOf(player, target)];
                mark.pct = Numbers::Num(spellId, "crit_taken_pct");
                Buffs::Add(mark.held, Now(), std::uint64_t(Numbers::Num(spellId, "duration_seconds") * 1000.0),
                           unsigned(Tune("brittle_touch_max_stacks")));
                break;
            }
            case Rune::BloodLance:
                // "an additional lance from yourself towards the target that deals {damage_pct} weapon damage."
                if (!ricocheting)
                {
                    ricocheting = true;
                    Combat::Strike(player, target, spellId, Numbers::Num(spellId, "damage_pct"));
                    ricocheting = false;
                }
                break;
            case Rune::VisceralImpact:
                // "Stuns the target for {stun_duration_seconds} seconds", stretched by the worn stun duration powers.
                Stun(player, target, Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player));
                break;
            case Rune::ShreddingSplinters:
            {
                // "Each lance slows the target by {slow_pct} and reduces its damage by {enemy_damage_pct} for
                // {duration_seconds} seconds. Stacks up to {max_stacks_count} times."
                double const seconds = Numbers::Num(spellId, "duration_seconds");
                unsigned const most = unsigned(Numbers::Num(spellId, "max_stacks_count"));
                unsigned stacks;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    stacks = Buffs::Add(splinters[KeyOf(player, target)], Now(), std::uint64_t(seconds * 1000.0), most);
                }
                Slow(player, target, StackedPct(Numbers::Num(spellId, "slow_pct"), stacks, most), seconds);
                EnemyEffects::Weaken(target, spellId, Numbers::Num(spellId, "enemy_damage_pct"), seconds, most);
                break;
            }
            default:
                break;
        }
    }

    double CritBonus(Player* player, Unit* target)
    {
        if (!player || !target)
            return 0.0;
        std::lock_guard<std::mutex> guard(mutex);
        auto const found = brittle.find(KeyOf(player, target));
        return found != brittle.end() && Holds(Now(), found->second.held.until)
                   ? StackedPct(found->second.pct, found->second.held.stacks, unsigned(Tune("brittle_touch_max_stacks")))
                   : 0.0;
    }
} // namespace DC::Combat::Necromancer::CorpseLance
