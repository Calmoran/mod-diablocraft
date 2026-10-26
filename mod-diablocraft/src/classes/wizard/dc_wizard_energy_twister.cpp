#include "dc_wizard_energy_twister.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_movement_effects.h"
#include "../../common/dc_tunables.h"
#include "MotionMaster.h"
#include "ObjectAccessor.h"
#include "TemporarySummon.h"
#include <algorithm>

namespace DC::Combat::Wizard::EnergyTwister
{
    using namespace Shared;

    void Begin(Player* player, State& state, std::uint32_t spellId, Unit* explicitTarget)
    {
        // Storm Chaser: "Casting a Signature spell releases all Lightning
        // Charges as a bolt of Lightning that deals {damage_pct} ... per
        // Lightning Charge".
        if (Signature(spellId) && state.stormCharges)
            for (Row const& row : Shells::Abilities)
                if (IsSkill(row.id, "Energy Twister") && IsRune(row.id, "Storm Chaser"))
                {
                    Unit* target =
                        explicitTarget && player->IsValidAttackTarget(explicitTarget) ? explicitTarget : nullptr;
                    double const pct = Num(row.id, "damage_pct") * state.stormCharges;
                    state.stormCharges = 0;
                    if (!target)
                        break;
                    ObjectGuid const guid = target->GetGUID();
                    uint32 const id = row.id;
                    After(player, 0,
                          [guid, id, pct](Player* p)
                          {
                              if (Unit* u = Find(p, guid))
                                  Combat::Strike(p, u, id, pct);
                          });
                    break;
                }
    }

    void Cast(State& state, uint32 id)
    {
        // "Each cast of Energy Twister grants you a Lightning Charge. You
        // can store up to {charge_count}".
        if (IsRune(id, "Storm Chaser"))
            state.stormCharges = std::min(state.stormCharges + 1, unsigned(Num(id, "charge_count")));
    }

    // No stock carrier moves (a missile hits once, a DynamicObject stays put), so the carrier is the stock World Invisible
    // Trigger (dc_shatter.cpp's) wearing the Crone's cyclone model, sent along the path leg by leg, and the damage is the module's:
    // a tick every interval_seconds, the first at once, on the enemies within the hit radius of where the path puts the twister,
    // each tick damage_pct / ticks as the stationary ground deals it. The number is the base skill's: Raging Storm's damage_pct
    // is the merged tornado's and Storm Chaser's its bolt's.
    // Constant (12999, 14501, 35): the trigger template, creature_template_model's display of Cyclone (The Crone) (18412), the
    // faction friendly to everyone (12999 ships hostile, dc_shatter.cpp); identifiers.
    namespace
    {
        constexpr uint32 TWISTER_CARRIER_ENTRY = 12999;
        constexpr uint32 TWISTER_DISPLAY = 14501;
        constexpr uint32 TWISTER_FACTION = 35;

        LiveTwister* TwisterOf(Player* player, unsigned serial)
        {
            for (LiveTwister& twister : StateOf(player).twisters)
                if (twister.serial == serial)
                    return &twister;
            return nullptr;
        }

        Position TwisterGround(Player* player, LiveTwister const& twister, Twister::Point at)
        {
            float x = float(at.x), y = float(at.y), z = twister.z;
            player->UpdateGroundPositionZ(x, y, z);
            return Position(x, y, z);
        }

        void MoveTwister(Player* player, unsigned serial, std::size_t leg)
        {
            std::lock_guard<std::recursive_mutex> guard(mutex);
            LiveTwister const* twister = TwisterOf(player, serial);
            if (!twister || twister->speed <= 0 || leg + 1 >= twister->path.size())
                return;
            if (Creature* carrier = ObjectAccessor::GetCreature(*player, twister->carrier))
            {
                Position const to = TwisterGround(player, *twister, twister->path[leg + 1]);
                carrier->GetMotionMaster()->MovePoint(0, to.GetPositionX(), to.GetPositionY(), to.GetPositionZ(),
                                                      FORCED_MOVEMENT_NONE, float(twister->speed), 0.0f, false);
            }
        }

