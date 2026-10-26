"""Every skill without a stated cooldown gets its own one-swing recovery (diablocraft-skill-swing-recovery).

    python3 mod-diablocraft/scripts/tests/classes/test_skill_swing_recovery.py

Ruling q-1001-25 A: "Every skill without a stated cooldown gets its own swirl of one swing at your attack
speed. Skills with a stated cooldown keep it. Pressing two DIFFERENT skills at the same moment still works."

The module's own functions are cut out of dc_combat.cpp, dc_abilities.cpp and compiled against doubles:
  real      SwingEligible, SwingRecoveryMilliseconds, StartSwingRecovery, AbilityCast, SendSkillCooldown,
            HandAttacksPerSecond, Abilities::UsesCharges, the generated shell catalogue (dc_spell_shells.h) and
            the primary table (dc_barbarian_primary_data.h);
  data      every shell's real RecoveryTime / CategoryRecoveryTime, read out of the generated spell_shells.sql;
  double    the player (a clock and a cooldown map), the sheet's attacks per second, the cooldown packet.
A press is modelled the way the core does it: refused while the skill's cooldown is up (the module's own
OnSpellCheckCast line, pinned below), otherwise the core installs the record's stated cooldown on the skill's
category and the module's AbilityCast runs where dc_ability_targets::Finish calls it.

MutationsAreCaught puts one old behaviour back at a time and requires the harness to fail.
What this does not run: the real Spell::CheckCast, the client's swirl and drop of a press (the sheet's job).
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import wizard_source  # noqa: E402
import harness_env
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
import barbarian_source  # noqa: E402

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / "mod-diablocraft"
COMBAT_CPP = MODULE / "src/combat/dc_combat.cpp"
ABILITIES_CPP = barbarian_source.CPP
SHELLS_H = MODULE / "src/combat/dc_spell_shells.h"
PRIMARY_H = MODULE / "src/classes/barbarian/dc_barbarian_primary_data.h"
SHELLS_SQL = MODULE / "data/generated/spell_shells.sql"
SCRATCH = ROOT / "azerothcore-wotlk/build/_agent-scratch/skill-swing-recovery"


def definition(marker, source):
    assert source.count(marker) == 1, "%r is not unique" % marker
    start = source.index(marker)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def sql_rows(text):
    """spell_dbc rows by column name: INSERT ... (cols) VALUES (..),(..); tuples with '' quoting."""
    rows = []
    for header in re.finditer(r"INSERT INTO `spell_dbc` \(([^)]*)\) VALUES", text):
        columns = [c.strip(" `") for c in header.group(1).split(",")]
        i = header.end()
        while True:
            while text[i] in " \n,":
                i += 1
            if text[i] != "(":
                break
            i += 1
            values, token, quoted = [], "", False
            while True:
                c = text[i]
                if quoted:
                    if c == "'" and text[i + 1] == "'":
                        token += "'"
                        i += 1
                    elif c == "'":
                        quoted = False
                    else:
                        token += c
                elif c == "'":
                    quoted = True
                elif c in ",)":
                    values.append(token.strip())
                    token = ""
                    if c == ")":
                        i += 1
                        break
                else:
                    token += c
                i += 1
            rows.append(dict(zip(columns, values)))
            while text[i] in " \n":
                i += 1
            if text[i] == ";":
                break
    return rows


def records():
    out = {}
    for row in sql_rows(SHELLS_SQL.read_text(encoding="utf-8")):
        out[int(row["ID"])] = (int(row["RecoveryTime"]), int(row["CategoryRecoveryTime"]), int(row["Category"]))
    return out


def abilities():
    """(id, skill, rune) of every shell in the generated catalogue."""
    src = SHELLS_H.read_text(encoding="utf-8")
    block = src[src.index("Abilities[]"):src.index("inline Ability const* FindAbility")]
    return [(int(i), s, r) for i, s, r in re.findall(r'\{(\d+), "([^"]*)", "([^"]*)", [\d.]+\}', block)]


# Skills that are channels: what dc_ability_targets::Finish tells AbilityCast (Whirlwind, and the Wizard's
# WizardChannel rows, which carry channel_tick_frames_count).
CHANNEL_SKILLS = ("Whirlwind", "Ray of Frost", "Arcane Torrent", "Disintegrate")

HARNESS = r'''
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <mutex>
#include <set>
#include <string>
#include <vector>
using uint32 = std::uint32_t; using uint64 = std::uint64_t; using uint8 = std::uint8_t;
#define CHECK(c) do { if (!(c)) { std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #c); std::exit(3); } } while (0)

#include "@SHELLS@"
#include "@PRIMARY@"

struct SpellInfo { uint32 RecoveryTime = 0, CategoryRecoveryTime = 0, Category = 0; };
static std::map<uint32, SpellInfo> records;
struct SpellMgrD { SpellInfo const* GetSpellInfo(uint32 id) { auto f = records.find(id); return f == records.end() ? nullptr : &f->second; } } spellMgrD;
SpellMgrD* sSpellMgr = &spellMgrD;

struct ObjectGuid { uint64 raw = 0; uint64 GetRawValue() const { return raw; } };
struct Sheet { double attacksPerSecond = 1.0, offhandAttacksPerSecond = 0; };
static std::map<uint64, Sheet> sheets;
namespace DC::Stats { inline Sheet const* Get(uint64 guid) { auto f = sheets.find(guid); return f == sheets.end() ? nullptr : &f->second; } }
struct Player;
namespace DC::Combat::Primaries { inline double AttackSpeed(Player*, uint32, double base) { return base; } }
// The Monk's passives' share of a hand's attack speed (Alacrity, dc_monk_passives_guardians_path.cpp): none here, the speed comes back as it was.
namespace DC::Combat::Monk { inline double AttackSpeed(Player*, uint32, double base) { return base; } }
namespace DC::Combat::Crusader { inline double AttackSpeed(Player*, uint32, double base) { return base; } }
namespace DC::Combat::Necromancer { inline double AttackSpeed(Player*, uint32, double base) { return base; } }
namespace DC::Combat::WitchDoctor { inline double AttackSpeed(Player*, uint32, double base) { return base; } }
// A skill's own attack speed from the item powers (diablocraft-li0ie): no item worn here; test_item_power_math.py drives it.
namespace DC::Combat::ItemPowers { inline double SkillFactor(Player const*, std::string const&, std::string const&) { return 1.0; }
                                     inline double AttackSpeedFactor(Player*) { return 1.0; } }

static uint64 now = 0;                 // the clock, milliseconds
static double cdrFraction = 0;         // a player's Cooldown Reduction, 0..1
struct WorldPacket {};
using PacketCooldowns = std::map<uint32, uint32>;
static int packetsSent = 0; static PacketCooldowns lastPacket;
struct Player {
    ObjectGuid guid{7};
    std::map<uint32, uint64> until;     // spell id -> the moment its cooldown ends
    ObjectGuid GetGUID() const { return guid; }
    bool HasSpellCooldown(uint32 id) const { auto f = until.find(id); return f != until.end() && f->second > now; }
    uint32 Remaining(uint32 id) const { auto f = until.find(id); return f != until.end() && f->second > now ? uint32(f->second - now) : 0; }
    void AddSpellCooldown(uint32 id, uint32, uint32 ms, bool) { until[id] = now + ms; }
    void RemoveSpellCooldown(uint32 id, bool) { until.erase(id); }
    void BuildCooldownPacket(WorldPacket&, int, PacketCooldowns const& c) { lastPacket = c; }
    void SendDirectMessage(WorldPacket*) { ++packetsSent; }
};
constexpr int SPELL_COOLDOWN_FLAG_NONE = 0;

namespace DC::Combat {
// Declared by dc_combat.h in the module; only what the extracted code calls.
inline std::uint32_t ReducedCooldownMilliseconds(Player*, std::uint32_t, std::uint32_t ms) { return uint32(ms * (1.0 - cdrFraction)); }
bool SwingEligible(std::uint32_t);
bool IsStandaloneAbility(std::uint32_t);
std::uint32_t SwingRecoveryMilliseconds(Player*, std::uint32_t, bool offhand = false);
void StartSwingRecovery(Player*, std::uint32_t, bool offhand = false);
}
namespace DC::Combat::Abilities {
using Row = Shells::Ability;
@RUNE@
@USES_CHARGES@
}
namespace DC::Combat {
@SEND@
@HAND@
@SWING@
}
using namespace DC::Combat;

// ---------------------------------------------------------------- the press, as the core does it
static bool IsChannel(uint32 id) {
    auto row = Shells::FindAbility(id);
    if (!row) { for (auto const& a : Shells::ArchonAbilities) if (a.id == id) return std::string(a.name) == "Disintegration Wave"; return false; }
    std::string s = row->skill;
    return s == "Whirlwind" || s == "Ray of Frost" || s == "Arcane Torrent" || s == "Disintegrate";
}
// OnSpellCheckCast refuses while the skill's cooldown is up (pinned in the Python test);
// Spell::cast then installs the record's stated cooldown on the skill and its category
// (Player::AddSpellAndCategoryCooldowns) BEFORE AfterCast, which is where AbilityCast runs.
static bool Press(Player& p, uint32 id, bool triggered = false) {
    if (!triggered && p.HasSpellCooldown(id)) return false;
    SpellInfo const* info = sSpellMgr->GetSpellInfo(id);
    uint32 const stated = info->RecoveryTime ? info->RecoveryTime : info->CategoryRecoveryTime;
    if (stated) {
        // Player::AddSpellAndCategoryCooldowns: the spell itself, and every spell sharing its category when the
        // record states a category recovery. A record with only RecoveryTime stays on that one spell.
        p.AddSpellCooldown(id, 0, stated, true);
        if (info->CategoryRecoveryTime && info->Category)
            for (auto const& row : Shells::Abilities)
                if (sSpellMgr->GetSpellInfo(row.id)->Category == info->Category) p.AddSpellCooldown(row.id, 0, stated, true);
    }
    AbilityCast(&p, id, triggered, IsChannel(id));
    return true;
}
static uint32 IdOf(char const* skill, char const* rune = "") {
    for (auto const& row : Shells::Abilities)
        if (std::string(row.skill) == skill && std::string(row.rune) == rune) return row.id;
    std::fprintf(stderr, "no shell %s %s\n", skill, rune); std::exit(4);
}
static Player fresh(double aps = 1.5, double offhand = 0) {
    Player p; p.guid = ObjectGuid{7}; sheets[7] = Sheet{aps, offhand}; now = 1000; cdrFraction = 0; packetsSent = 0; return p;
}
// an eligible skill of a class: first catalogue row in [lo, hi) with no stated cooldown, not primary, not a charge skill
static uint32 Eligible(uint32 lo, uint32 hi, int skip = 0) {
    for (auto const& row : Shells::Abilities)
        if (row.id >= lo && row.id < hi && SwingEligible(row.id) && !IsChannel(row.id) && skip-- <= 0) return row.id;
    std::fprintf(stderr, "no eligible skill in %u..%u\n", lo, hi); std::exit(4);
}

int main(int argc, char** argv) {
    std::string name = argc > 1 ? argv[1] : "";
@RECORDS@
    uint32 const magicMissile = IdOf("Magic Missile"), hammer = IdOf("Hammer of the Ancients");
    if (name == "wizard_signature_refused_within_one_swing") {
        Player p = fresh(1.5);                       // one swing = 667 ms
        CHECK(Press(p, magicMissile));
        now += 300;  CHECK(!Press(p, magicMissile)); // pressed again inside the swing: refused
        now += 366;  CHECK(!Press(p, magicMissile)); // 666 ms: still the swing
        now += 1;    CHECK(Press(p, magicMissile));  // 667 ms: casts again
    } else if (name == "no_stated_cooldown_refused_within_one_swing") {
        Player p = fresh(1.0);                       // one swing = 1000 ms
        uint32 wizard = Eligible(83000, 90000), barbarian = Eligible(81000, 82000, 3);
        for (uint32 id : {wizard, barbarian, hammer, IdOf("Rend"), IdOf("Seismic Slam")}) {
            now = 5000; p.until.clear();
            CHECK(Press(p, id));
            now += 999; CHECK(!Press(p, id));
            now += 1;   CHECK(Press(p, id));
        }
        CHECK(SwingEligible(hammer));
    } else if (name == "two_different_skills_both_cast") {
        Player p = fresh(1.5);
        uint32 a = magicMissile, b = hammer, c = Eligible(83000, 90000, 2);
        CHECK(Press(p, a) && Press(p, b) && Press(p, c)); // the same instant
        CHECK(!Press(p, a) && !Press(p, b) && !Press(p, c));
        // a skill's swing sits on its own shells only
        auto sa = Shells::FindAbility(a);
        for (auto const& row : Shells::Abilities) {
            if (std::string(row.skill) != sa->skill && p.HasSpellCooldown(row.id) && std::string(row.skill) != Shells::FindAbility(b)->skill
                && std::string(row.skill) != Shells::FindAbility(c)->skill)
                CHECK(false); // a timer leaked onto a skill nobody pressed
        }
    } else if (name == "stated_cooldown_keeps_only_its_own") {
        Player p = fresh(3.0);                      // a quick swing would be 334 ms
        for (char const* skill : {"Ground Stomp", "Leap", "War Cry", "Wrath of the Berserker", "Overpower", "Teleport"}) {
            now = 9000; p.until.clear();
            uint32 id = IdOf(skill);
            SpellInfo const* info = sSpellMgr->GetSpellInfo(id);
            uint32 stated = info->RecoveryTime ? info->RecoveryTime : info->CategoryRecoveryTime;
            CHECK(stated > 0 && !SwingEligible(id));
            CHECK(Press(p, id));
            CHECK(p.Remaining(id) == stated);        // the record's number, and nothing added to it
            now += stated - 1; CHECK(!Press(p, id));
            now += 1;          CHECK(Press(p, id));
        }
    } else if (name == "more_attack_speed_shortens_cdr_does_not") {
        uint32 slow = 0, fast = 0, withCdr = 0;
        { Player p = fresh(1.0); Press(p, magicMissile); slow = p.Remaining(magicMissile); }
        { Player p = fresh(2.0); Press(p, magicMissile); fast = p.Remaining(magicMissile); }
        { Player p = fresh(2.0); cdrFraction = 0.5; Press(p, magicMissile); withCdr = p.Remaining(magicMissile); }
        CHECK(slow == 1000 && fast == 500);
        CHECK(withCdr == fast);                      // Cooldown Reduction does not shorten the swing
        { Player p = fresh(1.25); Press(p, hammer); CHECK(p.Remaining(hammer) == 800); }
        { Player p = fresh(0.0); Press(p, hammer); CHECK(p.Remaining(hammer) == 0); } // no attack speed: no rate, no swing
    } else if (name == "main_hand_swing_without_alternation") {
        Player p = fresh(1.0, 2.0);                  // dual wielding: the off hand is quicker
        CHECK(SwingRecoveryMilliseconds(&p, hammer) == 1000);          // main hand
        CHECK(SwingRecoveryMilliseconds(&p, hammer, true) == 500);     // the hand asked for
    } else if (name == "channels_swing_when_they_end") {
        for (char const* skill : {"Whirlwind", "Ray of Frost", "Arcane Torrent", "Disintegrate"}) {
            Player p = fresh(1.0);
            uint32 id = IdOf(skill);
            CHECK(Press(p, id));
            CHECK(!p.HasSpellCooldown(id));          // none while the channel runs
            now += 3000; CHECK(Press(p, id));        // a press during/after launch is not refused by a swing
            StartSwingRecovery(&p, id);              // the channel ends (EndChannel / StopWhirlwind)
            CHECK(p.Remaining(id) == 1000);
            now += 999; CHECK(!Press(p, id));
            now += 1;   CHECK(Press(p, id));
        }
    } else if (name == "charge_skills_keep_only_their_charges") {
        for (auto const& pair : {std::make_pair("Furious Charge", ""), std::make_pair("Revenge", ""), std::make_pair("Avalanche", "Tectonic Rift")}) {
            Player p = fresh(1.0);
            uint32 id = IdOf(pair.first, pair.second);
            CHECK(DC::Combat::Abilities::UsesCharges(id) && !SwingEligible(id));
            p.until.clear(); CHECK(Press(p, id));
            // nothing of ours between charges: whatever stated cooldown the record carries is the core's, the swing is not added
            SpellInfo const* info = sSpellMgr->GetSpellInfo(id);
            uint32 stated = info->RecoveryTime ? info->RecoveryTime : info->CategoryRecoveryTime;
            CHECK(p.Remaining(id) == stated);
        }
        CHECK(!DC::Combat::Abilities::UsesCharges(IdOf("Avalanche")));   // the plain Avalanche and its other runes have no charge system
        CHECK(!DC::Combat::Abilities::UsesCharges(IdOf("Avalanche", "Glacier")));
    } else if (name == "a_triggered_cast_owes_nothing") {
        Player p = fresh(1.0);
        CHECK(Press(p, magicMissile, true));
        CHECK(p.Remaining(magicMissile) == 0 && packetsSent == 0);
    } else if (name == "the_swing_is_sent_to_the_client") {
        Player p = fresh(2.0);
        CHECK(Press(p, magicMissile));
        CHECK(packetsSent == 1 && lastPacket.count(magicMissile) && lastPacket[magicMissile] == 500);
        // every shell of the skill (its runes share the timer), and no other skill's
        for (auto const& row : Shells::Abilities) {
            bool mine = std::string(row.skill) == "Magic Missile";
            CHECK(mine == (lastPacket.count(row.id) == 1));
            CHECK(mine == p.HasSpellCooldown(row.id));
        }
    } else if (name == "wormhole_recast_still_works") {
        // dc_wizard.cpp clears Teleport's cooldown for the recasts inside the Wormhole window
        // (SendSkillCooldown(player, id, 0)). Teleport states a cooldown, so the swing is not added and
        // the window works as before.
        Player p = fresh(1.5);
        uint32 id = IdOf("Teleport", "Wormhole");
        CHECK(!SwingEligible(id));
        CHECK(Press(p, id));
        for (int recast = 0; recast < 3; ++recast) {
            SendSkillCooldown(&p, id, 0);            // the Wormhole window clears the cooldown after each cast
            CHECK(Press(p, id));                     // and the recast is not held by a swing
        }
        SendSkillCooldown(&p, id, 20000);            // the window's end puts the cooldown on
        CHECK(!Press(p, id));
    } else if (name == "archon_form_abilities_follow_the_rule") {
        uint32 const strike = 83274, blast = 83275, wave = 83276, slow = 83277, teleport = 83278;
        for (uint32 id : {strike, slow}) {
            Player p = fresh(1.0);
            CHECK(SwingEligible(id) && IsStandaloneAbility(id) && !Shells::FindAbility(id));
            CHECK(Press(p, id));
            now += 999; CHECK(!Press(p, id));
            now += 1;   CHECK(Press(p, id));
        }
        for (uint32 id : {blast, teleport}) {          // stated 2000 ms: kept exactly, no swing added
            Player p = fresh(3.0);
            CHECK(!SwingEligible(id));
            CHECK(Press(p, id)); CHECK(p.Remaining(id) == 2000);
            now += 1999; CHECK(!Press(p, id)); now += 1; CHECK(Press(p, id));
        }
        {   Player p = fresh(1.0);                      // the channel: none at launch, one swing when it ends
            CHECK(SwingEligible(wave) && Press(p, wave) && !p.HasSpellCooldown(wave));
            StartSwingRecovery(&p, wave); CHECK(p.Remaining(wave) == 1000);
            now += 999; CHECK(!Press(p, wave)); now += 1; CHECK(Press(p, wave)); }
        {   Player p = fresh(2.0);                      // two different skills both cast; no shared timer
            CHECK(Press(p, strike) && Press(p, slow) && Press(p, magicMissile) && Press(p, hammer));
            CHECK(p.Remaining(strike) == 500 && p.Remaining(slow) == 500);
            CHECK(!p.HasSpellCooldown(wave) && !p.HasSpellCooldown(83100 + 1));   // nothing leaks onto an unpressed skill
            cdrFraction = 0.5; Player q = fresh(2.0); cdrFraction = 0.5; Press(q, strike); CHECK(q.Remaining(strike) == 500); }
    } else if (name == "a_sibling_rune_with_a_stated_cooldown_keeps_it") {
        // diablocraft-xfvx: Wave of Force Impactful Wave states 5 s, Static Pulse states none. Swapping runes out of
        // combat and casting the one with no cooldown must not replace the stated rune's remaining time.
        uint32 const stated = IdOf("Wave of Force", "Impactful Wave"), free = IdOf("Wave of Force", "Static Pulse");
        Player p = fresh(1.5);
        CHECK(!SwingEligible(stated) && SwingEligible(free));
        CHECK(Press(p, stated)); CHECK(p.Remaining(stated) == 5000);
        now += 1000;
        CHECK(p.Remaining(stated) == 4000);
        CHECK(Press(p, free));                           // its own swing (667 ms) ...
        CHECK(p.Remaining(free) == 667);
        CHECK(p.Remaining(stated) == 4000);              // ... and the stated rune keeps what it had
        CHECK(!lastPacket.count(stated) && lastPacket.count(free));
        { Player q = fresh(1.5); uint32 meteorStated = IdOf("Meteor", "Molten Impact"), meteorFree = IdOf("Meteor", "Comet");
          CHECK(Press(q, meteorStated)); now += 2000; CHECK(Press(q, meteorFree));
          CHECK(q.Remaining(meteorStated) == 13000); }
    } else if (name == "every_skill_is_classified_by_its_record_not_its_class") {
        int eligible = 0, wizard = 0, barbarian = 0, stated = 0, primaries = 0, charge = 0;
        for (auto const& row : Shells::Abilities) {
            SpellInfo const* info = sSpellMgr->GetSpellInfo(row.id);
            bool isPrimary = PrimaryData::Find(row.id) != nullptr;
            bool hasStated = info->RecoveryTime || info->CategoryRecoveryTime;
            std::string sk = row.skill;   // the expectation is written out here, not read from UsesCharges
            bool charges = sk == "Revenge" || sk == "Furious Charge" || (sk == "Avalanche" && std::string(row.rune) == "Tectonic Rift");
            bool expect = !isPrimary && !hasStated && !charges;
            CHECK(SwingEligible(row.id) == expect);
            eligible += expect; stated += hasStated; primaries += isPrimary; charge += charges;
            if (expect) (row.id >= 83000 ? wizard : barbarian)++;
        }
        CHECK(wizard > 0 && barbarian > 0);
        for (auto const& a : Shells::ArchonAbilities) {      // the form abilities, by the same record rule
            SpellInfo const* info = sSpellMgr->GetSpellInfo(a.id);
            CHECK(SwingEligible(a.id) == !(info->RecoveryTime || info->CategoryRecoveryTime));
        }
        std::printf("eligible %d (wizard %d, barbarian %d) of %zu shells; stated %d, primaries %d, charge %d\n",
                    eligible, wizard, barbarian, sizeof(Shells::Abilities) / sizeof(Shells::Abilities[0]), stated, primaries, charge);
    } else { std::fprintf(stderr, "no scenario %s\n", name.c_str()); return 2; }
    std::printf("PASS %s\n", name.c_str());
    return 0;
}
'''

SCENARIOS = (
    "wizard_signature_refused_within_one_swing", "no_stated_cooldown_refused_within_one_swing",
    "two_different_skills_both_cast", "stated_cooldown_keeps_only_its_own", "more_attack_speed_shortens_cdr_does_not",
    "main_hand_swing_without_alternation", "channels_swing_when_they_end", "charge_skills_keep_only_their_charges",
    "a_triggered_cast_owes_nothing", "the_swing_is_sent_to_the_client", "wormhole_recast_still_works",
    "every_skill_is_classified_by_its_record_not_its_class", "archon_form_abilities_follow_the_rule",
    "a_sibling_rune_with_a_stated_cooldown_keeps_it",
)


def build(name, combat_text=None, abilities_text=None):
    combat = "".join(p.read_text(encoding="utf-8") for p in [COMBAT_CPP.parent / "dc_combat_internal.h", *sorted(COMBAT_CPP.parent.glob("dc_combat*.cpp"))]) if combat_text is None else combat_text
    ability = ABILITIES_CPP.read_text(encoding="utf-8") if abilities_text is None else abilities_text
    recs = records()
    lines = "".join('    records[%d] = SpellInfo{%d, %d, %d};\n' % (i, rt, crt, cat) for i, (rt, crt, cat) in sorted(recs.items()))
    send = definition("void SendSkillCooldown(Player* player, std::uint32_t spellId, std::uint32_t milliseconds)", combat)
    hand = definition("double HandAttacksPerSecond(Player* player, std::uint32_t spellId, bool offhand)", combat)
    swing = "\n".join((
        definition("bool IsStandaloneAbility(std::uint32_t spellId)", combat),
        definition("bool SwingEligible(std::uint32_t spellId)", combat),
        definition("std::uint32_t SwingRecoveryMilliseconds(Player* player, std::uint32_t spellId, bool offhand)", combat),
        definition("void StartSwingRecovery(Player* player, std::uint32_t spellId, bool offhand)", combat),
        definition("void AbilityCast(Player* player, std::uint32_t spellId, bool triggered, bool channel)", combat)))
    code = (HARNESS.replace("@SHELLS@", str(SHELLS_H)).replace("@PRIMARY@", str(PRIMARY_H))
            .replace("@RUNE@", definition("bool Rune(Row const& row, char const* name)", ability))
            .replace("@USES_CHARGES@", definition("bool UsesCharges(uint32 id)", ability))
            .replace("@SEND@", send).replace("@HAND@", hand).replace("@SWING@", swing).replace("@RECORDS@", lines))
    folder = SCRATCH / name
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / "harness.cpp"
    source.write_text(code, encoding="utf-8")
    return harness_env.build([source], flags=["-std=c++17", "-O0", "-UNDEBUG", "-Wall", "-Wno-unused-function"])


def run(binary, scenario):
    ran = harness_env.run([str(binary), scenario], capture_output=True, text=True)
    return ran.returncode, ran.stdout, ran.stderr


_main = {}


def main_binary():
    if "b" not in _main:
        _main["b"] = build("main")
    return _main["b"]


class Rule(unittest.TestCase):
    pass


def make(scenario):
    def test(self):
        code, out, err = run(main_binary(), scenario)
        self.assertEqual(code, 0, "%s\n%s\n%s" % (scenario, out, err))
        self.assertIn("PASS " + scenario, out)
    return test


for _name in SCENARIOS:
    setattr(Rule, "test_" + _name, make(_name))


class TheModulePins(unittest.TestCase):
    """What the harness mirrors and cannot run: the module's own text."""
    combat = "".join(p.read_text(encoding="utf-8") for p in [COMBAT_CPP.parent / "dc_combat_internal.h", *sorted(COMBAT_CPP.parent.glob("dc_combat*.cpp"))])

    def test_a_press_is_refused_on_cooldown_before_any_cost(self):
        check = self.combat[self.combat.index("// Recovery before Fury, for every skill"):]
        check = check[:check.index("Abilities::Ready(player, spell->GetSpellInfo()->Id)")]
        self.assertIn("player->HasSpellCooldown(spell->GetSpellInfo()->Id)", check)
        self.assertIn("SPELL_FAILED_NOT_READY", check)

    def test_finish_hands_every_cast_to_the_rule(self):
        finish = self.combat[self.combat.index("void Finish()\n            {\n                Player* player = GetCaster()->ToPlayer();\n                if (!paid"):]
        finish = finish[:finish.index("// The cooldown is the core's:")]
        self.assertIn("AbilityCast(player, shell.spellId, GetSpell()->IsTriggered(),", finish)
        self.assertIn('Abilities::PaysByTick(shell.skill) || WizardChannel(shell)', finish)

    def test_channels_swing_when_they_end(self):
        self.assertIn("StopChannel(player, true);", self.combat)
        self.assertEqual(self.combat.count("StopChannel(player, true);"), 2)
        self.assertIn("StartSwingRecovery(player, ended);", self.combat)
        ability = ABILITIES_CPP.read_text(encoding="utf-8")
        self.assertIn("if (ended && p->IsAlive()) StartSwingRecovery(p, ended);", ability)

    def test_the_rule_names_no_class(self):
        for marker in ("bool SwingEligible(", "std::uint32_t SwingRecoveryMilliseconds(", "void StartSwingRecovery(", "void AbilityCast("):
            body = definition(marker, self.combat)
            for word in ("Barbarian", "Wizard", "getClass", "CLASS_", "8310", "8100"):
                self.assertNotIn(word, body, marker + " must read the record and the catalogue, not a class")

    def test_the_wormhole_branch_is_untouched(self):
        wizard = wizard_source.CPP.read_text(encoding="utf-8")
        self.assertIn("SendSkillCooldown(player, id, 0);", wizard)
        self.assertIn("SendSkillCooldown(p, id, SkillCooldownMilliseconds(p, id));", wizard)


