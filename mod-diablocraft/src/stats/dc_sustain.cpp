/*
 * World of DiabloCraft - the four sustain stats (01-stats §2, stats.csv rows
 * 15, 16, 17 and 20).
 *
 * Life Regen, Life per Hit, Life per Kill and Thorns all roll on items, are
 * granted by Paragon and sum through the stat store; this file is the only
 * place that spends them. Every formula and every exclusion below is the
 * matching stats.csv row, and no number here is invented.
 */

#include "dc_stats.h"

#include "../combat/dc_combat.h"
#include "../combat/dc_gem_powers.h"
#include "../classes/dc_classes.h"
#include "../classes/dc_resources.h"
#include "dc_stat_readers.h"

#include "Creature.h"
#include "Log.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <mutex>
#include <unordered_map>

namespace DC::Stats
{
namespace
{
// spell_shells.csv, kind "stat". DealHit needs a real SpellInfo for the school
// and the combat-log line; generate_spells.py emits this one for Thorns.
constexpr std::uint32_t THORNS_SHELL = 81184;
// The three Life stats need one each for the same reason, on the heal side:
// Unit::HealBySpell builds a HealInfo, and HealInfo demands a SpellInfo.
constexpr std::uint32_t LIFE_REGEN_SHELL = 81185;
constexpr std::uint32_t LIFE_PER_HIT_SHELL = 81186;
constexpr std::uint32_t LIFE_PER_KILL_SHELL = 81187;
// stats.csv row 17: "Continuously restores Life every second".
constexpr std::uint32_t REGEN_PERIOD_MS = 1000;

std::mutex regenMutex;
std::unordered_map<std::uint64_t, std::uint32_t> regenElapsed;

// Thorns damage is dealt from inside the core's own damage path, and a Reflects
// Damage elite answers it with damage of its own, which lands straight back
// here. This ends that at the first bounce. Maps update on several threads, so
// the flag is per thread; a single hit never crosses one.
thread_local bool resolvingThorns = false;

struct ThornsGuard
{
    ThornsGuard() { resolvingThorns = true; }
    ~ThornsGuard() { resolvingThorns = false; }
};

// Every class with a D3 sheet sustains from it:
// the same one gate as the stat sheet and the hit path.
bool Sheeted(Player const* player) { return player && DC::Classes::Playable(player); }

double Sheet(Player* player, Stat stat)
{
    auto sheet = Get(player->GetGUID().GetRawValue());
    return sheet ? (*sheet)[stat] : 0.0;
}

// Every one of the three Life stats restores a flat amount out of the sheet.
// The core clamps the result to max Life itself; a dead character is left dead.
//
// This goes through the core's heal path rather than ModifyHealth. ModifyHealth
// moves the health field and tells the client nothing at all: no green number
// over the character, no combat-log line, so Life Regen ticking once a second
// was invisible and indistinguishable from not working. Unit::HealBySpell sends
// SMSG_SPELLHEALLOG, which is what draws both. The player is healer and target
// alike; the school comes from the shell so the C++ and the generator cannot
// drift apart.
void Restore(Player* player, double life, std::uint32_t shell, char const* source)
{
    if (!player->IsAlive() || life <= 0 || player->GetHealth() >= player->GetMaxHealth())
        return;
    int32 const amount = static_cast<int32>(std::min<double>(
        std::llround(life), static_cast<double>(std::numeric_limits<int32>::max())));
    if (amount <= 0)
        return;
    SpellInfo const* info = sSpellMgr->GetSpellInfo(shell);
    if (!info)
    {
        // Heal anyway - losing the Life would be worse than losing the packet -
        // but say so loudly, because every tick will hit this line.
        player->ModifyHealth(amount);
        LOG_ERROR("server", "[DC sustain] shell {} for {} is missing; apply "
                            "combat_0001_spell_shells.sql. Healed silently.", shell, source);
        return;
    }
    HealInfo heal(player, player, static_cast<uint32>(amount), info,
                  SpellSchoolMask(info->SchoolMask));
    int32 const gained = player->HealBySpell(heal, false);
    LOG_DEBUG("module.dc.combat", "[DC sustain] {} restored {} Life to {} ({}/{})", source, gained,
             player->GetName(), player->GetHealth(), player->GetMaxHealth());
}

// stats.csv row 17. Total_LPS is already on the sheet - flat sources times the
// % Life Regeneration bucket, in dc_common.cpp's Calculate - so one second of
// it goes in per tick, in and out of combat alike.
void Regen(Player* player, std::uint32_t diff)
{
    if (!Sheeted(player))
        return;
    std::uint32_t ticks = 0;
    {
        std::lock_guard<std::mutex> lock(regenMutex);
        std::uint32_t& elapsed = regenElapsed[player->GetGUID().GetRawValue()];
        elapsed += diff;
        ticks = elapsed / REGEN_PERIOD_MS;
        elapsed -= ticks * REGEN_PERIOD_MS;
    }
    if (ticks)
        Restore(player, Sheet(player, Stat::LifeRegen) * ticks, LIFE_REGEN_SHELL, "Life Regen");
}

// stats.csv row 16: a flat amount per monster the player slays.
void Killed(Player* killer)
{
    if (Sheeted(killer))
        Restore(killer, Sheet(killer, Stat::LifePerKill), LIFE_PER_KILL_SHELL, "Life per Kill");
}

// One Thorns hit of `amount` from `from` to `to`: Physical, no critical, under the Thorns shell. Struck (a hit taken) and ThornsHit (an attack
// made, Hack) both deal it.
void DealThorns(Player* from, Unit* to, double amount)
{
    if (amount <= 0)
        return;
    DC::Combat::Hit hit;
    hit.skillName = "Thorns";
    hit.school = SPELL_SCHOOL_MASK_NORMAL;
    hit.total = amount;
    hit.crit = 1.0;
    hit.critical = false;
    ThornsGuard guard;
    DC::Combat::DealHit(from, to, THORNS_SHELL, hit);
    LOG_DEBUG("module.dc.combat", "[DC sustain] Thorns dealt {} to {} for {}", hit.total, to->GetGUID().ToString(), from->GetName());
}

// stats.csv row 20. The sheet value is already Sheet_Thorns x (1 + % Thorns) x
// (1 + Strength / 100) - Calculate does that multiply - so this deals it as it
// stands. It cannot critically strike, and all of it is Physical.
void Struck(Unit* attacker, Player* victim)
{
    // Moratorium's payment is the debt of a hit Thorns already answered, not a new hit.
    if (resolvingThorns || DC::Combat::GemPowers::PayingStagger() || !attacker || !Sheeted(victim) || attacker == victim)
        return;
    if (!victim->IsAlive() || !attacker->IsAlive() || !victim->IsValidAttackTarget(attacker))
        return;
    DealThorns(victim, attacker, Sheet(victim, Stat::Thorns));
}

class SustainPlayer final : public PlayerScript
{
public:
    SustainPlayer() : PlayerScript("dc_sustain_player",
        {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_CREATURE_KILL, PLAYERHOOK_ON_LOGOUT}) { }

