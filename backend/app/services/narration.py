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


def next_irrigation_line(advice: Advice) -> tuple[str, str]:
    """When water is next likely to be needed, within the forecast only.

    Three outcomes, and the third is the one that must not be dressed up: if the
    deficit does not reach the stress point on any day we have weather for, the
    answer is "not within the next few days", never a date extrapolated from
    weather that does not exist.
    """
    if advice.action == "SEASON_OVER":
        return (
            "फसल की अवधि पूरी हो चुकी है, इसलिए आगे की सिंचाई की सलाह नहीं दी जा सकती।",
            "The season is over, so no further irrigation can be advised.",
        )

    if advice.next_irrigation_date is None:
        until = advice.forecast_covered_until
        span = (
            f"{until.strftime('%d-%m')} तक" if until else "उपलब्ध दिनों में"
        )
        return (
            f"अगले कुछ दिनों में पानी की ज़रूरत नहीं दिख रही ({span} का पूर्वानुमान)। "
            "इससे आगे का अंदाज़ा नहीं लगाया गया।",
            f"No irrigation looks necessary within the forecast (up to "
            f"{until.strftime('%d-%m') if until else 'the available days'}). "
            f"Nothing beyond that window is extrapolated.",
        )

    day = advice.next_irrigation_date.strftime("%d-%m-%Y")
    mm = f"{advice.next_irrigation_mm:.0f} mm"
    if advice.next_irrigation_date == advice.today:
        return (
            "पानी आज ही चाहिए — मिट्टी की नमी सीमा तक पहुँच चुकी है।",
            "Water is needed today — soil moisture has reached the stress point.",
        )
    return (
        f"अगली सिंचाई करीब {day} को चाहिए होगी (करीब {mm}) — यह मौजूदा पूर्वानुमान के "
        "हिसाब से है, मौसम बदले तो बदल सकता है।",
        f"Next irrigation is likely needed around {day} (about {mm}). This is "
        "based on the current forecast, so it can move if the weather does.",
    )


def usual_interval_line(advice: Advice) -> tuple[str, str] | None:
    """Compare the projected gap with the farmer's own habit.

    Presentation only. This number never enters the balance — the engine's
    arithmetic is the same whether or not the farmer states a habit, and a test
    asserts exactly that. It exists because a farmer who always waters every 12
    days and is now being told to wait 18 is more likely to trust the advice if
    the difference is named than if it is left for them to notice.

    Returns None when no habit was given, so the UI can omit the line rather
    than print a comparison against nothing.
    """
    if advice.usual_interval_days is None or advice.next_irrigation_date is None:
        return None

    gap = (advice.next_irrigation_date - advice.today).days
    usual = advice.usual_interval_days

    if gap == usual:
        return (
            f"आप आमतौर पर हर {usual} दिन में सिंचाई करते हैं, और यह सलाह भी करीब "
            f"{gap} दिन कहती है — दोनों मेल खाते हैं।",
            f"You usually irrigate every {usual} days and this advice also points to "
            f"about {gap} — the two agree.",
        )

    if gap > usual:
        return (
            f"आप आमतौर पर हर {usual} दिन में सिंचाई करते हैं, पर इस बार सलाह करीब "
            f"{gap} दिन कहती है — यानी इस बार थोड़ा रुकना बेहतर है।",
            f"You usually irrigate every {usual} days, but this time the advice points "
            f"to about {gap} — waiting a little longer is better here.",
        )

    return (
        f"आप आमतौर पर हर {usual} दिन में सिंचाई करते हैं, पर इस बार सलाह करीब "
        f"{gap} दिन कहती है — यानी इस बार जल्दी पानी की ज़रूरत है।",
        f"You usually irrigate every {usual} days, but this time the advice points to "
        f"about {gap} — water is needed sooner than usual.",
    )


SAVINGS_LABEL_HI = "अनुमान: आपकी अपनी आदत और मॉडल की सलाह की तुलना"
SAVINGS_LABEL_EN = "Estimate: comparing your own habit with the model's advice"


