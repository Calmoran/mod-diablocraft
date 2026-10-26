/*
 * Firebats and its five runes. The record is a real channel (the core holds it until the Witch Doctor lets go or does
 * something else) with no hit and no cost of its own; here: a tick at the cadence attack speed gives, the Mana of each
 * tick, and the rune's part: Dire Bats' one large bat a tick, Hungry Bats' bats that seek an enemy, Plague Bats'
 * growing damage, Vampire Bats' start cost in place of the ticks', Cloud of Bats' swirl round the Witch Doctor whose
 * damage grows.
 */

#include "dc_witch_doctor_firebats.h"
#include "dc_witch_doctor_common.h"
#include "dc_witch_doctor_pick.h"
#include "../dc_classes.h"
#include "../dc_resources.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_spell_numbers.h"
#include "GameTime.h"
#include "Player.h"
#include "Random.h"
#include "ScriptMgr.h"
#include "Spell.h"
#include "Unit.h"

#include <cmath>
#include <mutex>
#include <unordered_map>

namespace DC::Combat::WitchDoctor::Firebats
{
    namespace
    {
        constexpr std::string_view Skill = "Firebats";
        constexpr double Pi = 3.14159265358979323846;

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        struct Plague
        {
            unsigned stacks = 0;
            std::uint64_t lastMs = 0;
        };

        struct Channel
        {
            std::uint32_t spellId = 0;
            double clock = 0;   // ms since the last tick
            double seconds = 0; // ms the channel has lasted
            std::unordered_map<std::uint64_t, Plague> plagued;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, Channel> channels;

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        // The attacks a second's ticks: the skill's, and each rune that has its own.
        double TicksPerAttack(std::uint32_t spellId)
        {
            switch (RuneAt(spellId))
            {
                case Rune::DireBats:
                    return Tune("firebats_dire_ticks_per_attack");
                case Rune::HungryBats:
                    return Tune("firebats_hungry_ticks_per_attack");
                case Rune::CloudOfBats:
                    return Tune("firebats_cloud_ticks_per_attack");
                default:
                    return Tune("firebats_ticks_per_attack");
            }
        }

        // Whether the enemy is in the cone in front of the Witch Doctor and within its reach.
        bool InFront(Player* player, Unit* enemy)
        {
            double const offset = std::remainder(player->GetAngle(enemy) - player->GetOrientation(), 2.0 * Pi);
            return player->GetExactDist(enemy) <= Tune("firebats_cone_yards") &&
                   InCone(offset, Tune("firebats_cone_degrees"));
        }

        // The enemies in the cone.
        std::vector<Unit*> Cone(Player* player, std::uint32_t spellId)
        {
            std::vector<Unit*> out;
            for (Unit* enemy : Combat::Enemies(player, spellId, player->GetPosition(), Tune("firebats_cone_yards")))
                if (InFront(player, enemy))
                    out.push_back(enemy);
            return out;
        }

