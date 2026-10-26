// Env-var + per-extension .cfg-file config reader. Header-only: extensions have no object file to
// link core's own common/Config.cpp against, so each extension DLL that includes this compiles its
// own copy instead. Same "KEY=value", '#'/';' comment, trimmed format as the core's WarcraftXL.cfg;
// env var always wins, matching the core's own precedence.
// Copyright (C) 2026 WarcraftXL
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with this program. If not, see <https://www.gnu.org/licenses/>.

#pragma once

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <unordered_map>

namespace wxl::ext::config
{
    inline bool Truthy(const char* raw, bool fallback)
    {
        if (!raw || !raw[0]) return fallback;
        switch (raw[0])
        {
        case '0': case 'n': case 'N': case 'f': case 'F': return false;
        default: return true;
        }
    }

    /** @brief Parses one extension's .cfg file once; cached per-DLL (each includer gets its own copy). */
    inline const std::unordered_map<std::string, std::string>& File(const char* path)
    {
        static const std::unordered_map<std::string, std::string> entries = [&] {
            std::unordered_map<std::string, std::string> map;
            FILE* f = nullptr;
            if (fopen_s(&f, path, "rb") != 0 || !f) return map;
            char line[512];
            while (fgets(line, sizeof line, f))
            {
                char* text = line;
                while (*text == ' ' || *text == '\t') ++text;
                if (*text == '#' || *text == ';' || *text == '\0') continue;
                char* eq = std::strchr(text, '=');
                if (!eq) continue;
                char* keyEnd = eq;
                while (keyEnd > text && (keyEnd[-1] == ' ' || keyEnd[-1] == '\t')) --keyEnd;
                char* value = eq + 1;
                while (*value == ' ' || *value == '\t') ++value;
                char* valueEnd = value + std::strlen(value);
                while (valueEnd > value && (valueEnd[-1] == '\n' || valueEnd[-1] == '\r'
                                         || valueEnd[-1] == ' '  || valueEnd[-1] == '\t')) --valueEnd;
                if (keyEnd > text)
                    map.emplace(std::string(text, keyEnd), std::string(value, valueEnd));
            }
            fclose(f);
            return map;
        }();
        return entries;
    }

    /** @brief Resolves a knob's raw value: environment first, then cfgPath's .cfg file. */
    inline bool Raw(const char* name, char* buf, size_t cap, const char* cfgPath)
    {
        if (!name || !buf || !cap) return false;
        size_t written = 0;
        if (getenv_s(&written, buf, cap, name) == 0 && written > 0) return true;

        const auto& cfg = File(cfgPath);
        const auto it = cfg.find(name);
        if (it == cfg.end() || it->second.empty() || it->second.size() + 1 > cap) return false;
        std::memcpy(buf, it->second.c_str(), it->second.size() + 1);
        return true;
    }
}
