/*
 * Companion and its five runes. The pet is a minion of the shared piece (combat/dc_minions.h): permanent, raised again
 * a few seconds after it is lost, Life a share of the Demon Hunter's, striking for the form's weapon damage; the form
 * on the bar is the creature (demon_hunter_summons.csv). While it stands each form gives what its passive says: the
 * spider's attacks slow and reach a cone, the wolf's reach a cone, the boar gives the party Life regeneration and
 * resistance, the bat gives Hatred a second, the ferrets (a pair) give gold find and movement speed. The press is the
 * active: the raven's next attack, the spider's web, the boar's charge and taunt, the wolf's howl, the bat's Hatred;
 * the ferret's pick-up of health globes and gold has nothing to pick up (gold is paid to the account, health globes are
 * not built).
 */

#include "dc_demon_hunter_companion.h"
#include "dc_demon_hunter_companion_math.h"
#include "dc_demon_hunter_common.h"
#include "dc_demon_hunter_effects.h"
#include "dc_demon_hunter_hatred.h"
#include "../dc_classes.h"
#include "../dc_resources.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_damage_boost.h"
#include "../../combat/dc_healing_table.h"
#include "../../combat/dc_minions.h"
#include "../../combat/dc_spell_numbers.h"
#include "../../combat/dc_spell_shells.h"
#include "Creature.h"
#include "Group.h"
#include "GroupReference.h"
#include "MotionMaster.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "SpellAuras.h"

#include <algorithm>
#include <chrono>
#include <mutex>
#include <unordered_map>

namespace DC::Combat::DemonHunter::Companion
{
    namespace
    {
        constexpr std::string_view Skill = "Companion";
        // How often the bar is looked at for the pet and the passive gifts of its form (ms; the `companion_poll_seconds` tunable).
        std::uint32_t PollMs()
        {
            return Millis(Tune("companion_poll_seconds"));
        }
        // A passive gift is given for this many polls, so that a missed look does not drop it (`companion_gift_hold_polls`).
        double HoldPolls()
        {
            return Tune("companion_gift_hold_polls");
        }
        // Stock "Taunt" (355): one SPELL_AURA_MOD_TAUNT effect, which makes the enemy attack its caster; here the boar
        // casts it.
        constexpr std::uint32_t TauntAura = 355;

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::Raven;
        }

        // The skill or rune of the Companion on the Demon Hunter's bar; 0 when none is.
        std::uint32_t Slotted(Player* player)
        {
            for (Classes::Slot const& slot : Classes::Bar(player))
                if (RowOf(slot.spellId, Skill))
                    return slot.spellId;
            return 0;
        }

        bool IsDemonHunter(Player const* player)
        {
            return player && Classes::ClassIdOf(player) == Resources::Hatred.classId;
        }

        double Num(std::uint32_t record, char const* token, char const* qualifier = "")
        {
            return Numbers::Num(record, token, qualifier);
        }

        template<class Act>
        void After(Player* player, double seconds, Act act)
        {
            if (seconds <= 0)
                act();
            else
                player->m_Events.AddEventAtOffset(std::move(act), std::chrono::milliseconds(Millis(seconds)));
        }

        Creature* Pet(Player* player)
        {
            auto const pets = Minions::Standing(player, "companion");
            return pets.empty() ? nullptr : pets.front();
        }

        // The raven's next attack: set by the press, spent by the first blow after it.
        std::mutex mutex;
        std::unordered_map<std::uint64_t, bool> ravenArmed;
        std::unordered_map<std::uint64_t, std::uint32_t> waited;
        // The record the pet was last held as: a rune changed on the bar sends it away, and the keeper raises the new
        // form.
        std::unordered_map<std::uint64_t, std::uint32_t> heldAs;

        // "Spider: The spider's attacks Slow enemies by {slow_pct:passive} for {slow_duration_seconds:passive}
        // seconds."
        void SlowOne(Player* player, Unit* enemy, std::uint32_t record)
        {
            Slow(player, enemy, Num(record, "slow_pct", "passive"), Num(record, "slow_duration_seconds", "passive"));
        }

        // The spider and the wolf "attack enemies in front of him": the blow reaches every other enemy in the cone
        // round the one it struck.
        void Cone(Player* player, Unit* struck, std::uint32_t record, Rune rune)
        {
            Creature* pet = Pet(player);
            if (!pet)
                return;
            double const yards = Tune("companion_cone_radius_yards"), degrees = Tune("companion_cone_degrees");
            double const centre = pet->GetAngle(struck);
            for (Unit* other : Combat::Enemies(player, record, pet->GetPosition(), yards))
                if (other != struck && other->IsAlive() &&
                    InCone(pet->GetAngle(other), centre, pet->GetExactDist(other), yards, degrees) &&
                    Combat::Strike(player, other, record, Num(record, "damage_pct")) && rune == Rune::Spider)
                    SlowOne(player, other, record);
        }

