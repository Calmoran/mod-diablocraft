#include "dc_stats.h"
#include "dc_movement_math.h"
#include "dc_resource_pulse.h"
#include "../combat/dc_combat.h"
#include "../combat/dc_passives.h"
#include "../combat/dc_spell_shells.h"
#include "../combat/dc_spell_values.h"
#include "../combat/dc_weapon_flat.h"
#include "../classes/dc_classes.h"
#include "../classes/dc_resource_pool.h"
#include "../classes/dc_resources.h"
#include "../common/dc_tunables.h"

#include "../items/dc_items.h"
#include "Chat.h"
#include "DatabaseEnv.h"
#include "Item.h"
#include "Log.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "SpellAuraEffects.h"
#include "SpellAuras.h"
#include "WorldSession.h"

#include <algorithm>
#include <cmath>
#include <iomanip>
#include <locale>
#include <map>
#include <mutex>
#include <sstream>
#include <stdexcept>

namespace DC::Stats
{
    namespace
    {
        std::mutex storeMutex;
        std::map<std::uint64_t, CharacterStats> characters;
        // One base sheet per class,
        // keyed by the WoW class id and read from dc_class_base_stats.
        // `resource` is the class's primary resource in the class resource
        // registry: which WoW power slot it is
        // stored in and how many of its units one point is.
        struct ClassSheet
        {
            std::uint32_t classId = 0; // class_map.csv's class_id
            Resources::Resource const* resource = nullptr;
            // The class's second resource, beside the shown power (class_resources.csv role second), or nullptr.
            Resources::Resource const* second = nullptr;
            Stat mainStat = Stat::Strength;
            std::map<unsigned, BaseStats> levels;
        };
        std::map<unsigned, ClassSheet> classes;
        bool basesReady = false;
        // dc_block_tuning (docs/research/block.md §5, generate_block.py). Read once
        // at startup; the defaults in BlockTuning match the CSV the table is
        // generated from, so a server whose migration has not been applied behaves
        // exactly like one that has. Every stat path reads this one copy, so
        // `.dc reload block` style retuning is a DB edit plus a restart, not a
        // rebuild - none of these three numbers is a compile-time decision.
        BlockTuning blockTuning;

        constexpr std::array<SpellSchools, ElementCount> Schools = {
            SPELL_SCHOOL_NORMAL, SPELL_SCHOOL_FIRE,   SPELL_SCHOOL_FROST, SPELL_SCHOOL_NATURE,
            SPELL_SCHOOL_SHADOW, SPELL_SCHOOL_ARCANE, SPELL_SCHOOL_HOLY};
        constexpr std::array<char const*, ElementCount> ElementNames = {"Physical", "Fire",   "Cold", "Lightning",
                                                                        "Poison",   "Arcane", "Holy"};

        // 02 C7 / stats.csv Attack Speed: "Dual-wielding adds an additive 15% IAS into
        // the sheet bucket". It is a sheet number, so it belongs in a contribution.
        // The 15 is data (GitHub #58): stats.csv Attack Speed
        // dual_wield_ias_pct, reaching dc_tunables as combat/dual_wield_ias_pct.
        double DualWieldIas() { return DC::Tunables::Get("combat", "dual_wield_ias_pct"); }
        // Two contribution ids reserved for the weapon source. An item affix id is
        // (itemGuid << 16 | seq) (dc_items.cpp ContributionId) and an item guid is
        // never 0, so no affix can ever collide with 1 or 2.
        constexpr std::uint64_t WEAPON_APS_ID = 1, DUAL_WIELD_ID = 2;

        // A class whose primary resource is stored on the Rage slot (the Barbarian's Fury, the Shaman's Maelstrom) stays out of
        // the core's rage rewards: the resource pulse and the skills are its only source.
        bool RageResource(Player const* player)
        {
            if (!player)
                return false;
            if (player->getClass() == CLASS_WARRIOR)
                return true;
            Resources::Resource const* row = Resources::Of(Classes::ClassIdOf(player));
            return row && row->power == Pulse::Rage;
        }

        // The stats gate: every class with a
        // generated catalogue has a D3 sheet, the same one gate the hit path
        // uses. A playable class whose base rows did not load fails in Load()
        // and is kicked, as the Barbarian always was; nothing falls back to
        // WoW's own stats.
        bool Sheeted(Player const* player)
        {
            return player && Classes::Playable(player);
        }

        ClassSheet const& SheetOf(Player const* player)
        {
            return classes.at(player->getClass());
        }

        BaseStats const& BaseFor(Player const* player)
        {
            return SheetOf(player).levels.at(player->GetLevel());
        }

        Stat MainStatNamed(std::string const& name)
        {
            if (name == "Strength")
                return Stat::Strength;
            if (name == "Dexterity")
                return Stat::Dexterity;
            if (name == "Intelligence")
                return Stat::Intelligence;
            throw std::runtime_error("class_map.csv main stat " + name + " is not a primary attribute");
        }

