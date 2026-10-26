// diablocraft-pre-beta-bugs-b items 1-3 on the production functions.
//
// dc_combat_conformance_extract.h is written by
// scripts/tests/combat/test_combat_conformance.py from dc_combat.cpp, dc_combat.h and
// dc_barbarian_primaries.cpp. Nothing below restates a gate or a formula: every verdict
// is what the module's own code returns. argv carries the playable WoW class
// ids read from the generated dc_class_map rows, then one WoW class id the
// map does not list.
#include "conformance_shim.h"
#include "dc_combat_conformance_extract.h"

#include <cstdlib>
#include <iostream>
#include <vector>

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

    struct Outcome
    {
        int32 miss = 500, dodge = 500, parry = 500, block = 500;
    };

    Outcome Roll(Unit const* attacker, Unit const* victim)
    {
        Outcome out;
        int32 a = 0, b = 0, c = 0, d = 0, e = 0;
        DC::Combat::AlwaysHit{}.OnBeforeRollMeleeOutcomeAgainst(attacker, victim, BASE_ATTACK, a, b, c, d, e, out.miss,
                                                                out.dodge, out.parry, out.block);
        return out;
    }

    bool Stock(Outcome const& out)
    {
        return out.miss == 500 && out.dodge == 500 && out.parry == 500 && out.block == 500;
    }
} // namespace

