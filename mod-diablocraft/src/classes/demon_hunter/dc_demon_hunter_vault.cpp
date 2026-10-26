/*
 * Vault and its five runes. The vault is the engine's charge to the point aimed at (a spell record and the sheet's
 * numbers; the Discipline cost, Acrobatics' free cast and its cooldown are the record's); here: Trail of Cinders' fire
 * left along the path, Action Shot's arrows, Tumble's cheaper next Vault and Rattling Roll's knock and stun of the
 * enemies the Demon Hunter vaults through.
 */

#include "dc_demon_hunter_vault.h"
#include "dc_demon_hunter_common.h"
#include "dc_demon_hunter_effects.h"
#include "../dc_classes.h"
#include "../dc_resources.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_cost_cut.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_movement_effects.h"
#include "../../combat/dc_spell_numbers.h"
#include "GameTime.h"
#include "MotionMaster.h"
#include "Player.h"
#include "Position.h"
#include "ScriptMgr.h"
#include "Spell.h"
#include "SpellInfo.h"
#include "Unit.h"

#include <algorithm>
#include <cmath>
#include <mutex>
#include <optional>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace DC::Combat::DemonHunter::Vault
{
    namespace
    {
        constexpr std::string_view Skill = "Vault";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        // The fire left along a path, burning until its seconds are up.
        struct Trail
        {
            std::uint32_t spellId = 0;
            Position start;
            double angle = 0;
            double reach = 0;
            double left = 0;  // ms the trail burns still
            double clock = 0; // ms since the last tick
        };

        // The vault in flight whose path stuns: the box travels with the Demon Hunter until the charge ends.
        struct Roll
        {
            std::uint32_t spellId = 0;
            std::uint32_t spline = 0;
            double angle = 0;
            double clock = 0; // ms since the last check
            std::unordered_set<std::uint64_t> stunned;
        };

        struct Vaulting
        {
            std::vector<Trail> trails;
            std::optional<Roll> roll;
        };

        std::mutex mutex;
        std::unordered_map<std::uint64_t, Vaulting> vaulting;

        // One tick of a trail: "deals {damage_pct} weapon damage as Fire over {dot_duration_seconds} seconds" to the
        // enemies standing in it.
        void Burn(Player* player, Trail const& trail, unsigned ticks)
        {
            if (!ticks)
                return;
            double const width = Tune("vault_trail_width_yards");
            double const pct =
                TrailTickPct(Numbers::Num(trail.spellId, "damage_pct"),
                             Numbers::Num(trail.spellId, "dot_duration_seconds"), Tune("vault_trail_tick_seconds"));
            Position middle = trail.start;
            middle.Relocate(trail.start.GetPositionX() + float(std::cos(trail.angle) * trail.reach / 2),
                            trail.start.GetPositionY() + float(std::sin(trail.angle) * trail.reach / 2),
                            trail.start.GetPositionZ());
            for (unsigned i = 0; i < ticks; ++i)
                for (Unit* enemy : Combat::Enemies(player, trail.spellId, middle, trail.reach / 2 + width))
                    if (InBand(PlaceOn(trail.start.GetPositionX(), trail.start.GetPositionY(), trail.angle,
                                       enemy->GetPositionX(), enemy->GetPositionY()),
                               trail.reach, width))
                        Combat::Strike(player, enemy, trail.spellId, pct, true);
        }

        // One check of the box the vault carries: "Enemies you vault through are knocked away and Stunned for
        // {stun_duration_seconds} seconds." Each enemy once.
        void Sweep(Player* player, Roll& roll)
        {
            Position const here = player->GetPosition();
            for (Unit* enemy : Combat::Enemies(player, roll.spellId, here, Tune("vault_stun_area_yards")))
            {
                if (roll.stunned.count(enemy->GetGUID().GetRawValue()))
                    continue;
                if (!InBox(PlaceOn(here.GetPositionX(), here.GetPositionY(), roll.angle, enemy->GetPositionX(),
                                   enemy->GetPositionY()),
                           Tune("vault_stun_strip_length_yards"), Tune("vault_stun_strip_width_yards")))
                    continue;
                roll.stunned.insert(enemy->GetGUID().GetRawValue());
                Abilities::Knockback(player, enemy, Tune("vault_knockback_yards"));
                Stun(player, enemy,
                     Numbers::Num(roll.spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player));
            }
        }

        // One arrow of Action Shot: at the `shot`th nearest enemy of those near the Demon Hunter now, the arrows shared
        // round them.
        void Shoot(Player* player, std::uint32_t spellId, unsigned shot)
        {
            if (!player->IsAlive() || !player->IsInWorld())
                return;
            auto enemies =
                Combat::Enemies(player, spellId, player->GetPosition(), Tune("vault_action_shot_range_yards"));
            if (enemies.empty())
                return;
            std::stable_sort(enemies.begin(), enemies.end(),
                             [player](Unit* a, Unit* b) { return player->GetExactDist(a) < player->GetExactDist(b); });
            Combat::Strike(player, enemies[ShotAt(shot, enemies.size())], spellId, Numbers::Num(spellId, "damage_pct"));
        }

        class Vaults final : public PlayerScript
        {
        public:
            Vaults()
                : PlayerScript("dc_demon_hunter_vault",
                               {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_MAP_CHANGED})
            {
            }

            void OnPlayerUpdate(Player* player, uint32 diff) override
            {
                Vaulting mine;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    auto found = vaulting.find(player->GetGUID().GetRawValue());
                    if (found == vaulting.end())
                        return;
                    mine = found->second;
                }
                if (!player->IsAlive())
                {
                    Stop(player);
                    return;
                }
                std::optional<std::uint32_t> const carried = mine.roll ? std::optional(mine.roll->spline) : std::nullopt;
                std::vector<Trail> kept;
                for (Trail& trail : mine.trails)
                {
                    Burn(player, trail, Due(trail.clock, diff, Tune("vault_trail_tick_seconds") * 1000.0));
                    trail.left -= diff;
                    if (trail.left > 0)
                        kept.push_back(trail);
                }
                if (mine.roll)
                {
                    // The box is carried while the charge that began with the cast runs.
                    if (player->movespline->GetId() != mine.roll->spline || player->movespline->Finalized())
                        mine.roll.reset();
                    else if (Due(mine.roll->clock, diff, Tune("vault_stun_check_seconds") * 1000.0))
                        Sweep(player, *mine.roll);
                }
                std::lock_guard<std::mutex> guard(mutex);
                auto found = vaulting.find(player->GetGUID().GetRawValue());
                if (found == vaulting.end())
                    return;
                // Trails laid during this update were added to the stored list; keep them with what still burns.
                for (std::size_t i = mine.trails.size(); i < found->second.trails.size(); ++i)
                    kept.push_back(found->second.trails[i]);
                found->second.trails = std::move(kept);
                // The box is stored back unless a vault begun during this update has taken its place.
                if (carried && found->second.roll && found->second.roll->spline == *carried)
                    found->second.roll = std::move(mine.roll);
                if (found->second.trails.empty() && !found->second.roll)
                    vaulting.erase(found);
            }

            void OnPlayerLogout(Player* player) override
            {
                Stop(player);
            }

            void OnPlayerMapChanged(Player* player) override
            {
                Stop(player);
            }

            static void Stop(Player* player)
            {
                std::lock_guard<std::mutex> guard(mutex);
                vaulting.erase(player->GetGUID().GetRawValue());
            }
        };

        // The cast of a Vault of the Tumble rune: "After using Vault, your next Vault within {duration_seconds} seconds has its Discipline cost reduced by
        // {cost_reduction_pct}". The cut is the cost the core charges for the next Vault, lowered BEFORE the cast through the skill's hidden cost aura
        // (CostCut), so the full price is never taken; each Vault of the rune starts the window again.
        class CastHook final : public AllSpellScript
        {
        public:
            CastHook()
                : AllSpellScript("dc_demon_hunter_vault_cast", {ALLSPELLHOOK_ON_CAST})
            {
            }

            void OnSpellCast(Spell* spell, Unit* caster, SpellInfo const* info, bool) override
            {
                Player* player = caster ? caster->ToPlayer() : nullptr;
                if (!player || !info || spell->IsTriggered() || RuneAt(info->Id) != Rune::Tumble)
                    return;
                CostCut::Hold(player, Skill, BaseId(Skill), Numbers::Num(info->Id, "cost_reduction_pct"), Numbers::Num(info->Id, "duration_seconds"));
            }
        };
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        return Is(spellId) ? std::optional<double>(0.0) : std::nullopt;
    }

    double CritBonus(std::uint32_t spellId)
    {
        return CritBonus(RuneAt(spellId));
    }

    void Ground(Player* player, std::uint32_t spellId, Position const& destination)
    {
        if (!player || !Is(spellId))
            return;
        Position const start = player->GetPosition();
        double const angle = start.GetAbsoluteAngle(&destination);
        switch (RuneAt(spellId))
        {
            case Rune::TrailOfCinders:
            {
                // "Leave a trail of fire in your wake": the path the charge takes, at most the skill's distance toward
                // the point aimed at.
                Trail trail;
                trail.spellId = spellId;
                trail.start = start;
                trail.angle = angle;
                trail.reach =
                    std::min(double(start.GetExactDist2d(destination)), Numbers::Num(spellId, "distance_yards"));
                trail.left = Numbers::Num(spellId, "dot_duration_seconds") * 1000.0;
                std::lock_guard<std::mutex> guard(mutex);
                vaulting[player->GetGUID().GetRawValue()].trails.push_back(trail);
                break;
            }
            case Rune::ActionShot:
            {
                // "shoot {projectile_count} arrows for {damage_pct} weapon damage": one now, the rest every fire
                // interval.
                unsigned const arrows = unsigned(Numbers::Num(spellId, "projectile_count"));
                auto const interval = Tune("vault_action_shot_interval_seconds") * 1000.0;
                for (unsigned shot = 0; shot < arrows; ++shot)
                    if (shot == 0)
                        Shoot(player, spellId, shot);
                    else
                        player->m_Events.AddEventAtOffset(
                            [player, spellId, shot] { Shoot(player, spellId, shot); },
                            std::chrono::milliseconds(std::uint32_t(interval * shot + 0.5)));
                break;
            }
            case Rune::RattlingRoll:
            {
                // The charge began with the cast; its box is checked until it ends, the first check at once.
                if (player->movespline->Finalized())
                    break;
                Roll roll;
                roll.spellId = spellId;
                roll.spline = player->movespline->GetId();
                roll.angle = angle;
                Sweep(player, roll);
                std::lock_guard<std::mutex> guard(mutex);
                vaulting[player->GetGUID().GetRawValue()].roll = std::move(roll);
                break;
            }
            default:
                break;
        }
    }

    void RegisterScripts()
    {
        new Vaults();
        new CastHook();
    }
} // namespace DC::Combat::DemonHunter::Vault
