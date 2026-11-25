"""Agronomic rules for wheat and rice — the single data file.

Every agronomic number the irrigation engine uses lives here, and every number
carries the source it came from. This module imports nothing but the standard
library and performs no I/O: it is data, so the agronomy can be reviewed by
reading one file, and so the engine that consumes it stays testable without a
network.

Sources used, and only these:

  * FAO-56 Table 11 — lengths of crop development stages.
  * FAO-56 Table 12 — single crop coefficients (Kc).
  * FAO-56 Table 22 — maximum effective root depth (Zr) and the soil water
    depletion fraction (p) at which the crop starts to suffer stress.
  * FAO-56 Table 19 — typical soil water characteristics (field capacity and
    wilting point) by USDA texture class.
  * TNAU Agritech Portal, Crop Production — Wheat: critical irrigation stages.
  * OPERATIONAL — a threshold this app chose for itself. It has no published
    source, and the UI shows it to the farmer as an assumption rather than
    passing it off as agronomic fact.

Deliberately absent: any ICAR or state-university citation that could not be
read at source. A citation nobody can check is worse than no citation, because
it borrows authority the rule may not have.

Wheat Kc uses the FAO-56 "winter wheat, non-frozen soils" column (0.70 / 1.15 /
0.40), which is the Indian rabi case; the frozen-soil column does not apply.
Stage lengths use the FAO-56 Table 11 row for wheat in Central India sown in
November (15/25/50/30, 120 days), and for rice the tropical row (30/30/60/30,
150 days).
"""

from dataclasses import dataclass


# Reference strings, so each citation is stated once and reused verbatim.
FAO56_T11 = (
    "FAO-56 (Allen et al. 1998), Table 11 — lengths of crop development stages"
)
FAO56_T12 = "FAO-56 (Allen et al. 1998), Table 12 — single crop coefficient Kc"
FAO56_T22 = (
    "FAO-56 (Allen et al. 1998), Table 22 — root depth Zr and depletion fraction p"
)
TNAU_WHEAT = (
    "TNAU Agritech Portal, Crop Production — Wheat (after cultivation): "
    "critical irrigation stages"
)
FAO56_T19 = (
    "FAO-56 (Allen et al. 1998), Table 19 — typical soil water characteristics by "
    "USDA soil texture class"
)
OPERATIONAL = (
    "Operational threshold set for this app — no published source; shown to the "
    "farmer as an assumption"
)


@dataclass(frozen=True)
class Rule:
    """One agronomic value together with where it came from.

    Keeping the citation attached to the value (rather than in a comment the
    value can drift away from) means the UI can render the provenance of any
    single number it shows.
    """

    value: float
    source: str
    note: str = ""


@dataclass(frozen=True)
class StageLengths:
    """Growth-stage lengths in days from sowing (FAO-56 Table 11)."""

    initial: int
    development: int
    mid: int
    late: int
    source: str = FAO56_T11

    @property
    def total(self) -> int:
        return self.initial + self.development + self.mid + self.late

    @property
    def mid_start(self) -> int:
        return self.initial + self.development

    @property
    def late_start(self) -> int:
        return self.mid_start + self.mid


@dataclass(frozen=True)
class CriticalWindow:
    """A period where water stress costs yield most, in days after sowing."""

    start_day: int
    end_day: int
    label: str
    source: str


