"""The shared charm's master: whose charm a monster is under, and what the rifts do with it (diablocraft-osikc).

A monster charmed through the shared charm sits under its own invisible holder, not under the player, so the core's
Player::GetCharm and Unit::GetCharmer name the holder. The rifts read both: the pack attacks a charmed monster as an
aggro actor beside the players (ActorsOf, monsters/dc_monster_ai.cpp), and a charmed monster's kill is its master's rift
kill (RiftCharmKills, rifts/dc_rift_quests.cpp).

This cuts the production functions out of the three .cpp files (MasterOf, CharmedBy and the registry they read, ActorsOf,
RiftCharmKills::OnUnitDeath) and compiles them against doubles of the core types, so what is tested is what ships:

  * the player behind a holder is the master; the core's own charm (a player charmer) is too; a holder summoned by a
    monster, a charm by another creature and an uncharmed monster are nobody's;
  * CharmedBy returns the monsters still held and drops the dead, the released and the ones under another player's holder;
  * the pack's actors are the player, the core's one charm and every holder-charmed monster;
  * a kill by a holder-charmed monster, or a core-charmed one, credits the master once, and nothing else does.

Not covered: the core on a running server (the holder summon, Unit::Kill reaching UNITHOOK_ON_UNIT_DEATH), which
test_charm.py pins from the core's source, and the doubles are one Unit type standing for Player and Creature.
Seven mutations of the production text must each turn it red.

    python3 mod-diablocraft/scripts/tests/combat/test_charm_master.py
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
from test_class_parity import definition  # noqa: E402

ROOT = Path(__file__).resolve().parents[4]
SRC = ROOT / "mod-diablocraft/src"
EFFECT = (SRC / "combat/dc_charm_effect.cpp").read_text(encoding="utf-8")
AI = (SRC / "monsters/dc_monster_ai.cpp").read_text(encoding="utf-8")
QUESTS = (SRC / "rifts/dc_rift_quests.cpp").read_text(encoding="utf-8")

DOUBLES = r'''
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <map>
#include <mutex>
#include <unordered_map>
#include <vector>
#include "combat/dc_charm_effect_math.h"

struct ObjectGuid {
    std::uint64_t raw = 0;
    std::uint64_t GetRawValue() const { return raw; }
    bool operator==(ObjectGuid const& o) const { return raw == o.raw; }
};
// One type stands for Player, Creature and TempSummon: the flags say which a given object is.
struct Unit {
    std::uint64_t id = 0;
    bool player = false, summon = false, alive = true, inWorld = true;
    std::uint32_t entry = 0;
    Unit* charmer = nullptr;   // Unit::GetCharmer
    Unit* charm = nullptr;     // Player::GetCharm
    Unit* summoner = nullptr;  // TempSummon::GetSummonerUnit
    ObjectGuid GetGUID() const { return {id}; }
    Unit* GetCharmer() const { return charmer; }
    bool IsCharmed() const { return charmer != nullptr; }
    bool IsAlive() const { return alive; }
    bool IsInWorld() const { return inWorld; }
    bool IsPlayer() const { return player; }
    std::uint32_t GetEntry() const { return entry; }
    Unit* GetCharm() const { return charm; }
    Unit* ToCreature() { return player ? nullptr : this; }
    Unit* ToPlayer() { return player ? this : nullptr; }
    Unit* ToTempSummon() { return summon ? this : nullptr; }
    Unit* GetSummonerUnit() const { return summoner; }
};
using Player = Unit;
using Creature = Unit;
using TempSummon = Unit;

std::map<std::uint64_t, Unit*> world;
namespace ObjectAccessor {
    Creature* GetCreature(Unit const&, ObjectGuid guid) { auto it = world.find(guid.raw); return it == world.end() ? nullptr : it->second; }
}
// The rifts' own rule, as dc_monster_ai.cpp's IsCharmedMonster reads it for the monsters here: charmed, not a player.
bool IsCharmedMonster(Creature const* c) { return c && !c->player && c->IsCharmed(); }
std::vector<std::pair<Player*, Creature*>> credited;
void CreditRiftKill(Player* killer, Creature* killed) { credited.emplace_back(killer, killed); }
'''

MAIN = r'''
static int checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { std::printf("FAIL line %d: %s\n", __LINE__, #c); return 1; } } while (0)

int main()
{
    using namespace DC::Combat::CharmEffect;
    std::uint64_t next = 1;
    auto make = [&](bool player, std::uint32_t entry = 100) { auto* u = new Unit; u->id = next++; u->player = player; u->entry = entry; world[u->id] = u; return u; };
    Player* p = make(true);
    Player* other = make(true);
    Creature* pack = make(false);

    // M1: charmed through a holder the player summoned (the shared charm)
    Creature* holder1 = make(false, Holder); holder1->summon = true; holder1->summoner = p;
    Creature* m1 = make(false); m1->charmer = holder1;
    // M2: charmed by the player through the core's own charm
    Creature* m2 = make(false); m2->charmer = p; p->charm = m2;
    // M3: a holder summoned by a monster; M4: charmed by some other creature; M5: not charmed
    Creature* holder3 = make(false, Holder); holder3->summon = true; holder3->summoner = pack;
    Creature* m3 = make(false); m3->charmer = holder3;
    Creature* m4 = make(false); m4->charmer = pack;
    Creature* m5 = make(false);

    // whose charm it is
    CHECK(MasterOf(m1) == p);
    CHECK(MasterOf(m2) == p);
    CHECK(MasterOf(m3) == nullptr);
    CHECK(MasterOf(m4) == nullptr);
    CHECK(MasterOf(m5) == nullptr);
    CHECK(MasterOf(nullptr) == nullptr);
    Creature* notHolder = make(false, Holder + 1); notHolder->summon = true; notHolder->summoner = p;
    Creature* m6 = make(false); m6->charmer = notHolder;
    CHECK(MasterOf(m6) == nullptr);   // a summon of the player's that is not our holder

    // the monsters held
    CHECK(CharmedBy(p).empty());
    Remember(p, m1->GetGUID());
    {
        auto held = CharmedBy(p);
        CHECK(held.size() == 1 && held[0] == m1);
    }
    CHECK(CharmedBy(other).empty());
    Creature* holder7 = make(false, Holder); holder7->summon = true; holder7->summoner = other;
    Creature* m7 = make(false); m7->charmer = holder7;
    Remember(p, m7->GetGUID());           // registered for p, but held by other's holder: not p's
    {
        auto held = CharmedBy(p);
        CHECK(held.size() == 1 && held[0] == m1);
    }
    CHECK(charms.load() == 1);            // m7's entry was dropped by that read

    // the pack's actors: the player, the core's one charm, and the holder-charmed monster
    {
        auto actors = ActorsOf(p);
        CHECK(actors.size() == 3 && actors[0] == p);
        CHECK(std::find(actors.begin(), actors.end(), m1) != actors.end());
        CHECK(std::find(actors.begin(), actors.end(), m2) != actors.end());
        auto alone = ActorsOf(other);
        CHECK(alone.size() == 1 && alone[0] == other);
    }

    // a kill by a charmed monster credits its master
    OnUnitDeath(pack, m1);
    CHECK(credited.size() == 1 && credited[0].first == p && credited[0].second == pack);
    OnUnitDeath(pack, m2);
    CHECK(credited.size() == 2 && credited[1].first == p);
    OnUnitDeath(pack, m3);                // a holder a monster summoned
    OnUnitDeath(pack, m4);
    OnUnitDeath(pack, m5);
    OnUnitDeath(pack, p);                 // a player's kill is the core hook's, not this one
    OnUnitDeath(m1, m1);
    OnUnitDeath(nullptr, m1);
    OnUnitDeath(pack, nullptr);
    CHECK(credited.size() == 2);

    // the charm ends: released, then dead
    m1->charmer = nullptr;
    CHECK(CharmedBy(p).empty());
    CHECK(charms.load() == 0);
    m1->charmer = holder1;
    Remember(p, m1->GetGUID());
    m1->alive = false;
    CHECK(CharmedBy(p).empty());
    CHECK(charms.load() == 0);
    Remember(p, m1->GetGUID());
    Forget(p->GetGUID(), m1->GetGUID());  // the holder's look found the charm over
    CHECK(charms.load() == 0);

    std::printf("charm master: ok, %d checks\n", checks);
    return 0;
}
'''


def production():
    """The production text the harness compiles: the registry, MasterOf, CharmedBy, ActorsOf, OnUnitDeath."""
    registry_from = EFFECT.index("std::mutex registryMutex;")
    registry_to = EFFECT.index("std::atomic<std::size_t> charms{0};") + len("std::atomic<std::size_t> charms{0};")
    holder = re.search(r"constexpr std::uint32_t Holder = \d+;", EFFECT).group(0)
    pieces = {
        "registry": EFFECT[registry_from:registry_to],
        "holder": holder,
        "remember": definition(EFFECT, "void Remember("),
        "forget": definition(EFFECT, "void Forget("),
        "master": definition(EFFECT, "Player* MasterOf(Unit const* charmed)"),
        "held": definition(EFFECT, "std::vector<Creature*> CharmedBy(Player* master)"),
        "actors": definition(AI, "static std::vector<Unit*> ActorsOf(Player* player)"),
        "death": definition(QUESTS[QUESTS.index("class RiftCharmKills"):], "void OnUnitDeath(Unit* victim, Unit* killer)"),
    }
    return pieces


def program(pieces):
    return (DOUBLES + "namespace DC::Combat::CharmEffect {\n" + pieces["holder"] + "\n" + pieces["registry"] + "\n"
            + pieces["remember"] + "\n" + pieces["forget"] + "\n" + pieces["master"] + "\n" + pieces["held"] + "\n}\n"
            + pieces["actors"] + "\n" + pieces["death"] + "\n" + MAIN)


def run(pieces):
    return harness_env.run_cpp(program(pieces), extra=("-I", str(SRC)))


class CharmMaster(unittest.TestCase):
    def test_a_holder_charmed_monster_is_the_players_for_the_pack_and_the_rift_kill(self):
        ok, out = run(production())
        self.assertTrue(ok, out)
        self.assertIn("charm master: ok", out)

    def test_each_mutation_of_the_production_text_is_caught(self):
        mutations = [
            ("the holder's summoner is not asked", "master",
             "who.summonerPlayer = summoner && summoner->IsPlayer();", "who.summonerPlayer = false;"),
            ("any summon of a player's passes for the holder", "master",
             "who.holder = holder && holder->GetEntry() == Holder;", "who.holder = holder != nullptr;"),
            ("CharmedBy keeps a monster another player's holder holds", "held",
             " && MasterOf(creature) == master", ""),
            ("CharmedBy keeps the dead", "held", "creature->IsAlive() && ", ""),
            ("the pack leaves out the holder-charmed", "actors",
             "for (Creature* monster : DC::Combat::CharmEffect::CharmedBy(player))", "for (Creature* monster : std::vector<Creature*>{})"),
            ("the kill credits the holder's side, not the master", "death",
             "CreditRiftKill(master, dead);", "CreditRiftKill(nullptr, dead);"),
            ("the kill reads the core charmer only", "death",
             "Player* master = body ? DC::Combat::CharmEffect::MasterOf(body) : nullptr;",
             "Player* master = body && body->GetCharmer() && body->GetCharmer()->IsPlayer() ? body->GetCharmer()->ToPlayer() : nullptr;"),
        ]
        for label, piece, old, new in mutations:
            with self.subTest(label):
                pieces = production()
                squeezed = re.sub(r"\s+", " ", pieces[piece])
                old_s = re.sub(r"\s+", " ", old)
                self.assertEqual(squeezed.count(old_s), 1, f"the mutation target is gone or not unique: {old!r}")
                pieces[piece] = squeezed.replace(old_s, new)
                ok, out = run(pieces)
                self.assertFalse(ok, f"{label} was not caught")


class Wiring(unittest.TestCase):
    """The calls the harness does not make: the registry is fed by Apply and emptied by the holder's look."""

    def test_apply_remembers_the_charm_and_the_look_forgets_it(self):
        apply_ = re.sub(r"\s+", " ", definition(EFFECT, "bool Apply("))
        look = re.sub(r"\s+", " ", definition(EFFECT, "void Look("))
        self.assertIn("Remember(master, creature->GetGUID());", apply_)
        self.assertLess(apply_.index("Remember("), apply_.index("return true;"))
        self.assertLess(apply_.index("creature->GetCharmerGUID() != holder->GetGUID()"), apply_.index("Remember("),
                        "only a charm that took hold is remembered")
        self.assertIn("Forget(master, charmed); holder->DespawnOrUnsummon();", look)

    def test_the_rifts_name_no_class(self):
        for text in (AI, QUESTS):
            for name in ("Crusader", "Barbarian", "Wizard", "Monk", "Necromancer"):
                self.assertNotIn(name + "::", text)


if __name__ == "__main__":
    unittest.main()