    void OnPlayerUpdate(Player* player, uint32 diff) override { Regen(player, diff); }
    void OnPlayerCreatureKill(Player* killer, Creature*) override { Killed(killer); }
    void OnPlayerLogout(Player* player) override
    {
        std::lock_guard<std::mutex> lock(regenMutex);
        regenElapsed.erase(player->GetGUID().GetRawValue());
    }
};

class SustainUnit final : public UnitScript
{
public:
    SustainUnit() : UnitScript("dc_sustain_unit", true, {UNITHOOK_ON_DAMAGE}) { }

    void OnDamage(Unit* attacker, Unit* victim, uint32& damage) override
    {
        if (damage)
            Struck(attacker, victim ? victim->ToPlayer() : nullptr);
    }
};
}

// stats.csv row 15. Patch 2.1+ restores 100% of the sheet value once per cast
// that hit at least one target, so combat calls this once for a connected cast
// and never for a splash target: the same row excludes Area Damage, Thorns and
// passive/secondary item procs.
void SkillHit(Player* player)
{
    if (Sheeted(player))
        Restore(player, Sheet(player, Stat::LifePerHit), LIFE_PER_HIT_SHELL, "Life per Hit");
}

void ThornsHit(Player* player, Unit* target, double amount)
{
    if (!Sheeted(player))
        return;
    if (resolvingThorns || DC::Combat::GemPowers::PayingStagger() || !target || target == player)
        return;
    if (!player->IsAlive() || !target->IsAlive() || !player->IsValidAttackTarget(target))
        return;
    DealThorns(player, target, amount);
}

// d3planner lifefury: N Life for each Fury point spent. Only the class whose resource is Fury spends it; the heal goes
// through the Life per Hit shell (a shell of its own would need a client record).
void FurySpent(Player* player, double fury)
{
    if (!Sheeted(player) || fury <= 0 || DC::Classes::ClassIdOf(player) != DC::Resources::Fury.classId)
        return;
    if (auto const sheet = Get(player->GetGUID().GetRawValue()))
        Restore(player, Readers::LifeForFurySpent(*sheet, fury), LIFE_PER_HIT_SHELL, "Life per Fury Spent");
}

void RegisterSustainScripts()
{
    new SustainPlayer();
    new SustainUnit();
}
}
