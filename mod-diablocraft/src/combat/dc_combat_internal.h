// What the dc_combat*.cpp files share: their includes, the shell data, the helpers and each file's scripts.
#ifndef DC_COMBAT_INTERNAL_H
#define DC_COMBAT_INTERNAL_H

#include "dc_combat.h"
#include "../classes/barbarian/dc_barbarian.h"
#include "dc_exact_damage.h"
#include "dc_life_commands.h"
#include "dc_buff_values.h"
#include "dc_gem_powers.h"
#include "dc_item_powers.h"
#include "dc_passives.h"
#include "dc_pylons.h"
#include "../classes/barbarian/dc_barbarian_call_of_the_ancients.h"
#include "dc_spell_shells.h"
#include "dc_spell_numbers.h"
#include "dc_spell_values.h"
#include "dc_cost_math.h"
#include "../classes/barbarian/dc_barbarian_primary_data.h"
#include "../classes/barbarian/dc_barbarian_primaries.h"
#include "../common/dc_tunables.h"

#include "../common/dc_numeric_data.h"
#include "dc_monster_d3_type.h"
#include "../stats/dc_stat_readers.h"
#include "../stats/dc_stats.h"
#include "../classes/dc_classes.h"
#include "../classes/dc_resources.h"
#include "../classes/crusader/dc_crusader.h"
#include "../classes/demon_hunter/dc_demon_hunter.h"
#include "../classes/necromancer/dc_necromancer.h"
#include "../classes/shaman/dc_shaman.h"
#include "../classes/witch_doctor/dc_witch_doctor.h"
#include "dc_corpses.h"
#include "../classes/monk/dc_monk.h"
#include "../classes/necromancer/dc_necromancer_pets.h"
#include "../classes/witch_doctor/dc_witch_doctor_pets.h"
#include "dc_minions.h"
#include "../classes/wizard/dc_wizard.h"
#include "../items/dc_items.h"
#include "../rifts/dc_rifts.h"

#include "Chat.h"
#include "DatabaseEnv.h"
#include "Item.h"
#include "Log.h"
#include "ObjectMgr.h"
#include "ObjectAccessor.h"
#include "MoveSpline.h"
#include "Opcodes.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "CellImpl.h"
#include "GridNotifiers.h"
#include "GridNotifiersImpl.h"
#include "Spell.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "SpellScript.h"
#include "SpellAuraEffects.h"
#include "Unit.h"
#include "WorldSession.h"
#include "WorldPacket.h"

