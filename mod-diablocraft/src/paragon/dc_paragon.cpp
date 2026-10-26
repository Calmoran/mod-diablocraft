#include "dc_paragon.h"
#include "../hardcore/dc_hardcore.h"
#include "dc_paragon_math.h"
#include "../stats/dc_stats.h"
#include "../classes/dc_classes.h"
#include "../classes/dc_resources.h"
#include "../combat/dc_pylons.h"
#include "../common/dc_request_gap.h"
#include "../common/dc_tunables.h"
#include "../common/dc_numeric_data.h"
#include "../difficulty/dc_difficulty.h"
#include "../rifts/dc_rifts.h"
#include "Chat.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "Group.h"
#include "KillRewarder.h"
#include "Formulas.h"
#include "World.h"
#include "Log.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "UpdateFields.h"
#include "WorldPacket.h"
#include "WorldSession.h"
#include <chrono>
#include <cmath>
#include <future>
#include <iomanip>
#include <limits>
#include <map>
#include <mutex>
#include <optional>
#include <type_traits>
#include <set>
#include <sstream>

// Literal audit (docs/research/literal-audit-claude.md): the numbers below are
// constants, not tunables - recorded here, nothing else changes.
// Constant (16): paragon stat count; Structure, four categories of four.
// Constant (70): level cap that separates leveling from paragon; D3's cap; six copies of the literal in this file.
// Constant (800): rows the paragon XP table must have; Row-count assertion.