        // 01 §3: max Life is ours and the core only stores it. Publishing a new max has
        // to carry current Life with it. The core decides current health once, inside
        // Player::LoadFromDB, and Unit::SetMaxHealth only ever clamps health downwards,
        // so any source that raises max Life after that point (a first login, Paragon's
        // Vitality, a level, gear) would otherwise leave the character stranded at the
        // bottom of a much larger globe. Current Life keeps its share of max Life.
        void SetMaxLife(Player* player, double maxLife)
        {
            std::uint32_t const previousMax = player->GetMaxHealth();
            std::uint32_t const previousLife = player->GetHealth();
            player->SetMaxHealth(static_cast<uint32>(std::clamp(maxLife, 1.0, 4294967295.0)));
            std::uint32_t const max = player->GetMaxHealth();
            if (max == previousMax || previousMax == 0 || !player->IsAlive())
                return;
            player->SetHealth(std::max<uint32>(
                1, static_cast<uint32>(std::llround(static_cast<double>(previousLife) * max / previousMax))));
        }

        // A share of 0 means this character has no saved D3 Life: a character that has
        // never logged in under the D3 stat sheet, or a row written before Life was
        // ours. Both start full. A corpse or a ghost is left dead.
        void RestoreLife(Player* player, double share)
        {
            if (!player->IsAlive())
                return;
            std::uint32_t const max = player->GetMaxHealth();
            player->SetHealth(share <= 0 ? max : std::max<uint32>(1, static_cast<uint32>(std::llround(share * max))));
        }

        // Issue #54: the sheet's Movement Speed, published as the
        // one aura the core actually reads. It had no publisher at all before
        // this - the number was accumulated, capped and drawn on the screen,
        // and nothing turned it into speed.
        //
        // One aura, not one per source: Unit::UpdateSpeed takes the LARGEST
        // SPELL_AURA_MOD_INCREASE_SPEED and not the sum, so a per-source aura
        // would silently drop every source but the biggest. The amount is the
        // sheet's whole total - the capped gear and paragon share and the
        // uncapped skill bonuses, combined by dc_common.cpp - so this reads one
        // number and casts one aura, the same shape as the gear cost and
        // cooldown reductions (dc_passives.cpp RebuildGearModifier).
        //
        // Whole percent, because that is what an aura amount is: at most half a
        // percent of movement speed is lost to the rounding, and nothing else
        // rounds, since the sheet's own cap is applied before this sees it.
        //
        // The elite-affix slows are the stock negative aura beside it
        // (dc_rift_elites.cpp), so the core combines the pair itself and a slow
        // no longer overwrites the bonus.
        void PublishMovement(Player* player, StatSheet const& sheet)
        {
            auto const amount = MovementAuraAmount(sheet[Stat::MovementSpeed]);
            Aura* current = player->GetAura(Combat::Shells::MovementAggregate);
            AuraEffect const* effect = current ? current->GetEffect(EFFECT_0) : nullptr;
            if (effect && effect->GetAmount() == amount)
                return;
            if (current)
                player->RemoveAurasDueToSpell(Combat::Shells::MovementAggregate);
            if (amount > 0)
            {
                int32 value = int32(amount);
                player->CastCustomSpell(player, Combat::Shells::MovementAggregate, &value,
                                        nullptr, nullptr, true);
            }
        }

        // A resource that refills by itself
        // (Arcane Power, 10 per second in and out of combat) does it through
        // the core's own mana regeneration. The rate is in the hidden aura's
        // record (generate_spells.py RESOURCE_REGENERATION, from
        // wizard_resource.csv); the module only keeps the aura on. It is a
        // passive record, so death does not take it off, and a passive aura is
        // not saved, so every login puts it back through here.
        //
        // A resource on Energy at another rate than the slot's native 10 per second
        // (Wrath 2.5, Hatred 5) carries a second hidden passive,
        // Combat::Shells::EnergyRateFor (generate_spells.py ENERGY_RATE): a percent
        // aura on Energy that Player::UpdateEnergyRegen multiplies into the native
        // gain, so the core pays the D3 rate itself.
        //
        // Each lookup is 0 for a class without that record, which the generator
        // writes only from the registry row: the Mana aura for a Mana resource that
        // refills by itself, the rate passive for an Energy resource off the native
        // rate. Decay needs nothing here: a Decay::Stock resource (Fury) loses at the
        // slot's own core rule and rate, paid by the resource pulse
        // (dc_resource_pulse.cpp), a Decay::Timed one (Maelstrom) loses its combat.csv
        // rate after its wait out of combat, also paid by the pulse, and a Decay::None
        // resource does not decay (generate_class_resources.py refuses anything else).
        void PublishRegeneration(Player* player, ClassSheet const& cls)
        {
            for (std::uint32_t const spell : {Combat::Shells::ResourceRegenerationFor(cls.classId),
                                              Combat::Shells::EnergyRateFor(cls.classId)})
                if (spell && !player->HasAura(spell))
                    player->AddAura(spell, player);
        }

