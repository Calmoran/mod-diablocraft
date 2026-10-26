/*
 * Epiphany and its five runes. The record is a DUMMY with the sheet's 15 s and 60 s cooldown and no aura, so
 * the buff is module state, as Sweeping Wind's vortex is: a 1 s tick pays the Spirit per second (the Runic Power slot
 * has no regeneration aura, contract monk-class.md), Desert Shroud is a Temporary damage reduction on the stat sheet
 * while it lasts, and the other runes act on the Monk's casts while it is up.
 */

#include "dc_monk_epiphany.h"
#include "../dc_level_heal.h"
#include "dc_monk_common.h"
#include "../dc_resources.h"
#include "../../combat/dc_item_powers.h"
#include "../../stats/dc_resource_pulse.h"
#include "../../stats/dc_stats.h"
#include "Group.h"
#include "ScriptMgr.h"
#include "SpellMgr.h"

#include <array>
#include <chrono>

namespace DC::Combat::Monk::Epiphany
{
    namespace
    {
        constexpr std::string_view Skill = "Epiphany";
        // Stock "Stun" (56): one MOD_STUN effect, Stun mechanic; the carrier of Lashing Tail Kick - Scorpion Sting's
        // stun, here Ascendance's.
        constexpr std::uint32_t Stunned = 56;
        // The power file's teleporting skills (SF_7-SF_20) that Torment casts at an enemy. Tempest Rush, Cyclone
        // Strike and Seven-Sided Strike are self-aimed here and Wave of Light is aimed at the ground, so none has an
        // enemy to dash to.
        constexpr std::array<std::string_view, 6> Dashing = {"Fists of Thunder",  "Deadly Reach",
                                                             "Crippling Wave",    "Way of the Hundred Fists",
                                                             "Lashing Tail Kick", "Exploding Palm"};

        Shells::Ability const* Row(std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && Skill == row->skill ? row : nullptr;
        }

        bool IsRune(std::uint32_t spellId, std::string_view rune)
        {
            return rune == Row(spellId)->rune;
        }

        double Tune(char const* name)
        {
            return DC::Tunables::Get("monk", name);
        }

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        std::uint64_t Millis(double seconds)
        {
            return seconds > 0 ? std::uint64_t(seconds * 1000 + 0.5) : 0u;
        }

        Point At(Unit const* unit)
        {
            return {unit->GetPositionX(), unit->GetPositionY()};
        }

        // Per Monk while Epiphany is up: the rune cast, when it ends, the Spirit paid so far and its tick's stamp (a
        // recast starts a new stamp and the old ticks find it gone), the two internal cooldowns and Ascendance's
        // stride.
        struct State
        {
            std::uint32_t spellId = 0;
            std::uint64_t until = 0;
            std::uint64_t stamp = 0;
            unsigned paid = 0;
            std::optional<std::uint64_t> dashed, onCast;
            Ascent ascent;
            Point last;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, State> states; // by Monk
        std::uint64_t stamps = 0;

        // Desert Shroud: "reducing damage taken by {damage_reduction_pct}", the stat sheet's Specific DR while it
        // lasts (the Wizard's Safe Passage's way). Keyed by the rune's spell id.
        void Shroud(Player* player, std::uint32_t spellId, bool on)
        {
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            Stats::RemoveContribution(guid, DC::Source::Temporary, Stat::SpecificReduction, spellId);
            if (on)
                Stats::AddContribution(guid, {DC::Source::Temporary, Stat::SpecificReduction, spellId,
                                              Numbers::Num(spellId, "damage_reduction_pct"), Bucket::Flat});
            Stats::Recompute(player);
        }

        void End(Player* player, std::uint32_t spellId)
        {
            if (IsRune(spellId, "Desert Shroud"))
                Shroud(player, spellId, false);
            if (std::uint32_t const reach = Shells::HelperFor("Epiphany - reach"))
                player->RemoveAurasDueToSpell(reach);
        }

