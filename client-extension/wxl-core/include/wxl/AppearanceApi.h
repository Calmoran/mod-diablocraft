// wxl-db2's model appearance recipes, published for other extensions to consume via
// WXL_Api::GetInterface("wxl.appearance", WXL_APPEARANCE_API_VERSION).
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

#ifndef WXL_APPEARANCE_API_H
#define WXL_APPEARANCE_API_H

#include <stdint.h>

// A modern model does not carry its own finished look. Which of its parts are visible, what is
// painted onto it, and what extra pieces are worn with it all live in database tables, and the model
// file is the same bytes whichever answer those tables give.
//
// This publishes that answer as ONE shape, deliberately not a character-specific one. A player's look
// comes from the customization tables and a creature's from its display entry, but both end as the
// same three lists, and the consumer that turns those lists into draws should not have to care which
// table produced them. That is also what keeps the split honest: everything on this side of the
// boundary knows the tables and nothing about models, everything on the other side knows models and
// nothing about the tables.

#ifdef __cplusplus
extern "C" {
#endif

#define WXL_APPEARANCE_API_VERSION 2

/// One texture the runtime owes the model, for one of the slots the model itself leaves unfilled.
typedef struct WXL_TextureLayer
{
    /// The model's own texture-slot number, as its texture record states it. The model asks for a
    /// slot; this says what belongs in it.
    uint32_t textureType;
    /// Paint order within that slot, lowest first. Layers are not commutative: a later one covers.
    uint32_t layer;
    uint32_t blendMode;
    /// Which regions of the slot's layout this covers. A layer paints part of a sheet, not all of it.
    uint32_t sectionMask;
    /// What to paint, still as a material id: turning it into a file is the texture tables' job, and
    /// doing it here would put a second resolution path beside the one wxl.fdid already owns.
    uint32_t materialResourceId;
} WXL_TextureLayer;

/// A separate model skinned to the SAME skeleton and drawn with the main one (hair, horns, tusks).
/// It is not an attachment in the model's own sense: it shares the bone palette rather than hanging
/// off a point.
typedef struct WXL_AttachedModel
{
    uint32_t fileDataId;
    /// The geoset it counts as, so one visibility rule covers it and the main model's own parts.
    uint32_t geoset;
} WXL_AttachedModel;

/// Everything needed to draw one appearance, in the model side's own vocabulary.
typedef struct WXL_Recipe
{
    uint32_t modelFileDataId;
    uint32_t skeletonFileDataId;  ///< 0 when the model is not split-skeleton
    uint32_t textureLayoutId;     ///< the sheet layout the layers below address

    /// Geosets to show, as the FINAL ids the model's own submeshes carry (group * 100 + value).
    /// Resolved to that form here on purpose: which table expressed them, and in how many pieces,
    /// is not something the model side should have to learn.
    const uint16_t* geosets;
    uint32_t        geosetCount;

    const WXL_TextureLayer* layers;
    uint32_t                layerCount;

    const WXL_AttachedModel* attached;
    uint32_t                 attachedCount;
} WXL_Recipe;

/// One region of a composited sheet: where a section type lands on it, in the sheet's own pixels.
///
/// A model's UVs are authored against a LAYOUT, not against a texture, and every layout states its
/// own sheet size. Two layouts can place the same section at the same pixels and still disagree on
/// every UV, because normalising those pixels needs the size. So a consumer that composes a sheet
/// needs both, and the size is not derivable from the sections.
typedef struct WXL_TextureSection
{
    uint32_t sectionType;
    uint32_t x, y, width, height;
    uint32_t overlapMask;
} WXL_TextureSection;

/// One customization option a model offers (skin, face, hair, horns...), as the tables state it.
typedef struct WXL_ChrOption
{
    uint32_t id;
    uint32_t optionType;
    uint32_t orderIndex;
    uint32_t flags;
} WXL_ChrOption;

/// One setting of one option. Its id is what a recipe is built from.
typedef struct WXL_ChrChoice
{
    uint32_t id;
    uint32_t orderIndex;
    uint32_t uiOrderIndex;
    uint32_t flags;
    uint32_t swatchColor;
} WXL_ChrChoice;

typedef struct WXL_AppearanceApi
{
    uint32_t structSize;
    uint32_t apiVersion;

    /// A player character: race, sex, and the customization choices made.
    /// @param choiceIds  ChrCustomizationChoice ids, in any order.
    /// @return nonzero when out was filled.
    int(__cdecl* BuildForCharacter)(uint32_t chrRaceId, uint32_t sex,
                                    const uint32_t* choiceIds, uint32_t choiceCount,
                                    WXL_Recipe* out);

    /// A creature or NPC: everything comes from its display entry.
    /// @return nonzero when out was filled.
    int(__cdecl* BuildForCreature)(uint32_t creatureDisplayInfoId, WXL_Recipe* out);

    // --- what a model can be customized into --------------------------------------------------
    //
    // Published rather than reduced to a fixed set of slots, because there is no table left that
    // maps the stock client's five customization bytes onto modern choices: the one that used to,
    // ChrCustClientChoiceConversion, still exists but ships zero rows. So the mapping has to be
    // decided outside this resolver, and deciding it needs to see what the options actually are.
    // A character-creation screen needs the same enumeration for its own reasons.

    /// The ChrModel a race and sex resolve to. 0 when the tables pair them with none.
    uint32_t(__cdecl* ChrModelForRace)(uint32_t chrRaceId, uint32_t sex);

    /// Options a ChrModel offers, ordered as the tables order them. Index is 0-based and dense.
    uint32_t(__cdecl* OptionCount)(uint32_t chrModelId);
    int(__cdecl* OptionAt)(uint32_t chrModelId, uint32_t index, WXL_ChrOption* out);

    /// Choices one option offers, likewise ordered and dense.
    uint32_t(__cdecl* ChoiceCount)(uint32_t chrCustomizationOptionId);
    int(__cdecl* ChoiceAt)(uint32_t chrCustomizationOptionId, uint32_t index, WXL_ChrChoice* out);

    // --- the sheet a recipe's layers address ----------------------------------------------------

    /// The layout a ChrModel's textures are addressed in, 0 when it names none. Available without
    /// building a recipe on purpose: the sheet has to be sized before anything is painted into it,
    /// and at that moment the customization choices are not yet known.
    uint32_t(__cdecl* LayoutForModel)(uint32_t chrModelId);

    /// The sheet size one layout describes. @return nonzero when both were filled.
    int(__cdecl* LayoutSize)(uint32_t layoutId, uint32_t* outWidth, uint32_t* outHeight);

    /// Regions of one layout, ordered as the table orders them. Index is 0-based and dense.
    uint32_t(__cdecl* SectionCount)(uint32_t layoutId);
    int(__cdecl* SectionAt)(uint32_t layoutId, uint32_t index, WXL_TextureSection* out);

    /// The name a ChrCustomizationOption shows in the character-creation UI ("Hair Style", "Face").
    const char*(__cdecl* OptionName)(uint32_t chrCustomizationOptionId);
    /// The name one of an option's choices shows ("Bald", "None", "Goatee").
    const char*(__cdecl* ChoiceName)(uint32_t chrCustomizationChoiceId);
} WXL_AppearanceApi;

// LIFETIME. The three arrays a filled recipe points at belong to the resolver, not to the caller,
// and only until that thread's next Build call. A caller that keeps a recipe past its next question
// copies the arrays first. This is the same bargain wxl.fdid makes, minus the permanence: a resolved
// path is interned for the process because paths are few and repeat, whereas a recipe is one answer
// to one question and interning every one of them would grow without bound.

#ifdef __cplusplus
}
#endif

#endif // WXL_APPEARANCE_API_H