namespace DC::Paragon
{
Pool PoolFor(Player const* player) { return Hardcore::IsHardcore(player) ? Pool::Hardcore : Pool::Normal; }
namespace
{
struct Rule
{
    unsigned id = 0, category = 0, cap = 0;
    std::string key, name, unit;
    double value = 0;
    Stat stat = Stat::Strength;
    Bucket bucket = Bucket::Flat;
    // paragon.csv Core: "Primary stat ... by class". The stat is the player's
    // own main stat, resolved per player in Contributions, never a fixed one.
    bool classPrimary = false;
    // paragon.csv Core: Maximum Resource. What a point buys is the player's
    // own primary resource's (paragon.csv resource_keys through the registry:
    // +4 Mana, +1 Fury/Spirit/Essence, +0.5 Wrath/Arcane Power/Hatred paid
    // as +1 per two points), resolved per player, never this row's value.
    bool classResource = false;
};
using Points = std::array<unsigned, 16>;
using AccountKey = std::pair<uint32, Pool>;
struct Character
{
    AccountKey account;
    Points points{};
    bool dirty = false;
    bool progressDirty = false;
    bool hasRespec = false;
    std::uint64_t lastRespecMs = 0;
    bool saving = false; // a commit for this character is in flight while the module lock is free
    unsigned announce = 0; // the Paragon level this character reached since its last update; one chat line says it
};
// Account mutations are serialized across map threads. Player stat updates run
// only from that player's own hook/command; an account level-up marks peers dirty.
std::mutex mutex;
std::map<AccountKey, Progress> accounts;
std::map<uint32, Character> characters;
std::array<Rule, 16> rules;
std::vector<XP> xpTable;
std::map<unsigned, XP> tierBonuses;
XP baseXP = 0;
unsigned partyPerMember = 0, partyCap = 0, maxMembers = 0;
bool ready = false;
char const* PoolName(Pool pool) { return pool == Pool::Hardcore ? "hardcore" : "normal"; }
char const* Categories[] = {"Core", "Offense", "Defense", "Utility"};
AccountKey Key(Player* player) { return {player->GetSession()->GetAccountId(), PoolFor(player)}; }
uint32 Guid(Player* player) { return player->GetGUID().GetCounter(); }
// The one Paragon class gate: every playable D3
// class, meaning a dc_class_map row (class_map.csv), the same gate stats and
// hits use. A class with no row is named once in the log and refused, never
// treated as a Barbarian.
bool ParagonClass(Player const* player)
{
    if (!player)
        return false;
    if (Classes::Playable(player))
        return true;
    static std::mutex namedMutex;
    static std::set<unsigned> named;
    unsigned const wowClass = player->getClass();
    std::lock_guard<std::mutex> lock(namedMutex);
    if (named.insert(wowClass).second)
        LOG_WARN("server", "[DC paragon] WoW class {} has no dc_class_map row; Paragon is refused for it", wowClass);
    return false;
}
// class_map.csv's primary_stat for this player's class: Strength for the
// Barbarian, Intelligence for the Wizard. Empty for a class with none.
// The player's primary resource from the registry, by class_map.csv class.
Resources::Resource const& ClassResource(Player const* player)
{
    auto const* resource = Resources::Of(Classes::ClassIdOf(player));
    Need(resource != nullptr, "Your class has no class_resources.csv row; Paragon cannot apply Maximum Resource.");
    return *resource;
}
// What `count` points in a rule buy this player: the rule's value, or for
// Maximum Resource the player's resource's whole-point amount.
double Paid(Player const* player, Rule const& rule, unsigned count);
std::optional<Stat> PrimaryStat(Player const* player)
{
    std::string const name = Classes::PrimaryStatOf(player);
    if (name == "Strength") return Stat::Strength;
    if (name == "Dexterity") return Stat::Dexterity;
    if (name == "Intelligence") return Stat::Intelligence;
    return std::nullopt;
}
void Check(Player* player)
{
    Need(ready, "Paragon is unavailable; check the Paragon migrations and server log.");
    Need(ParagonClass(player), "Paragon is not available for your class yet.");
}
Progress ReadAccount(AccountKey const& key)
{
    auto row = CharacterDatabase.Query("SELECT level,xp FROM dc_account_paragon WHERE account_id={} AND pool='{}'", key.first, PoolName(key.second));
    Need(bool(row), "Cannot read the account Paragon pool.");
    return {(*row)[0].Get<uint32>(), (*row)[1].Get<uint64>()};
}
Progress& Account(AccountKey const& key)
{
    auto found = accounts.find(key);
    if (found != accounts.end()) return found->second;
    CharacterDatabase.DirectExecute("INSERT IGNORE INTO dc_account_paragon(account_id,pool) VALUES({},'{}')", key.first, PoolName(key.second));
    auto state = ReadAccount(key);
    Need(state.xp < NextXP(state.level, xpTable), "Invalid saved Paragon XP; administrator repair required.");
    return accounts.emplace(key, state).first->second;
}
Points ReadPoints(uint32 guid)
{
    // Sentinel distinguishes an empty allocation from a failed database query.
    auto rows = CharacterDatabase.Query("SELECT stat,points FROM dc_character_paragon WHERE guid={} UNION ALL SELECT 0,0", guid);
    Need(bool(rows), "Cannot read character Paragon allocation.");
    Points points{};
    do
    {
        unsigned id = (*rows)[0].Get<uint32>(), count = (*rows)[1].Get<uint32>();
        if (!id) continue;
        Need(id <= rules.size(), "Unknown saved Paragon stat.");
        points[id-1] = count;
    } while (rows->NextRow());
    return points;
}
// Audit row 62: the paragon level after which every point is Core, read from
// dc_tunables instead of compiled in.
unsigned CoreOnlyAfterLevel()
{
    return static_cast<unsigned>(DC::Tunables::Get("paragon", "core_only_after_level"));
}

std::array<unsigned, 4> Available(Points const& points, unsigned level)
{
    auto left = Earned(level, CoreOnlyAfterLevel());
    for (auto const& rule : rules)
    {
        unsigned count = points[rule.id-1];
        Need((!rule.cap || count <= rule.cap) && count <= left[rule.category], "Invalid saved Paragon allocation.");
        left[rule.category] -= count;
    }
    return left;
}
double Paid(Player const* player, Rule const& rule, unsigned count)
{
    if (rule.classResource)
        return Resources::ParagonMaximum(ClassResource(player), count);
    return count*rule.value;
}
std::vector<Contribution> Contributions(Player const* player, Points const& points)
{
    std::vector<Contribution> result;
    for (auto const& rule : rules)
        if (points[rule.id-1])
        {
            Stat stat = rule.stat;
            if (rule.classPrimary)
            {
                auto const primary = PrimaryStat(player);
                Need(primary.has_value(), "Your class has no main stat in class_map.csv; Paragon cannot apply it.");
                stat = *primary;
            }
            result.push_back({Source::Paragon, stat, rule.id, Paid(player, rule, points[rule.id-1]), rule.bucket});
        }
    return result;
}
Character& State(Player* player)
{
    Check(player);
    auto found = characters.find(Guid(player));
    Need(found != characters.end(), "Paragon character state is not loaded; relog.");
    Need(found->second.account == Key(player), "Character mode changed; relog before using Paragon.");
    return found->second;
}
std::string Number(double value)
{
    std::ostringstream out;
    out.imbue(std::locale::classic());
    out << std::fixed << std::setprecision(4) << value;
    std::string text = out.str();
    while (text.back() == '0') text.pop_back();
    if (text.back() == '.') text.pop_back();
    return text;
}
void Wire(Player* player, std::string const& message)
{
    WorldPacket packet;
    ChatHandler::BuildChatPacket(packet, CHAT_MSG_WHISPER, LANG_ADDON, player, player, "DCPARAGON\t" + message);
    player->GetSession()->SendPacket(&packet);
}
// 10 P-bar: Paragon rides the STOCK XP bar. The client
// keeps drawing it at 70 because its own cap is 80 (Expansion = 2) while
// OnPlayerSetMaxLevel caps the server at 70, and ordinary XP is dead there
// (OnPlayerGiveXP zeroes every source), so the three fields are ours. Values are
// always the H record's own pool XP and threshold, so bar and screen cannot
// disagree. Idempotent: called from Snapshot, login and OnPlayerUpdate.
void PublishBar(Player* player, XP xp, XP next)
{
    if (player->GetLevel() != 70) return; // Below 70 the fields are real leveling.
    auto shown = Display(xp, next);
    if (player->GetUInt32Value(PLAYER_NEXT_LEVEL_XP) != shown.next) player->SetUInt32Value(PLAYER_NEXT_LEVEL_XP, shown.next);
    if (player->GetUInt32Value(PLAYER_XP) != shown.xp) player->SetUInt32Value(PLAYER_XP, shown.xp);
    // Rest bonus is the one core writer still live at 70: Player::SetRestBonus
    // only self-zeroes at CONFIG_MAX_PLAYER_LEVEL, which is 80 here, so the inn
    // tick would paint a rested overlay sized from our own threshold.
    if (player->GetRestBonus() > 0.0f || player->GetUInt32Value(PLAYER_REST_STATE_EXPERIENCE)) player->SetRestBonus(0.0f);
}
// The H record: the bar's numbers. XP stays a decimal string through Lua/AIO (no IEEE-754 precision loss).
void SendHeader(Player* player, Character const& state, Progress const& account, bool open)
{
    XP const next = NextXP(account.level, xpTable);
    PublishBar(player, account.xp, next);
    Wire(player, "H|" + std::string(PoolName(state.account.second)) + "|" + std::to_string(account.level) + "|" +
        std::to_string(account.xp) + "|" + std::to_string(next) + "|" + (open ? "1" : "0"));
}
void Snapshot(Player* player, bool open, bool chat)
{
    auto& state = State(player);
    auto const& account = Account(state.account);
    auto left = Available(state.points, account.level);
    XP next = NextXP(account.level, xpTable);
    SendHeader(player, state, account, open);
    ChatHandler handler(player->GetSession());
    if (chat) handler.PSendSysMessage("Paragon pool={} level={} XP={}/{} (toward next level).", PoolName(state.account.second), account.level, account.xp, next);
    for (unsigned i = 0; i < 4; ++i)
    {
        Wire(player, "C|" + std::to_string(i) + "|" + std::to_string(left[i]));
        if (chat) handler.PSendSysMessage("{}: {} unspent points.", Categories[i], left[i]);
    }
    for (auto const& rule : rules)
    {
        unsigned count = state.points[rule.id-1];
        double const perPoint = rule.classResource ? ClassResource(player).paragonPerPoint : rule.value;
        std::string total = Number(Paid(player, rule, count));
        Wire(player, "R|" + std::to_string(rule.id) + "|" + rule.key + "|" + rule.name + "|" + std::to_string(rule.category) +
            "|" + std::to_string(count) + "|" + Number(perPoint) + "|" + total + "|" + std::to_string(rule.cap) + "|" + rule.unit);
        if (chat) handler.PSendSysMessage("{} ({}): {} points / {}; +{}{} total, +{}{} per point.", rule.name, rule.key, count,
            rule.cap ? std::to_string(rule.cap) : "uncapped", total, rule.unit, Number(perPoint), rule.unit);
    }
    Wire(player, "E");
    state.progressDirty = false;
    if (chat) handler.SendSysMessage("Out of combat: .dc paragon allocate <stat-key> <1|10|100>, deallocate <stat-key> <1|10|100>, or respec. Open: talent key, sheet Paragon button, /dcparagon.");
}
// The caller holds `lock` (Run). It is released for the commit and the read-back and taken
// again before anything shared is touched, so kill XP on every map waits for one player's
// clicks no longer (security.md G1 gaps). `saving` keeps a second change to the same
// character out while the lock is free; the state is only this character's own.
void StorePoints(Player* player, Character& state, Points const& candidate, std::unique_lock<std::mutex>& lock)
{
    Need(!state.saving, "Paragon is saving your last change; try again in a moment.");
    Need(Stats::ReplaceParagon(player, Contributions(player, candidate)), "Allocation would exceed supported stat limits.");
    auto tx = CharacterDatabase.BeginTransaction();
    tx->Append("DELETE FROM dc_character_paragon WHERE guid={}", Guid(player));
    for (auto const& rule : rules)
        if (candidate[rule.id-1]) tx->Append("INSERT INTO dc_character_paragon(guid,stat,points) VALUES({},{},{})", Guid(player), rule.id, candidate[rule.id-1]);
    // Async queue, awaited: the read below must see the commit (security.md G1).
    state.saving = true;
    bool saved = false;
    try
    {
        saved = WithoutLock(lock, [&]
        {
            bool const committed = CharacterDatabase.AsyncCommitTransaction(tx).m_future.get();
            return committed && ReadPoints(Guid(player)) == candidate;
        });
    }
    catch (...) { saved = false; } // the lock is held again here
    state.saving = false;
    try { Need(saved, "Paragon allocation could not be saved."); }
    catch (...)
    {
        Stats::ReplaceParagon(player, Contributions(player, state.points));
        ready = false; // Ambiguous commit: never continue from potentially stale state.
        throw;
    }
    state.points = candidate;
    state.dirty = false;
}
// A kill's effective gear percentage, shared by both award paths. Native
// CustomData owns the snapshot; death/evade/remove-world clear it even when
// there is no Paragon award. Never retain player pointers in a corpse.
struct PartyXPBonus : DataMap::Base
{
    XP hundredths = 0;
    std::set<uint32> recipients;
};

bool ParagonKillMember(Player* player, Unit* victim)
{
    return player && player->IsAlive() && player->IsInMap(victim) &&
        player->InSamePhase(victim) && player->IsAtGroupRewardDistance(victim);
}

bool LevellingKillMember(Player* player, Creature* victim, Player* tapper)
{
    // KillRewarder::_RewardXP: alive and no higher than the highest non-gray
    // member. Gray thresholds are monotonic, so this is the same gray gate.
    // Player::GiveXP then rejects disabled XP, missing tap and the server/trial
    // cap. Apply these eligibility gates, not a second
    // stock award calculation. Group rounding, ModHealth, vehicle and later
    // OnPlayerGiveXP modifiers do not change who counts in this average.
    // Stock leveling has no phase gate; the same-map tapper is exempt from
    // group reward distance (KillRewarder::_InitGroupData/_RewardGroup).
    if (!player || !player->IsAlive() || !player->IsInMap(victim) ||
        (player != tapper && !player->IsAtGroupRewardDistance(victim)) ||
        player->HasPlayerFlag(PLAYER_FLAGS_NO_XP_GAIN) ||
        player->HasPlayerFlag(PLAYER_FLAGS_NO_PLAY_TIME) || !victim->hasLootRecipient())
        return false;
    uint8 level = player->GetLevel();
    sScriptMgr->OnPlayerBeforeGetLevelForXPGain(player, level);
    uint32 cap = sWorld->getIntConfig(CONFIG_MAX_PLAYER_LEVEL);
    if (uint32 trialCap = sWorld->getIntConfig(CONFIG_TRIAL_LEVEL_CAP))
        if (player->GetSession()->IsTrialAccount())
            cap = std::min(cap, trialCap);
    return level < cap && victim->GetLevel() > Acore::XP::GetGrayLevel(level);
}

PartyXPBonus const* PartyBonus(Creature* victim, Player* tapper = nullptr)
{
    if (!victim || !victim->GetLootRecipientGroup())
        return nullptr;
    if (auto* cached = victim->CustomData.Get<PartyXPBonus>("DCPartyXPBonus"))
        return cached;

    PartyXPBonus bonus;
    double total = 0;
    unsigned tier = 0;
    bool const inRift = Rifts::InRift(victim, tier);
    std::lock_guard<std::mutex> lock(mutex);
    for (auto* ref = victim->GetLootRecipientGroup()->GetFirstMember(); ref; ref = ref->next())
    {
        Player* member = ref->GetSource();
        if (!member)
            continue;
        bool eligible = false;
        if (member->GetLevel() == NumericData::MaximumLevel())
        {
            eligible = ready && ParagonKillMember(member, victim) && ParagonClass(member) &&
                characters.count(Guid(member)) && !victim->IsPet() && !victim->IsTotem() &&
                !victim->IsCritter() && !victim->IsLootRewardDisabled() &&
                victim->IsDamageEnoughForLootingAndReward() &&
                tierBonuses.count(inRift ? tier : Difficulty::CurrentTier(member));
        }
        else if (member->GetLevel() < NumericData::MaximumLevel())
            eligible = LevellingKillMember(member, victim, tapper);
        if (!eligible)
            continue;
        bonus.recipients.insert(Guid(member));
        // stats.csv XP bonus: dc_common.cpp Calculate already divides each
        // level-70 member's gear percentage by xp_divisor. Average those
        // effective sheets, then round once using the existing award precision.
        if (auto sheet = Stats::Get(member->GetGUID().GetRawValue()))
            total += (*sheet)[Stat::XPBonus];
    }
    if (!bonus.recipients.empty())
        bonus.hundredths = Hundredths(total / bonus.recipients.size());
    auto* cached = victim->CustomData.GetDefault<PartyXPBonus>("DCPartyXPBonus");
    *cached = std::move(bonus);
    return cached;
}

void ClearPartyBonus(Unit* victim)
{
    if (victim)
        victim->CustomData.Erase("DCPartyXPBonus");
}

// Gear percentage is shared; flat XP is still the recipient's own value,
// added after the percentage. Non-kills and solo awards keep their old path.
XP SheetAward(Player* player, XP amount, bool fromKill, PartyXPBonus const* bonus = nullptr)
{
    if (!player || !amount || !fromKill)
        return amount;
    // Enlightened Shrine (pylons.md 4.3): the wearer's own kill XP, after the party's shared gear bonus.
    auto const enlightened = [player](XP paid)
    {
        double const pct = Combat::Pylons::ExperiencePct(player);
        return pct > 0.0 ? Enlightened(paid, Hundredths(pct)) : paid;
    };
    auto sheet = Stats::Get(player->GetGUID().GetRawValue());
    bool const shared = bonus && bonus->recipients.count(Guid(player));
    if (!sheet && !shared)
        return enlightened(amount);
    XP const percent = shared ? bonus->hundredths : Hundredths((*sheet)[Stat::XPBonus]);
    double const flat = sheet ? (*sheet).flatXP : 0.0;
    return enlightened(AwardXP(amount, percent, flat > 0.0 ? XP(flat) : XP(0)));
}
// Paragon XP lives in `accounts` (memory) and reaches the database in the background: a kill
// changes memory and never waits on the database. A pool is written, asynchronously, at most once per
// paragon_save_interval_ms while it keeps changing, at once on a Paragon level-up and for a rift's closing XP, and
// waited for when the last character of the account logs out, at the creation floor and at shutdown. One write per
// account is in flight at a time, so two never land out of order. A failed write is logged and the pool stays owed
// (it stays in memory and is tried again); the entry is not dropped from `accounts` until it is written.
struct Save
{
    bool dirty = false;   // memory is ahead of the database
    bool urgent = false;  // do not wait for the interval (a level-up, a rift's reward)
    bool flying = false;  // a write is in flight
    bool orphan = false;  // nobody is online and the logout write failed: the tick tries again, then forgets it
    std::uint64_t lastMs = 0; // when the last write started
    std::future<bool> inFlight;
};
std::map<AccountKey, Save> saves;
std::uint64_t ClockMs()
{
    return std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();
}
// Starts the write of the account's pool: false when nothing is owed or one is already in flight.
bool StartSave(AccountKey const& key)
{
    auto held = accounts.find(key);
    auto found = saves.find(key);
    if (held == accounts.end() || found == saves.end() || !found->second.dirty || found->second.flying)
        return false;
    auto tx = CharacterDatabase.BeginTransaction();
    tx->Append("UPDATE dc_account_paragon SET level={},xp={} WHERE account_id={} AND pool='{}'", held->second.level,
        held->second.xp, key.first, PoolName(key.second));
    found->second.inFlight = CharacterDatabase.AsyncCommitTransaction(tx).m_future;
    found->second.flying = true;
    found->second.dirty = false;
    found->second.urgent = false;
    found->second.lastMs = ClockMs();
    return true;
}
// Takes a finished write (or waits for it): a failed one is logged and the pool is owed again.
void Settle(AccountKey const& key, Save& save, bool wait)
{
    if (!save.flying || (!wait && save.inFlight.wait_for(std::chrono::seconds(0)) != std::future_status::ready))
        return;
    bool ok = false;
    try { ok = save.inFlight.get(); }
    catch (...) { ok = false; }
    save.flying = false;
    if (!ok)
    {
        save.dirty = true;
        LOG_ERROR("server", "[DC paragon] Paragon XP could not be saved (account {}, {} pool); it stays in memory and is tried again",
            key.first, PoolName(key.second));
    }
}
// Everything the account is owed, written and waited for. False when it could not be.
bool FlushNow(AccountKey const& key)
{
    auto found = saves.find(key);
    if (found == saves.end())
        return true;
    Settle(key, found->second, true);
    if (StartSave(key))
        Settle(key, found->second, true);
    return !found->second.dirty && !found->second.flying;
}
// Once per server tick: take finished writes, start the ones that are due, forget accounts left behind and written
// (not while a character of the account is online again: it holds the pool in memory and the kill path must not read).
void SaveTick()
{
    std::uint64_t const now = ClockMs();
    std::uint64_t const interval = static_cast<std::uint64_t>(std::max(0.0, DC::Tunables::Get("paragon", "paragon_save_interval_ms")));
    for (auto it = saves.begin(); it != saves.end();)
    {
        Settle(it->first, it->second, false);
        if (it->second.dirty && !it->second.flying && (it->second.urgent || now - it->second.lastMs >= interval))
            StartSave(it->first);
        if (it->second.orphan && !it->second.dirty && !it->second.flying
            && std::none_of(characters.begin(), characters.end(), [&](auto const& entry) { return entry.second.account == it->first; }))
        {
            accounts.erase(it->first);
            it = saves.erase(it);
        }
        else
            ++it;
    }
}
// Memory takes the new pool state; the database follows (above). Every character of the account is told: the bar's
// numbers moved (progressDirty), and on a level-up its points moved too (dirty).
void ApplyProgress(AccountKey const& key, Progress const& previous, Progress const& updated)
{
    accounts[key] = updated;
    auto& save = saves[key];
    save.dirty = true;
    if (updated.level != previous.level)
        save.urgent = true;
    for (auto& entry : characters)
        if (entry.second.account == key)
        {
            entry.second.progressDirty = true;
            if (updated.level != previous.level) entry.second.dirty = true;
        }
}
void AddXP(Player* player, XP amount, bool writeNow = false)
{
    auto& state = State(player);
    Need(player->GetLevel() == 70, "Paragon XP requires character level 70.");
    Need(amount > 0, "Grant a positive amount of Paragon XP.");
    auto previous = Account(state.account);
    auto updated = Grant(previous, amount, xpTable);
    ApplyProgress(state.account, previous, updated);
    if (updated.level != previous.level)
        state.announce = updated.level; // OnPlayerUpdate says it once, whatever the burst crossed
    if (writeNow || updated.level != previous.level)
        StartSave(state.account);
    // The bar's numbers go out from OnPlayerUpdate, once a tick; a kill sends nothing.
}
class World final : public WorldScript
{
public:
    World() : WorldScript("dc_paragon_world", {WORLDHOOK_ON_STARTUP, WORLDHOOK_ON_UPDATE, WORLDHOOK_ON_SHUTDOWN}) { }
    void OnUpdate(uint32) override
    {
        std::lock_guard<std::mutex> lock(mutex);
        SaveTick();
    }
    // Runs before KickAll (Main.cpp), so players are still online: every owed pool is written here, online ones included.
    // The later logouts find nothing owed, and the database is still open.
    void OnShutdown() override
    {
        std::lock_guard<std::mutex> lock(mutex);
        for (auto& entry : saves)
            FlushNow(entry.first);
    }
    void OnStartup() override
    {
        std::lock_guard<std::mutex> lock(mutex);
        try
        {
            // dc_character_paragon.stat stores the ID, so the ID-to-key pairing is
            // what a saved allocation means. Contiguous IDs are not enough: swap
            // two keys and every ID still runs 1..16 in the right categories while
            // the points a player saved now buy a different stat. The expected
            // pairing is compiled in here, so the sheet and the binary are two
            // independent witnesses that have to agree. "primary" pairs with id
            // 1 like every other key; its Stat is a placeholder, because the
            // stat is each player's own main stat (classPrimary, Contributions).
            struct Mapping { unsigned id; Stat stat; Bucket bucket; };
            std::map<std::string, Mapping> mappings = {
                {"primary",{1,Stat::Strength,Bucket::Flat}}, {"vitality",{2,Stat::Vitality,Bucket::Flat}},
                {"movement",{3,Stat::MovementSpeed,Bucket::Flat}}, {"resource",{4,Stat::MaxFury,Bucket::Flat}},
                {"ias",{5,Stat::AttackSpeed,Bucket::Flat}}, {"cdr",{6,Stat::CooldownReduction,Bucket::Flat}},
                {"chc",{7,Stat::CritChance,Bucket::Flat}}, {"chd",{8,Stat::CritDamage,Bucket::Flat}},
                {"armor",{9,Stat::Armor,Bucket::Percent}}, {"life",{10,Stat::LifePercent,Bucket::Flat}},
                {"resistance",{11,Stat::AllResistance,Bucket::Flat}}, {"regen",{12,Stat::LifeRegen,Bucket::Flat}},
                {"area",{13,Stat::AreaDamage,Bucket::Flat}}, {"rcr",{14,Stat::ResourceCostReduction,Bucket::Flat}},
                {"loh",{15,Stat::LifePerHit,Bucket::Flat}}, {"pickup",{16,Stat::GoldPickupRange,Bucket::Flat}}};
            auto rows = WorldDatabase.Query("SELECT id,stat_key,name,category,CAST(per_point AS CHAR),cap,unit FROM dc_paragon_rules ORDER BY id");
            Need(bool(rows), "dc_paragon_rules is missing.");
            unsigned count = 0;
            do
            {
                auto* f = rows->Fetch(); Rule rule;
                rule.id=f[0].Get<uint32>(); rule.key=f[1].Get<std::string>(); rule.name=f[2].Get<std::string>();
                rule.category=f[3].Get<uint32>(); rule.value=std::stod(f[4].Get<std::string>()); rule.cap=f[5].Get<uint32>(); rule.unit=f[6].Get<std::string>();
                Need(rule.id == count+1 && count < rules.size() && rule.category == count/4 && std::isfinite(rule.value) && rule.value > 0, "Invalid Paragon rule.");
                auto found = mappings.find(rule.key);
                Need(found != mappings.end(), "Unknown Paragon stat key.");
                Need(rule.id == found->second.id,
                     "Paragon stat id and key no longer pair as published; saved allocations would change meaning.");
                rule.stat=found->second.stat; rule.bucket=found->second.bucket; rule.classPrimary=rule.key=="primary";
                rule.classResource=rule.key=="resource";
                mappings.erase(found); rules[count++] = rule;
            } while (rows->NextRow());
            Need(count == rules.size() && mappings.empty(), "Missing Paragon stat rules.");
            rows=WorldDatabase.Query("SELECT level,xp_to_reach_level FROM dc_paragon_xp ORDER BY level");
            Need(bool(rows), "dc_paragon_xp is missing.");
            do
            {
                auto level=(*rows)[0].Get<int64>(), xp=(*rows)[1].Get<int64>();
                Need(level == int64(xpTable.size()+1) && xp > 0 && (xpTable.empty() || XP(xp) >= xpTable.back()), "Invalid Paragon XP table.");
                xpTable.push_back(XP(xp));
            } while (rows->NextRow());
            Need(xpTable.size() >= 800, "Paragon XP requires levels 1-800.");
            rows=WorldDatabase.Query("SELECT p.tier_id,t.xp_bonus_pct FROM dc_tier_phase p JOIN dc_difficulty_tiers t ON t.tier=p.tier_name ORDER BY p.tier_id");
            Need(bool(rows), "Paragon difficulty XP data missing.");
            do
            {
                unsigned tier=(*rows)[0].Get<uint8>(); auto pct=(*rows)[1].Get<int64>();
                Need(pct >= 0 && !(*rows)[1].IsNull(), "Invalid tier XP percentage.");
                Need(tierBonuses.emplace(tier,Multiply(XP(pct),100)).second, "Duplicate tier XP rule.");
            } while (rows->NextRow());
            for (unsigned tier=1; tier<=LaunchTierCount(); ++tier) Need(tierBonuses.count(tier) != 0, "Missing tier XP rule.");
            rows=WorldDatabase.Query("SELECT base_monster_xp FROM dc_loot_tuning WHERE source='normal'");
            Need(bool(rows) && rows->GetRowCount() == 1 && !(*rows)[0].IsNull(), "base_monster_xp tunable is missing.");
            auto base=(*rows)[0].Get<int64>(); Need(base > 0, "base_monster_xp must be positive."); baseXP=XP(base);
            rows=WorldDatabase.Query("SELECT per_member,bonus_cap,max_members FROM dc_paragon_party_xp WHERE id=1");
            Need(bool(rows), "Paragon party XP rule missing.");
            partyPerMember=(*rows)[0].Get<uint32>(); partyCap=(*rows)[1].Get<uint32>(); maxMembers=(*rows)[2].Get<uint32>();
            Need(maxMembers > 0 && Multiply(maxMembers-1,partyPerMember) == partyCap, "Invalid party XP rule.");
            for (auto const& tier : tierBonuses) (void)KillXP(baseXP,tier.second,maxMembers,partyPerMember,partyCap);
            Need(bool(CharacterDatabase.Query("SELECT COUNT(*) FROM dc_account_paragon")) &&
                 bool(CharacterDatabase.Query("SELECT COUNT(*) FROM dc_character_paragon")), "Paragon character migrations missing.");
            ready = true;
            LOG_INFO("server.loading", "[DC paragon] Loaded {} XP levels and {} stats; base_monster_xp={}; mode=normal until 11-hardcore.", xpTable.size(), rules.size(), baseXP);
        }
        catch (std::exception const& e) { LOG_ERROR("server", "[DC paragon] Disabled: {}",e.what()); }
    }
};
class Hooks final : public PlayerScript
{
public:
    Hooks() : PlayerScript("dc_paragon_player", {PLAYERHOOK_ON_LOGIN,PLAYERHOOK_ON_LOGOUT,PLAYERHOOK_ON_UPDATE,
        PLAYERHOOK_ON_DELETE_FROM_DB,PLAYERHOOK_ON_GIVE_EXP,PLAYERHOOK_ON_SET_MAX_LEVEL,
        PLAYERHOOK_ON_REWARD_KILL_REWARDER}) { }
    void OnPlayerRewardKillRewarder(Player*, KillRewarder* rewarder, bool, float&) override
    {
        // Unit::Kill may have replaced GetLootRecipient with the round-robin
        // looter. The stock rewarder still owns the original tapper identity.
        // Snapshot before the first member's award can change a level/sheet.
        if (rewarder && rewarder->GetVictim())
            PartyBonus(rewarder->GetVictim()->ToCreature(), rewarder->GetKiller());
    }
    void OnPlayerGiveXP(Player* player, uint32& amount, Unit* victim, uint8) override
    {
        // 04 K7 / 08 W3: level 70 starts Paragon. Never award ordinary XP there,
        // including quest/exploration sources; kill Paragon uses its own hook.
        if (player->GetLevel() >= NumericData::MaximumLevel()) { amount = 0; return; }
        // #55, the levelling half: the sheet's Experience Bonus applies below
        // the cap, on the core's own number, before the core banks it. Every
        // other multiplier the core has already applied stays where it is -
        // this adds one factor and reorders nothing.
        auto const* bonus = amount && victim ? PartyBonus(victim->ToCreature()) : nullptr;
        // Greater Rift: the XP split on the core's number, identity outside one.
        if (victim) amount = uint32(std::min<XP>(Rifts::GreaterRiftXp(victim->ToCreature(), amount), std::numeric_limits<uint32>::max()));
        XP const paid = SheetAward(player, amount, victim != nullptr, bonus);
        amount = uint32(std::min<XP>(paid, std::numeric_limits<uint32>::max()));
    }
    void OnPlayerSetMaxLevel(Player*, uint32& maxLevel) override { maxLevel = 70; }
    void OnPlayerLogin(Player* player) override
    {
        if (!ParagonClass(player)) return;
        std::lock_guard<std::mutex> lock(mutex);
        try
        {
            Check(player); auto key=Key(player); auto const& account=Account(key);
            Character state{key, ReadPoints(Guid(player)), false};
            Available(state.points,account.level);
            Need(Stats::ReplaceParagon(player,Contributions(player,state.points)), "Paragon stats could not load.");
            characters[Guid(player)] = state;
            PublishBar(player, account.xp, NextXP(account.level, xpTable));
        }
        catch (std::exception const& e)
        {
            LOG_ERROR("server", "[DC paragon] {} login: {}",player->GetName(),e.what());
            ChatHandler(player->GetSession()).SendSysMessage(e.what());
            player->GetSession()->KickPlayer(std::string("Paragon state could not load"));
        }
    }
    void OnPlayerLogout(Player* player) override
    {
        std::lock_guard<std::mutex> lock(mutex);
        auto key=Key(player); characters.erase(Guid(player));
        if (std::none_of(characters.begin(),characters.end(),[&](auto const& entry){return entry.second.account==key;}))
        {
            // The last character of the account leaves: its XP is written and waited for before a relog can read
            // the database. A write that fails keeps the pool in memory; the tick tries again.
            if (FlushNow(key)) { accounts.erase(key); saves.erase(key); }
            else saves[key].orphan = true;
        }
    }
    void OnPlayerDeleteFromDB(CharacterDatabaseTransaction tx, uint32 guid) override
    {
        tx->Append("DELETE FROM dc_character_paragon WHERE guid={}",guid); // Account pool survives deletion/death.
    }
    void OnPlayerUpdate(Player* player, uint32) override
    {
        std::lock_guard<std::mutex> lock(mutex);
        auto found=characters.find(Guid(player));
        if (!ready || found==characters.end()) return;
        // Re-asserted every tick, not only on gain: dc_world's GiveLevel(70) on a
        // first login, the resting tick and GM level commands all write these
        // fields after ours, and the client must never show a stock number.
        auto held=accounts.find(found->second.account);
        if (held!=accounts.end()) PublishBar(player,held->second.xp,NextXP(held->second.level,xpTable));
        if (found->second.dirty && Stats::ReplaceParagon(player,Contributions(player,found->second.points)))
        {
            found->second.dirty=false;
            Snapshot(player,false,false);
        }
        else if (!found->second.dirty && found->second.progressDirty && held!=accounts.end())
        {
            // A burst of kills moved only the bar: the H record, once a tick. C and R move with a level-up (above).
            SendHeader(player,found->second,held->second,false);
            found->second.progressDirty=false;
        }
        if (found->second.announce)
        {
            ChatHandler(player->GetSession()).PSendSysMessage("Paragon level {}.",found->second.announce);
            found->second.announce=0;
        }
    }
    static void Kill(Creature* victim)
    {
        if (!victim || victim->IsPet() || victim->IsTotem() || victim->IsCritter() || victim->IsLootRewardDisabled() || !victim->IsDamageEnoughForLootingAndReward()) return;
        // Credit the tapped owner/group, including pet kills and finishing blows by outsiders.
        Player* recipient=victim->GetLootRecipient();
        Group* group=victim->GetLootRecipientGroup();
        if (!recipient && !group) return;
        std::vector<Player*> members;
        auto eligible=[&](Player* p) {return ParagonKillMember(p, victim);};
        if (group)
        {
            for (auto* ref=group->GetFirstMember();ref;ref=ref->next()) if (eligible(ref->GetSource())) members.push_back(ref->GetSource());
        }
        else if (eligible(recipient)) members.push_back(recipient);
        unsigned tier=0;
        bool inRift=Rifts::InRift(victim,tier);
        auto const* bonus = PartyBonus(victim);
        std::lock_guard<std::mutex> lock(mutex);
        if (!ready) return;
        for (auto* member : members)
        {
            if (!ParagonClass(member) || member->GetLevel()!=NumericData::MaximumLevel()) continue;
            try
            {
                unsigned selected=inRift?tier:Difficulty::CurrentTier(member);
                auto amount=KillXP(baseXP,tierBonuses.at(selected),unsigned(members.size()),partyPerMember,partyCap);
                amount=Rifts::GreaterRiftXp(victim,amount); // Greater Rift: the XP split, identity outside one
                // #55, the Paragon half: at the cap the kill XP is ours, and
                // the sheet's Experience Bonus applies to it the same way it
                // applies below the cap, so that
                // the bonus speeds up Paragon too. The tier and party factors
                // KillXP already applied are untouched.
                AddXP(member,SheetAward(member,amount,true,bonus)); // memory only: no database, no message
            }
            catch (std::exception const& e)
            {
                LOG_ERROR("server", "[DC paragon] XP for {}: {}",member->GetName(),e.what());
                ChatHandler(member->GetSession()).SendSysMessage(e.what());
            }
        }
    }
};
class Deaths final : public UnitScript
{
public:
    Deaths() : UnitScript("dc_paragon_death",true,{UNITHOOK_ON_UNIT_DEATH, UNITHOOK_ON_UNIT_ENTER_EVADE_MODE}) { }
    // Unit::Kill emits this once after reward/death handling for every killer
    // type. Player/pet-only hooks omit guardian summons and NPC finishing blows.
    void OnUnitDeath(Unit* victim, Unit*) override
    {
        // Clear on early return or exception too, after the shared award.
        struct Cleanup
        {
            Unit* victim;
            ~Cleanup() { ClearPartyBonus(victim); }
        } cleanup{victim};
        if (victim) Hooks::Kill(victim->ToCreature());
    }
    void OnUnitEnterEvadeMode(Unit* unit, uint8) override { ClearPartyBonus(unit); }
};
class PartyBonusLifetime final : public AllCreatureScript
{
public:
    PartyBonusLifetime() : AllCreatureScript("dc_paragon_party_bonus_lifetime") { }
    void OnCreatureRemoveWorld(Creature* creature) override { ClearPartyBonus(creature); }
    void OnCreatureAddWorld(Creature* creature) override { ClearPartyBonus(creature); }
};
class Commands final : public CommandScript
{
public:
    Commands() : CommandScript("dc_paragon_commands") { }
    Acore::ChatCommands::ChatCommandTable GetCommands() const override
    {
        using namespace Acore::ChatCommands;
        static ChatCommandTable paragon={{"xp",XPCommand,SEC_ADMINISTRATOR,Console::No},
            {"allocate",Allocate,SEC_PLAYER,Console::No},{"deallocate",Deallocate,SEC_PLAYER,Console::No},
            {"respec",Respec,SEC_PLAYER,Console::No},{"open",Open,SEC_PLAYER,Console::No},
            {"sync",Sync,SEC_PLAYER,Console::No},{"",Show,SEC_PLAYER,Console::No}};
        static ChatCommandTable dc={{"paragon",paragon}};
        static ChatCommandTable root={{"dc",dc}}; return root;
    }
    static inline DC::Gap::PerPlayer editGap; // allocate and deallocate share one gap per character
    template<class Action> static bool Run(ChatHandler* handler, Action action)
    {
        std::unique_lock<std::mutex> lock(mutex);
        auto* player=handler->GetSession()->GetPlayer();
        try
        {
            State(player);
            if constexpr (std::is_invocable_v<Action, Player*, std::unique_lock<std::mutex>&>) action(player, lock);
            else action(player);
            return true;
        }
        catch (std::exception const& e) { handler->SendErrorMessage(e.what()); Wire(player,"X|"+std::string(e.what())); return false; }
    }
    static void CanEdit(Player* player)
    {
        Need(!player->IsInCombat(),"Paragon cannot be opened or changed in combat.");
        Need(player->IsAlive(),"Paragon changes require a living character.");
        Need(player->GetLevel()==70,"Paragon allocation requires level 70; sourced per-point values are level-70 values.");
    }
    static bool EditGapOpen(Player* player)
    {
        return !player || editGap.Admit(player->GetGUID().GetRawValue(), DC::Gap::NowMs(),
                                        DC::Gap::GapFromTunable(DC::Tunables::Get("paragon","allocate_gap_ms")));
    }
    static bool Edit(ChatHandler* h, std::string const& key, uint32 amount, bool allocate)
    {
        // Inside the gap: dropped without a word. The addon draws only what the server sends,
        // so its view is still the server's (security.md G1 gaps).
        if (!EditGapOpen(h->GetSession()->GetPlayer()))
            return true;
        return Run(h,[&](Player* p, std::unique_lock<std::mutex>& lock)
        {
            CanEdit(p); auto& state=State(p); auto candidate=state.points;
            auto rule=std::find_if(rules.begin(),rules.end(),[&](Rule const& r){return r.key==key;});
            Need(rule!=rules.end(),"Unknown Paragon stat key; use .dc paragon to list keys.");
            auto left=Available(candidate,Account(state.account).level);
            candidate[rule->id-1]=Change(candidate[rule->id-1],amount,allocate,left[rule->category],rule->cap);
            StorePoints(p,state,candidate,lock); Snapshot(p,false,true);
        });
    }
    static bool Allocate(ChatHandler* h,std::string key,uint32 amount) {return Edit(h,key,amount,true);}
    static bool Deallocate(ChatHandler* h,std::string key,uint32 amount) {return Edit(h,key,amount,false);}
    static bool XPCommand(ChatHandler* h,uint64 amount) {return Run(h,[&](Player* p){AddXP(p,amount);});}
    static bool Show(ChatHandler* h) {return Run(h,[](Player* p){Snapshot(p,false,true);});}
    static bool Sync(ChatHandler* h) {return Run(h,[](Player* p){Snapshot(p,false,false);});}
    static bool Open(ChatHandler* h) {return Run(h,[](Player* p){Need(!p->IsInCombat(),"Paragon cannot be opened or changed in combat.");Snapshot(p,true,false);});}
    static std::uint64_t NowMs()
    {
        return std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();
    }
    // The attempt is stamped before the commit, so a client looping on a failing
    // respec is throttled as well (security.md G1).
    static void RespecGate(Character& state)
    {
        std::uint64_t const now = NowMs();
        Need(!RespecCooling(now, state.hasRespec, state.lastRespecMs,
                            static_cast<std::uint64_t>(std::max(0.0, DC::Tunables::Get("paragon", "respec_cooldown_ms")))),
             "Respec was used a moment ago; try again in a second.");
        state.hasRespec = true;
        state.lastRespecMs = now;
    }
    static bool Respec(ChatHandler* h) {return Run(h,[](Player* p, std::unique_lock<std::mutex>& lock){CanEdit(p);auto& state=State(p);RespecGate(state);StorePoints(p,state,{},lock);Snapshot(p,false,true);});}
};
}
// The one Paragon XP entry point other folders get. AddXP itself is unchanged
// and stays internal, including its assumption that the caller already holds
// the module lock - every call site above takes it first. A raw export would
// hand that obligation to a caller that cannot see the mutex, so the lock is
// taken here, and AddXP's throwing contract becomes a bool so one ineligible
// member cannot abort a whole payout.
bool GrantXP(Player* player, std::uint64_t amount, std::string& error)
{
    if (!amount) return true;              // nothing owed is not a failure
    std::lock_guard<std::mutex> lock(mutex);
    try { AddXP(player, amount, true); return true; } // the rift's closing XP is written at once
    catch (std::exception const& e) { error = e.what(); return false; }
}
bool TopUpLevel(Player* player, std::uint32_t target, std::uint32_t& before,
                std::uint32_t& after, std::string& error)
{
    std::lock_guard<std::mutex> lock(mutex);
    try
    {
        auto const& state = State(player);
        auto const& progress = Account(state.account);
        before = progress.level;
        after = before;
        if (before >= target)
            return true;
        // Sum per-level thresholds from the current in-level XP. AddXP then
        // runs the same Grant/DB/dirty-state/Snapshot path as an ordinary award.
        XP amount = NextXP(before, xpTable) - progress.xp;
        for (std::uint32_t level = before + 1; level < target; ++level)
            amount = Add(amount, NextXP(level, xpTable));
        AddXP(player, amount, true);
        after = Account(state.account).level;
        return true;
    }
    catch (std::exception const& e)
    {
        error = e.what();
        return false;
    }
}
bool EnsureStartingLevel(Player* player, std::uint32_t target, std::string& error)
{
    std::lock_guard<std::mutex> lock(mutex);
    try
    {
        Check(player);
        auto const mode = Hardcore::ModeOf(player);
        Need(mode != Hardcore::Mode::Unchosen, "Starting Paragon requires a permanent character mode.");
        Need(target <= xpTable.size(), "Starting Paragon exceeds the sourced XP table.");
        // Creation does not install Character state or allocate any points.
        AccountKey const key{player->GetSession()->GetAccountId(),
                             mode == Hardcore::Mode::Hardcore ? Pool::Hardcore : Pool::Normal};
        auto const previous = Account(key);
        bool written = true;
        bool const raised = previous.level < target;
        if (raised)
        {
            XP amount = NextXP(previous.level, xpTable) - previous.xp;
            for (std::uint32_t level = previous.level + 1; level < target; ++level)
                amount = Add(amount, NextXP(level, xpTable));
            ApplyProgress(key, previous, Grant(previous, amount, xpTable));
            written = FlushNow(key); // the creation floor is written and waited for, once per character
        }
        if (std::none_of(characters.begin(), characters.end(),
                         [&](auto const& entry) { return entry.second.account == key; }))
        {
            // Nobody of the account is online: settle what is owed (a failed logout write included), then forget it;
            // a write that failed stays owed to the tick.
            if (raised ? written : FlushNow(key))
            {
                accounts.erase(key);
                saves.erase(key);
            }
            else
                saves[key].orphan = true;
        }
        Need(written, "Paragon XP could not be saved.");
        return true;
    }
    catch (std::exception const& e)
    {
        error = e.what();
        return false;
    }
}
void RegisterScripts() { new World(); new Hooks(); new Deaths(); new PartyBonusLifetime(); new Commands(); }
}
