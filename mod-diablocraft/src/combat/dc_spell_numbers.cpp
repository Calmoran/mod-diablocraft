#include "dc_spell_numbers.h"
#include "dc_spell_values.h"
#include "dc_spell_shells.h"
#include "../classes/dc_resource_data.h"
#include "DBCStructure.h"
#include "DatabaseEnv.h"
#include "Field.h"
#include "QueryResult.h"
#include "Log.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include <map>
#include <mutex>
#include <set>
#include <string>
#include <tuple>
#include <unordered_map>

namespace DC::Combat::Numbers
{
    namespace
    {
        using SpellValues::Origin;
        using SpellValues::Row;
        using SpellValues::Source;

        using Key = std::tuple<uint32_t, std::string_view, std::string_view>;

        struct KeyHash
        {
            std::size_t operator()(Key const& key) const
            {
                std::size_t hash = std::hash<uint32_t>()(std::get<0>(key));
                hash ^= std::hash<std::string_view>()(std::get<1>(key)) + 0x9e3779b9 + (hash << 6) + (hash >> 2);
                hash ^= std::hash<std::string_view>()(std::get<2>(key)) + 0x9e3779b9 + (hash << 6) + (hash >> 2);
                return hash;
            }
        };

        // (spell, token, qualifier) -> the row that answers for it, which is
        // the record's OWN row wherever it has one.
        //
        // A record states a token itself or inherits it, and almost never
        // both. Step 8 made two records do both: Hardened Wrath and Demoralize
        // each carry their skill's shout duration, which the record's
        // DurationIndex holds so Inspiring Presence's SPELLMOD_DURATION can
        // double it, AND their own duration_seconds - the armour window and
        // the taunt - which must not double and which
        // therefore lives as an exact value. The
        // module asks for the record's own number, so own wins; the skill's
        // is still in the record and is what the client's $d renders.
        // Three of them, so a key that has both rows can still be asked for
        // either one: `any` is what Num() reads and prefers the record's own,
        // `own` and `inherited` answer only for their origin.
        struct Indexes
        {
            std::unordered_map<Key, Row const*, KeyHash> any, own, inherited;
        };

        Indexes const& Index()
        {
            static Indexes const index = []
            {
                Indexes built;
                built.any.reserve(std::size(SpellValues::Rows));
                for (Row const& row : SpellValues::Rows)
                {
                    Key const key{row.spell, row.token, row.qualifier};
                    auto [entry, fresh] = built.any.emplace(key, &row);
                    if (!fresh && row.origin == Origin::Own)
                        entry->second = &row;
                    (row.origin == Origin::Own ? built.own : built.inherited).emplace(key, &row);
                }
                return built;
            }();
            return index;
        }

        std::map<std::tuple<uint32_t, std::string, std::string>, double> exactValues;
        std::once_flag exactLoaded;

        void LoadExact()
        {
            QueryResult rows = WorldDatabase.Query("SELECT spell_id, token, qualifier, value FROM dc_spell_values");
            if (!rows)
            {
                LOG_ERROR("server", "dc_spell_values is missing or empty; the exact spell "
                                    "numbers (the cooldowns, Whirlwind's per-tick Fury cost, "
                                    "the unrepresentable radii) read as absent");
                return;
            }
            do
            {
                Field* field = rows->Fetch();
                exactValues[std::make_tuple(field[0].Get<uint32>(), field[1].Get<std::string>(),
                                            field[2].Get<std::string>())] = field[3].Get<double>();
            } while (rows->NextRow());
        }

        std::optional<double> Exact(Row const& row)
        {
            std::call_once(exactLoaded, LoadExact);
            auto found =
                exactValues.find(std::make_tuple(row.spell, std::string(row.token), std::string(row.qualifier)));
            return found == exactValues.end() ? std::nullopt : std::optional<double>(found->second);
        }