        void Display(Player* player, StatSheet const& sheet)
        {
            // Only direct display writes: these setters do not recalculate WoW stats.
            auto rounded = [](double value) { return static_cast<int32>(std::llround(value)); };
            player->SetStat(STAT_STRENGTH, rounded(sheet[Stat::Strength]));
            player->SetStat(STAT_AGILITY, rounded(sheet[Stat::Dexterity]));
            player->SetStat(STAT_INTELLECT, rounded(sheet[Stat::Intelligence]));
            player->SetStat(STAT_STAMINA, rounded(sheet[Stat::Vitality]));
            // Armor and magic resistance fields feed the core's mitigation.
            // Keep them zero: our combat hooks already apply D3 defence and
            // re-zero these fields before the core can reduce the hit again.
            // D3 Armor and resists remain on the sheet, read by the inventory
            // screen and .dc stats.
            player->SetArmor(0);
            // WoW's physical resistance field IS armor; zero the six magic schools too.
            for (unsigned element = 1; element < ElementCount; ++element)
                player->SetResistance(Schools[element], 0);
            SetMaxLife(player, sheet.maxLife);
            // The class's resource maximum, in its own slot at the row's units
            // a point (class_resources.csv storage_scale).
            ClassSheet const& cls = SheetOf(player);
            Resources::SetMax(player, *cls.resource, sheet[Stat::MaxFury]);
            Resources::ClampToMax(player, *cls.resource);
            // A second resource's maximum is its pool (class_resources.csv), what skills add (Resources::Pool) and what gear adds
            // (Stat::MaxSecond); Paragon gives it none.
            if (cls.second)
            {
                Resources::SetMax(player, *cls.second,
                                  Resources::Pool::Maximum(cls.second->pool, player->GetGUID().GetRawValue(), sheet[Stat::MaxSecond]));
                Resources::ClampToMax(player, *cls.second);
            }
            PublishRegeneration(player, cls);
            player->UpdateAttackPowerAndDamage(false);
            player->UpdateAttackPowerAndDamage(true);
            player->UpdateAllCritPercentages();
            player->UpdateAllSpellCritChances();
            // Last, and not read back: the aura's amount comes from the sheet,
            // and nothing puts it into the sheet, so this cannot feed itself.
            PublishMovement(player, sheet);
        }

        void Save(Player* player)
        {
            if (!Sheeted(player))
                return;
            // The core stores current health too, but it restores it against whatever
            // max is in place at that moment, so it is not a reliable record of D3 Life.
            // Stats own Life: current_life plus max_life in the same row is the share.
            std::uint32_t const currentLife = player->IsAlive() ? player->GetHealth() : 0;
            std::lock_guard<std::mutex> lock(storeMutex);
            auto found = characters.find(player->GetGUID().GetRawValue());
            if (found == characters.end())
                return;
            auto& state = found->second;
            std::uint32_t const maxLife = static_cast<uint32>(std::clamp(state.sheet.maxLife, 1.0, 4294967295.0));
            state.lifeShare = currentLife > 0 ? std::min(static_cast<double>(currentLife) / maxLife, 1.0) : 0.0;
            // Serialization emits only numeric tokens/spaces, never SQL text or names.
            // Synchronous write preserves logout/relogin ordering; OnPlayerSave has no
            // character transaction argument in the pinned core.
            CharacterDatabase.DirectExecute("INSERT INTO dc_character_stats (guid, level, max_life, current_life, "
                                            "armor, sheet, contributions) VALUES ({}, {}, {}, {}, {}, '{}', '{}') "
                                            "ON DUPLICATE KEY UPDATE level=VALUES(level), max_life=VALUES(max_life), "
                                            "current_life=VALUES(current_life), armor=VALUES(armor), "
                                            "sheet=VALUES(sheet), contributions=VALUES(contributions)",
                                            player->GetGUID().GetRawValue(), state.sheet.level, maxLife, currentLife,
                                            state.sheet[Stat::Armor], Serialize(state.sheet),
                                            Serialize(state.contributions));
        }

        void Load(Player* player)
        {
            if (!basesReady)
                throw std::runtime_error("D3 base table failed validation");
            CharacterStats state;
            if (QueryResult result = CharacterDatabase.Query(
                    "SELECT sheet, contributions, current_life, max_life FROM dc_character_stats WHERE guid={}",
                    player->GetGUID().GetRawValue()))
            {
                state.sheet = DeserializeSheet((*result)[0].Get<std::string>());
                state.contributions = DeserializeContributions((*result)[1].Get<std::string>());
                double const savedLife = (*result)[2].Get<uint32>();
                double const savedMax = (*result)[3].Get<uint32>();
                state.lifeShare = savedLife > 0 && savedMax > 0 ? std::min(savedLife / savedMax, 1.0) : 0.0;
            }
            // Paragon is rebuilt by its login hook; a Temporary buff up at the logout does not come back.
            DropRebuiltSources(state.contributions);
            // Validate and recompute before publishing any state. Base data/level may
            // have changed since the snapshot; saved source contributions survive.
            state.sheet = Calculate(BaseFor(player), state.contributions, blockTuning);
            std::lock_guard<std::mutex> lock(storeMutex);
            characters[player->GetGUID().GetRawValue()] = state;
        }

