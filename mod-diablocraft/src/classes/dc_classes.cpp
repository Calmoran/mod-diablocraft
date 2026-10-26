#include "dc_classes.h"
#include "barbarian/dc_barbarian.h"
#include "follower/dc_follower_skills.h"
#include "../combat/dc_passives.h"
#include "../combat/dc_spell_shells.h"
#include "dc_potion.h"
#include "dc_resources.h"

#include "../combat/dc_combat.h"
#include "../common/dc_request_gap.h"
#include "../common/dc_tunables.h"
#include "../items/dc_inventory.h"
#include "../rifts/dc_rifts.h"
#include "../stats/dc_stats.h"

#include "Chat.h"
#include "DBCStores.h"
#include "DatabaseEnv.h"
#include "Log.h"
#include "Map.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "Spell.h"
#include "SpellAuraEffects.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "WorldSession.h"

#include <algorithm>
#include <cmath>
#include <mutex>
#include <optional>
#include <sstream>
#include <string_view>
#include <unordered_map>
#include <unordered_set>

// Literal audit (docs/research/literal-audit-claude.md): the numbers below are
// constants, not tunables - recorded here, nothing else changes.
// Constant (6): LIMIT 6 on the default-skill-bar query; Should use ActiveSlots rather than repeat it.

namespace DC::Classes
{
// The bar's shape, read from dc_tunables rather than compiled in.
// Both rows are D3's published values, so
// `.dc tunables get combat active_skill_slots` answers 6 with no tuned_value
// until the sheet sets one.
unsigned ActiveSlots()
{
    return static_cast<unsigned>(DC::Tunables::Get("combat", "active_skill_slots"));
}

unsigned PassiveSlots()
{
    return static_cast<unsigned>(DC::Tunables::Get("combat", "passive_skill_slots"));
}

namespace
{
constexpr std::uint32_t TOWN_PORTAL_SHELL = 81167;
// K2: the level each passive slot opens at, one published row per slot
// (data/d3/character_rules.csv). `slot` is 0-based, so slot 0
// reads combat/passive_slot_1_unlock_level.
//
// A slot with no row has NO GATE and stays locked. That
// is the whole reason this returns a bool: a missing row reads 0 through Get(),
// and `level >= 0` would open the slot to a level-1 character instead of
// keeping it shut. Nothing is invented and no gate is guessed from a
// neighbouring slot; a fifth slot opens the day the sheet gets a
// passive_slot_5_unlock_level row, and not before. dc_skillbar.lua
// carries the same rule with the same rows, so both sides agree.
std::string PassiveSlotKey(unsigned slot)
{
    return "passive_slot_" + std::to_string(slot + 1) + "_unlock_level";
}

bool PassiveSlotGate(unsigned slot, unsigned& unlockLevel)
{
    std::string const key = PassiveSlotKey(slot);
    if (!DC::Tunables::Has("combat", key))
        return false;
    unlockLevel = static_cast<unsigned>(DC::Tunables::Get("combat", key));
    return true;
}

// B1+B2: one class-keyed catalogue, where three Barbarian tables used to be.
// A row carries no English - the labels are joined from dc_class_label - so a
// renamed skill cannot move a row, and a second class is data rather than a
// second set of tables and a second branch in every gate.
struct PairHash
{
    std::size_t operator()(std::pair<std::uint32_t, std::string> const& key) const
    {
        return std::hash<std::uint32_t>()(key.first) ^ (std::hash<std::string>()(key.second) << 1);
    }
};

struct CatalogueEntry
{
    std::uint32_t classId = 0, skillId = 0, runeId = 0, spellId = 0, indicatorSpellId = 0;
    unsigned unlockLevel = 1;
    std::string category;
};

std::mutex dataMutex;
// K3: saved picks are spell ids now, so the id index is what the bar reads.
// The label key stays for the ONE place a name legitimately arrives - a player
// typing `.dc skill <name>` - and the label map turns an id back into the text
// the client shows. Neither is a join any code performs on saved data.
std::map<std::pair<std::uint32_t, std::string>, CatalogueEntry> catalogue;
std::unordered_map<std::uint32_t, CatalogueEntry> catalogueById;
std::unordered_map<std::uint32_t, std::pair<std::string, std::string>> labelById;
std::map<std::pair<std::uint32_t, std::string>, unsigned> classPassives;
std::unordered_map<std::uint32_t, std::string> passiveNameById;
std::unordered_map<std::pair<std::uint32_t, std::string>, std::uint32_t, PairHash> passiveIdByName;
std::unordered_map<unsigned, std::uint32_t> classMap;       // wow class id -> class_id
// wow class id -> class_map.csv's primary_stat ("Strength", "Intelligence"),
// the main stat a hit scales with.
std::unordered_map<unsigned, std::string> primaryStatMap;
// class_id -> the shells that class learns: its catalogue's skills and runes
// and its passives, each one that has a spell record.
// For the Barbarian this is exactly 81000-81156, the range this
// used to read for every class, which taught a Wizard the Barbarian's skills
// and none of its own.
std::unordered_map<std::uint32_t, std::vector<std::uint32_t>> classShells;
bool dataReady = false;

// dc_class_map lists only classes whose spells are generated, so a class with
// reference sheets and no shells is absent and plays nothing - which is what
// the hardcoded CLASS_WARRIOR test used to say, without naming a class.
std::uint32_t ClassId(Player const* player)
{
    if (!player)
        return 0;
    auto found = classMap.find(static_cast<unsigned>(player->getClass()));
    return found == classMap.end() ? 0 : found->second;
}

// One selection path: every "is this unlocked" question resolves here.
CatalogueEntry const* Entry(Player const* player, std::string const& label)
{
    auto const classId = ClassId(player);
    if (!classId)
        return nullptr;
    auto found = catalogue.find({classId, label});
    return found == catalogue.end() ? nullptr : &found->second;
}

std::string Key(std::string const& skill, std::string const& rune)
{
    return rune.empty() ? skill : skill + " - " + rune;
}

// K3: this used to look the English label up in Spell.dbc, which made a
// renamed skill orphan every saved pick that used it. The catalogue already
// publishes the id for a label, so that is what answers now - and this is only
// ever reached from typed input, never from a saved row.
// Returns false when the label is not this class's. It keeps the lock the
// name lookup has always taken - the catalogue is replaced wholesale on a
// reload - and hands back BOTH ids, because the caller needs the base skill
// for the once-per-bar rule and the shell for the cast.
bool ShellFor(Player const* player, std::string const& skill, std::string const& rune,
              std::uint32_t& skillId, std::uint32_t& spellId)
{
    std::lock_guard<std::mutex> lock(dataMutex);
    CatalogueEntry const* entry = Entry(player, Key(skill, rune));
    if (!entry || !entry->spellId)
        return false;
    skillId = entry->skillId;
    spellId = entry->spellId;
    return true;
}

// The saved id, back to the text the client shows. Display only.
std::pair<std::string, std::string> LabelFor(std::uint32_t spellId)
{
    std::lock_guard<std::mutex> lock(dataMutex);
    auto found = labelById.find(spellId);
    return found == labelById.end() ? std::pair<std::string, std::string>{} : found->second;
}

// How long a skill still has on cooldown, in
// milliseconds; 0 when it is ready. The cooldown belongs to the skill, not to the rune that
// was slotted when it started: a record states a cooldown on some runes only (Meteor - Molten
// Impact), and the runes that share a Category share one timer, so every shell of the skill is
// asked - the base skill and each of its runes carry the same skill_id - and the longest wins.
// The shells are copied under the lock and the core is asked with it released, as GrantShells
// does: a call out of the module under dataMutex is how a new Mage's first login hung.
std::uint32_t SkillCooldownLeft(Player* player, std::uint32_t skillId)
{
    std::vector<std::uint32_t> shells;
    {
        std::lock_guard<std::mutex> lock(dataMutex);
        for (auto const& [spellId, entry] : catalogueById)
            if (entry.skillId == skillId)
                shells.push_back(spellId);
    }
    std::uint32_t left = 0;
    for (std::uint32_t spellId : shells)
        left = std::max(left, player->GetSpellCooldownDelay(spellId));
    return left;
}

// The family a WoW class teaches its own spells in, read out of ChrClasses.dbc
// (SpellClassSet) instead of being named here: Warrior is 4. The second class
// (04 §5) is another row in the same table, so none of this changes for it. No
// playable class maps to family 0 (SPELLFAMILY_GENERIC), so a missing row means
// "strip nothing" rather than "strip everything the core owns".
std::uint32_t ClassSpellFamily(Player const* player)
{
    ChrClassesEntry const* entry = player ? sChrClassesStore.LookupEntry(player->getClass()) : nullptr;
    return entry ? entry->spellfamily : 0;
}

// K3: empty the class's book. Everything the class itself teaches that is not
// one of our shells goes - abilities, stances and the talent-granted spells, all
// of which carry the class's own family. K3 keeps weapon skills (they auto-max
// via AlwaysMaxWeaponSkill), and racials, languages and professions are a
// different family and stay, so the character remains valid to the core.
bool IsClassSpell(Player const* player, std::uint32_t spellId)
{
    if (Potion::IsPotionShell(spellId))
        return false;
    if (Combat::Shells::IsShell(spellId))
        return false;                                   // one of ours (#66)
    std::uint32_t const family = ClassSpellFamily(player);
    if (!family)
        return false;
    SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId);
    return info && info->SpellFamilyName == family;
}

void StripClassSpells(Player* player)
{
    std::vector<std::uint32_t> remove;
    for (auto const& [spellId, state] : player->GetSpellMap())
        if (state && state->State != PLAYERSPELL_REMOVED && IsClassSpell(player, spellId))
            remove.push_back(spellId);
    for (std::uint32_t spellId : remove)
        player->removeSpell(spellId, SPEC_MASK_ALL, false);
    // Stances are auras, not just spells; drop any that survived.
    player->RemoveAurasByType(SPELL_AURA_MOD_SHAPESHIFT);
}

// ==================== talents are removed from the game =====================
// All talents come out; progression is D3
// skills, runes and passives. What closes the tree is the POINT, not the spell.
// A character that never holds a point has nothing to spend, so stripping the
// spells afterwards is a sweep, not the rule.
//
// Player::CalculateTalentsPoints is the one place the core decides what a level
// is worth, and every path that hands points out goes through it: login,
// level-up, a quest talent reward, a spec change, .reset talents and
// resetTalents itself all call InitTalentForLevel or CalculateTalentsPoints
// directly. Zeroing it there closes all of them at once.
// OnPlayerBeforeInitTalentForLevel LOOKS like the obvious hook and is not: at
// our core pin the core declares and defines it and never calls it.

// True when this character has talents in the spec it is playing - the same set
// resetTalents would clear, since that only touches the active spec.
bool HasSpentTalents(Player const* player)
{
    for (auto const& [spellId, talent] : player->GetTalentMap())
        if (talent && talent->State != PLAYERSPELL_REMOVED && (talent->specMask & player->GetActiveSpecMask()))
            return true;
    return false;
}

// Empties an existing character's tree on its next login, then costs nothing on
// every login after it, so there is no stored "done once" flag and no GM
// command. Nobody on the realm has a talent spent today (character_talent was
// empty when this was written, 9 characters), so in practice this only takes
// away the points they were holding - but it is deliberately not left to the
// core's own InitTalentForLevel, which resets the tree only when the account
// lacks RBAC_PERM_SKIP_CHECK_MORE_TALENTS_THAN_ALLOWED. A GM account has it, and
// for those the core zeroes the points and leaves the tree filled in.
void ClearTalents(Player* player)
{
    if (HasSpentTalents(player))
        player->resetTalents(true);
    player->SetFreeTalentPoints(0);
}

// Every shell is granted hidden: the player never browses them, the skill bar is
// the only way to cast (04 §2).
void GrantShells(Player* player)
{
    std::vector<std::uint32_t> added;
    if (!player->HasSpell(Potion::BaseSpell) &&
        player->addSpell(Potion::BaseSpell, SPEC_MASK_ALL, true, false, false))
        added.push_back(Potion::BaseSpell);
    // Copy the list, then grant with the lock released. addSpell casts a
    // passive shell on the spot (Player::_addSpell), and a scripted one re-enters
    // this file: Evocation's dc_wizard_buff Applied -> Refresh -> Passives::Has
    // -> Playable locks dataMutex again. It is a plain std::mutex, so holding it
    // here hung a new Mage's first login.
    std::vector<std::uint32_t> shells;
    {
        std::lock_guard<std::mutex> lock(dataMutex);
        auto const own = classShells.find(ClassId(player));
        if (own != classShells.end())
            shells = own->second;
    }
    for (std::uint32_t spellId : shells)
        if (!player->HasSpell(spellId) && player->addSpell(spellId, SPEC_MASK_ALL, true, false, false))
            added.push_back(spellId);
    // Login hooks run after the initial spell packet. New spells must use the
    // same learned-spell notification as Player::learnSpell before the buttons
    // arrive; replaying SMSG_INITIAL_SPELLS did not populate a fresh client's bar.
    if (player->IsInWorld())
        for (auto spellId : added)
            player->SendLearnPacket(spellId, true);
}
}

