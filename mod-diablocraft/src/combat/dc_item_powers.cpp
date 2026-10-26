#include "dc_item_powers_internal.h"

// The item powers' engine: the table the sheets render, each player's worn items, set counts and Cube choices, the equip refresh, and the scripts' registration.

namespace DC::Combat::ItemPowers
{
    namespace
    {
        // N-CTF: ItemPower::CreatureTypes names the core's creature types by their numbers.
        static_assert(CREATURE_TYPE_BEAST == 1 && CREATURE_TYPE_DRAGONKIN == 2 && CREATURE_TYPE_DEMON == 3 && CREATURE_TYPE_ELEMENTAL == 4 &&
                          CREATURE_TYPE_GIANT == 5 && CREATURE_TYPE_UNDEAD == 6 && CREATURE_TYPE_HUMANOID == 7 && CREATURE_TYPE_CRITTER == 8 &&
                          CREATURE_TYPE_MECHANICAL == 9 && CREATURE_TYPE_NOT_SPECIFIED == 10 && CREATURE_TYPE_TOTEM == 11 &&
                          CREATURE_TYPE_NON_COMBAT_PET == 12 && CREATURE_TYPE_GAS_CLOUD == 13,
                      "ItemPower::CreatureTypes follows the core's creature type numbers");
    } // namespace
} // namespace DC::Combat::ItemPowers

namespace DC::Combat
{
    namespace Detail
    {
        Table const& Data()
        {
            static Table const table = []
            {
                Table loaded;
                if (QueryResult found = WorldDatabase.Query("SELECT owner, pieces, kind, skill, stat, value_min, value_max, cond, cond_arg, cond_skills, stack_seconds, stack_max, fire_on, fire_skills, chance_pct, icd_seconds FROM dc_legendary_power"))
                    do
                    {
                        Field* f = found->Fetch();
                        ItemPower::Row row{f[0].Get<std::string>(), f[1].Get<std::uint32_t>(), f[2].Get<std::string>(),
                                           f[3].Get<std::string>(), f[4].Get<std::string>(), f[5].Get<double>(),
                                           f[6].Get<double>(), f[7].Get<std::string>(), f[8].Get<double>(), {},
                                           f[10].Get<double>(), f[11].Get<std::uint32_t>()};
                        auto split = [](std::string const& list, std::vector<std::string>& out)
                        {
                            for (std::size_t from = 0, to; from < list.size(); from = to + 1)
                            {
                                to = list.find(';', from);
                                if (to == std::string::npos)
                                    to = list.size();
                                out.push_back(list.substr(from, to - from));
                            }
                        };
                        split(f[9].Get<std::string>(), row.condSkills);
                        row.fireOn = f[12].Get<std::string>();
                        split(f[13].Get<std::string>(), row.fireSkills);
                        row.chancePct = f[14].Get<double>();
                        row.icdSeconds = f[15].Get<double>();
                        if (!row.fireOn.empty())
                            loaded.events.insert(row.fireOn);
                        loaded.controls = loaded.controls || row.fireOn.rfind("control_", 0) == 0;
                        loaded.prevents = loaded.prevents || row.stat == "damage_prevented_pct";
                        loaded.still = loaded.still || row.cond == "standing_still";
                        loaded.impaired = loaded.impaired || (row.kind == "player" && row.stat == "damage_vs_impaired_pct");
                        loaded.blockReduction = loaded.blockReduction || (row.kind == "player" && row.stat == "damage_reduction_of_block_pct");
                        loaded.speed = loaded.speed || (row.kind == "player" && row.stat == "movement_speed_pct");
                        loaded.stunned = loaded.stunned || row.stat == "damage_reduction_per_stunned_pct";
                        loaded.marks = loaded.marks || row.cond == "first_hit_on_target";
                        loaded.enemyStacks = loaded.enemyStacks || row.stat == "damage_per_enemy_hit_pct";
                        loaded.vitalityThorns = loaded.vitalityThorns || row.stat == "thorns_per_vitality_pct";
                        loaded.moves = loaded.moves || row.cond == "moving" || row.cond == "not_moving";
                        if (row.cond == "skills_active")
                            loaded.watched.insert(row.condSkills.begin(), row.condSkills.end());
                        loaded.resource = loaded.resource || row.cond == "resource_above" || row.stat == "damage_by_missing_resource_pct";
                        loaded.life = loaded.life || row.cond == "life_missing" || row.cond == "own_life_below";
                        loaded.quietCost = loaded.quietCost || row.stat == "resource_cost_reduction_pct";
                        loaded.missingRegen = loaded.missingRegen || row.stat == "life_regen_by_missing_pct";
                        loaded.rows.push_back(std::move(row));
                    } while (found->NextRow());
                if (QueryResult found = WorldDatabase.Query("SELECT entry, set_name, d3_name FROM dc_base_item WHERE set_name <> ''"))
                    do
                    {
                        Field* f = found->Fetch();
                        loaded.pieces[f[0].Get<std::uint32_t>()] = {f[1].Get<std::string>(), f[2].Get<std::string>()};
                    } while (found->NextRow());
                if (QueryResult found = WorldDatabase.Query("SELECT entry, d3_id, d3_name, rarity, pool_version, usable_by, designated_class FROM dc_base_item"))
                {
                    std::vector<ItemPower::BaseItem> items;
                    std::vector<std::pair<std::uint32_t, std::string>> entries;
                    std::vector<std::pair<std::string, std::string>> classes;
                    do
                    {
                        Field* f = found->Fetch();
                        entries.emplace_back(f[0].Get<std::uint32_t>(), f[1].Get<std::string>());
                        classes.emplace_back(f[5].Get<std::string>(), f[6].Get<std::string>());
                        items.push_back({f[1].Get<std::string>(), f[2].Get<std::string>(), f[3].Get<std::string>(), f[4].Get<std::string>() == "yes"});
                    } while (found->NextRow());
                    loaded.ids = ItemPower::PowerIds(items);
                    for (std::size_t at = 0; at < entries.size(); ++at)
                    {
                        std::uint32_t const entry = entries[at].first;
                        std::string const powerId = ItemPower::PowerId(loaded.ids, entries[at].second);
                        if (items[at].pool)
                            loaded.poolClass[items[at].id] = classes[at];
                        if (!ItemPower::Built(loaded.rows, powerId))
                            continue;
                        loaded.owners[entry] = powerId;
                        if (std::any_of(loaded.rows.begin(), loaded.rows.end(), [&](ItemPower::Row const& row)
                                        { return row.owner == powerId && !row.pieces && row.kind != "stat"; }))
                            loaded.sweep.insert(entry);
                    }
                }
                if (QueryResult found = WorldDatabase.Query("SELECT DISTINCT slot FROM dc_cube_slot_item ORDER BY slot"))
                    do
                        loaded.cubeSlots.push_back(found->Fetch()[0].Get<std::uint32_t>());
                    while (found->NextRow());
                LOG_INFO("server.loading", "[DC item powers] {} power row(s), {} set piece(s), {} item(s) with an item-owned power",
                         loaded.rows.size(), loaded.pieces.size(), loaded.owners.size());
                return loaded;
            }();
            return table;
        }