        // Player::LoadFromDB calls this hook, then UpdateAllStats(), then restores the
        // saved health and powers clamped to the max values that update produced. With
        // the sheet already published here, that clamp is against our max Life and max
        // Fury instead of WoW's; loading at OnPlayerLogin instead is what left every
        // character pinned to WoW's much smaller max health.
        void Preload(Player* player)
        {
            if (!Sheeted(player))
                return;
            try
            {
                Load(player);
            }
            catch (std::exception const& error)
            {
                // OnPlayerLogin retries and kicks if it fails there too.
                LOG_ERROR("server", "D3 stats preload failed for {}: {}", player->GetName(), error.what());
            }
        }

        void Login(Player* player)
        {
            if (!Sheeted(player))
                return;
            try
            {
                std::uint64_t const guid = player->GetGUID().GetRawValue();
                bool loaded;
                {
                    std::lock_guard<std::mutex> lock(storeMutex);
                    loaded = characters.find(guid) != characters.end();
                }
                if (!loaded)
                    Load(player);
                // The weapon is only in its slot by now: OnPlayerLoadFromDB runs before
                // the inventory is read. Until this ran, nothing ever wrote the weapon
                // source, which is why the sheet printed APS=0.
                RefreshWeapon(player);
                StatSheet sheet;
                double share;
                {
                    std::lock_guard<std::mutex> lock(storeMutex);
                    auto const& state = characters.at(guid);
                    sheet = state.sheet;
                    share = state.lifeShare;
                }
                Display(player, sheet);
                // Whatever the core restored was decided against a max that was not
                // final. Set current Life from the saved share of the max we just
                // published; sources that land after this (Paragon) carry it along.
                RestoreLife(player, share);
                // A resource that starts full (class_resources.csv starts_full) is at its maximum on entering the world, whatever the core
                // restored or zeroed (Player::ResetAllPowers sets Runic Power to 0), and one that does not is empty, whatever the core
                // filled (it fills Energy, Player.cpp:2090): login, which is also a new character's first entry.
                // The same for a second resource (the core zeroes Focus at a power reset, Player.cpp:2552).
                for (Resources::Resource const* resource : {SheetOf(player).resource, SheetOf(player).second})
                    if (resource)
                        player->SetPower(Resources::Slot(*resource),
                                         resource->startsFull ? player->GetMaxPower(Resources::Slot(*resource)) : 0);
                Save(player);
                LOG_INFO("server.loading", "[DC stats] Loaded {} at level {} with {}/{} Life", player->GetName(),
                         player->GetLevel(), player->GetHealth(), player->GetMaxHealth());
            }
            catch (std::exception const& error)
            {
                LOG_ERROR("server", "D3 stats login failed for {}: {}", player->GetName(), error.what());
                player->GetSession()->KickPlayer(std::string("Invalid D3 stat data"));
            }
        }

