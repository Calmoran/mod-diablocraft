#pragma once
// Elemental Shield's rules that need no core type, header-only so tests/shaman_elemental_shield compiles this exact
// code: which rune is which, the charges a hit spends, how often the shield strikes back, the charges a Primary hit
// adds, and the pool a broken Stoneskin leaves. The production half is dc_shaman_elemental_shield.cpp, called from
// dc_shaman.cpp.
#include <algorithm>
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Shaman::ElementalShield
{
    enum class Rune
    {
        None,
        LightningShield, // Lightning; each charge used generates Maelstrom; Primary hits add charges
        Stoneskin,       // Physical; more charges, Armor while one remains, an absorb when the last breaks
        WaterShield,     // Cold; each charge used heals, restores Maelstrom and Chills the attacker
        FlameShield,     // Fire; enemies nearby burn; a charge used strikes the attacker and the enemies around it
        TotemicWard      // the shield regains charges near a Totem of the Shaman's (waits on the Totems)
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Lightning Shield")
            return Rune::LightningShield;
        if (name == "Stoneskin")
            return Rune::Stoneskin;
        if (name == "Water Shield")
            return Rune::WaterShield;
        if (name == "Flame Shield")
            return Rune::FlameShield;
        if (name == "Totemic Ward")
            return Rune::TotemicWard;
        return Rune::None;
    }

    // The shield a Shaman wears. `stamp` tells one cast from the next, so the end of an old shield finds its own gone.
    struct Shield
    {
        std::uint32_t spellId = 0;
        Rune rune = Rune::None;
        unsigned charges = 0;
        std::uint64_t until = 0;      // ms: the shield is gone from this moment on
        std::uint64_t lastStrike = 0; // ms of the last strike back; 0: none yet
        bool struck = false;          // a strike back has happened (lastStrike is meaningful)
        std::uint64_t stamp = 0;
    };

    inline bool Active(Shield const& shield, std::uint64_t now)
    {
        return shield.spellId && shield.charges > 0 && shield.until > now;
    }

    // What one hit taken does to the shield.
    struct Spent
    {
        bool used = false;   // a charge was spent
        bool strike = false; // the shield strikes the attacker (at most once every `interval` ms)
        bool broke = false;  // that was the last charge
    };

    inline Spent Hit(Shield& shield, std::uint64_t now, std::uint64_t intervalMs)
    {
        Spent spent;
        if (!Active(shield, now))
            return spent;
        spent.used = true;
        --shield.charges;
        spent.broke = shield.charges == 0;
        if (!shield.struck || now >= shield.lastStrike + intervalMs)
        {
            spent.strike = true;
            shield.struck = true;
            shield.lastStrike = now;
        }
        return spent;
    }

    // One charge more, up to `most`. True when it added one.
    inline bool AddCharge(Shield& shield, std::uint64_t now, unsigned most)
    {
        if (!Active(shield, now) || shield.charges >= most)
            return false;
        ++shield.charges;
        return true;
    }

    // "Lowers that hit's damage by {damage_reduction_pct}%".
    inline double Lowered(double damage, double reductionPct)
    {
        return damage * (1.0 - reductionPct / 100.0);
    }

    // What the Shaman's mitigation worked out for a hit and the shield has not paid yet. A swing can be mitigated and then miss,
    // be dodged or be blinded away, and the core mitigates before it rolls: only a hit that lands (the core's damage event, after the
    // roll, even when other absorbs took all of it) pays the charge. The note names the attacker and the game time it was made at,
    // so the note of a swing that never landed is not paid by a later hit.
    struct Pending
    {
        bool set = false;
        std::uint64_t attacker = 0;
        std::uint64_t at = 0;
        bool charge = false; // the hit spends a charge
    };

    inline void Note(Pending& pending, std::uint64_t attacker, std::uint64_t now, bool charge)
    {
        pending = {true, attacker, now, charge};
    }

    // A hit from `attacker` landed at `now`: the note made for it, once; nothing when there is none for this hit.
    inline std::optional<Pending> Claim(Pending& pending, std::uint64_t attacker, std::uint64_t now)
    {
        if (!pending.set || pending.attacker != attacker || pending.at != now)
            return std::nullopt;
        Pending const claimed = pending;
        pending = {};
        return claimed;
    }

    // Whether a roll of `roll` (0 to 100) adds a charge for a hit of `chancePct`.
    inline bool Rolled(double roll, double chancePct)
    {
        return roll < chancePct;
    }

    // A burn "N% weapon damage as Fire per second" in ticks of `tickSeconds`: the percent of one tick.
    inline double TickPct(double perSecondPct, double tickSeconds)
    {
        return perSecondPct * tickSeconds;
    }

    // The production half (dc_shaman_elemental_shield.cpp).
    bool Is(std::uint32_t spellId);
    // A cast of `spellId` began: the shield is put on, replacing the one worn.
    void Casting(Player* player, std::uint32_t spellId);
    // The damage a hit by `attacker` does to the Shaman once the shield has taken its part: lowered, the charge not yet paid (a swing
    // may still miss).
    double Reduce(Unit* victim, Unit* attacker, double damage);
    // A hit by `attacker` landed on `victim` for `damage`, which may be 0 when every point was absorbed (the core's damage event, after
    // every roll): the charge is paid, and Stoneskin's absorb is put on when the last one breaks.
    void Damaged(Unit* attacker, Unit* victim, std::uint32_t damage);
    // A hit of `spellId` landed on `target`: a Primary may add a charge to a Lightning Shield.
    void Landed(Player* player, std::uint32_t spellId);
    // The buff bar and the timers; called from the class's upkeep.
    void Upkeep(Player* player);
    void Forget(Player* player);
} // namespace DC::Combat::Shaman::ElementalShield