namespace
{
// Tell the client how long a potion shell has left.
// AddSpellCooldown(..., needSendToClient=true) sends nothing: that flag only puts the
// cooldown in the login spell list and the save. So a shell that was put on cooldown by a
// DIFFERENT potion's drink looked ready until a relog, and a shell learned by a potion swap
// arrived with no cooldown at all. The skill shells send the packet themselves
// (dc_combat.cpp SendSkillCooldown); the potion shells now do the same.
void SendPotionCooldown(Player* player, std::uint32_t spellId)
{
    std::uint32_t const remaining = player->GetSpellCooldownDelay(spellId);
    if (!remaining)
        return;
    PacketCooldowns cooldowns;
    cooldowns[spellId] = remaining;
    WorldPacket packet;
    player->BuildCooldownPacket(packet, SPELL_COOLDOWN_FLAG_NONE, cooldowns);
    player->SendDirectMessage(&packet);
}
}

// The server owns the fixed part of the stock action bar: skill slots 0-5 become
// action buttons 0-5 (keys 1-6), potion is button 6 (key 7), and Town Portal
// is button 7 (key 8). Buttons after that remain player-owned.
// Writing the buttons only changes server state; without SendActionButtons the
// client keeps drawing the bar it was given at login, which is why a slotted
// skill used to appear only after a relog.
void WriteActionBar(Player* player, std::vector<Slot> const& bar)
{
    for (unsigned slot = 0; slot < ActiveSlots() + 2; ++slot)
        player->removeActionButton(static_cast<uint8>(slot));
    for (Slot const& entry : bar)
        if (entry.spellId)
            player->addActionButton(static_cast<uint8>(entry.slot), entry.spellId, ACTION_BUTTON_SPELL);
    std::uint32_t const potion = Inventory::ActivePotionSpell(player);
    // A legendary shell is known only while its potion is the one in the slot;
    // taking it off puts the Health Potion (always known) back on key 7.
    for (Potion::Legendary const& legendary : Potion::Legendaries)
        if (potion != legendary.shell && player->HasSpell(legendary.shell))
            player->removeSpell(legendary.shell, SPEC_MASK_ALL, false);
    if (!player->HasSpell(potion) && sSpellMgr->GetSpellInfo(potion))
        player->learnSpell(potion);
    if (player->HasSpell(potion))
    {
        player->addActionButton(static_cast<uint8>(ActiveSlots()), potion, ACTION_BUTTON_SPELL);
        // The server keeps a potion's cooldown per spell id whoever drank it and whatever was
        // slotted, so a swap right after a drink must show the time left, not a ready button.
        SendPotionCooldown(player, potion);
    }
    // Classes registers before Rifts, whose login hook also grants this spell.
    // AzerothCore refuses a spell action until the player knows it, so make the
    // invariant local to the function that owns the button.
    if (!player->HasSpell(TOWN_PORTAL_SHELL) && sSpellMgr->GetSpellInfo(TOWN_PORTAL_SHELL))
        player->learnSpell(TOWN_PORTAL_SHELL);
    if (player->HasSpell(TOWN_PORTAL_SHELL))
        player->addActionButton(static_cast<uint8>(ActiveSlots() + 1), TOWN_PORTAL_SHELL, ACTION_BUTTON_SPELL);
    player->SendActionButtons(1);
}

