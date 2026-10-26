/*
 * Lashing Tail Kick and its five runes.
 */

#include "dc_monk_lashing_tail_kick_cast.h"
#include "dc_monk_lashing_tail_kick.h"
#include "dc_monk_common.h"
#include "../../combat/dc_item_powers.h"
#include "ObjectAccessor.h"
#include "SpellAuraEffects.h"

#include <chrono>
#include <map>

namespace DC::Combat::Monk::Kick
{
    namespace
    {
        constexpr std::string_view Skill = "Lashing Tail Kick";
        // Stock "Dazed" (50259): one MOD_DECREASE_SPEED effect, Snare mechanic; Hand of Ytar's slow, set to the sheet's
        // percentage and seconds.
        constexpr std::uint32_t Slowed = 50259;
        // Stock "Stun" (56): one MOD_STUN effect, Stun mechanic; Scorpion Sting's stun.
        constexpr std::uint32_t Stunned = 56;

        Shells::Ability const* Row(std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && Skill == row->skill ? row : nullptr;
        }

        bool IsRune(std::uint32_t spellId, std::string_view rune)
        {
            auto const* row = Row(spellId);
            return row && rune == row->rune;
        }

        double Tune(char const* name)
        {
            return DC::Tunables::Get("monk", name);
        }

        // A stock aura of `seconds` on `target`, its first effect set to `amount` (0 keeps the record's). Control
        // immunity answers nothing.
        void Hold(Player* player, Unit* target, std::uint32_t aura, int amount, double seconds)
        {
            if (seconds <= 0 || !target->IsAlive())
                return;
            target->RemoveAurasDueToSpell(aura, player->GetGUID());
            if (Aura* held = player->AddAura(aura, target))
            {
                if (amount)
                    if (AuraEffect* effect = held->GetEffect(EFFECT_0))
                        effect->ChangeAmount(amount);
                held->SetMaxDuration(int32(seconds * 1000));
                held->SetDuration(int32(seconds * 1000));
            }
        }

        // Vulture Claw Kick's burn, one per Monk and enemy: a new kick starts it over, and the ticks of the old one
        // find their stamp gone and stop.
        std::mutex mutex;
        std::map<std::pair<std::uint64_t, std::uint64_t>, std::uint64_t> burns;
        std::uint64_t stamps = 0;

        void Tick(Player* player, ObjectGuid enemy, std::uint32_t spellId, std::uint64_t stamp, unsigned left,
                  double pct, std::uint32_t intervalMs)
        {
            auto const key = std::make_pair(player->GetGUID().GetRawValue(), enemy.GetRawValue());
            Unit* target = ObjectAccessor::GetUnit(*player, enemy);
            bool alive = target && target->IsAlive() && player->IsAlive();
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto found = burns.find(key);
                if (found == burns.end() || found->second != stamp)
                    return;
                if (!alive || left == 0)
                {
                    burns.erase(found);
                    return;
                }
            }
            Combat::Strike(player, target, spellId, pct, true);
            if (left > 1)
                player->m_Events.AddEventAtOffset([player, enemy, spellId, stamp, left, pct, intervalMs]
                                                  { Tick(player, enemy, spellId, stamp, left - 1, pct, intervalMs); },
                                                  std::chrono::milliseconds(intervalMs));
            else
            {
                std::lock_guard<std::mutex> guard(mutex);
                burns.erase(key);
            }
        }

        void Burn(Player* player, Unit* enemy, std::uint32_t spellId)
        {
            // The sheet gives the total and the seconds, the power file no tick length (Power/Monk_LashingTailKick.pow
            // SF_26, SF_27): the tick is a blank tunable, and without it the burn is not built.
            if (!DC::Tunables::Has("monk", "lashing_tail_kick_dot_tick_seconds"))
                return;
            double const tick = Tune("lashing_tail_kick_dot_tick_seconds");
            unsigned const ticks = DotTicks(Numbers::Num(spellId, "dot_duration_seconds"), tick);
            if (!ticks)
                return;
            std::uint64_t stamp;
            {
                std::lock_guard<std::mutex> guard(mutex);
                stamp = ++stamps;
                burns[{player->GetGUID().GetRawValue(), enemy->GetGUID().GetRawValue()}] = stamp;
            }
            auto const interval = std::uint32_t(tick * 1000 + 0.5);
            double const pct = TickPct(Numbers::Num(spellId, "damage_pct", "dot"), ticks);
            player->m_Events.AddEventAtOffset([player, guid = enemy->GetGUID(), spellId, stamp, ticks, pct, interval]
                                              { Tick(player, guid, spellId, stamp, ticks, pct, interval); },
                                              std::chrono::milliseconds(interval));
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return Row(spellId) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        if (!Row(spellId))
            return std::nullopt;
        // Vulture Claw Kick states its rows as "hit" (755%) and "dot" (230%); the kick itself is the first.
        if (IsRune(spellId, "Vulture Claw Kick"))
            return Numbers::Get(spellId, "damage_pct", "hit");
        return Numbers::Get(spellId, "damage_pct");
    }