@dataclass(frozen=True)
class CropRules:
    """Everything the water-balance engine needs for one crop."""

    key: str
    name_hi: str
    name_en: str
    stages: StageLengths
    kc_initial: Rule
    kc_mid: Rule
    kc_end: Rule
    root_depth_m: Rule
    depletion_fraction: Rule
    application_efficiency: Rule
    critical_windows: tuple[CriticalWindow, ...]

    def kc_for_age(self, age_days: int) -> float:
        """Kc for a given crop age, interpolated across the Kc curve.

        FAO-56 defines the curve as constant through the initial and mid
        stages and interpolated in between, so growth and ripening ramp rather
        than step.
        """
        s = self.stages
        ini = self.kc_initial.value
        mid = self.kc_mid.value
        end = self.kc_end.value

        if age_days <= s.initial:
            return ini
        if age_days <= s.mid_start:
            span = max(s.development, 1)
            return ini + (mid - ini) * (age_days - s.initial) / span
        if age_days <= s.late_start:
            return mid
        if age_days <= s.total:
            span = max(s.late, 1)
            return mid + (end - mid) * (age_days - s.late_start) / span
        return end

    def stage_name(self, age_days: int) -> str:
        # Boundaries use < rather than <= so the label agrees with kc_for_age:
        # on the first day of the mid season the Kc is already the mid value,
        # and the stage label must say "mid" too.
        s = self.stages
        if age_days <= s.initial:
            return "initial"
        if age_days < s.mid_start:
            return "development"
        if age_days < s.late_start:
            return "mid"
        if age_days <= s.total:
            return "late"
        return "harvested"

    def critical_window(self, age_days: int) -> CriticalWindow | None:
        """The critical window the crop is inside right now, if any."""
        for window in self.critical_windows:
            if window.start_day <= age_days <= window.end_day:
                return window
        return None


# --- soil water capacity ---------------------------------------------------

# Field capacity and wilting point by soil type, from FAO-56 Table 19, which
# tabulates each as a RANGE rather than a single number. A range is useless to
# an arithmetic engine, so these are the midpoints of the tabulated ranges and
# the note on each value says so. Read directly from the table:
#
#   USDA class      theta_FC        theta_WP
#   Sandy loam      0.18 - 0.28     0.06 - 0.16
#   Loam            0.20 - 0.30     0.07 - 0.17
#   Clay            0.32 - 0.40     0.20 - 0.24
#
# Table 19 has no class called plain "sandy" or "clay" in the loose sense the
# Hindi labels imply: it uses USDA texture classes. "Sandy" therefore maps to
# the Sandy loam row, which is named in `fao_class` on each soil so a reviewer
# can see exactly which row was used rather than having to trust the label.
# Pure "Sand" (holding only 0.05-0.11 m/m) is not a realistic field soil and is
# deliberately not offered.


@dataclass(frozen=True)
class SoilType:
    """A soil's water-holding capacity, as the engine needs it.

    Field capacity and wilting point are stored as volumetric fractions
    (m3/m3), which is the form Table 19 gives them. The available water the
    engine actually uses is their difference, computed rather than stored, so
    the two tabulated numbers stay the single source.
    """

    key: str
    name_hi: str
    name_en: str
    fao_class: str
    field_capacity: Rule
    wilting_point: Rule

    @property
    def available_water_mm_per_m(self) -> float:
        """Readily stored water in mm per metre of soil depth.

        (theta_FC - theta_WP) is a fraction of a metre; x1000 gives mm per
        metre of root zone.
        """
        return round((self.field_capacity.value - self.wilting_point.value) * 1000, 1)


SANDY = SoilType(
    key="sandy",
    name_hi="रेतीली",
    name_en="Sandy",
    fao_class="Sandy loam",
    field_capacity=Rule(0.23, FAO56_T19, "midpoint of the Sandy loam range 0.18-0.28"),
    wilting_point=Rule(0.11, FAO56_T19, "midpoint of the Sandy loam range 0.06-0.16"),
)

LOAM = SoilType(
    key="loam",
    name_hi="दोमट",
    name_en="Loam",
    fao_class="Loam",
    field_capacity=Rule(0.25, FAO56_T19, "midpoint of the Loam range 0.20-0.30"),
    wilting_point=Rule(0.12, FAO56_T19, "midpoint of the Loam range 0.07-0.17"),
)

CLAY = SoilType(
    key="clay",
    name_hi="चिकनी",
    name_en="Clay",
    fao_class="Clay",
    field_capacity=Rule(0.36, FAO56_T19, "midpoint of the Clay range 0.32-0.40"),
    wilting_point=Rule(0.22, FAO56_T19, "midpoint of the Clay range 0.20-0.24"),
)