int main(int argc, char** argv)
{
    if (argc < 3)
    {
        std::cerr << "usage: conformance_harness <playable wow class id>... <stock wow class id>\n";
        return 2;
    }
    std::vector<uint32> playable;
    for (int i = 1; i < argc - 1; ++i)
        playable.push_back(uint32(std::strtoul(argv[i], nullptr, 10)));
    uint32 const stockClass = uint32(std::strtoul(argv[argc - 1], nullptr, 10));
    DC::Classes::playableClasses.insert(playable.begin(), playable.end());
    if (DC::Classes::playableClasses.count(stockClass) || playable.size() < 2)
    {
        std::cerr << "need two or more playable classes and one class outside the map\n";
        return 2;
    }

    Creature monster;
    uint64 guid = 1;

    // ---- items 1 and 2: every playable D3 class, never a named one ----------
    for (uint32 wowClass : playable)
    {
        std::string const who = "class " + std::to_string(wowClass);
        Player player(++guid, wowClass);
        WorldSession session(&player);

        // Item 1: the swing packet is dropped, other packets pass.
        Expect(!DC::Combat::NoAutoAttack{}.CanPacketReceive(&session, WorldPacket(CMSG_ATTACKSWING)),
               who + ": CMSG_ATTACKSWING reached the core");
        Expect(DC::Combat::NoAutoAttack{}.CanPacketReceive(&session, WorldPacket(CMSG_CAST_SPELL)),
               who + ": a spell packet was dropped");

        // Item 1: a swing started by another route is stopped.
        player.AddUnitState(UNIT_STATE_MELEE_ATTACKING);
        DC::Combat::NoAutoAttackUpdate{}.OnPlayerUpdate(&player, 100);
        Expect(!player.HasUnitState(UNIT_STATE_MELEE_ATTACKING) && player.stops == 1,
               who + ": a stray swing kept running");

        // Item 2: a creature's swing at this class gets the D3 outcome - no
        // miss, parry or WoW block - with Dodge only as the sheet supplies it.
        Outcome none = Roll(&monster, &player);
        Expect(none.miss == 0 && none.parry == 0 && none.block == 0 && none.dodge == 0,
               who + ": creature swing kept the native table (miss " + std::to_string(none.miss) + ", dodge " +
                   std::to_string(none.dodge) + ", parry " + std::to_string(none.parry) + ", block " +
                   std::to_string(none.block) + ")");
        DC::Combat::Abilities::dodge[player.GetGUID().GetRawValue()] = 12.5;
        Outcome dodging = Roll(&monster, &player);
        Expect(dodging.dodge == 1250 && dodging.miss == 0, who + ": the sheet's Dodge did not reach the roll");

        // Item 2, attacking side: this class's own swing sees no avoidance.
        Outcome out = Roll(&player, &monster);
        Expect(out.miss == 0 && out.parry == 0 && out.block == 0 && out.dodge == 0,
               who + ": its swing at a creature kept the native table");
    }

    // ---- a class outside the map keeps stock combat --------------------------
    {
        Player stock(++guid, stockClass);
        WorldSession session(&stock);
        Expect(DC::Combat::NoAutoAttack{}.CanPacketReceive(&session, WorldPacket(CMSG_ATTACKSWING)),
               "stock class: CMSG_ATTACKSWING was dropped");
        stock.AddUnitState(UNIT_STATE_MELEE_ATTACKING);
        DC::Combat::NoAutoAttackUpdate{}.OnPlayerUpdate(&stock, 100);
        Expect(stock.HasUnitState(UNIT_STATE_MELEE_ATTACKING) && stock.stops == 0,
               "stock class: its auto-attack was stopped");
        DC::Combat::Abilities::dodge[stock.GetGUID().GetRawValue()] = 12.5;
        Expect(Stock(Roll(&monster, &stock)), "stock class: a creature's swing lost the native table");
        Expect(Stock(Roll(&stock, &monster)), "stock class: its swing lost the native table");
        WorldSession empty(nullptr);
        Expect(DC::Combat::NoAutoAttack{}.CanPacketReceive(&empty, WorldPacket(CMSG_ATTACKSWING)),
               "a session with no player dropped the packet");
        Expect(Stock(Roll(&monster, &monster)), "creature on creature lost the native table");
    }

    // ---- item 3: each hand's own recovery -----------------------------------
    {
        uint32 const primary = 81000;
        DC::Combat::PrimaryData::primaries.insert(primary);
        Player barbarian(++guid, playable.front());
        // Unequal speeds, as a 1.4 APS sword with a 1.2 APS axe off-hand.
        DC::Stats::sheets[barbarian.GetGUID().GetRawValue()] = StatSheet{1.4, 1.2};
        Caster caster{&barbarian};

        auto finish = [&](bool off, bool triggered)
        {
            DC::Combat::sent.clear();
            DC::Combat::Primaries::Script script;
            script.caster = caster;
            script.spellId = primary;
            script.spell.triggered = triggered;
            script.identity = &script.spell;
            DC::Combat::Primaries::casts[&script.spell] = Cast{off};
            script.Finish();
            DC::Combat::Primaries::casts.erase(&script.spell);
            auto found = DC::Combat::sent.find(primary);
            return found == DC::Combat::sent.end() ? -1 : int64_t(found->second);
        };

        int64_t const mainMs = finish(false, false), offMs = finish(true, false);
        Expect(mainMs == 715, "main hand recovery " + std::to_string(mainMs) + " ms, want ceil(1000/1.4) = 715");
        Expect(offMs == 834, "off-hand recovery " + std::to_string(offMs) + " ms, want ceil(1000/1.2) = 834");
        Expect(finish(true, true) == -1, "a triggered cast installed a recovery");

        // The skill's own speed rule (Frenzy) applies to the hand that swung.
        DC::Combat::Primaries::speedRule = 1.5;
        int64_t const frenzyOff = finish(true, false);
        Expect(frenzyOff == 556, "off-hand recovery under the speed rule " + std::to_string(frenzyOff) +
                                     " ms, want ceil(1000/1.8) = 556");
        DC::Combat::Primaries::speedRule = 1.0;

        // One hand only: the off-hand request falls back to the main hand.
        DC::Stats::sheets[barbarian.GetGUID().GetRawValue()] = StatSheet{1.4, 0};
        Expect(finish(true, false) == 715, "a one-handed off-hand request did not use the main hand");

        // The readout path keeps the main hand when no hand is named.
        DC::Stats::sheets[barbarian.GetGUID().GetRawValue()] = StatSheet{1.4, 1.2};
        Expect(DC::Combat::SkillCooldownMilliseconds(&barbarian, primary) == 715,
               "the default hand is not the main hand");
    }

    // ---- #72: a Wizard shell's cooldown is read like a Barbarian's ------------
    {
        Player wizard(++guid, playable.back());
        uint32 const teleport = 83111;
        uint32 const ms = DC::Combat::SkillCooldownMilliseconds(&wizard, teleport);
        Expect(ms == 16000, "Wizard Teleport cooldown " + std::to_string(ms) + " ms, want the record's 16000");
        Expect(DC::Combat::SkillCooldownMilliseconds(&wizard, 83999) == 0, "an id no class owns has a cooldown");
    }

    if (failures)
        return 1;
    std::cout << "ok\n";
    return 0;
}