void WriteActionBar(Player* player)
{
    std::vector<Slot> const bar = Bar(player);
    WriteActionBar(player, bar);
    Combat::BarWritten(player, bar);
}

std::uint32_t SkillIdOf(std::uint32_t spellId)
{
    std::lock_guard<std::mutex> lock(dataMutex);
    auto found = catalogueById.find(spellId);
    return found == catalogueById.end() ? 0 : found->second.skillId;
}

std::string CategoryOf(std::uint32_t spellId)
{
    std::lock_guard<std::mutex> lock(dataMutex);
    auto found = catalogueById.find(spellId);
    return found == catalogueById.end() ? std::string() : found->second.category;
}

bool Playable(Player const* player)
{
    std::lock_guard<std::mutex> lock(dataMutex);
    return ClassId(player) != 0;
}

std::string PrimaryStatOf(Player const* player)
{
    if (!player)
        return {};
    std::lock_guard<std::mutex> lock(dataMutex);
    auto found = primaryStatMap.find(static_cast<unsigned>(player->getClass()));
    return found == primaryStatMap.end() ? std::string() : found->second;
}

std::uint32_t ClassIdOf(Player const* player)
{
    std::lock_guard<std::mutex> lock(dataMutex);
    return ClassId(player);
}

bool SkillUnlocked(Player const* player, std::string const& skill)
{
    if (!player)
        return false;
    std::lock_guard<std::mutex> lock(dataMutex);
    CatalogueEntry const* entry = Entry(player, skill);
    return entry && player->GetLevel() >= entry->unlockLevel;
}

bool RuneUnlocked(Player const* player, std::string const& skill, std::string const& rune)
{
    if (!player)
        return false;
    if (rune.empty())
        return SkillUnlocked(player, skill);
    std::lock_guard<std::mutex> lock(dataMutex);
    CatalogueEntry const* entry = Entry(player, Key(skill, rune));
    return entry && player->GetLevel() >= entry->unlockLevel;
}

bool PassiveUnlocked(Player const* player, std::string const& passive)
{
    if (!player)
        return false;
    std::lock_guard<std::mutex> lock(dataMutex);
    auto const classId = ClassId(player);
    auto found = classPassives.find({classId, passive});
    return classId && found != classPassives.end() && player->GetLevel() >= found->second;
}

// Per slot, never a count: a slot with no unlock-level row is locked even when
// a later slot has one, so "how many are open" can never stand in for "is THIS
// slot open". dc_skillbar.lua carries the same rule and
// keys its payload by the actual slot index.
bool PassiveSlotUnlocked(Player const* player, unsigned slot)
{
    if (!player || slot >= PassiveSlots())
        return false;
    unsigned unlockLevel = 0;
    if (!PassiveSlotGate(slot, unlockLevel))
        return false;
    return player->GetLevel() >= unlockLevel;
}

// A headline count for the screen and `.dc bar`. It counts the slots that are
// actually unlocked, holes included, and is never the eligibility test.
unsigned PassiveSlotsOpen(Player const* player)
{
    if (!player)
        return 0;
    unsigned open = 0;
    for (unsigned slot = 0; slot < PassiveSlots(); ++slot)
        if (PassiveSlotUnlocked(player, slot))
            ++open;
    return open;
}

std::vector<Slot> Bar(Player* player)
{
    std::vector<Slot> bar;
    if (!player)
        return bar;
    // K3: the saved row IS the id. The names come back out of the catalogue
    // for display, so renaming a skill re-labels the bar instead of emptying it.
    QueryResult result = CharacterDatabase.Query(
        "SELECT slot, skill_id, spell_id FROM dc_character_skillbar WHERE guid={} ORDER BY slot",
        player->GetGUID().GetRawValue());
    if (!result)
        return bar;
    do
    {
        Field* fields = result->Fetch();
        Slot entry;
        entry.slot = fields[0].Get<uint8>();
        entry.skillId = fields[1].Get<uint32>();
        entry.spellId = fields[2].Get<uint32>();
        std::tie(entry.skill, entry.rune) = LabelFor(entry.spellId);
        bar.push_back(entry);
    } while (result->NextRow());
    return bar;
}

unsigned FirstFreeSlot(Player* player)
{
    std::vector<Slot> const bar = Bar(player);
    for (unsigned slot = 0; slot < ActiveSlots(); ++slot)
        if (std::none_of(bar.begin(), bar.end(), [&](Slot const& e) { return e.slot == slot; }))
            return slot;
    return ActiveSlots();
}

bool SetSlot(Player* player, unsigned slot, std::string const& skill, std::string const& rune,
             std::string& error)
{
    if (!Playable(player))
    {
        error = "This class has no Diablocraft skills.";
        return false;
    }
    if (slot >= ActiveSlots())
    {
        error = "Slots are 1 to 6.";
        return false;
    }
    // 04 §3: no bar edits in combat or inside an instance, except in a Greater Rift whose Guardian is dead
    // (as D3).
    if (player->IsInCombat())
    {
        error = "Not in combat.";
        return false;
    }
    if (player->GetMap() && player->GetMap()->Instanceable() && !DC::Rifts::GreaterRiftGuardianDead(player))
    {
        error = "Not inside an instance or rift.";
        return false;
    }
    if (!SkillUnlocked(player, skill))
    {
        error = skill + " is not unlocked yet.";
        return false;
    }
    if (!rune.empty() && !RuneUnlocked(player, skill, rune))
    {
        error = rune + " is not unlocked yet.";
        return false;
    }
    std::uint32_t skillId = 0, spellId = 0;
    if (!ShellFor(player, skill, rune, skillId, spellId))
    {
        error = "No shell for " + Key(skill, rune) + ".";
        return false;
    }
    // A skill that is on cooldown is not changed - not
    // swapped for another skill, not given another rune - until its cooldown ends; a skill that
    // is ready swaps freely. What the write below disturbs is what its DELETE removes: this
    // slot's row, and the row that already holds this skill (K6). A row that already holds this
    // very shell is not changed by it, so moving a skill with the rune it has, or writing the
    // same row again, is not refused.
    for (Slot const& held : Bar(player))
    {
        if ((held.slot != slot && held.skillId != skillId) || held.spellId == spellId)
            continue;
        if (std::uint32_t const left = SkillCooldownLeft(player, held.skillId))
        {
            error = held.skill + " is on cooldown (" + std::to_string((left + 999) / 1000) + " s left).";
            return false;
        }
    }
    // K6: a skill may sit in only one slot; moving it frees the old one.
    // One transaction, committed through the async queue and awaited. It has to
    // be atomic so a failed insert cannot leave the slot deleted, and the wait is
    // because WriteActionBar re-reads the bar on the next line - an unawaited
    // commit let the read race ahead and write the bar as it was before the
    // change. Not the direct commit: that borrows the world thread's
    // synchronous connection (security.md G1).
    std::string escapedSkill = skill;
    std::string escapedRune = rune;
    CharacterDatabase.EscapeString(escapedSkill);
    CharacterDatabase.EscapeString(escapedRune);
    std::uint64_t const guid = player->GetGUID().GetRawValue();
    CharacterDatabaseTransaction transaction = CharacterDatabase.BeginTransaction();
    // K6 keys on the BASE skill, so the "already on the bar" test is skill_id.
    // Keying it on spell_id would let two runes of one skill both sit there.
    transaction->Append("DELETE FROM dc_character_skillbar WHERE guid={} AND (slot={} OR skill_id={})",
                        guid, slot, skillId);
    transaction->Append("INSERT INTO dc_character_skillbar (guid, slot, skill_id, spell_id, skill, rune) "
                        "VALUES ({}, {}, {}, {}, '{}', '{}')",
                        guid, slot, skillId, spellId, escapedSkill, escapedRune);
    if (!CharacterDatabase.AsyncCommitTransaction(transaction).m_future.get())
    {
        error = "The skill bar could not be saved.";
        return false;
    }
    WriteActionBar(player);
    return true;
}

