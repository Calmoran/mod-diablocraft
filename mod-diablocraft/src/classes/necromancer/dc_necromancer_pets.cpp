/*
 * The Necromancer's minions on the shared piece (combat/dc_minions.h): what each kind is made of, from the skill's own
 * sheet rows and the tunables, the two keepers that hold a standing minion while its skill is on the bar, and the calls
 * the skills make. The creatures are necromancer_summons.csv (entries 900150-900154).
 */

#include "dc_necromancer_pets.h"
#include "dc_necromancer_command_golem_math.h"
#include "dc_necromancer_command_skeletons_math.h"
#include "dc_necromancer_common.h"
#include "dc_necromancer_frailty.h"
#include "dc_necromancer_passives.h"
#include "dc_necromancer_revive_math.h"
#include "dc_necromancer_skeletal_mage_math.h"
#include "../dc_classes.h"
#include "../dc_resources.h"
#include "../../combat/dc_corpses.h"
#include "../../combat/dc_minions.h"
#include "../../combat/dc_spell_numbers.h"
#include "../../combat/dc_spell_shells.h"
#include "../../common/dc_tunables.h"
#include "../../monsters/dc_family_ai.h"

#include "DatabaseEnv.h"
#include "Field.h"
#include "Log.h"
#include "Player.h"
#include "QueryResult.h"
#include "ScriptMgr.h"

#include <cmath>
#include <mutex>
#include <numbers>
#include <string_view>
#include <unordered_map>

namespace DC::Combat::Necromancer::Pets
{
    namespace
    {
        constexpr std::string_view MageSkill = "Skeletal Mage", ReviveSkill = "Revive",
                                   SkeletonSkill = "Command Skeletons", GolemSkill = "Command Golem",
                                   SimulacrumSkill = "Simulacrum";
        // The creatures of necromancer_summons.csv.
        constexpr std::uint32_t MageEntry = 900150, SkeletonEntry = 900151, GolemEntry = 900152, RevivedEntry = 900153,
                                SimulacrumEntry = 900154;

        double Tune(char const* name)
        {
            return DC::Tunables::Get("necromancer", name);
        }

        std::uint32_t BaseId(std::string_view skill)
        {
            for (auto const& row : Shells::Abilities)
                if (skill == row.skill && !*row.rune)
                    return row.id;
            return 0;
        }

        // The skill or rune of `skill` on the Necromancer's bar; 0 when none is.
        std::uint32_t Slotted(Player* player, std::string_view skill)
        {
            for (Classes::Slot const& slot : Classes::Bar(player))
                if (auto const* row = Shells::FindAbility(slot.spellId); row && skill == row->skill)
                    return slot.spellId;
            return 0;
        }

        // The rune on the bar, else the skill's own record (the numbers a rune inherits).
        std::uint32_t RecordOf(Player* player, std::string_view skill)
        {
            std::uint32_t const slotted = Slotted(player, skill);
            return slotted ? slotted : BaseId(skill);
        }

        bool IsNecromancer(Player const* player)
        {
            return player && Classes::ClassIdOf(player) == Resources::Find("Necromancer", "essence")->classId;
        }

        std::uint32_t Millis(double seconds)
        {
            return seconds > 0 ? std::uint32_t(std::llround(seconds * 1000.0)) : 0;
        }

        // The cast that raises a mage: the record of the skill or rune cast, and Singularity's bonus. Set by RaiseMage,
        // which asks for the kind at once; a mage raised without a cast (the GM command) reads the bar.
        struct MageCast
        {
            std::uint32_t record = 0;
            double bonusPct = 0;
        } mageCast;