def savings_lines(savings) -> tuple[str, str]:
    """Narrate the savings comparison, including the negative case.

    A negative saving is reported as such rather than clamped to zero or hidden:
    if the farmer's habit is already using less water than the advice would, that
    is useful information and hiding it would make the whole panel untrustworthy.
    """
    if savings.saved_mm > 0:
        hindi = (
            f"आपकी आदत में {savings.habit_total_mm:.0f} मिमी पानी लगता "
            f"({savings.habit_irrigations} बार), और सलाह से {savings.advised_total_mm:.0f} मिमी "
            f"({savings.advised_irrigations} बार)। यानी करीब {savings.saved_mm:.0f} मिमी, "
            f"यानी {format_indian(savings.saved_litres_per_acre)} लीटर प्रति एकड़ पानी बच सकता है।"
        )
        english = (
            f"Your habit uses {savings.habit_total_mm:.0f} mm ({savings.habit_irrigations} "
            f"irrigations); the advice uses {savings.advised_total_mm:.0f} mm "
            f"({savings.advised_irrigations}). That is about {savings.saved_mm:.0f} mm — "
            f"{format_indian(savings.saved_litres_per_acre)} litres per acre you could save."
        )
    elif savings.saved_mm == 0:
        hindi = (
            "आपकी आदत और सलाह से लगभग बराबर पानी लगता है — कोई ख़ास बचत नहीं दिख रही।"
        )
        english = (
            "Your habit and the advice use about the same amount of water — no "
            "meaningful saving either way."
        )
    else:
        extra = abs(savings.saved_mm)
        hindi = (
            f"आपकी आदत में {savings.habit_total_mm:.0f} मिमी पानी लगता है, जो सलाह से "
            f"करीब {extra:.0f} मिमी कम है। यानी आप पहले से कम पानी दे रहे हैं — "
            "सलाह ज़्यादा पानी कह रही है।"
        )
        english = (
            f"Your habit uses {savings.habit_total_mm:.0f} mm, about {extra:.0f} mm less "
            f"than the advice. You are already applying less water than advised."
        )

    if savings.pump_hours_saved is not None and savings.money_saved is not None:
        money = format_indian(int(round(savings.money_saved)))
        hindi += (
            f" पंप करीब {savings.pump_hours_saved:.1f} घंटे कम चलेगा, यानी करीब ₹{money} की बचत।"
        )
        english += (
            f" The pump would run about {savings.pump_hours_saved:.1f} hours less — "
            f"roughly ₹{money} saved."
        )
    return hindi, english


def savings_money_reason(savings) -> tuple[str, str] | None:
    """Why rupees are missing, in words, so the gap is explained not ignored."""
    if savings.pump_hours_saved is not None:
        return None
    if savings.money_unavailable_reason == "both":
        return (
            "₹ की बचत दिखाने के लिए पंप की क्षमता (लीटर/घंटा) और प्रति घंटे की लागत, दोनों भरें।",
            "To show savings in rupees, fill in both the pump discharge (litres/hour) "
            "and the cost per hour.",
        )
    return (
        "पंप और बिजली-डीज़ल की जानकारी नहीं दी गई, इसलिए बचत सिर्फ़ पानी में दिखाई गई है — "
        "रुपये में नहीं।",
        "No pump or fuel details were given, so the saving is shown in water only, "
        "not in rupees.",
    )


def savings_prompt() -> tuple[str, str]:
    """What to ask for when no habit is stated and no savings can be computed."""
    return (
        "बचत देखने के लिए बताइए: आप आमतौर पर कितने दिन में सिंचाई करते हैं और "
        "हर बार कितना पानी देते हैं। ये दोनों भरे बिना कोई बचत नहीं दिखाई जा सकती।",
        "To see your savings, tell us how often you usually irrigate and how much "
        "water you apply each time. Without both, no saving can be shown.",
    )


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
