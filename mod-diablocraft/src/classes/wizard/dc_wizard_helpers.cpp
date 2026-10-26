#include "dc_wizard_internal.h"
#include "../../combat/dc_gem_powers.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_passives.h"
#include "Creature.h"
#include "GameTime.h"
#include "ObjectAccessor.h"
#include "SpellAuraEffects.h"
#include "SpellMgr.h"
#include "SpellScript.h"
#include "TemporarySummon.h"
#include <algorithm>
#include <cmath>

namespace DC::Combat::Wizard::Shared
{

    std::recursive_mutex mutex;

    std::map<std::string, double> tuning;

    std::unordered_map<uint64, State> states;

    // An enemy's reduced damage, whoever put it there: Debilitating
    // Force and Spellsteal's debuff, keyed by the enemy.
    std::unordered_map<uint64, std::map<uint32, Expiring>> weakened;

    // --- proc coefficients ----------------------------------------------
    //
    // A hit's proc coefficient scales every "chance on hit" (d3planner
    // cast.js:568-572, damage.js:145). It is the source record's
    // proc_coefficient - a DoT tick's too, since each tick re-enters its
    // cast's castInfo (buffs.js:324, damage.js:375-376) - and zero for a
    // record with none, as for a pet (damage.js:130). A hit whose own
    // coefficient differs from its record's (the Scorch wall, Shocking
    // Aspect's shock, Blazar's explosion) is struck inside a ProcAs.
    thread_local std::optional<double> procOverride;

    double Num(uint32 id, std::string_view token, std::string_view qualifier)
    {
        return Numbers::Num(id, token, qualifier);
    }

    // A placeholder tunable not yet filled reads zero, and every
    // caller treats zero as "not built yet" rather than as a number.
    double Tune(char const* name)
    {
        std::lock_guard<std::recursive_mutex> guard(mutex);
        auto found = tuning.find(name);
        return found == tuning.end() ? 0.0 : std::max(0.0, found->second);
    }

    uint64 Now()
    {
        return uint64(GameTime::GetGameTimeMS().count());
    }

    std::mt19937_64& Engine()
    {
        static thread_local std::mt19937_64 engine{std::random_device{}()};
        return engine;
    }

    double Roll()
    {
        return std::uniform_real_distribution<double>(0.0, 100.0)(Engine());
    }

    double ProcOf(uint32 id)
    {
        if (procOverride)
            return *procOverride;
        return Numbers::Get(id, "proc_coefficient").value_or(0);
    }

    Row const* RowOf(uint32 id)
    {
        return Shells::FindAbility(id);
    }

    bool IsSkill(uint32 id, std::string_view skill)
    {
        Row const* row = RowOf(id);
        return row && skill == row->skill;
    }

    bool IsRune(uint32 id, std::string_view rune)
    {
        Row const* row = RowOf(id);
        return row && rune == row->rune;
    }

    uint32 BaseOf(std::string_view skill)
    {
        for (Row const& row : Shells::Abilities)
            if (skill == row.skill && !*row.rune)
                return row.id;
        return 0;
    }

    uint32 PassiveId(std::string_view name)
    {
        for (auto const& passive : Shells::Passives)
            if (name == passive.name)
                return passive.id;
        return 0;
    }

    bool Has(Player* player, char const* passive)
    {
        return Passives::Has(player, passive);
    }

    // The record of `skill` whose aura the player wears, 0 for none: a
    // buff's rune is the record that was cast.
    uint32 BuffOf(Unit* unit, std::string_view skill)
    {
        if (!unit)
            return 0;
        for (Row const& row : Shells::Abilities)
            if (skill == row.skill && unit->HasAura(row.id))
                return row.id;
        return 0;
    }

    bool BuffRune(Unit* unit, std::string_view skill, std::string_view rune)
    {
        uint32 id = BuffOf(unit, skill);
        return id && IsRune(id, rune);
    }

    uint32 ArchonAbilityId(std::string_view name)
    {
        for (auto const& ability : Shells::ArchonAbilities)
            if (name == ability.name)
                return ability.id;
        return 0;
    }

