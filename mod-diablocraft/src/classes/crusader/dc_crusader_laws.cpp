// The Crusader's Laws: one aura mechanism, and what each Law's passive and activation do on it.
//
// A Law is an aura: its passive is on while the skill is on the bar and is the Law in force (dc_crusader_laws.h: the
// one cast last, or every slotted one before any cast). The aura pulses; a pulse starts from the always-on hook at the
// bottom, a cast or a kill, and stops by itself when the Law leaves the bar or another one is cast. What a pulse gives
// is a timed number on the sheet of the Crusader and of each ally in its group within the skill's radius (Hold),
// renewed by the next pulse and gone a pulse after the last. A Law's own file is its flavour: the pulse and the press.

#include "dc_crusader_laws.h"
#include "dc_crusader_common.h"
#include "dc_crusader_passives.h"
#include "../../combat/dc_passives.h"
#include "../../items/dc_inventory.h"
#include "../../stats/dc_stats.h"

#include "Group.h"
#include "Spell.h"
#include "SpellInfo.h"
#include "ScriptMgr.h"

#include <map>
#include <tuple>

namespace DC::Combat::Crusader::Laws
{
    namespace
    {
        // Seconds between two pulses when the tunable laws_pulse_seconds is blank, and the
        // slack a held number carries past the next pulse so a late pulse does not drop it. Guards, not tuning numbers.
        constexpr double DefaultPulseSeconds = 1.0;
        constexpr double HoldGraceSeconds = 0.25;
        // How often the bar is looked at, in milliseconds: a Law slotted in play starts within this long.
        constexpr std::uint32_t PollMs = 1000;

        std::vector<Flavour const*> flavours;

        std::uint64_t Millis(double seconds)
        {
            return seconds > 0 ? std::uint64_t(seconds * 1000.0 + 0.5) : 0;
        }

        // ---- timed numbers on a sheet
        // --------------------------------------------------------------------------------
        struct Held
        {
            double value = 0;
            std::uint64_t until = 0;
        };
        using HoldKey = std::tuple<std::uint64_t, unsigned, std::uint64_t>; // player guid, stat, contribution id
        std::mutex holdMutex;
        std::map<HoldKey, Held> holds;

        // Puts the number on the sheet (0 takes it off) and tells the client; a cost number also moves the cost auras.
        void Sheet(Player* target, Stat stat, Bucket bucket, std::uint64_t id, double value, Element element)
        {
            std::uint64_t const guid = target->GetGUID().GetRawValue();
            if (value != 0)
                Stats::AddContribution(guid, {Source::Temporary, stat, id, value, bucket, element});
            else
                Stats::RemoveContribution(guid, Source::Temporary, stat, id);
            Stats::Recompute(target);
            if (stat == Stat::ResourceCostReduction)
                Passives::RefreshModifiers(target);
            Inventory::PushSheet(target);
        }

        // The end of a hold: the number comes off unless a pulse renewed it, and then the check moves to the new end.
        void Lapse(Player* target, HoldKey const& key, Bucket bucket, Element element)
        {
            std::uint64_t const now = Now();
            std::uint64_t again = 0;
            {
                std::lock_guard<std::mutex> guard(holdMutex);
                auto found = holds.find(key);
                if (found == holds.end())
                    return;
                if (found->second.until > now)
                    again = found->second.until - now;
                else
                    holds.erase(found);
            }
            if (again)
            {
                target->m_Events.AddEventAtOffset([target, key, bucket, element] { Lapse(target, key, bucket, element); },
                                                  std::chrono::milliseconds(again + 1));
                return;
            }
            Sheet(target, Stat(std::get<1>(key)), bucket, std::get<2>(key), 0, element);
        }

