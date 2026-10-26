"""diablocraft-87qlt: each Bottomless potion's power on its drink, at the roll the potion slot keeps.

    python3 mod-diablocraft/scripts/tests/items/test_potion_powers.py

Data, read across sources: the generated potion table (src/classes/dc_potion_table.h) is generate_potion_icons.py's render,
its numbers are the ones each row's own D3 text states, every potion's shell and power record is a generated spell row of
the right shape, and the power table has a `potion` row for exactly the potions with a roll range. Production C++: the
power code of dc_classes.cpp (DrinkPotionPower, PotionStatSync, PutPotionAura, PotionCast, PotionPowers) compiled against
stubs of the core, the sheet and the slot, driven with the generated table and the sheet's ranges.

Not covered: the real core (an aura's tooltip, the fear's flight, the immunity's purge, the sheet's own maths), which the
dev checks prove.
"""
import csv
import re
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_potion_icons as potions
import harness_env

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / "mod-diablocraft"
OUT = ROOT / "azerothcore-wotlk/build/_agent-scratch/scripts/potion-powers-tests"
CLASSES = MODULE / "src/classes/dc_classes.cpp"


def extract(source, signature):
    start = source.index(signature)
    opening = source.index("{", start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end] + ";"


def sheet():
    with (MODULE / "data/d3/legendary_potions.csv").open(encoding="utf-8-sig", newline="") as stream:
        return {row["d3_id"]: row for row in csv.DictReader(stream)}


