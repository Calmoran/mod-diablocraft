/*
 * GitHub #74: a Rend tick records its pre-crit hit receipt before the core
 * absorbs and delivers the tick, and the one consumer, the rift-elite OnDamage,
 * never takes it when the tick is absorbed whole (it returns on zero damage).
 * The receipt then waits for the next hit on that elite.
 *
 * REAL here, cut out of the module's own files by scripts/tests/classes/test_rend_receipt.py
 * and not copied: Hit and PreCritHit, the receipt store with
 * RecordPreCritHit / ClearPreCritHit / ConsumePreCritHit, VictimAdjustedTotal,
 * the Rend tick (FinalTick), RendPeriodicProvider with its hook list, and the
 * rift-elite OnDamage.
 *
 * DOUBLES, which prove nothing about the core: the units, the aura, the hook
 * gate of UnitScript, the shield, and EliteStruck, which stands for production's
 * first act on a struck elite, taking the receipt once (the Python test pins
 * that line). Unit::DealDamage's script step is modelled from the pinned core
 * text: every script that listed UNITHOOK_ON_DAMAGE is called with the damage
 * left after absorb, in registration order. The module does not control that
 * order, so every case runs both.
 *
 * Not covered: the native absorb itself, patch 0016's call into the provider
 * and the live Reflects Damage cast; docs/test-diablocraft-rend-receipt.md says
 * what a GM can check.
 */

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <limits>
#include <optional>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

using uint16 = std::uint16_t;
using uint32 = std::uint32_t;
using uint64 = std::uint64_t;

#define LOG_DEBUG(...) ((void) 0)

struct ObjectGuid
{
    uint64 raw = 0;
    uint64 GetRawValue() const
    {
        return raw;
    }
    std::string ToString() const
    {
        return std::to_string(raw);
    }
};

class Player;
class Creature;
class Unit
{
public:
    explicit Unit(uint64 guid)
        : guid_{guid}
    {
    }
    virtual ~Unit() = default;
    ObjectGuid GetGUID() const
    {
        return guid_;
    }
    virtual Player* ToPlayer()
    {
        return nullptr;
    }
    virtual Creature* ToCreature()
    {
        return nullptr;
    }

private:
    ObjectGuid guid_;
};

class Player final : public Unit
{
public:
    using Unit::Unit;
    Player* ToPlayer() override
    {
        return this;
    }
    std::string GetName() const
    {
        return "fixture";
    }
};

struct EliteState
{
};

class Creature final : public Unit
{
public:
    using Unit::Unit;
    Creature* ToCreature() override
    {
        return this;
    }
    bool IsAlive() const
    {
        return alive;
    }
    bool alive = true;
    // A rift elite carries its state in CustomData; any other creature has none.
    struct Data
    {
        EliteState* state = nullptr;
        template<class T>
        T* Get(char const*) const
        {
            return state;
        }
    } CustomData;
};

enum UnitHook : uint16
{
    UNITHOOK_PROVIDE_FINAL_PERIODIC_DAMAGE,
    UNITHOOK_ON_DAMAGE
};

class AuraEffect;
// the core's saturating cast (Unit.h), which the provider's 64-bit handover uses
inline uint32 LifeToUInt32(uint64 value) { return value > 0xFFFFFFFFull ? 0xFFFFFFFFu : static_cast<uint32>(value); }

class UnitScript
{
public:
    UnitScript(char const*, bool, std::vector<uint16> hooks)
        : hooks_(std::move(hooks))
    {
    }
    virtual ~UnitScript() = default;
    virtual bool ProvideFinalPeriodicDamage(AuraEffect const*, Unit*, Unit*, uint64&, bool&)
    {
        return false;
    }
    virtual void OnDamage(Unit*, Unit*, uint32&) {}
    // The core calls a hook only on the scripts that listed it
    // (ScriptRegistry<UnitScript>::EnabledHooks).
    bool Enabled(uint16 hook) const
    {
        return std::find(hooks_.begin(), hooks_.end(), hook) != hooks_.end();
    }

private:
    std::vector<uint16> hooks_;
};

class Aura
{
public:
    template<class T>
    T* GetScript(char const*) const
    {
        return static_cast<T*>(script);
    }
    void* script = nullptr;
};

class AuraEffect
{
public:
    uint32 GetId() const
    {
        return id;
    }
    uint32 GetTickNumber() const
    {
        return tick;
    }
    uint32 GetTotalTicks() const
    {
        return totalTicks;
    }
    Aura* GetBase() const
    {
        return base;
    }
    uint32 id = 0, tick = 0, totalTicks = 5;
    Aura* base = nullptr;
};

