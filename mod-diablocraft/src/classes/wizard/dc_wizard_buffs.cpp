#include "dc_wizard_buffs.h"
#include "dc_wizard_slow_time.h"
#include "../../combat/dc_buff_values.h"
#include "../../combat/dc_passives.h"
#include "Spell.h"
#include "SpellAuraEffects.h"
#include <algorithm>
#include <cmath>

namespace DC::Combat::Wizard::Buffs
{
    using namespace Shared;

    namespace
    {
        // --- the buffs the player wears (buff icons build 2, data/class_buffs.csv) ---------
        //
        // Each effect below that has a window, a stack count or a condition is also an aura on the Wizard, so the buff
        // bar shows it: the record states one stack's number and the client multiplies it by the stacks. Wanted() says
        // what is on now, in step with the sheet contributions it builds, and ShowBuffs puts it there.
        struct ShownBuff
        {
            char const* identity;
            unsigned stacks;
            double seconds;               // left on its timer, 0: no timer
            std::vector<double> values{}; // the addon line (docs/contracts/buff-values-messages.md)
        };

        // Every record this file shows, so one that is no longer wanted (or was saved with the character) is taken off.
        constexpr char const* ClassBuffs[] = {
            "Illusionist - buff",
            "Unwavering Will - buff",
            "Arcane Dynamo - flashes - buff",
            "Arcane Dynamo - empowered - buff",
            "Storm Armor - Scramble - buff",
            "Frost Nova - Deep Freeze - buff",
            "Teleport - Safe Passage - buff",
            "Energy Twister - Storm Chaser - buff",
            "Wave of Force - Arcane Attunement - buff",
            "Arcane Orb - Spark - buff",
            "Flame Ward - buff",
            "Archon - kills - buff",
            "Ice Armor - Crystallize - buff",
        };

        // The shields: their record says "Absorbs damage." and the addon line is the amount left.
        constexpr char const* ShieldBuffs[] = {
            "Galvanizing Ward - shield", "Dominance - shield", "Unstable Anomaly - shield",
            "Magic Weapon - Deflection - shield", "Spectral Blade - Barrier Blades - shield",
        };

        uint32 BuffId(std::string_view identity)
        {
            static std::map<std::string, uint32, std::less<>> ids = []
            {
                std::map<std::string, uint32, std::less<>> found;
                for (char const* identity : ClassBuffs)
                    found[identity] = Shells::HelperFor(identity);
                for (char const* identity : ShieldBuffs)
                    found[identity] = Shells::HelperFor(identity);
                return found;
            }();
            auto it = ids.find(identity);
            return it == ids.end() ? 0 : it->second;
        }

        void ShowBuffs(Player* player, std::vector<ShownBuff> const& shown)
        {
            for (char const* identity : ClassBuffs)
            {
                auto it = std::find_if(shown.begin(), shown.end(),
                                       [identity](ShownBuff const& buff) { return std::string_view(buff.identity) == identity; });
                if (it != shown.end())
                    BuffValues::Show(player, BuffId(identity), it->stacks, it->seconds, it->values);
                else
                    BuffValues::Show(player, BuffId(identity), 0);
            }
            for (char const* identity : ShieldBuffs)
            {
                uint32 const id = BuffId(identity);
                Aura* aura = id ? player->GetAura(id) : nullptr;
                if (AuraEffect* effect = aura ? aura->GetEffect(EFFECT_0) : nullptr)
                    BuffValues::Set(player, id, {double(effect->GetAmount())});
                else
                    BuffValues::Clear(player, id);
            }
        }

        double SecondsLeft(uint64 until, uint64 now)
        {
            return until > now ? double(until - now) / 1000 : 0;
        }

        struct Want
        {
            Stat stat;
            uint64 id;
            double value;
            Bucket bucket;
            bool resistance; // value is a percentage of each baseline resistance
        };

