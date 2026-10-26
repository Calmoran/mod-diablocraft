#pragma once
// What the follower skills share between their files: the player's follower as the skills see it, the sheet's numbers, the cooldowns
// and the few stock holds the skills put on enemies. dc_follower_skills.cpp defines them; dc_follower_templar.cpp is the Templar's.
#include "dc_follower_skill_rules.h"
#include "../dc_resources.h"
#include "../../common/dc_common.h"
#include "../../items/dc_items.h"

#include <cstdint>
#include <string_view>

class Creature;
class Player;
class Unit;

namespace DC::Classes::Follower
{
// The ids of dc_follower (data/d3/followers_roster.csv).
inline constexpr unsigned TemplarId = 1;
inline constexpr unsigned ScoundrelId = 2;
inline constexpr unsigned EnchantressId = 3;

// A player and the follower standing beside them, with what the skills read of it.
struct Ctx
{
    Player* player = nullptr;
    Creature* companion = nullptr;
    unsigned follower = 0;
    Items::FollowerGear::SkillStats stats; // main stat, level and swing of the follower's own gear
    double share = 0;                      // how far the main stat is up the scale (0 to 1)
    unsigned level = 0;
    bool halved = false;   // a relic halves the follower's cooldowns
    bool allSkills = false; // a relic gives it every skill
};

// The context of the player's follower; false when none is out and alive, or the data is not loaded.
bool Context(Player* player, Ctx& out);

// Whether the skill is on: it is the pick of its tier and the tier is open, or the all-skills relic is worn.
bool On(Ctx const& c, std::string_view skill);

// A rule every skill shares (the sheet's row with no follower and no skill); 0 when the sheet has none.
double Rule(std::string_view token);
// The sheet's number of a skill at no main stat; 0 when the sheet has none.
double Raw(unsigned follower, std::string_view skill, std::string_view token);
// The sheet's number of a skill at the follower's main stat (between its minimum and its maximum).
double Num(Ctx const& c, std::string_view skill, std::string_view token);

bool Ready(Ctx const& c, std::string_view skill);
// Starts the skill's cooldown (dc_follower_skill), halved by the relic.
void Spend(Ctx const& c, std::string_view skill);

// The stock auras the skills put on enemies, cast by `caster` (the companion for what the Templar does): a stun, a slow of `pct`
// percent, a taunt. A second one restarts the first.
void Stun(Unit* caster, Unit* target, double seconds);
void Slow(Unit* caster, Unit* target, double pct, double seconds);
void Taunt(Unit* caster, Unit* target, double seconds);
// `amount` Life given to `target` as a heal of the player's under the stock spell `spellId`.
void Heal(Player* healer, Unit* target, std::uint32_t spellId, double amount);
// One hit of `pct` percent of the follower's weapon damage on `target`, dealt as the player's under the stock spell `spellId`: it rolls
// the follower's critical hit chance (and what its skills add) and carries its damage bonuses. True when it was critical.
bool Strike(Ctx const& c, Unit* target, std::uint32_t spellId, double pct, unsigned schoolMask);
// An attack-speed slow of `pct` percent on `target` for `seconds` (stock "Slow", one MOD_MELEE_HASTE effect).
void Weary(Unit* caster, Unit* target, double pct, double seconds);
// `want` of a stat on the player's sheet, held under `key` (a skill's own): it replaces what the key put there before and nothing takes
// it off; the follower going away does (ClearStanding). The element is the bonus' own for an elemental one.
void Stand(Player* player, std::uint64_t key, Stat stat, Bucket bucket, double want, Element element = Element::Physical);
// What the key has put on the sheet now (0 when nothing) and the element it is for.
double Standing(Player* player, std::uint64_t key, Element* element = nullptr);
void ClearStanding(Player* player);
// `player` is invisible to enemies for `seconds`, nothing breaking it (stock "Super Invis").
void Conceal(Player* player, double seconds);

// A shield on the player that takes every blow until the time.
void Shield(Player* player, std::uint64_t untilMs);
bool Shielded(Player* player);
std::uint64_t Now();

namespace Templar
{
// The Templar's skills that cast and pulse; `diffMs` is the time since the last look.
void Tick(Ctx& c, Unit* target, std::uint32_t diffMs);
// The factor Inspire puts on what the player's skills generate of `resource` (Fury, Spirit, Essence): 1 for any other, and when the Templar is not out.
double Generation(Player const* player, Resources::Resource const& resource);
// The Templar is gone (dismissed, down, a party): what stands on the player ends.
void Away(Player* player);
// An enemy hit the player (Intervene).
void Hurt(Ctx& c, Unit* attacker);
// The Templar hit an enemy or an enemy hit the Templar (Intimidate).
void Fought(Ctx& c, Unit* enemy);
// A fatal blow on the player (Guardian): true when it was saved.
bool Fatal(Ctx& c, std::uint32_t& damage);
} // namespace Templar

namespace Scoundrel
{
// The Scoundrel's skills that cast and stand: Anatomy's chance on the player, and the shots, volleys and cloud.
void Tick(Ctx& c, Unit* target, std::uint32_t diffMs);
// A fatal blow on the player (Vanish): true when it was saved.
bool Fatal(Ctx& c, std::uint32_t& damage);
// A critical hit by the player or by the Scoundrel (Hysteria).
void Crit(Ctx const& c);
// What the Scoundrel's hits carry: Hysteria's more damage, and Anatomy's and the cloud's more critical hit chance against `target`.
double DamageFactor(Ctx const& c);
double CritBonus(Ctx const& c, Unit* target);
// Percent more critical hit chance against `target` for any hit of `player`'s: the cloud (100 inside it).
double CloudBonus(Player const* player, Unit const* target);
// The Scoundrel is gone (dismissed, down, a party): what stands on the player ends.
void Away(Player* player);
} // namespace Scoundrel

namespace Enchantress
{
// The Enchantress' skills that cast and stand: the auras on the player's sheet, Charm, the orb, the pool.
void Tick(Ctx& c, Unit* target, std::uint32_t diffMs);
// A fatal blow on the player (Fate's Lapse): true when it was saved.
bool Fatal(Ctx& c, std::uint32_t& damage);
// An enemy struck the player or the Enchantress in melee (Powered Shield).
void Struck(Ctx& c, Unit* attacker);
// The multiplier Powered Shield puts on a blow the player takes.
double Taken(Player const* player, bool melee);
// The Enchantress is gone: her pool and her shield end.
void Away(Player* player);
} // namespace Enchantress
} // namespace DC::Classes::Follower