        // Skeletal Mage: "Raise a skeleton ... dealing {damage_pct} weapon damage as Physical over two attacks. Lasts
        // {duration_seconds} seconds"; the most mages standing is the power's pet cap. The runes: Gift of Death leaves a
        // corpse where the mage dies or expires, Life Support adds its seconds, Contamination strikes the enemies around
        // each second instead of attacking, Skeleton Archer shoots and speeds the Necromancer up with each blow.
        Minions::Kind Mage(Player* owner)
        {
            std::uint32_t const record = mageCast.record ? mageCast.record : RecordOf(owner, MageSkill);
            auto const* row = Shells::FindAbility(record);
            SkeletalMage::Rune const rune = row ? SkeletalMage::RuneOf(row->rune) : SkeletalMage::Rune::None;
            bool const lifeSupport = rune == SkeletalMage::Rune::LifeSupport;
            Minions::Kind kind;
            kind.group = "mage";
            kind.bonusAgainst = Frailty::MinionBonus;
            kind.entry = MageEntry;
            kind.record = record;
            kind.damagePct = Numbers::Num(record, "damage_pct") * (1.0 + mageCast.bonusPct / 100.0);
            // "dealing {damage_pct} weapon damage as Physical over two attacks": the tooltip's number of attacks in one cast.
            kind.hitsPerSwing = unsigned(Tune("minion_mage_attacks"));
            kind.lifeMs = Millis(SkeletalMage::LifeSeconds(Numbers::Num(BaseId(MageSkill), "duration_seconds"),
                                                           lifeSupport ? Numbers::Num(record, "duration_seconds") : 0.0,
                                                           lifeSupport) *
                                 Passive::DurationFactor(owner, MageSkill));
            kind.cap = unsigned(Tune("minion_mage_cap"));
            if (rune == SkeletalMage::Rune::GiftOfDeath)
                kind.ended = [](Player* player, Position const& at) { Corpses::LeaveMade(player, at, 0); };
            if (rune == SkeletalMage::Rune::Contamination)
            {
                // "channels an aura of decay for {damage_pct} weapon damage as Poison for its duration": a mage that
                // does not attack.
                kind.auraPct = kind.damagePct;
                kind.damagePct = 0;
                kind.auraRadius = Tune("contamination_radius_yards");
            }
            if (rune == SkeletalMage::Rune::SkeletonArcher)
            {
                // "Skeleton Archers increase your attack speed by {attack_speed_pct} for {duration_seconds} seconds each
                // time they deal damage. Max {max_stacks_count} stacks."
                kind.rangeYards = Tune("skeleton_archer_range_yards");
                kind.struck = [record](Player* player, Unit*)
                {
                    Buffs::Stack(player, record, Stat::AttackSpeed, Bucket::Flat, Numbers::Num(record, "attack_speed_pct"),
                                 unsigned(Numbers::Num(record, "max_stacks_count")), Numbers::Num(record, "duration_seconds"));
                };
            }
            return kind;
        }

        // Command Skeletons: "Skeletal minions deal {damage_pct} weapon damage as Physical per attack", ordered at a
        // target they deal {damage_bonus_pct} more to it; each dies after the power's number of hits; at most
        // {max_count} stand. The runes: Dark Mending heals the Necromancer for each blow at the commanded target, Frenzy
        // speeds the commanded up, Freezing Grasp turns the blows to Cold (its record's school); Kill Command's own number is
        // the explosion's, so its skeletons strike as the skill.
        Minions::Kind Skeleton(Player* owner)
        {
            std::uint32_t const slotted = RecordOf(owner, SkeletonSkill);
            auto const* row = Shells::FindAbility(slotted);
            auto const rune = row ? CommandSkeletons::RuneOf(row->rune) : CommandSkeletons::Rune::None;
            std::uint32_t const record = CommandSkeletons::BlowsUseSkillRecord(rune) ? BaseId(SkeletonSkill) : slotted;
            Minions::Kind kind;
            kind.group = "skeleton";
            kind.bonusAgainst = Frailty::MinionBonus;
            kind.entry = SkeletonEntry;
            kind.record = record;
            kind.damagePct = Numbers::Num(record, "damage_pct");
            kind.commandBonusPct = Numbers::Num(record, "damage_bonus_pct");
            kind.hitsToDie = unsigned(Tune("minion_skeleton_hits"));
            kind.cap = unsigned(Numbers::Num(record, "max_count"));
            if (rune == CommandSkeletons::Rune::Frenzy)
                kind.commandSpeedPct = Numbers::Num(slotted, "attack_speed_pct");
            if (rune == CommandSkeletons::Rune::DarkMending)
                kind.struck = [slotted](Player* player, Unit* enemy)
                {
                    Heal(player, slotted,
                         CommandSkeletons::HealPerBlow(Minions::IsOrdered(player, "skeleton", enemy), player->GetMaxHealth(),
                                                       Numbers::Num(slotted, "heal_pct")));
                };
            return kind;
        }

        // Command Golem: "Flesh Golem deals {damage_pct} weapon damage as Physical per attack"; one stands. Decay Golem's and
        // Ice Golem's records turn its blows to Poison and Cold; every other rune's {damage_pct} is its active's, so the
        // Golem strikes as the skill.
        Minions::Kind Golem(Player* owner)
        {
            std::uint32_t const slotted = RecordOf(owner, GolemSkill);
            auto const* row = Shells::FindAbility(slotted);
            auto const rune = row ? CommandGolem::RuneOf(row->rune) : CommandGolem::Rune::None;
            std::uint32_t const record = CommandGolem::BlowsUseRuneRecord(rune) ? slotted : BaseId(GolemSkill);
            Minions::Kind kind;
            kind.group = "golem";
            kind.bonusAgainst = Frailty::MinionBonus;
            kind.entry = GolemEntry;
            kind.record = record;
            kind.damagePct = Numbers::Num(record, "damage_pct");
            kind.cap = 1;
            return kind;
        }

