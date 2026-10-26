#include "dc_item_powers_internal.h"

// The item powers that run on time: a skill's re-used casts and the cooldown cut (Lut Socks, In-geom), the stood-still timer (Boots of Disregard) and
// the movement speed that follows the Life missing (Irontoe Mudsputters).

namespace DC::Combat
{
    namespace Detail
    {
        // The seconds `cooldown_reduction_seconds` powers that are on (In-geom) take off a skill's cooldown.
        double CooldownCut(Player* player)
        {
            ItemPower::Situation seen = Seen(player);
            std::lock_guard<std::mutex> lock(mutex);
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            return ItemPower::PlayerSum(Data().rows, CountsOf(guid), "cooldown_reduction_seconds", SituationOf(guid, std::move(seen)));
        }

        // N-COST (Pride's Fall): the percent the `resource_cost_reduction_pct` rows that hold now take off every resource cost, kept on the sheet as a Temporary flat Resource
        // Cost Reduction (QuietCostId) that the class's gear cost aura is rebuilt from (Passives::RefreshModifiers), beside every other reduction, and redone only when it changed:
        // it comes on when the row's condition holds (no damage taken for its seconds) and off at the first update after a hit is taken. Looked at only when some row holds the stat.
        void NoDamageCost(Player* player)
        {
            if (!Data().quietCost)
                return;
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            double cut;
            bool changed;
            {
                std::lock_guard<std::mutex> lock(mutex);
                auto mine = clocks.find(guid);
                if (mine == clocks.end())
                    return;
                Clock& clock = mine->second;
                cut = ItemPower::CostCutPct(Data().rows, CountsOf(guid), SituationOf(guid));
                changed = cut != clock.quietCost;
                clock.quietCost = cut;
            }
            if (!changed)
                return;
            Stats::RemoveContribution(guid, Source::Temporary, Stat::ResourceCostReduction, QuietCostId);
            if (cut > 0)
                Stats::AddContribution(guid, {Source::Temporary, Stat::ResourceCostReduction, QuietCostId, cut, Bucket::Flat});
            Passives::RefreshModifiers(player);
        }

        // N-PLIFE (Rogar's Huge Stone): the Life Regen bonus follows the wearer's missing Life: looked at once per the item's `life_regen_tick_seconds` (ItemPower::LifeLookDue), put on the
        // sheet as a Temporary Percent contribution of the sheet's Life Regen (MissingRegenId; the sheet multiplies the regeneration by 1 + the percent) and redone only when it
        // changed (ItemPower::RegenByMissing rounds to 0.1). Looked at only when some row holds the stat, and only for a player who wears something that owns a power.
        void MissingLifeRegen(Player* player)
        {
            if (!Data().missingRegen)
                return;
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            std::uint32_t const now = getMSTime();
            double const life = player->GetMaxHealth() ? 100.0 * player->GetHealth() / player->GetMaxHealth() : 100.0;
            double pct;
            bool changed;
            {
                std::lock_guard<std::mutex> lock(mutex);
                auto mine = clocks.find(guid);
                if (mine == clocks.end())
                    return;
                Clock& clock = mine->second;
                ItemPower::Situation const situation = SituationOf(guid);
                double const every = ItemPower::PlayerSetTo(Data().rows, CountsOf(guid), "life_regen_tick_seconds", 0.0, situation);
                if (!ItemPower::LifeLookDue(clock.missingRegenAt, now, every))
                    return;
                clock.missingRegenAt = now;
                pct = ItemPower::RegenByMissing(Data().rows, CountsOf(guid), life, situation);
                changed = pct != clock.missingRegen;
                clock.missingRegen = pct;
            }
            if (!changed)
                return;
            Stats::RemoveContribution(guid, Source::Temporary, Stat::LifeRegen, MissingRegenId);
            if (pct > 0)
                Stats::AddContribution(guid, {Source::Temporary, Stat::LifeRegen, MissingRegenId, pct, Bucket::Percent});
            Stats::Recompute(player);
            Inventory::PushSheet(player);
        }

        // N-NEXT (Saffron Wrap): a skill was pressed. The enemies its last cast hit, if that was within the item's `enemy_hit_stack_seconds`, ride on this cast and are spent by it
        // (ItemPower::EnemyPress); the hits of the cast read them (ItemPowers::EnemyStacks). Only for a skill some worn row counts: the others keep no stack.
        void EnemyStackPress(Player* player, std::string const& skill)
        {
            if (!Data().enemyStacks)
                return;
            double const seconds = ItemPowers::SkillSetTo(player, skill, "enemy_hit_stack_seconds", 0.0);
            std::lock_guard<std::mutex> lock(mutex);
            auto mine = clocks.find(player->GetGUID().GetRawValue());
            if (mine == clocks.end())
                return;
            ItemPower::EnemyStack& stack = mine->second.enemyStacks[skill];
            stack = ItemPower::EnemyPress(stack, getMSTime(), seconds);
        }