SOILS: dict[str, SoilType] = {s.key: s for s in (SANDY, LOAM, CLAY)}
DEFAULT_SOIL_KEY = "loam"


def get_soil(key: str | None) -> SoilType:
    """Look a soil up by key, falling back to loam when unset or unrecognised.

    Returning the default rather than None keeps the engine total: there is
    always a soil, and the advice always says which one it used.
    """
    return SOILS.get((key or DEFAULT_SOIL_KEY).strip().lower(), LOAM)

# Spray and fertiliser decision thresholds. These are this app's own judgement
# calls, and are labelled as such rather than dressed in a citation.
SPRAY_RAIN_MM_24H = Rule(
    value=5.0,
    source=OPERATIONAL,
    note="rain above this in the next 24 h wets the leaf and washes off spray",
)
SPRAY_WIND_KMH = Rule(
    value=15.0,
    source=OPERATIONAL,
    note="above this, spray drifts off target and can damage neighbouring crops",
)
UREA_HEAVY_RAIN_MM_48H = Rule(
    value=20.0,
    source=OPERATIONAL,
    note="heavy rain after urea leaches the nitrogen below the root zone",
)


# --- wheat -----------------------------------------------------------------

WHEAT = CropRules(
    key="wheat",
    name_hi="गेहूँ",
    name_en="Wheat",
    stages=StageLengths(initial=15, development=25, mid=50, late=30),
    kc_initial=Rule(0.70, FAO56_T12, "winter wheat, non-frozen soils"),
    kc_mid=Rule(1.15, FAO56_T12, "winter wheat, non-frozen soils"),
    kc_end=Rule(0.40, FAO56_T12, "winter wheat, upper end of the 0.25-0.40 range"),
    root_depth_m=Rule(
        1.0,
        FAO56_T22,
        "lower end of the 1.0-1.5 m range: shallower roots deplete sooner, "
        "which errs toward irrigating rather than withholding water",
    ),
    depletion_fraction=Rule(0.55, FAO56_T22, "p for wheat"),
    application_efficiency=Rule(
        0.7,
        OPERATIONAL,
        "surface/flood application; gross = net / efficiency",
    ),
    critical_windows=(
        CriticalWindow(15, 20, "crown root initiation", TNAU_WHEAT),
        CriticalWindow(35, 40, "active tillering", TNAU_WHEAT),
        CriticalWindow(50, 55, "flowering", TNAU_WHEAT),
        CriticalWindow(70, 75, "grain filling", TNAU_WHEAT),
    ),
)


# --- rice ------------------------------------------------------------------

# Rice carries no state-university citation here: the university pages that
# would carry it were not reachable when this file was written, so its critical
# window is derived from the FAO-56 Table 11 stage boundaries instead of being
# asserted. It spans the reproductive period (end of vegetative growth through
# flowering), which is where Table 11 places panicle initiation and flowering.
RICE = CropRules(
    key="rice",
    name_hi="धान",
    name_en="Rice",
    stages=StageLengths(initial=30, development=30, mid=60, late=30),
    kc_initial=Rule(1.05, FAO56_T12, "rice, tropical"),
    kc_mid=Rule(1.20, FAO56_T12, "rice, tropical"),
    kc_end=Rule(0.90, FAO56_T12, "rice, upper end of the 0.90-0.60 range"),
    root_depth_m=Rule(0.5, FAO56_T22, "lower end of the 0.5-1.0 m range"),
    depletion_fraction=Rule(
        0.20, FAO56_T22, "p for rice: a paddy tolerates very little depletion"
    ),
    application_efficiency=Rule(
        0.7,
        OPERATIONAL,
        "surface/flood application; gross = net / efficiency",
    ),
    critical_windows=(
        CriticalWindow(60, 100, "panicle initiation to flowering", FAO56_T11),
    ),
)


CROPS: dict[str, CropRules] = {WHEAT.key: WHEAT, RICE.key: RICE}


def get_crop(key: str) -> CropRules | None:
    """Look a crop up by its API key, or None if it is not supported."""
    return CROPS.get((key or "").strip().lower())
