// Stand-ins for the core types the module's gate code touches, with the core's own names
// (Common.h AccountTypes, Config.h GetOption, Player.h, WorldSession.h, ScriptMgr.h's PlayerScript at
// the pin). The module's functions themselves are the patched source's own text, cut out by
// test_gobject_editor.py; nothing of the module is retyped here.
#pragma once
#include <algorithm>
#include <cstdint>
#include <iostream>
#include <map>
#include <string>
#include <vector>

using uint8 = uint8_t;
using uint32 = uint32_t;
using uint64 = uint64_t;

enum AccountTypes
{
    SEC_PLAYER = 0,
    SEC_MODERATOR = 1,
    SEC_GAMEMASTER = 2,
    SEC_ADMINISTRATOR = 3,
    SEC_CONSOLE = 4
};
constexpr uint32 LANG_ADDON = 0xFFFFFFFF;

struct ConfigMgr
{
    std::map<std::string, std::string> values;
    template<typename T>
    T GetOption(char const* key, T def) const
    {
        auto itr = values.find(key);
        if (itr == values.end())
            return def;
        return static_cast<T>(std::stoul(itr->second));
    }
};
extern ConfigMgr g_config;
#define sConfigMgr (&g_config)

struct WorldSession
{
    AccountTypes security = SEC_PLAYER;
    AccountTypes GetSecurity() const
    {
        return security;
    }
};
struct Player
{
    WorldSession* session = nullptr;
    std::string name = "Tester";
    WorldSession* GetSession() const
    {
        return session;
    }
    std::string const& GetName() const
    {
        return name;
    }
};

struct PlayerScript
{
    explicit PlayerScript(char const*) {}
    virtual ~PlayerScript() = default;
    virtual void OnPlayerBeforeSendChatMessage(Player*, uint32&, uint32&, std::string&) {}
    virtual void OnPlayerLogout(Player*) {}
};

#define LOG_INFO(...) (void) 0

// What the module's own code reports to; the driver reads these back.
extern std::vector<std::string> g_payloads;   // SendAddonPayload
extern std::vector<std::string> g_dispatched; // DispatchPayload
extern std::vector<bool> g_cleared;           // ClearEditorSession(notify)