        // Once a second for the buff's life: "increasing your Spirit Regeneration per Second by
        // {regen_per_second_resource}" (20; Insight's own row 45, SF_49 = 20 + SF_30).
        void Tick(Player* player, std::uint64_t stamp)
        {
            // Death ends it, as D3's buffs end.
            bool const alive = player->IsAlive() && player->IsInWorld();
            std::uint32_t spellId;
            bool last;
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto found = states.find(player->GetGUID().GetRawValue());
                if (found == states.end() || found->second.stamp != stamp)
                    return;
                State& state = found->second;
                spellId = state.spellId;
                last = !alive || ++state.paid >= Payments(Numbers::Num(spellId, "duration_seconds"));
                if (last)
                    states.erase(found);
            }
            // The second's worth as a flow over the second.
            if (alive)
                Resources::Flow(player, Resources::Spirit, Numbers::Num(spellId, "regen_per_second_resource"), 1000);
            if (last)
                End(player, spellId);
            else
                player->m_Events.AddEventAtOffset([player, stamp] { Tick(player, stamp); }, std::chrono::seconds(1));
        }

        // Ascendance: the Monk's movement, sampled every SF_43 'E: Move Distance Check Rate'.
        void Sample(Player* player, std::uint64_t stamp)
        {
            std::uint64_t const every = Millis(Tune("epiphany_move_sample_seconds"));
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto found = states.find(player->GetGUID().GetRawValue());
                if (found == states.end() || found->second.stamp != stamp || !every)
                    return;
                State& state = found->second;
                Point const here = At(player);
                state.ascent.stride.Add(std::hypot(here.x - state.last.x, here.y - state.last.y));
                state.last = here;
            }
            player->m_Events.AddEventAtOffset([player, stamp] { Sample(player, stamp); },
                                              std::chrono::milliseconds(every));
        }

        void Start(Player* player, std::uint32_t spellId)
        {
            std::uint32_t previous = 0;
            std::uint64_t stamp;
            {
                std::lock_guard<std::mutex> guard(mutex);
                State& state = states[player->GetGUID().GetRawValue()];
                previous = state.spellId;
                state = State{};
                state.spellId = spellId;
                state.until = Now() + Millis(Numbers::Num(spellId, "duration_seconds"));
                state.stamp = stamp = ++stamps;
                state.last = At(player);
            }
            if (previous)
                End(player, previous);
            // Epiphany's reach: while it is up every Monk skill reaches 15 yards farther
            // (the hidden SPELLMOD_RANGE record generate_spells.py writes, lasting Epiphany's duration), so a melee attack can
            // be aimed at the enemy it dashes to; End takes it off.
            if (std::uint32_t const reach = Shells::HelperFor("Epiphany - reach"))
                player->AddAura(reach, player);
            if (IsRune(spellId, "Desert Shroud"))
                Shroud(player, spellId, true);
            player->m_Events.AddEventAtOffset([player, stamp] { Tick(player, stamp); }, std::chrono::seconds(1));
            if (IsRune(spellId, "Ascendance"))
                Sample(player, stamp);
        }

        void Stun(Player* player, Unit* enemy, double seconds)
        {
            if (seconds <= 0 || !enemy->IsAlive())
                return;
            enemy->RemoveAurasDueToSpell(Stunned, player->GetGUID());
            if (Aura* hold = player->AddAura(Stunned, enemy))
            {
                hold->SetMaxDuration(int32(seconds * 1000));
                hold->SetDuration(int32(seconds * 1000));
            }
        }

        void Heal(Player* player, Unit* target, std::uint32_t spellId, double amount)
        {
            auto const* info = sSpellMgr->GetSpellInfo(spellId);
            if (!info || !target || !target->IsAlive() || amount <= 0)
                return;
            HealInfo heal(player, target, uint32(std::min(amount, double(UINT32_MAX))), info, info->GetSchoolMask());
            player->HealBySpell(heal);
        }

