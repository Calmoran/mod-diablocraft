/*
 * World of DiabloCraft - shared tunables.
 *
 * Copied from the elite-affix mechanism rather than designed again:
 * dc_rift_elites.cpp:146 builds one snapshot from one WORLD query, :374 swaps
 * it in under a mutex only when the build succeeded, and dc_rifts.cpp:1944
 * registers the `.dc affix` commands that write one row and reload. The only
 * differences here are the key - (category, name) instead of (affix,
 * parameter) - and that a missing row cannot disable anything, because a
 * tunable belongs to whatever system asked for it.
 */

#include "dc_tunables.h"

#include "Chat.h"
#include "ChatCommand.h"
#include "DatabaseEnv.h"
#include "Log.h"
#include "ScriptMgr.h"

#include <cctype>
#include <cmath>
#include <memory>
#include <mutex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>

namespace DC::Tunables
{
    namespace
    {
        struct Snapshot
        {
            // "category|name" -> the number the server is using for it.
            std::unordered_map<std::string, double> value;
        };

        std::mutex dataMutex;
        std::shared_ptr<Snapshot const> snapshot;
        // One automatic load attempt, so a failing table cannot turn every
        // Get() into a query. `.dc tunables reload` is always allowed through.
        bool autoLoadTried = false;
        // One log line per missing key, not one per read: a Get() in a combat
        // path would otherwise fill the log with the same sentence.
        std::set<std::string> warned;

        void LoadOnce(std::string& error);

        std::string Key(std::string const& category, std::string const& name)
        {
            return category + "|" + name;
        }

        // Every path takes its own copy of the pointer and works off that, so it
        // can never see half a reload.
        std::shared_ptr<Snapshot const> Current()
        {
            {
                std::lock_guard<std::mutex> lock(dataMutex);
                if (snapshot)
                    return snapshot;
            }
            // Nothing has loaded yet. WorldScript startup order is the core's,
            // not ours, so a system whose own OnStartup reads a number can get
            // here first; build once here rather than hand it a 0. The lock is
            // not held across the query.
            std::string error;
            LoadOnce(error);
            std::lock_guard<std::mutex> lock(dataMutex);
            return snapshot;
        }

        // Read dc_tunables and build one snapshot of it. tuned_value when one is set,
        // d3_value otherwise. A row with neither is a number
        // nobody has chosen yet: it is left out, so asking for it is a missing
        // row rather than a silent 0 that looks deliberate.
        std::shared_ptr<Snapshot const> Build(std::string& error)
        {
            // A query that returns nothing and a query that FAILED both arrive
            // here as a null QueryResult, and they must not mean the same thing:
            // an empty table is the shipped state of section M, while a missing
            // table or a broken connection has to leave the previous numbers
            // running. The UNION ALL row is the difference. It always comes back
            // from a query that ran, so a null result now means only failure,
            // and it costs one row rather than a second query.
            QueryResult rows = WorldDatabase.Query("SELECT category, name, d3_value, tuned_value FROM dc_tunables "
                                                   "UNION ALL SELECT '', '', NULL, NULL");
            if (!rows)
            {
                error = "dc_tunables could not be read (missing table or failed query); "
                        "apply tunables_0001.sql";
                return nullptr;
            }
            auto built = std::make_shared<Snapshot>();
            do
            {
                Field* f = rows->Fetch();
                // The sentinel. A real row cannot be it: the generator refuses a
                // name that is not lower_snake_case, so none is empty.
                if (f[1].Get<std::string>().empty())
                    continue;
                std::string const key = Key(f[0].Get<std::string>(), f[1].Get<std::string>());
                double number = 0.0;
                if (!f[3].IsNull())
                    number = f[3].Get<double>();
                else if (!f[2].IsNull())
                    number = f[2].Get<double>();
                else
                    continue;
                if (!std::isfinite(number))
                {
                    error = "Non-finite tunable: " + key;
                    return nullptr;
                }
                built->value[key] = number;
            } while (rows->NextRow());
            return built;
        }

        // The one unattended load, for a caller that arrives before the startup
        // hook has run. It never replaces a snapshot that already exists.
        void LoadOnce(std::string& error)
        {
            {
                std::lock_guard<std::mutex> lock(dataMutex);
                if (autoLoadTried)
                    return;
                autoLoadTried = true;
            }
            std::shared_ptr<Snapshot const> built = Build(error);
            if (!built)
                return;
            std::lock_guard<std::mutex> lock(dataMutex);
            if (!snapshot)
                snapshot = std::move(built);
        }
    } // namespace

