#include "dc_version.h"
#include "dc_version_parse.h"
#include "Chat.h"
#include "ChatCommand.h"
#include "Config.h"
#include "DatabaseEnv.h"
#include "Log.h"
#include "ScriptMgr.h"
#include "World.h"
#include <algorithm>
#include <fstream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <vector>
namespace DC::Version
{
    using namespace Acore::ChatCommands;
    namespace
    {
        int schema = 0, clientPatch = 0;
        std::string module = "0.0.0", version;
        std::map<std::string, std::string> ReadValues(std::string const& path)
        {
            std::ifstream input(path);
            if (!input)
                throw std::runtime_error("cannot read " + path);
            std::map<std::string, std::string> values;
            std::string line;
            while (std::getline(input, line))
            {
                auto p = line.find('=');
                if (p != std::string::npos)
                    values[line.substr(0, p)] = line.substr(p + 1);
            }
            return values;
        }
        struct Row
        {
            int number;
            std::string file;
        };
        std::vector<Row> ReadSchema(std::string const& path)
        {
            std::ifstream input(path);
            if (!input)
                throw std::runtime_error("cannot read " + path);
            std::vector<Row> rows;
            std::string line;
            std::getline(input, line);
            while (std::getline(input, line))
            {
                if (line.empty())
                    continue;
                auto p = line.find(',');
                if (p == std::string::npos)
                    throw std::runtime_error("malformed schema.csv row: " + line);
                rows.push_back({std::stoi(line.substr(0, p)), line.substr(p + 1)});
            }
            return rows;
        }
        // The newest client patch the launcher manifest has published, 0 when it cannot be read; the same
        // file and pattern dc_version.lua uses, so both name the same minimum.
        int PublishedPatch()
        {
            std::ifstream input(sConfigMgr->GetOption<std::string>("Diablocraft.PublishedManifest",
                                                                   "/srv/torment-dl/stable/manifest.json"));
            std::stringstream text;
            text << input.rdbuf();
            return ParsePublishedPatch(text.str());
        }
        // The version of the launcher manifest, "" when it cannot be read (see PublishedPatch).
        std::string PublishedVersion()
        {
            std::ifstream input(sConfigMgr->GetOption<std::string>("Diablocraft.PublishedManifest",
                                                                   "/srv/torment-dl/stable/manifest.json"));
            std::stringstream text;
            text << input.rdbuf();
            return ParsePublishedVersion(text.str());
        }
        void CheckStartup()
        {
            auto versionPath = sConfigMgr->GetOption<std::string>("Diablocraft.VersionFile", "../../../VERSION");
            auto schemaPath = sConfigMgr->GetOption<std::string>("Diablocraft.SchemaFile",
                                                                 "../../../mod-diablocraft/data/sql/schema.csv");
            try
            {
                auto values = ReadValues(versionPath);
                module = values.at("module");
                // The game version players see: module X.Y.Z plus the launcher-only letter, both from VERSION.
                version = ComposeVersion(module, values.count("launcher_letter") ? values.at("launcher_letter") : "");
                schema = std::stoi(values.at("schema"));
                clientPatch = std::stoi(values.at("client_patch"));
                auto rows = ReadSchema(schemaPath);
                if (rows.empty() || rows.back().number != schema)
                    throw std::runtime_error("highest schema.csv row does not match VERSION");
                for (size_t i = 0; i < rows.size(); ++i)
                    if (rows[i].number != int(i + 1) || rows[i].file.empty())
                        throw std::runtime_error("schema.csv is not a contiguous explicit mapping");
                std::ostringstream missing;
                bool found = false;
                for (auto const& row : rows)
                    if (!WorldDatabase.Query(
                            "SELECT name FROM updates WHERE name='{}' AND state IN ('MODULE','RELEASED')", row.file))
                    {
                        if (found)
                            missing << ',';
                        missing << row.file;
                        found = true;
                    }
                if (found)
                    throw std::runtime_error("missing applied migration(s): " + missing.str());
                LOG_INFO("server.loading", "[DC version] version={} module={} schema={} client_patch={}", version, module,
                         schema, clientPatch);
            }
            catch (std::exception const& error)
            {
                LOG_ERROR("server.loading", "[DC version] startup refused: {}", error.what());
                World::StopNow(ERROR_EXIT_CODE);
            }
        }
        class VersionWorld final : public WorldScript
        {
        public:
            VersionWorld()
                : WorldScript("dc_version_world", {WORLDHOOK_ON_STARTUP})
            {
            }
            void OnStartup() override
            {
                CheckStartup();
            }
        };
        bool VersionCommand(ChatHandler* handler)
        {
            handler->SendSysMessage(VersionReply(version, module, schema, std::max(clientPatch, PublishedPatch()),
                                                 PublishedVersion()));
            handler->SendSysMessage(
                "Client addon status is reported by the AIO login handshake; a mismatch never blocks login.");
            return true;
        }
        class VersionCommands final : public CommandScript
        {
        public:
            VersionCommands()
                : CommandScript("dc_version_commands")
            {
            }
            ChatCommandTable GetCommands() const override
            {
                static ChatCommandTable dc = {{"version", VersionCommand, SEC_PLAYER, Console::Yes}};
                static ChatCommandTable root = {{"dc", dc}};
                return root;
            }
        };
    } // namespace
    int Schema()
    {
        return schema;
    }
    int ClientPatch()
    {
        return clientPatch;
    }
    std::string Module()
    {
        return module;
    }
    std::string GameVersion()
    {
        return version;
    }
    void RegisterScripts()
    {
        new VersionWorld();
        new VersionCommands();
    }
} // namespace DC::Version