        std::mutex mutex;

        std::unordered_map<std::uint64_t, std::map<std::string, unsigned>> counts; // player guid -> set -> worn pieces

        std::unordered_map<std::uint64_t, Clock> clocks;

        std::unordered_map<std::uint64_t, std::map<std::uint64_t, std::vector<ItemPower::Value>>> worn; // player guid -> item guid -> its powers

        std::unordered_map<std::uint64_t, std::map<std::uint64_t, bool>> legendaries; // player guid -> worn Legendary or Set item guid -> Ancient or Primal

        std::unordered_map<std::uint64_t, std::map<std::string, Window>> windows; // player guid -> skill -> its open window

        std::unordered_map<std::uint64_t, std::set<std::string>> immune;               // player guid -> the immunities put on the unit

        std::unordered_map<std::uint64_t, std::map<unsigned, ItemPower::Cubed>> cubes; // player guid -> Cube slot (one of Data().cubeSlots) -> the power chosen in it

        // Arreat's Law: the players whose resource maximum carries the item's extra points now, as a Temporary contribution of this
        // id (an item's affix ids are its guid << 16 | seq, a Cube slot's 256..65535, the weapon's 1 and 2: none can reach 1 << 62).
        std::set<std::uint64_t> raised;

        // Kekegi's Unbreakable Spirit: when each player's window of free abilities ends (server clock), and the id of its
        // Temporary Resource Cost Reduction (beside OverCapId, out of every affix id's reach).
        std::unordered_map<std::uint64_t, std::uint32_t> costFree;

