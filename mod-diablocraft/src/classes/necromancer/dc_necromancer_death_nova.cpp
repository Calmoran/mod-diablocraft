/*
 * Death Nova and its five runes. The engine strikes every enemy within the skill's radius of the Necromancer; here:
 * Tendril Nova heals for the enemies hit, Bone Nova and Unstable Compound strike for themselves (their radius is not
 * the skill's), Blood Nova takes Life, Blight leaves a patch that slows and weakens what stands in it.
 */

#include "dc_necromancer_death_nova.h"
#include "dc_necromancer_common.h"
#include "dc_necromancer_death_nova_math.h"
#include "dc_necromancer_buffs.h"
#include "../../combat/dc_enemy_effects.h"

#include "GameTime.h"

#include <chrono>
#include <mutex>
#include <unordered_map>

namespace DC::Combat::Necromancer::DeathNova
{
    namespace
    {
        constexpr std::string_view Skill = "Death Nova";

        double Tune(char const* name)
        {
            return DC::Tunables::Get("necromancer", name);
        }

        // Blight's effects last the sheet's second; the patch is felt again in it so they never lapse.
        double PulseSeconds() { return Tune("blight_pulse_seconds"); }

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        // Unstable Compound's stacks, per Necromancer: a cast adds one and starts the time over.
        std::mutex mutex;
        std::unordered_map<std::uint64_t, Buffs::Held> stacks;

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        // "causing them to deal {enemy_damage_pct} less damage for {duration_seconds} second" and slowed by {slow_pct}:
        // on every enemy within the patch.
        void Blight(Player* player, std::uint32_t spellId, Position where, double radius)
        {
            for (Unit* enemy : Combat::Enemies(player, spellId, where, radius))
            {
                double const seconds = Numbers::Num(spellId, "duration_seconds");
                Slow(player, enemy, Numbers::Num(spellId, "slow_pct"), seconds);
                EnemyEffects::Weaken(enemy, spellId, Numbers::Num(spellId, "enemy_damage_pct"), seconds);
            }
        }

        void Pulse(Player* player, std::uint32_t spellId, Position where, double radius, unsigned left)
        {
            if (!player->IsInWorld() || !player->IsAlive() || left == 0)
                return;
            Blight(player, spellId, where, radius);
            if (left > 1)
                player->m_Events.AddEventAtOffset(
                    [player, spellId, where, radius, left] { Pulse(player, spellId, where, radius, left - 1); },
                    std::chrono::milliseconds(std::uint32_t(PulseSeconds() * 1000 + 0.5)));
        }
    } // namespace

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) && StrikesForItself(RuneAt(spellId)) ? std::optional<double>(0.0) : std::nullopt;
    }

    void Casting(Player* player, std::uint32_t spellId)
    {
        if (!player)
            return;
        // "Spend 10% health to unleash a Blood Nova."
        if (RowOf(spellId, Skill) && RuneAt(spellId) == Rune::BloodNova)
            SpendLife(player, Tune("blood_nova_life_cost_pct"));
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        if (!player || !RowOf(spellId, Skill))
            return;
        switch (RuneAt(spellId))
        {
            case Rune::TendrilNova:
                // "Now heals you for {heal_pct} of your health per target hit."
                Heal(
                    player, spellId,
                    HealOfEnemies(player->GetMaxHealth(), Numbers::Num(spellId, "heal_pct"), unsigned(targets.size())));
                break;
            case Rune::BoneNova:
                // "Spines radiate outward and deal {damage_pct} weapon damage as Physical within {radius_yards} yards."
                Combat::StrikeArea(player, spellId, player->GetPosition(), Numbers::Num(spellId, "radius_yards"));
                break;
            case Rune::Blight:
            {
                // "Leave a lingering patch of blight on the ground": the patch has the nova's radius.
                double const radius = Numbers::Num(BaseId(Skill), "radius_yards");
                Blight(player, spellId, player->GetPosition(), radius);
                if (unsigned const pulses = PatchPulses(Tune("blight_patch_seconds"), PulseSeconds()))
                    player->m_Events.AddEventAtOffset(
                        [player, spellId, where = player->GetPosition(), radius, pulses]
                        { Pulse(player, spellId, where, radius, pulses); },
                        std::chrono::milliseconds(std::uint32_t(PulseSeconds() * 1000 + 0.5)));
                break;
            }
            case Rune::UnstableCompound:
            {
                // "Each cast increases the radius of your next Nova by {radius_yards} yards up to {max_stacks_count} times":
                // the stacks the last cast left, if they have not run out, and one more with the time started over.
                unsigned before = 0;
                unsigned const most = unsigned(Numbers::Num(spellId, "max_stacks_count"));
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    Buffs::Held& held = stacks[player->GetGUID().GetRawValue()];
                    before = Buffs::Over(held, Now()) ? 0 : held.stacks;
                    Buffs::Add(held, Now(), std::uint64_t(Tune("unstable_compound_stack_seconds") * 1000.0), most);
                }
                Combat::StrikeArea(player, spellId, player->GetPosition(),
                                   GrownRadius(Tune("unstable_compound_base_radius_yards"), Numbers::Num(spellId, "radius_yards"),
                                               before, most));
                break;
            }
            default:
                break;
        }
    }
} // namespace DC::Combat::Necromancer::DeathNova
