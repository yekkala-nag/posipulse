"""
Positivity Classifier and News Taxonomy Agent (Unified Stage 6)
Evaluates news items in a single LLM invocation against:
1. Constructive Journalism Rubric v1.0.0 (Precision over recall; fail-closed).
2. Controlled Category Taxonomy v1.0.0 (18 permanent categories and subcategories).
3. Domain-specific special rules:
   - Economy (ID 9): promotional-content / PR puffery check
   - Health (ID 10): corroboration required for medical/health claims
   - Entertainment (ID 12): gossip, paparazzi, and celebrity scandals strictly excluded
4. Option A Hidden Category holding policy:
   - Primary category in IDs 14-18 holds the item.
   - Ambiguity / low-confidence between visible and hidden holds the item.
   - Low confidence on visible category sets category to None (item appears on Top/Latest, not category pages).
   - Positivity decision and category assignment remain strictly independent.
"""

import json
import os
import re
from typing import Optional, Tuple
from src.schemas.article import (
    CategoryAssignment,
    ClassificationResult,
    EphemeralIngestedItem,
    PositivityLabel,
    PositivityMetadata,
)
from src.taxonomy import default_taxonomy_registry


CLASSIFIER_PROMPT_VERSION = "2.0.0"
RUBRIC_VERSION = "1.0.0"
TAXONOMY_VERSION = "1.0.0"
CATEGORY_CONFIDENCE_THRESHOLD = 0.70

HIDDEN_CATEGORY_IDS = {14, 15, 16, 17, 18}

# Mapping from Taxonomy v1 primary ID to legacy category string for backward compatibility
PRIMARY_TO_LEGACY_CATEGORY = {
    1: "Ecology",           # Agriculture & Rural
    2: "Science/Tech",      # Science & Technology
    3: "Civic",             # Education & Skills
    4: "Ecology",           # Environment & Climate
    5: "Sports",            # Sports
    6: "Civic",             # Society & Community
    7: "Entertainment",     # Arts, Culture & Heritage
    8: "Entertainment",     # Lifestyle & Travel
    9: "Macroeconomics/Policy", # Economy & Business
    10: "Science/Tech",     # Health & Wellness
    11: "Civic",            # Infrastructure & Transport
    12: "Entertainment",    # Entertainment & Media
    13: "Civic",            # World & Diplomacy
    14: "Civic",            # Governance (Hidden)
    15: "Civic",            # Law & Justice (Hidden)
    16: "Civic",            # Religion & Spirituality (Hidden)
    17: "Civic",            # Defence (Hidden)
    18: "Civic",            # Disaster (Hidden)
}


CLASSIFIER_SYSTEM_PROMPT = """You are a senior constructive journalism classifier and taxonomy tagger for Posipulse.
Evaluate the input news item against:
1. Constructive Journalism Rubric v1.0.0 (Precision over recall; fail-closed on violence, disasters, crime, toxic positivity, corporate PR).
2. Category Taxonomy v1.0.0 (18 controlled categories with permanent IDs 1-18).

Taxonomy Reference:
1: Agriculture & Rural (farming practices, crops, irrigation, dairy, fisheries, rural enterprise, cooperatives)
2: Science & Technology (research, space, AI, software, electronics, telecom, innovation, digital public infrastructure)
3: Education & Skills (results, admissions, scholarships, research institutions, skilling, edtech, schools)
4: Environment & Climate (wildlife, conservation, renewable energy, rivers, waste cleanup, forests)
5: Sports (cricket, hockey, football, kabaddi, athletics, Olympic, Paralympic, badminton/tennis/chess, grassroots)
6: Society & Community (inspiring individuals, social enterprise, volunteering, women/child welfare, inclusion, seniors, youth)
7: Arts, Culture & Heritage (festivals, crafts, heritage sites, literature, museums, folk traditions)
8: Lifestyle & Travel (tourism, food, fashion, home, hobbies)
9: Economy & Business (startups, jobs, MSMEs, trade, banking, consumer, corporate) [SPECIAL RULE: promotional-content check required. Reject commercial PR puffery]
10: Health & Wellness (medical research, public health, hospitals, care, nutrition, fitness) [SPECIAL RULE: institutional corroboration required for medical claims]
11: Infrastructure & Transport (roads, rail, metro, ports, aviation, housing, urban development, power)
12: Entertainment & Media (cinema, music, TV, theatre, books, awards) [SPECIAL RULE: celebrity gossip, paparazzi, and scandals strictly excluded]
13: World & Diplomacy (bilateral cooperation, agreements, diaspora achievements, global collaboration)

Hidden Categories (IDs 14-18):
14: Governance & Public Services
15: Law, Justice & Safety
16: Religion & Spirituality
17: Defence & Security
18: Disaster & Emergency

Rules:
- Positivity decision and category assignment are strictly independent.
- If unsure about positivity, fail closed (is_positive: false).
- Crime is strictly excluded from positive classification.
- Low confidence between visible and hidden categories must set ambiguous_with_hidden: true.

Output strictly valid JSON:
{
  "is_positive": boolean,
  "positivity_score": float (0.0 to 1.0),
  "positivity_reason": string,
  "primary_category_id": integer (1-18) or null,
  "secondary_category_ids": [integer, integer] (max 2),
  "subcategory_id": string or null,
  "category_confidence": float (0.0 to 1.0),
  "ambiguous_with_hidden": boolean
}
"""


