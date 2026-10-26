// The Lua error drop's core glue (rules in dc_lua_error_drop.h): the three Diablocraft.LuaErrorDrop options, the chat
// hook that appends BugSack's chunks, and the answer to core patch 0025's IsAddonWhisperDrop.
#include "dc_lua_error_drop.h"
#include "Config.h"
#include "Log.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "Timer.h"
#include <atomic>
#include <ctime>

namespace DC::LuaErrorDrop
{
    namespace
    {
        struct Options
        {
            std::string dir;  // blank: off (the live realm)
            std::string name; // blank: every addon whisper is the stock one
            std::uintmax_t cap = 2097152;
        };

        std::mutex optionsMutex;
        Options options;

        Options Current()
        {
            std::lock_guard<std::mutex> guard(optionsMutex);
            return options;
        }

        // Read once at startup and on a config reload, not per message: a missing option logs on every read.
        void Load()
        {
            Options next;
            next.dir = sConfigMgr->GetOption<std::string>("Diablocraft.LuaErrorDrop.Dir", "");
            next.name = sConfigMgr->GetOption<std::string>("Diablocraft.LuaErrorDrop.Name", "Torment");
            next.cap = sConfigMgr->GetOption<uint64>("Diablocraft.LuaErrorDrop.CapBytes", 2097152);
            if (!next.name.empty() && !normalizePlayerName(next.name))
            {
                LOG_ERROR("module",
                          "[DC lua errors] Diablocraft.LuaErrorDrop.Name '{}' is not a player name; no drop name",
                          next.name);
                next.name.clear();
            }
            std::lock_guard<std::mutex> guard(optionsMutex);
            options = next;
        }

        Drop& Files()
        {
            static Drop drop;
            return drop;
        }

        class ConfigScript final : public WorldScript
        {
        public:
            ConfigScript()
                : WorldScript("dc_lua_error_drop_config", {WORLDHOOK_ON_STARTUP, WORLDHOOK_ON_AFTER_CONFIG_LOAD})
            {
            }

            void OnStartup() override
            {
                Load();
            }

            void OnAfterConfigLoad(bool reload) override
            {
                if (reload)
                    Load();
            }
        };

        class ChatScript final : public PlayerScript
        {
        public:
            ChatScript()
                : PlayerScript("dc_lua_error_drop", {PLAYERHOOK_ON_BEFORE_SEND_CHAT_MESSAGE})
            {
            }

            // The hook is void: the whisper still goes on to the chat handler (core patch 0025 quiets the drop name).
            void OnPlayerBeforeSendChatMessage(Player* player, uint32& /*type*/, uint32& lang,
                                               std::string& msg) override
            {
                if (lang != LANG_ADDON || !player || !IsBugSack(msg))
                    return;
                Options const now = Current();
                if (now.dir.empty())
                    return;
                std::tm const local = Acore::Time::TimeBreakdown();
                char date[11];
                char clock[9];
                std::strftime(date, sizeof(date), "%Y-%m-%d", &local);
                std::strftime(clock, sizeof(clock), "%H:%M:%S", &local);
                switch (Files().Append(File(now.dir, date, player->GetName()), Line(clock, msg), now.cap))
                {
                    case Outcome::CapReached:
                        LOG_INFO("module",
                                 "[DC lua errors] {} reached {} bytes for {}; nothing more lands until tomorrow",
                                 player->GetName(), now.cap, date);
                        break;
                    case Outcome::Failed:
                    {
                        static std::atomic<bool> warned{false};
                        if (!warned.exchange(true))
                            LOG_ERROR("module", "[DC lua errors] cannot write under '{}'", now.dir);
                        break;
                    }
                    default:
                        break;
                }
            }
        };

        class WhisperScript final : public GlobalScript
        {
        public:
            WhisperScript()
                : GlobalScript("dc_lua_error_drop_whisper", {GLOBALHOOK_IS_ADDON_WHISPER_DROP})
            {
            }

            bool IsAddonWhisperDrop(std::string const& to) override
            {
                return IsDropName(to, Current().name);
            }
        };
    } // namespace

    void RegisterScripts()
    {
        new ConfigScript();
        new ChatScript();
        new WhisperScript();
    }
} // namespace DC::LuaErrorDrop