        std::vector<Want> Wanted(Player* player, State const& state, std::vector<ShownBuff>& shown, bool stretching)
        {
            std::vector<Want> out;
            uint64 const now = Now();
            auto armor = [&](uint64 id, double pct) { out.push_back({Stat::Armor, id, pct, Bucket::Percent, false}); };
            auto resist = [&](uint64 id, double pct)
            { out.push_back({Stat::SingleResistance, id, pct, Bucket::Flat, true}); };
            auto flat = [&](Stat stat, uint64 id, double value, Bucket bucket = Bucket::Flat)
            { out.push_back({stat, id, value, bucket, false}); };

            if (uint32 id = BuffOf(player, "Energy Armor"))
            {
                armor(id, Num(id, "armor_pct"));
                // Energy Tap: "Rather than decreasing your maximum Arcane
                // Power, Energy Armor increases it" - its own number is the
                // increase, the inherited one the decrease.
                if (IsRune(id, "Energy Tap"))
                    flat(Stat::MaxFury, id, Numbers::Own(id, "max_pool_resource").value_or(0));
                else
                    flat(Stat::MaxFury, id, -Num(id, "max_pool_resource"));
                if (IsRune(id, "Prismatic Armor"))
                    resist(id, Num(id, "resistance_pct"));
                if (IsRune(id, "Pinpoint Barrier"))
                    flat(Stat::CritChance, id, Num(id, "crit_chance_pct"));
            }
            if (uint32 id = BuffOf(player, "Diamond Skin"); id && IsRune(id, "Sleek Shell"))
                flat(Stat::MovementSpeed, id, Num(id, "movement_speed_pct"), Bucket::Uncapped);
            // Archon: "your Armor and resistances are increased by 150%"
            // (wizard.js:1010 armor_percent 150, resist_percent 150).
            if (uint32 id = BuffOf(player, "Archon"))
            {
                armor(id, Num(id, "resistance_pct"));
                resist(id, Num(id, "resistance_pct"));
                // Each kill in the form is a stack of its damage bonus, for the rest of the form.
                Aura* form = player->GetAura(id);
                if (state.archonStacks && form && form->GetDuration() > 0)
                    shown.push_back({"Archon - kills - buff", state.archonStacks, form->GetDuration() / 1000.0});
            }
            if (uint32 id = BuffOf(player, "Ice Armor"); id && IsRune(id, "Crystallize"))
            {
                auto stacks = std::count_if(state.crystallize.begin(), state.crystallize.end(),
                                            [now](uint64 until) { return until > now; });
                if (stacks)
                {
                    armor(id, Num(id, "armor_pct") * double(stacks));
                    uint64 last = 0;
                    for (uint64 until : state.crystallize)
                        last = std::max(last, until);
                    shown.push_back({"Ice Armor - Crystallize - buff", unsigned(stacks), SecondsLeft(last, now)});
                }
            }
            if (uint32 id = BuffOf(player, "Storm Armor"); id && IsRune(id, "Scramble") && state.scramble > now)
            {
                flat(Stat::MovementSpeed, id, Num(id, "movement_speed_pct"), Bucket::Uncapped);
                shown.push_back({"Storm Armor - Scramble - buff", 1, SecondsLeft(state.scramble, now)});
            }
            // Stretch Time: the bubble's third slot reaches allies only, so
            // wearing that record is standing in it; a follow aura is the same
            // (Crown of the Primus), its id the one on the sheet.
            uint32 const stretch = Shells::HelperFor("Slow Time - Stretch Time - bubble");
            if ((stretch && player->HasAura(stretch)) || stretching)
                for (Row const& row : Shells::Abilities)
                    if (IsSkill(row.id, "Slow Time") && IsRune(row.id, "Stretch Time"))
                        flat(Stat::AttackSpeed, stretch, Numbers::Own(row.id, "attack_speed_pct").value_or(0));
            if (state.deepFreeze > now)
                for (Row const& row : Shells::Abilities)
                    if (IsSkill(row.id, "Frost Nova") && IsRune(row.id, "Deep Freeze"))
                    {
                        flat(Stat::CritChance, row.id, Num(row.id, "crit_chance_pct"));
                        shown.push_back({"Frost Nova - Deep Freeze - buff", 1, SecondsLeft(state.deepFreeze, now)});
                    }
            if (state.safePassage > now)
                for (Row const& row : Shells::Abilities)
                    if (IsSkill(row.id, "Teleport") && IsRune(row.id, "Safe Passage"))
                    {
                        flat(Stat::SpecificReduction, row.id, Num(row.id, "damage_reduction_pct"));
                        shown.push_back({"Teleport - Safe Passage - buff", 1, SecondsLeft(state.safePassage, now)});
                    }

            // Flame Ward: "You take {damage_reduction_pct:base} less damage
            // from attacks while channeling. Every second you channel
            // increases this amount by {damage_reduction_pct:ramp}, up to a
            // maximum total of {max_damage_pct}".
            if (Spell* channel = player->GetCurrentSpell(CURRENT_CHANNELED_SPELL))
                if (uint32 id = channel->GetSpellInfo()->Id; IsRune(id, "Flame Ward") && state.flameWard)
                {
                    double const seconds = std::floor(double(now - std::min(now, state.flameWard)) / 1000);
                    double const reduction = std::min(Num(id, "max_damage_pct"), Num(id, "damage_reduction_pct", "base") +
                                                                                     Num(id, "damage_reduction_pct", "ramp") * seconds);
                    flat(Stat::SpecificReduction, id, reduction);
                    shown.push_back({"Flame Ward - buff", 1, 0, {reduction}});
                }

            if (uint32 id = PassiveId("Blur"); id && Has(player, "Blur"))
                flat(Stat::SpecificReduction, id, Num(id, "damage_reduction_pct"));
            if (uint32 id = PassiveId("Glass Cannon"); id && Has(player, "Glass Cannon"))
            {
                armor(id, -Num(id, "resistance_pct"));
                resist(id, -Num(id, "resistance_pct"));
            }
            // Astral Presence's maximum only: its +2.5 per second is held
            // for the class resource model.
            if (uint32 id = PassiveId("Astral Presence"); id && Has(player, "Astral Presence"))
                flat(Stat::MaxFury, id, Num(id, "max_pool_resource"));
            if (uint32 id = PassiveId("Unwavering Will");
                id && Has(player, "Unwavering Will") && state.still >= Num(id, "duration_seconds") * 1000)
            {
                armor(id, Num(id, "armor_pct"));
                resist(id, Num(id, "resistance_pct"));
                shown.push_back({"Unwavering Will - buff", 1, 0});
            }
            if (uint32 id = PassiveId("Illusionist"); id && Has(player, "Illusionist") && state.illusionistSpeed > now)
            {
                flat(Stat::MovementSpeed, id, Num(id, "movement_speed_pct"), Bucket::Uncapped);
                shown.push_back({"Illusionist - buff", 1, SecondsLeft(state.illusionistSpeed, now)});
            }
            // Arcane Dynamo: a stack per Flash of Insight, then the full set until a listed spell spends it.
            if (uint32 id = PassiveId("Arcane Dynamo"); id && Has(player, "Arcane Dynamo") && state.flashes)
            {
                if (state.flashes >= unsigned(Num(id, "stack_threshold_count")))
                    shown.push_back({"Arcane Dynamo - empowered - buff", 1, 0});
                else
                    shown.push_back({"Arcane Dynamo - flashes - buff", state.flashes, 0});
            }
            // Storm Chaser's charges, Arcane Attunement's and Spark's counted enemies: the next spell spends them.
            if (state.stormCharges)
                shown.push_back({"Energy Twister - Storm Chaser - buff", state.stormCharges, 0});
            if (state.attunement > 0)
                shown.push_back({"Wave of Force - Arcane Attunement - buff", state.attunementHits, 0});
            if (state.spark > 0)
                shown.push_back({"Arcane Orb - Spark - buff", state.sparkHits, 0});
            return out;
        }
    } // namespace