        // Inner Fire: "causing your attacks to assault enemies for {damage_pct} weapon damage as Fire". The simulator
        // (monk.js:1071-1080): a generator's cast throws a piercing fireball, any other cast up to SF_31 missiles at
        // different enemies; each hit is the 353% (SF_36).
        void InnerFire(Player* player, std::uint32_t rune, std::uint32_t castSpellId)
        {
            double const pct = Numbers::Num(rune, "damage_pct");
            if (Numbers::Get(castSpellId, "generated_resource"))
            {
                double const length = Tune("epiphany_fireball_length_yards"),
                             width = Tune("epiphany_fireball_radius_yards");
                Point const from = At(player);
                for (Unit* enemy : Combat::Enemies(player, rune, player->GetPosition(), length + width))
                    if (OnLine(from, player->GetOrientation(), At(enemy), length, width))
                        Combat::Strike(player, enemy, rune, pct);
                return;
            }
            auto enemies = Combat::Enemies(player, rune, player->GetPosition(), Tune("epiphany_missile_radius_yards"));
            std::sort(enemies.begin(), enemies.end(),
                      [player](Unit* a, Unit* b) { return player->GetExactDistSq(a) < player->GetExactDistSq(b); });
            std::size_t const count = std::size_t(Tune("epiphany_missile_count"));
            for (std::size_t i = 0; i < enemies.size() && i < count; ++i)
                Combat::Strike(player, enemies[i], rune, pct);
        }

        // Soothing Mist: "causing your abilities to heal yourself and allies within {radius_yards} yards for
        // {heal_life} Life". The Health Globe Healing Bonus share (healing_bonus_share_pct) waits on health globes,
        // which the game does not have yet (as Cyclone Strike - Soothing Breeze).
        void SoothingMist(Player* player, std::uint32_t rune)
        {
            double const radius = Numbers::Num(rune, "radius_yards"), amount = Classes::HealAtLevel(Numbers::Num(rune, "heal_life"), player->GetLevel());
            Heal(player, player, rune, amount);
            if (Group* group = player->GetGroup())
                for (GroupReference* ref = group->GetFirstMember(); ref; ref = ref->next())
                    if (Player* member = ref->GetSource();
                        member && member != player && player->IsWithinDistInMap(member, radius))
                        Heal(player, member, rune, amount);
        }

        // Rabid Strike: a Spirit spender a dash carried is cast again on a nearby enemy, free, its damage 1 + N/100
        // (Monk::Mimic under Combat::CopyFactor). The copy does not dash, so it is never copied.
        void MimicNearby(Player* player, std::uint32_t spellId, Unit* target)
        {
            double const mimic = ItemPowers::SkillSetTo(player, std::string(Skill), "mimic_damage_pct", 0);
            if (!Mimics(mimic, Numbers::Num(spellId, "cost_resource")))
                return;
            std::vector<Unit*> const near =
                Combat::Enemies(player, spellId, player->GetPosition(), Tune("rabid_strike_search_radius_yards"));
            std::vector<double> distances;
            int primary = -1;
            for (Unit* enemy : near)
            {
                if (enemy == target)
                    primary = int(distances.size());
                distances.push_back(player->GetExactDist2d(enemy));
            }
            int const pick = MimicTarget(distances, primary);
            if (pick < 0)
                return;
            double& factor = Combat::CopyFactor();
            double const before = factor;
            factor = before * MimicFactor(mimic);
            Monk::Mimic(player, spellId, near[std::size_t(pick)]);
            factor = before;
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return Row(spellId) != nullptr;
    }

    namespace
    {
        // A Monk who logs out mid-buff leaves no tick to end it (the player's events die with it): its entry goes here.
        // Stats drops the character's contributions, Desert Shroud's with them, in its own logout hook.
        class dc_monk_epiphany_logout final : public PlayerScript
        {
        public:
            dc_monk_epiphany_logout()
                : PlayerScript("dc_monk_epiphany_logout", {PLAYERHOOK_ON_LOGOUT})
            {
            }

