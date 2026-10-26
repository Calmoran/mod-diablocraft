"""diablocraft-potion-shared-cooldown - the Health Potion and the Bottomless Potion share one cooldown,
on the server AND on the client's button, and the potion slot may change in combat.

The designer, Nightly 58 check 5/6 (q-1003-16): "they do not share a cooldown". The server did put every shell
on cooldown, but only with AddSpellCooldown(..., needSendToClient=true), and that flag sends nothing to
the client (Player.cpp:2859 reads it for the login spell list and the save only). A shell that another
potion's drink had put on cooldown, or one a swap had just learned, therefore showed a READY button.
Ruling q-1003-21: the potion slot may also change in combat, shipped with this fix so a swap never skips or
resets a cooldown.

The production functions are cut out of dc_classes.cpp and dc_inventory.cpp and compiled, as they are,
against a Player that keeps a server cooldown table and a record of what the client was told. Each rule
has a mutation that must turn the harness red.
"""
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

HERE = Path(__file__).resolve().parents[2]
MODULE = HERE.parent
ROOT = MODULE.parent
CLASSES_CPP = MODULE / "src" / "classes" / "dc_classes.cpp"
INVENTORY_CPP = MODULE / "src" / "items" / "dc_inventory.cpp"
POTION_H = MODULE / "src" / "classes" / "dc_potion.h"
SCRATCH = ROOT / "azerothcore-wotlk" / "build" / "_agent-scratch" / "potion_cooldown"
CXX = shutil.which("c++") or shutil.which("g++")


def definition(marker, source):
    """One definition, braces balanced, exactly as the module has it."""
    assert source.count(marker) == 1, "%r is not unique" % marker
    start = source.index(marker)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    if source[end:end + 1] == ";":
        end += 1
    return source[start:end]


def cuts(classes, inventory):
    return {
        "send": definition("void SendPotionCooldown(Player* player, std::uint32_t spellId)", classes),
        "share": definition("void SharePotionCooldown(Player* player, SpellInfo const* info)", classes),
        "cast": definition("class PotionCast final : public AllSpellScript", classes),
        "bar": definition("void WriteActionBar(Player* player, std::vector<Slot> const& bar)", classes),
        "acting": definition("Player* Acting(ChatHandler* handler)", inventory),
    }


