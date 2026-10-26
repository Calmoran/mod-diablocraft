// Runs the patched module's own gate code (gate.inc, cut out of the patched GObjectEditor.cpp) on the cases
// the brief names: the module does nothing with Enable = 0, and a player below the gate is refused.
#include "shim.h"

ConfigMgr g_config;
std::vector<std::string> g_payloads;
std::vector<std::string> g_dispatched;
std::vector<bool> g_cleared;

static int failures = 0;
#define CHECK(cond)                                                                                                    \
    do                                                                                                                 \
    {                                                                                                                  \
        if (!(cond))                                                                                                   \
        {                                                                                                              \
            std::cerr << "FAIL line " << __LINE__ << ": " #cond "\n";                                                  \
            ++failures;                                                                                                \
        }                                                                                                              \
    } while (0)

static void SendAddonPayload(Player*, std::string const& payload)
{
    g_payloads.push_back(payload);
}
static void ClearEditorSession(Player*, bool notify)
{
    g_cleared.push_back(notify);
}
static void DispatchPayload(Player*, std::string const& payload)
{
    g_dispatched.push_back(payload);
}

namespace
{
#include "gate.inc"
}

static void reset(std::map<std::string, std::string> config)
{
    g_config.values = std::move(config);
    g_payloads.clear();
    g_dispatched.clear();
    g_cleared.clear();
}

static bool send(Player& player, uint32 lang, std::string msg)
{
    gobject_editor_player_script script;
    uint32 type = 0;
    script.OnPlayerBeforeSendChatMessage(&player, type, lang, msg);
    return !g_dispatched.empty();
}

int main()
{
    WorldSession session;
    Player player;
    player.session = &session;
    Player ghost; // no session at all

    // Module off: a missing key is off, and an explicit 0 is off, even for the highest account.
    for (auto config :
         {std::map<std::string, std::string>{}, std::map<std::string, std::string>{{"GObjectEditor.Enable", "0"}}})
    {
        reset(config);
        session.security = SEC_CONSOLE;
        CHECK(!IsModuleEnabled());
        CHECK(!HasAccess(&player));
        CHECK(!send(player, LANG_ADDON, "GE\tSCAN:5"));
        CHECK(!send(player, LANG_ADDON, "GE\tHELLO:GOBJECT_EDITOR_ACCESS"));
        CHECK(g_payloads.empty()); // nothing answered, not even a refusal
        gobject_editor_player_script().OnPlayerLogout(&player);
        CHECK(g_payloads.empty());
    }

    // Module on: only GM 3 and above pass, whatever the conf says RequiredSecurity is.
    for (uint32 required : {0u, 1u, 2u, 3u})
    {
        reset({{"GObjectEditor.Enable", "1"}, {"GObjectEditor.RequiredSecurity", std::to_string(required)}});
        for (AccountTypes level : {SEC_PLAYER, SEC_MODERATOR, SEC_GAMEMASTER})
        {
            session.security = level;
            CHECK(!HasAccess(&player));
        }
        session.security = SEC_ADMINISTRATOR;
        CHECK(HasAccess(&player));
    }
    reset({{"GObjectEditor.Enable", "1"}});
    session.security = SEC_ADMINISTRATOR;
    CHECK(HasAccess(&player)); // the key absent: the default gate is 3
    CHECK(!HasAccess(&ghost));
    CHECK(!HasAccess(nullptr));
    reset({{"GObjectEditor.Enable", "1"}, {"GObjectEditor.RequiredSecurity", "4"}});
    CHECK(!HasAccess(&player)); // the gate can be raised
    session.security = SEC_CONSOLE;
    CHECK(HasAccess(&player));

    // Module on: the hook hands only addon messages with the GE prefix to the dispatcher.
    reset({{"GObjectEditor.Enable", "1"}});
    session.security = SEC_PLAYER;
    CHECK(send(player, LANG_ADDON, "GE\tSCAN:5")); // the dispatcher gets it and its handlers refuse; here it is a stub
    CHECK(g_dispatched.size() == 1 && g_dispatched[0] == "SCAN:5");
    reset({{"GObjectEditor.Enable", "1"}});
    CHECK(!send(player, 0, "GE\tSCAN:5"));        // not addon chat
    CHECK(!send(player, LANG_ADDON, "XX\tSCAN")); // another addon's prefix
    CHECK(!send(player, LANG_ADDON, "GESCAN"));   // no tab

    // CLEAR: refused for a player below the gate, run for GM 3, and logout never notifies.
    reset({{"GObjectEditor.Enable", "1"}});
    session.security = SEC_GAMEMASTER;
    HandleClear(&player);
    CHECK(g_cleared.empty());
    CHECK(g_payloads.size() == 1 && g_payloads[0] == GE_ACCESS_DENIED);
    reset({{"GObjectEditor.Enable", "1"}});
    session.security = SEC_ADMINISTRATOR;
    HandleClear(&player);
    CHECK(g_cleared.size() == 1 && g_cleared[0] == true);
    reset({{"GObjectEditor.Enable", "1"}});
    gobject_editor_player_script().OnPlayerLogout(&player);
    CHECK(g_cleared.size() == 1 && g_cleared[0] == false);
    CHECK(g_payloads.empty());

    if (failures)
        return 1;
    std::cout << "ALL OK\n";
    return 0;
}