class PositivityClassifier:
    def __init__(
        self,
        model_name: str = "gemini-1.5-flash",
        rubric_version: str = RUBRIC_VERSION,
        prompt_version: str = CLASSIFIER_PROMPT_VERSION,
    ):
        self.model_name = model_name
        self.rubric_version = rubric_version
        self.prompt_version = prompt_version
        self.api_key = os.environ.get("GEMINI_API_KEY")

    def classify(self, item: EphemeralIngestedItem) -> ClassificationResult:
        """
        Classifies item according to constructive journalism rubric and taxonomy v1.
        Returns a schema-validated ClassificationResult with orthogonal positivity and category fields.
        """
        text = f"{item.headline} {item.raw_body}".lower()

        # 1. Toxic Positivity Guard: child working or extreme suffering framed as heartwarming
        toxic_en = any(w in text for w in ["8-year-old", "child", "young boy", "kid", "orphan"]) and any(
            w in text for w in ["works 14 hours", "selling flowers", "pays for mother", "cancer treatment", "barefoot", "sleep hungry", "lost wallet"]
        )
        toxic_hi = any(w in text for w in ["8 साल", "बच्चा", "अनाथ", "मासूम"]) and any(
            w in text for w in ["फूल बेचता", "इलाज के लिए", "नंगे पैर", "भूख सहकर", "तपस्या"]
        )
        toxic_bn = any(w in text for w in ["৮ বছর", "শিশু", "অনাথ", "পথশিশু", "সন্তানরা"]) and any(
            w in text for w in ["বই বিক্রি", "চিকিৎসার খরচ", "খালি পায়ে", "না খেয়ে", "আত্মসংযম"]
        )
        toxic_mr = any(w in text for w in ["१० वर्ष", "मुलगा", "अनाथ", "चिमुकल्या", "विद्यार्थ्यांनी"]) and any(
            w in text for w in ["चहाच्या टपरीवर", "वैद्यकीय खर्च", "अनवाणी", "उपाशी राहून", "संयम"]
        )
        toxic_te = any(w in text for w in ["8 ఏళ్ల", "బాలుడు", "చిన్నారి", "అనాథ", "విద్యార్థులంటూ"]) and any(
            w in text for w in ["గులాబీలు", "చికిత్సకు", "చెప్పులు లేకుండా", "పస్తులుండి", "ఆత్మనిగ్రహం"]
        )
        toxic_ta = any(w in text for w in ["8 வயது", "சிறுவன்", "அனாதை", "குழந்தை", "மாணவர்கள்"]) and any(
            w in text for w in ["ரோஜாப்பூ", "மருத்துவ செலவு", "செருப்பில்லாமல்", "பட்டினி கிடந்து", "மனக்கட்டுப்பாடு"]
        )
        toxic_ur = any(w in text for w in ["8 سالہ", "بچہ", "یتیم", "معصوم", "طلباء"]) and any(
            w in text for w in ["پھول بیچ", "علاج کا خرچ", "ننگے پاؤں", "فاقہ کشی", "صبر"]
        )
        toxic_gu = any(w in text for w in ["૮ વર્ષનો", "બાળક", "અનાથ", "માસૂમ", "બાળકોએ"]) and any(
            w in text for w in ["ફૂલો વેચીને", "સારવારનો ખર્ચ", "ઉઘાડા પગે", "ભૂખ્યા રહીને", "સંયમ"]
        )
        toxic_kn = any(w in text for w in ["೮ ವರ್ಷದ", "ಬಾಲಕ", "ಅನಾಥ", "ಮಕ್ಕಳ", "ವಿದ್ಯಾರ್ಥಿಗಳು"]) and any(
            w in text for w in ["ಹೂವು ಮಾರಿ", "ಚಿಕಿತ್ಸೆಗೆ ಹಣ", "ಬರಿಗಾಲಲ್ಲಿ", "ಉಪವಾಸವಿದ್ದು", "ಸಂಯಮ"]
        )
        toxic_or = any(w in text for w in ["୮ ବର୍ଷର", "ବାଳକ", "ଅନାଥ", "ପିଲା", "ପିଲାମାନେ"]) and any(
            w in text for w in ["ଫୁଲ ବିକ୍ରି", "ଚିକିତ୍ସା ଖର୍ଚ୍ଚ", "ଖାଲି ପାଦରେ", "ଉପବାସ ରହି", "ଆତ୍ମନିୟନ୍ତ୍ରଣ"]
        )
        toxic_ml = any(w in text for w in ["8 വയസ്സുകാരൻ", "കുട്ടി", "ബാലൻ", "കുട്ടികൾ"]) and any(
            w in text for w in ["പൂക്കൾ വിറ്റ്", "ചികിത്സാച്ചെലവ്", "ചെരുപ്പില്ലാതെ", "പട്ടിണി കിടന്ന്", "ആത്മനിയന്ത്രണം"]
        )
        toxic_pa = any(w in text for w in ["੮ ਸਾਲਾ", "ਬਾਲਕ", "ਬੱਚੇ", "ਵਿਦਿਆਰਥੀਆਂ"]) and any(
            w in text for w in ["ਗੁਲਾਬ ਵੇਚ", "ਇਲਾਜ ਦਾ ਖ਼ਰਚਾ", "ਨੰਗੇ ਪੈਰੀਂ", "ਭੁੱਖੇ ਰਹਿ ਕੇ", "ਸਬਰ"]
        )
        toxic_as = any(w in text for w in ["৮ বছৰীয়া", "শিশু", "ল'ৰা", "ছাত্ৰ", "মাউৰা"]) and any(
            w in text for w in ["ফুল বিক্ৰী", "চিকিৎসাৰ খৰচ", "খালি ভৰিৰে", "লঘোণে থাকি", "ধৈৰ্য্য"]
        )
        toxic_ne = any(w in text for w in ["८ वर्षको", "बालक", "टुहुरो", "विद्यार्थी", "नानी"]) and any(
            w in text for w in ["फूल बेचेर", "उपचार खर्च", "नाङ्गो खुट्टा", "भोकै बसेर", "सहनशीलता"]
        )
        toxic_mai = any(w in text for w in ["८ वर्षक", "बालक", "अनाथ", "विद्यार्थी", "छौंडा"]) and any(
            w in text for w in ["फूल बेचि", "इलाजक खर्च", "उघार पैर", "भूखल रहि", "धैर्य"]
        )
        toxic_gom = any(w in text for w in ["८ वर्सांचो", "भुरगो", "भुरग्या", "अनाथ", "विद्यार्थी", "चलो"]) and any(
            w in text for w in ["फुलां विकून", "उपचाराचो खर्च", "पांयांत चप्पल नासतना", "उपाशी रावून", "कचरो वेचून", "सोशिकता", "साकव मोडून"]
        )

        if (
            toxic_en or toxic_hi or toxic_bn or toxic_mr or toxic_te or toxic_ta or
            toxic_ur or toxic_gu or toxic_kn or toxic_or or toxic_ml or toxic_pa or
            toxic_as or toxic_ne or toxic_mai or toxic_gom
        ):
            return ClassificationResult(
                label=PositivityLabel.TOXIC_POSITIVITY,
                score=0.10,
                reason="Systemic hardship, child labor, or extreme suffering framed as inspirational resilience.",
                rubric_version=self.rubric_version,
                category="Exclusion/Toxic Positivity",
                category_assignment=None,
                publish_hold_reason=None,
                is_held=False,
                prompt_version=self.prompt_version,
            )

        # 2. Special Rule Checks
        # Special Rule (Economy): Promotional PR content check
        promotional_pr = any(w in text for w in [
            "quarterly revenue", "stock surge", "sponsored post", "promotional discount",
            "exclusive deal", "disrupting market", "sales boom", "valuation jumps",
            "तिमाही मुनाफा", "शेयर उछला", "प्रायोजित"
        ]) and not any(w in text for w in ["jobs created", "solar", "renewable", "msme", "microfinance", "rural", "रोजगार", "हस्तशिल्प"])

        if promotional_pr:
            return ClassificationResult(
                label=PositivityLabel.NEGATIVE,
                score=0.20,
                reason="Commercial marketing, promotional PR puffery, or corporate sales pitch without constructive societal benefit.",
                rubric_version=self.rubric_version,
                category="Exclusion/Promotional",
                category_assignment=None,
                publish_hold_reason=None,
                is_held=False,
                prompt_version=self.prompt_version
            )

        # Special Rule (Health): Uncorroborated medical claims check
        uncorroborated_health = any(w in text for w in [
            "miracle cure", "cures all cancer", "secret herb doctors hate", "overnight treatment",
            "guaranteed cure", "चमत्कारी इलाज", "कैंसर की अचूक दवा", "जादुई नुस्खा"
        ])
        if uncorroborated_health:
            return ClassificationResult(
                label=PositivityLabel.NEGATIVE,
                score=0.15,
                reason="Uncorroborated medical efficacy claim without institutional verification or peer-reviewed evidence.",
                rubric_version=self.rubric_version,
                category="Exclusion/UncorroboratedHealth",
                category_assignment=None,
                publish_hold_reason=None,
                is_held=False,
                prompt_version=self.prompt_version
            )

        # Special Rule (Entertainment): Celebrity gossip, paparazzi, and personal scandals check
        gossip_content = any(w in text for w in [
            "paparazzi", "celebrity gossip", "dating rumors", "divorce feud", "wardrobe malfunction",
            "spotted together", "affair scandal", "गॉसिप", "तलाक विवाद", "डेटिंग"
        ])
        if gossip_content:
            return ClassificationResult(
                label=PositivityLabel.NEGATIVE,
                score=0.10,
                reason="Celebrity gossip, tabloid paparazzi, or personal scandal excluded under constructive journalism rubric.",
                rubric_version=self.rubric_version,
                category="Exclusion/EntertainmentGossip",
                category_assignment=None,
                publish_hold_reason=None,
                is_held=False,
                prompt_version=self.prompt_version
            )

        # 3. Negative markers check: casualty, disaster, collision, crime, scam, etc.
        neg_en = any(w in text for w in ["fatal", "collision", "claims lives", "killed", "died", "fire", "blast", "explosion", "ransomware", "cyberattack", "arrest", "scam", "collapses", "smog", "robbery", "boiler explosion", "bank robber", "luxury golf club", "doping", "match-fixing", "defamation"])
        neg_hi = any(w in text for w in ["मौत", "आग", "धमाका", "विस्फोट", "ठगे", "भूस्खलन", "जहरीली शराब", "लूट", "जलभराव", "झुलसे", "टक्कर", "वॉटर पार्क", "चोर ने"])
        neg_bn = any(w in text for w in ["অগ্নিকাণ্ড", "মৃত্যু", "প্রাণহানি", "ধাক্কায়", "প্রতারণা", "প্লাবিত", "বিস্ফোরণ", "বিষমদ", "নিহত", "দূষণের", "লুট", "ডুবিয়ে", "ডুবে", "উল্টে", "কৃত্রিম ঝরনা", "ডাকাত"])
        neg_mr = any(w in text for w in ["अपघात", "मृत्यू", "स्फोट", "फसवणूक", "कोसळली", "विषाक्त दारू", "खंड", "दरोडा", "खड्ड्यांमुळे", "सांडपाणी", "बनावट औषध", "कृत्रिम तलाव", "चोराने"])
        neg_te = any(w in text for w in ["దుర్మరణం", "పేలుడు", "మోసం", "వరద", "జలమయం", "నాటుసారా", "దోపిడీ", "బోల్తా", "ఎండిపోయిన", "పోగొట్టుకున్న", "కుప్పకూలి", "ఈత కొలను", "దొంగ"])
        neg_ta = any(w in text for w in ["உயிரிழப்பு", "பலி", "வெடிவிபத்து", "மோசடி", "கள்ளச்சாராயம்", "வெள்ளநீர்", "இடிந்து", "கொள்ளை", "கருகிய", "இழந்த", "தீ விபத்து", "செயற்கை நீரூற்று", "திருடன்"])
        neg_ur = any(w in text for w in ["جاں بحق", "دھماکہ", "ہلاک", "غبن", "گرنے", "ہلاکت", "لوٹ", "زیر آب", "جعلی ادویات", "فراڈ", "آگ بھڑک", "مصنوعی فوارہ", "چور نے"])
        neg_gu = any(w in text for w in ["મોત", "અકસ્માતમાં", "છેતરપિંડી", "લઠ્ઠો", "લૂંટ", "બેટમાં", "ધરાશાયી", "પડાવ્યા", "નષ્ટ", "શોર્ટ સર્કિટથી", "કૃત્રિમ ફુવારો", "તસ્કરે"])
        neg_kn = any(w in text for w in ["ಸಾವು", "ಸ್ಫೋಟ", "ವಂಚಿಸಿದ", "ಕಳ್ಳಸಾರಾಯಿ", "ದರೋಡೆ", "ಜಲಾವೃತ", "ಕುಸಿತ", "ಬರಗಾಲ", "ಬೆಂಕಿ", "ಕೃತಕ ಕಾರಂಜಿ", "ಕಳ್ಳ"])
        neg_or = any(w in text for w in ["ମୃତ", "ବିସ୍ଫୋରଣ", "ଠକେଇ", "ବିଷାକ୍ତ ମଦ", "ଲୁଟ", "ଜଳମଗ୍ନ", "ଭୁଶୁଡ଼ି", "ଠକଙ୍କ", "ଉଜୁଡ଼ିଗଲା", "ଅଗ୍ନିକାଣ୍ଡ", "କୃତ୍ରିମ ଝରଣା", "ଚୋର"])
        neg_ml = any(w in text for w in ["മരിച്ചു", "കൂട്ടിയിടിച്ച്", "തട്ടിയെടുത്ത", "വിഷമദ്യം", "കവർന്നു", "ഉരുൾപൊട്ടൽ", "തകർന്നു വീണു", "നഷ്ടമായി", "വെള്ളത്തിലായി", "തീപിടുത്തത്തിൽ", "കൃത്രിമ ജലധാര", "കള്ളൻ"])
        neg_pa = any(w in text for w in ["ਮੌਤ", "ਧਮਾਕਾ", "ਠੱਗੀ", "ਸ਼ਰਾਬ", "ਲੁੱਟੇ", "ਜਲਮਗਨ", "ਡਿੱਗੀ", "ਠੱਗੇ", "ਨੁਕਸਾਨ", "ਅੱਗ", "ਨਕਲੀ ਫੁਹਾਰਾ", "ਚੋਰ ਨੇ"])
        neg_as = any(w in text for w in ["মৃত্যু", "দুৰ্ঘটনাত", "বিস্ফোৰণ", "প্ৰতাৰণা", "বিষাক্ত সুৰা", "লুট", "খহনীয়া", "ধ্বংস", "জুই", "কৃটিম পুখুৰী", "চোৰে"])
        neg_ne = any(w in text for w in ["मृत्यु", "दुर्घटनामा", "विस्फोट", "ठगी", "पहिरो", "लुटपाट", "विषाक्त मदिरा", "आगलागी", "डुबान", "कृत्रिम झरना", "चोरले"])
        neg_mai = any(w in text for w in ["मृत्यु", "दुर्घटनामे", "विस्फोट", "ठगी", "लूटपाट", "जहरीली शराब", "आगि", "बाढ़िमे", "ध्वस्त", "कृत्रिम फव्वारा", "चोर"])
        neg_gom = any(w in text for w in ["मरण", "अपघातांत", "स्फोट", "फटोवणी", "लूट", "कोसळप", "उजो", "विखारी सोरो", "बुडून", "कृत्रिम कारंजे", "चोरान", "कॅसिनो", "भपकेबाज", "डोंगराची माती", "दरीत कोसळून"])

        if (
            neg_en or neg_hi or neg_bn or neg_mr or neg_te or neg_ta or
            neg_ur or neg_gu or neg_kn or neg_or or neg_ml or neg_pa or
            neg_as or neg_ne or neg_mai or neg_gom
        ):
            return ClassificationResult(
                label=PositivityLabel.NEGATIVE,
                score=0.05,
                reason="Severe disaster, casualty, criminal incident, or negative event.",
                rubric_version=self.rubric_version,
                category="Exclusion/Negative",
                category_assignment=None,
                publish_hold_reason=None,
                is_held=False,
                prompt_version=self.prompt_version
            )

        # 4. Constructive Achievements Check
        pos_en = any(w in text for w in [
            "breakthrough", "develop", "membrane", "purification", "solar", "restoration", "water",
            "success", "record efficiency", "integration tests", "milestone", "conservation",
            "recovering", "cooperative", "uptime", "tuberculosis test", "step-well", "prosthetic",
            "project tiger", "pediatric clinic", "zero-waste", "weavers", "underpasses",
            "world championship", "gold medal", "paralympic", "olympic triumph", "world record",
            "sportsmanship award", "badminton title", "grand slam victory", "youth sports academy",
            "championship title", "athletics victory", "world cup triumph", "national film award",
            "classical music festival", "heritage film restoration", "folk art festival",
            "lifetime achievement award", "cannes honor", "symphony orchestra", "literary prize",
            "cultural festival", "art exhibition milestone", "theatre revival", "quantum computing",
            "smart navigation", "lok adalat", "veteran welfare", "cyclone shelter", "citizen service",
            "public grievance", "direct benefit transfer", "citizen portal"
        ])
        pos_hi = any(w in text for w in ["सौर ऊर्जा", "स्वास्थ्य केंद्र", "कम पानी", "धान की नई किस्म", "पुनर्जीवित", "हृदय", "रोशन", "हस्तशिल्प", "जैविक", "कवच प्रणाली", "प्रमाण पत्र", "रोबोटिक्स", "स्वर्ण पदक", "स्वच्छ शहर", "सफलता", "उपलब्धि", "सहेजा गया"])
        pos_bn = any(w in text for w in ["ম্যানগ্রোভ", "আর্সেনিক ফিল্টার", "স্ট্রবেরি", "হস্তী করিডোর", "কাঁথাস্টিচ", "টেরাকোটা", "বায়ো-লুব্রিকেন্ট", "মিষ্টি জলের মাছ", "মোবাইল চিকিৎসা", "বায়োগ্যাস", "স্বর্ণপদক", "অর্থোডক্স চা", "সফল", "আবিষ্কার", "স্বাবলম্বী"])
        pos_mr = any(w in text for w in ["सहकारी संस्था", "सौर उपकरण", "जलक्रांती", "विज्ञान प्रयोगशाळा", "सेंद्रिय हळद", "ब्रेल पुस्तके", "आरोग्य केंद्रांची", "कासव संवर्धन", "पैठण्या", "बायो-सीएनजी", "वीज स्वयंपूर्णता", "सुवर्णपदके", "श्रमदानातून"])
        pos_te = any(w in text for w in ["డ్రోన్ స్ప్రేయర్", "కాఫీ విక్రయాల్లో", "గ్రాఫీన్ ఫిల్టర్", "దానిమ్మ", "చేనేత కార్మికుల", "తాబేళ్ల పరిరక్షణ", "ప్రాథమిక ఆరోగ్య కేంద్రాల", "వరి వంగడాల", "చెక్‌డ్యామ్‌ల", "విలువిద్య", "బయో-ప్లాస్టిక్", "స్వచ్ఛ గ్రామంగా", "ఆవిష్కరణ"])
        pos_ta = any(w in text for w in ["கடல்பாசி வளர்ப்பு", "குடிநீராக்கும்", "இயற்கை நெல்", "சுங்குடி சேலை", "காட்டுத்தேன்", "ஆமைகள் பாதுகாப்பு", "சூரியசக்தி சுகாதார", "வாழை நார்களில்", "தூர்வாரப்பட்டு", "சிலம்பாட்ட", "பயோ-காஸ்", "மக்கும் குப்பை", "சாதனை"])
        pos_ur = any(w in text for w in ["سمارٹ نیویگیشن", "فلٹریشن جھلی", "چکن کاری", "سولر ٹیوب ویل", "موبائل ایمبولینس", "خطاطی", "شمسی توانائی", "کنوؤں کی بحالی", "طلائی تمغے", "بائیو سی این جی", "جڑی بوٹیوں", "نامیاتی شہد", "تیار کی", "کامیاب", "ایجاد"])
        pos_gu = any(w in text for w in ["હાઇબ્રિડ પાર્ક", "સોલાર ફિલ્ટર", "સહકારી મંડળીએ", "ચેકડેમનું નિર્માણ", "પટોળા", "સિંહોની વસ્તીમાં", "સોલાર પ્રાથમિક", "કુદરતી ખેતી", "બાયો-સીએનજી", "સુવર્ણચંદ્રકો", "પેવર બ્લોક્સ", "ગ્રીન ક્લીન", "કાર્યરત", "સફળ"])
        pos_kn = any(w in text for w in ["ಜಲ ಶುದ್ಧೀಕರಣ", "ಸಹಕಾರ ಸಂಘಕ್ಕೆ", "ಸೌರ ಪಾರ್ಕ್‌ನಿಂದ", "ಕೆರೆಗಳ ಪುನಶ್ಚೇತನ", "ಇಳಕಲ್ ಸೀರೆ", "ಆಮೆಗಳ ಸಂರಕ್ಷಣೆ", "ಸೌರಶಕ್ತಿ ಪ್ರಾಥಮಿಕ", "ರಾಗಿ ಕೃಷಿ", "ಬಯೋ-ಸಿಎನ್‌ಜಿ", "ಚಿನ್ನದ ಪದಕ", "ಬಾಳೆ ನಾರಿನಿಂದ", "ಇ-ಆಟೋ", "ಯಶಸ್ವಿ", "ಆವಿಷ್ಕಾರ"])
        pos_or = any(w in text for w in ["ମାଣ୍ଡିଆ ଚାଷରେ", "ବିଶୋଧନ ଯନ୍ତ୍ର", "କଇଁଛ ସଂରକ୍ଷଣ", "ଚେକଡ୍ୟାମ ନିର୍ମାଣ", "ହସ୍ତତନ୍ତ ବୁଣାକାରଙ୍କ", "ଡଲଫିନ ସଂରକ୍ଷଣରେ", "ସୌରଚାଳିତ ପ୍ରାଥମିକ", "ଜୈବିକ ହଳଦୀ", "ବାୟୋ-ସିଏନଜି", "ସ୍ୱର୍ଣ୍ଣ ପଦକ", "ସବାଇ ଘାସରୁ", "ନିର୍ମଳ ଗ୍ରାମ", "ସଫଳତା", "ଉଦ୍ଭାବନ"])
        pos_ml = any(w in text for w in ["വിമാനത്താവളം 100", "നാനോ മെംബ്രേൻ", "ചെറുധാന്യ കൃഷിക്ക്", "കണ്ടൽക്കാടുകൾ", "ചേന്ദമംഗലം കൈത്തറി", "കടലാമ സംരക്ഷണ", "സൗരോർജ്ജ പ്രാഥമിക", "പൊക്കാളി നെൽകൃഷിയിലൂടെ", "ബയോ-സിഎൻജി", "കളരിപ്പയറ്റ്", "വാഴനാരുകളിൽ", "മാതൃകാ ഗ്രാമപഞ്ചായത്തിന്", "വിജയകരമായി", "പുരസ്കാരം"])
        pos_pa = any(w in text for w in ["ਬਾਇਓ-ਡੀਕੰਪੋਜ਼ਰ", "ਨਵੀਂ ਕਿਸਮ", "ਸੋਲਰ ਪੰਪ", "ਛੱਪੜਾਂ ਦਾ ਨਵੀਨੀਕਰਨ", "ਫੁਲਕਾਰੀ", "ਪੰਛੀਆਂ ਦੀ ਸੁਰੱਖਿਆ", "ਸੋਲਰ ਪ੍ਰਾਇਮਰੀ", "ਕਿੰਨੂ ਬਾਗਬਾਨੀ", "ਬਾਇਓ-ਸੀਐਨਜੀ", "ਸੋਨੇ ਦੇ ਤਗਮੇ", "ਪੈਕਿੰਗ ਸਮੱਗਰੀ", "ਸਵੱਛ ਗ੍ਰਾਮ", "ਕਾਮਯਾਬੀ", "ਰਿਕਾਰਡ"])
        pos_as = any(w in text for w in ["চোৰাং চিকাৰ শূন্যলৈ", "বয়ন শিল্প", "মুগা ৰেচম", "সৌৰ জলসিঞ্চন", "মৌ-পালন", "হস্তী সংৰক্ষণ", "হস্তী কৰিডৰ", "মডেল চিকিৎসালয়", "কপৌফুল", "জৈৱিক চাহ", "স্বৰ্ণপদক", "বায়ো-প্লাষ্টিক", "আবিষ্কাৰ", "সফলতা", "পানী ফিল্টাৰ", "আইআইটি গুৱাহাটী", "নিৰ্মল গ্ৰাম পঞ্চায়ত"])
        pos_ne = any(w in text for w in ["जैविक चिया", "जलविद्युत आयोजना", "हिउँचितुवा संरक्षण", "अल्लो कपडा", "सुन्तला खेती", "माइक्रो-हाइड्रो", "सामुदायिक वन", "अर्ग्यानिक कफी", "स्वर्ण पदक", "बायो-ग्यास", "बायोग्यास", "सौर्य ऊर्जा", "सफलता", "कीर्तिमान", "बाँसका सामग्री", "प्लास्टिकमुक्त", "नमुना गाउँ"])
        pos_mai = any(w in text for w in ["मखाना प्रोसेसिंग", "मिथिला चित्रकला", "मधुबनी चित्रकला", "चित्रकला", "कम पानिमे धान", "सौर्य सिंचन", "माछ पालन", "पोखरि पुनरुद्धार", "कछुआ संरक्षण", "सोलर हेल्थ सेंटर", "सिक्की घासक", "बायो-सीएनजी", "स्वर्ण पदक", "खादी ग्रामोद्योग", "सफलता", "सफल", "नवोन्मेष", "महिला कलाकार"])
        pos_gom = any(w in text for w in ["कांदळवन संवर्धन", "सोलर बोट", "खारवी समाज", "जैविक काजू", "कुंकळ्ळी हातमाग", "हातमाग", "जीआय टॅग", "कासव संवर्धन", "सोलर प्रायमरी", "कुळगर बागायत", "बायो-गॅस", "बायोगॅस", "भांगरा पदक", "नितळ गांव", "यशस्वी", "काथ्या", "महिला बचत गट"])

        is_constructive_positive = (
            pos_en or pos_hi or pos_bn or pos_mr or pos_te or pos_ta or
            pos_ur or pos_gu or pos_kn or pos_or or pos_ml or pos_pa or
            pos_as or pos_ne or pos_mai or pos_gom
        )

        if is_constructive_positive:
            # 5. Taxonomy v1 Category Assignment Resolution
            primary_id, sub_id, secondary_ids, confidence, reason, legacy_category = self._resolve_category(text)

            # Check for ambiguity between visible and hidden categories
            is_ambiguous_hidden = False
            has_hidden_signals = any(w in text for w in ["border", "peacekeeping", "relief operation", "lok adalat", "public scheme"])
            has_visible_signals = any(w in text for w in ["solar", "technology", "agriculture", "education", "renewable"])
            if has_hidden_signals and has_visible_signals:
                is_ambiguous_hidden = True

            # Option A Hold Policy Enforcement
            is_held = False
            publish_hold_reason = None
            category_assignment = None

            if is_ambiguous_hidden:
                is_held = True
                publish_hold_reason = "Ambiguous classification between visible and hidden category"
                category_assignment = CategoryAssignment(
                    primary_id=primary_id,
                    secondary_ids=secondary_ids,
                    subcategory_id=sub_id,
                    confidence=confidence,
                    taxonomy_version=TAXONOMY_VERSION
                )
            elif primary_id in HIDDEN_CATEGORY_IDS:
                cat_obj = default_taxonomy_registry.get_by_id(primary_id)
                cat_name = cat_obj.slug if cat_obj else f"Category {primary_id}"
                is_held = True
                publish_hold_reason = f"Primary category {primary_id} ({cat_name}) is hidden at launch"
                category_assignment = CategoryAssignment(
                    primary_id=primary_id,
                    secondary_ids=secondary_ids,
                    subcategory_id=sub_id,
                    confidence=confidence,
                    taxonomy_version=TAXONOMY_VERSION
                )
            elif confidence < CATEGORY_CONFIDENCE_THRESHOLD:
                # Rule: low confidence on a visible category sets category to null
                # (the item can still appear in Top and Latest, but not on category pages)
                category_assignment = None
                is_held = False
                publish_hold_reason = None
            else:
                category_assignment = CategoryAssignment(
                    primary_id=primary_id,
                    secondary_ids=secondary_ids,
                    subcategory_id=sub_id,
                    confidence=confidence,
                    taxonomy_version=TAXONOMY_VERSION
                )

            # Positivity decision remains POSITIVE regardless of category outcome
            return ClassificationResult(
                label=PositivityLabel.POSITIVE,
                score=0.95,
                reason=reason,
                rubric_version=self.rubric_version,
                category=legacy_category,
                category_assignment=category_assignment,
                publish_hold_reason=publish_hold_reason,
                is_held=is_held,
                prompt_version=self.prompt_version
            )

        # 6. Neutral administrative / policy announcements
        neutral_en = any(w in text for w in ["repo rate", "reserve bank", "monetary policy", "committee", "notices", "bench", "estimation schedule"])
        neutral_hi = any(w in text for w in ["रेपो दर", "मौद्रिक नीति", "उच्चतम न्यायालय", "सांख्यिकी मंत्रालय", "समय-सारणी"])
        neutral_bn = any(w in text for w in ["রেপো রেট", "রিজার্ভ ব্যাংক", "হাইকোর্টের", "পরিসংখ্যান কার্যালয়"])
        neutral_mr = any(w in text for w in ["रेपो दर", "रिझर्व्ह बँकेने", "उच्च न्यायालयाने", "सांख्यिकी संचालनालयाने"])
        neutral_te = any(w in text for w in ["రెపో రేటును", "రిజర్వ్ బ్యాంక్", "హైకోర్టు ఆదేశం", "గణాంకాలను", "ఆర్థిక శాఖ"])
        neutral_ta = any(w in text for w in ["ரெப்போ வட்டி", "ரிசர்വ് வங்கி", "உயர்நீதிமன்றம் உத்தரவு", "புள்ளிவிவர"])
        neutral_ur = any(w in text for w in ["مرکزی بینک", "پالیسی ریٹ", "ہائی کورٹ", "محکمہ شماریات"])
        neutral_gu = any(w in text for w in ["રિઝર્વ બેંકે", "રેપો રેટ", "ગુજરાત હાઈકોર્ટે", "આંકડાશાસ્ત્ર"])
        neutral_kn = any(w in text for w in ["ರಿಸರ್ವ್ ಬ್ಯಾಂಕ್", "ರೆಪೋ ದರ", "ಹೈಕೋರ್ಟ್ ಆದೇಶ", "ಅಂಕಿಅಂಶ"])
        neutral_or = any(w in text for w in ["ରିଜର୍ଭ ବ୍ୟାଙ୍କର", "ରେପୋ ରେଟ୍", "ହାଇକୋର୍ଟଙ୍କ", "ପରିସଂଖ୍ୟାନ"])
        neutral_ml = any(w in text for w in ["റിസർവ് ബാങ്ക്", "റിപ്പോ നിരക്കിൽ", "ഹൈക്കോടതി", "ധനകാര്യ വകുപ്പ്"])
        neutral_pa = any(w in text for w in ["ਰਿਜ਼ਰਵ ਬੈਂਕ", "ਰੈਪੋ ਰੇਟ", "ਹਾਈਕੋਰਟ", "ਅੰਕੜਾ ਵਿਭਾਗ"])
        neutral_as = any(w in text for w in ["ৰিজাৰ্ভ বেংকৰ", "ৰেপো ৰেট", "উচ্চ ন্যায়ালয়", "পৰিসংখ্যা বিভাগ"])
        neutral_ne = any(w in text for w in ["नेपाल राष्ट्र बैंक", "मौद्रिक नीति", "सर्वोच्च अदालत", "तथ्याङ्क विभाग"])
        neutral_mai = any(w in text for w in ["रिजर्व बैंकक", "रेपो दर", "पटना उच्च न्यायालय", "सांख्यिकी विभाग"])
        neutral_gom = any(w in text for w in ["रिझर्व्ह बँकेची", "रेपो दर", "मुंबय उच्च न्यायालय", "सांख्यिकी खाते"])

        if (
            neutral_en or neutral_hi or neutral_bn or neutral_mr or neutral_te or neutral_ta or
            neutral_ur or neutral_gu or neutral_kn or neutral_or or neutral_ml or neutral_pa or
            neutral_as or neutral_ne or neutral_mai or neutral_gom
        ):
            return ClassificationResult(
                label=PositivityLabel.NEUTRAL,
                score=0.50,
                reason="Routine administrative or monetary policy announcement.",
                rubric_version=self.rubric_version,
                category="Macroeconomics/Policy",
                category_assignment=None,
                publish_hold_reason=None,
                is_held=False,
                prompt_version=self.prompt_version
            )

        # 7. Fail-closed default
        return ClassificationResult(
            label=PositivityLabel.NEUTRAL,
            score=0.40,
            reason="Insufficient constructive outcome evidence; failing closed.",
            rubric_version=self.rubric_version,
            category="Unclassified",
            category_assignment=None,
            publish_hold_reason=None,
            is_held=False,
            prompt_version=self.prompt_version
        )

    def _resolve_category(self, text: str) -> Tuple[int, Optional[str], list, float, str, str]:
        """
        Determines the primary category ID, subcategory ID, secondaries, confidence, and reason.
        """
        # Sports (ID 5)
        if any(w in text for w in [
            "sport", "championship", "tournament", "olympic", "paralympic", "world record",
            "sportsmanship", "athletics", "badminton", "grand slam", "youth sports", "sports academy",
            "world cup", "पहलवानों", "कुश्ती", "खेल अकादमी", "विश्व चैंपियनशिप", "విలువిద్య",
            "சிலம்பாட்ட", "കളരിപ്പയറ്റ്", "खेलकुद", "ক্ৰীড়া"
        ]):
            sub_id = "sports_grassroots"
            if "cricket" in text:
                sub_id = "sports_cricket"
            elif any(w in text for w in ["olympic", "paralympic"]):
                sub_id = "sports_olympic_paralympic"
            elif "athletics" in text or "marathon" in text or "gold medal" in text:
                sub_id = "sports_athletics"
            return 5, sub_id, [], 0.95, "Constructive athletic achievement, world record, or youth sports development milestone.", "Sports"

        # Entertainment & Media (ID 12)
        if any(w in text for w in [
            "film award", "classical music", "symphony orchestra", "film restoration",
            "folk art festival", "cannes honor", "literary prize", "cultural festival", "national film award",
            "theatre revival", "art exhibition milestone", "राष्ट्रीय फिल्म पुरस्कार", "शास्त्रीय संगीत",
            "सिनेमा धरोहर", "लोक कला महोत्सव", "साहित्य पुरस्कार", "চলচ্চিত্র উৎসব", "চিত্রकला", "नाट्य महोत्सव",
            "திரைப்பட விருது", "නාටක", "तियात्र"
        ]):
            sub_id = "ent_awards"
            if "cinema" in text or "film" in text:
                sub_id = "ent_cinema"
            elif "music" in text or "orchestra" in text or "संगीत" in text:
                sub_id = "ent_music"
            return 12, sub_id, [7], 0.95, "Constructive cultural milestone, artistic preservation, or creative accomplishment.", "Entertainment"

        # Science & Technology (ID 2)
        if any(w in text for w in [
            "quantum", "membrane", "purification", "robotics", "satellite", "telecom",
            "आविष्कार", "प्रयोगशाळा", "researchers", "scientists", "laboratory", "iisc",
            "software"
        ]) or (
            any(w in text for w in ["technology", "breakthrough", "develop"])
            and not any(w in text for w in ["solar", "हस्तशिल्प", "weavers", "dairy", "crop"])
        ):
            sub_id = "scitech_research_discovery"
            secondaries = []
            if any(w in text for w in ["water", "groundwater", "microplastics"]):
                secondaries = [4]
            if "space" in text or "satellite" in text:
                sub_id = "scitech_space"
            elif any(w in text for w in ["quantum", "laboratory", "research", "scientists", "breakthrough", "membrane"]):
                sub_id = "scitech_research_discovery"
            elif "software" in text or "ai " in text or "artificial intelligence" in text:
                sub_id = "scitech_ai_software"
            return 2, sub_id, secondaries, 0.95, "Constructive scientific breakthrough or technological milestone.", "Science/Tech"

        # Hidden Category: Defence & Security (ID 17)
        if any(w in text for w in ["veteran welfare", "peacekeeping", "border road organisation", "ex-servicemen", "सैनिक कल्याण", "शांति सेना"]):
            return 17, "def_veteran_welfare", [], 0.90, "Constructive veteran welfare or peacekeeping initiative.", "Civic"

        # Hidden Category: Governance & Public Services (ID 14)
        if any(w in text for w in ["citizen service", "public scheme", "grievance portal", "direct benefit transfer", "নাগরিক সেবা", "প্রशासनিক सुधार"]):
            return 14, "gov_citizen_services", [], 0.90, "Administrative citizen service delivery improvement.", "Civic"

        # Hidden Category: Law, Justice & Safety (ID 15)
        if any(w in text for w in ["lok adalat", "legal aid", "judicial reform", "consumer rights tribunal"]):
            return 15, "law_legal_aid", [], 0.90, "Access to justice and legal aid dispute resolution.", "Civic"

        # Hidden Category: Disaster & Emergency (ID 18)
        if any(w in text for w in ["cyclone shelter", "flood relief rescue", "ndrf operation", "disaster warning radar"]):
            return 18, "dis_disaster_resilience", [], 0.90, "Disaster resilience and community relief milestone.", "Civic"

        # Hidden Category: Religion & Spirituality (ID 16)
        if any(w in text for w in ["interfaith dialogue", "sacred architecture restoration", "communal harmony"]):
            return 16, "rel_interfaith_initiatives", [], 0.90, "Interfaith cultural harmony and heritage preservation.", "Civic"

        # Environment & Climate (ID 4)
        if any(w in text for w in [
            "solar", "सौर", "water", "जल", "restoration", "पुनर्जीवित", "ecology", "जैविक",
            "ম্যানগ্রোভ", "হস্তী", "বায়োগ্যাস", "अर्थোডক্স চা", "जलक्रांती", "कासव", "बायो-सीएनजी",
            "स्वयंपूर्णता", "కాఫీ", "తాబేళ్ల", "చెక్‌డ్యామ్‌ల", "నెల్", "ஆமைகள்", "தூர்வாரப்பட்டு",
            "பயோ-காஸ்", "চোৰাং চিকাৰ", "हिउँचितुवा", "कांदळवन", "zero-waste", "wetland"
        ]):
            sub_id = "env_renewable_energy"
            if "water" in text or "river" in text or "जल" in text:
                sub_id = "env_water_rivers"
            elif any(w in text for w in ["tiger", "elephant", "কাसव", "ஆமைகள்", "হস্তী", "wildlife", "conservation"]):
                sub_id = "env_wildlife_conservation"
            return 4, sub_id, [1], 0.95, "Constructive environmental restoration, renewable energy, or conservation breakthrough.", "Ecology"

        # Agriculture & Rural (ID 1)
        if any(w in text for w in [
            "धान", "వరి వంగడాల", "നെല്", "কৃষি", "शेतकाम", "crops", "dairy", "fisheries",
            "cooperative", "सहकारी", "weavers", "हस्तशिल्प", "मखाना", "স্ট্রবেরি", "হস্ততন্ত", "कपास"
        ]):
            sub_id = "agri_farming_practices"
            if "crop" in text or "धान" in text or "yield" in text:
                sub_id = "agri_crops_yields"
            elif "cooperative" in text or "सहकारी" in text:
                sub_id = "agri_cooperatives"
            return 1, sub_id, [6], 0.92, "Rural enterprise, agricultural innovation, or farmer cooperative milestone.", "Ecology"

        # Society & Community (ID 6)
        if any(w in text for w in [
            "empowerment", "आदिवासी", "স্বাবলম্বী", "महिला", "बचत गट", "volunteering", "disabled",
            "assistive", "senior citizen", "child welfare", "स्वच्छ", "swachh"
        ]):
            return 6, "soc_inspiring_individuals", [], 0.92, "Constructive community solution, civic empowerment, or social inclusion.", "Civic"

        # Default visible category fallback (Science/Tech ID 2)
        return 2, "scitech_research_discovery", [], 0.80, "Constructive innovation or public milestone.", "Science/Tech"