    std::vector<Unit*> Beside(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        std::vector<Unit*> beside;
        if (!player || !Row(spellId))
            return beside;
        // "enemies within {radius_yards} yards" (Vulture Claw Kick 10, Sweeping Armada 15,
        // Power/Monk_LashingTailKick.pow SF_9 and SF_13 'AOE radius'): all around. The other runes and the kick itself
        // are the cone of 10 yards and 180 degrees (SF_6, SF_7), where the core's own cone is 90: the enemies of the
        // half circle it did not take are struck here.
        bool const around = IsRune(spellId, "Vulture Claw Kick") || IsRune(spellId, "Sweeping Armada");
        double const reach = Numbers::Own(spellId, "radius_yards").value_or(Combat::TargetRadius(spellId));
        float const arc = float(ArcRadians(Tune("lashing_tail_kick_cone_degrees")));
        auto add = [&](Unit* enemy)
        {
            if (std::find(targets.begin(), targets.end(), enemy) == targets.end() &&
                std::find(beside.begin(), beside.end(), enemy) == beside.end())
                beside.push_back(enemy);
        };
        for (Unit* enemy : Combat::Enemies(player, spellId, player->GetPosition(), reach))
            if (around || player->HasInArc(arc, enemy))
                add(enemy);

        // Spinning Flame Kick: "a column of fire that burns through enemies" for SF_16 50 yards; its width is in no
        // sheet and no power file: a blank tunable, and without it only the kick's own cone is struck.
        if (IsRune(spellId, "Spinning Flame Kick") && DC::Tunables::Has("monk", "lashing_tail_kick_column_width_yards"))
        {
            double const length = Tune("lashing_tail_kick_column_yards"),
                         width = Tune("lashing_tail_kick_column_width_yards");
            for (Unit* enemy : Combat::Enemies(player, spellId, player->GetPosition(), length))
                if (InColumn(player->GetPositionX(), player->GetPositionY(), player->GetOrientation(), length, width,
                             enemy->GetPositionX(), enemy->GetPositionY()))
                    add(enemy);
        }
        return beside;
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        if (!player || !Row(spellId))
            return;
        auto const pct = BasePct(spellId);
        std::vector<Unit*> struck = targets;
        // N-NHIT (Scarbringer): the kick hits the core's cone and these together, so each one's place among the cast's
        // hits is counted over both lists, nearest the Monk first, as Combat's ResolveCast counted the cone's (a
        // `first_hits` row reads it), and the enemies the cast hits in all are both lists (`cast_enemies_at_most`).
        auto const beside = Beside(player, spellId, targets);
        std::vector<double> distances;
        for (Unit* enemy : targets)
            distances.push_back(player->GetExactDist(enemy));
        for (Unit* enemy : beside)
            distances.push_back(player->GetExactDist(enemy));
        unsigned& place = ItemPowers::HitPlace();
        unsigned& enemies = ItemPowers::CastEnemies();
        unsigned const outerPlace = place, outerEnemies = enemies;
        enemies = distances.size();
        std::size_t index = targets.size();
        for (Unit* enemy : beside)
        {
            place = ItemPower::NearestPlace(distances, index++);
            if (Combat::Strike(player, enemy, spellId, pct))
                struck.push_back(enemy);
        }
        place = outerPlace;
        enemies = outerEnemies;

        // No enemy in the core's cone but one beside you: the kick still connected, once.
        if (targets.empty() && !struck.empty())
            Combat::Connected(player, spellId, unsigned(struck.size()));

        // The power file's knockback (SF_3 'Total Knockback Magnitude', SF_4 height, SF_5 gravity), every rune's: each
        // enemy the kick struck is thrown away from you by the stock knockback record the pylons' knock-up and Deadly
        // Reach's use, so the core spares what it always spares (bosses, the knockback-immune, the rooted). That
        // record's speeds are baked into it (pylon_speed_knockup_speed_xy and _z); the power file's three numbers are
        // D3 physics units no sheet converts, so they are kept as tunables (lashing_tail_kick_knockback_*) and do not
        // yet drive the throw.
        for (Unit* enemy : struck)
            if (Knocks(true, enemy->IsAlive()))
                player->CastSpell(enemy, Shells::PylonSpeedThrow, true);

        if (IsRune(spellId, "Vulture Claw Kick"))
            for (Unit* enemy : struck)
                Burn(player, enemy, spellId);
        // Hand of Ytar: "Enemies are chilled at long range, Slowing them by {slow_pct} for {slow_duration_seconds}
        // seconds".
        if (IsRune(spellId, "Hand of Ytar"))
            for (Unit* enemy : struck)
                Hold(player, enemy, Slowed, SlowAmount(Numbers::Num(spellId, "slow_pct")),
                     Numbers::Num(spellId, "slow_duration_seconds"));
        // Scorpion Sting: "Enemies hit are stunned for {stun_duration_seconds} seconds" (SF_11 the chance, 1).
        if (IsRune(spellId, "Scorpion Sting"))
            for (Unit* enemy : struck)
                Hold(player, enemy, Stunned, 0, Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player));
    }
} // namespace DC::Combat::Monk::Kick