        void TwisterTick(Player* player, unsigned serial, double t)
        {
            uint32 id = 0;
            double radius = 0, pct = 0;
            Position at;
            {
                std::lock_guard<std::recursive_mutex> guard(mutex);
                LiveTwister const* twister = TwisterOf(player, serial);
                if (!twister)
                    return;
                id = twister->id, radius = twister->radius, pct = twister->tickPct;
                at = TwisterGround(player, *twister, Twister::At(twister->path, twister->turnSeconds, twister->lifeSeconds, t));
            }
            Combat::StrikeArea(player, id, at, radius, pct, true);
        }

        // N-LESSER (Ranslor's Folly): a pull. Every lesser enemy (Combat::IsLesser) within `yards` of where the path puts the twister is drawn to it
        // (Abilities::Pull), unless one of the wearer's twisters pulled it in the last `cooldown` seconds (ItemPower::LesserPull: the reach and the per-target clock).
        // The stamps live in the player's state, so any twister of the wearer counts; one older than the cooldown is dropped here.
        void PullAt(Player* player, uint32 id, Position const& at, double yards, double cooldown)
        {
            if (!player->IsAlive())
                return;
            std::vector<Unit*> pulled;
            for (Unit* enemy : Combat::Enemies(player, id, at, yards))
            {
                std::uint32_t const now = getMSTime();
                std::lock_guard<std::recursive_mutex> guard(mutex);
                auto& stamps = StateOf(player).twisterPulled;
                std::uint64_t const guid = enemy->GetGUID().GetRawValue();
                auto const last = stamps.find(guid);
                if (!ItemPower::LesserPull(Combat::IsLesser(enemy), enemy->GetExactDist(&at), yards, now, last != stamps.end(),
                                           last != stamps.end() ? last->second : 0, cooldown))
                    continue;
                std::erase_if(stamps, [now, cooldown](auto const& stamp) { return now - stamp.second >= cooldown * 1000.0; });
                stamps[guid] = now;
                pulled.push_back(enemy);
            }
            for (Unit* enemy : pulled)
                Combat::Abilities::Pull(enemy, at);
        }

        // The pull of a twister that wanders: where the path puts it at `t`.
        void TwisterPull(Player* player, unsigned serial, double t, double yards, double cooldown)
        {
            uint32 id = 0;
            Position at;
            {
                std::lock_guard<std::recursive_mutex> guard(mutex);
                LiveTwister const* twister = TwisterOf(player, serial);
                if (!twister)
                    return;
                id = twister->id;
                at = TwisterGround(player, *twister, Twister::At(twister->path, twister->turnSeconds, twister->lifeSeconds, t));
            }
            PullAt(player, id, at, yards, cooldown);
        }
    } // namespace

    bool Wanders(uint32 id)
    {
        return IsSkill(id, "Energy Twister") && !IsRune(id, "Wicked Wind");
    }

    void Stay(Player* player, uint32 id, Position const& center)
    {
        // Wicked Wind's twister spins in place on the generic ground: its damage is the ground's, its pull is the same rule from the cast point, for the
        // ground's life.
        double const yards = ItemPowers::SkillSetTo(player, "Energy Twister", "twister_pull_yards", 0);
        double const every = ItemPowers::SkillSetTo(player, "Energy Twister", "twister_pull_seconds", 0);
        double const cooldown = ItemPowers::SkillSetTo(player, "Energy Twister", "twister_pull_target_cooldown_seconds", 0);
        std::size_t const pulls = yards > 0 ? Twister::Ticks(Num(id, "dot_duration_seconds"), every) : 0;
        for (std::size_t k = 0; k < pulls; ++k)
            After(player, k * every, [id, center, yards, cooldown](Player* p) { PullAt(p, id, center, yards, cooldown); });
    }

