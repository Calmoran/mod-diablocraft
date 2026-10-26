/*
 * World of DiabloCraft - the Kanai's Cube window handler (contract
 * docs/contracts/cube-messages.md).
 *
 * DCCUBE carries seven verbs (D3's three windows): `list` (the recipes with their page text, what each
 * costs and what the player's ledger holds, and the three power slots), `fill` (the reagents a recipe puts in the grid),
 * `transmute` (the grid: one item and its reagents; the server finds the recipe it holds), `powers` (one page of the
 * powers a slot can hold, with which the account has extracted), `power` (one power's text), `choose` (a slot's power) and `buffs` (the powers in the slots, for the buff bar; ungated).
 * Clicking the Cube in the Sanctum pushes the same records as `list`, under the verb `open`, so the window opens with
 * them. The execution path, the gate and the change records are dc_crafting_window.h's, shared with the Artisans; this
 * header adds the Cube's records only. It includes no core header: scripts/tests/crafting/test_cube.py drives it behind the real
 * router with a fake Game; dc_crafting.cpp supplies the real one.
 *
 * Game, beyond what Execute() asks (Gate, Carried, Balance, Detail, Failed):
 *   Cube::Recipes Recipes()                       the dc_cube_rule rows with their pages, in sort order
 *   void Transmute(std::string const& id, guid, gems)  run one recipe on one item and the bag gems of the grid; throws its refusal
 *   std::string GemClass(guid)                    the gem class of a bag item (legendary_gem, or a normal gem's tier); empty for any other
 *   std::vector<CubeSlot> Slots()                 every Cube slot in order, with the power chosen in it
 *   std::vector<CubePower> Powers(slot)           the powers that slot can hold, by name, with the account's extracted set
 *   std::optional<CubePowerText> PowerText(entry) one power's name and line; nullopt when it is no Cube power
 *   void Choose(slot, entry)                      put an extracted power in a slot (0 empties it); throws its refusal
 */
#ifndef DC_CUBE_WINDOW_H
#define DC_CUBE_WINDOW_H

#include "dc_crafting_window.h"
#include "dc_cube_rule.h"

#include <algorithm>
#include <cstdlib>
#include <iterator>
#include <optional>
#include <stdexcept>

namespace DC::Crafting::Window
{
    // The longest recipe id a request may name (generate_cube.py TOKEN).
    constexpr std::size_t CubeRecipeId = 24;
    // The grid is 3x3 and the item takes one cell, so a recipe has at most this many reagents (generate_cube.py MAX_REAGENTS).
    constexpr std::size_t CubeReagentCells = 8;
    // One cell's token, `entry_amount` or `iguid_count` (Cube::ParseCell): the longest it can be.
    constexpr std::size_t CubeCellToken = 22;
    // The Collection panel's layout: three columns by six rows a page.
    constexpr unsigned CubePowersPerPage = 18;
    // A power's line goes out in pieces of this many bytes (a line is up to 370; a record holds 248 after its prefix).
    constexpr std::size_t CubeTextPiece = 150;

    // One of the Cube's power slots: its number, its label (Weapon, Armor, Jewelry), and the power chosen in it
    // (the power's item entry and name; entry 0 and no name when it is empty).
    struct CubeSlot
    {
        unsigned slot = 0;
        std::string label;
        std::uint32_t entry = 0;
        std::string name;
    };
    // A power a slot can hold, named by its item. `extracted`: the account has it; `fits`: this character's class may use it.
    struct CubePower
    {
        std::uint32_t entry = 0;
        std::string name;
        bool extracted = false, fits = false;
    };
    struct CubePowerText
    {
        std::string name, text;
    };

    // What the ledger holds of one material; "0" when it has no row (or could not be read: no rows then).
    inline std::string Have(Funds const& funds, std::uint32_t entry)
    {
        auto found = funds.materials.find(entry);
        return found == funds.materials.end() ? "0" : found->second;
    }

    // One recipe: C, its page (P the subtitle, the item it takes and the note; Q the quote and its source; each only when the
    // sheet has one), a T for each spend line (need, have, ok), a K for each take line (the gem class, how many), then a Y for
    // each make line.
    template<class W>
    void SendRecipe(W const& wire, Cube::Recipe const& recipe, Funds const& funds)
    {
        wire.Record({"C", recipe.id, recipe.rule, recipe.name});
        if (!recipe.subtitle.empty())
            wire.Record({"P", recipe.id, recipe.subtitle, recipe.item, recipe.note});
        if (!recipe.quote.empty())
            wire.Record({"Q", recipe.id, recipe.quote, recipe.quoteSource});
        for (auto const& line : recipe.lines)
            if (line.kind == "spend")
            {
                std::string have = Have(funds, line.entry);
                bool ok = std::strtoull(have.c_str(), nullptr, 10) >= line.amount;
                wire.Record({"T", recipe.id, Num(line.entry), Num(line.amount), have, ok ? "1" : "0"});
            }
        for (auto const& line : recipe.lines)
            if (line.kind == "take")
                wire.Record({"K", recipe.id, line.rarity, Num(line.amount)});
        for (auto const& line : recipe.lines)
            if (line.kind == "make")
                wire.Record({"Y", recipe.id, line.rarity, Num(line.entry), Num(line.amount)});
    }

