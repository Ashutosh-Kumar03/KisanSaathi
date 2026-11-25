"""Hindi and English narration for a decision the engine already made.

This module turns numbers into sentences. It never decides anything, never
calls a network, and never alters a figure it is handed. That separation is the
core rule of the project: a language model may not compute the recommendation,
and the safest way to guarantee that is for the narration layer to have no way
of computing anything at all.

Deliberately not an LLM call. An LLM would add a key to configure, a latency
spike in the critical path, a cost per request, and a failure mode where a
farmer's phone shows nothing because a provider is down. The sentences a farmer
needs are few and fixed, so they are written here and translated once, in the
voice of someone standing in the field rather than a form letter.

Both languages are written by hand, not machine-translated. Hindi is the
primary text, not a subtitle: it is what the voice reads out and what the
farmer reads first. English exists for the toggle, and is generated from the
same numbers so the two can never disagree about the amount of water.

Numbers are formatted the Indian way (1,30,000 rather than 130,000), because a
lakh-grouped figure is what the reader recognises.
"""

from .irrigation import Advice

ACTION_IRRIGATE = "IRRIGATE_TODAY"
ACTION_WAIT_RAIN = "WAIT_RAIN"
ACTION_OK = "SOIL_MOISTURE_OK"
ACTION_OVER = "SEASON_OVER"


