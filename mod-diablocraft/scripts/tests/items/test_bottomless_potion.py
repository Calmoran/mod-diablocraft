"""diablocraft-potion-regeneration: the first legendary potion, Bottomless Potion of Regeneration.

Data (the item, its slot, no on-use spell, the shell, the client rows, no loot) and
production C++ (key 7 follows the equipped potion, the shell heals 60%). Every check
fails on the files before this task: there is no item, no shell 81205, no mapping.
The tooltip half is test_bottomless_potion.lua, run from here.
"""
import csv
import re
import struct
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_spells as generator
import harness_env

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / "mod-diablocraft"
ENTRY, SHELL = 102200, 81205
NAME = "Bottomless Potion of Regeneration"
MIGRATION = MODULE / "data/sql/db-world/updates/items_0015_bottomless_potion.sql"


def extract(source, signature):
    start = source.index(signature)
    opening = source.index("{", start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def csv_row():
    with (MODULE / "data/d3/legendary_potions.csv").open(encoding="utf-8-sig", newline="") as stream:
        return next(row for row in csv.DictReader(stream) if row["d3_id"] == "HealthPotionLegendary_03")


def data_checks():
    row = csv_row()
    sql = MIGRATION.read_text(encoding="utf-8")
    # The item: the CSV row's name, legendary quality (5), required level, flavour; the potion
    # class; and NO on-use spell - spellid_1 is not even a column the insert names.
    template = re.search(r"INSERT INTO `item_template`\s*\((.*?)\)\s*VALUES\s*\((.*?)\);", sql, re.S)
    columns = [c.strip().strip("`") for c in template[1].split(",")]
    assert not any(c.startswith(("spellid", "spelltrigger")) for c in columns), "no on-use spell"
    values = template[2]
    assert values.lstrip().startswith(f"{ENTRY}, 0, 1, '{NAME}'"), "a potion (class 0, subclass 1) of that name"
    fields = dict(zip(columns, [v.strip() for v in values.split(",")[:len(columns) - 1]]))
    assert fields["Quality"] == "5", "legendary quality"
    assert fields["RequiredLevel"] == row["required_level"] == "61"
    assert row["flavor_text"].strip("“”").split("”")[0] in sql, "the CSV flavour text"
    assert "Restores an additional 75000–100000 Life over 5 seconds." in sql, "the power line with its range"
    assert (row["roll_min"], row["roll_max"]) == ("75000", "100000")
    # dc_base_item: the slot the sheet's potion slot reads, outside every pool.
    base = re.search(r"INSERT INTO `dc_base_item`.*?VALUES\s*\((.*?)\);", sql, re.S)[1]
    assert base.startswith(f"{ENTRY}, 'HealthPotionLegendary_03', '{NAME}', 'potion', "), "slot 'potion'"
    assert "'no', '', 'no'" in base, "pool_version 'no': never rolled, never in a pool"
    # The shell: its own spell, 30 s cooldown, heals 60% of max Life.
    shells = (generator.GENERATED / "spell_shells.sql").read_text(encoding="utf-8")
    cols = [c.strip().strip("`") for c in re.search(r"INSERT INTO `spell_dbc` \((.*?)\) VALUES", shells)[1].split(",")]
    line = next(entry for entry in shells.splitlines() if entry.startswith(f"({SHELL},"))
    fields = dict(zip(cols, next(csv.reader([line[1:-2]], quotechar="'", skipinitialspace=True))))
    assert fields["Name_Lang_enUS"] == NAME
    assert int(fields["RecoveryTime"]) == 30000 and int(fields["CastingTimeIndex"]) == 1
    assert fields["Description_Lang_enUS"] == "Instantly restores 60% of maximum Life."
    assert int(fields["SpellIconID"]) == 3035 and int(fields["Effect_1"]) == 3
    update = MODULE / "data/sql/db-world/updates/combat_0043_bottomless_potion_shell.sql"
    assert f"({SHELL}," in update.read_text(encoding="utf-8")
    header = (MODULE / "src/combat/dc_spell_shells.h").read_text(encoding="utf-8")
    assert re.search(rf"\b{SHELL},", header), "a shell the class strip keeps"
    # The client: Spell.dbc name; Item.dbc row (display 90300 = DC_Potion_HealthPotionLegendary_03, set over
    # build_item.py's 24152 by generate_potion_icons.py, diablocraft-71scy).
    dbc = generator.CLIENT_DBC.read_bytes()
    _, count, _, size, _ = struct.unpack_from("<4sIIII", dbc)
    record = next(dbc[p:p + size] for p in range(20, 20 + count * size, size)
                  if struct.unpack_from("<I", dbc, p)[0] == SHELL)
    strings = dbc[20 + count * size:]
    offset = struct.unpack_from("<I", record, generator.F_NAME_ENUS * 4)[0]
    assert strings[offset:strings.index(b"\0", offset)] == NAME.encode()
    item = (ROOT / "client-patch/dbc/Item.dbc").read_bytes()
    _, n, _, isize, _ = struct.unpack_from("<4sIIII", item)
    rows = [struct.unpack_from("<IIIiiIII", item, 20 + i * isize) for i in range(n)]
    assert (ENTRY, 0, 1, -1, 3, 90300, 0, 0) in rows, "Item.dbc row: potion, its own icon"
    # Every shell the generator marks as a potion is in the cooldown catalogue, so a future legendary
    # potion that forgets Potion::Shells fails here instead of getting a private timer.
    with (generator.GENERATED / "spell_shells.csv").open(encoding="utf-8", newline="") as stream:
        potions = {int(r["spell_id"]) for r in csv.DictReader(stream) if r["kind"] == "potion"}
    # Since diablocraft-87qlt the catalogue is the Health Potion and every row of the generated potion table.
    header = (MODULE / "src/classes/dc_potion.h").read_text()
    assert "std::array<std::uint32_t, std::size(Legendaries) + 1> shells{BaseSpell};" in header
    assert "shells[i + 1] = Legendaries[i].shell;" in header
    table = (MODULE / "src/classes/dc_potion_table.h").read_text()
    shells = {int(m) for m in re.findall(r"^    \{\d+, (\d+), \d+, ", table, re.M)}
    assert potions == {81202} | shells and SHELL in shells, "Potion::Shells lists every potion shell"
    # GM-only: no loot, vendor, kit, mail or reward file names the entry.
    allowed = {"items_0015_bottomless_potion.sql", "dc_potion.h", "tests/items/test_bottomless_potion.py",
               "tests/items/test_bottomless_potion.lua", "build_item.py", "potion_icons.csv", "items_0023_potion_icons.sql",
               "generate/items/generate_potion_icons.py", "tests/items/test_potion_icons.py", "items_0027_bottomless_potions.sql",
               "dc_potion_table.h"}
    for path in MODULE.rglob("*"):
        if (not path.is_file() or path.name in allowed or path.name.startswith("test_") or "azerothcore-wotlk" in path.parts
                or path.suffix not in (".sql", ".csv", ".lua", ".cpp", ".h", ".py", ".json")):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert not re.search(rf"\b{ENTRY}\b", text), f"{path.relative_to(MODULE)} names the potion"
    print("PASS bottomless potion data, client rows, GM-only", flush=True)


CODE = r'''
#include <algorithm>
#include <cstdint>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>
#include "@HEADER@"
using uint8 = std::uint8_t;
using uint32 = std::uint32_t;
constexpr uint8 ACTION_BUTTON_SPELL = 0;
constexpr uint32 SPEC_MASK_ALL = 0xFFFFFFFF;
using SpellSchoolMask = uint32;
struct SpellInfo { uint32 Id = 0, SchoolMask = 2; };
struct SpellMgr {
    SpellInfo portal{81167}, base{81202}, bottomless{81205};
    SpellInfo const* GetSpellInfo(uint32 spell) {
        return spell == 81167 ? &portal : spell == 81202 ? &base : spell == 81205 ? &bottomless : nullptr;
    }
} spellMgr;
SpellMgr* sSpellMgr = &spellMgr;
struct Player;
struct HealInfo {
    Player* healer; Player* target; uint32 amount; SpellInfo const* info;
    HealInfo(Player* h, Player* t, uint32 a, SpellInfo const* s, SpellSchoolMask) : healer(h), target(t), amount(a), info(s) {}
};
struct Player {
    std::map<uint8, std::pair<uint32, uint8>> buttons;
    std::set<uint32> known;
    uint32 maximum = 1000, current = 100, lastHealSpell = 0;
    std::map<uint32, uint32> cooldowns;          // spell id -> relative ms installed
    void AddSpellCooldown(uint32 spell, uint32, uint32 ms, bool) { cooldowns[spell] = ms; }
    bool alive = true;
    void removeActionButton(uint8 slot) { buttons.erase(slot); }
    bool addActionButton(uint8 slot, uint32 spell, uint8 type) { buttons[slot] = {spell, type}; return true; }
    void SendActionButtons(uint8) {}
    bool HasSpell(uint32 spell) const { return known.count(spell) != 0; }
    void learnSpell(uint32 spell) { known.insert(spell); }
    void removeSpell(uint32 spell, uint32, bool) {
        known.erase(spell);
        for (auto it = buttons.begin(); it != buttons.end();)
            it = it->second.first == spell ? buttons.erase(it) : std::next(it);
    }
    bool IsAlive() const { return alive; }
    uint32 GetMaxHealth() const { return maximum; }
    uint32 GetHealth() const { return current; }
    void HealBySpell(HealInfo const& heal, bool) {
        current = std::min(maximum, current + heal.amount); lastHealSpell = heal.info->Id;
    }
    Player* ToPlayer() { return this; }
};
using Unit = Player;
struct Spell {};
constexpr int ALLSPELLHOOK_ON_CAST = 1;
struct AllSpellScript {
    AllSpellScript(char const*, std::vector<int>) {}
    virtual void OnSpellCast(Spell*, Unit*, SpellInfo const*, bool) {}
    virtual ~AllSpellScript() = default;
};
std::uint32_t equipped = 0;                    // dc_character_potion.item_entry for the player
namespace DC::Inventory {
std::uint32_t EquippedPotionEntry(Player*) { return equipped; }
@ACTIVE@
}
namespace DC::Classes {
inline unsigned ActiveSlots() { return 6; }
struct Slot { unsigned slot = 0; std::string skill, rune; std::uint32_t spellId = 0; };
namespace {
constexpr std::uint32_t TOWN_PORTAL_SHELL = 81167;
// What the client is told (the real SendPotionCooldown is compiled in test_potion_cooldown.py): the shells sent.
std::vector<std::uint32_t> told;
void SendPotionCooldown(Player*, std::uint32_t spellId) { told.push_back(spellId); }
@WRITE@
@HEAL@
@SHARE@
// The power on the drink is test_potion_powers.py's (diablocraft-87qlt); here only that the cast hands it over.
std::vector<std::uint32_t> drunk;
void DrinkPotionPower(Player*, DC::Potion::Legendary const& potion, bool) { drunk.push_back(potion.shell); }
@CAST@;
}
}
int checks = 0;
void check(bool pass, char const* name) { ++checks; if (!pass) throw std::runtime_error(name); }
int main() {
    using namespace DC;
    using namespace DC::Classes;
    check(Potion::SpellFor(0) == 81202, "no potion equipped: the Health Potion");
    check(Potion::SpellFor(Potion::BottomlessItem) == 81205, "the Bottomless Potion maps to its own shell");
    check(Potion::SpellFor(900001) == 81202, "any other potion keeps the Health Potion");
    check(Potion::IsPotionShell(81202) && Potion::IsPotionShell(81205) && !Potion::IsPotionShell(81167), "potion shells");
    Player player;
    std::vector<Slot> bar;
    WriteActionBar(&player, bar);
    check(player.buttons.at(6).first == 81202, "nothing equipped: key 7 is the Health Potion");
    equipped = Potion::BottomlessItem;
    WriteActionBar(&player, bar);
    check(player.buttons.at(6) == std::make_pair(uint32(81205), ACTION_BUTTON_SPELL), "equipped: key 7 is the Bottomless shell");
    check(player.HasSpell(81205), "its shell is learned before the button is added");
    check(player.buttons.at(7).first == 81167, "Town Portal stays on key 8");
    equipped = 0;
    WriteActionBar(&player, bar);
    check(player.buttons.at(6).first == 81202, "taken off: the Health Potion is back on key 7");
    check(!player.HasSpell(81205), "taken off: the legendary shell is forgotten");
    check(player.HasSpell(81202), "the Health Potion stays known");
    // The shell heals 60% of max Life, like the Health Potion; a full-Life cast heals nothing.
    for (uint32 id : {81202u, 81205u}) {
        Player p; p.maximum = 2500; p.current = 250;
        PotionCast script;
        SpellInfo info{id};
        script.OnSpellCast(nullptr, &p, &info, false);
        check(p.current == 250 + 1500 && p.lastHealSpell == id, "60% of max Life, by that shell");
        p.current = p.maximum; p.lastHealSpell = 0;
        script.OnSpellCast(nullptr, &p, &info, false);
        check(p.lastHealSpell == 0, "no heal at full Life");
    }
    check(drunk == std::vector<std::uint32_t>{81205, 81205}, "the Bottomless shell hands its drink to the power, the Health Potion does not");
    // ONE cooldown for every potion shell (the designer, q-1002-02 A): drinking either puts BOTH on 30 s.
    for (uint32 id : {81202u, 81205u}) {
        Player p; PotionCast script; SpellInfo info{id};
        told.clear();
        script.OnSpellCast(nullptr, &p, &info, false);
        for (uint32 shell : DC::Potion::Shells)
            if (shell != id)
            {
                check(p.cooldowns.count(shell) == 1 && p.cooldowns.at(shell) == DC::Potion::CooldownMs,
                      "drinking one potion puts every other potion shell on the 30 s cooldown");
                check(std::count(told.begin(), told.end(), shell) == 1,
                      "and the client is told about each of them");
            }
        check(p.cooldowns.count(id) == 0, "the cast shell's own cooldown is the spell record's, not doubled here");
    }
    {
        Player p; PotionCast script; SpellInfo info{81167};
        script.OnSpellCast(nullptr, &p, &info, false);
        check(p.cooldowns.empty(), "another spell shares no cooldown");
    }
    SpellInfo other{81167};
    Player q; q.current = 100; PotionCast otherScript;
    otherScript.OnSpellCast(nullptr, &q, &other, false);
    check(q.current == 100, "another spell is not a potion");
    std::cout << "PASS " << checks << " production bottomless potion checks\n";
}
'''


def cpp_checks():
    inventory = (MODULE / "src/items/dc_inventory.cpp").read_text(encoding="utf-8")
    classes = (MODULE / "src/classes/dc_classes.cpp").read_text(encoding="utf-8")
    code = (CODE.replace("@HEADER@", (MODULE / "src/classes/dc_potion.h").as_posix())
            .replace("@ACTIVE@", extract(inventory, "std::uint32_t ActivePotionSpell("))
            .replace("@WRITE@", extract(classes, "void WriteActionBar(Player* player, std::vector<Slot> const& bar)"))
            .replace("@HEAL@", extract(classes, "void RestorePotionLife("))
            .replace("@SHARE@", extract(classes, "void SharePotionCooldown("))
            .replace("@CAST@", extract(classes, "class PotionCast final")))
    binary = harness_env.build_text(code, flags=["-std=c++17", "-Wall"])
    harness_env.run([str(binary)], check=True)


def main():
    data_checks()
    cpp_checks()


if __name__ == "__main__":
    main()