bool SwapSlots(Player* player, unsigned from, unsigned to, std::string& error)
{
    if (!Playable(player))
    {
        error = "This class has no Diablocraft skills.";
        return false;
    }
    if (from >= ActiveSlots() || to >= ActiveSlots())
    {
        error = "Slots are 1 to 6.";
        return false;
    }
    if (from == to)
    {
        error = "Pick two different slots.";
        return false;
    }
    // SetSlot's rules for a bar edit: not in combat, not inside an instance except a Greater Rift whose Guardian is dead.
    if (player->IsInCombat())
    {
        error = "Not in combat.";
        return false;
    }
    if (player->GetMap() && player->GetMap()->Instanceable() && !DC::Rifts::GreaterRiftGuardianDead(player))
    {
        error = "Not inside an instance or rift.";
        return false;
    }
    std::vector<Slot> const bar = Bar(player);
    auto const at = [&bar](unsigned slot)
    {
        auto const found = std::find_if(bar.begin(), bar.end(), [slot](Slot const& held) { return held.slot == slot; });
        return found == bar.end() ? nullptr : &*found;
    };
    Slot const* const held[2] = {at(from), at(to)};
    if (!held[0] && !held[1])
    {
        error = "Both slots are empty.";
        return false;
    }
    // Both rows leave their slots and come back in the other's, in one transaction: a skill that is on the bar before is on the
    // bar after, whatever else fails. Each skill keeps its shell, so no cooldown rule applies (nothing it casts changes).
    std::uint64_t const guid = player->GetGUID().GetRawValue();
    CharacterDatabaseTransaction transaction = CharacterDatabase.BeginTransaction();
    transaction->Append("DELETE FROM dc_character_skillbar WHERE guid={} AND slot IN ({}, {})", guid, from, to);
    for (unsigned side = 0; side < 2; ++side)
    {
        if (!held[side])
            continue;
        std::string skill = held[side]->skill, rune = held[side]->rune;
        CharacterDatabase.EscapeString(skill);
        CharacterDatabase.EscapeString(rune);
        transaction->Append("INSERT INTO dc_character_skillbar (guid, slot, skill_id, spell_id, skill, rune) "
                            "VALUES ({}, {}, {}, {}, '{}', '{}')",
                            guid, side == 0 ? to : from, held[side]->skillId, held[side]->spellId, skill, rune);
    }
    if (!CharacterDatabase.AsyncCommitTransaction(transaction).m_future.get())
    {
        error = "The skill bar could not be saved.";
        return false;
    }
    WriteActionBar(player);
    return true;
}

bool InitializeStarterBar(Player* player, std::string& error)
{
    // The class, not a class: a second class is data now, so the refusal says
    // what is wrong rather than naming the only one that used to work.
    if (!Playable(player)) { error = "This class has no Diablocraft skills."; return false; }
    // Audit row 24: the LIMIT was a second copy of the 6 the row count is then
    // checked against, so it now binds the same number rather than repeating it.
    //
    // The starter bar comes from the catalogue like every other selection, so
    // it is the player's own class that is read rather than one named table.
    // rune_id = 0 keeps this to base skills; the category order is D3's own.
    auto rows = WorldDatabase.Query(
        "SELECT l.skill_name, c.skill_id, c.spell_id FROM dc_class_catalogue c "
        "JOIN dc_class_label l ON l.spell_id = c.spell_id AND l.class_id = c.class_id "
        "WHERE c.class_id = {} AND c.rune_id = 0 AND c.unlock_level <= {} "
        "ORDER BY FIELD(l.category,'Primary','Secondary','Defensive','Might','Tactics','Rage'),"
        "c.unlock_level,l.skill_name LIMIT {}",
        ClassIdOf(player), player->GetLevel(), ActiveSlots());
    if (!rows || rows->GetRowCount() != ActiveSlots()) { error = "Six starter skills are unavailable."; return false; }
    struct Starter { std::string skill; std::uint32_t skillId, spellId; };
    std::vector<Starter> skills;
    do
    {
        Field* f = rows->Fetch();
        Starter starter{f[0].Get<std::string>(), f[1].Get<uint32>(), f[2].Get<uint32>()};
        if (!starter.spellId) { error = "Missing starter shell: " + starter.skill; return false; }
        skills.push_back(starter);
    } while (rows->NextRow());
    auto transaction = CharacterDatabase.BeginTransaction();
    auto guid = player->GetGUID().GetCounter();
    transaction->Append("DELETE FROM dc_character_skillbar WHERE guid={}", guid);
    for (unsigned slot = 0; slot < skills.size(); ++slot)
    {
        std::string name = skills[slot].skill;
        CharacterDatabase.EscapeString(name);
        transaction->Append("INSERT INTO dc_character_skillbar(guid,slot,skill_id,spell_id,skill,rune) "
                            "VALUES({},{},{},{},'{}','')",
                            guid, slot, skills[slot].skillId, skills[slot].spellId, name);
    }
    if (!CharacterDatabase.AsyncCommitTransaction(transaction).m_future.get())
    {
        error = "The starter bar could not be saved.";
        return false;
    }
    ClearTalents(player);
    StripClassSpells(player);
    GrantShells(player);
    WriteActionBar(player);
    return true;
}

std::vector<std::string> Passives(Player* player)
{
    std::vector<std::string> slotted;
    if (!player)
        return slotted;
    // K3: stored as an id, named from the catalogue for everything that shows
    // or matches a passive by name.
    QueryResult result = CharacterDatabase.Query(
        "SELECT slot, spell_id FROM dc_character_passives WHERE guid={} ORDER BY slot",
        player->GetGUID().GetRawValue());
    if (!result)
        return slotted;
    do
    {
        std::uint32_t const spellId = result->Fetch()[1].Get<uint32>();
        std::lock_guard<std::mutex> lock(dataMutex);
        auto found = passiveNameById.find(spellId);
        if (found != passiveNameById.end())
            slotted.push_back(found->second);
    } while (result->NextRow());
    return slotted;
}

bool SetPassive(Player* player, unsigned slot, std::string const& passive, std::string& error)
{
    if (!Playable(player))
    {
        error = "This class has no Diablocraft skills.";
        return false;
    }
    // K2: the fourth slot only opens at 70, so the gate is the slot, not the bar.
    // A slot with no unlock-level row has no gate and is refused here too, so an
    // ungated slot can never be written even if the count said otherwise.
    if (!PassiveSlotUnlocked(player, slot))
    {
        error = "That passive slot is not open yet.";
        return false;
    }
    if (player->IsInCombat())
    {
        error = "Not in combat.";
        return false;
    }
    if (player->GetMap() && player->GetMap()->Instanceable() && !DC::Rifts::GreaterRiftGuardianDead(player))
    {
        error = "Not inside an instance or rift.";
        return false;
    }
    if (!PassiveUnlocked(player, passive))
    {
        error = passive + " is not unlocked yet.";
        return false;
    }
    std::uint32_t passiveId = 0;
    {
        std::lock_guard<std::mutex> lock(dataMutex);
        auto found = passiveIdByName.find({ClassId(player), passive});
        if (found != passiveIdByName.end())
            passiveId = found->second;
    }
    if (!passiveId)
    {
        error = passive + " has no generated spell.";
        return false;
    }
    std::uint64_t const guid = player->GetGUID().GetRawValue();
    CharacterDatabaseTransaction transaction = CharacterDatabase.BeginTransaction();
    std::string escapedPassive = passive;
    CharacterDatabase.EscapeString(escapedPassive);
    // A passive sits in one slot only, same rule as the active bar (K6), and
    // the rule keys on the id now rather than on the English name.
    transaction->Append("DELETE FROM dc_character_passives WHERE guid={} AND (slot={} OR spell_id={})",
                        guid, slot, passiveId);
    transaction->Append("INSERT INTO dc_character_passives (guid, slot, spell_id, passive) "
                        "VALUES ({}, {}, {}, '{}')",
                        guid, slot, passiveId, escapedPassive);
    if (!CharacterDatabase.AsyncCommitTransaction(transaction).m_future.get())
    {
        error = "The passive could not be saved.";
        return false;
    }
    Combat::Passives::Invalidate(player);
    return true;
}