        // The powers chosen in the Cube, in slot order. Called with `mutex` held.
        std::vector<ItemPower::Cubed> CubedOf(std::uint64_t guid)
        {
            std::vector<ItemPower::Cubed> out;
            if (auto mine = cubes.find(guid); mine != cubes.end())
                for (auto const& slot : mine->second)
                    out.push_back(slot.second);
            return out;
        }

        // What a condition reads of the player's own state: the watched skills that are active and the primary resource's percent.
        // Taken before `mutex`, because the summons answer under a lock of their own. Nothing is looked at that no row reads.
        ItemPower::Situation Seen(Player const* player)
        {
            ItemPower::Situation situation;
            if (Data().watched.empty() && !Data().resource && !Data().life && !Data().moves)
                return situation;
            {
                // Nothing worn that owns a power and no set piece: no row is in play for this player, so nothing is looked at
                // (the readers and the hit events run for every hit of every player).
                std::lock_guard<std::mutex> lock(mutex);
                std::uint64_t const guid = player->GetGUID().GetRawValue();
                if (!clocks.count(guid) && !counts.count(guid))
                    return situation;
            }
            for (std::string const& skill : Data().watched)
                if (SkillIsActive(player, skill))
                    situation.active.insert(skill);
            if (Data().resource)
                if (Resources::Resource const* resource = Resources::Of(Classes::ClassIdOf(player)))
                    if (std::uint32_t const most = Resources::MaxUnits(player, *resource))
                        situation.resourcePct = 100.0 * Resources::Units(player, *resource) / most;
            // N-MOVE: whether the player is moving now, at the moment the number is read.
            if (Data().moves)
                situation.moving = player->isMoving();
            // The player's Life now, at the moment the number is read (a hit taken reads it before the hit lands), never kept from an earlier one.
            if (Data().life && player->GetMaxHealth())
                situation.lifePct = 100.0 * player->GetHealth() / player->GetMaxHealth();
            return situation;
        }

        // What a condition reads, for one player now, on top of what Seen took of the player. Called with `mutex` held.
        ItemPower::Situation SituationOf(std::uint64_t guid, ItemPower::Situation situation)
        {
            situation.now = getMSTime();
            situation.hitPlace = HitPlace();
            situation.castEnemies = CastEnemies();
            if (auto mine = clocks.find(guid); mine != clocks.end())
            {
                situation.channels = mine->second.channels;
                situation.hurt = mine->second.hurt;
                situation.lastHurt = mine->second.lastHurt;
                situation.wornSince = mine->second.wornSince;
                situation.fired = mine->second.fired;
                situation.stillTracked = mine->second.stillTracked;
                situation.stillSince = mine->second.stillSince;
                situation.stunnedNear = mine->second.stunnedNear;
                situation.elementWindow = ItemPower::WindowOn(mine->second.elements, situation.now);
            }
            if (auto items = worn.find(guid); items != worn.end())
                for (auto const& [itemGuid, values] : items->second)
                    for (ItemPower::Value const& value : values)
                        situation.itemValues[value.owner].push_back(value);
            // The Cube is the second source: a cubed power that is not worn joins the situation, so every reader below takes it unchanged
            ItemPower::AddCubed(situation, Data().rows, CubedOf(guid));
            return situation;
        }

        // The set counts of one player (empty before the first set piece is worn). Called with `mutex` held.
        std::map<std::string, unsigned> const& CountsOf(std::uint64_t guid)
        {
            static std::map<std::string, unsigned> const none;
            auto mine = counts.find(guid);
            return mine == counts.end() ? none : mine->second;
        }
    } // namespace Detail
} // namespace DC::Combat

namespace DC::Combat::ItemPowers
{
    namespace
    {
        // The d3_ids of the worn, unbroken items that own a power row, the changed item taken out or put in by hand.
        std::set<std::string> WornOwners(Player* player, Item* changed, bool equipping)
        {
            auto const& owners = Data().owners;
            std::set<std::string> owned;
            auto add = [&](Item* item)
            {
                if (auto found = owners.find(item->GetEntry()); found != owners.end())
                    owned.insert(found->second);
            };
            for (std::uint8_t slot = EQUIPMENT_SLOT_START; slot < EQUIPMENT_SLOT_END; ++slot)
                if (Item* item = player->GetItemByPos(INVENTORY_SLOT_BAG_0, slot); item && item != changed && !item->IsBroken())
                    add(item);
            if (equipping)
                add(changed);
            return owned;
        }