    // S: one power slot and what it holds.
    template<class W>
    void SendSlot(W const& wire, CubeSlot const& slot)
    {
        wire.Record({"S", Num(slot.slot), slot.label, Num(slot.entry), slot.name});
    }

    // The whole list: R, every recipe, every slot, E. `verb` is list (a request) or open (the click's push).
    template<class Game, class W>
    void SendCube(Game& game, W const& wire, char const* verb)
    {
        Cube::Recipes recipes;
        std::vector<CubeSlot> slots;
        Plain(
            [&]
            {
                game.Gate(Npc::Cube);
                recipes = game.Recipes();
                slots = game.Slots();
            });
        Funds funds = game.Balance();
        wire.Record({"R", verb, Num(recipes.size())});
        for (auto const& recipe : recipes)
            SendRecipe(wire, recipe, funds);
        for (auto const& slot : slots)
            SendSlot(wire, slot);
        wire.Record({"E", verb});
    }

    // Fill: the reagents of one recipe as grid cells, from what the ledger holds. Read-only: nothing leaves the ledger
    // until Transmute. A recipe the ledger cannot cover fills nothing.
    template<class Game, class W>
    void FillCube(Game& game, W const& wire, std::string const& id)
    {
        Cube::Recipes recipes;
        Plain(
            [&]
            {
                game.Gate(Npc::Cube);
                recipes = game.Recipes();
            });
        auto const* recipe = Cube::Find(recipes, id);
        if (!recipe)
            throw Bridge::Refusal("Choose a recipe.");
        Funds funds = game.Balance();
        std::vector<std::string> cells;
        for (auto const& line : recipe->lines)
            if (line.kind == "spend")
            {
                if (std::strtoull(Have(funds, line.entry).c_str(), nullptr, 10) < line.amount)
                    throw Bridge::Refusal("Not enough materials for that recipe.");
                cells.push_back(Num(line.entry) + ":" + Num(line.amount));
            }
        wire.Record({"R", "fill", Num(cells.size())});
        Pack(wire, {"G", recipe->id}, cells);
        wire.Record({"E", "fill"});
    }

    // One page of the powers a slot can hold: R, L (slot, page, pages, how many in all), W (entry:state:name, state 0 not
    // extracted, 1 extracted, 2 extracted but this class cannot use it), E. A page past the end is the last page.
    template<class Game, class W>
    void SendPowers(Game& game, W const& wire, unsigned slot, unsigned want)
    {
        std::vector<CubePower> powers;
        bool known = false;
        Plain(
            [&]
            {
                game.Gate(Npc::Cube);
                known = slot <= game.Slots().size();
                if (known)
                    powers = game.Powers(slot);
            });
        if (!known)
            throw Bridge::Refusal("There is no such slot.");
        auto page = Cube::Page(powers.size(), CubePowersPerPage, want);
        wire.Record({"R", "powers", Num(page.count)});
        wire.Record({"L", Num(slot), Num(page.page), Num(page.pages), Num(powers.size())});
        std::vector<std::string> parts;
        for (std::size_t i = page.first; i < page.first + page.count; ++i)
        {
            std::string name = powers[i].name;
            for (char& c : name)
                if (c == ':')
                    c = ' ';
            parts.push_back(Num(powers[i].entry) + ":" + (powers[i].extracted ? (powers[i].fits ? "1" : "2") : "0") + ":" +
                            name);
        }
        Pack(wire, {"W", Num(slot)}, parts);
        wire.Record({"E", "powers"});
    }

    // U: the pieces of one power's line (entry, name, piece number from 1, text).
    template<class W>
    void SendPieces(W const& wire, std::uint32_t entry, CubePowerText const& power, std::vector<std::string> const& pieces)
    {
        for (std::size_t i = 0; i < pieces.size(); ++i)
            wire.Record({"U", Num(entry), power.name, Num(i + 1), pieces[i]});
    }

    // One power's line, for its tooltip: R (the pieces), a U per piece (entry, name, piece number from 1, text), E. The
    // pieces join back to the line; the line has each range at its top.
    template<class Game, class W>
    void SendPower(Game& game, W const& wire, std::uint32_t entry)
    {
        std::optional<CubePowerText> found;
        Plain(
            [&]
            {
                game.Gate(Npc::Cube);
                found = game.PowerText(entry);
            });
        if (!found)
            throw Bridge::Refusal("That is not a Cube power.");
        auto pieces = Cube::Chunks(Cube::TopOfRanges(found->text), CubeTextPiece);
        wire.Record({"R", "power", Num(pieces.size())});
        SendPieces(wire, entry, *found, pieces);
        wire.Record({"E", "power"});
    }

