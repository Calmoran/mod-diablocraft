/*
 * World of DiabloCraft - Kanai's Cube recipe rules (plan docs/research/kanais-cube.md 6.1).
 *
 * A recipe is the rows of dc_cube_rule (data/d3/cube_rules.csv, generate_cube.py): `spend` lines take account ledger
 * materials, and a `convert` recipe's `make` lines say what it makes for each rarity of the controlling item (the item
 * the player puts in, which the Cube does not consume; D3's three Iben Fahd conversions). A `set_convert` recipe (Skill of
 * Nilfur) consumes a Set item for another piece of its set, a `rare_upgrade` one (Hope of Cain) a Rare item for a legendary or
 * set item of its item type, a `reforge` one (Law of Kulle) a legendary or set item for the same item rolled
 * again, a `primal_upgrade` one (Curiosity of Lorath Nahr) a legendary or set item for the same item as a Primal
 * with its maker marked, an `extract` one (Archive of Tal Rasha) a legendary item for its power, learned by
 * the account; they make no material. An `augment` recipe (Caldesann's Despair)
 * keeps its Ancient or Primal item and consumes bag gems, named by its `take` lines. The grid a player fills
 * names no recipe: Match() finds the one whose spend and take lines are exactly its reagents and gems. No number lives here. Pure,
 * so scripts/tests/crafting/test_cube.py compiles this very header; dc_cube.cpp reads the rows and calls these.
 */
#ifndef DC_CUBE_RULE_H
#define DC_CUBE_RULE_H

#include <algorithm>
#include <cstdint>
#include <functional>
#include <map>
#include <optional>
#include <string>
#include <vector>

namespace DC::Crafting::Cube
{
    struct Line
    {
        unsigned line = 0;
        std::string kind;   // spend, make or take
        std::string rarity; // a make line's controlling rarity; a take line's gem class (legendary_gem or a normal gem's tier); empty on a spend line
        std::uint32_t entry = 0;
        std::uint64_t amount = 0;
    };
    struct Recipe
    {
        std::string id, rule, name;
        unsigned sort = 0;
        std::vector<Line> lines;
        // The Recipes panel's page text (dc_cube_page, cube_pages.csv); empty when a recipe has none.
        std::string subtitle, item, note, quote, quoteSource;
    };
    using Recipes = std::vector<Recipe>;

    inline Recipe const* Find(Recipes const& recipes, std::string const& id)
    {
        for (auto const& recipe : recipes)
            if (recipe.id == id)
                return &recipe;
        return nullptr;
    }

    // What a convert recipe makes for a controlling item of this rarity; nullptr when it takes no item of that rarity.
    inline Line const* Makes(Recipe const& recipe, std::string const& rarity)
    {
        for (auto const& line : recipe.lines)
            if (line.kind == "make" && line.rarity == rarity)
                return &line;
        return nullptr;
    }

    // Whether a recipe consumes its item and rolls a new one; a convert recipe's controlling item stays, and so does an
    // augment recipe's (it consumes the gems it takes).
    inline bool Consumes(Recipe const& recipe)
    {
        return recipe.rule != "convert" && recipe.rule != "augment";
    }

    // Whether a recipe that consumes its item takes one of this rarity (a convert recipe's rarities are its make lines).
    inline bool Takes(Recipe const& recipe, std::string const& rarity)
    {
        return recipe.rule == "set_convert" ? rarity == "set"
             : recipe.rule == "rare_upgrade" ? rarity == "rare"
             : recipe.rule == "reforge" ? rarity == "legendary" || rarity == "set"
             : recipe.rule == "primal_upgrade" ? rarity == "legendary" || rarity == "set"
             : recipe.rule == "augment" ? rarity == "legendary" || rarity == "set"
             : recipe.rule == "extract" ? rarity == "legendary"
                                         : false;
    }

    // The Archive of Tal Rasha's refusals, all decided before anything is taken (D3: "fails with no cost if the power is already
    // extracted or cannot be extracted", cube_costs.csv). `built`: the legendary framework has a row for the item's power
    // (ItemPowers::Built, so the Cube never destroys an item for a power that does nothing); `listed`: some Cube slot lists it
    // (dc_cube_slot_item), so the Collection panel can show it; `known`: the account has extracted it. Empty when the extraction may run.
    inline std::string ExtractRefusal(bool built, bool listed, bool known)
    {
        if (!built || !listed)
            return "The Cube cannot extract that item's power yet.";
        if (known)
            return "You have already extracted that power.";
        return {};
    }