        // The worn set pieces, the changed item taken out or put in by hand: the equip hooks run before or after the
        // core moves the item, so the slot is never trusted for it. A broken item counts for nothing, as in
        // Items::Apply.
        std::vector<ItemPower::Piece> Worn(Player* player, Item* changed, bool equipping)
        {
            auto const& pieces = Data().pieces;
            std::vector<ItemPower::Piece> worn;
            auto add = [&](Item* item)
            {
                if (auto found = pieces.find(item->GetEntry()); found != pieces.end())
                    worn.push_back(found->second);
            };
            for (std::uint8_t slot = EQUIPMENT_SLOT_START; slot < EQUIPMENT_SLOT_END; ++slot)
                if (Item* item = player->GetItemByPos(INVENTORY_SLOT_BAG_0, slot); item && item != changed && !item->IsBroken())
                    add(item);
            if (equipping)
                add(changed);
            return worn;
        }

        // `.dc setcount`: the GM's look at the counter.
        bool HandleSetCount(ChatHandler* handler)
        {
            Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
            if (!player)
            {
                handler->SendSysMessage("This command needs a player.");
                return false;
            }
            std::map<std::string, unsigned> mine;
            {
                std::lock_guard<std::mutex> lock(mutex);
                mine = counts[player->GetGUID().GetRawValue()];
            }
            if (mine.empty())
                handler->SendSysMessage("No set piece worn.");
            for (auto const& [set, worn] : mine)
            {
                handler->PSendSysMessage("{}: {} worn", set, worn);
                for (unsigned level : {2u, 3u, 4u, 6u})
                    if (std::any_of(Data().rows.begin(), Data().rows.end(),
                                    [&](ItemPower::Row const& row) { return row.owner == set && row.pieces == level; }))
                        handler->PSendSysMessage("  ({}) {}", level, BonusActive(player, set, level) ? "active" : "inactive");
            }
            return true;
        }

        class SetCountCommand final : public CommandScript
        {
        public:
            SetCountCommand() : CommandScript("dc_set_count_command") { }
            Acore::ChatCommands::ChatCommandTable GetCommands() const override
            {
                using namespace Acore::ChatCommands;
                static ChatCommandTable dc = {{"setcount", HandleSetCount, SEC_ADMINISTRATOR, Console::No}};
                static ChatCommandTable root = {{"dc", dc}};
                return root;
            }
        };

        // The Cube's choice changed: the powers in play are not the worn items' alone, so what Refresh puts on the unit is redone.
        void CubeChanged(Player* player)
        {
            Immunize(player);
            CostAuras(player);
            DropStacks(player);
        }

        class Cache final : public PlayerScript
        {
        public:
            Cache() : PlayerScript("dc_item_powers_cache", {PLAYERHOOK_ON_BEFORE_LOGOUT, PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_CREATURE_KILL, PLAYERHOOK_ON_UPDATE}) { }
            // N-CLOCK: the `tick` event on every update; a tick row's icd_seconds is its period (ItemPower::Fire's internal
            // cooldown), so it fires once per period while it is worn. Fire returns at once when no row listens for `tick`.
            // ponytail: Fire on every update of a wearer; an accumulator per player if a profile ever shows it.
                NoDamageCost(player);
                MissingLifeRegen(player);
            void OnPlayerUpdate(Player* player, std::uint32_t) override
            {
                Fire(player, "tick", "", 1.0);
                StandStill(player);
                StunScan(player);
                VitalityThorns(player);
                MovementSpeed(player);
            }
            // The elite test the loot and the damage formula use: a native elite, or a rift champion or rare pack's leader (its members are not).
            void OnPlayerCreatureKill(Player* killer, Creature* killed) override
            {
                if (!killer || !killed)
                    return;
                Fire(killer, "kill", "", 1.0, killed);
                if (killed->isElite() || DC::Rifts::IsPromotedElite(killed))
                    Fire(killer, "kill_elite", "", 1.0, killed);
            }
            void OnPlayerBeforeLogout(Player* player) override
            {
                ReuseLogout(player);
            }
            void OnPlayerLogout(Player* player) override
            {
                std::lock_guard<std::mutex> lock(mutex);
                ItemTrail::Clear(player->GetGUID().GetRawValue());
                windows.erase(player->GetGUID().GetRawValue());
                counts.erase(player->GetGUID().GetRawValue());
                clocks.erase(player->GetGUID().GetRawValue());
                worn.erase(player->GetGUID().GetRawValue());
                legendaries.erase(player->GetGUID().GetRawValue());
                immune.erase(player->GetGUID().GetRawValue());
                cubes.erase(player->GetGUID().GetRawValue());
                raised.erase(player->GetGUID().GetRawValue());
                costFree.erase(player->GetGUID().GetRawValue());
            }
        };
    } // namespace
} // namespace DC::Combat::ItemPowers