        class StatWorld final : public WorldScript
        {
        public:
            StatWorld()
                : WorldScript("dc_stat_world", {WORLDHOOK_ON_STARTUP})
            {
            }
            void OnStartup() override
            {
                // A base that names no class
                // falls back to the Barbarian's class rules; say so, once.
                SetClassRuleFallbackNotice([](char const* rule)
                {
                    LOG_WARN("server", "D3 stats: a base stat row names no class, so {} came from the "
                                       "Barbarian's rules (dc_numeric_rule) and its main stat defaults to "
                                       "Strength; give the class a class_primary_stats.csv row", rule);
                });
                try
                {
                    // Every class's base sheet in one query, keyed by class.
                    // The rows come
                    // from each class's <class>_base_stats.csv, the main stat
                    // from class_map.csv and the class rules from
                    // class_primary_stats.csv, all through generate_sql.py.
                    QueryResult result = WorldDatabase.Query(
                        "SELECT m.wow_class_id, m.class_id, m.power_type, m.primary_stat, r.class_dr_pct, "
                        "r.all_res_per_int, b.level, b.str, b.dex, b.`int`, b.vit, b.base_life, b.life_per_vit, "
                        "b.base_armor, b.resource_max FROM dc_class_base_stats b "
                        "JOIN dc_class_map m ON m.class_id = b.class_id "
                        "JOIN dc_class_stat_rules r ON r.class_id = b.class_id ORDER BY m.class_id, b.level");
                    if (!result)
                        throw std::runtime_error(
                            "dc_class_base_stats is missing or empty; apply stats_0001_class_base_stats.sql");
                    do
                    {
                        Field* fields = result->Fetch();
                        ClassSheet& cls = classes[fields[0].Get<uint32>()];
                        cls.classId = fields[1].Get<uint32>();
                        // The class's resource comes from the registry; the
                        // table's power_type (class_map.csv) must name the
                        // same slot, which generate_class_resources.py also
                        // checks, so a stale table fails here, not in play.
                        std::string const power = fields[2].Get<std::string>();
                        cls.resource = Resources::Of(cls.classId);
                        cls.second = Resources::Of(cls.classId, Resources::Data::Role::Second);
                        if (!cls.resource)
                            throw std::runtime_error("Class " + std::to_string(cls.classId) +
                                                     " has no class_resources.csv row");
                        if (power != cls.resource->wowPower)
                            throw std::runtime_error("Class power type " + power + " disagrees with class_resources.csv " +
                                                     cls.resource->wowPower);
                        cls.mainStat = MainStatNamed(fields[3].Get<std::string>());
                        BaseStats base;
                        base.classDRPct = fields[4].Get<double>();
                        base.allResPerInt = fields[5].Get<double>();
                        base.mainStat = cls.mainStat;
                        base.level = fields[6].Get<uint32>();
                        base.strength = static_cast<double>(fields[7].Get<uint32>());
                        base.dexterity = static_cast<double>(fields[8].Get<uint32>());
                        base.intelligence = static_cast<double>(fields[9].Get<uint32>());
                        base.vitality = static_cast<double>(fields[10].Get<uint32>());
                        base.baseLife = static_cast<double>(fields[11].Get<uint32>());
                        base.lifePerVitality = static_cast<double>(fields[12].Get<uint32>());
                        base.baseArmor = static_cast<double>(fields[13].Get<uint32>());
                        base.maxFury = static_cast<double>(fields[14].Get<uint32>());
                        Calculate(base, {});
                        if (!cls.levels.emplace(base.level, base).second)
                            throw std::runtime_error("Duplicate D3 base level");
                    } while (result->NextRow());
                    for (auto const& [wowClass, cls] : classes)
                    {
                        if (cls.levels.size() != 70)
                            throw std::runtime_error("Expected all 70 D3 base levels for every class");
                        for (unsigned level = 1; level <= 70; ++level)
                            (void) cls.levels.at(level);
                    }
                    if (!CharacterDatabase.Query("SELECT COUNT(*) FROM dc_character_stats"))
                        throw std::runtime_error("dc_character_stats migration has not been applied");
                    // The block model's three numbers. tuned_value is the hand-set value,
                    // d3_value is there for a figure Blizzard never published and
                    // is NULL for all three today; a missing table leaves the
                    // documented model defaults in place and says so.
                    if (QueryResult block = WorldDatabase.Query(
                            "SELECT parameter, COALESCE(tuned_value, d3_value) FROM dc_block_tuning"))
                    {
                        do
                        {
                            Field* row = block->Fetch();
                            if (row[1].IsNull())
                                continue;
                            std::string const parameter = row[0].Get<std::string>();
                            double const value = row[1].Get<double>();
                            if (parameter == "block_chance_base_cap")
                                blockTuning.baseChanceCap = value;
                            else if (parameter == "block_chance_total_cap")
                                blockTuning.totalChanceCap = value;
                            else if (parameter == "block_amount_percent_scale")
                                blockTuning.amountPercentScale = value;
                        } while (block->NextRow());
                    }
                    else
                        LOG_WARN("server.loading",
                                 "[DC stats] dc_block_tuning is missing; using the block.md model "
                                 "defaults. Apply items_0006_block_tuning.sql.");
                    basesReady = true;
                    LOG_INFO("server.loading",
                             "[DC stats] Validated all 70 base levels for {} classes; character persistence ready",
                             classes.size());
                }
                catch (std::exception const& error)
                {
                    LOG_ERROR("server", "D3 stat startup failed: {}. Logins of every D3 class are disabled.",
                              error.what());
                }
            }
        };

        class StatPlayer final : public PlayerScript
        {
        public:
            StatPlayer()
                : PlayerScript("dc_stat_player",
                               {PLAYERHOOK_ON_LOAD_FROM_DB, PLAYERHOOK_ON_LOGIN, PLAYERHOOK_ON_LOGOUT,
                                PLAYERHOOK_ON_SAVE, PLAYERHOOK_ON_LEVEL_CHANGED, PLAYERHOOK_ON_DELETE_FROM_DB,
                                PLAYERHOOK_ON_AFTER_UPDATE_MAX_HEALTH, PLAYERHOOK_ON_AFTER_UPDATE_MAX_POWER,
                                PLAYERHOOK_ON_AFTER_UPDATE_ATTACK_POWER_AND_DAMAGE, PLAYERHOOK_ON_UPDATE_CRIT_CHANCE,
                                PLAYERHOOK_ON_UPDATE_SPELL_CRIT_CHANCE, PLAYERHOOK_ON_EQUIP,
                                PLAYERHOOK_ON_UNEQUIP_ITEM})
            {
            }