HARNESS = r'''
#include <algorithm>
#include <cstdint>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
#include "dc_potion.h"

using uint8 = std::uint8_t;
using uint32 = std::uint32_t;
enum { SPEC_MASK_ALL = 0xFFFF, ACTION_BUTTON_SPELL = 0, SPELL_COOLDOWN_FLAG_NONE = 0, ALLSPELLHOOK_ON_CAST = 1 };
constexpr uint32 TOWN_PORTAL_SHELL = 81206;
using PacketCooldowns = std::map<uint32, uint32>;
struct WorldPacket { PacketCooldowns cooldowns; };
struct SpellInfo { uint32 Id; };
struct Spell {};
struct Player;
struct Session;
struct Unit { Player* ToPlayer(); virtual ~Unit() = default; };

static uint32 now = 0;
static unsigned failures = 0;
static void Check(bool ok, std::string const& message)
{
    if (!ok) { std::cerr << "FAILED: " << message << "\n"; ++failures; }
}

struct Player : Unit
{
    // The server's table: when each shell is ready again.
    std::map<uint32, uint32> serverEnd;
    // What the client was told: spell -> (milliseconds, the moment the packet arrived).
    std::map<uint32, std::pair<uint32, uint32>> client;
    std::set<uint32> known;
    std::map<uint8, uint32> buttons;
    uint32 slotted = DC::Potion::BaseSpell;
    bool inCombat = false, alive = true;
    Session* session = nullptr;
    Session* GetSession() { return session; }

    void AddSpellCooldown(uint32 id, uint32, uint32 ms, bool) { serverEnd[id] = now + ms; }
    uint32 GetSpellCooldownDelay(uint32 id) const
    {
        auto found = serverEnd.find(id);
        return found != serverEnd.end() && found->second > now ? found->second - now : 0;
    }
    void BuildCooldownPacket(WorldPacket& packet, int, PacketCooldowns const& cooldowns) { packet.cooldowns = cooldowns; }
    void SendDirectMessage(WorldPacket* packet)
    {
        for (auto const& [id, ms] : packet->cooldowns)
            client[id] = {ms, now};
    }
    // What the client's button for `id` would show right now.
    uint32 Shown(uint32 id) const
    {
        auto found = client.find(id);
        if (found == client.end())
            return 0;
        uint32 const elapsed = now - found->second.second;
        return found->second.first > elapsed ? found->second.first - elapsed : 0;
    }
    bool HasSpell(uint32 id) const { return known.count(id) != 0; }
    void learnSpell(uint32 id) { known.insert(id); }
    void removeSpell(uint32 id, int, bool) { known.erase(id); }   // the core keeps the cooldown table
    void removeActionButton(uint8 slot) { buttons.erase(slot); }
    void addActionButton(uint8 slot, uint32 id, int) { buttons[slot] = id; }
    void SendActionButtons(int) {}
    bool IsInCombat() const { return inCombat; }
    bool IsAlive() const { return alive; }
    uint32 GetHealth() const { return 100; }
    uint32 GetMaxHealth() const { return 100; }
};
Player* Unit::ToPlayer() { return static_cast<Player*>(this); }

struct AllSpellScript
{
    AllSpellScript(char const*, std::vector<int>) {}
    virtual ~AllSpellScript() = default;
    virtual void OnSpellCast(Spell*, Unit*, SpellInfo const*, bool) = 0;
};

struct SpellMgrStub { SpellInfo const* GetSpellInfo(uint32 id) { static SpellInfo info{0}; info.Id = id; return &info; } } spellMgr;
#define sSpellMgr (&spellMgr)

struct Slot { unsigned slot; uint32 spellId; };
unsigned ActiveSlots() { return 6; }
namespace Inventory { uint32 ActivePotionSpell(Player* player) { return player->slotted; } }
// The heal is test_potion.py's business; this file is about the cooldown.
namespace { void RestorePotionLife(Player*, SpellInfo const*) {} }
// The power on the drink is test_potion_powers.py's business (diablocraft-87qlt).
namespace { void DrinkPotionPower(Player*, DC::Potion::Legendary const&, bool) {} }
namespace DC { }
using namespace DC;

void Need(bool ok, char const* message) { if (!ok) throw std::runtime_error(message); }
struct Session { Player* player; bool aborted; Player* GetPlayer() { return player; } bool EconomyAborted() { return aborted; } };
struct ChatHandler { Session* session; Session* GetSession() { return session; } };

@SEND@
@SHARE@
@CAST@
@BAR@
namespace Acting_ { @ACTING@ }

static void Drink(Player& player, PotionCast& script, uint32 spell)
{
    // The core starts the cast shell's own 30 s and tells the client; then the script hook runs.
    player.AddSpellCooldown(spell, 0, DC::Potion::CooldownMs, true);
    WorldPacket own;
    own.cooldowns[spell] = DC::Potion::CooldownMs;
    player.SendDirectMessage(&own);
    SpellInfo info{spell};
    script.OnSpellCast(nullptr, &player, &info, true);
}

int main()
{
    PotionCast script;
    uint32 const health = DC::Potion::BaseSpell, bottomless = DC::Potion::BottomlessSpell;
    std::vector<Slot> const bar = {};

    {   // 1. Drinking the Health Potion puts the Bottomless Potion on cooldown, on the client too.
        now = 1000;
        Player player; player.known = {health};
        Drink(player, script, health);
        Check(player.GetSpellCooldownDelay(bottomless) == 30000, "1: the server did not share the cooldown");
        Check(player.Shown(bottomless) == 30000, "1: the client was never told the Bottomless Potion is on cooldown");
        now += 10000;
        Check(player.Shown(bottomless) == 20000, "1: the client's cooldown does not run down with time");
    }
    {   // 2. And the other way round.
        now = 1000;
        Player player; player.known = {bottomless}; player.slotted = bottomless;
        Drink(player, script, bottomless);
        Check(player.GetSpellCooldownDelay(health) == 30000, "2: the server did not share the cooldown");
        Check(player.Shown(health) == 30000, "2: the client was never told the Health Potion is on cooldown");
    }
    {   // 3. A swap right after a drink shows the time left: not ready, not restarted.
        now = 1000;
        Player player; player.known = {health};
        Drink(player, script, health);
        now += 5000;
        // A client with no record of the shell: it was forgotten, or this is just after a relog.
        // The server table still holds the cooldown; the swap alone must put it on the button.
        player.client.erase(bottomless);
        player.slotted = bottomless;
        WriteActionBar(&player, bar);
        Check(player.HasSpell(bottomless), "3: the Bottomless shell was not learned by the swap");
        Check(player.buttons[6] == bottomless, "3: key 7 does not hold the Bottomless Potion after the swap");
        uint32 const shown = player.Shown(bottomless);
        Check(shown > 0, "3: a potion swapped in right after a drink shows a READY button");
        Check(shown == 25000, "3: the swapped-in potion shows the wrong time left");
        now += 2000;
        player.slotted = health;
        WriteActionBar(&player, bar);
        Check(!player.HasSpell(bottomless), "3: the Bottomless shell was not forgotten on the swap back");
        Check(player.GetSpellCooldownDelay(bottomless) == 23000, "3: forgetting the shell dropped its cooldown on the server");
        Check(player.Shown(health) == 23000, "3: the swap back shows a different time than the drink left");
    }
    {   // 4. A swap after the cooldown ran out shows nothing to wait for.
        now = 1000;
        Player player; player.known = {health};
        Drink(player, script, health);
        now += 30001;
        player.slotted = bottomless;
        WriteActionBar(&player, bar);
        Check(player.GetSpellCooldownDelay(bottomless) == 0 && player.Shown(bottomless) == 0,
              "4: a finished cooldown still shows");
    }
    {   // 5. The potion slot may change in combat: the guard no longer refuses a fight, still refuses the rest.
        Player player;
        Session session{&player, false};
        player.session = &session;
        ChatHandler handler{&session};
        player.inCombat = true;
        bool refused = false;
        try { Acting_::Acting(&handler); } catch (std::exception const&) { refused = true; }
        Check(!refused, "5: a swap was refused in combat");
        player.alive = false;
        refused = false;
        try { Acting_::Acting(&handler); } catch (std::exception const&) { refused = true; }
        Check(refused, "5: a dead character changed gear");
        player.alive = true; session.aborted = true;
        refused = false;
        try { Acting_::Acting(&handler); } catch (std::exception const&) { refused = true; }
        Check(refused, "5: a character with an aborted economy changed gear");
        session.aborted = false;
        ChatHandler none{nullptr};
        refused = false;
        try { Acting_::Acting(&none); } catch (std::exception const&) { refused = true; }
        Check(refused, "5: no character was accepted");
    }
    if (failures)
    {
        std::cerr << failures << " check(s) failed\n";
        return 1;
    }
    std::cout << "potion cooldown OK\n";
    return 0;
}
'''


