/*
 * Multishot and its five runes. The cast is the engine's cone (a spell record, its Hatred cost and the sheet's numbers:
 * Full Broadside's damage, Fire at Will's cost and Lightning); here: Wind Chill's chill and the critical hit chance
 * every attacker has against the enemies it chilled, Arsenal's rockets, Suppression Fire's knockback of the first
 * enemies hit.
 */

#include "dc_demon_hunter_multishot.h"
#include "dc_demon_hunter_common.h"
#include "dc_demon_hunter_effects.h"
#include "dc_demon_hunter_passives.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_movement_effects.h"
#include "../../combat/dc_spell_numbers.h"
#include "GameTime.h"
#include "Player.h"
#include "Random.h"
#include "Unit.h"

#include <chrono>
#include <mutex>
#include <unordered_map>

namespace DC::Combat::DemonHunter::Multishot
{
    namespace
    {
        constexpr std::string_view Skill = "Multishot";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        // The enemies Wind Chill has chilled: when each one's extra critical hit chance ends, and how much it is.
        struct Chill
        {
            std::uint64_t closes = 0;
            double pct = 0;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, Chill> chilled;

        // Arsenal: one rocket at a random enemy within the file's search radius of the Demon Hunter, as the player
        // stands now.
        void Rocket(Player* player, std::uint32_t spellId)
        {
            if (!player->IsAlive() || !player->IsInWorld())
                return;
            auto const enemies =
                Combat::Enemies(player, spellId, player->GetPosition(), Tune("multishot_rocket_range_yards"));
            if (!enemies.empty())
                Combat::Strike(player, enemies[PickAt(frand(0.0f, 1.0f), enemies.size())], spellId,
                               Numbers::Num(spellId, "damage_pct") * Passive::RocketFactor(player));
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        // Arsenal states its rockets' damage as its own; the volley is the skill's.
        return RuneAt(spellId) == Rune::Arsenal ? std::optional<double>(Numbers::Num(BaseId(Skill), "damage_pct"))
                                                : std::nullopt;
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const&)
    {
        if (!player || RuneAt(spellId) != Rune::Arsenal)
            return;
        // "Every time you fire, launch {projectile_count} rockets at nearby enemies": the first after the warmup, one
        // every interval.
        for (unsigned index = 0, count = unsigned(Numbers::Num(spellId, "projectile_count")); index < count; ++index)
            player->m_Events.AddEventAtOffset(
                [player, spellId] { Rocket(player, spellId); },
                std::chrono::milliseconds(RocketDelayMs(index, Tune("multishot_rocket_warmup_seconds"),
                                                        Tune("multishot_rocket_interval_seconds"))));
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId)
    {
        if (!player || !target)
            return;
        switch (RuneAt(spellId))
        {
            case Rune::WindChill:
            {
                // "Enemies hit are Chilled and have {crit_chance_pct} increased chance to be Critically Hit for
                // {duration_seconds} seconds."
                double const seconds = Numbers::Num(spellId, "duration_seconds");
                Slow(player, target, Tune("multishot_chill_pct"), seconds);
                std::lock_guard<std::mutex> guard(mutex);
                std::uint64_t const now = Now();
                std::erase_if(chilled, [now](auto const& entry) { return !Open(entry.second.closes, now); });
                chilled[target->GetGUID().GetRawValue()] = {ClosesAt(now, seconds), Numbers::Num(spellId, "crit_chance_pct")};
                break;
            }
            case Rune::SuppressionFire:
                // "Knockback the first {target_count} enemies hit."
                if (KnockedBack(ItemPowers::HitPlace(), unsigned(Numbers::Num(spellId, "target_count"))))
                    Abilities::Knockback(player, target, Tune("multishot_knockback_yards"));
                break;
            default:
                break;
        }
    }

    double CritBonus(Unit* target)
    {
        if (!target)
            return 0.0;
        std::lock_guard<std::mutex> guard(mutex);
        auto const found = chilled.find(target->GetGUID().GetRawValue());
        return found != chilled.end() && Open(found->second.closes, Now()) ? found->second.pct : 0.0;
    }
} // namespace DC::Combat::DemonHunter::Multishot