        // Revive: "reviving up to {target_count} corpses ... for {duration_seconds} seconds"; the sheets state no
        // damage for a revived minion (revive_damage_pct is a placeholder), so until it has a number it follows and
        // strikes nothing.
        // The cast that revives a corpse: the record cast and the creature the corpse was. Set by Revive, which asks for the
        // kind at once; a minion raised without a cast (the GM command) reads the bar.
        struct ReviveCast
        {
            std::uint32_t record = 0;
            std::uint32_t corpseEntry = 0;
        } reviveCast;

        // The attack scalar of a revivable roster monster (dc_revive_scalar, from necromancer_revive_attacks.csv): the
        // monster keeps its own attack, scaled by D3's Damage Scalar of it. A monster with no row has the base scalar, 1.
        double ReviveScalar(std::uint32_t entry)
        {
            static auto const scalars = []
            {
                std::unordered_map<std::uint32_t, double> loaded;
                QueryResult rows = WorldDatabase.Query("SELECT entry, scalar FROM dc_revive_scalar");
                if (!rows)
                {
                    LOG_ERROR("module.dc.combat", "dc_revive_scalar is missing or empty; apply necromancer_revive_0001_scalars.sql");
                    return loaded;
                }
                do
                {
                    Field* f = rows->Fetch();
                    loaded[f[0].Get<std::uint32_t>()] = f[1].Get<double>();
                } while (rows->NextRow());
                return loaded;
            }();
            auto const found = scalars.find(Rifts::Family::BaseEntry(entry));
            return found == scalars.end() ? 1.0 : found->second;
        }

        // The runes: Oblation and Recklessness raise the damage by their percent, Recklessness's seconds are its own,
        // Purgatory leaves a corpse where the time is up.
        Minions::Kind Revived(Player* owner)
        {
            std::uint32_t const record = reviveCast.record ? reviveCast.record : RecordOf(owner, ReviveSkill);
            Minions::Kind kind;
            kind.group = "revived";
            kind.bonusAgainst = Frailty::MinionBonus;
            kind.entry = RevivedEntry;
            kind.record = record;
            kind.damagePct = Tune("revive_damage_pct") * ReviveScalar(reviveCast.corpseEntry) *
                             (1.0 + Numbers::Num(record, "damage_bonus_pct") / 100.0);
            kind.lifeMs = Millis(Numbers::Num(record, "duration_seconds") * Passive::DurationFactor(owner, ReviveSkill));
            kind.cap = unsigned(Tune("minion_revive_cap"));
            kind.lifeToCopyPct = Tune("revive_life_pct");
            if (auto const* row = Shells::FindAbility(record);
                row && CorpseRevive::RuneOf(row->rune) == CorpseRevive::Rune::Purgatory)
                kind.timedOut = [entry = reviveCast.corpseEntry](Player* player, Position const& at)
                { Corpses::LeaveMade(player, at, entry); };
            return kind;
        }

        // Simulacrum: "Create a Simulacrum ... for {duration_seconds} seconds": one copy of the Necromancer with the
        // power's share of its Life.
        Minions::Kind CopyOf(Player* owner, char const* group)
        {
            std::uint32_t const record = RecordOf(owner, SimulacrumSkill);
            Minions::Kind kind;
            kind.group = group;
            kind.bonusAgainst = Frailty::MinionBonus;
            kind.entry = SimulacrumEntry;
            kind.record = record;
            kind.lifeMs = Millis(Numbers::Num(record, "duration_seconds"));
            kind.cap = unsigned(Tune("simulacrum_mirrors"));
            kind.lifeToCopyPct = Tune("simulacrum_life_pct");
            return kind;
        }

        Minions::Kind Copy(Player* owner)
        {
            return CopyOf(owner, "simulacrum");
        }

        Minions::Kind CopyOfBone(Player* owner)
        {
            return CopyOf(owner, "simulacrum_bone");
        }

        // The Necromancer's two standing minions are held while their skill is on the bar, a look a second.
        std::mutex mutex;
        std::unordered_map<std::uint64_t, std::uint32_t> waited;
        // The record the owner's skeletons were last held as: a rune changed on the bar sends them away, and the keeper
        // raises new ones of the new rune (a skeleton carries its rune's numbers from the moment it rises).
        std::unordered_map<std::uint64_t, std::uint32_t> heldAs;
        std::unordered_map<std::uint64_t, std::uint32_t> heldGolemAs;

