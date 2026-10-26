-- WindowSkinExample: one whole window, the Cube, drawn on this skin's own canvas (Torment/SKINNING.md,
-- "Windows"). media/mycube.tga is a plain placeholder made by make_placeholder.py; a skin of your own puts its own window picture there under any name.
--
-- Every number below is a pixel of that picture, measured from its top-left corner:
--   width, height  the canvas: the part of the picture that is the window (the file is 256 x 512,
--                  a power of two, and the window is its top 256 x 400)
--   coords         the same crop for the texture: right = 256/256, bottom = 400/512
--   anchors        where the window's pieces go on the canvas, each {left, top, width, height}:
--                  content  where the Cube's own body is drawn (its slots and lines, as they are)
--                  title    the window's title text
--                  close    the close button
--                  buttons  one spot per button, in the window's order (the Cube: Transmute, then
--                           the recipe book)
-- Torment fits `content` to the window's width and draws the whole canvas at that one scale.
local ART = Diablocraft.ART
local MEDIA = [[Interface\AddOns\WindowSkinExample\media\]]

ART["window-cube"] = {
    path = MEDIA .. "mycube",
    width = 256, height = 400,
    coords = {0, 1, 0, 400 / 512},
    anchors = {
        content = {left = 21, top = 36, width = 214, height = 328},
        title = {left = 21, top = 8, width = 214, height = 22},
        close = {left = 232, top = 8, width = 18, height = 18},
        buttons = {
            {left = 78, top = 370, width = 100, height = 18},
            {left = 200, top = 368, width = 22, height = 22},
        },
    },
}
