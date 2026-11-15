"""Chooses which satellite views to show, so the farmer never has to pick a NASA product.

The choice uses the farmer's answers (priorities, soil cover) and what weighs most in each plot's result.
It returns view keys and reason codes; the page maps them to NASA GIBS layers and plain-language texts.
The views are for looking only: they never feed the index.
"""

# A plot's own top risk (3 points) outweighs what the farmer ticked (1 point each).
# Fixed order breaks ties: the first views are the most generally useful.
VIEWS = ["soil_moisture", "greenness", "rain", "ground_heat", "satellite_photo"]
MAX_VIEWS = 2


def choose_views(farm, plots):
    score = {v: 0 for v in VIEWS}
    reasons = {v: [] for v in VIEWS}

    def add(view, points, reason):
        score[view] += points
        if reason not in reasons[view]:
            reasons[view].append(reason)

    top = {v for p in plots for v in p.get("top_variables", [])}
    priorities = {pr for p in farm.get("plots", []) for pr in p.get("priorities") or []}
    covers = {p.get("current_cover") for p in farm.get("plots", [])}

    if top & {"dry_spell", "moisture"}:
        add("soil_moisture", 3, "top_water")
        add("rain", 1, "top_water")
    if "heat" in top:
        add("ground_heat", 3, "top_heat")
    if "erosion" in top:
        add("satellite_photo", 3, "top_erosion")
        add("greenness", 1, "top_erosion")
    if "greenness" in top:
        add("greenness", 3, "top_greenness")
    if "water" in priorities:
        add("soil_moisture", 1, "priority_water")
        add("rain", 1, "priority_water")
    if "erosion" in priorities:
        add("satellite_photo", 1, "priority_erosion")
        add("greenness", 1, "priority_erosion")
    if "nitrogen" in priorities:
        add("greenness", 1, "priority_nitrogen")
    if "bare_soil" in covers:
        add("satellite_photo", 1, "bare_soil")

    chosen = sorted((v for v in VIEWS if score[v] > 0), key=lambda v: (-score[v], VIEWS.index(v)))[:MAX_VIEWS]
    if not chosen:
        return [{"view": "greenness", "reasons": ["default"]}, {"view": "soil_moisture", "reasons": ["default"]}]
    return [{"view": v, "reasons": reasons[v]} for v in chosen]