def spell_rows():
    sql = (MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8")
    rows = {}
    for columns, values in re.findall(r"INSERT INTO `spell_dbc` \((.*?)\) VALUES\n(.*?);\n", sql, re.S):
        names = [c.strip().strip("`") for c in columns.split(",")]
        for line in values.splitlines():
            cells = next(csv.reader([line.rstrip(",")[1:-1]], quotechar="'", skipinitialspace=True))
            rows[int(cells[0])] = dict(zip(names, cells))
    return rows


class TheData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.potions, cls.sheet, cls.spells = potions.rows(), sheet(), spell_rows()

    def test_the_table_is_the_generators_render(self):
        self.assertEqual((MODULE / "src/classes/dc_potion_table.h").read_text(encoding="utf-8"),
                         potions.table_header(self.potions))

    def test_each_number_is_the_one_the_rows_text_states(self):
        for p in self.potions:
            text = self.sheet[p["d3_id"]]["power_text"]
            for key, pattern in (("seconds", "{:g} seconds"), ("yards", "within {:g} yards"),
                                 ("below_life_pct", "below {:g}%% health")):
                if p[key]:
                    self.assertIn(pattern.format(p[key]), text, p["d3_id"])
        by = {p["power_id"]: p for p in self.potions}
        self.assertEqual((by["leg_potion_tower"]["seconds"], by["leg_potion_fear"]["yards"],
                          by["leg_potion_rejuvenation"]["below_life_pct"]), (5, 12, 50))
        self.assertEqual(by["leg_potion_unfettered"]["seconds"], 0, "Unfettered's seconds are its roll")

    def test_every_shell_and_power_record_is_a_spell_of_its_shape(self):
        for p in self.potions:
            shell = self.spells[p["spell"]]
            self.assertEqual((shell["Name_Lang_enUS"], int(shell["RecoveryTime"])), (p["name"], 30000), p["d3_id"])
            built = bool(self.sheet[p["d3_id"]]["roll_min"])
            if p["power_id"] in ("leg_potion_rejuvenation",) or not built:
                self.assertEqual(p["power_spell"], 0, f"{p['d3_id']}: an instant power or none needs no record")
                continue
            record = self.spells[p["power_spell"]]
            self.assertEqual(record["Name_Lang_enUS"], p["name"])
            aura, target = int(record["EffectAura_1"]), int(record["ImplicitTargetA_1"])
            if p["power_id"] == "leg_potion_fear":
                self.assertEqual((aura, target, int(record["Mechanic"])), (7, 6, 5), "a fear on each enemy")
                continue
            self.assertEqual((aura, target), (4, 1), f"{p['d3_id']}: a buff marker on the drinker")
            self.assertEqual(record["AuraDescription_Lang_enUS"],
                             self.sheet[p["d3_id"]]["power_text"].replace("%d", "$s1").replace("%%", "%"))
            if p["power_id"] == "leg_potion_unfettered":
                self.assertEqual((int(record["EffectAura_2"]), int(record["EffectMiscValue_2"])), (147, 96),
                                 "Ignore Pain's control immunity")

    def test_the_power_table_rolls_exactly_the_potions_with_a_range(self):
        # The table's newest full replacement (legendary_powers_0010; 0005-0007 are frozen on nightly, 0008 and 0009 are tab0h's and ghb4o's).
        sql = (MODULE / "data/sql/db-world/updates/legendary_powers_0010_table.sql").read_text(encoding="utf-8")
        rows = re.findall(r"\('([^']*)',0,'potion','','([^']*)',([\d.]+),([\d.]+),", sql)
        want = [(d3, r["power_id"], r["roll_min"], r["roll_max"]) for d3, r in self.sheet.items() if r["roll_min"]]
        self.assertEqual(sorted(rows), sorted(want))
        self.assertEqual(len(rows), 9)

    def test_every_built_power_has_its_code(self):
        source = CLASSES.read_text(encoding="utf-8")
        for p in self.potions:
            if self.sheet[p["d3_id"]]["roll_min"]:
                self.assertIn(f'"{p["power_id"]}"', source, f"{p['d3_id']}: a rolled power nothing reads")


CODE = r'''
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <map>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>
#include "@COMMON@"
#include "@POTION@"
using uint8 = std::uint8_t;
using int32 = std::int32_t;
using uint32 = std::uint32_t;
using uint64 = std::uint64_t;
enum { ALLSPELLHOOK_ON_CAST, UNITHOOK_MODIFY_HEAL_RECEIVED, UNITHOOK_ON_AURA_APPLY, UNITHOOK_ON_AURA_REMOVE };
enum SpellEffIndex { EFFECT_0 };
enum AuraRemoveMode { AURA_REMOVE_BY_EXPIRE };
struct SpellInfo { uint32 Id; };
struct Spell {};
struct Position {};
struct Guid { uint64 raw; uint64 GetRawValue() const { return raw; } };
struct AuraEffect {
    int32 amount = 1;
    int32 GetAmount() const { return amount; }
    void ChangeAmount(int32 value) { amount = value; }
};
struct Aura {
    uint32 id; int32 duration = -1, maxDuration = -1; AuraEffect effect;
    uint32 GetId() const { return id; }
    void SetDuration(int32 ms) { duration = ms; }
    void SetMaxDuration(int32 ms) { maxDuration = ms; }
    AuraEffect* GetEffect(SpellEffIndex) { return &effect; }
};
struct AuraApplication { Aura* base; Aura* GetBase() const { return base; } };
struct Player;
struct Unit {
    std::map<uint32, Aura> auras;
    bool immune = false;
    virtual ~Unit() = default;
    virtual Player* ToPlayer() { return nullptr; }
};
struct Player : Unit {
    uint64 guid = 7;
    uint32 health = 100, maxHealth = 1000;
    bool alive = true;
    Player* ToPlayer() override { return this; }
    Guid GetGUID() const { return {guid}; }
    uint32 GetHealth() const { return health; }
    uint32 GetMaxHealth() const { return maxHealth; }
    bool IsAlive() const { return alive; }
    Position GetPosition() const { return {}; }
    Aura* AddAura(uint32 id, Unit* target) {
        if (target->immune) return nullptr;
        target->auras[id] = Aura{id};
        return &target->auras[id];
    }
    AuraEffect* GetAuraEffect(uint32 id, SpellEffIndex) {
        auto found = auras.find(id);
        return found == auras.end() ? nullptr : &found->second.effect;
    }
};
struct AllSpellScript {
    AllSpellScript(char const*, std::vector<int>) {}
    virtual ~AllSpellScript() = default;
    virtual void OnSpellCast(Spell*, Unit*, SpellInfo const*, bool) {}
};
struct UnitScript {
    UnitScript(char const*, bool, std::vector<int>) {}
    virtual ~UnitScript() = default;
    virtual void ModifyHealReceived(Unit*, Unit*, uint32&, SpellInfo const*) {}
    virtual void OnAuraApply(Unit*, Aura*) {}
    virtual void OnAuraRemove(Unit*, AuraApplication*, AuraRemoveMode) {}
};

// The sheet: the contributions present, by (stat, id).
std::map<std::pair<DC::Stat, uint64>, DC::Contribution> sheet;
int recomputes = 0;
namespace DC::Stats {
bool AddContribution(uint64, Contribution const& c) { sheet[{c.stat, c.id}] = c; return true; }
bool RemoveContribution(uint64, Source source, Stat stat, uint64 id) {
    if (source != Source::Temporary) throw std::runtime_error("only Temporary");
    sheet.erase({stat, id}); return true;
}
bool Recompute(Player*) { ++recomputes; return true; }
}
// The slot (diablocraft-1z5ye): its shell and its roll.
uint32 slotShell = 0;
std::optional<double> slotRoll;
namespace DC::Inventory {
std::optional<double> ActivePotionRoll(Player*) { return slotRoll; }
uint32 ActivePotionSpell(Player*) { return slotShell; }
}
// The primary resource: 200 points, starting at 10.
double resource = 10;
namespace DC::Resources {
struct Resource {};
Resource fury;
Resource const* Of(uint32 classId) { return classId == 1 ? &fury : nullptr; }
double Max(Player const*, Resource const&) { return 200; }
void Add(Player*, Resource const&, double points) { resource = std::min(200.0, resource + points); }
}
// The enemies within reach of the record and the radius asked.
std::vector<Unit*> nearby;
double askedRadius = 0;
uint32 askedSpell = 0;
namespace DC::Combat {
std::vector<Unit*> Enemies(Player*, uint32 spellId, Position const&, double radius) {
    askedSpell = spellId; askedRadius = radius; return nearby;
}
}
namespace DC::Classes {
uint32 ClassIdOf(Player const*) { return 1; }
namespace {
// The heal is test_potion.py's: here it heals to full, so a Life threshold read after it would never hold.
void RestorePotionLife(Player* player, SpellInfo const*) { if (player) player->health = player->maxHealth; }
void SharePotionCooldown(Player*, SpellInfo const*) {}
@POWERS@
}
}
int checks = 0;
void check(bool ok, char const* name) { ++checks; if (!ok) throw std::runtime_error(name); }
using namespace DC;
using namespace DC::Classes;
Potion::Legendary const& P(char const* power) {
    for (auto const& p : Potion::Legendaries) if (std::string_view(p.powerId) == power) return p;
    throw std::runtime_error(power);
}
void Drink(Player& player, Potion::Legendary const& potion, std::optional<double> roll) {
    slotShell = potion.shell; slotRoll = roll;
    PotionCast cast; SpellInfo info{potion.shell};
    cast.OnSpellCast(nullptr, &player, &info, false);
}
void reset(Player& p) { p.auras.clear(); sheet.clear(); resource = 10; nearby.clear(); p.health = 100; }
int main() {
    PotionPowers hooks;
    // The four stat powers and Regeneration: the record's aura for the text's seconds, the roll as its amount, the
    // sheet's number while it is on.
    struct Want { char const* power; Stat stat; Bucket bucket; double roll, value; };
    for (Want want : {Want{"leg_potion_tower", Stat::Armor, Bucket::Percent, 17, 17},
                      Want{"leg_potion_diamond", Stat::AllResistance, Bucket::Flat, 80, 80},
                      Want{"leg_potion_leech", Stat::LifePerHit, Bucket::Flat, 16000, 16000},
                      Want{"leg_potion_mutilation", Stat::LifePerKill, Bucket::Flat, 45000, 45000},
                      Want{"leg_potion_regeneration", Stat::LifeRegen, Bucket::Flat, 90000, 18000}}) {
        Player player; reset(player);
        auto const& potion = P(want.power);
        Drink(player, potion, want.roll);
        Aura const& aura = player.auras.at(potion.power);
        check(aura.duration == int32(potion.seconds * 1000) && aura.maxDuration == aura.duration, "the text's seconds");
        check(aura.effect.amount == int32(want.roll), "the roll is the aura's amount");
        auto found = sheet.find({want.stat, potion.power});
        check(found != sheet.end() && found->second.value == want.value && found->second.bucket == want.bucket &&
              found->second.source == Source::Temporary, "the sheet's number while the aura is on");
        check(sheet.size() == 1, "one number, on its own stat");
        // The aura goes (its end, a death, a dispel): the number goes with it, even if the core still finds the aura
        // while the hook runs.
        Aura gone = player.auras.at(potion.power);
        AuraApplication application{&player.auras.at(potion.power)};
        hooks.OnAuraRemove(&player, &application, AURA_REMOVE_BY_EXPIRE);
        player.auras.erase(potion.power);
        check(sheet.empty(), "the aura's end takes the number off");
        // A login restores the aura with its saved amount: the number comes back with it.
        player.auras[potion.power] = gone;
        hooks.OnAuraApply(&player, &player.auras.at(potion.power));
        check(sheet.count({want.stat, potion.power}) && sheet.at({want.stat, potion.power}).value == want.value,
              "the restored aura brings its number back");
    }
    {   // Amplification: every heal of the player on itself is that much larger while its aura is on.
        Player player; reset(player);
        auto const& potion = P("leg_potion_amplification");
        uint32 heal = 1000;
        hooks.ModifyHealReceived(&player, &player, heal, nullptr);
        check(heal == 1000, "no aura, no change");
        Drink(player, potion, 25);
        check(player.auras.at(potion.power).duration == int32(potion.seconds * 1000), "for the text's seconds");
        heal = 1000;
        hooks.ModifyHealReceived(&player, &player, heal, nullptr);
        check(heal == 1250, "healing received x (1 + roll/100)");
        Player other;
        heal = 1000;
        hooks.ModifyHealReceived(&player, &other, heal, nullptr);
        check(heal == 1000, "only a heal the player gives itself is placed with certainty");
        check(sheet.empty(), "no sheet number");
    }
    {   // Rejuvenation: the roll's percent of the primary resource, when drunk below the threshold (read before the heal).
        Player player; reset(player);
        auto const& potion = P("leg_potion_rejuvenation");
        player.health = 400;   // 40% < 50%
        Drink(player, potion, 25);
        check(resource == 60, "25% of the 200 maximum restored below the threshold");
        reset(player); player.health = 600;
        Drink(player, potion, 25);
        check(resource == 10, "nothing above the threshold");
        reset(player); player.health = 500;
        Drink(player, potion, 25);
        check(resource == 10, "exactly at the threshold is not below it");
    }
    {   // Fear: every enemy in the text's reach, for the roll's seconds; an immune one is skipped.
        Player player; reset(player);
        auto const& potion = P("leg_potion_fear");
        Unit a, b, immune; immune.immune = true;
        nearby = {&a, &b, &immune};
        Drink(player, potion, 3);
        check(askedRadius == potion.yards && askedSpell == potion.power, "the enemies within the text's yards");
        check(a.auras.at(potion.power).duration == 3000 && b.auras.at(potion.power).duration == 3000, "feared for the roll");
        check(immune.auras.empty() && player.auras.empty(), "no fear on an immune enemy or on the drinker");
    }
    {   // Unfettered: immune for the roll's seconds.
        Player player; reset(player);
        auto const& potion = P("leg_potion_unfettered");
        Drink(player, potion, 6);
        check(player.auras.at(potion.power).duration == 6000 && player.auras.at(potion.power).effect.amount == 6,
              "the immunity lasts the roll");
        check(sheet.empty(), "no sheet number");
    }
    {   // No power: Kulle-Aid and Chaos (not built), a potion with no roll, a shell that is not the slotted one,
        // the Health Potion, a dead drinker.
        for (char const* power : {"leg_potion_kulleaid", "leg_potion_chaos"}) {
            Player player; reset(player);
            Drink(player, P(power), 5);
            check(player.auras.empty() && sheet.empty() && resource == 10, "a power that is not built does nothing");
        }
        Player player; reset(player);
        Drink(player, P("leg_potion_tower"), std::nullopt);
        check(player.auras.empty() && sheet.empty(), "a potion with no roll has no power");
        slotShell = P("leg_potion_diamond").shell; slotRoll = 17;
        PotionCast cast; SpellInfo info{P("leg_potion_tower").shell};
        cast.OnSpellCast(nullptr, &player, &info, false);
        check(player.auras.empty(), "a shell that is not the slotted potion's reads no roll");
        SpellInfo health{Potion::BaseSpell};
        cast.OnSpellCast(nullptr, &player, &health, false);
        check(player.auras.empty(), "the Health Potion has no power");
        player.alive = false;
        Drink(player, P("leg_potion_tower"), 17);
        check(player.auras.empty() && sheet.empty(), "a dead drinker gets no power");
    }
    std::cout << "PASS " << checks << " production potion power checks\n";
}
'''


def build_and_run():
    source = CLASSES.read_text(encoding="utf-8")
    powers = "\n".join(extract(source, signature) for signature in (
        "struct PotionStat\n", "constexpr PotionStat PotionStats[]", "PotionStat const* PotionStatOf(",
        "Potion::Legendary const* PotionByPower(", "void PotionStatSync(", "void PutPotionAura(",
        "void DrinkPotionPower(", "class PotionCast final", "class PotionPowers final"))
    code = (CODE.replace("@COMMON@", (MODULE / "src/common/dc_common.h").as_posix())
            .replace("@POTION@", (MODULE / "src/classes/dc_potion.h").as_posix())
            .replace("@POWERS@", powers))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "test.cpp").write_text(code, encoding="utf-8")
    binary = OUT / "potion_powers_test"
    harness_env.run(["c++", "-std=c++17", "-Wall", "-o", str(binary), str(OUT / "test.cpp")], check=True)
    return harness_env.run([str(binary)], capture_output=True, text=True)


class TheCode(unittest.TestCase):
    def test_the_production_powers(self):
        run = build_and_run()
        self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
        print(run.stdout.strip())


if __name__ == "__main__":
    unittest.main()