namespace
{
void RestorePotionLife(Player* player, SpellInfo const* info)
{
    if (!player || !player->IsAlive())
        return;
    uint32 const amount = Potion::HealAmount(player->GetMaxHealth(), player->GetHealth());
    if (!amount)
        return;
    // Same packet-producing path as dc_sustain.cpp. No healing bonus/crit or
    // healing-taken calculation: the amount is exactly the capped 60% heal.
    HealInfo heal(player, player, amount, info, SpellSchoolMask(info->SchoolMask));
    player->HealBySpell(heal, false);
}

// One cooldown for every potion shell. The cast shell already has its own 30 s;
// every OTHER shell in the catalogue gets the same. Same relative-millisecond
// AddSpellCooldown the skill shells use (dc_combat.cpp SendSkillCooldown); a cooldown
// is per spell id, so it survives the legendary shell being forgotten and learned
// again. The client is told with a packet as well (SendPotionCooldown): the flag on
// AddSpellCooldown sends nothing, which is why the two potions did not share a cooldown
// on screen.
void SharePotionCooldown(Player* player, SpellInfo const* info)
{
    if (!player)
        return;
    for (std::uint32_t shell : Potion::Shells)
        if (shell != info->Id)
        {
            player->AddSpellCooldown(shell, 0, Potion::CooldownMs, true);
            SendPotionCooldown(player, shell);
        }
}

// Bottomless potions: the slotted potion's power, at the roll the slot keeps
// (Inventory::ActivePotionRoll). A timed power is its record's aura on the drinker for the potion's
// seconds with the roll as the aura's amount ($s1 in its tooltip); a stat power's sheet contribution follows that aura
// (PotionStatSync: on while the aura is on, at its amount), so the aura saved at logout and restored at login brings its
// number back with it, and its end, a death or a dispel takes it off.
struct PotionStat
{
    std::string_view power;
    Stat stat;
    Bucket bucket;
};
// Regeneration's roll is the Life restored over its seconds: Life per Second, the sheet's regeneration (dc_sustain).
constexpr PotionStat PotionStats[] = {{"leg_potion_tower", Stat::Armor, Bucket::Percent},
                                      {"leg_potion_diamond", Stat::AllResistance, Bucket::Flat},
                                      {"leg_potion_regeneration", Stat::LifeRegen, Bucket::Flat},
                                      {"leg_potion_leech", Stat::LifePerHit, Bucket::Flat},
                                      {"leg_potion_mutilation", Stat::LifePerKill, Bucket::Flat}};

PotionStat const* PotionStatOf(Potion::Legendary const& potion)
{
    for (PotionStat const& row : PotionStats)
        if (row.power == potion.powerId)
            return &row;
    return nullptr;
}

Potion::Legendary const* PotionByPower(std::uint32_t spellId)
{
    for (Potion::Legendary const& potion : Potion::Legendaries)
        if (potion.power && potion.power == spellId)
            return &potion;
    return nullptr;
}

void PotionStatSync(Player* player, Potion::Legendary const& potion, bool on)
{
    PotionStat const* row = PotionStatOf(potion);
    if (!row)
        return;
    std::uint64_t const guid = player->GetGUID().GetRawValue();
    AuraEffect const* effect = on ? player->GetAuraEffect(potion.power, EFFECT_0) : nullptr;
    if (effect)
    {
        double value = effect->GetAmount();
        if (row->stat == Stat::LifeRegen)
            value = potion.seconds > 0 ? value / potion.seconds : 0;
        Stats::AddContribution(guid, {Source::Temporary, row->stat, potion.power, value, row->bucket});
    }
    else
        Stats::RemoveContribution(guid, Source::Temporary, row->stat, potion.power);
    Stats::Recompute(player);
}

// The record's aura on `target`, lasting `seconds`; `amount` is the number its tooltip shows (0: the record's own).
void PutPotionAura(Player* player, Unit* target, std::uint32_t spellId, double seconds, double amount)
{
    Aura* aura = player->AddAura(spellId, target);
    if (!aura)
        return;
    int32 const ms = static_cast<int32>(std::llround(seconds * 1000));
    aura->SetMaxDuration(ms);
    aura->SetDuration(ms);
    if (amount > 0)
        if (AuraEffect* effect = aura->GetEffect(EFFECT_0))
            effect->ChangeAmount(static_cast<int32>(std::llround(amount)));
}

// `belowLife`: the drinker's Life was under the potion's threshold before the drink healed it (Rejuvenation).
void DrinkPotionPower(Player* player, Potion::Legendary const& potion, bool belowLife)
{
    // The roll is the slotted potion's, and this shell is the slotted potion's; a potion with no roll (one granted with
    // .additem, which no roller saw) has no power.
    std::optional<double> const roll = Inventory::ActivePotionRoll(player);
    if (!roll || Inventory::ActivePotionSpell(player) != potion.shell)
        return;
    std::string_view const power = potion.powerId;
    if (power == "leg_potion_rejuvenation")
    {
        if (belowLife)
            if (Resources::Resource const* resource = Resources::Of(ClassIdOf(player)))
                Resources::Add(player, *resource, Resources::Max(player, *resource) * *roll / 100.0);
        return;
    }
    if (!potion.power)
        return;   // Kulle-Aid and Chaos: built as the item and the heal only
    if (power == "leg_potion_fear")
    {
        for (Unit* enemy : Combat::Enemies(player, potion.power, player->GetPosition(), potion.yards))
            PutPotionAura(player, enemy, potion.power, *roll, 0);
        return;
    }
    // Unfettered lasts its roll; every other timed power the seconds of its text.
    PutPotionAura(player, player, potion.power, power == "leg_potion_unfettered" ? *roll : potion.seconds, *roll);
    PotionStatSync(player, potion, true);
}

class PotionCast final : public AllSpellScript
{
public:
    PotionCast() : AllSpellScript("dc_health_potion", {ALLSPELLHOOK_ON_CAST}) { }
    void OnSpellCast(Spell*, Unit* caster, SpellInfo const* info, bool) override
    {
        if (Potion::IsPotionShell(info->Id))
        {
            Player* player = caster->ToPlayer();
            Potion::Legendary const* legendary = Potion::ByShell(info->Id);
            bool const belowLife = player && legendary &&
                                   player->GetHealth() * 100.0 < player->GetMaxHealth() * legendary->belowLifePct;
            RestorePotionLife(player, info);
            SharePotionCooldown(player, info);
            if (player && legendary && player->IsAlive())
                DrinkPotionPower(player, *legendary, belowLife);
        }
    }
};

// A cast's cost keeps its fraction: 25 Fury at 30% off is 17.5 under the hood, 35 over two casts. The core charges the reduced cost truncated to a whole unit (SpellInfo::CalcPowerCost, before
// Spell::cast's OnSpellCast); this works the same cost in float, CalcPowerCost's terms with ApplySpellMod's float
// form, and takes the whole units the dropped parts add up to. The shown cost stays the core's.
class CostFraction final : public AllSpellScript
{
public:
    CostFraction() : AllSpellScript("dc_resource_cost_fraction", {ALLSPELLHOOK_ON_CAST}) { }
    void OnSpellCast(Spell* spell, Unit* caster, SpellInfo const* info, bool) override
    {
        Player* player = caster ? caster->ToPlayer() : nullptr;
        if (!player || !spell || !info->ManaCost || info->ManaCostPercentage ||
            spell->HasTriggeredCastFlag(TRIGGERED_IGNORE_POWER_AND_REAGENT_COST))
            return;
        Resources::Resource const* resource = nullptr;
        for (Resources::Resource const& row : Resources::Data::Rows)
            if (row.classId == ClassIdOf(player) && row.power == info->PowerType)
                resource = &row;
        if (!resource)
            return;
        std::uint16_t const school = GetFirstSchoolInMask(info->GetSchoolMask());
        float exact = float(info->ManaCost) + player->GetInt32Value(UNIT_FIELD_POWER_COST_MODIFIER + school);
        player->ApplySpellMod(info->Id, SPELLMOD_COST, exact);
        exact *= 1.0f + player->GetFloatValue(UNIT_FIELD_POWER_COST_MULTIPLIER + school);
        int32 const owed = Resources::CostOwed(player, *resource, std::max(0.0f, exact), spell->GetPowerCost());
        if (owed > 0)
            Resources::SpendUnits(player, *resource, owed);
    }
};

// The potion powers' hooks: Amplification's healing received while its aura is on, and the stat powers' sheet numbers
// following their auras (applied: at the drink and at the restore after a login; removed: the end, a death, a dispel).
class PotionPowers final : public UnitScript
{
public:
    PotionPowers()
        : UnitScript("dc_potion_powers", true,
                     {UNITHOOK_MODIFY_HEAL_RECEIVED, UNITHOOK_ON_AURA_APPLY, UNITHOOK_ON_AURA_REMOVE})
    {
    }
    // Like Invigorating Gemstone's (dc_gem_powers.cpp Heals): the core passes healer and target in opposite orders from
    // its two callers, so only the heal whose healer is its own target is placed with certainty; every heal Torment
    // gives a player (the potion, regeneration, Life per Hit and per Kill, globes) is one.
    void ModifyHealReceived(Unit* first, Unit* second, uint32& heal, SpellInfo const*) override
    {
        Player* player = first && first == second ? first->ToPlayer() : nullptr;
        if (!player || !heal)
            return;
        for (Potion::Legendary const& potion : Potion::Legendaries)
            if (potion.power && std::string_view(potion.powerId) == "leg_potion_amplification")
                if (AuraEffect const* effect = player->GetAuraEffect(potion.power, EFFECT_0))
                    heal = static_cast<uint32>(std::llround(heal * (1 + effect->GetAmount() / 100.0)));
    }
    void OnAuraApply(Unit* unit, Aura* aura) override
    {
        if (Player* player = unit ? unit->ToPlayer() : nullptr)
            if (Potion::Legendary const* potion = aura ? PotionByPower(aura->GetId()) : nullptr)
                PotionStatSync(player, *potion, true);
    }
    void OnAuraRemove(Unit* unit, AuraApplication* application, AuraRemoveMode) override
    {
        if (Player* player = unit ? unit->ToPlayer() : nullptr)
            if (Potion::Legendary const* potion = application ? PotionByPower(application->GetBase()->GetId()) : nullptr)
                PotionStatSync(player, *potion, false);
    }
};

class ClassWorld final : public WorldScript
{
public:
    ClassWorld() : WorldScript("dc_class_world", {WORLDHOOK_ON_STARTUP}) { }
    void OnStartup() override
    {
        try
        {
            // One catalogue, one read. The three dc_barbarian_* tables are
            // still generated as reference, but nothing here selects from
            // them: a second class arrives as rows, not as another branch.
            std::unordered_map<unsigned, std::uint32_t> loadedClasses;
            std::unordered_map<unsigned, std::string> loadedPrimaryStats;
            if (QueryResult mapped = WorldDatabase.Query(
                    "SELECT wow_class_id, class_id, primary_stat FROM dc_class_map"))
                do
                {
                    Field* f = mapped->Fetch();
                    loadedClasses[static_cast<unsigned>(f[0].Get<uint32>())] = f[1].Get<uint32>();
                    loadedPrimaryStats[static_cast<unsigned>(f[0].Get<uint32>())] = f[2].Get<std::string>();
                } while (mapped->NextRow());
            if (loadedClasses.empty())
                throw std::runtime_error("dc_class_map is missing or empty; apply the class "
                                         "catalogue migration");

            std::map<std::pair<std::uint32_t, std::string>, CatalogueEntry> loadedCatalogue;
            std::unordered_map<std::uint32_t, CatalogueEntry> loadedById;
            std::unordered_map<std::uint32_t, std::pair<std::string, std::string>> loadedLabels;
            QueryResult result = WorldDatabase.Query(
                "SELECT c.class_id, c.skill_id, c.rune_id, c.spell_id, c.unlock_level, "
                "c.indicator_spell_id, l.skill_name, l.rune_name, l.category "
                "FROM dc_class_catalogue c JOIN dc_class_label l ON l.spell_id = c.spell_id "
                "AND l.class_id = c.class_id");
            if (!result)
                throw std::runtime_error("dc_class_catalogue is missing; apply the class "
                                         "catalogue migration");
            do
            {
                Field* f = result->Fetch();
                CatalogueEntry entry;
                entry.classId = f[0].Get<uint32>();
                entry.skillId = f[1].Get<uint32>();
                entry.runeId = f[2].Get<uint32>();
                entry.spellId = f[3].Get<uint32>();
                entry.unlockLevel = static_cast<unsigned>(f[4].Get<uint32>());
                entry.indicatorSpellId = f[5].Get<uint32>();
                entry.category = f[8].Get<std::string>();
                // The label is the key the skill bar persists today: "Skill" on
                // a base row, "Skill - Rune" on a runed one.
                std::string const label = Key(f[6].Get<std::string>(), f[7].Get<std::string>());
                loadedById[entry.spellId] = entry;
                loadedLabels[entry.spellId] = {f[6].Get<std::string>(), f[7].Get<std::string>()};
                if (!loadedCatalogue.emplace(std::make_pair(entry.classId, label), entry).second)
                    throw std::runtime_error("dc_class_catalogue has two rows for the same "
                                             "class and label: " + label);
            } while (result->NextRow());

            std::map<std::pair<std::uint32_t, std::string>, unsigned> loadedPassives;
            std::unordered_map<std::uint32_t, std::string> loadedPassiveNames;
            std::unordered_map<std::pair<std::uint32_t, std::string>, std::uint32_t, PairHash>
                loadedPassiveIds;
            result = WorldDatabase.Query(
                "SELECT p.class_id, p.unlock_level, l.passive_name, p.spell_id FROM dc_class_passive p "
                "JOIN dc_class_passive_label l ON l.spell_id = p.spell_id");
            if (!result)
                throw std::runtime_error("dc_class_passive is missing; apply the class "
                                         "catalogue migration");
            do
            {
                Field* f = result->Fetch();
                loadedPassives[{f[0].Get<uint32>(), f[2].Get<std::string>()}] =
                    static_cast<unsigned>(f[1].Get<uint32>());
                loadedPassiveNames[f[3].Get<uint32>()] = f[2].Get<std::string>();
                loadedPassiveIds[{f[0].Get<uint32>(), f[2].Get<std::string>()}] = f[3].Get<uint32>();
            } while (result->NextRow());

            // K3: the id range, and ONLY the id range. This used to read
            // Name_Lang_enUS and key the bar's resolution on it, which is the
            // Spell.dbc name join this task removes; the catalogue owns the
            // label-to-id answer now.
            std::unordered_map<std::uint32_t, std::vector<std::uint32_t>> shells;
            std::size_t shellCount = 0;
            result = WorldDatabase.Query(
                "SELECT c.class_id, c.spell_id FROM dc_class_catalogue c JOIN spell_dbc s ON s.ID = c.spell_id "
                "UNION SELECT p.class_id, p.spell_id FROM dc_class_passive p JOIN spell_dbc s ON s.ID = p.spell_id "
                "ORDER BY 1, 2");
            if (!result)
                throw std::runtime_error("spell shells are missing; apply the class's spell record migration");
            do
            {
                shells[result->Fetch()[0].Get<uint32>()].push_back(result->Fetch()[1].Get<uint32>());
                ++shellCount;
            } while (result->NextRow());

            if (!CharacterDatabase.Query("SELECT COUNT(*) FROM dc_character_skillbar") ||
                !CharacterDatabase.Query("SELECT COUNT(*) FROM dc_character_passives"))
                throw std::runtime_error("skill bar migrations have not been applied");

            std::lock_guard<std::mutex> lock(dataMutex);
            catalogue = std::move(loadedCatalogue);
            catalogueById = std::move(loadedById);
            labelById = std::move(loadedLabels);
            classPassives = std::move(loadedPassives);
            passiveNameById = std::move(loadedPassiveNames);
            passiveIdByName = std::move(loadedPassiveIds);
            classMap = std::move(loadedClasses);
            primaryStatMap = std::move(loadedPrimaryStats);
            classShells = std::move(shells);
            dataReady = true;
            LOG_INFO("server.loading",
                     "[DC classes] {} catalogue entries, {} passives, {} shells, {} playable class(es)",
                     catalogue.size(), classPassives.size(), shellCount, classMap.size());
            // Say it once at load when the sheet asks for
            // more passive slots than it gives unlock levels. The missing ones
            // stay locked rather than opening at level 0, and this is the line
            // that says a row is missing.
            //
            // How many rows EXIST and which slot is the highest one that has a
            // row are two different numbers, and only the first decides whether
            // to warn: four slots configured with slot 2's row missing and slot
            // 4's present is three rows with a highest of 4, which is exactly
            // the case a "highest" test walks past in silence. A gap is no more
            // acceptable than a short tail, so neither the test nor the wording
            // assumes the missing rows are the trailing ones.
            unsigned const configured = PassiveSlots();
            unsigned present = 0, highest = 0;
            for (unsigned slot = 0; slot < configured; ++slot)
            {
                unsigned unlockLevel = 0;
                if (!PassiveSlotGate(slot, unlockLevel))
                    continue;
                ++present;
                highest = slot + 1;
            }
            if (configured > present)
                LOG_WARN("server.loading",
                         "[DC classes] combat/passive_skill_slots is {} but only {} "
                         "passive_slot_N_unlock_level row(s) exist (highest numbered: {}). "
                         "Any slot without its own row has no gate and stays locked, wherever "
                         "in the run it is; add the missing rows to "
                         "data/d3/character_rules.csv.",
                         configured, present, highest);
        }
        catch (std::exception const& error)
        {
            LOG_ERROR("server", "D3 class startup failed: {}. The skill bar is disabled.", error.what());
        }
    }
};

class ClassPlayer final : public PlayerScript
{
public:
    ClassPlayer() : PlayerScript("dc_class_player", {
        PLAYERHOOK_ON_LOGIN, PLAYERHOOK_ON_LEVEL_CHANGED, PLAYERHOOK_ON_DELETE_FROM_DB,
        PLAYERHOOK_ON_LEARN_SPELL}) { }