        // ---- the pulse
        // ----------------------------------------------------------------------------------------------- Per Law and
        // Crusader: `generation` tells a stopped loop's beat from the running one's (0: none runs), `beat` is when it
        // last ran, so a loop that stopped beating (a Crusader who logged out) is started again.
        struct Loop
        {
            std::uint64_t generation = 0;
            std::uint64_t beat = 0;
        };
        std::mutex loopMutex;
        std::map<std::pair<Flavour const*, std::uint64_t>, Loop> loops;
        std::uint64_t generations = 0;

        // One beat: while the Law is slotted and is the one in force, one pulse, and the next one a period later;
        // otherwise the loop stops (what it handed out lapses on its own).
        void Beat(Flavour const& flavour, Player* owner, std::uint64_t generation)
        {
            std::uint64_t const guid = owner->GetGUID().GetRawValue();
            std::uint32_t const slotted = Slotted(owner, flavour.skill);
            std::uint32_t const base = BaseId(flavour.skill);
            bool const on = slotted && On(guid, base);
            {
                std::lock_guard<std::mutex> guard(loopMutex);
                Loop& loop = loops[{&flavour, guid}];
                if (loop.generation != generation)
                    return;
                if (on)
                    loop.beat = Now();
                else
                    loop.generation = 0;
            }
            if (!on)
                return;
            flavour.pulse(owner, slotted, Boosted(guid, base, Now()));
            owner->m_Events.AddEventAtOffset([&flavour, owner, generation] { Beat(flavour, owner, generation); },
                                             std::chrono::milliseconds(Millis(PulseSeconds())));
        }

        // Starts the Law's pulse when the skill is on the bar, is the one in force and no loop runs; a loop whose last
        // beat is three periods old has stopped beating and is replaced.
        void StartPulse(Flavour const& flavour, Player* player)
        {
            if (!player)
                return;
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            {
                std::lock_guard<std::mutex> guard(loopMutex);
                Loop const& loop = loops[{&flavour, guid}];
                if (loop.generation && Now() < loop.beat + 3 * Millis(PulseSeconds()))
                    return;
            }
            if (!On(guid, BaseId(flavour.skill)) || !Slotted(player, flavour.skill))
                return;
            std::uint64_t generation;
            {
                std::lock_guard<std::mutex> guard(loopMutex);
                Loop& loop = loops[{&flavour, guid}];
                loop.generation = generation = ++generations;
                loop.beat = Now();
            }
            Beat(flavour, player, generation);
        }

        // ---- the always-on hook
        // --------------------------------------------------------------------------------------
        std::mutex waitedMutex;
        // Per player: the milliseconds since the bar was last looked at; absent at login, which looks at once.
        std::unordered_map<std::uint64_t, std::uint32_t> waited;

        class Always final : public PlayerScript
        {
        public:
            Always()
                : PlayerScript("dc_crusader_laws_always",
                               {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_CREATURE_KILL, PLAYERHOOK_ON_SPELL_CAST})
            {
            }

            void OnPlayerUpdate(Player* player, std::uint32_t diff) override
            {
                if (!player || !player->IsInWorld())
                    return;
                {
                    std::lock_guard<std::mutex> guard(waitedMutex);
                    auto const found = waited.find(player->GetGUID().GetRawValue());
                    if (found == waited.end())
                        waited[player->GetGUID().GetRawValue()] = 0;
                    else if ((found->second += diff) < PollMs)
                        return;
                    else
                        found->second = 0;
                }
                if (Classes::ClassIdOf(player) != Resources::Find("Crusader", "wrath")->classId)
                    return;
                for (Flavour const* flavour : flavours)
                    StartPulse(*flavour, player);
            }

            void OnPlayerLogout(Player* player) override
            {
                std::uint64_t const guid = player->GetGUID().GetRawValue();
                {
                    std::lock_guard<std::mutex> guard(waitedMutex);
                    waited.erase(guid);
                }
                Forget(guid);
            }