// FinalTick's tick arithmetic (the module's own, pure).
#include "../../src/combat/dc_item_power_math.h"
// The victim-debuff bonuses VictimAdjustedTotal adds; a fixture elite has none. (Hit carries the damage buckets' Factors.)
#include "../../src/combat/dc_damage_buckets.h"
namespace DC::Combat
{
    namespace Primaries
    {
        inline double TargetBonus(Unit*)
        {
            return 0;
        }
    } // namespace Primaries
    namespace Abilities
    {
        inline double TargetBonus(Unit*)
        {
            return 0;
        }
    } // namespace Abilities
    namespace Wizard
    {
        inline double TargetBonus(Player*, Unit*, unsigned)
        {
            return 0;
        }
        inline double TargetFactor(Player*, Unit*)
        {
            return 1;
        }
    } // namespace Wizard
    namespace Monk
    {
        inline double TargetBonus(Player*, Unit*)
        {
            return 0;
        }
    } // namespace Monk
    namespace GemPowers
    {
        inline double TargetBonus(Unit*)
        {
            return 0;
        }
    } // namespace GemPowers
} // namespace DC::Combat

// The producers' one conversion (src/combat/dc_exact_damage.h) is the real header; the GM's dev multiplier is off in this harness.
#include "../../src/combat/dc_exact_damage.h"
namespace DC::Combat
{
    inline double DevBoost(Unit const*, double amount)
    {
        return amount;
    }
} // namespace DC::Combat

void EliteStruck(Creature*, EliteState*, Player*, uint32&);

#include "dc_rend_receipt_extract.h"

namespace
{
    unsigned failures = 0;

    void Expect(bool condition, std::string const& what)
    {
        if (!condition)
        {
            std::cerr << "FAIL: " << what << "\n";
            ++failures;
        }
    }

    // What the last struck elite took from the receipt store, and how often
    // the consumer ran at all.
    std::optional<DC::Combat::PreCritHit> taken;
    int strikes = 0;

    using DC::Combat::ConsumePreCritHit;

    enum class Order
    {
        ProviderFirst,
        ConsumerFirst
    };

    struct Fixture
    {
        Player player{1}, other{2};
        Creature elite{100}, monster{101};
        EliteState state;
        DC::Combat::dc_rend_bleed bleed;
        Aura aura;
        AuraEffect effect;
        DC::Combat::RendPeriodicProvider provider;
        EliteScript consumer;

        Fixture()
        {
            elite.CustomData.state = &state;
            bleed.valid = true;
            bleed.baseTicks = 5;
            bleed.stacks = {{1000, 5, 5, 5, 0}}; // one bleed of the aura's own length
            bleed.snapshot.total = 1000; // the whole bleed; each tick carries its share
            bleed.snapshot.crit = 2.0;   // so a tick's pre-crit amount is half its damage
            bleed.snapshot.school = 1;
            aura.script = &bleed;
            effect.id = DC::Combat::REND_BLEED_FIRST;
            effect.base = &aura;
            // The receipt store is process-wide: start every case with nothing pending.
            DC::Combat::ClearPreCritHit(&player);
            DC::Combat::ClearPreCritHit(&other);
            taken.reset();
            strikes = 0;
        }

        // Unit::DealDamage's script step: sScriptMgr->OnDamage(attacker, victim, damage).
        void DealDamage(Order order, Unit* attacker, Unit* victim, uint32 damage)
        {
            UnitScript* scripts[2] = {&provider, &consumer};
            if (order == Order::ConsumerFirst)
                std::swap(scripts[0], scripts[1]);
            for (UnitScript* script : scripts)
                if (script->Enabled(UNITHOOK_ON_DAMAGE))
                    script->OnDamage(attacker, victim, damage);
        }

        // AuraEffect::HandlePeriodicDamageAurasTick for a provided tick: the
        // provider hook, then the target's shield takes what it holds, then
        // DealDamage runs the scripts with what is left. Returns what is left.
        uint32 Tick(Order order, uint32 number, uint32 shield)
        {
            effect.tick = number;
            uint64 damage = 0;
            bool critical = false;
            bool const claimed = provider.ProvideFinalPeriodicDamage(&effect, &player, &elite, damage, critical);
            Expect(claimed && damage > 0, "the provider did not claim a Rend tick with damage");
            uint32 const left = static_cast<uint32>(damage - std::min<uint64>(damage, shield));
            DealDamage(order, &player, &elite, left);
            return left;
        }
    };
} // namespace

void EliteStruck(Creature* elite, EliteState*, Player* player, uint32&)
{
    taken = DC::Combat::ConsumePreCritHit(player, elite);
    ++strikes;
}