        // N-NEXT: a cast of the skill hit `enemies` enemies (Combat::Connected): they are what the next cast of it will ride on, at most the item's `enemy_hit_stacks_max`.
        void EnemyStackConnect(Player* player, std::uint32_t spellId, unsigned enemies)
        {
            if (!Data().enemyStacks || !enemies)
                return;
            auto const shell = Shells::FindAbility(spellId);
            if (!shell)
                return;
            double const most = ItemPowers::SkillSetTo(player, shell->skill, "enemy_hit_stacks_max", 0.0);
            if (most < 1)
                return;
            std::lock_guard<std::mutex> lock(mutex);
            auto mine = clocks.find(player->GetGUID().GetRawValue());
            if (mine == clocks.end())
                return;
            ItemPower::EnemyStack& stack = mine->second.enemyStacks[shell->skill];
            stack = ItemPower::EnemyConnect(stack, enemies, static_cast<unsigned>(most), getMSTime());
        }
    } // namespace Detail
} // namespace DC::Combat

namespace DC::Combat::ItemPowers
{
    namespace
    {
        // Lut Socks (N-CHG): the cooldown a skill would have had at the cast, its own less the In-geom seconds, installed on every rune of the skill.
        void StartCooldown(Player* player, std::uint32_t spellId)
        {
            std::uint32_t const full = Combat::SkillCooldownMilliseconds(player, spellId);
            double const cut = CooldownCut(player) * 1000.0;
            Combat::SendSkillCooldown(player, spellId, cut >= full ? 0 : full - static_cast<std::uint32_t>(cut));
        }

        // The end of the window numbered `token`: if the last cast did not close it first, the cooldown begins.
        void ReuseEnded(Player* player, std::uint32_t spellId, std::string const& skill, std::uint32_t token)
        {
            bool closed = false;
            {
                std::lock_guard<std::mutex> lock(mutex);
                auto mine = windows.find(player->GetGUID().GetRawValue());
                if (mine != windows.end())
                {
                    auto window = mine->second.find(skill);
                    closed = window != mine->second.end() && ItemPower::ReuseEnded(window->second.state, token);
                }
            }
            if (closed)
                StartCooldown(player, spellId);
        }
    } // namespace
} // namespace DC::Combat::ItemPowers

namespace DC::Combat
{
    namespace Detail
    {
        // A pressed cast of `skill`, after the core installed its cooldown: true when the rows (reuse_casts within reuse_window_seconds) keep
        // the skill open, so the cooldown is taken back and the end of the window is scheduled by the cast that opened it. The numbers are
        // read before the lock, like every reader here.
        bool ReuseCast(Player* player, std::uint32_t spellId, std::string const& skill)
        {
            double const casts = SkillSetTo(player, skill, "reuse_casts", 0);
            double const window = SkillSetTo(player, skill, "reuse_window_seconds", 0);
            if (casts < 2 || window <= 0)
                return false;
            ItemPower::ReuseStep step;
            {
                std::lock_guard<std::mutex> lock(mutex);
                Window& mine = windows[player->GetGUID().GetRawValue()][skill];
                mine.spellId = spellId;
                step = ItemPower::ReuseCast(mine.state, static_cast<unsigned>(casts), window, getMSTime());
            }
            if (!step.keepOpen)
                return false;
            Combat::SendSkillCooldown(player, spellId, 0);
            if (step.opened)
                player->m_Events.AddEventAtOffset([player, spellId, skill, token = step.token] { ReuseEnded(player, spellId, skill, token); },
                                                  Milliseconds(static_cast<std::uint32_t>(std::lround(window * 1000.0))));
            return true;
        }

        // A logout inside a window: the cooldown begins now, so that the saved character does not come back with none.
        void ReuseLogout(Player* player)
        {
            std::vector<std::uint32_t> open;
            {
                std::lock_guard<std::mutex> lock(mutex);
                auto mine = windows.find(player->GetGUID().GetRawValue());
                if (mine == windows.end())
                    return;
                for (auto const& window : mine->second)
                    if (window.second.state.open)
                        open.push_back(window.second.spellId);
                windows.erase(mine);
            }
            for (std::uint32_t spellId : open)
                StartCooldown(player, spellId);
        }