            // A Wrath skill was cast: the Laws that pay for Wrath spent are told how many points it costs, reductions
            // included (the core takes that number between this hook and the hits).
            void OnPlayerSpellCast(Player* player, Spell* spell, bool) override
            {
                if (!player || !spell || spell->GetPowerCost() <= 0 || !Shells::FindAbility(spell->GetSpellInfo()->Id))
                    return;
                auto const& wrath = *Resources::Find("Crusader", "wrath");
                if (Classes::ClassIdOf(player) != wrath.classId || spell->GetSpellInfo()->PowerType != POWER_ENERGY)
                    return;
                double const points = Resources::ToPoints(wrath, spell->GetPowerCost());
                for (Flavour const* flavour : flavours)
                    if (flavour->spent)
                        flavour->spent(player, points);
            }

            void OnPlayerCreatureKill(Player* killer, Creature*) override
            {
                if (!killer)
                    return;
                for (Flavour const* flavour : flavours)
                    if (flavour->killed)
                        flavour->killed(killer);
            }
        };
    } // namespace

    std::uint64_t Now()
    {
        return std::uint64_t(GameTime::GetGameTimeMS().count());
    }

    double ActiveSeconds(Player* player, double seconds)
    {
        return Passive::LongArm(seconds, Passive::LongArmSeconds(player));
    }

    double PulseSeconds()
    {
        double const set = DC::Tunables::Get("crusader", "laws_pulse_seconds");
        return set > 0 ? set : DefaultPulseSeconds;
    }

    std::uint64_t PulseHoldMs()
    {
        return HoldMs(PulseSeconds(), HoldGraceSeconds);
    }

    std::uint32_t BaseId(std::string_view skill)
    {
        return Crusader::BaseId(skill);
    }

    std::uint32_t Slotted(Player* player, std::string_view skill)
    {
        return Crusader::Slotted(player, skill);
    }

    std::vector<Player*> InAura(Player* owner, std::string_view skill)
    {
        std::vector<Player*> holders{owner};
        Group* group = owner->GetGroup();
        auto const* row = Shells::FindAbility(BaseId(skill));
        if (!group || !row)
            return holders;
        for (GroupReference* ref = group->GetFirstMember(); ref; ref = ref->next())
            if (Player* member = ref->GetSource())
                if (member != owner && member->IsAlive() && member->IsInWorld() &&
                    member->GetMap() == owner->GetMap() && owner->GetExactDist(member) <= row->radius)
                    holders.push_back(member);
        return holders;
    }

    void Hold(Player* target, Stat stat, Bucket bucket, std::uint64_t id, double value, std::uint64_t untilMs,
              Element element)
    {
        if (!target)
            return;
        HoldKey const key{target->GetGUID().GetRawValue(), unsigned(stat), id};
        std::uint64_t const now = Now();
        bool fresh;
        {
            std::lock_guard<std::mutex> guard(holdMutex);
            Held& held = holds[key];
            fresh = held.until <= now || held.value != value;
            held.value = value;
            held.until = untilMs;
            if (value == 0 || untilMs <= now)
                holds.erase(key);
        }
        if (!fresh && value != 0 && untilMs > now)
            return;
        Sheet(target, stat, bucket, id, untilMs > now ? value : 0, element);
        if (value != 0 && untilMs > now)
            target->m_Events.AddEventAtOffset([target, key, bucket, element] { Lapse(target, key, bucket, element); },
                                              std::chrono::milliseconds(untilMs - now + 1));
    }

    void Add(Flavour const& flavour)
    {
        flavours.push_back(&flavour);
    }

    void Press(Flavour const& flavour, Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        auto const* row = Shells::FindAbility(spellId);
        if (!player || !row || flavour.skill != row->skill)
            return;
        std::uint32_t const base = BaseId(flavour.skill);
        Laws::Cast(player->GetGUID().GetRawValue(), base, Now(), Millis(ActiveSeconds(player, Numbers::Num(base, flavour.window))));
        flavour.activate(player, spellId, targets);
        StartPulse(flavour, player);
    }

    void RegisterScripts()
    {
        new Always();
    }
} // namespace DC::Combat::Crusader::Laws
