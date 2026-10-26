/*
 * World of DiabloCraft - the allies a legendary item summons, Combat's side (N-SUMMON; Bovine Bardiche). See dc_item_summons.h.
 */

#include "dc_item_summons.h"
#include "dc_combat.h"
#include "dc_item_summon_math.h"
#include "dc_spell_shells.h"
#include "../common/dc_tunables.h"
#include "../rifts/dc_ally.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "Random.h"
#include "TemporarySummon.h"
#include "Timer.h"
#include "World.h"

#include <algorithm>
#include <limits>
#include <mutex>
#include <unordered_map>

namespace DC::Combat::ItemSummons
{
    namespace
    {
        // The cow of data/legendary_summons.csv (the stock Cow 2442, display 1060) and the item whose hit record its
        // swings are dealt under (data/legendary_power_buffs.csv, `hit`).
        constexpr std::uint32_t Cow = 900120;
        constexpr char const* Bardiche = "Unique_Polearm_101_x1";
        // A cow swings once a second, carrying its owner's attacks per second (ItemSummon::SwingPct): the Ancients'
        // damage a second, on the fixed clock Ally::OnSwing takes at startup. An engineering cadence, not a D3 number.
        constexpr std::uint32_t SwingMs = 1000;

        std::mutex mutex;
        // When each player's last herd came (getMSTime). ponytail: one entry per player who ever called a herd, never
        // erased; erase on logout if the map ever matters.
        std::unordered_map<std::uint64_t, std::uint32_t> lastHerd;

        // The combat tunables bovine_bardiche_*; a blank one reads 0.
        double Tune(char const* name)
        {
            return DC::Tunables::Has("combat", name) ? DC::Tunables::Get("combat", name) : 0.0;
        }

        // One swing: the owner's hit at the cow's percent, dealt as the owner's (a pylon strike's way), so the kill is
        // the owner's. World's AI calls it only while the cow stands within melee range of its target.
        void Swing(Creature&, Player& owner, Unit& target)
        {
            std::uint32_t const record = Shells::PowerBuffFor(Bardiche, "summon_herd");
            double const pct = ItemSummon::SwingPct(Tune("bovine_bardiche_cow_damage_pct"),
                                                    Tune("bovine_bardiche_cow_damage_delta_pct"), rand_norm(),
                                                    AttacksPerSecond(&owner), SwingMs);
            Hit hit;
            if (record && pct > 0 && ComputeHit(&owner, &target, record, hit, pct))
                DealHit(&owner, &target, record, hit);
        }
    } // namespace

    void Herd(Player* player, unsigned cows, double coefficient)
    {
        std::uint32_t const ms = std::uint32_t(std::max(0.0, Tune("bovine_bardiche_cow_seconds")) * 1000.0);
        if (!player || !cows || !ms)
            return;
        std::uint32_t const now = getMSTime();
        {
            std::lock_guard<std::mutex> lock(mutex);
            auto const found = lastHerd.find(player->GetGUID().GetRawValue());
            std::optional<std::uint32_t> const last =
                found == lastHerd.end() ? std::nullopt : std::optional<std::uint32_t>(found->second);
            if (!ItemSummon::HerdComes(last, now, Tune("bovine_bardiche_cooldown_seconds"), coefficient,
                                       Tune("bovine_bardiche_chance_pct"),
                                       [](double pct) { return roll_chance_f(static_cast<float>(pct)); }))
                return;
            lastHerd[player->GetGUID().GetRawValue()] = now;
        }
        double const life = Tune("bovine_bardiche_cow_life_pct_of_owner");
        for (unsigned i = 0; i < cows; ++i)
            if (TempSummon* cow = player->SummonCreature(Cow, player->GetPosition(), TEMPSUMMON_TIMED_DESPAWN, ms))
            {
                // A stock summon's Life at the owner's level, as Creature::SelectLevel makes it (the Cow is a normal
                // rank); a tunable number is instead that share of the owner's maximum Life, as Call of the Ancients.
                CreatureTemplate const* info = cow->GetCreatureTemplate();
                CreatureBaseStats const* stats = sObjectMgr->GetCreatureBaseStats(player->GetLevel(), info->unit_class);
                double const maxLife = life > 0 ? life / 100.0 * player->GetMaxHealth()
                                                : stats->GenerateHealth(info) * double(sWorld->getRate(RATE_CREATURE_NORMAL_HP));
                cow->SetMaxHealth(std::max<std::uint32_t>(
                    1, std::uint32_t(std::min(double(std::numeric_limits<std::uint32_t>::max()), maxLife))));
                cow->SetHealth(cow->GetMaxHealth());
            }
    }

    void RegisterScripts()
    {
        DC::Rifts::Ally::OnSwing(Cow, SwingMs, Swing);
    }
} // namespace DC::Combat::ItemSummons