def build_and_run(classes, inventory, tag):
    parts = cuts(classes, inventory)
    code = HARNESS
    for key, text in parts.items():
        code = code.replace("@%s@" % key.upper(), text)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix=tag + "-", dir=SCRATCH))
    source = folder / "harness.cpp"
    source.write_text(code, encoding="utf-8")
    binary = folder / "harness"
    built = subprocess.run([CXX, "-std=c++17", "-I", str(POTION_H.parent), "-o", str(binary), str(source)],
                           capture_output=True, text=True)
    if built.returncode:
        raise AssertionError("the harness did not compile:\n" + built.stderr[-6000:])
    return harness_env.run([str(binary)], capture_output=True, text=True)


def code_only(text):
    return "\n".join(line.split("//")[0] for line in text.splitlines()
                     if not line.strip().startswith(("//", "*", "/*")))


# One mutation per rule; each must turn the harness red. (file, old, new)
MUTATIONS = [
    ("the drink does not tell the client about the other shell", "classes",
     "            player->AddSpellCooldown(shell, 0, Potion::CooldownMs, true);\n            SendPotionCooldown(player, shell);\n",
     "            player->AddSpellCooldown(shell, 0, Potion::CooldownMs, true);\n"),
    ("the swap does not resend the cooldown of the potion it slots", "classes",
     "        SendPotionCooldown(player, potion);\n", ""),
    ("the resend restarts the cooldown instead of showing what is left", "classes",
     "cooldowns[spellId] = remaining;", "cooldowns[spellId] = DC::Potion::CooldownMs;"),
    ("the shell is shared on the server only for the cast shell", "classes",
     "        if (shell != info->Id)\n        {", "        if (shell == info->Id)\n        {"),
    ("the guard refuses a swap in combat again", "inventory",
     'Need(player->IsAlive(), "You cannot change gear while dead.");',
     'Need(player->IsAlive(), "You cannot change gear while dead.");\n            Need(!player->IsInCombat(), "You cannot change gear in combat.");'),
    ("the guard lets a dead character change gear", "inventory",
     'Need(player->IsAlive(), "You cannot change gear while dead.");', ""),
]