MUTATIONS = [
    ("the form abilities are not abilities",
     "if ((!Shells::FindAbility(spellId) && !IsStandaloneAbility(spellId)) || PrimaryData::Find(spellId))",
     "if (!Shells::FindAbility(spellId) || PrimaryData::Find(spellId))",
     ["archon_form_abilities_follow_the_rule", "every_skill_is_classified_by_its_record_not_its_class"]),
    ("a sibling rune's stated cooldown is overwritten",
     "if (own && std::string(row.skill) == own->skill && SwingEligible(row.id))",
     "if (own && std::string(row.skill) == own->skill)",
     ["a_sibling_rune_with_a_stated_cooldown_keeps_it"]),
    ("the form ability gets the swing on a catalogue shell only",
     "if (!own)\n        {\n            player->AddSpellCooldown(spellId, 0, milliseconds, true);\n            cooldowns[spellId] = milliseconds;\n        }",
     "",
     ["archon_form_abilities_follow_the_rule"]),
    ("today's behaviour: a press starts no swing",
     "if (triggered || channel)\n            return;\n        StartSwingRecovery(player, spellId);",
     "return;",
     ["wizard_signature_refused_within_one_swing", "no_stated_cooldown_refused_within_one_swing", "two_different_skills_both_cast"]),
    ("a stated cooldown also gets a swing",
     "if (!info || info->RecoveryTime || info->CategoryRecoveryTime)\n            return false;",
     "if (!info)\n            return false;",
     ["stated_cooldown_keeps_only_its_own", "every_skill_is_classified_by_its_record_not_its_class", "wormhole_recast_still_works"]),
    ("cooldown reduction shortens the swing",
     "return uint32(std::clamp(std::ceil(1.0 / aps * 1000), 0.0, double(UINT32_MAX)));",
     "return ReducedCooldownMilliseconds(player, spellId, uint32(std::ceil(1.0 / aps * 1000)));",
     ["more_attack_speed_shortens_cdr_does_not"]),
    ("the swing reads the wrong hand",
     "double const aps = HandAttacksPerSecond(player, spellId, offhand);\n        if (aps <= 0)\n            return 0;",
     "double const aps = HandAttacksPerSecond(player, spellId, true);\n        if (aps <= 0)\n            return 0;",
     ["main_hand_swing_without_alternation"]),
    ("a triggered cast starts a swing",
     "if (triggered || channel)\n            return;",
     "if (channel)\n            return;",
     ["a_triggered_cast_owes_nothing"]),
    ("a channel swings at launch",
     "if (triggered || channel)\n            return;",
     "if (triggered)\n            return;",
     ["channels_swing_when_they_end"]),
    ("the rule only knows ids below the Wizard's",
     "if ((!Shells::FindAbility(spellId) && !IsStandaloneAbility(spellId)) || PrimaryData::Find(spellId))\n            return false;",
     "if ((!Shells::FindAbility(spellId) && !IsStandaloneAbility(spellId)) || PrimaryData::Find(spellId) || spellId >= 83000)\n            return false;",
     ["wizard_signature_refused_within_one_swing", "every_skill_is_classified_by_its_record_not_its_class"]),
    ("the rule only knows the Wizard",
     "if ((!Shells::FindAbility(spellId) && !IsStandaloneAbility(spellId)) || PrimaryData::Find(spellId))\n            return false;",
     "if ((!Shells::FindAbility(spellId) && !IsStandaloneAbility(spellId)) || PrimaryData::Find(spellId) || spellId < 83000)\n            return false;",
     ["no_stated_cooldown_refused_within_one_swing"]),
    ("a primary gets the swing rule too",
     "if ((!Shells::FindAbility(spellId) && !IsStandaloneAbility(spellId)) || PrimaryData::Find(spellId))\n            return false;",
     "if (!Shells::FindAbility(spellId) && !IsStandaloneAbility(spellId))\n            return false;",
     ["every_skill_is_classified_by_its_record_not_its_class"]),
    ("the swing is installed on one shell only",
     "if (own && std::string(row.skill) == own->skill && SwingEligible(row.id))",
     "if (own && row.id == spellId)",
     ["the_swing_is_sent_to_the_client"]),
]