    // Skill of Nilfur's choice: the set's other pieces (the drop pool's, so never a crafted set's), none when the set has
    // fewer than `least` pieces (D3: not a 2-piece set). `own` is the piece put in; an older version of it is not in the pool.
    inline std::vector<std::uint32_t> OtherPieces(std::vector<std::uint32_t> const& pieces, std::uint32_t own, unsigned least)
    {
        std::vector<std::uint32_t> out;
        if (pieces.size() < least)
            return out;
        for (auto piece : pieces)
            if (piece != own)
                out.push_back(piece);
        return out;
    }

    // A take line's class for the 21 legendary gems; any other class is a normal gem's tier (gems.csv, "Flawless Royal").
    inline constexpr char const* LegendaryGem = "legendary_gem";

    // One cell of the grid: a material of the account ledger and how many of it, or (`item`) a stack of bag items, `entry` its
    // item guid, `amount` how many of the stack (Caldesann's gems).
    struct Cell
    {
        std::uint32_t entry = 0;
        std::uint64_t amount = 0;
        bool item = false;
    };

    // A cell as a request carries it: `entry_amount` for a material, `i` and then `guid_count` for bag items; digits only, both
    // numbers above 0 and each under 2^32.
    inline std::optional<Cell> ParseCell(std::string const& text)
    {
        bool const item = !text.empty() && text[0] == 'i';
        std::size_t const from = item ? 1 : 0;
        auto split = text.find('_');
        if (split == std::string::npos || split == from || split + 1 >= text.size() || split - from > 10 || text.size() - split - 1 > 10)
            return std::nullopt;
        std::uint64_t part[2] = {0, 0};
        for (std::size_t i = from; i < text.size(); ++i)
        {
            if (i == split)
                continue;
            if (text[i] < '0' || text[i] > '9')
                return std::nullopt;
            part[i > split] = part[i > split] * 10 + static_cast<std::uint64_t>(text[i] - '0');
        }
        if (part[0] == 0 || part[1] == 0 || part[0] > UINT32_MAX || part[1] > UINT32_MAX)
            return std::nullopt;
        return Cell{static_cast<std::uint32_t>(part[0]), part[1], item};
    }

    // The recipe the grid holds: the one whose spend lines are exactly the reagents, each material at its amount (two cells
    // of one material add up) and no other material, and whose take lines are exactly the gems: `classOf` names the gem class of
    // a bag item's guid (legendary_gem, or a normal gem's tier; empty for anything else), and the cells of one class add up.
    // nullptr when none does: the Cube refuses a grid that matches nothing, and an item cell of no class matches nothing.
    template<class ClassOf>
    Recipe const* Match(Recipes const& recipes, std::vector<Cell> const& cells, ClassOf&& classOf)
    {
        std::map<std::uint32_t, std::uint64_t> held;
        std::map<std::string, std::uint64_t> gems;
        for (auto const& cell : cells)
        {
            if (!cell.item)
            {
                held[cell.entry] += cell.amount;
                continue;
            }
            std::string const gem = classOf(cell.entry);
            if (gem.empty())
                return nullptr;
            gems[gem] += cell.amount;
        }
        for (auto const& recipe : recipes)
        {
            std::map<std::uint32_t, std::uint64_t> spend;
            std::map<std::string, std::uint64_t> take;
            for (auto const& line : recipe.lines)
            {
                if (line.kind == "spend")
                    spend[line.entry] += line.amount;
                else if (line.kind == "take")
                    take[line.rarity] += line.amount;
            }
            if ((!spend.empty() || !take.empty()) && spend == held && take == gems)
                return &recipe;
        }
        return nullptr;
    }
    inline Recipe const* Match(Recipes const& recipes, std::vector<Cell> const& cells)
    {
        return Match(recipes, cells, [](std::uint32_t) { return std::string(); });
    }

    // Caldesann's Despair (cube_augment.csv, dc_cube_augment): the attribute of each gem colour, the amount a
    // rank gives, and the smallest Legendary Gem rank for each power slot label.
    struct AugmentRules
    {
        std::map<std::string, std::string> stat;         // gem colour -> main-stat affix id
        std::uint64_t perRank = 0;
        std::map<std::string, std::uint64_t> minRank;    // power slot label -> smallest Legendary Gem rank
    };
    struct Augmentation
    {
        std::string stat, refusal;
        std::uint64_t value = 0;
    };

