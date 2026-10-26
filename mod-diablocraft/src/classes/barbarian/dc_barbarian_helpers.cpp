#include "dc_barbarian_internal.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_proc_math.h"
#include "../../combat/dc_spell_numbers.h"
#include "../../combat/dc_passives.h"
#include "../dc_resources.h"
#include "CellImpl.h"
#include "GridNotifiers.h"
#include "GridNotifiersImpl.h"
#include "MotionMaster.h"
#include "Player.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include <algorithm>
#include <cmath>

// Literal audit (docs/research/literal-audit-claude.md): the numbers below are
// constants, not tunables - recorded here, nothing else changes.
// Audit 6 (the bare x10 here and at dc_passives.cpp, dc_primaries.cpp, dc_ancients.cpp) moved: every Fury write goes through dc_resources.h.
// Constant (131): multiplier in the ability-state signature hash; Hash seed, no game meaning.
// Constant (81000, 81137, 81310): the same range plus the marker shell; Third and fourth copies of the range live in dc_classes.cpp:33 and dc_rifts_internal.h:356.
// Constant (81710, 81910): aura-shell and proc-shell id bases; Identifiers.

namespace DC::Combat::Abilities
{
    namespace Shared
    {
        std::unordered_map<std::string, double> tuning;
        std::unordered_map<uint64, State> states;
        // All mutation runs on the owning player's map thread. The global index is
        // guarded because separate maps may update simultaneously.
        std::recursive_mutex mutex;
        std::unordered_map<uint64, std::vector<Classes::Slot>> bars;
        uint32 AuraId(uint32 id)
        {
            return Marker + id - First;
        }
        // Only the Barbarian's block has marker auras. Shells::Abilities also
        // lists every other class's skills too, and
        // AuraId of one of those names no record of ours, so the loops that walk
        // every ability's marker skip them.
        bool HasMarker(Row const& row)
        {
            return row.id >= First && row.id <= Last;
        }
        Row const* Base(std::string const& skill)
        {
            for (auto const& r : Shells::Abilities)
                if (r.skill == skill && !*r.rune)
                    return &r;
            return nullptr;
        }
        bool Rune(Row const& row, char const* name)
        {
            return std::string(row.rune) == name;
        }
        // The row whose numbers a rune's effect reads: `active` when it is that rune, else the rune's own row when a power gives the player the
        // rune without choosing it (kind `rune`: the Wastes 6-piece's Dust Devils, Mortick's Brace's every rune), else null. A rune that is
        // chosen and also given is the one row, so it counts once.
        Row const* RuneRow(Player const* p, Row const& active, char const* rune)
        {
            if (Rune(active, rune))
                return &active;
            if (!p || !ItemPowers::GrantsRune(p, active.skill, rune))
                return nullptr;
            for (auto const& r : Shells::Abilities)
                if (std::string(r.skill) == active.skill && Rune(r, rune))
                    return &r;
            return nullptr;
        }
        Row const* Active(Player* p, char const* skill)
        {
            std::lock_guard<std::recursive_mutex> lock(mutex);
            auto key = p->GetGUID().GetRawValue();
            if (!bars.count(key))
                bars[key] = Classes::Bar(p);
            for (auto const& slot : bars[key])
                if (slot.skill == skill)
                    return Shells::FindAbility(slot.spellId);
            return nullptr;
        }
        Row const* Buff(Unit const* p, char const* skill)
        {
            if (!p)
                return nullptr;
            for (auto const& r : Shells::Abilities)
                if (std::string(r.skill) == skill && p->HasAura(AuraId(r.id)))
                    return &r;
            return nullptr;
        }
        double Tune(char const* key)
        {
            auto it = tuning.find(key);
            return it == tuning.end() ? 0 : it->second;
        }
        void Fury(Player* p, double amount)
        {
            Resources::Add(p, Resources::Fury, amount * Passives::GenerationFactor(p));
        }
        void Heal(Player* owner, Unit* target, uint32 spell, double amount)
        {
            if (!target || !target->IsAlive() || amount <= 0)
                return;
            if (auto info = sSpellMgr->GetSpellInfo(spell))
            {
                HealInfo heal(owner, target, uint32(std::min(amount, double(UINT32_MAX))), info,
                              SPELL_SCHOOL_MASK_HOLY);
                owner->HealBySpell(heal);
            }
        }
        namespace
        {
        struct Check
        {
            Player* owner;
            Unit* center;
            double radius;
            bool friendly;
            bool operator()(Unit* u) const
            {
                return u && u->IsAlive() && u->IsInWorld() && owner->IsInMap(u) && owner->InSamePhase(u) &&
                       center->GetExactDist(u) <= radius && owner->IsWithinLOSInMap(u) &&
                       (friendly ? owner->IsValidAssistTarget(u) : owner->IsValidAttackTarget(u));
            }
        };
        } // namespace
        std::vector<Unit*> Nearby(Player* owner, Unit* center, double radius, bool friendly)
        {
            std::list<Unit*> units;
            Check check{owner, center, radius, friendly};
            Acore::UnitListSearcher<Check> searcher(owner, units, check);
            Cell::VisitObjects(center->GetPositionX(), center->GetPositionY(), owner->GetMap(), searcher,
                               float(radius));
            if (friendly && check(owner))
                units.push_back(owner);
            std::vector<Unit*> result;
            for (auto u : units)
                if (std::find(result.begin(), result.end(), u) == result.end())
                    result.push_back(u);
            return result;
        }
        namespace
        {
        struct PositionCheck
        {
            Player* owner;
            Position center;
            double radius;
            bool operator()(Unit* u) const
            {
                return u && u->IsAlive() && owner->IsInMap(u) && owner->InSamePhase(u) && owner->IsWithinLOSInMap(u) &&
                       owner->IsValidAttackTarget(u) && center.GetExactDist(u) <= radius;
            }
        };
        } // namespace
        std::vector<Unit*> At(Player* p, Position const& center, double radius)
        {
            if (radius <= 0)
                return {};
            std::list<Unit*> units;
            PositionCheck check{p, center, radius};
            Acore::UnitListSearcher<PositionCheck> searcher(p, units, check);
            Cell::VisitObjects(center.GetPositionX(), center.GetPositionY(), p->GetMap(), searcher, float(radius));
            return {units.begin(), units.end()};
        }
        double ZoneDamage(double total, double previous, double elapsed, double duration)
        {
            if (duration <= 0) return 0;
            return std::floor(total * std::min(elapsed, duration) / duration) -
                   std::floor(total * std::clamp(previous, 0.0, duration) / duration);
        }
        unsigned TremorsDue(double previous, double elapsed, double duration, unsigned count)
        {
            if (duration <= 0) return 0;
            return unsigned(std::floor(count * std::min(elapsed, duration) / duration)) -
                   unsigned(std::floor(count * std::clamp(previous, 0.0, duration) / duration));
        }
        void ZoneStart(Player* p, Row const& row, Position const& center, double duration, double radius,
                       double overridePct, bool slowOnly)
        {
            if (duration <= 0 || radius <= 0)
                return;
            Hit h;
            if (!ComputeHit(p, nullptr, row.id, h) || h.skill <= 0)
                return;
            // DoT snapshots always bake average crit; the ordinary direct-skill roll is
            // replaced here rather than repeating the roll once per tick.
            auto sheet = Stats::Get(p->GetGUID().GetRawValue());
            if (!sheet)
                return;
            double average =
                1 + std::clamp((*sheet)[Stat::CritChance] / 100, 0.0, 1.0) * (*sheet)[Stat::CritDamage] / 100;
            if (overridePct > 0)
                h.total *= overridePct / 100 / h.skill;
            h.total = h.total / h.crit * average;
            h.crit = average;
            h.critical = false;
            h.areaDamage = 0;
            states[p->GetGUID().GetRawValue()].zones.push_back({row.id, center, h, duration * 1000, 0, radius, false, slowOnly, {}});
        }
        void Mark(Player* owner, Unit* target, Row const& row, double seconds)
        {
            if (!target || seconds <= 0)
                return;
            // A skill refresh replaces its rune, including a marker from another caster.
            for (auto const& old : Shells::Abilities)
                if (std::string(old.skill) == row.skill)
                    target->RemoveAurasDueToSpell(AuraId(old.id));
            if (auto aura = owner->AddAura(AuraId(row.id), target))
            {
                aura->SetMaxDuration(int32(seconds * 1000));
                aura->SetDuration(int32(seconds * 1000));
            }
        }
        void Control(Player* p, Unit* u, Row const& row, double seconds)
        {
            if (seconds <= 0)
                return;
            if (auto aura = p->AddAura(81710 + row.id - First, u))
            {
                aura->SetMaxDuration(int32(seconds * 1000));
                aura->SetDuration(int32(seconds * 1000));
            }
        }
        void Add(Player* p, uint32 id, Stat stat, double value, Bucket bucket)
        {
            Stats::AddContribution(p->GetGUID().GetRawValue(), {Source::Temporary, stat, id, value, bucket});
        }
        bool Procs(uint32 spellId)
        {
            // Both crit procs roll the proc coefficient of the skill and rune that
            // landed the crit. A hit whose spell states none (a pet's, an item's, a
            // proc of a proc) does not proc; it is never read as 1.
            return Proc::Rolls(Numbers::Get(spellId, "proc_coefficient"),
                               [](float pct) { return roll_chance_f(pct); });
        }
        uint32 WrathBuff()
        {
            static uint32 const id = Shells::HelperFor("War Cry - Hardened Wrath - buff");
            return id;
        }
        uint32 FrayBuff()
        {
            static uint32 const id = Shells::HelperFor("Battle Rage - Into the Fray - buff");
            return id;
        }
        void Reduce(Player* p, char const* skill, double milliseconds)
        {
            for (auto const& r : Shells::Abilities)
                if (std::string(r.skill) == skill && p->GetSpellCooldownDelay(r.id))
                    p->ModifySpellCooldown(r.id, -int32(milliseconds));
        }
        void Eruption(Player* p, Unit* center, uint32 spell, double pct, double radius)
        {
            Hit snapshot;
            if (!ComputeHit(p, center, spell, snapshot) || snapshot.skill <= 0)
                return;
            snapshot.total *= (pct / 100) / snapshot.skill;
            snapshot.areaDamage = 0;
            for (auto u : Nearby(p, center, radius))
                DealHit(p, u, spell, snapshot);
        }
    } // namespace Shared
} // namespace DC::Combat::Abilities