    // Sweeping on login and level-up is not enough: the core teaches the class
    // its defaults from several paths and some of them run after those hooks,
    // which is how "Heroic Strike (Rank 1)" and "Battle Stance" kept appearing in
    // the login chat. A veto hook exists now (OnPlayerCanLearnSpell, upstream #27552),
    // but OnPlayerLearnSpell still only reports, and this takes whatever the class
    // itself teaches straight back off, whichever path taught it.
    void OnPlayerLearnSpell(Player* player, uint32 spellId) override
    {
        if (Playable(player) && IsClassSpell(player, spellId))
            player->removeSpell(spellId, SPEC_MASK_ALL, false);
    }

    void OnPlayerLogin(Player* player) override
    {
        if (!Playable(player))
            return;
        {
            std::lock_guard<std::mutex> lock(dataMutex);
            if (!dataReady)
                return;
        }
        // K3 runs on every login, not just the first: the class can regain
        // stances through level-up grants, so the book is swept each time.
        StripClassSpells(player);
        GrantShells(player);
        WriteActionBar(player);
    }

    void OnPlayerLevelChanged(Player* player, uint8) override
    {
        if (!Playable(player))
            return;
        // K1/K2: unlocks are derived, so nothing is stored; the sweep just keeps
        // any newly granted class spell out of the book.
        StripClassSpells(player);
        GrantShells(player);
    }