def format_indian(number: int) -> str:
    """Group an integer the Indian way: 1,30,000 rather than 130,000.

    The last three digits stay together, then pairs: a farmer reading a pump
    figure knows a lakh when they see one.
    """
    negative = number < 0
    digits = str(abs(int(number)))
    if len(digits) <= 3:
        grouped = digits
    else:
        head, tail = digits[:-3], digits[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        grouped = ",".join(parts + [tail])
    return f"-{grouped}" if negative else grouped


def _mm(value: float) -> str:
    """Millimetres, without a trailing .0 that reads as false precision."""
    return f"{value:.0f}" if abs(value - round(value)) < 0.05 else f"{value:.1f}"


def _stage_hi(stage: str) -> str:
    return {
        "initial": "शुरुआती अवस्था",
        "development": "बढ़वार की अवस्था",
        "mid": "फसल की मुख्य अवस्था",
        "late": "पकने की अवस्था",
        "harvested": "कटाई का समय",
    }.get(stage, stage)


def _stage_en(stage: str) -> str:
    return {
        "initial": "early growth",
        "development": "growing stage",
        "mid": "main growth stage",
        "late": "ripening stage",
        "harvested": "harvest time",
    }.get(stage, stage)


def _critical_hi(advice: Advice) -> str:
    if not advice.in_critical_window:
        return ""
    return (
        f" यह {advice.critical_window_label} का समय है — इस अवस्था में पानी की कमी "
        "से उपज पर सीधा असर पड़ता है।"
    )


def _critical_en(advice: Advice) -> str:
    if not advice.in_critical_window:
        return ""
    return (
        f" This is the {advice.critical_window_label} stage, when a water shortage "
        "cuts yield most."
    )


def irrigate_hindi(advice: Advice) -> str:
    return (
        f"आज सिंचाई करें। {advice.crop_name_hi} की {advice.age_days} दिन की फसल में "
        f"लगभग {_mm(advice.gross_mm)} मिमी पानी दें, यानी करीब "
        f"{format_indian(advice.litres_per_acre)} लीटर प्रति एकड़।"
        f"{_critical_hi(advice)}"
    )


def irrigate_english(advice: Advice) -> str:
    return (
        f"Irrigate today. Give about {_mm(advice.gross_mm)} mm of water — roughly "
        f"{format_indian(advice.litres_per_acre)} litres per acre — to your "
        f"{advice.age_days}-day-old {advice.crop_name_en.lower()} crop."
        f"{_critical_en(advice)}"
    )


def wait_rain_hindi(advice: Advice) -> str:
    return (
        f"आज सिंचाई न करें। अगले 24 घंटे में करीब {_mm(advice.rain_next_24h_mm)} मिमी "
        "बारिश का अनुमान है, जो फसल के लिए काफी है। बारिश के बाद मिट्टी देखकर "
        "फिर तय करें।"
        f"{_critical_hi(advice)}"
    )


def wait_rain_english(advice: Advice) -> str:
    return (
        f"Do not irrigate today. About {_mm(advice.rain_next_24h_mm)} mm of rain is "
        "forecast in the next 24 hours, which is enough for the crop. Check the soil "
        "again after it rains."
        f"{_critical_en(advice)}"
    )


def ok_hindi(advice: Advice) -> str:
    return (
        f"आज सिंचाई की ज़रूरत नहीं है। खेत में अभी नमी ठीक है — "
        f"{_stage_hi(advice.stage)} में पानी की कमी नहीं है। अगले कुछ दिन मौसम देखते "
        "रहें।"
        f"{_critical_hi(advice)}"
    )


def ok_english(advice: Advice) -> str:
    return (
        "No irrigation needed today. Soil moisture is adequate — your crop is in the "
        f"{_stage_en(advice.stage)} and is not short of water. Keep watching the "
        "weather over the next few days."
        f"{_critical_en(advice)}"
    )


def over_hindi(advice: Advice) -> str:
    return (
        f"{advice.crop_name_hi} की फसल अपनी अवधि पूरी कर चुकी है "
        f"({advice.age_days} दिन)। अब सिंचाई की सलाह नहीं दी जा सकती — कटाई और "
        "भंडारण पर ध्यान दें।"
    )


def over_english(advice: Advice) -> str:
    return (
        f"Your {advice.crop_name_en.lower()} crop has passed the end of its season "
        f"({advice.age_days} days). Irrigation advice no longer applies — focus on "
        "harvest and storage."
    )


def soil_line(advice: Advice) -> tuple[str, str]:
    """Which soil the balance used, and whether it was assumed.

    Stated in both languages because it changes the answer rather than merely
    annotating it: sandy soil holds far less water than clay, so the same
    forecast can mean irrigate on one and wait on the other.
    """
    capacity = f"{advice.soil_available_water_mm_per_m:.0f} mm/m"
    if advice.soil_is_default:
        return (
            f"मिट्टी नहीं चुनी गई, इसलिए दोमट (loam) मानी गई — उपलब्ध पानी {capacity}।",
            f"No soil was chosen, so loam is assumed — {capacity} of available water.",
        )
    return (
        f"मिट्टी: {advice.soil_name_hi} ({advice.soil_name_en}), "
        f"उपलब्ध पानी {capacity}।",
        f"Soil: {advice.soil_name_en} — {capacity} of available water.",
    )


def irrigation_line(advice: Advice) -> tuple[str, str]:
    """What the balance assumed about the last irrigation.

    Three distinct cases, and they must not be confused: no irrigation at all,
    an irrigation refilling the profile, and a stated amount of which only part
    was held by the soil. The third is the one worth spelling out — a farmer who
    put down 80 mm on a field that was 20 mm short will otherwise believe they
    banked 80.
    """
    if advice.last_irrigation_date is None:
        return (
            "यह सलाह मानती है कि बोने के बाद से सिंचाई नहीं हुई।",
            "This advice assumes no irrigation since sowing.",
        )

    day = advice.last_irrigation_date.strftime("%d-%m-%Y")
    if advice.last_irrigation_mm is None:
        return (
            f"गणना में माना गया: पिछली सिंचाई {day} को हुई थी और उससे मिट्टी में पानी पूरा भर गया।",
            f"Calculated assuming you last irrigated on {day} and refilled the soil.",
        )

    applied = f"{advice.last_irrigation_mm:.0f} mm"
    held = f"{advice.last_irrigation_effective_mm:.0f} mm"
    lost = advice.last_irrigation_mm - advice.last_irrigation_effective_mm

    hindi = (
        f"गणना में माना गया: {day} को {applied} पानी दिया, जिसमें से {held} मिट्टी ने रोका"
    )
    english = f"Calculated assuming {applied} applied on {day}, of which the soil held {held}"
    if lost > 0.5:
        hindi += f"; बाकी {lost:.0f} मिमी जड़ों के नीचे बह गया"
        english += f"; the remaining {lost:.0f} mm drained past the roots"
    return hindi + "।", english + "."


def narrate(advice: Advice) -> tuple[str, str]:
    """Return (hindi, english) for an advice.

    A separate branch per action rather than one f-string with a placeholder:
    the WAIT_RAIN wording must never be able to leak into an irrigate-today
    decision through a formatting mistake, because the two say opposite things.
    """
    if advice.action == ACTION_IRRIGATE:
        return irrigate_hindi(advice), irrigate_english(advice)
    if advice.action == ACTION_WAIT_RAIN:
        return wait_rain_hindi(advice), wait_rain_english(advice)
    if advice.action == ACTION_OVER:
        return over_hindi(advice), over_english(advice)
    return ok_hindi(advice), ok_english(advice)


def headline(advice: Advice) -> tuple[str, str]:
    """The two or three words that are the decision itself."""
    mapping = {
        ACTION_IRRIGATE: ("आज सिंचाई करें", "Irrigate today"),
        ACTION_WAIT_RAIN: ("आज पानी न दें", "Wait — rain is coming"),
        ACTION_OK: ("आज पानी की ज़रूरत नहीं", "No irrigation needed today"),
        ACTION_OVER: ("फसल की अवधि पूरी", "Season complete"),
    }
    return mapping.get(advice.action, ("सलाह उपलब्ध नहीं", "No advice available"))