namespace DC::Combat::ItemPowers
{
    void Refresh(Player* player, Item* changed, bool equipping, Items::Instance const& instance)
    {
        // Only a set piece can change a count, and only an item that owns a power row can change what is worn.
        if (!player || !changed)
            return;
        // Legacy of Dreams counts every worn Legendary or Set item (an Ancient twice from its rank 25), whether or not it owns a power.
        if (DC::Quality::Eligible(instance.rarity))
        {
            std::lock_guard<std::mutex> lock(mutex);
            auto& mine = legendaries[player->GetGUID().GetRawValue()];
            if (equipping)
                mine[changed->GetGUID().GetCounter()] = DC::Quality::Clean(instance.qualityTier) != "normal";
            else
                mine.erase(changed->GetGUID().GetCounter());
        }
        bool const setPiece = Data().pieces.count(changed->GetEntry()) != 0, owner = Data().owners.count(changed->GetEntry()) != 0;
        if (!setPiece && !owner)
            return;
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        if (setPiece)
        {
            auto const now = ItemPower::CountSets(Worn(player, changed, equipping));
            std::lock_guard<std::mutex> lock(mutex);
            counts[guid] = now;
        }
        if (owner)
        {
            // An item with an item-owned power gives its numbers while it is worn and unbroken (Items::Apply passes equipping false for a
            // broken one): its stored rolls are read here, once, so the hit path reads a map.
            std::vector<ItemPower::Stored> stored;
            for (Items::Affix const& affix : instance.affixes)
                if (affix.kind == "power")
                    stored.push_back({affix.affixId, affix.value});
            auto values = ItemPower::WornValues(Data().rows, Data().owners.at(changed->GetEntry()), stored);
            auto const wornNow = WornOwners(player, changed, equipping);
            std::lock_guard<std::mutex> lock(mutex);
            auto& mine = worn[guid];
            if (equipping)
                mine[changed->GetGUID().GetCounter()] = std::move(values);
            else
                mine.erase(changed->GetGUID().GetCounter());
            // The moment each worn item went on, for the conditions that count from it: an item already worn keeps its moment (Refresh runs
            // for each worn item on login and on every change).
            std::map<std::string, std::uint32_t>& since = clocks[guid].wornSince;
            for (auto it = since.begin(); it != since.end();)
                it = wornNow.count(it->first) ? std::next(it) : since.erase(it);
            for (std::string const& id : wornNow)
                since.emplace(id, getMSTime());
        }
        Immunize(player);
        CostAuras(player);
        DropStacks(player);
    }

    std::vector<double> WornRolls(Player const* player, std::string const& skill, std::string const& stat)
    {
        std::lock_guard<std::mutex> lock(mutex);
        auto mine = player ? worn.find(player->GetGUID().GetRawValue()) : worn.end();
        return mine == worn.end() ? std::vector<double>{} : ItemPower::WornRolls(mine->second, skill, stat);
    }

    unsigned SetCount(Player const* player, std::string const& set)
    {
        std::lock_guard<std::mutex> lock(mutex);
        auto mine = player ? counts.find(player->GetGUID().GetRawValue()) : counts.end();
        if (mine == counts.end())
            return 0;
        auto found = mine->second.find(set);
        return found == mine->second.end() ? 0 : found->second;
    }

    bool BonusActive(Player const* player, std::string const& set, unsigned pieces)
    {
        return ItemPower::BonusActive(Data().rows, set, pieces, SetCount(player, set));
    }

    std::vector<std::pair<unsigned, ItemPower::Row>> SetStats(Player const* player)
    {
        std::map<std::string, unsigned> worn;
        {
            std::lock_guard<std::mutex> lock(mutex);
            if (auto mine = player ? counts.find(player->GetGUID().GetRawValue()) : counts.end(); mine != counts.end())
                worn = mine->second;
        }
        return ItemPower::SetStats(Data().rows, worn);
    }

