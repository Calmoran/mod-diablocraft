// The server half of the window bridge (dc_bridge.h, contract docs/contracts/window-bridge.md):
// the one PlayerScript that hands a registered prefix's addon message to the router, and the
// packet a reply travels in. Same wire as DCPARAGON and DCMYSTIC: a prefixed addon whisper to
// oneself, which the client reassembles in CHAT_MSG_ADDON.
#include "dc_bridge.h"
#include "Chat.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "WorldPacket.h"
#include "WorldSession.h"

namespace DC::Bridge
{
    namespace
    {
        // The one packet a reply or a push travels in.
        Router<Player>::Sender const& Send()
        {
            static Router<Player>::Sender const send =
                [](Player* player, std::string const& prefix, std::string const& record)
            {
                WorldPacket packet;
                ChatHandler::BuildChatPacket(packet, CHAT_MSG_WHISPER, LANG_ADDON, player, player,
                                             prefix + "\t" + record);
                player->GetSession()->SendPacket(&packet);
            };
            return send;
        }
    } // namespace

    Router<Player>& Routes()
    {
        static Router<Player> router(Send());
        return router;
    }

    bool Push(Player* player, std::string const& prefix, std::vector<std::string> const& fields)
    {
        if (!player || !player->GetSession())
            return false;
        return Wire<Player>(Send(), player, prefix).Record(fields);
    }

    namespace
    {
        class BridgeScript final : public PlayerScript
        {
        public:
            BridgeScript()
                : PlayerScript("dc_window_bridge", {PLAYERHOOK_ON_BEFORE_SEND_CHAT_MESSAGE})
            {
            }

            // The hook is void and cannot swallow the message; harmless, it is a whisper to oneself.
            void OnPlayerBeforeSendChatMessage(Player* player, uint32& /*type*/, uint32& lang,
                                               std::string& msg) override
            {
                if (lang != LANG_ADDON || !player || !player->IsInWorld() || !player->GetSession())
                    return;
                Routes().Dispatch(player, msg, DC::Gap::NowMs());
            }
        };
    } // namespace

    void RegisterScripts()
    {
        new BridgeScript();
    }
} // namespace DC::Bridge