        // The record is the storage; this is the conversion back out of it.
        std::optional<double> Read(Row const& row)
        {
            if (row.source == Source::Exact)
                return Exact(row);

            SpellInfo const* info = sSpellMgr->GetSpellInfo(row.holder);
            if (!info)
            {
                LOG_ERROR("server", "Spell {} holds a number for spell {} ({}) and does not exist", row.holder,
                          row.spell, row.token);
                return std::nullopt;
            }

            switch (row.source)
            {
                case Source::BasePoints:
                {
                    // The writer stores value - 1 with a die side of 1, which is
                    // how WoW spells its own numbers: the roll is always the one.
                    SpellEffectInfo const& effect = info->Effects[row.slot - 1];
                    return double(effect.BasePoints + effect.DieSides);
                }
                case Source::Duration:
                {
                    int32 duration = info->GetDuration();
                    if (duration < 0)
                        return std::nullopt;
                    // A `_minutes` token is minutes (the armors' ten minutes had been written
                    // as ten seconds), everything else seconds.
                    std::string_view const token = row.token;
                    std::string_view const minutes = "_minutes";
                    bool const inMinutes =
                        token.size() >= minutes.size() && token.substr(token.size() - minutes.size()) == minutes;
                    return duration / (inMinutes ? 60000.0 : 1000.0);
                }
                case Source::Radius:
                {
                    SpellEffectInfo const& effect = info->Effects[row.slot - 1];
                    return effect.RadiusEntry ? std::optional<double>(effect.RadiusEntry->RadiusMin) : std::nullopt;
                }
                case Source::Period:
                    return info->Effects[row.slot - 1].Amplitude / 1000.0;
                case Source::Chain:
                    // The record's ChainTarget counts the primary victim -
                    // Spell::SelectImplicitChainTargets searches ChainTarget-1
                    // more after the primary is already a target - and the
                    // sheets state the additional enemies. So the field is one
                    // more than the sheet and this takes the one back off,
                    // which is the same conversion the sentence makes when the
                    // client renders ${$x1-1}.
                    return double(info->Effects[row.slot - 1].ChainTarget) - 1;
                case Source::ProcChance:
                    return double(info->ProcChance);
                case Source::Stacks:
                    return double(info->StackAmount);
                case Source::Charges:
                    return double(info->ProcCharges);
                case Source::MaxTargets:
                    return double(info->MaxAffectedTargets);
                case Source::Cost:
                    // Step 5: the record holds the cost in its PowerType
                    // slot's units, and the sheets speak resource points. This
                    // is the number the core charges, before any SPELLMOD_COST
                    // reduction - the reductions are the player's, not the
                    // record's. The scale is the class resource registry's
                    // for the record's own class (its spell family) on that
                    // slot, since two classes can share a slot at different
                    // scales.
                    return info->ManaCost / Resources::Data::ScaleOf(Shells::ClassOfFamily(info->SpellFamilyName),
                                                                     info->PowerType);
                case Source::Cooldown:
                    // Step 6: the record holds the skill's own recovery and
                    // Player::AddSpellAndCategoryCooldowns installs it. This is
                    // the number before any SPELLMOD_COOLDOWN reduction - the
                    // reductions are the player's, not the record's.
                    return info->RecoveryTime / 1000.0;
                case Source::Recharge:
                    // The timer a base skill and its runes share, which for a
                    // charge skill is the charge recharge and its only timer.
                    return info->CategoryRecoveryTime / 1000.0;
                default:
                    return std::nullopt;
            }
        }

        Row const* Look(std::unordered_map<Key, Row const*, KeyHash> const& index, uint32_t spell,
                        std::string_view token, std::string_view qualifier)
        {
            auto found = index.find(Key{spell, token, qualifier});
            return found == index.end() ? nullptr : found->second;
        }

        Row const* Find(uint32_t spell, std::string_view token, std::string_view qualifier)
        {
            return Look(Index().any, spell, token, qualifier);
        }
    } // namespace

    std::optional<double> Get(uint32_t spell, std::string_view token, std::string_view qualifier)
    {
        Row const* row = Find(spell, token, qualifier);
        return row ? Read(*row) : std::nullopt;
    }

    std::optional<double> Own(uint32_t spell, std::string_view token, std::string_view qualifier)
    {
        Row const* row = Look(Index().own, spell, token, qualifier);
        return row ? Read(*row) : std::nullopt;
    }

    std::optional<double> Inherited(uint32_t spell, std::string_view token, std::string_view qualifier)
    {
        Row const* row = Look(Index().inherited, spell, token, qualifier);
        return row ? Read(*row) : std::nullopt;
    }

    bool Has(uint32_t spell, std::string_view token, std::string_view qualifier)
    {
        return Find(spell, token, qualifier) != nullptr;
    }

    double Num(uint32_t spell, std::string_view token, std::string_view qualifier)
    {
        if (std::optional<double> value = Get(spell, token, qualifier))
            return *value;

        static std::set<std::tuple<uint32_t, std::string, std::string>> reported;
        static std::mutex reportedMutex;
        std::lock_guard<std::mutex> guard(reportedMutex);
        if (reported.insert(std::make_tuple(spell, std::string(token), std::string(qualifier))).second)
            LOG_ERROR("server", "Spell {} has no number named {}{}{}; reading zero", spell, token,
                      qualifier.empty() ? "" : ":", qualifier);
        return 0.0;
    }

    void Load()
    {
        Index();
        std::call_once(exactLoaded, LoadExact);
    }

    std::size_t ExactCount()
    {
        std::call_once(exactLoaded, LoadExact);
        return exactValues.size();
    }
} // namespace DC::Combat::Numbers