            void OnPlayerLoadFromDB(Player* player) override
            {
                Preload(player);
            }
            void OnPlayerLogin(Player* player) override
            {
                Login(player);
            }
            // Stock equipment updates overwrite display fields, and a weapon swap moves
            // the sheet's own APS. Both fire after the slot has changed, so re-reading
            // the weapon here and recomputing restores the display as well.
            void OnPlayerEquip(Player* player, Item*, uint8, uint8, bool) override
            {
                RefreshWeapon(player);
            }
            void OnPlayerUnequip(Player* player, Item*) override
            {
                RefreshWeapon(player);
            }
            void OnPlayerSave(Player* player) override
            {
                Save(player);
            }
            void OnPlayerLogout(Player* player) override
            {
                Save(player);
                std::lock_guard<std::mutex> lock(storeMutex);
                characters.erase(player->GetGUID().GetRawValue());
            }
            void OnPlayerDeleteFromDB(CharacterDatabaseTransaction trans, uint32 guid) override
            {
                trans->Append("DELETE FROM dc_character_stats WHERE guid={}", guid);
            }
            void OnPlayerLevelChanged(Player* player, uint8) override
            {
                if (Sheeted(player) && !Recompute(player))
                    player->GetSession()->KickPlayer(std::string("D3 stat recomputation failed"));
                else
                    Save(player);
            }
            void OnPlayerAfterUpdateMaxHealth(Player* player, float& value) override
            {
                if (Sheeted(player))
                    if (auto sheet = Get(player->GetGUID().GetRawValue()))
                        value = static_cast<float>(sheet->maxLife);
            }
            void OnPlayerAfterUpdateMaxPower(Player* player, Powers& power, float& value) override
            {
                if (Sheeted(player))
                    if (auto sheet = Get(player->GetGUID().GetRawValue()))
                    {
                        ClassSheet const& cls = SheetOf(player);
                        if (power == Resources::Slot(*cls.resource))
                            value = static_cast<float>(Resources::ToUnits(*cls.resource, (*sheet)[Stat::MaxFury]));
                        // A second resource's slot holds its pool (the core gives a player no Focus at all).
                        else if (cls.second && power == Resources::Slot(*cls.second))
                            value = static_cast<float>(Resources::ToUnits(
                                *cls.second, Resources::Pool::Maximum(cls.second->pool, player->GetGUID().GetRawValue(),
                                                                      (*sheet)[Stat::MaxSecond])));
                        // A class with
                        // no resource on Mana (the Wizard, now on Energy) keeps
                        // no Mana, so the stock second bar stays hidden.
                        else if (Resources::ZeroMaximum(cls.classId, power))
                            value = 0.0f;
                    }
            }
            void OnPlayerAfterUpdateAttackPowerAndDamage(Player* player, float&, float& base, float& modifier,
                                                         float& multiplier, bool) override
            {
                if (Sheeted(player))
                    base = modifier = multiplier = 0;
            }
            void OnPlayerUpdateCritChance(Player* player, WeaponAttackType, float& value) override
            {
                if (!Sheeted(player))
                    return;
                auto sheet = Get(player->GetGUID().GetRawValue());
                value = sheet ? static_cast<float>((*sheet)[Stat::CritChance]) : 5.0f;
            }
            void OnPlayerUpdateSpellCritChance(Player* player, uint32, float& value) override
            {
                OnPlayerUpdateCritChance(player, BASE_ATTACK, value);
            }
        };

        class StatRage final : public UnitScript
        {
        public:
            StatRage()
                : UnitScript("dc_stat_rage", true, {UNITHOOK_CAN_REWARD_RAGE})
            {
            }
            bool CanRewardRage(Unit* unit, uint32, uint32, bool, float&) override
            {
                return !RageResource(unit->ToPlayer());
            }
        };

        class StatCommand final : public CommandScript
        {
        public:
            StatCommand()
                : CommandScript("dc_stat_command")
            {
            }
            Acore::ChatCommands::ChatCommandTable GetCommands() const override
            {
                using namespace Acore::ChatCommands;
                static ChatCommandTable stats = {{"stats", Handle, SEC_GAMEMASTER, Console::No}};
                static ChatCommandTable root = {{"dc", stats}};
                return root;
            }
            static bool Handle(ChatHandler* handler)
            {
                Player* target = handler->getSelectedPlayer();
                if (!Sheeted(target))
                {
                    handler->SendSysMessage("Select a character whose class has a D3 stat sheet.");
                    return false;
                }
                auto sheet = Get(target->GetGUID().GetRawValue());
                if (!sheet)
                {
                    handler->SendSysMessage("D3 stat sheet is not loaded.");
                    return false;
                }
                auto const& s = *sheet;
                auto emit = [&](std::string const& text)
                {
                    handler->SendSysMessage(text);
                    LOG_INFO("server.loading", "[DC stats output] {}", text);
                };
                auto line = [&]()
                {
                    std::ostringstream out;
                    out.imbue(std::locale::classic());
                    out << std::setprecision(10);
                    return out;
                };
                emit("D3 stats: " + target->GetName() + " (level " + std::to_string(s.level) + ")");
                auto a = line();
                a << "Str=" << s[Stat::Strength] << " Dex=" << s[Stat::Dexterity] << " Int=" << s[Stat::Intelligence]
                  << " Vit=" << s[Stat::Vitality];
                emit(a.str());
                auto b = line();
                ClassSheet const& cls = SheetOf(target);
                b << "Life=" << s.maxLife << " Armor=" << s[Stat::Armor]
                  << " Max " << cls.resource->d3Name << "=" << s[Stat::MaxFury];
                emit(b.str());
                auto c = line();
                c << "CHC=" << s[Stat::CritChance] << "% CHD=" << s[Stat::CritDamage]
                  << "% IAS=" << s[Stat::AttackSpeed] << "% Weapon IAS=" << s.weaponIAS
                  << "% APS=" << s.attacksPerSecond;
                emit(c.str());
                auto d = line();
                d << "CDR=" << s[Stat::CooldownReduction] << "% RCR=" << s[Stat::ResourceCostReduction]
                  << "% Area Damage=" << s[Stat::AreaDamage] << "%";
                emit(d.str());
                auto e = line();
                e << "Life/Hit=" << s[Stat::LifePerHit] << " Life/Kill=" << s[Stat::LifePerKill]
                  << " Life Regen=" << s[Stat::LifeRegen] << " Life%=" << s[Stat::LifePercent]
                  << " Move Speed=" << s[Stat::MovementSpeed] << "%";
                emit(e.str());
                auto f = line();
                f << "Thorns=" << s[Stat::Thorns] << " MF=" << s[Stat::MagicFind] << "% GF=" << s[Stat::GoldFind]
                  << "% XP=" << s[Stat::XPBonus] << "% Flat XP=" << s.flatXP
                  << " Gold Pickup Range=" << s[Stat::GoldPickupRange] << " yards";
                emit(f.str());
                auto bl = line();
                bl << "Block Chance=" << s[Stat::BlockChance] << "% (base " << s[Stat::BaseBlockChance]
                   << "%, caps " << blockTuning.baseChanceCap << "/" << blockTuning.totalChanceCap
                   << ") Block Amount=" << s[Stat::BlockAmountMin] << "-" << s[Stat::BlockAmountMax];
                emit(bl.str());
                auto g = line();
                g << "All Res=" << s[Stat::AllResistance] << " Armor DR=" << s.armorDR * 100
                  << "% Class DR=" << s.classDR * 100 << "% Specific DR=" << s[Stat::SpecificReduction] << "% Elite DR=" << s[Stat::EliteReduction] << "%";
                emit(g.str());
                for (unsigned element = 0; element < ElementCount; ++element)
                {
                    auto h = line();
                    h << ElementNames[element] << ": Damage=" << s.elementalDamage[element]
                      << "% Resist=" << s.resistance[element] << " Resist DR=" << s.resistanceDR[element] * 100
                      << "% Reduction=" << s.elementReduction[element] << "% Taken factor=" << s.damageTaken[element];
                    emit(h.str());
                }
                auto i = line();
                i << "Core: MaxHealth=" << target->GetMaxHealth() << " Armor=" << target->GetArmor()
                  << " Max" << cls.resource->wowPower << "=" << Resources::MaxUnits(target, *cls.resource)
                  << " AP=" << target->GetInt32Value(UNIT_FIELD_ATTACK_POWER)
                  << " Crit=" << target->GetFloatValue(PLAYER_CRIT_PERCENTAGE) << "%";
                emit(i.str());
                return true;
            }
        };
    } // namespace