@unittest.skipUnless(CXX, "no C++ compiler")
class PotionCooldown(unittest.TestCase):
    classes = CLASSES_CPP.read_text(encoding="utf-8")
    inventory = INVENTORY_CPP.read_text(encoding="utf-8")

    def test_production_passes(self):
        done = build_and_run(self.classes, self.inventory, "real")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("potion cooldown OK", done.stdout)

    def test_every_rule_fails_when_removed(self):
        survived = []
        for index, (label, which, old, new) in enumerate(MUTATIONS):
            classes, inventory = self.classes, self.inventory
            source = classes if which == "classes" else inventory
            self.assertEqual(source.count(old), 1, "mutation anchor not unique or not found: " + label)
            mutated = source.replace(old, new)
            done = build_and_run(mutated if which == "classes" else classes,
                                 mutated if which == "inventory" else inventory, "mutant%d" % index)
            if done.returncode == 0:
                survived.append(label)
        self.assertEqual(survived, [], "the harness passed with the rule removed")


class Wiring(unittest.TestCase):
    """The hooks that cannot run offline, read with comments removed."""

    classes = code_only(CLASSES_CPP.read_text(encoding="utf-8"))
    inventory = code_only(INVENTORY_CPP.read_text(encoding="utf-8"))

    def test_a_potion_swap_rewrites_the_bar_so_the_cooldown_is_resent(self):
        body = definition("void ChangePotion(Player* player, Item* source)", self.inventory)
        self.assertIn("Classes::WriteActionBar(player);", body)
        self.assertIn("SendPotionCooldown(player, potion);", definition(
            "void WriteActionBar(Player* player, std::vector<Slot> const& bar)", self.classes))

    def test_the_cast_hook_shares_the_cooldown_for_every_potion_shell(self):
        self.assertIn("SharePotionCooldown(player, info);",
                      definition("class PotionCast final : public AllSpellScript", self.classes))

    def test_equip_and_unequip_have_no_combat_refusal_of_their_own(self):
        for handler in ("static bool HandleEquip(ChatHandler* handler, int32 index)",
                        "static bool HandleUnequip(ChatHandler* handler, int32 slot)"):
            body = definition(handler, self.inventory)
            self.assertIn("Acting(handler)", body)
            self.assertNotIn("IsInCombat", body)

    def test_identify_keeps_its_own_combat_refusal(self):
        body = definition("static bool HandleIdentify(ChatHandler* handler, int32 index)", self.inventory)
        self.assertIn("DC::Identify::Refusal(player->IsAlive(), player->IsInCombat(), item->IsInTrade())", body)

    def test_the_catalogue_holds_every_shell(self):
        # The Health Potion and every Bottomless potion of the generated table (diablocraft-87qlt).
        header = POTION_H.read_text(encoding="utf-8")
        self.assertIn("std::array<std::uint32_t, std::size(Legendaries) + 1> shells{BaseSpell};", header)
        self.assertIn("shells[i + 1] = Legendaries[i].shell;", header)


if __name__ == "__main__":
    unittest.main()