ABILITY_MUTATIONS = [
    ("Revenge is not a charge skill",
     'return skill == "Revenge" || skill == "Furious Charge"',
     'return skill == "Furious Charge"',
     ["charge_skills_keep_only_their_charges", "every_skill_is_classified_by_its_record_not_its_class"]),
    ("Tectonic Rift is not a charge skill",
     '(skill == "Avalanche" && Rune(*r, "Tectonic Rift"))', "false",
     ["charge_skills_keep_only_their_charges"]),
]


class MutationsAreCaught(unittest.TestCase):
    pass


def make_mutation(index, name, old, new, scenarios, abilities):
    def test(self):
        source = (ABILITIES_CPP if abilities else COMBAT_CPP).read_text(encoding="utf-8")
        self.assertEqual(source.count(old), 1, "the text this break targets is not there once: %r" % old[:70])
        mutated = source.replace(old, new)
        binary = build("mutation-%d" % index, None if abilities else mutated, mutated if abilities else None)
        for scenario in scenarios:
            code, out, err = run(binary, scenario)
            self.assertNotEqual(code, 0, "%r survived scenario %s\n%s" % (name, scenario, out))
    return test


for _i, (_n, _o, _w, _s) in enumerate(MUTATIONS):
    setattr(MutationsAreCaught, "test_" + re.sub(r"\W+", "_", _n), make_mutation(_i, _n, _o, _w, _s, False))
for _i, (_n, _o, _w, _s) in enumerate(ABILITY_MUTATIONS):
    setattr(MutationsAreCaught, "test_" + re.sub(r"\W+", "_", _n), make_mutation(100 + _i, _n, _o, _w, _s, True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
