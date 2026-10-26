"""The two spellings of a D3 class name the data and the code use ("Demon Hunter" is the first name of two words).

sheet_stem: the stem of a class's data sheets, docs and folders (demon_hunter_skills.csv, src/classes/demon_hunter/).
item_key: the class key base_items.csv, class_starts.csv and class_proficiency_ids.csv spell it by (usable_by,
designated_class: demonhunter). A one-word name is the same in both and is the lower-cased name.
"""


def sheet_stem(d3_class):
    return d3_class.strip().lower().replace(" ", "_")


def item_key(d3_class):
    return d3_class.strip().lower().replace(" ", "")