        class Keeper final : public PlayerScript
        {
        public:
            Keeper()
                : PlayerScript("dc_necromancer_pets", {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT})
            {
            }

            void OnPlayerUpdate(Player* player, uint32 diff) override
            {
                if (!IsNecromancer(player) || !player->IsInWorld())
                    return;
                // How often the bar is looked at for the two standing minions: how soon one slotted in play is raised.
                std::uint32_t const pollMs = Millis(Tune("minion_keeper_poll_seconds"));
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    auto const found = waited.find(player->GetGUID().GetRawValue());
                    if (found == waited.end())
                        waited[player->GetGUID().GetRawValue()] = 0;
                    else if ((found->second += diff) < pollMs)
                        return;
                    else
                        found->second = 0;
                }
                // "Passive: Raise skeletons from the ground every {interval_seconds} seconds to a max of {max_count}".
                if (std::uint32_t const record = Slotted(player, SkeletonSkill))
                {
                    bool changed;
                    {
                        std::lock_guard<std::mutex> guard(mutex);
                        std::uint32_t& held = heldAs[player->GetGUID().GetRawValue()];
                        changed = held && held != record;
                        held = record;
                    }
                    if (changed)
                        Minions::Dismiss(player, "skeleton");
                    Minions::Keep(player, "command_skeleton", unsigned(Numbers::Num(record, "max_count")),
                                  Millis(Numbers::Num(record, "interval_seconds")), 0);
                }
                else
                {
                    {
                        std::lock_guard<std::mutex> guard(mutex);
                        heldAs.erase(player->GetGUID().GetRawValue());
                    }
                    Minions::Dismiss(player, "skeleton");
                }
                // "Passive: Raise a Flesh Golem to fight for you": one, and a new one the power's seconds after it
                // dies.
                if (std::uint32_t const record = Slotted(player, GolemSkill))
                {
                    bool changed;
                    {
                        std::lock_guard<std::mutex> guard(mutex);
                        std::uint32_t& held = heldGolemAs[player->GetGUID().GetRawValue()];
                        changed = held && held != record;
                        held = record;
                    }
                    if (changed)
                        Minions::Dismiss(player, "golem");
                    Minions::Keep(player, "command_golem", 1, 0, Millis(Tune("minion_golem_return_seconds")));
                }
                else
                {
                    {
                        std::lock_guard<std::mutex> guard(mutex);
                        heldGolemAs.erase(player->GetGUID().GetRawValue());
                    }
                    Minions::Dismiss(player, "golem");
                }
            }

            void OnPlayerLogout(Player* player) override
            {
                std::lock_guard<std::mutex> guard(mutex);
                waited.erase(player->GetGUID().GetRawValue());
                heldAs.erase(player->GetGUID().GetRawValue());
                heldGolemAs.erase(player->GetGUID().GetRawValue());
            }
        };
    } // namespace

    Creature* RaiseMage(Player* owner, Position const& at, std::uint32_t record, double bonusPct)
    {
        mageCast = {record, bonusPct};
        Creature* mage = Minions::Raise(owner, "skeletal_mage", at);
        mageCast = {};
        return mage;
    }

    Creature* Revive(Player* owner, Position const& at, std::uint32_t display, std::uint32_t record,
                     std::uint32_t corpseEntry)
    {
        reviveCast = {record, corpseEntry};
        Creature* minion = Minions::Raise(owner, "revived_minion", at, display);
        reviveCast = {};
        return minion;
    }

    Creature* Simulacrum(Player* owner, bool bone)
    {
        if (!owner)
            return nullptr;
        // "Spawn Distance Around Player": the copy stands that far off, the Simulacrum of Bone on the opposite side.
        Position const at = owner->GetNearPosition(float(Tune("simulacrum_spawn_yards")), bone ? std::numbers::pi_v<float> : 0.0f);
        return bone ? Minions::Raise(owner, "simulacrum_bone", at, 0, true) : Minions::Raise(owner, "simulacrum", at, 0, true);
    }

    void CommandSkeletons(Player* owner, Unit* target, std::uint32_t ms)
    {
        Minions::Command(owner, "skeleton", target, ms);
    }

    void RegisterScripts()
    {
        Minions::Define("skeletal_mage", Mage);
        Minions::Define("command_skeleton", Skeleton);
        Minions::Define("command_golem", Golem);
        Minions::Define("revived_minion", Revived);
        Minions::Define("simulacrum", Copy);
        Minions::Define("simulacrum_bone", CopyOfBone);
        new Keeper();
    }
} // namespace DC::Combat::Necromancer::Pets