    double Get(std::string const& category, std::string const& name)
    {
        std::string const key = Key(category, name);
        auto const live = Current();
        if (live)
        {
            auto const found = live->value.find(key);
            if (found != live->value.end())
                return found->second;
        }
        {
            std::lock_guard<std::mutex> lock(dataMutex);
            if (!warned.insert(key).second)
                return 0.0;
        }
        LOG_ERROR("server",
                  "[DC tunables] {} has no value; returning 0. Add the row to "
                  "data/tunables/{}.csv, regenerate and apply tunables_0001.sql, "
                  "then .dc tunables reload.",
                  key, category);
        return 0.0;
    }

    bool Has(std::string const& category, std::string const& name)
    {
        auto const live = Current();
        return live && live->value.count(Key(category, name)) > 0;
    }

    std::size_t Count()
    {
        auto const live = Current();
        return live ? live->value.size() : 0;
    }

    // Swap in a fresh snapshot. Startup and `.dc tunables reload` both come
    // here, and a failed read leaves the previous one in place rather than
    // zeroing every number on the map.
    bool Reload(std::string& error)
    {
        std::shared_ptr<Snapshot const> built = Build(error);
        if (!built)
        {
            // The read failed. Keep the snapshot that is running - that is the
            // whole point - and record the attempt so the caller's own error
            // message does not set another failing query going.
            std::lock_guard<std::mutex> lock(dataMutex);
            autoLoadTried = true;
            return false;
        }
        std::lock_guard<std::mutex> lock(dataMutex);
        snapshot = std::move(built);
        autoLoadTried = true;
        // A row that was missing may exist now; let it be reported again if it
        // is still absent after the reload.
        warned.clear();
        return true;
    }

    namespace
    {
        using namespace Acore::ChatCommands;

        std::string EscapeWorld(std::string value)
        {
            WorldDatabase.EscapeString(value);
            return value;
        }

        std::string Shown(double number)
        {
            std::ostringstream text;
            text << number; // 2.5 rather than 2.500000
            return text.str();
        }

        // What the server is actually using for one row: the tuned value when
        // one is set, D3's otherwise. Same wording as `.dc affix show`.
        std::string Effective(Field* row)
        {
            if (!row[1].IsNull())
                return Shown(row[1].Get<double>()) + " (tuned; D3 " +
                       (row[0].IsNull() ? "publishes none" : Shown(row[0].Get<double>())) + ")";
            if (!row[0].IsNull())
                return Shown(row[0].Get<double>()) + " (D3)";
            return "unset";
        }

        bool ReloadCommand(ChatHandler* handler)
        {
            std::string error;
            if (!Reload(error))
            {
                handler->PSendSysMessage("Tunables NOT reloaded: {}", error);
                // The count is what makes the retained snapshot visible: a failed
                // read must never quietly empty the numbers the server is running.
                handler->PSendSysMessage("The previous {} row(s) are still in use.", Count());
                return true;
            }
            handler->PSendSysMessage("Tunables reloaded: {} row(s). Code reads the new numbers "
                                     "from its next read.",
                                     Count());
            // 12-ui: the AIO Lua scripts hook this command through ALE's
            // PLAYER_EVENT_ON_COMMAND and re-read dc_tunables on the next world
            // tick - see docs/contracts/tunables.md.
            handler->SendSysMessage("Values already applied to something standing on the map keep "
                                    "the old number until it is rebuilt - as `.dc affix reload` says.");
            return true;
        }

        // `.dc tunables get <category> <name>`
        bool GetCommand(ChatHandler* handler, std::string category, std::string name)
        {
            QueryResult row = WorldDatabase.Query("SELECT d3_value, tuned_value, unit, notes FROM dc_tunables "
                                                  "WHERE category='{}' AND name='{}'",
                                                  EscapeWorld(category), EscapeWorld(name));
            if (!row)
            {
                handler->PSendSysMessage("dc_tunables has no {} / {}.", category, name);
                handler->SendSysMessage("The categories are the file names in data/tunables/.");
                return true;
            }
            Field* fields = row->Fetch();
            handler->PSendSysMessage("{} / {} = {} {}", category, name, Effective(fields),
                                     fields[2].Get<std::string>());
            handler->PSendSysMessage("  {}", fields[3].Get<std::string>());
            if (!Has(category, name))
                handler->SendSysMessage("  The live snapshot has no number for it; "
                                        "`.dc tunables set` one, or reload after applying the SQL.");
            return true;
        }