    char const* ArchonAbilityName(uint32 id)
    {
        for (auto const& ability : Shells::ArchonAbilities)
            if (ability.id == id)
                return ability.name;
        return nullptr;
    }

    // A Signature spell is the catalogue's Primary category (Prodigy's
    // and Arcane Dynamo's own sentence names the four).
    bool Signature(uint32 id)
    {
        return Classes::CategoryOf(id) == "Primary";
    }

    std::string_view ElementOf(unsigned school)
    {
        switch (school)
        {
            case SPELL_SCHOOL_MASK_ARCANE:
                return "arcane";
            case SPELL_SCHOOL_MASK_FROST:
                return "cold";
            case SPELL_SCHOOL_MASK_FIRE:
                return "fire";
            case SPELL_SCHOOL_MASK_NATURE:
                return "lightning";
            default:
                return "";
        }
    }

    State& StateOf(Player* player)
    {
        return states[player->GetGUID().GetRawValue()];
    }

    void After(Player* player, double seconds, std::function<void(Player*)> run)
    {
        std::lock_guard<std::recursive_mutex> guard(mutex);
        StateOf(player).timers.push_back({Now() + uint64(std::max(0.0, seconds) * 1000), std::move(run)});
    }

    Unit* Find(Player* player, ObjectGuid guid)
    {
        Unit* unit = ObjectAccessor::GetUnit(*player, guid);
        return unit && unit->IsAlive() && unit->IsInMap(player) ? unit : nullptr;
    }

    Aura* Apply(Player* player, Unit* target, char const* helper, double seconds, Unit* caster)
    {
        uint32 const id = Shells::HelperFor(helper);
        // A negative duration keeps the record's own (a shield that
        // lasts until it is spent).
        if (!player || !target || !id || seconds == 0 || !target->IsAlive())
            return nullptr;
        if (seconds > 0)
            seconds = ModifiedDurationSeconds(player, id, seconds);
        Aura* aura = (caster ? caster : player)->AddAura(id, target);
        if (aura && seconds > 0)
        {
            aura->SetMaxDuration(int32(seconds * 1000));
            aura->SetDuration(int32(seconds * 1000));
        }
        return aura;
    }

    // The marks follow the aura: no aura, no mark. A Juggernaut elite
    // is immune to freeze and snare, so AddAura refuses them; the marks used to be written anyway, and Cold Blooded,
    // Bone Chill and the chill procs then read a status the target did not have. Whether the freeze landed is the
    // return value; the reads below ask the unit as well as the mark.
    bool Freeze(Player* player, Unit* target, double seconds)
    {
        if (!Apply(player, target, "Wizard - Frozen", seconds))
            return false;
        std::lock_guard<std::recursive_mutex> guard(mutex);
        StateOf(player).marks[target->GetGUID().GetRawValue()].frozen = Now() + uint64(seconds * 1000);
        return true;
    }

    void Stun(Player* player, Unit* target, double seconds)
    {
        Apply(player, target, "Wizard - Stunned", seconds * ItemPowers::StunFactor(player));
    }

    bool Slow(Player* player, Unit* target, double pct, double seconds)
    {
        if (pct <= 0)
            return false;
        Aura* aura = Apply(player, target, "Wizard - Slowed", seconds);
        if (!aura)
            return false;
        if (AuraEffect* effect = aura->GetEffect(EFFECT_0))
            effect->ChangeAmount(-int32(std::lround(pct)));
        return true;
    }

    // Chilled is a status and a slow. The status is sourced wherever a
    // sheet says an enemy is chilled; the slow's strength is not
    // (wizard_chill_slow_pct, a placeholder), so the target is marked
    // chilled for Cold Blooded, Bone Chill and Comet whatever the slow's strength,
    // but only once the slow aura is on the target (row 8): no aura, no mark.
    void Chill(Player* player, Unit* target, double seconds, double pct)
    {
        if (!target || seconds <= 0)
            return;
        // Iceblink: "your Chill effects now slow enemy movement speed by an additional X%", on a chill that
        // has a slow at all (a placeholder of 0 stays no slow).
        double const slow = pct >= 0 ? pct : Tune("wizard_chill_slow_pct");
        if (!Slow(player, target, slow > 0 ? slow + GemPowers::ChillBonus(player) : slow, seconds))
            return;
        std::lock_guard<std::recursive_mutex> guard(mutex);
        StateOf(player).marks[target->GetGUID().GetRawValue()].chilled = Now() + uint64(seconds * 1000);
    }