    void OnPlayerDeleteFromDB(CharacterDatabaseTransaction trans, uint32 guid) override
    {
        trans->Append("DELETE FROM dc_character_skillbar WHERE guid={}", guid);
        trans->Append("DELETE FROM dc_character_passives WHERE guid={}", guid);
        trans->Append("DELETE FROM dc_character_potion WHERE guid={}", guid);
    }
};

// Talents are removed (04-classes K3). This script is
// not gated on the class: the rule is the game's, not the Barbarian's, and it
// has to hold for the second class the day its rows land.
class TalentRemoval final : public PlayerScript
{
public:
    TalentRemoval() : PlayerScript("dc_talents_removed", {
        PLAYERHOOK_ON_CALCULATE_TALENTS_POINTS, PLAYERHOOK_CAN_LEARN_TALENT,
        PLAYERHOOK_ON_LOGIN, PLAYERHOOK_ON_LEVEL_CHANGED}) { }

    // The rule itself. Every point the core would grant, at any level, from any
    // path, is worth nothing; see the note above ClearTalents for why this hook
    // and not OnPlayerBeforeInitTalentForLevel.
    void OnPlayerCalculateTalentsPoints(Player const*, uint32& points) override { points = 0; }

    // With no points there is nothing to spend, so this can only ever be a
    // client that made its own packet. Refused rather than left to arithmetic.
    bool OnPlayerCanLearnTalent(Player*, TalentEntry const*, uint32) override { return false; }

    // Existing characters: emptied once, on the next login, then a no-op.
    void OnPlayerLogin(Player* player) override { ClearTalents(player); }

    // The core recalculates points on every level, and this is the belt to
    // CalculateTalentsPoints's braces: if any path ever hands out a point
    // without asking it, the next level takes it away again.
    void OnPlayerLevelChanged(Player* player, uint8) override { ClearTalents(player); }
};

// Dual spec is a second talent specialisation, so it goes with the talents. The
// core drives both halves through a spell - the trainer's purchase is
// SPELL_EFFECT_TALENT_SPEC_COUNT and the switch is SPELL_EFFECT_TALENT_SPEC_SELECT -
// and OnSpellCheckCast is the first thing Spell::CheckCast runs, so one refusal
// covers the trainer, the talent frame's spec button and a hand-made macro.
class SpecRemoval final : public AllSpellScript
{
public:
    SpecRemoval() : AllSpellScript("dc_dual_spec_removed", {ALLSPELLHOOK_ON_SPELL_CHECK_CAST}) { }
    void OnSpellCheckCast(Spell* spell, bool, SpellCastResult& result) override
    {
        SpellInfo const* info = spell ? spell->GetSpellInfo() : nullptr;
        if (!info)
            return;
        for (uint8 index = 0; index < MAX_SPELL_EFFECTS; ++index)
            if (info->Effects[index].Effect == SPELL_EFFECT_TALENT_SPEC_COUNT ||
                info->Effects[index].Effect == SPELL_EFFECT_TALENT_SPEC_SELECT)
            {
                result = SPELL_FAILED_SPELL_UNAVAILABLE;
                return;
            }
    }
};

// The picker's click has to reach SetSlot, and ALE cannot call into our C++.
// It does not need to: the addon sends a plain addon message (SendAddonMessage
// is not protected) and OnPlayerBeforeSendChatMessage sees it, because that hook
// fires before the chat handler's type switch and so covers LANG_ADDON traffic.
// No core change and no mod-ale change; the rules still live in SetSlot, so the
// client cannot talk its way past one.
class ClassBridge final : public PlayerScript
{
    // security.md G1 gaps: each SetSlot/SetPassive waits for a database commit on the world
    // thread. A request inside the gap is dropped without a word; the server's bar is
    // unchanged and the skills screen redraws from it on its Refresh.
    DC::Gap::PerPlayer slotGap_, passiveGap_;
    static bool Admit(DC::Gap::PerPlayer& gap, Player* player, char const* tunable)
    {
        return gap.Admit(player->GetGUID().GetRawValue(), DC::Gap::NowMs(),
                         DC::Gap::GapFromTunable(DC::Tunables::Get("combat", tunable)));
    }

public:
    ClassBridge() : PlayerScript("dc_class_bridge", {PLAYERHOOK_ON_BEFORE_SEND_CHAT_MESSAGE}) { }