        // `.dc tunables set <category> <name> <value>` writes tuned_value and
        // reloads; `.dc tunables default <category> <name>` clears it so the row
        // falls back to what D3 published.
        bool Write(ChatHandler* handler, std::string const& category, std::string const& name, bool clearing,
                   double number)
        {
            std::string const escapedCategory = EscapeWorld(category), escapedName = EscapeWorld(name);
            if (!WorldDatabase.Query("SELECT name FROM dc_tunables WHERE category='{}' AND name='{}'", escapedCategory,
                                     escapedName))
            {
                handler->PSendSysMessage("dc_tunables has no {} / {}.", category, name);
                handler->SendSysMessage("Add the row to the category CSV, regenerate and apply "
                                        "tunables_0001.sql first.");
                return true;
            }
            // Direct, not queued: the reload on the next line has to see it.
            if (clearing)
                WorldDatabase.DirectExecute("UPDATE dc_tunables SET tuned_value=NULL "
                                            "WHERE category='{}' AND name='{}'",
                                            escapedCategory, escapedName);
            else
                WorldDatabase.DirectExecute("UPDATE dc_tunables SET tuned_value={} "
                                            "WHERE category='{}' AND name='{}'",
                                            number, escapedCategory, escapedName);
            std::string error;
            if (!Reload(error))
            {
                handler->PSendSysMessage("Written, but NOT reloaded: {}", error);
                return true;
            }
            if (QueryResult row = WorldDatabase.Query("SELECT d3_value, tuned_value, unit FROM dc_tunables "
                                                      "WHERE category='{}' AND name='{}'",
                                                      escapedCategory, escapedName))
                handler->PSendSysMessage("{} / {} is now {} {}", category, name, Effective(row->Fetch()),
                                         (*row)[2].Get<std::string>());
            // The CSV is the source of truth, so a `set` is a
            // scratch override for the session being tested and the next apply
            // of tunables_0001.sql takes it back. Say so at the point where it
            // is easy to believe otherwise. `default` says nothing extra: it
            // asks for the published value, which is what an apply gives it.
            if (!clearing)
                handler->PSendSysMessage("(temporary: lasts until the next apply from {}.csv; "
                                         "put it in the CSV to keep it)", category);
            return true;
        }

        bool SetCommand(ChatHandler* handler, std::string category, std::string name, Tail wanted)
        {
            std::string const text(wanted);
            double number = 0;
            try
            {
                std::size_t used = 0;
                number = std::stod(text, &used);
                while (used < text.size() && std::isspace(static_cast<unsigned char>(text[used])))
                    ++used;
                if (used != text.size() || !std::isfinite(number))
                    throw std::invalid_argument("trailing text");
            }
            catch (std::exception const&)
            {
                handler->PSendSysMessage("'{}' is not a number. Use `.dc tunables default {} {}` "
                                         "to go back to D3's value.",
                                         text, category, name);
                return true;
            }
            return Write(handler, category, name, false, number);
        }

        bool DefaultCommand(ChatHandler* handler, std::string category, std::string name)
        {
            return Write(handler, category, name, true, 0.0);
        }

        class TunablesCommands final : public CommandScript
        {
        public:
            TunablesCommands()
                : CommandScript("dc_tunables_commands")
            {
            }

            ChatCommandTable GetCommands() const override
            {
                // Console::Yes on all four, so a number can be changed from the
                // worldserver window as well as in game, exactly as `.dc affix` is.
                static ChatCommandTable tunables = {
                    {"reload", ReloadCommand, SEC_ADMINISTRATOR, Console::Yes},
                    {"get", GetCommand, SEC_GAMEMASTER, Console::Yes},
                    {"set", SetCommand, SEC_ADMINISTRATOR, Console::Yes},
                    {"default", DefaultCommand, SEC_ADMINISTRATOR, Console::Yes},
                };
                static ChatCommandTable dc = {{"tunables", tunables}};
                static ChatCommandTable root = {{"dc", dc}};
                return root;
            }
        };

        class TunablesWorld final : public WorldScript
        {
        public:
            TunablesWorld()
                : WorldScript("dc_tunables_world", {WORLDHOOK_ON_STARTUP})
            {
            }

            void OnStartup() override
            {
                // Unlike the affixes, a missing table does not stop the server:
                // nothing has migrated into dc_tunables yet, and a realm that
                // cannot start is worse than a system that logs what it lacks.
                std::string error;
                if (!Reload(error))
                {
                    LOG_ERROR("server.loading",
                              "[DC tunables] not loaded: {}. Fix it and `.dc tunables reload`; "
                              "until then every tunable reads 0.",
                              error);
                    return;
                }
                LOG_INFO("server.loading", "[DC tunables] {} row(s) loaded from dc_tunables.", Count());
            }
        };
    } // namespace

    void RegisterScripts()
    {
        new TunablesCommands();
        new TunablesWorld();
    }
} // namespace DC::Tunables