    void Shield(Player* player, char const* helper, double lifePct, double seconds)
    {
        if (lifePct <= 0 || seconds == 0)
            return;
        if (Aura* aura = Apply(player, player, helper, seconds))
            if (AuraEffect* effect = aura->GetEffect(EFFECT_0))
                effect->ChangeAmount(int32(player->GetMaxHealth() * lifePct / 100 * ItemPowers::ShieldFactor(player)));
    }

    // The freeze mark alone: it was frozen when the freeze landed, whatever has happened to the aura since (a
    // kill takes the auras with it, and the kill hook asks whether the enemy died frozen).
    bool FrozenMark(Player* player, Unit* target)
    {
        std::lock_guard<std::recursive_mutex> guard(mutex);
        State& state = StateOf(player);
        auto found = state.marks.find(target->GetGUID().GetRawValue());
        return found != state.marks.end() && found->second.frozen > Now();
    }

    // Frozen now: the mark and the aura it stands for.
    bool Frozen(Player* player, Unit* target)
    {
        return FrozenMark(player, target) && target->HasAura(Shells::HelperFor("Wizard - Frozen"), player->GetGUID());
    }

    bool Chilled(Player* player, Unit* target)
    {
        std::lock_guard<std::recursive_mutex> guard(mutex);
        State& state = StateOf(player);
        auto found = state.marks.find(target->GetGUID().GetRawValue());
        return found != state.marks.end() && found->second.chilled > Now() &&
               target->HasAura(Shells::HelperFor("Wizard - Slowed"), player->GetGUID());
    }

    void Weaken(Unit* enemy, uint32 source, double pct, double seconds)
    {
        if (!enemy || pct <= 0 || seconds <= 0)
            return;
        std::lock_guard<std::recursive_mutex> guard(mutex);
        weakened[enemy->GetGUID().GetRawValue()][source] = {Now() + uint64(seconds * 1000), pct};
    }

    void Despawn(Player* player, ObjectGuid guid)
    {
        if (Creature* creature = ObjectAccessor::GetCreature(*player, guid))
            if (TempSummon* summon = creature->ToTempSummon())
                summon->UnSummon();
    }

    void ClearSummons(Player* player)
    {
        std::lock_guard<std::recursive_mutex> guard(mutex);
        State& state = StateOf(player);
        for (LiveTwister const& twister : state.twisters)
            Despawn(player, twister.carrier);
        state.twisters.clear();
        Despawn(player, state.familiar);
        state.familiar.Clear();
        for (ObjectGuid guid : state.images)
            Despawn(player, guid);
        state.images.clear();
    }

    Player* OwnerOf(Creature* me)
    {
        Unit* owner = me->GetOwner();
        if (!owner)
            if (TempSummon* summon = me->ToTempSummon())
                owner = summon->GetSummonerUnit();
        return owner ? owner->ToPlayer() : nullptr;
    }

    // Does this record carry the aura a handler is about to bind to? The
    // core's own test (_SpellScript::EffectAuraNameCheck): `aura` is
    // SPELL_AURA_ANY for any aura, and `index` EFFECT_ALL for any slot.
    bool HasAuraEffect(uint32 spellId, uint16 aura, uint8 index)
    {
        SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId);
        if (!info)
            return false;
        for (uint8 i = 0; i < MAX_SPELL_EFFECTS; ++i)
        {
            if (index != EFFECT_ALL && index != i)
                continue;
            uint16 const name = info->Effects[i].ApplyAuraName;
            if (name && (aura == SPELL_AURA_ANY || name == aura))
                return true;
        }
        return false;
    }

} // namespace DC::Combat::Wizard::Shared
