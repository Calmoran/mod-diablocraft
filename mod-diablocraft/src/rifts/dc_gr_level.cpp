#include "dc_gr_level.h"
#include "dc_gr_unlock.h"
#include "dc_rifts.h"

#include "../common/dc_tunables.h"
#include "../hardcore/dc_hardcore.h"

#include "Chat.h"
#include "DatabaseEnv.h"
#include "Player.h"
#include "ScriptMgr.h"

#include <algorithm>
#include <string>

namespace DC::Rifts
{
    namespace
    {
        unsigned Level(char const* name)
        {
            return static_cast<unsigned>(Tunables::Get("rifts", name));
        }

        // Constant: the rows of the unlock chart (greater_rifts.csv keystone_upgrade_rule: +1 to +10).
        constexpr unsigned UnlockRows = 10;

        // The row's mode: the character's own, the realm's while it has none (11-hardcore H4).
        char const* ModeKey(std::uint32_t guid)
        {
            Hardcore::Mode mode = Hardcore::ModeOf(guid);
            if (mode == Hardcore::Mode::Unchosen)
                mode = Hardcore::RealmMode();
            return mode == Hardcore::Mode::Hardcore ? "hardcore" : "normal";
        }

        // The account's best solo level, which caps its Blood Shards (kadala.md 4.2). It only ever
        // rises, and it stays when the character is deleted, unlike its dc_character_gr row.
        void RaiseAccountSolo(std::uint32_t guid, unsigned level)
        {
            if (level)
                CharacterDatabase.DirectExecute(
                    "INSERT INTO dc_account_gr_solo (account_id,mode,beaten_solo) SELECT account,'{}',{} FROM characters "
                    "WHERE guid={} ON DUPLICATE KEY UPDATE beaten_solo=GREATEST(beaten_solo,VALUES(beaten_solo))",
                    ModeKey(guid), level, guid);
        }
    } // namespace

    GrLevels GreaterRiftLevels(std::uint32_t guid)
    {
        unsigned const start = Level("greater_rift_start_level");
        unsigned const cap = Level("greater_rift_max_level");
        GrLevels levels;
        levels.unlocked = start;
        if (auto row = CharacterDatabase.Query(
                "SELECT unlocked, beaten FROM dc_character_gr WHERE guid={} AND mode='{}'", guid, ModeKey(guid)))
        {
            levels.unlocked = std::max(start, std::min<unsigned>((*row)[0].Get<uint16>(), cap));
            levels.beaten = std::min<unsigned>((*row)[1].Get<uint16>(), levels.unlocked);
        }
        return levels;
    }

    bool SetGreaterRiftLevels(std::uint32_t guid, unsigned unlocked, unsigned beaten, std::string& error)
    {
        unsigned const start = Level("greater_rift_start_level");
        unsigned const cap = Level("greater_rift_max_level");
        if (unlocked < start || unlocked > cap)
        {
            error = "unlocked must be " + std::to_string(start) + " to " + std::to_string(cap);
            return false;
        }
        if (beaten > unlocked)
        {
            error = "beaten cannot be above unlocked";
            return false;
        }
        CharacterDatabase.DirectExecute(
            "INSERT INTO dc_character_gr (guid,mode,unlocked,beaten) VALUES ({},'{}',{},{}) "
            "ON DUPLICATE KEY UPDATE unlocked=VALUES(unlocked),beaten=VALUES(beaten)",
            guid, ModeKey(guid), unlocked, beaten);
        return true;
    }

    unsigned GreaterRiftBeatenSolo(std::uint32_t guid)
    {
        if (auto row = CharacterDatabase.Query("SELECT beaten_solo FROM dc_character_gr WHERE guid={} AND mode='{}'", guid,
                                               ModeKey(guid)))
            return (*row)[0].Get<uint16>();
        return 0;
    }

    unsigned AccountGreaterRiftBeatenSolo(std::uint32_t guid)
    {
        if (auto row = CharacterDatabase.Query(
                "SELECT COALESCE((SELECT s.beaten_solo FROM dc_account_gr_solo s JOIN characters c ON c.account=s.account_id "
                "WHERE c.guid={} AND s.mode='{}'),0)",
                guid, ModeKey(guid)))
            return (*row)[0].Get<uint32>();
        return 0;
    }