#include <algorithm>
#include <cmath>
#include <iomanip>
#include <locale>
#include <mutex>
#include <limits>
#include <optional>
#include <random>
#include <regex>
#include <sstream>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace DC::Combat
{
    namespace Internal
    {
        // Matches the block generate_spells.py reserves.
        constexpr std::uint32_t FIRST_SHELL = 81000, LAST_SHELL = 81156;
        constexpr double AREA_DAMAGE_CHANCE = 0.20; // step 11

        struct Targeting
        {
            std::string type, rangeKind;
            float range = 0, radius = 0, width = 0;
            bool Ready() const
            {
                return !type.empty();
            }
            bool Line() const
            {
                return type == "line_pierce" || type == "line_to_point";
            }
            bool Destination() const
            {
                return type == "ground_point_aoe" || type == "ground_area" || type == "line_to_point";
            }
            bool Friendly() const
            {
                return type == "self" || type == "self_allies" || type == "self_summon";
            }
        };

        struct Shell
        {
            std::uint32_t spellId = 0;
            std::string skill, rune, element;
            double damagePct = 0; // damage_pct_weapon_damage
            // No furyCost: every cost is in the spell record, and the
            // core charges it. Whirlwind's per-tick cost, the one the module
            // still pays, is read by name from the record's exact values.
            // No cooldown either: it is in the spell record, and
            // Player::AddSpellAndCategoryCooldowns installs it from there.
            double furyGeneration = 0;
            bool passive = false;
            bool dot = false; // Rend, Earthquake: C11 average-crit ticks
            double extraDamage = 0;
            double dotSeconds = 0;
            Targeting targeting;
        };

        inline std::mutex dataMutex;
        inline std::unordered_map<std::uint32_t, Shell> shells;
        inline bool dataReady = false;

        inline std::optional<Shell> FindShell(uint32 id)
        {
            std::lock_guard<std::mutex> lock(dataMutex);
            auto it = shells.find(id);
            return it == shells.end() ? std::nullopt : std::optional<Shell>(it->second);
        }

        inline bool Slotted(Player* player, uint32 spellId)
        {
            // Every class's skills and runes are Shells::Abilities; for the
            // Barbarian that is exactly 81000..81137, the range this used to
            // test; no id range is written here any more.
            if (!Shells::FindAbility(spellId))
                return true;
            auto bar = Classes::Bar(player);
            return std::any_of(bar.begin(), bar.end(),
                               [spellId](Classes::Slot const& slot) { return slot.spellId == spellId; });
        }

        inline std::mt19937_64& Engine()
        {
            static thread_local std::mt19937_64 engine{std::random_device{}()};
            return engine;
        }
        inline double Roll()
        {
            return std::uniform_real_distribution<double>(0.0, 1.0)(Engine());
        }

        inline bool Barbarian(Player const* player)
        {
            return player && player->getClass() == CLASS_WARRIOR;
        }

        // The hit path's gate:
        // any class with a generated catalogue casts and hits through the
        // same path. The auto-attack guards and the melee outcome use it too;
        // only what is about Fury
        // keeps the Barbarian gate above.
        inline bool HitsThroughCombat(Player const* player)
        {
            return player && Classes::Playable(player);
        }

        // The main stat a hit scales with, from class_map.csv's primary_stat
        // (dc_class_map) - Strength for the Barbarian, Intelligence for the
        // Wizard. A class with no main stat named there has none, and no hit.
        inline std::optional<Stat> MainStat(Player const* player)
        {
            std::string const name = Classes::PrimaryStatOf(player);
            if (name == "Strength")
                return Stat::Strength;
            if (name == "Dexterity")
                return Stat::Dexterity;
            if (name == "Intelligence")
                return Stat::Intelligence;
            return std::nullopt;
        }

        inline unsigned SchoolOf(std::string const& element)
        {
            // 01-stats S9.
            if (element == "fire")
                return SPELL_SCHOOL_MASK_FIRE;
            if (element == "cold")
                return SPELL_SCHOOL_MASK_FROST;
            if (element == "lightning")
                return SPELL_SCHOOL_MASK_NATURE;
            if (element == "poison")
                return SPELL_SCHOOL_MASK_SHADOW;
            if (element == "arcane")
                return SPELL_SCHOOL_MASK_ARCANE;
            if (element == "holy")
                return SPELL_SCHOOL_MASK_HOLY;
            return SPELL_SCHOOL_MASK_NORMAL;
        }

        inline Stat ElementalStatFor(std::string const&)
        {
            return Stat::ElementalDamage;
        }

        // The inverse of SchoolOf. The generator already resolved every shell's element
        // into its SchoolMask - from the rune's element, or from barbarian_skills.csv's
        // element column for a base skill - so the school in spell_dbc is the single
        // source of truth and the server cannot disagree with the client about it.
        inline std::string ElementOfSchool(unsigned mask)
        {
            switch (mask)
            {
                case SPELL_SCHOOL_MASK_FIRE:
                    return "fire";
                case SPELL_SCHOOL_MASK_FROST:
                    return "cold";
                case SPELL_SCHOOL_MASK_NATURE:
                    return "lightning";
                case SPELL_SCHOOL_MASK_SHADOW:
                    return "poison";
                case SPELL_SCHOOL_MASK_ARCANE:
                    return "arcane";
                case SPELL_SCHOOL_MASK_HOLY:
                    return "holy";
                default:
                    return "physical";
            }
        }

        // A class's runes.csv modified_cost_cooldown_damage. The same grammar
        // generate_spells.py parses (RUNE_MODIFIERS there): clauses separated by "|",
        // and an unrecognised clause throws rather than being dropped, so a new CSV
        // value cannot silently stop applying.
        //
        // "N% increased damage" is not a damage override. Those rows are buffs and
        // debuffs - "enemies ... take 10% increased damage from all sources", "gain 50%
        // increased damage" - and belong in the additive bucket once auras carry them,
        // not in the shell's own skill percentage. They are recognised and ignored.
        struct RuneModifiers
        {
            // The cost and cooldown clauses are still parsed - an
            // unrecognised clause has to stay an error on both sides - but
            // nothing here applies them any more: generate_spells.py reads
            // the same column and writes the cost and the cooldown
            // into the record, which is what the core uses.
            double damagePct = 0;
            bool hasDamage = false;
        };

        inline RuneModifiers ParseRuneModifiers(std::string const& text)
        {
            // A cost form names the class's resource: any d3_name of the generated
            // resource registry (class_resources.csv), as generate_spells.py reads it.
            static std::string const resourceNames = []
            {
                std::string names;
                for (DC::Resources::Data::Row const& row : DC::Resources::Data::Rows)
                    names += (names.empty() ? "" : "|") + std::string(row.d3Name);
                return names;
            }();
            static std::regex const forms[] = {
                std::regex(R"(^([0-9]+(?:\.[0-9]+)?)% weapon damage$)"),
                std::regex(R"(^([0-9]+(?:\.[0-9]+)?)% damage$)"),
                std::regex(R"(^([0-9]+(?:\.[0-9]+)?)% increased damage$)"),
                std::regex(R"(^Cooldown (?:reduced|increased) to ([0-9]+(?:\.[0-9]+)?) seconds?$)"),
                std::regex("^Cost reduced to ([0-9]+(?:\\.[0-9]+)?) (?:" + resourceNames + ")$"),
                std::regex("^(?:" + resourceNames + ") cost removed$"),
                std::regex("^Cost changed to ([0-9]+(?:\\.[0-9]+)?) (?:" + resourceNames + ")$"),
                std::regex(R"(^Cooldown removed$)"),
            };
            RuneModifiers out;
            std::size_t start = 0;
            while (start <= text.size())
            {
                std::size_t const bar = text.find('|', start);
                std::string clause = text.substr(start, bar == std::string::npos ? std::string::npos : bar - start);
                start = bar == std::string::npos ? text.size() + 1 : bar + 1;
                std::size_t const first = clause.find_first_not_of(" \t");
                if (first == std::string::npos)
                    continue;
                clause = clause.substr(first, clause.find_last_not_of(" \t") - first + 1);
                std::smatch match;
                if (std::regex_match(clause, match, forms[0]) || std::regex_match(clause, match, forms[1]))
                {
                    out.damagePct = std::stod(match[1]);
                    out.hasDamage = true;
                }
                else if (std::regex_match(clause, match, forms[2]))
                {
                    // A buff or debuff; not this shell's damage. Recognised, not applied.
                }
                else if (std::regex_match(clause, match, forms[3]))
                {
                    // "Cooldown reduced/increased to N seconds": the record carries the
                    // result, so this is recognised here and applied there.
                    // generate_spells.py checks the rune's values sheet states
                    // the same number the clause does.
                }
                else if (std::regex_match(clause, match, forms[4]) ||
                         std::regex_match(clause, forms[5]) ||
                         std::regex_match(clause, match, forms[6]) ||
                         std::regex_match(clause, forms[7]))
                {
                    // "Cost reduced/changed to N <resource>" / "<resource> cost removed" /
                    // "Cooldown removed": the
                    // record carries the result, so it is recognised here and
                    // applied by the generator, not at runtime.
                }
                else
                    throw std::runtime_error("Unparsed rune modifier: " + clause);
            }
            return out;
        }

        inline Element ElementEnum(std::string const& element)
        {
            if (element == "fire")
                return Element::Fire;
            if (element == "cold")
                return Element::Cold;
            if (element == "lightning")
                return Element::Lightning;
            if (element == "poison")
                return Element::Poison;
            if (element == "arcane")
                return Element::Arcane;
            if (element == "holy")
                return Element::Holy;
            return Element::Physical;
        }

        // --- Fury (02 §4) ----------------------------------------------------------
        // Which slot Fury lives in and how many of its units a point is are the
        // class resource registry's (dc_resources.h); generate_spells.py wrote
        // every ManaCost from the same registry row, so the two cannot drift.
        // Audit row 7: barbarian_fury.csv carried this only as prose ("0.5 Fury
        // per 1% Life lost"), so section B transcribed it into the numeric cell
        // fury_per_life_pct and generates it as the dc_numeric_rule
        // fury_from_damage_per_life_pct. Read rather than repeated; a number is
        // never parsed out of prose at runtime.
        inline double FuryPerPercentLife()
        {
            return DC::NumericData::Rule("fury_from_damage_per_life_pct");
        }

        inline void ChangeFury(Player* player, double fury)
        {
            if (!player || fury == 0)
                return;
            Resources::Add(player, Resources::Fury, fury * (fury > 0 ? Passives::GenerationFactor(player) : 1));
        }

        inline double CurrentFury(Player* player)
        {
            return player ? Resources::Get(player, Resources::Fury) : 0.0;
        }

        // --- who pays ----------------------
        // The cost is a field on the spell record and Spell::TakePower charges
        // it; every reduction is a SPELLMOD_COST aura, so the arithmetic is the
        // core's own - percentages, then flat, clamped at zero
        // (Player::ApplySpellMod, SpellInfo::CalcPowerCost), with
        // core-patches/0014 making those percentages multiply the way D3's do.
        // There is no second copy of that arithmetic here.
        //
        // Two things the core cannot do stay module-owned.
        // This is the first: the cost of a skill the core is not
        // charging - Whirlwind's channel tick - reduced exactly as the core
        // would have reduced it. What the core is asked for is the FACTOR its
        // own SPELLMOD_COST auras produce for this spell, which is also what
        // the character sheet displays: a probe cost in, the reduced cost out.
        // Reading a factor rather than charging a Rage-unit cost keeps the
        // tick's own precision - the record's integer units are the core's
        // business, not this one's.

        // The second exception:
        // a rune that spends the whole pool. A stock record says
        // "this costs 25 Fury"; it cannot say "and then take the rest", so the
        // core charges the base cost and the module empties what is left.
        // Ancient Spear - Boulder Toss and Seismic Slam - Rumble, and D3
        // charges the base cost for both (docs/research/d3-cost-cooldown-math.md).
        inline bool SpendsEveryPoint(Shell const& shell)
        {
            return Abilities::SpendsEveryPoint(shell.skill, shell.rune);
        }

        // The third exception: the Wizard's channels - Ray of
        // Frost, Arcane Torrent and Disintegrate, and their runes - are paid by
        // the module tick by tick in Whirlwind's shape. Their records are real
        // channels with no ManaCost (generate_spells.py CHANNEL_DRAIN_SKILLS);
        // what marks one is its sourced channel frame count. Whirlwind has one
        // too and keeps its own loop in dc_abilities.cpp.
        // A record whose damage is not one hit at the cast: it is spread over a window, ramps, or waits on a
        // duration, a summon or an armour (the loader below gives it no damage; the class's own mechanic deals it).
        // A duration the record states under any other name is no wait: Flame Blades' stacks last
        // bonus_duration_seconds and its hit is at once (under the name duration_seconds it
        // loaded with no damage, and the rune dealt none).
        inline bool DamageWaits(std::uint32_t id)
        {
            return Numbers::Has(id, "dot_duration_seconds") || Numbers::Has(id, "duration_seconds") ||
                   Numbers::Has(id, "duration_minutes") || Numbers::Has(id, "damage_pct", "ramp");
        }

        inline bool WizardChannel(Shell const& shell)
        {
            return !Abilities::PaysByTick(shell.skill) && Numbers::Has(shell.spellId, "channel_tick_frames_count");
        }

        // Arcane Power a Wizard gains, through the core's own energize
        // (Unit::EnergizeBySpell, the call Spell::EffectEnergize makes): it
        // adds the power, clamps it at the maximum and sends the energize log.
        // No record effect can do these two: EffectEnergize gives power to the
        // effect's target, which is the enemy on a damage record, and a caster
        // target fires once per cast, not once per enemy hit.
        inline void GainArcanePower(Player* player, std::uint32_t spellId, double points)
        {
            if (!player || points <= 0 || !Resources::Displayed(player, Resources::ArcanePower))
                return;
            Resources::Energize(player, Resources::ArcanePower, spellId, points * ItemPowers::GenerationFactor(player));
        }

        // Power Affinity, Siphoning Blade, Surge of Power: "Gain N Arcane Power
        // for each enemy hit" (wizard_runes.csv, wizard_resource.csv row 8).
        // The Barbarian's own gain_resource runes are paid in dc_abilities.cpp
        // and are Rage, which GainArcanePower leaves alone.
        inline void GainPerEnemyHit(Player* player, std::uint32_t spellId)
        {
            if (auto gain = Numbers::Get(spellId, "gain_resource"))
                GainArcanePower(player, spellId, *gain);
        }

        // What is left of the old PayCast once the Fury is the core's to take:
        // the passives that watch Fury being spent, and the skill's own
        // generation. `furySpent` is what the core actually charged.
        inline void AfterPayment(Player* player, Shell const& shell, double furySpent)
        {
            Abilities::Spent(player, furySpent);
            ChangeFury(player, shell.furyGeneration);
        }

        // An elite for the sheet's two elite stats, Elite Damage on the hit dealt and Elite Damage Reduction on the
        // hit taken, so both directions agree: the creature's own rank, or any monster of a rift's champion or rare pack, its
        // members included, as D3 counts a rare's minions and every champion (loot still asks IsPromotedElite).
        inline bool IsElite(Unit const* unit)
        {
            Creature const* creature = unit ? unit->ToCreature() : nullptr;
            return creature && (creature->isElite() || DC::Rifts::IsElitePack(creature));
        }

        // The creature kind the sheet's Damage to Beasts, Demons, Undead and Humans read (d3planner damage_beasts, damage_demons,
        // damage_undead, damage_humans): the template's creature type for the first three. D3's Human has no 3.3.5 type of its
        // own, so it is a monster the sheet types as Human (data/d3/gr_monster_progress.csv, dc_monster_d3_type).
        inline Stats::Readers::MonsterKind KindOf(Unit const* unit)
        {
            Creature const* creature = unit ? unit->ToCreature() : nullptr;
            switch (creature ? creature->GetCreatureTemplate()->type : 0)
            {
                case CREATURE_TYPE_BEAST: return Stats::Readers::MonsterKind::Beast;
                case CREATURE_TYPE_DEMON: return Stats::Readers::MonsterKind::Demon;
                case CREATURE_TYPE_UNDEAD: return Stats::Readers::MonsterKind::Undead;
                default: return MonsterTypes::D3TypeOf(creature) == "Human" ? Stats::Readers::MonsterKind::Human : Stats::Readers::MonsterKind::Other;
            }
        }
    } // namespace Internal
    using namespace Internal;

    // Defined in dc_combat.cpp and called from the other files.
    void ChannelSpent(Player*, std::uint32_t);
    double ChannelTickCost(Player*, std::uint32_t);

    // Each file's scripts, registered by RegisterScripts.
    void RegisterResolveScripts();
    void RegisterHookScripts();
    void RegisterCommandScripts();
} // namespace DC::Combat

#endif // DC_COMBAT_INTERNAL_H