    std::optional<StatSheet> Get(std::uint64_t playerGuid)
    {
        std::lock_guard<std::mutex> lock(storeMutex);
        auto found = characters.find(playerGuid);
        return found == characters.end() ? std::nullopt : std::optional<StatSheet>(found->second.sheet);
    }

    double Sum(std::uint64_t playerGuid, Source source, Stat stat, Element element)
    {
        std::lock_guard<std::mutex> lock(storeMutex);
        auto found = characters.find(playerGuid);
        double total = 0;
        if (found != characters.end())
            for (Contribution const& c : found->second.contributions)
                if (c.source == source && c.stat == stat && c.element == element)
                    total += c.value;
        return total;
    }

    bool AddContribution(std::uint64_t playerGuid, Contribution const& contribution)
    {
        Validate(contribution);
        std::lock_guard<std::mutex> lock(storeMutex);
        auto found = characters.find(playerGuid);
        if (found == characters.end())
            return false;
        DC::SetContribution(found->second, contribution);
        return true;
    }

    std::vector<Contribution> Contributions(std::uint64_t playerGuid)
    {
        std::lock_guard<std::mutex> lock(storeMutex);
        auto found = characters.find(playerGuid);
        return found == characters.end() ? std::vector<Contribution>() : found->second.contributions;
    }

    bool RemoveContribution(std::uint64_t playerGuid, Source source, Stat stat, std::uint64_t id)
    {
        std::lock_guard<std::mutex> lock(storeMutex);
        auto found = characters.find(playerGuid);
        if (found == characters.end())
            return false;
        DC::RemoveContribution(found->second, source, stat, id);
        return true;
    }

    bool Recompute(Player* player)
    {
        if (!Sheeted(player))
            return false;
        try
        {
            StatSheet sheet;
            {
                std::lock_guard<std::mutex> lock(storeMutex);
                auto found = characters.find(player->GetGUID().GetRawValue());
                if (found == characters.end())
                    return false;
                sheet = Calculate(BaseFor(player), found->second.contributions, blockTuning);
                found->second.sheet = sheet;
            }
            Display(player, sheet);
            return true;
        }
        catch (std::exception const& error)
        {
            LOG_ERROR("server", "D3 stat recomputation failed for {}: {}", player->GetName(), error.what());
            return false;
        }
    }