    void OnPlayerBeforeSendChatMessage(Player* player, uint32& /*type*/, uint32& lang, std::string& msg) override
    {
        if (!Playable(player) || lang != LANG_ADDON)
            return;
        // "DCSLOT	skill	rune[	slot]" or "DCPASSIVE	slot	passive"
        std::vector<std::string> parts;
        std::istringstream stream(msg);
        std::string part;
        while (std::getline(stream, part, '	'))
            parts.push_back(part);
        if (parts.empty())
            return;
        std::string error;
        if (parts[0] == "DCSLOT" && parts.size() >= 2)
        {
            if (!Admit(slotGap_, player, "skill_slot_gap_ms"))
                return;
            // The command path sends three fields and means "anywhere free"; the
            // skills screen sends a fourth and means "this slot", because changing
            // the rune on slot 4 must not move the skill to slot 1. An
            // out-of-range slot falls back to the picker's behaviour rather than
            // being trusted: SetSlot would refuse it anyway, but the message is
            // clearer this way.
            unsigned slot = ActiveSlots();
            if (parts.size() > 3)
            {
                try { slot = static_cast<unsigned>(std::stoul(parts[3])); }
                catch (std::exception const&) { slot = ActiveSlots(); }
            }
            if (slot >= ActiveSlots())
                slot = FirstFreeSlot(player);
            if (slot >= ActiveSlots())
            {
                ChatHandler(player->GetSession()).SendSysMessage("The bar is full.");
                return;
            }
            if (!SetSlot(player, slot, parts[1], parts.size() > 2 ? parts[2] : "", error))
                ChatHandler(player->GetSession()).SendSysMessage(error);
        }
        else if (parts[0] == "DCSWAP" && parts.size() >= 3)
        {
            // "DCSWAP	from	to": two wells, 0-based as DCSLOT's slot field; one request, one server step.
            if (!Admit(slotGap_, player, "skill_slot_gap_ms"))
                return;
            unsigned from = 0, to = 0;
            try
            {
                from = static_cast<unsigned>(std::stoul(parts[1]));
                to = static_cast<unsigned>(std::stoul(parts[2]));
            }
            catch (std::exception const&)
            {
                return;
            }
            if (!SwapSlots(player, from, to, error))
                ChatHandler(player->GetSession()).SendSysMessage(error);
        }
        else if (parts[0] == "DCPASSIVE" && parts.size() >= 3)
        {
            if (!Admit(passiveGap_, player, "passive_slot_gap_ms"))
                return;
            unsigned slot = 0;
            try { slot = static_cast<unsigned>(std::stoul(parts[1])); }
            catch (std::exception const&) { return; }
            if (!SetPassive(player, slot, parts[2], error))
                ChatHandler(player->GetSession()).SendSysMessage(error);
        }
    }
};

class ClassCommand final : public CommandScript
{
public:
    ClassCommand() : CommandScript("dc_class_command") { }
    Acore::ChatCommands::ChatCommandTable GetCommands() const override
    {
        using namespace Acore::ChatCommands;
        static ChatCommandTable classes = {
            {"skill", HandleSkill, SEC_ADMINISTRATOR, Console::No},
            {"bar", HandleBar, SEC_ADMINISTRATOR, Console::No},
            {"passive", HandlePassive, SEC_ADMINISTRATOR, Console::No},
        };
        static ChatCommandTable root = {{"dc", classes}};
        return root;
    }

    // .dc skill <skill name>[; rune name] - slot into the first free slot.
    static bool HandleSkill(ChatHandler* handler, Acore::ChatCommands::Tail arguments)
    {
        Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
        if (!player)
            return false;
        std::string text(arguments);
        std::string skill = text, rune;
        std::size_t const split = text.find(';');
        if (split != std::string::npos)
        {
            skill = text.substr(0, split);
            rune = text.substr(split + 1);
        }
        auto trim = [](std::string& value)
        {
            while (!value.empty() && value.front() == ' ') value.erase(value.begin());
            while (!value.empty() && value.back() == ' ') value.pop_back();
        };
        trim(skill);
        trim(rune);
        if (skill.empty())
        {
            handler->SendSysMessage("Usage: .dc skill <skill>[; rune]  e.g. .dc skill Frenzy; Maniac");
            return false;
        }
        unsigned const slot = FirstFreeSlot(player);
        if (slot >= ActiveSlots())
        {
            handler->SendSysMessage("The bar is full; all six slots are taken.");
            return false;
        }
        std::string error;
        if (!SetSlot(player, slot, skill, rune, error))
        {
            handler->SendSysMessage(error);
            return false;
        }
        // Acore::StringFormat is fmt-based: the placeholders are {}, not printf's.
        handler->PSendSysMessage("Slot {}: {}{}{}", slot + 1, skill,
                                 rune.empty() ? "" : " - ", rune);
        return true;
    }

    // .dc passive <slot 1-4> <passive name>
    static bool HandlePassive(ChatHandler* handler, uint32 slot, Acore::ChatCommands::Tail name)
    {
        Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
        if (!player)
            return false;
        std::string passive(name);
        if (passive.empty() || slot < 1 || slot > PassiveSlots())
        {
            handler->SendSysMessage("Usage: .dc passive <1-4> <passive name>");
            return false;
        }
        std::string error;
        if (!SetPassive(player, slot - 1, passive, error))
        {
            handler->SendSysMessage(error);
            return false;
        }
        handler->PSendSysMessage("Passive slot {}: {}", slot, passive);
        return true;
    }

    static bool HandleBar(ChatHandler* handler)
    {
        Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
        if (!player)
            return false;
        std::vector<Slot> const bar = Bar(player);
        if (bar.empty())
        {
            handler->SendSysMessage("Skill bar is empty.");
            return true;
        }
        for (Slot const& entry : bar)
        {
            std::ostringstream line;
            line << "slot " << entry.slot + 1 << ": " << entry.skill
                 << (entry.rune.empty() ? "" : " - " + entry.rune)
                 << "  (spell " << entry.spellId << ")";
            handler->SendSysMessage(line.str());
            LOG_INFO("server.loading", "[DC classes] {}", line.str());
        }
        std::vector<std::string> const slotted = Passives(player);
        for (std::size_t index = 0; index < slotted.size(); ++index)
            handler->PSendSysMessage("passive {}: {}", index + 1, slotted[index]);
        handler->PSendSysMessage("Passive slots open: {} of {}", PassiveSlotsOpen(player),
                                 static_cast<unsigned>(PassiveSlots()));
        return true;
    }
};
}

void ReducePotionCooldown(Player* player, std::uint32_t ms)
{
    if (!player || !ms)
        return;
    for (std::uint32_t shell : Potion::Shells)
        if (player->GetSpellCooldownDelay(shell))
        {
            player->ModifySpellCooldown(shell, -static_cast<int32>(ms));
            SendPotionCooldown(player, shell);
        }
}

void RegisterScripts()
{
    new PotionCast();
    new CostFraction();
    new PotionPowers();
    new ClassWorld();
    new ClassPlayer();
    new TalentRemoval();
    new SpecRemoval();
    new ClassBridge();
    new ClassCommand();
    Follower::RegisterScripts();
}
}