    // The buff bar (contract "The buff bar"): read-only and ungated, so it answers dead, in combat or away
    // from the Cube. R (the slots that hold a power), then for each, in slot order, its S and the U pieces of its line (what
    // `power` sends for that entry), E. A slot with no power, or whose item has no Cube text, sends nothing.
    template<class Game, class W>
    void SendBuffs(Game& game, W const& wire)
    {
        std::vector<std::pair<CubeSlot, CubePowerText>> held;
        Plain(
            [&]
            {
                for (auto const& slot : game.Slots())
                    if (auto text = game.PowerText(slot.entry)) // entry 0 (an empty slot) is no Cube power
                        held.push_back({slot, *text});
            });
        wire.Record({"R", "buffs", Num(held.size())});
        for (auto const& [slot, text] : held)
        {
            SendSlot(wire, slot);
            SendPieces(wire, slot.entry, text, Cube::Chunks(Cube::TopOfRanges(text.text), CubeTextPiece));
        }
        wire.Record({"E", "buffs"});
    }

    // DCCUBE: list | fill recipeId | transmute itemGuid cell... | powers slot page | power entry | choose slot entry | buffs, a cell being
    // entry_amount (a ledger material) or iguid_count (bag items).
    template<class Game, class Actor>
    void CubeRequest(Game& game, Bridge::Request const& request, Bridge::Wire<Actor> const& wire)
    {
        auto verb = request.Token(0, 12);
        if (!verb)
            throw Bridge::Refusal("Choose an action.");
        char const* bad = "That request was not understood.";
        if (*verb == "list")
        {
            Exactly(request, 1, 1);
            SendCube(game, wire, "list");
        }
        else if (*verb == "fill")
        {
            Exactly(request, 2, 2);
            auto id = request.Token(1, CubeRecipeId);
            if (!id)
                throw Bridge::Refusal(bad);
            FillCube(game, wire, *id);
        }
        else if (*verb == "transmute")
        {
            // The grid: the item's guid (0: none in the grid), then each cell as entry_amount or iguid_count.
            Exactly(request, 2 + CubeReagentCells, 3);
            auto guid = RequiredUint(request, 1, 0, Max, bad);
            std::vector<Cube::Cell> cells;
            for (std::size_t i = 2; i < request.Count(); ++i)
            {
                auto token = request.Token(i, CubeCellToken);
                auto cell = token ? Cube::ParseCell(*token) : std::nullopt;
                if (!cell)
                    throw Bridge::Refusal(bad);
                cells.push_back(*cell);
            }
            // The server decides which recipe the grid holds. The recipe's item stays or goes by its rule; the tail sends the
            // recipe again with the ledger it left.
            std::string chosen;
            Execute(
                game, wire, "transmute", Npc::Cube, 0, false,
                [&]
                {
                    auto recipes = game.Recipes();
                    auto const* recipe = Cube::Match(recipes, cells, [&](std::uint32_t gem) { return game.GemClass(gem); });
                    if (!recipe)
                        throw std::runtime_error("The Cube cannot use what is in the grid.");
                    if (guid == 0)
                        throw std::runtime_error("Put an item in the Cube.");
                    chosen = recipe->id;
                    std::vector<Cube::Cell> gems;
                    std::copy_if(cells.begin(), cells.end(), std::back_inserter(gems), [](Cube::Cell const& cell) { return cell.item; });
                    game.Transmute(chosen, guid, gems);
                },
                [&]
                {
                    auto recipes = game.Recipes();
                    if (auto const* recipe = Cube::Find(recipes, chosen))
                        SendRecipe(wire, *recipe, game.Balance());
                });
        }
        else if (*verb == "powers")
        {
            Exactly(request, 3, 3);
            auto slot = RequiredUint(request, 1, 1, Max, bad);
            auto page = RequiredUint(request, 2, 1, Max, bad);
            SendPowers(game, wire, slot, page);
        }
        else if (*verb == "power")
        {
            Exactly(request, 2, 2);
            SendPower(game, wire, RequiredUint(request, 1, 1, Max, bad));
        }
        else if (*verb == "buffs")
        {
            Exactly(request, 1, 1);
            SendBuffs(game, wire);
        }
        else if (*verb == "choose")
        {
            Exactly(request, 3, 3);
            auto slot = RequiredUint(request, 1, 1, Max, bad);
            auto entry = RequiredUint(request, 2, 0, Max, bad);
            std::vector<CubeSlot> slots;
            Plain(
                [&]
                {
                    game.Gate(Npc::Cube);
                    game.Choose(slot, entry);
                    slots = game.Slots();
                });
            wire.Record({"R", "choose", entry ? "1" : "0"});
            for (auto const& s : slots)
                if (s.slot == slot)
                    SendSlot(wire, s);
            wire.Record({"E", "choose"});
        }
        else
            throw Bridge::Refusal("Unknown Cube action.");
    }
} // namespace DC::Crafting::Window

#endif