    // What the Cube adds to an item: only an Ancient or Primal one, a Legendary Gem of at least the slot's rank, and gems all of
    // one colour that has an attribute; the bonus is `perRank` of that attribute for each rank of the Legendary Gem.
    inline Augmentation Augment(AugmentRules const& rules, std::string const& quality, std::string const& slotLabel,
                                std::uint64_t gemRank, std::vector<std::string> const& colours)
    {
        Augmentation out;
        auto fail = [&](std::string text)
        {
            out.refusal = std::move(text);
            return out;
        };
        if (quality != "ancient" && quality != "primal")
            return fail("The Cube augments only an Ancient or Primal item.");
        auto const need = rules.minRank.find(slotLabel);
        if (need == rules.minRank.end())
            return fail("The Cube cannot augment that kind of item.");
        if (gemRank < need->second)
            return fail("That Legendary Gem is too weak for this item: it needs rank " + std::to_string(need->second) + ".");
        if (colours.empty() || std::adjacent_find(colours.begin(), colours.end(), std::not_equal_to<>()) != colours.end())
            return fail("Use gems of one colour.");
        auto const found = rules.stat.find(colours.front());
        if (found == rules.stat.end())
            return fail("A " + colours.front() + " adds no attribute.");
        out.stat = found->second;
        out.value = rules.perRank * gemRank;
        return out;
    }

    // A power's text for a Cube slot: an extracted power is stored at the top of its range, so every
    // `a–b` range in the line (the generator's en dash, generate_crafting.py item_tooltip_rows) reads as `b`.
    inline std::string TopOfRanges(std::string const& text)
    {
        auto const digit = [](char c) { return c >= '0' && c <= '9'; };
        auto const number = [&](std::size_t at)
        {
            std::size_t end = at;
            while (end < text.size() && digit(text[end]))
                ++end;
            if (end + 1 < text.size() && text[end] == '.' && digit(text[end + 1]))
                for (++end; end < text.size() && digit(text[end]); ++end)
                    ;
            return end;
        };
        std::string const dash = "\xe2\x80\x93";
        std::string out;
        for (std::size_t i = 0; i < text.size();)
        {
            if (digit(text[i]))
            {
                std::size_t first = number(i);
                if (text.compare(first, dash.size(), dash) == 0 && digit(text[first + dash.size()]))
                {
                    std::size_t from = first + dash.size();
                    std::size_t to = number(from);
                    out += text.substr(from, to - from);
                    i = to;
                }
                else
                {
                    out += text.substr(i, first - i);
                    i = first;
                }
                continue;
            }
            out += text[i++];
        }
        return out;
    }

    // A long text in pieces of at most `size` bytes that join back to it: each ends after a space where there is one, and never
    // inside a multi-byte character. An empty text is one empty piece.
    inline std::vector<std::string> Chunks(std::string const& text, std::size_t size)
    {
        std::vector<std::string> out;
        std::size_t at = 0;
        do
        {
            std::size_t end = at + size < text.size() ? at + size : text.size();
            if (end < text.size())
            {
                std::size_t space = text.rfind(' ', end - 1);
                if (space != std::string::npos && space >= at)
                    end = space + 1;
                else
                    while (end > at + 1 && (static_cast<unsigned char>(text[end]) & 0xC0) == 0x80)
                        --end;
            }
            out.push_back(text.substr(at, end - at));
            at = end;
        } while (at < text.size());
        return out;
    }

    // One page of a list: the 1-based page clamped into 1..pages (an empty list is one empty page), its first index and how
    // many entries it holds.
    struct Paging
    {
        unsigned page = 1, pages = 1;
        std::size_t first = 0, count = 0;
    };
    inline Paging Page(std::size_t total, unsigned perPage, unsigned want)
    {
        Paging out;
        out.pages = perPage && total ? static_cast<unsigned>((total + perPage - 1) / perPage) : 1;
        out.page = want < 1 ? 1 : want > out.pages ? out.pages : want;
        out.first = static_cast<std::size_t>(out.page - 1) * perPage;
        out.count = out.first >= total ? 0 : (total - out.first < perPage ? total - out.first : perPage);
        return out;
    }
} // namespace DC::Crafting::Cube

#endif