    GrUnlock RecordGreaterRiftBeaten(std::uint32_t guid, unsigned level, unsigned secondsLeft, bool solo)
    {
        // The chart: ten rows, each the seconds a kill must still have left for that bonus. A row that
        // is missing or blank is out of reach, so a half-loaded sheet grants less, never more.
        unsigned minSeconds[UnlockRows];
        for (unsigned i = 0; i < UnlockRows; ++i)
        {
            std::string const name = "gr_unlock_plus_" + std::to_string(i + 1) + "_min_seconds_left";
            minSeconds[i] = Tunables::Has("rifts", name) ? static_cast<unsigned>(Tunables::Get("rifts", name)) : ~0u;
        }
        GrUnlock done;
        done.before = GreaterRiftLevels(guid);
        Gr::Reach const reach = Gr::Beat({done.before.unlocked, done.before.beaten, GreaterRiftBeatenSolo(guid)}, level,
                                         Gr::UnlockBonus(secondsLeft, minSeconds, UnlockRows), solo,
                                         Level("greater_rift_max_level"));
        done.after = {reach.unlocked, reach.beaten};
        // GREATEST per column: the write only ever raises, so a retry or a second member's call for the
        // same character cannot undo or double anything.
        CharacterDatabase.DirectExecute(
            "INSERT INTO dc_character_gr (guid,mode,unlocked,beaten,beaten_solo) VALUES ({},'{}',{},{},{}) "
            "ON DUPLICATE KEY UPDATE unlocked=GREATEST(unlocked,VALUES(unlocked)),beaten=GREATEST(beaten,VALUES(beaten)),"
            "beaten_solo=GREATEST(beaten_solo,VALUES(beaten_solo))",
            guid, ModeKey(guid), reach.unlocked, reach.beaten, reach.beatenSolo);
        RaiseAccountSolo(guid, reach.beatenSolo);
        return done;
    }

    namespace
    {
        class GrLevelPlayer final : public PlayerScript
        {
        public:
            GrLevelPlayer()
                : PlayerScript("dc_gr_level_player")
            {
            }
            void OnPlayerDeleteFromDB(CharacterDatabaseTransaction trans, uint32 guid) override
            {
                trans->Append("DELETE FROM dc_character_gr WHERE guid={}", guid);
            }
        };

        // A hand way to move the numbers, for testing; the run writes them in play.
        class GrLevelCommand final : public CommandScript
        {
        public:
            GrLevelCommand()
                : CommandScript("dc_gr_level_command")
            {
            }
            Acore::ChatCommands::ChatCommandTable GetCommands() const override
            {
                using namespace Acore::ChatCommands;
                static ChatCommandTable gr = {
                    {"set", HandleSet, SEC_ADMINISTRATOR, Console::No},
                    {"solo", HandleSolo, SEC_ADMINISTRATOR, Console::No},
                    {"", HandleShow, SEC_GAMEMASTER, Console::No},
                };
                static ChatCommandTable dc = {{"gr", gr}};
                static ChatCommandTable root = {{"dc", dc}};
                return root;
            }

            // `.dc gr` on the selected character, or on the GM's own when nothing is selected.
            static bool HandleShow(ChatHandler* handler)
            {
                Player* player = handler->getSelectedPlayerOrSelf();
                if (!player)
                    return false;
                GrLevels const levels = GreaterRiftLevels(player->GetGUID().GetCounter());
                handler->PSendSysMessage("{}: Greater Rift unlocked {}, beaten {}, beaten solo {} (0 is none).", player->GetName(),
                                         levels.unlocked, levels.beaten, GreaterRiftBeatenSolo(player->GetGUID().GetCounter()));
                return true;
            }

            // `.dc gr solo <level>`: the highest level beaten alone, for testing Torment VII to XVI before a
            // character can earn it. Unlocked and beaten stay as they are.
            static bool HandleSolo(ChatHandler* handler, unsigned level)
            {
                Player* player = handler->getSelectedPlayerOrSelf();
                if (!player)
                    return false;
                if (level > Level("greater_rift_max_level"))
                {
                    handler->PSendSysMessage("Not set: solo must be 0 to {}.", Level("greater_rift_max_level"));
                    return false;
                }
                std::uint32_t const guid = player->GetGUID().GetCounter();
                GrLevels const levels = GreaterRiftLevels(guid);
                CharacterDatabase.DirectExecute(
                    "INSERT INTO dc_character_gr (guid,mode,unlocked,beaten,beaten_solo) VALUES ({},'{}',{},{},{}) "
                    "ON DUPLICATE KEY UPDATE beaten_solo=VALUES(beaten_solo)",
                    guid, ModeKey(guid), levels.unlocked, levels.beaten, level);
                RaiseAccountSolo(guid, level);
                return HandleShow(handler);
            }

            // `.dc gr set <unlocked> <beaten>`
            static bool HandleSet(ChatHandler* handler, unsigned unlocked, unsigned beaten)
            {
                Player* player = handler->getSelectedPlayerOrSelf();
                if (!player)
                    return false;
                std::string error;
                if (!SetGreaterRiftLevels(player->GetGUID().GetCounter(), unlocked, beaten, error))
                {
                    handler->PSendSysMessage("Not set: {}.", error);
                    return false;
                }
                return HandleShow(handler);
            }
        };
    } // namespace

    void RegisterGreaterRiftLevelScripts()
    {
        new GrLevelPlayer();
        new GrLevelCommand();
    }
} // namespace DC::Rifts