        // One tick: its Mana, then its damage; false when the Mana is not there, which ends the channel.
        bool Tick(Player* player, Channel& channel)
        {
            std::uint32_t const spellId = channel.spellId;
            Rune const rune = RuneAt(spellId);
            double const ticks = TicksPerAttack(spellId);
            // "Vampire Bats: Firebats has an initial Mana cost ... but no longer has a channeling cost."
            double const cost =
                rune == Rune::VampireBats ? 0.0 : TickShare(Numbers::Num(BaseId(Skill), "cost_resource"), ticks);
            if (Resources::Get(player, Resources::Mana) < cost)
                return false;
            if (cost > 0)
                Resources::SpendUnits(player, Resources::Mana,
                                      int32(std::lround(Resources::ToUnits(Resources::Mana, cost))));
            unsigned struck = 0;
            switch (rune)
            {
                case Rune::HungryBats:
                {
                    // "Rapidly summon two bats that each seek out a nearby enemy": a bat a tick at a random enemy
                    // within the file's range.
                    auto const enemies =
                        Combat::Enemies(player, spellId, player->GetPosition(), Tune("firebats_hungry_range_yards"));
                    if (!enemies.empty())
                        struck += Combat::Strike(player, enemies[PickAt(frand(0.0f, 1.0f), enemies.size())], spellId,
                                                 TickShare(Numbers::Num(spellId, "damage_pct"), ticks))
                                      ? 1
                                      : 0;
                    break;
                }
                case Rune::PlagueBats:
                {
                    // "Damage is slow at first, but can increase over time to a maximum of {damage_pct}": an enemy hit
                    // tick after tick carries more stacks.
                    double const lasts = Tune("firebats_plague_stack_ticks") * Tune("firebats_plague_max_stacks") *
                                         1000.0 * TickSeconds(ticks, Combat::AttacksPerSecond(player, spellId));
                    for (Unit* enemy : Cone(player, spellId))
                    {
                        Plague& plague = channel.plagued[enemy->GetGUID().GetRawValue()];
                        plague.stacks = PlagueStacks(plague.stacks, double(Now() - plague.lastMs), lasts,
                                                     unsigned(Tune("firebats_plague_max_stacks")));
                        plague.lastMs = Now();
                        struck += Combat::Strike(player, enemy, spellId,
                                                 TickShare(PlaguePct(Numbers::Num(spellId, "damage_pct"), plague.stacks,
                                                                     unsigned(Tune("firebats_plague_max_stacks"))),
                                                           ticks))
                                      ? 1
                                      : 0;
                    }
                    break;
                }
                case Rune::CloudOfBats:
                {
                    // "a swirl of bats that damage nearby enemies for {damage_pct:base} ... increases every second":
                    // round the Witch Doctor.
                    double const pct = TickShare(Numbers::Num(spellId, "damage_pct", "base"), ticks) *
                                       CloudFactor(channel.seconds / 1000.0, Tune("firebats_cloud_stack_bonus"),
                                                   unsigned(Tune("firebats_cloud_max_stacks")));
                    for (Unit* enemy :
                         Combat::Enemies(player, spellId, player->GetPosition(), Tune("firebats_cloud_area_yards")))
                        struck += Combat::Strike(player, enemy, spellId, pct) ? 1 : 0;
                    break;
                }
                default:
                    for (Unit* enemy : Cone(player, spellId))
                        struck += Combat::Strike(player, enemy, spellId,
                                                 TickShare(Numbers::Num(spellId, "damage_pct"), ticks))
                                      ? 1
                                      : 0;
                    break;
            }
            if (struck)
                Combat::Connected(player, spellId, struck);
            return true;
        }

        class Channels final : public PlayerScript
        {
        public:
            Channels()
                : PlayerScript("dc_witch_doctor_firebats",
                               {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_MAP_CHANGED})
            {
            }

            void OnPlayerUpdate(Player* player, uint32 diff) override
            {
                Channel channel;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    auto found = channels.find(player->GetGUID().GetRawValue());
                    if (found == channels.end())
                        return;
                    channel = found->second;
                }
                // The player let go - cast something else, was interrupted - or died: the core ended the channel.
                Spell* current = player->GetCurrentSpell(CURRENT_CHANNELED_SPELL);
                if (!player->IsAlive() || !current || current->GetSpellInfo()->Id != channel.spellId)
                {
                    Stop(player);
                    return;
                }
                channel.seconds += diff;
                double const interval =
                    TickSeconds(TicksPerAttack(channel.spellId), Combat::AttacksPerSecond(player, channel.spellId)) *
                    1000.0;
                for (unsigned i = 0, due = Due(channel.clock, diff, interval); i < due; ++i)
                    if (!Tick(player, channel))
                    {
                        // Out of Mana: the channel is over.
                        player->InterruptSpell(CURRENT_CHANNELED_SPELL);
                        Stop(player);
                        return;
                    }
                std::lock_guard<std::mutex> guard(mutex);
                if (auto found = channels.find(player->GetGUID().GetRawValue()); found != channels.end())
                    found->second = channel;
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
                channels.erase(player->GetGUID().GetRawValue());
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

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const&)
    {
        if (!player || !Is(spellId))
            return;
        // "Vampire Bats: Firebats has an initial Mana cost of {cost_resource} mana": the record carries no cost, the
        // start is paid here.
        if (RuneAt(spellId) == Rune::VampireBats)
        {
            double const initial = Numbers::Num(spellId, "cost_resource");
            if (Resources::Get(player, Resources::Mana) < initial)
            {
                player->InterruptSpell(CURRENT_CHANNELED_SPELL);
                return;
            }
            Resources::SpendUnits(player, Resources::Mana,
                                  int32(std::lround(Resources::ToUnits(Resources::Mana, initial))));
        }
        Channel channel;
        channel.spellId = spellId;
        // The first tick falls with the cast.
        if (!Tick(player, channel))
        {
            player->InterruptSpell(CURRENT_CHANNELED_SPELL);
            return;
        }
        std::lock_guard<std::mutex> guard(mutex);
        channels[player->GetGUID().GetRawValue()] = channel;
    }

    void RegisterScripts()
    {
        new Channels();
    }
} // namespace DC::Combat::WitchDoctor::Firebats