    void RefreshWeapon(Player* player)
    {
        if (!Sheeted(player))
            return;
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        Item* main = player->GetWeaponForAttack(BASE_ATTACK, true);
        Item* off = player->GetWeaponForAttack(OFF_ATTACK, true);
        // 02 §3: weapon base speed comes from the item template (05 I10). Bare
        // handed falls back to the core's own attack time, and to 2 s if that is
        // unset, which is what the old live calculation in combat did.
        double delay =
            main && main->GetTemplate()->Delay ? main->GetTemplate()->Delay : player->GetAttackTime(BASE_ATTACK);
        if (delay <= 0)
            delay = 2000;
        AddContribution(guid, {Source::Items, Stat::WeaponAPS, WEAPON_APS_ID, 1000.0 / delay, Bucket::Flat});
        if (off)
        {
            AddContribution(guid, {Source::Items, Stat::AttackSpeed, DUAL_WIELD_ID, DualWieldIas(), Bucket::Flat});
            // The other hand keeps its own base speed: D3 runs its weapon
            // calculation once per hand (stats_full.js:673-675) and the
            // Whirlwind channel swings them alternately.
            // Bare-handed cannot be an offhand, so the item
            // template's delay is the only source here.
            double offDelay = off->GetTemplate()->Delay;
            if (offDelay <= 0)
                offDelay = player->GetAttackTime(OFF_ATTACK);
            if (offDelay <= 0)
                offDelay = 2000;
            AddContribution(guid, {Source::Items, Stat::OffhandWeaponAPS, WEAPON_APS_ID, 1000.0 / offDelay, Bucket::Flat});
        }
        else
        {
            RemoveContribution(guid, Source::Items, Stat::AttackSpeed, DUAL_WIELD_ID);
            RemoveContribution(guid, Source::Items, Stat::OffhandWeaponAPS, WEAPON_APS_ID);
        }
        Recompute(player);
    }

    // The template and gem portion of one hand's average hit, read exactly as
    // DC::Combat::ComputeHit reads it, with the same 1-2 bare-hand fallback.
    // SheetSummary adds the sheet's flat damage after averaging hands, to show
    // the weapon combat actually swings, not a second opinion about it.
    static double AverageWeaponDamage(Player* player, WeaponAttackType attack)
    {
        Item* weapon = player->GetWeaponForAttack(attack, true);
        double low = 1, high = 2;
        if (weapon)
        {
            ItemTemplate const* proto = weapon->GetTemplate();
            low = proto->Damage[0].DamageMin;
            high = proto->Damage[0].DamageMax;
            if (high <= 0)
            {
                low = 1;
                high = 2;
            }
            // G1: the socketed gem's flat damage on both endpoints plus the weapon's rolled
            // elemental range (its own low/high), before the sheet's flat damage.
            DC::Items::WeaponExtraDamage const extra =
                DC::Items::WeaponExtraDamageOf(player->GetGUID().GetRawValue(), weapon->GetGUID().GetCounter());
            low += extra.low;
            high += extra.high;
        }
        return (low + high) / 2;
    }

    Summary SheetSummary(Player* player)
    {
        if (!Sheeted(player))
            return {};
        auto found = Get(player->GetGUID().GetRawValue());
        if (!found)
            return {};
        // The weapon the player swings; combat reads the same hands (AverageWeaponDamage).
        SummaryInputs in;
        in.averageHit = AverageWeaponDamage(player, BASE_ATTACK);
        if (player->GetWeaponForAttack(OFF_ATTACK, true))
            in.averageHit = (in.averageHit + AverageWeaponDamage(player, OFF_ATTACK)) / 2; // §2.3E average DPH
        in.mainStat = SheetOf(player).mainStat;
        in.multiplier = (1 + DC::Combat::DamageBonus(player) / 100) * DC::Combat::DamageFactor(player);
        return SheetSummaryOf(*found, in);
    }

    bool ReplaceParagon(Player* player, std::vector<Contribution> const& contributions)
    {
        if (!Sheeted(player))
            return false;
        try
        {
            StatSheet sheet;
            {
                std::lock_guard<std::mutex> lock(storeMutex);
                auto found = characters.find(player->GetGUID().GetRawValue());
                if (found == characters.end())
                    return false;
                auto candidate = found->second;
                auto& inputs = candidate.contributions;
                inputs.erase(std::remove_if(inputs.begin(), inputs.end(),
                                            [](Contribution const& c) { return c.source == Source::Paragon; }),
                             inputs.end());
                for (auto const& c : contributions)
                {
                    if (c.source != Source::Paragon)
                        return false;
                    SetContribution(candidate, c);
                }
                sheet = Calculate(BaseFor(player), inputs, blockTuning);
                candidate.sheet = sheet;
                found->second = std::move(candidate);
            }
            Display(player, sheet);
            // A paragon point in Resource Cost Reduction has to reach the
            // aura that charges it, the same as an item does.
            // Outside the lock: it recomputes in turn.
            DC::Combat::Passives::RefreshModifiers(player);
            return true;
        }
        catch (std::exception const& error)
        {
            LOG_ERROR("server", "Paragon stat update failed for {}: {}", player->GetName(), error.what());
            return false;
        }
    }

    void RegisterSustainScripts(); // dc_sustain.cpp
    void RegisterResourcePulseScripts(); // dc_resource_pulse.cpp

    void RegisterScripts()
    {
        new StatWorld();
        new StatPlayer();
        new StatRage();
        new StatCommand();
        RegisterSustainScripts();
        RegisterResourcePulseScripts();
    }
} // namespace DC::Stats