        // After each blow of the pet.
        void Struck(Player* player, Unit* enemy, std::uint32_t record, Rune rune)
        {
            if (rune == Rune::Raven)
            {
                bool armed = false;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    bool& flag = ravenArmed[player->GetGUID().GetRawValue()];
                    armed = flag;
                    flag = false;
                }
                if (armed)
                    Minions::Boost(player, "companion", 0.0, 0);
            }
            if (rune == Rune::Spider)
                SlowOne(player, enemy, record);
            if (HasCone(rune))
                Cone(player, enemy, record, rune);
        }

        Minions::Kind Make(Player* owner)
        {
            std::uint32_t const slotted = Slotted(owner);
            std::uint32_t const record = slotted ? slotted : BaseId(Skill);
            Rune const rune = RuneAt(record);
            Minions::Kind kind;
            kind.group = "companion";
            kind.entry = EntryOf(rune);
            kind.record = record;
            kind.damagePct = Num(record, "damage_pct");
            kind.cap = Pets(rune);
            kind.lifeToCopyPct = LifePct(rune, Tune("companion_life_pct"), Tune("companion_boar_life_pct"));
            kind.struck = [record, rune](Player* player, Unit* enemy) { Struck(player, enemy, record, rune); };
            return kind;
        }

        // The members of the Demon Hunter's party that are alive, on its map and within `yards` of it, the Demon Hunter
        // first.
        std::vector<Player*> Party(Player* owner, double yards)
        {
            std::vector<Player*> party{owner};
            if (Group* group = owner->GetGroup())
                for (GroupReference* ref = group->GetFirstMember(); ref; ref = ref->next())
                    if (Player* member = ref->GetSource(); member && member != owner && member->IsAlive() &&
                                                           member->IsInWorld() && member->GetMap() == owner->GetMap() &&
                                                           InPartyRange(member->GetExactDist(owner), yards))
                        party.push_back(member);
            return party;
        }

        // What the form gives while the pet stands, once a poll.
        void Gifts(Player* player, std::uint32_t record, Rune rune)
        {
            double const hold = HoldPolls() * PollMs() / 1000.0;
            switch (rune)
            {
                case Rune::Boar:
                {
                    // "The boar increases your and your party's Life regeneration by {heal_per_second_life} and
                    // resistance to all elements by {resistance_pct}": the regeneration follows D3's Healing table at
                    // each member's level.
                    double const seconds = Tune("companion_boar_party_seconds");
                    for (Player* member : Party(player, Tune("companion_boar_party_radius_yards")))
                    {
                        Buffs::Stack(
                            member, record, Stat::LifeRegen, Bucket::Flat,
                            RegenPerSecond(Healing::At(member->GetLevel()), Tune("companion_boar_regen_healing_share")),
                            1, seconds);
                        Buffs::Stack(member, record, Stat::AllResistance, Bucket::Percent,
                                     Num(record, "resistance_pct"), 1, seconds);
                    }
                    break;
                }
                case Rune::Bat:
                    // "The bat grants you {regen_per_second_resource} Hatred per second."
                    Generate(player, Classes::ClassIdOf(player), record,
                             Num(record, "regen_per_second_resource") * PollMs() / 1000.0);
                    break;
                case Rune::Ferret:
                    // "increase gold found on monsters by {gold_find_pct}, and increase your movement speed by
                    // {movement_speed_pct}".
                    Buffs::Stack(player, record, Stat::GoldFind, Bucket::Flat, Num(record, "gold_find_pct"), 1, hold);
                    Buffs::Stack(player, record, Stat::MovementSpeed, Bucket::Flat, Num(record, "movement_speed_pct"),
                                 1, hold);
                    break;
                default:
                    break;
            }
        }

        class Keeper final : public PlayerScript
        {
        public:
            Keeper()
                : PlayerScript("dc_demon_hunter_companion", {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT})
            {
            }

            void OnPlayerUpdate(Player* player, uint32 diff) override
            {
                if (!IsDemonHunter(player) || !player->IsInWorld())
                    return;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    auto const found = waited.find(player->GetGUID().GetRawValue());
                    if (found == waited.end())
                        waited[player->GetGUID().GetRawValue()] = 0;
                    else if ((found->second += diff) < PollMs())
                        return;
                    else
                        found->second = 0;
                }
                std::uint32_t const record = Slotted(player);
                if (!record)
                {
                    {
                        std::lock_guard<std::mutex> guard(mutex);
                        heldAs.erase(player->GetGUID().GetRawValue());
                    }
                    Minions::Dismiss(player, "companion");
                    return;
                }
                bool changed;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    std::uint32_t& held = heldAs[player->GetGUID().GetRawValue()];
                    changed = held && held != record;
                    held = record;
                }
                if (changed)
                    Minions::Dismiss(player, "companion");
                Rune const rune = RuneAt(record);
                // "Passive: Summons a companion": one, or the ferret's pair, and a new one after the power's respawn
                // seconds.
                Minions::Keep(player, "companion", Pets(rune), 0, Millis(Tune("companion_respawn_seconds")));
                if (player->IsAlive() && Minions::Alive(player, "companion") > 0)
                    Gifts(player, record, rune);
            }

            void OnPlayerLogout(Player* player) override
            {
                std::lock_guard<std::mutex> guard(mutex);
                waited.erase(player->GetGUID().GetRawValue());
                heldAs.erase(player->GetGUID().GetRawValue());
                ravenArmed.erase(player->GetGUID().GetRawValue());
            }
        };

        // "Active: Your spider throws webs at all enemies within {radius_yards} yards of you and him, Slowing them by
        // {slow_pct:active} for {slow_duration_seconds:active} seconds."
        void Web(Player* player, std::uint32_t record)
        {
            double const radius = Num(record, "radius_yards");
            std::vector<Unit*> reached = Combat::Enemies(player, record, player->GetPosition(), radius);
            if (Creature* pet = Pet(player))
                for (Unit* enemy : Combat::Enemies(player, record, pet->GetPosition(), radius))
                    if (std::find(reached.begin(), reached.end(), enemy) == reached.end())
                        reached.push_back(enemy);
            for (Unit* enemy : reached)
                Slow(player, enemy, Num(record, "slow_pct", "active"), Num(record, "slow_duration_seconds", "active"));
        }

        // "Active: Your boar charges to you, then taunts all enemies within {radius_yards} yards for {duration_seconds}
        // seconds."
        void Taunt(Player* player, ObjectGuid boarGuid, std::uint32_t record)
        {
            Creature* boar = ObjectAccessor::GetCreature(*player, boarGuid);
            if (!boar || !boar->IsAlive() || !player->IsAlive())
                return;
            double const seconds = Num(record, "duration_seconds");
            for (Unit* enemy : Combat::Enemies(player, record, player->GetPosition(), Num(record, "radius_yards")))
            {
                enemy->EngageWithTarget(boar);
                enemy->GetThreatMgr().AddThreat(boar, 1.0f);
                if (Aura* taunt = boar->AddAura(TauntAura, enemy))
                {
                    taunt->SetMaxDuration(int32(Millis(seconds)));
                    taunt->SetDuration(int32(Millis(seconds)));
                }
            }
        }

        void Intervene(Player* player, std::uint32_t record)
        {
            Creature* boar = Pet(player);
            if (!boar)
                return;
            Position const to = player->GetPosition();
            double const travel = boar->GetExactDist(&to) / SPEED_CHARGE;
            boar->GetMotionMaster()->MoveCharge(to.GetPositionX(), to.GetPositionY(), to.GetPositionZ());
            After(player, travel, [player, guid = boar->GetGUID(), record] { Taunt(player, guid, record); });
        }

        // "Active: Your wolf howls, granting you and your allies within {radius_yards} yards {damage_bonus_pct}
        // increased damage for {duration_seconds} seconds."
        void Howl(Player* player, std::uint32_t record)
        {
            for (Player* member : Party(player, Num(record, "radius_yards")))
                DamageBoost::Hold(member, BaseId(Skill), Num(record, "damage_bonus_pct"),
                                  Num(record, "duration_seconds"));
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        return Is(spellId) ? std::optional<double>(0.0) : std::nullopt;
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const&)
    {
        if (!player || !Is(spellId))
            return;
        std::uint32_t const base = BaseId(Skill);
        switch (RuneAt(spellId))
        {
            case Rune::Raven:
                // "Active: Your raven deals an additional {damage_bonus_pct} damage on its next attack": until the next
                // blow, or the skill's cooldown, whichever comes first.
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    ravenArmed[player->GetGUID().GetRawValue()] = true;
                }
                Minions::Boost(player, "companion", Num(base, "damage_bonus_pct"),
                               Millis(Num(base, "cooldown_seconds")));
                break;
            case Rune::Spider:
                Web(player, spellId);
                break;
            case Rune::Boar:
                Intervene(player, spellId);
                break;
            case Rune::Wolf:
                Howl(player, spellId);
                break;
            case Rune::Bat:
                // "Active: Instantly gain {gain_resource} Hatred."
                Generate(player, Classes::ClassIdOf(player), spellId, Num(spellId, "gain_resource"));
                break;
            case Rune::Ferret:
                // "Active: Instantly pick up all health globes and gold within {radius_yards} yards": gold is paid to
                // the account at the kill and the health globes are not built, so nothing lies on the ground to be
                // picked up.
                break;
        }
    }

    void RegisterScripts()
    {
        Minions::Define("companion", Make);
        new Keeper();
    }
} // namespace DC::Combat::DemonHunter::Companion