    void Start(Player* player, uint32 id, Position const& center)
    {
        LiveTwister twister;
        twister.id = id;
        twister.lifeSeconds = Num(id, "dot_duration_seconds");
        twister.turnSeconds = DC::Tunables::Get("wizard", "energy_twister_turn_interval_seconds");
        twister.speed = DC::Tunables::Get("wizard", "energy_twister_speed_yards_per_second");
        twister.radius = DC::Tunables::Get("wizard", "energy_twister_hit_radius_yards");
        double const interval = Num(id, "interval_seconds");
        std::size_t const ticks = Twister::Ticks(twister.lifeSeconds, interval);
        twister.tickPct = Twister::TickPct(Num(BaseOf("Energy Twister"), "damage_pct"), ticks);
        twister.z = center.GetPositionZ();
        twister.raging = IsRune(id, "Raging Storm") || ItemPowers::GrantsRune(player, "Energy Twister", "Raging Storm");
        // "Travels in a straight path" is a turn limit of 0.
        bool const straight = ItemPowers::SkillSetTo(player, "Energy Twister", "straight_path", 0) > 0;
        double const limit = straight ? 0 : DC::Tunables::Get("wizard", "energy_twister_turn_limit_degrees");
        Twister::Point const start{center.GetPositionX(), center.GetPositionY()};
        double const heading =
            Twister::Heading({player->GetPositionX(), player->GetPositionY()}, player->GetOrientation(), start);
        std::vector<double> rolls;
        for (std::size_t i = 0; i < 2 * Twister::Legs(twister.lifeSeconds, twister.turnSeconds); ++i)
            rolls.push_back(std::uniform_real_distribution<double>(0, 1)(Engine()));
        twister.path = Twister::Path(start, heading, twister.speed, twister.lifeSeconds, twister.turnSeconds, limit, rolls);
        if (TempSummon* carrier =
                player->SummonCreature(TWISTER_CARRIER_ENTRY, center.GetPositionX(), center.GetPositionY(), center.GetPositionZ(),
                                       Position::NormalizeOrientation(float(heading)), TEMPSUMMON_TIMED_DESPAWN,
                                       uint32(twister.lifeSeconds * 1000)))
        {
            carrier->SetDisplayId(TWISTER_DISPLAY);
            carrier->SetFaction(TWISTER_FACTION);
            carrier->SetImmuneToAll(true);
            twister.carrier = carrier->GetGUID();
        }
        unsigned serial = 0;
        std::size_t const legs = twister.path.size() - 1;
        double const life = twister.lifeSeconds, turn = twister.turnSeconds > 0 ? twister.turnSeconds : life;
        {
            std::lock_guard<std::recursive_mutex> guard(mutex);
            State& state = StateOf(player);
            serial = twister.serial = ++state.twisterSerial;
            state.twisters.push_back(std::move(twister));
        }
        for (std::size_t leg = 0; leg < legs; ++leg)
            After(player, leg * turn, [serial, leg](Player* p) { MoveTwister(p, serial, leg); });
        for (std::size_t k = 0; k < ticks; ++k)
            After(player, k * interval, [serial, t = k * interval](Player* p) { TwisterTick(p, serial, t); });
        // Ranslor's Folly: the pull, a tick of its own, the first as the twister appears.
        double const pullYards = ItemPowers::SkillSetTo(player, "Energy Twister", "twister_pull_yards", 0);
        double const pullEvery = ItemPowers::SkillSetTo(player, "Energy Twister", "twister_pull_seconds", 0);
        double const pullCooldown = ItemPowers::SkillSetTo(player, "Energy Twister", "twister_pull_target_cooldown_seconds", 0);
        std::size_t const pulls = pullYards > 0 ? Twister::Ticks(life, pullEvery) : 0;
        for (std::size_t k = 0; k < pulls; ++k)
            After(player, k * pullEvery,
                  [serial, t = k * pullEvery, pullYards, pullCooldown](Player* p) { TwisterPull(p, serial, t, pullYards, pullCooldown); });
        After(player, life,
              [serial](Player* p)
              {
                  std::lock_guard<std::recursive_mutex> guard(mutex);
                  auto& list = StateOf(p).twisters;
                  std::erase_if(list, [serial](LiveTwister const& twister) { return twister.serial == serial; });
              });
    }
} // namespace DC::Combat::Wizard::EnergyTwister