    Legendaries WornLegendaries(Player const* player)
    {
        Legendaries out;
        if (!player)
            return out;
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        std::lock_guard<std::mutex> lock(mutex);
        if (auto mine = legendaries.find(guid); mine != legendaries.end())
            for (auto const& [itemGuid, ancient] : mine->second)
            {
                ++out.items;
                out.ancients += ancient ? 1 : 0;
            }
        out.setBonusOn = ItemPower::AnySetBonus(CountsOf(guid));
        return out;
    }

    unsigned& HitPlace()
    {
        thread_local unsigned place = 0;
        return place;
    }

    unsigned& CastEnemies()
    {
        thread_local unsigned count = 0;
        return count;
    }

    std::vector<ItemPower::Row> ItemStats(std::string const& d3Id)
    {
        return ItemPower::StatsOf(Data().rows, Data().ids, d3Id);
    }

    bool HasItemPower(std::uint32_t entry)
    {
        return Data().sweep.count(entry) != 0;
    }

    std::vector<ItemPower::Row> ItemRows(std::string const& d3Id)
    {
        return ItemPower::RowsOf(Data().rows, Data().ids, d3Id);
    }

    std::string PowerIdOf(std::string const& d3Id)
    {
        return ItemPower::PowerId(Data().ids, d3Id);
    }

    bool Built(std::string const& powerId)
    {
        return ItemPower::Built(Data().rows, PowerIdOf(powerId));
    }

    bool ClassMayChoose(Player const* player, std::string const& powerId)
    {
        auto const found = Data().poolClass.find(PowerIdOf(powerId));
        if (!player || found == Data().poolClass.end())
            return false;
        return RollClass::Eligible(found->second.first, found->second.second, Items::ClassKeyOf(player->getClass()));
    }

    bool CubeSet(Player* player, unsigned slot, std::string const& powerId)
    {
        if (!player || !ItemPower::CubeSlotExists(Data().cubeSlots, slot) || !Built(powerId) || !ClassMayChoose(player, powerId))
            return false;
        std::string const id = PowerIdOf(powerId);
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        {
            std::lock_guard<std::mutex> lock(mutex);
            clocks[guid]; // a chosen power puts the player in play: Seen and Fire skip a player with no clock and no set count
            ItemPower::Cubed& one = cubes[guid][slot];
            if (one.id != id)
                one = {id, getMSTime()};
        }
        CubeChanged(player);
        return true;
    }

    void CubeClear(Player* player, unsigned slot)
    {
        if (!player)
            return;
        {
            std::lock_guard<std::mutex> lock(mutex);
            auto mine = cubes.find(player->GetGUID().GetRawValue());
            if (mine == cubes.end() || !mine->second.erase(slot))
                return;
            if (mine->second.empty())
                cubes.erase(mine);
        }
        CubeChanged(player);
    }

    std::vector<std::string> Cubed(Player const* player)
    {
        std::vector<std::string> out;
        if (!player)
            return out;
        std::lock_guard<std::mutex> lock(mutex);
        for (ItemPower::Cubed const& one : CubedOf(player->GetGUID().GetRawValue()))
            out.push_back(one.id);
        return out;
    }

    std::vector<ItemPower::Active> ActivePowers(Player const* player)
    {
        if (!player)
            return {};
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        std::lock_guard<std::mutex> lock(mutex);
        std::vector<ItemPower::Active> held;
        std::vector<std::string> chosen;
        if (auto mine = clocks.find(guid); mine != clocks.end())
            for (auto const& entry : mine->second.wornSince)
            {
                ItemPower::Active power{entry.first, ItemPower::Source::Worn, {}};
                if (auto items = worn.find(guid); items != worn.end())
                    for (auto const& item : items->second)
                        if (!item.second.empty() && item.second.front().owner == entry.first)
                        {
                            power.values = item.second;
                            break;
                        }
                held.push_back(std::move(power));
            }
        for (ItemPower::Cubed const& one : CubedOf(guid))
            chosen.push_back(one.id);
        return ItemPower::ActivePowers(Data().rows, held, chosen);
    }

    void RegisterScripts()
    {
        new Cache();
        new SetCountCommand();
        RegisterBuffScripts();
        RegisterEventScripts();
        ItemSummons::RegisterScripts();
    }
} // namespace DC::Combat::ItemPowers