    // Puts this file's contributions on the sheet when they changed, the
    // dc_abilities Refresh way: take them all off, read the baseline the
    // resistances are a percentage of, put them back, recompute once.
    void Refresh(Player* player, bool force)
    {
        // Read before the lock: it asks the item table (Crown of the Primus gives Stretch Time to its follow aura).
        bool const stretching = SlowTime::GivenFollow(player, "Stretch Time");
        std::lock_guard<std::recursive_mutex> guard(mutex);
        State& state = StateOf(player);
        std::vector<ShownBuff> shown;
        std::vector<Want> wanted = Wanted(player, state, shown, stretching);
        // Every call: the aura is touched only when its stacks or its timer differ.
        ShowBuffs(player, shown);
        std::string signature;
        for (Want const& want : wanted)
            signature += std::to_string(Index(want.stat)) + ":" + std::to_string(want.id) + ":" +
                         std::to_string(want.value) + ";";
        if (!force && signature == state.signature)
            return;
        uint64 const guid = player->GetGUID().GetRawValue();
        for (auto const& [stat, id] : state.applied)
            Stats::RemoveContribution(guid, DC::Source::Temporary, stat, id);
        state.applied.clear();
        Stats::Recompute(player);
        auto baseline = Stats::Get(guid);
        for (Want const& want : wanted)
        {
            if (!want.resistance)
            {
                Stats::AddContribution(guid, {DC::Source::Temporary, want.stat, want.id, want.value, want.bucket});
                state.applied.push_back({want.stat, want.id});
                continue;
            }
            if (!baseline)
                continue;
            for (unsigned e = 0; e < ElementCount; ++e)
            {
                uint64 const key = want.id * ElementCount + e;
                Stats::AddContribution(guid, {DC::Source::Temporary, Stat::SingleResistance, key,
                                              baseline->resistance[e] * want.value / 100, Bucket::Flat,
                                              static_cast<DC::Element>(e)});
                state.applied.push_back({Stat::SingleResistance, key});
            }
        }
        Stats::Recompute(player);
        state.signature = signature;
    }
} // namespace DC::Combat::Wizard::Buffs