int main()
{
    uint32 const everything = std::numeric_limits<uint32>::max();
    for (Order order : {Order::ProviderFirst, Order::ConsumerFirst})
    {
        std::string const where =
            order == Order::ProviderFirst ? " (provider's hook first)" : " (consumer's hook first)";

        // A. The bug: a tick the shield swallows whole must not leave its
        // receipt for the next hit on that elite.
        {
            Fixture f;
            uint32 const left = f.Tick(order, 1, everything);
            Expect(left == 0, "A: the shield did not swallow the tick" + where);
            Expect(strikes == 0, "A: the consumer ran for a zero-damage event; its early return is gone" + where);
            Expect(!ConsumePreCritHit(&f.player, &f.elite),
                   "A: a fully absorbed tick left its receipt for the next hit" + where);
        }

        // A2. The same, from the next hit's side: one that records no receipt
        // of its own (an unrelated tick, a native hit) takes nothing stale.
        {
            Fixture f;
            f.Tick(order, 1, everything);
            f.DealDamage(order, &f.player, &f.elite, 500);
            Expect(strikes == 1 && !taken, "A2: the next hit took the absorbed tick's receipt" + where);
        }

        // B. A tick that lands: the consumer takes its receipt once, with the
        // tick's own pre-crit amount and school, and nothing is left after.
        {
            Fixture f;
            uint32 const left = f.Tick(order, 1, 0);
            Expect(left > 0 && strikes == 1 && taken.has_value(),
                   "B: a landed tick's receipt did not reach the consumer" + where);
            if (taken)
                Expect(taken->damage * 2.0 == double(left) && taken->school == 1,
                       "B: the receipt is not the tick's pre-crit amount and school" + where);
            Expect(!ConsumePreCritHit(&f.player, &f.elite), "B: a taken receipt was still there" + where);
        }

        // C. A tick the shield only dents still lands, and its receipt is the
        // tick's whole pre-crit amount, not what the shield let through.
        {
            uint32 const full = Fixture{}.Tick(order, 1, 0);
            Fixture f;
            uint32 const left = f.Tick(order, 1, full / 2);
            Expect(left > 0 && left < full, "C: the shield did not dent the tick" + where);
            Expect(strikes == 1 && taken.has_value() && taken->damage * 2.0 == double(full),
                   "C: a partly absorbed tick did not hand over its receipt" + where);
        }

        // D. Only the tick's own attacker loses a receipt: another player's
        // pending one survives.
        {
            Fixture f;
            DC::Combat::RecordPreCritHit(&f.other, &f.elite, 777, 2);
            f.Tick(order, 1, everything);
            auto const theirs = ConsumePreCritHit(&f.other, &f.elite);
            Expect(theirs && theirs->damage == 777 && theirs->school == 2,
                   "D: an absorbed tick cleared another player's receipt" + where);
        }

        // E. Zero damage from a monster, or from no one, is not a player's tick.
        {
            Fixture f;
            DC::Combat::RecordPreCritHit(&f.player, &f.elite, 321, 1);
            f.DealDamage(order, &f.monster, &f.player, 0);
            f.DealDamage(order, nullptr, &f.elite, 0);
            Expect(ConsumePreCritHit(&f.player, &f.elite).has_value(),
                   "E: a zero-damage event by a non-player cleared a player's receipt" + where);
        }
    }

    // G. A bleed a power lengthened (Wrath of the Wastes 2-piece): 15 ticks of the same size, three times the total, and no
    // tick past its aura's last pays nothing it should have.
    {
        Fixture f;
        f.effect.totalTicks = 15;
        f.bleed.stacks = {{1000, 5, 15, 15, 0}};
        uint64 paid = 0;
        for (uint32 tick = 1; tick <= 16; ++tick)
        {
            uint64 damage = 0;
            bool critical = false;
            f.effect.tick = tick;
            f.provider.ProvideFinalPeriodicDamage(&f.effect, &f.player, &f.elite, damage, critical);
            Expect(tick > 15 ? damage == 0 : damage == 200, "G: a 15-tick Rend pays 200 a tick and nothing after its last");
            paid += damage;
        }
        Expect(paid == 3000, "G: a bleed three times as long pays three times the total");
    }

    // F. 64-bit Life: a tick of 2^32 or more reaches the core whole, with nothing left over for a hook to find.
    {
        Fixture f;
        f.bleed.snapshot.total = 5e10; // tick 1 carries a fifth: 1e10
        f.bleed.stacks = {{5e10, 5, 5, 5, 0}};
        uint64 damage = 0;
        bool critical = false;
        f.effect.tick = 1;
        f.provider.ProvideFinalPeriodicDamage(&f.effect, &f.player, &f.elite, damage, critical);
        Expect(damage == 10000000000ull, "F: a tick of 1e10 did not reach the core whole");
        Fixture g;
        uint64 small = 0;
        bool smallCritical = false;
        g.effect.tick = 1;
        g.provider.ProvideFinalPeriodicDamage(&g.effect, &g.player, &g.elite, small, smallCritical);
        Expect(small == 200, "F: an ordinary tick of 200 changed on the way");
    }

    if (failures)
        return 1;
    std::cout << "ok\n";
    return 0;
}