        // N-MOVE (Boots of Disregard): the stood-still timer restarts whenever the player moves, and the Life Regen the `life_regen` rows give
        // (their number per stack of `standing_still`) is a Temporary contribution on the sheet, redone when the stacks change. Looked at only
        // for a player who wears an item that owns a power, and only when some row holds `standing_still`.
        void StandStill(Player* player)
        {
            if (!Data().still)
                return;
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            double regen;
            bool changed;
            {
                std::lock_guard<std::mutex> lock(mutex);
                auto mine = clocks.find(guid);
                if (mine == clocks.end())
                    return;
                Clock& clock = mine->second;
                clock.stillSince = ItemPower::StillSince(player->isMoving(), clock.stillTracked, clock.stillSince, getMSTime());
                clock.stillTracked = true;
                regen = ItemPower::PlayerSum(Data().rows, CountsOf(guid), "life_regen", SituationOf(guid));
                changed = regen != clock.lifeRegen;
                clock.lifeRegen = regen;
            }
            if (!changed)
                return;
            Stats::RemoveContribution(guid, Source::Temporary, Stat::LifeRegen, RegenId);
            if (regen > 0)
                Stats::AddContribution(guid, {Source::Temporary, Stat::LifeRegen, RegenId, regen, Bucket::Flat});
            Stats::Recompute(player);
            Inventory::PushSheet(player);
        }

        // N-PSPD (Irontoe Mudsputters): the movement speed the `movement_speed_pct` rows give (under `life_missing`, their number per 1% of Life missing)
        // is a Temporary contribution on the sheet in the bucket of a power's own speed, looked at again at most every look period and redone only
        // when it changed. Looked at only when some row gives it, and only for a player who wears an item that owns a power.
        void MovementSpeed(Player* player)
        {
            if (!Data().speed)
                return;
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            {
                std::lock_guard<std::mutex> lock(mutex);
                auto mine = clocks.find(guid);
                if (mine == clocks.end())
                    return;
                Clock& clock = mine->second;
                std::uint32_t const now = getMSTime();
                if (!ItemPower::LookDue(clock.speedLooked, clock.speedAt, now,
                                        static_cast<std::uint32_t>(DC::Tunables::Get("combat", "item_power_speed_look_seconds") * 1000.0)))
                    return;
                clock.speedLooked = true;
                clock.speedAt = now;
            }
            double speed;
            bool changed;
            ItemPower::Situation seen = Seen(player);
            {
                std::lock_guard<std::mutex> lock(mutex);
                auto mine = clocks.find(guid);
                if (mine == clocks.end())
                    return;
                speed = ItemPower::PlayerSum(Data().rows, CountsOf(guid), "movement_speed_pct", SituationOf(guid, std::move(seen)));
                changed = speed != mine->second.movementSpeed;
                mine->second.movementSpeed = speed;
            }
            if (!changed)
                return;
            Stats::RemoveContribution(guid, Source::Temporary, Stat::MovementSpeed, SpeedId);
            if (speed > 0)
                Stats::AddContribution(guid, {Source::Temporary, Stat::MovementSpeed, SpeedId, speed, Bucket::Uncapped});
            Stats::Recompute(player);
            Inventory::PushSheet(player);
        }

        // N-DERIVED (Heart of Iron): the Thorns the `thorns_per_vitality_pct` rows give are a share of the sheet's Vitality, so the number follows it: read from the
        // update hook, put on the sheet as a Temporary flat Thorns contribution (VitalityThornsId) and redone only when it changed (an item put on or taken off, a roll,
        // any change of Vitality). Flat, so the sheet's Thorns bonuses multiply it after, as they do every Thorns source (Calculate). Looked at only when some row
        // holds the stat, and only for a player who wears something that owns a power.
        void VitalityThorns(Player* player)
        {
            if (!Data().vitalityThorns)
                return;
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            auto const sheet = Stats::Get(guid);
            double const vitality = sheet ? (*sheet)[Stat::Vitality] : 0.0;
            double thorns;
            bool changed;
            {
                std::lock_guard<std::mutex> lock(mutex);
                auto mine = clocks.find(guid);
                if (mine == clocks.end())
                    return;
                Clock& clock = mine->second;
                thorns = ItemPower::ThornsOfVitality(Data().rows, CountsOf(guid), vitality, SituationOf(guid));
                changed = thorns != clock.vitalityThorns;
                clock.vitalityThorns = thorns;
            }
            if (!changed)
                return;
            Stats::RemoveContribution(guid, Source::Temporary, Stat::Thorns, VitalityThornsId);
            if (thorns > 0)
                Stats::AddContribution(guid, {Source::Temporary, Stat::Thorns, VitalityThornsId, thorns, Bucket::Flat});
            Stats::Recompute(player);
            Inventory::PushSheet(player);
        }

    } // namespace Detail
} // namespace DC::Combat
