#ifndef DC_VERSION_PARSE_H
#define DC_VERSION_PARSE_H
#include <regex>
#include <string>
namespace DC::Version
{
    // The game version players see: VERSION's `module` X.Y.Z with
    // the launcher-only letter appended, "0.1.1" or "0.1.1a". A `module` that is not X.Y.Z gives "" (no
    // label); a letter that is not one lower-case a-z is dropped. The client patch stays the machine
    // number; this is only ever shown, never compared.
    inline std::string ComposeVersion(std::string module, std::string letter)
    {
        while (!module.empty() && (module.back() == '\r' || module.back() == ' '))
            module.pop_back();
        while (!letter.empty() && (letter.back() == '\r' || letter.back() == ' '))
            letter.pop_back();
        if (!std::regex_match(module, std::regex("\\d{1,3}\\.\\d{1,3}\\.\\d{1,4}")))
            return "";
        if (letter.size() == 1 && letter[0] >= 'a' && letter[0] <= 'z')
            return module + letter;
        return module;
    }

    // The top-level "version" string of a launcher manifest body (X.Y.Z with an optional letter), "" when
    // absent or not that shape. Never throws.
    inline std::string ParsePublishedVersion(std::string const& body)
    {
        std::smatch match;
        if (!std::regex_search(body, match, std::regex("\"version\"\\s*:\\s*\"(\\d{1,3}\\.\\d{1,3}\\.\\d{1,4}[a-z]?)\"")))
            return "";
        return match[1].str();
    }

    // The .dc version reply: the game version first, next to the client patch line. `published` is the
    // version of the launcher manifest the server reads (a launcher-only publish moves it past this
    // server's own VERSION without a restart); it is named only when it differs.
    inline std::string VersionReply(std::string const& version, std::string const& module, int schema,
                                    int expectedPatch, std::string const& published)
    {
        std::string out = "Torment version " + (version.empty() ? module : version) + ". Server expects client patch " +
                          std::to_string(expectedPatch) + " or newer";
        if (!published.empty() && published != version)
            out += " (published client: version " + published + ")";
        return out + ". Module " + module + ", schema " + std::to_string(schema) + ".";
    }

    // The "client_patch" number of a launcher manifest body, 0 when absent or not a sane patch number.
    // Never throws: this runs inside a GM command handler.
    inline int ParsePublishedPatch(std::string const& body)
    {
        std::smatch match;
        if (!std::regex_search(body, match, std::regex("\"client_patch\"\\s*:\\s*(\\d{1,6})(?!\\d)")))
            return 0;
        try
        {
            return std::stoi(match[1].str());
        }
        catch (...)
        {
            return 0;
        }
    }
} // namespace DC::Version
#endif