            void OnPlayerLogout(Player* player) override
            {
                std::lock_guard<std::mutex> guard(mutex);
                states.erase(player->GetGUID().GetRawValue());
            }
        };
    } // namespace

    void RegisterScripts()
    {
        new dc_monk_epiphany_logout();
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        return Row(spellId) ? std::optional<double>(0.0) : std::nullopt;
    }

    bool Dash(Player* player, std::uint32_t spellId, Unit* target)
    {
        auto const* row = Shells::FindAbility(spellId);
        if (!player || !target || target == player || !row ||
            std::find(Dashing.begin(), Dashing.end(), std::string_view(row->skill)) == Dashing.end())
            return false;
        double const distance = player->GetExactDist2d(target);
        if (!Dashes(distance, Tune("epiphany_dash_min_yards"), Tune("epiphany_dash_max_yards")))
            return false;
        Point const to = Landing(At(player), At(target), Tune("epiphany_dash_offset_yards"));
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = states.find(player->GetGUID().GetRawValue());
            if (found == states.end() || found->second.until <= Now() ||
                !Ready(Now(), found->second.dashed, Millis(Tune("epiphany_dash_icd_seconds"))))
                return false;
            // The dash is movement too: Ascendance counts it before the attack it carries, and a dash that fills the
            // stride arms that very attack.
            State& state = found->second;
            state.ascent.Dashed(spellId, std::hypot(to.x - state.last.x, to.y - state.last.y),
                                IsRune(state.spellId, "Ascendance") ? Numbers::Num(state.spellId, "distance_yards") : 0);
            state.last = to;
        }
        float z = target->GetPositionZ();
        player->UpdateAllowedPositionZ(float(to.x), float(to.y), z);
        player->NearTeleportTo(float(to.x), float(to.y), z,
                               float(std::atan2(target->GetPositionY() - to.y, target->GetPositionX() - to.x)), true);
        MimicNearby(player, spellId, target);
        return true;
    }

    void Cast(Player* player, std::uint32_t spellId)
    {
        if (player && Is(spellId))
            Start(player, spellId);
    }

    void Casting(Player* player, std::uint32_t spellId)
    {
        if (!player || Is(spellId))
            return;
        std::uint32_t rune;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = states.find(player->GetGUID().GetRawValue());
            if (found == states.end() || found->second.until <= Now())
                return;
            State& state = found->second;
            rune = state.spellId;
            // "your next attack after moving {distance_yards} yards" (SF_46): a cast that begins with the stride full
            // stuns what its hits land on (Landed below); its dash may still fill it (Dash above).
            if (IsRune(rune, "Ascendance"))
            {
                state.ascent.Begin(spellId, Numbers::Num(rune, "distance_yards"));
                return;
            }
            // Inner Fire and Soothing Mist act on a cast at most once per SF_25 'On-Attack Internal Cooldown'.
            if (!Ready(Now(), state.onCast, Millis(Tune("epiphany_on_cast_icd_seconds"))))
                return;
        }
        if (IsRune(rune, "Inner Fire"))
            InnerFire(player, rune, spellId);
        if (IsRune(rune, "Soothing Mist"))
            SoothingMist(player, rune);
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId)
    {
        if (!player || !target || target == player)
            return;
        std::uint32_t rune;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = states.find(player->GetGUID().GetRawValue());
            if (found == states.end() || !spellId || !found->second.ascent.Hit(spellId, Now()))
                return;
            rune = found->second.spellId;
        }
        // Dovu Energy Trap: a stun that sets its own seconds stretches them by the worn items' factor.
        Stun(player, target, Numbers::Num(rune, "stun_duration_seconds") * ItemPowers::StunFactor(player));
    }
} // namespace DC::Combat::Monk::Epiphany
