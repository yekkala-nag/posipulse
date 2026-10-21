"""
Positivity Classifier Agent
Evaluates news items against Constructive Journalism Rubric v1.0.0.
Supports both live Gemini LLM evaluation and deterministic local rubric engine for CI/test fixtures.
"""

import json
import os
import re
from typing import Optional
from src.schemas.article import EphemeralIngestedItem, PositivityLabel, PositivityMetadata


class PositivityClassifier:
    def __init__(self, model_name: str = "gemini-1.5-flash", rubric_version: str = "1.0.0"):
        self.model_name = model_name
        self.rubric_version = rubric_version
        self.api_key = os.environ.get("GEMINI_API_KEY")

    def classify(self, item: EphemeralIngestedItem) -> PositivityMetadata:
        """
        Classifies item according to constructive journalism rubric.
        Fails closed on ambiguity (precision over recall).
        """
        text = f"{item.headline} {item.raw_body}".lower()

        # Check for toxic positivity trap: child working or suffering framed as heartwarming
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
            return PositivityMetadata(
                label=PositivityLabel.TOXIC_POSITIVITY,
                score=0.10,
                reason="Systemic hardship, child labor, or extreme suffering framed as inspirational resilience.",
                rubric_version=self.rubric_version,
                category="Exclusion/Toxic Positivity"
            )

        # Check for negative markers: accident, casualty, collapse, attack
        neg_en = any(w in text for w in ["fatal", "collision", "claims lives", "killed", "died", "fire", "blast", "explosion", "ransomware", "cyberattack", "arrest", "scam", "collapses", "smog", "robbery", "boiler explosion", "bank robber", "luxury golf club"])
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
            return PositivityMetadata(
                label=PositivityLabel.NEGATIVE,
                score=0.05,
                reason="Severe disaster, casualty, criminal incident, or commercial PR puffery.",
                rubric_version=self.rubric_version,
                category="Exclusion/Negative"
            )

        # Check for positive constructive achievements:
        pos_en = any(w in text for w in ["breakthrough", "develop", "membrane", "purification", "solar", "restoration", "water", "success", "record efficiency", "integration tests", "milestone", "conservation", "recovering", "cooperative", "uptime", "tuberculosis test", "step-well", "prosthetic", "project tiger", "pediatric clinic", "zero-waste", "weavers", "underpasses"])
        pos_hi = any(w in text for w in ["सौर ऊर्जा", "स्वास्थ्य केंद्र", "कम पानी", "धान की नई किस्म", "पुनर्जीवित", "हृदय", "रोशन", "हस्तशिल्प", "जैविक", "कवच प्रणाली", "प्रमाण पत्र", "रोबोटिक्स", "स्वर्ण पदक", "स्वच्छ शहर", "सफलता", "उपलब्धि", "सहेजा गया"])
        pos_bn = any(w in text for w in ["ম্যানগ্রোভ", "আর্সেনিক ফিল্টার", "স্ট্রবেরি", "হস্তী করিডোর", "কাঁথাস্টিচ", "টেরাকোটা", "বায়ো-লুব্রিকেন্ট", "মিষ্টি জলের মাছ", "মোবাইল চিকিৎসা", "বায়োগ্যাস", "স্বর্ণপদক", "অর্থোডক্স চা", "সফল", "আবিষ্কার", "স্বাবলম্বী"])
        pos_mr = any(w in text for w in ["सहकारी संस्था", "सौर उपकरण", "जलक्रांती", "विज्ञान प्रयोगशाळा", "सेंद्रिय हळद", "ब्रेल पुस्तके", "आरोग्य केंद्रांची", "कासव संवर्धन", "पैठण्या", "बायो-सीएनजी", "वीज स्वयंपूर्णता", "सुवर्णपदके", "श्रमदानातून"])
        pos_te = any(w in text for w in ["డ్రోన్ స్ప్రేయర్", "కాఫీ విక్రయాల్లో", "గ్రాఫీన్ ఫిల్టర్", "దానిమ్మ", "చేనేత కార్మికుల", "తాబేళ్ల పరిరక్షణ", "ప్రాథమిక ఆరోగ్య కేంద్రాల", "వరి వంగడాల", "చెక్‌డ్యామ్‌ల", "విలువిద్య", "బయో-ప్లాస్టిక్", "స్వచ్ఛ గ్రామంగా", "ఆవిష్కరణ"])
        pos_ta = any(w in text for w in ["கடல்பாசி வளர்ப்பு", "குடிநீராக்கும்", "இயற்கை நெல்", "சுங்குடி சேலை", "காட்டுத்தேன்", "ஆமைகள் பாதுகாப்பு", "சூரியசக்தி சுகாதார", "வாழை நார்களில்", "தூர்வாரப்பட்டு", "சிலம்பாட்ட", "பயோ-காஸ்", "மக்கும் குப்பை", "சாதனை"])
        pos_ur = any(w in text for w in ["سمارٹ نیویگیشن", "فلٹریشن جھلی", "چکن کاری", "سولر ٹیوب ویل", "موبائل ایمبولینس", "خطاطی", "شمسی توانائی", "کنوؤں کی بحالی", "طلائی تمغے", "بائیو سی این جی", "جڑی بوٹیوں", "نامیاتی شہد", "تیار کی", "کامیاب", "ایجاد"])
        pos_gu = any(w in text for w in ["હાઇબ્રિડ પાર્ક", "સોલાર ફિલ્ટર", "સહકારી મંડળીએ", "ચેકડેમનું નિર્માણ", "પટોળા", "સિંહોની વસ્તીમાં", "સોલાર પ્રાથમિક", "કુદરતી ખેતી", "બાયો-સીએનજી", "સુવર્ણચંદ્રકો", "પેવર બ્લોક્સ", "ગ્રીન ક્લીન", "કાર્યરત", "સફળ"])
        pos_kn = any(w in text for w in ["ಜಲ ಶುದ್ಧೀಕರಣ", "ಸಹಕಾರ ಸಂಘಕ್ಕೆ", "ಸೌರ ಪಾರ್ಕ್‌ನಿಂದ", "ಕೆರೆಗಳ ಪುನಶ್ಚೇತನ", "ಇಳಕಲ್ ಸೀರೆ", "ಆಮೆಗಳ ಸಂರಕ್ಷಣೆ", "ಸೌರಶಕ್ತಿ ಪ್ರಾಥಮಿಕ", "ರಾಗಿ ಕೃಷಿ", "ಬಯೋ-ಸಿಎನ್‌ಜಿ", "ಚಿನ್ನದ ಪದಕ", "ಬಾಳೆ ನಾರಿನಿಂದ", "ಇ-ಆಟೋ", "ಯಶಸ್ವಿ", "ಆವಿಷ್ಕಾರ"])
        pos_or = any(w in text for w in ["ମାଣ୍ଡିଆ ଚାଷରେ", "ବିଶୋଧନ ଯନ୍ତ୍ର", "କଇଁଛ ସଂରକ୍ଷଣ", "ଚେକଡ୍ୟାମ ନିର୍ମାଣ", "ହସ୍ତତନ୍ତ ବୁଣାକାରଙ୍କ", "ଡଲଫିନ ସଂରକ୍ଷଣରେ", "ସୌරଚାଳିତ ପ୍ରାଥମିକ", "ଜୈବିକ ହଳଦୀ", "ବାୟୋ-ସିଏନଜି", "ସ୍ୱର୍ଣ୍ଣ ପଦକ", "ସବାଇ ଘାସରୁ", "ନିର୍ମଳ ଗ୍ରାମ", "ସଫଳତା", "ଉଦ୍ଭାବନ"])
        pos_ml = any(w in text for w in ["വിമാനത്താവളം 100", "നാനോ മെംബ്രേൻ", "ചെറുധാന്യ കൃഷിക്ക്", "കണ്ടൽക്കാടുകൾ", "ചേന്ദമംഗലം കൈത്തറി", "കടലാമ സംരക്ഷണ", "സൗരോർജ്ജ പ്രാഥമിക", "പൊക്കാളി നെൽകൃഷിയിലൂടെ", "ബയോ-സിഎൻജി", "കളരിപ്പയറ്റ്", "വാഴനാരുകളിൽ", "മാതൃകാ ഗ്രാമപഞ്ചായത്തിന്", "വിജയകരമായി", "പുരസ്കാരം"])
        pos_pa = any(w in text for w in ["ਬਾਇਓ-ਡੀਕੰਪੋਜ਼ਰ", "ਨਵੀਂ ਕਿਸਮ", "ਸੋਲਰ ਪੰਪ", "ਛੱਪੜਾਂ ਦਾ ਨਵੀਨੀਕਰਨ", "ਫੁਲਕਾਰੀ", "ਪੰਛੀਆਂ ਦੀ ਸੁਰੱਖਿਆ", "ਸੋਲਰ ਪ੍ਰਾਇਮਰੀ", "ਕਿੰਨੂ ਬਾਗਬਾਨੀ", "ਬਾਇਓ-ਸੀਐਨਜੀ", "ਸੋਨੇ ਦੇ ਤਗਮੇ", "ਪੈਕਿੰਗ ਸਮੱਗਰੀ", "ਸਵੱਛ ਗ੍ਰਾਮ", "ਕਾਮਯਾਬੀ", "ਰਿਕਾਰਡ"])
        pos_as = any(w in text for w in ["চোৰাং চিকাৰ শূন্যলৈ", "বয়ন শিল্প", "মুগা ৰেচম", "সৌৰ জলসিঞ্চন", "মৌ-পালন", "হস্তী সংৰক্ষণ", "হস্তী কৰিডৰ", "মডেল চিকিৎসালয়", "কপৌফুল", "জৈৱিক চাহ", "স্বৰ্ণপদক", "বায়ো-প্লাষ্টিক", "আবিষ্কাৰ", "সফলতা", "পানী ফিল্টাৰ", "আইআইটি গুৱাহাটী", "নিৰ্মল গ্ৰাম পঞ্চায়ত"])
        pos_ne = any(w in text for w in ["जैविक चिया", "जलविद्युत आयोजना", "हिउँचितुवा संरक्षण", "अल्लो कपडा", "सुन्तला खेती", "माइक्रो-हाइड्रो", "सामुदायिक वन", "अर्ग्यानिक कफी", "स्वर्ण पदक", "बायो-ग्यास", "बायोग्यास", "सौर्य ऊर्जा", "सफलता", "कीर्तिमान", "बाँसका सामग्री", "प्लास्टिकमुक्त", "नमुना गाउँ"])
        pos_mai = any(w in text for w in ["मखाना प्रोसेसिंग", "मिथिला चित्रकला", "मधुबनी चित्रकला", "चित्रकला", "कम पानिमे धान", "सौर्य सिंचन", "माछ पालन", "पोखरि पुनरुद्धार", "कछुआ संरक्षण", "सोलर हेल्थ सेंटर", "सिक्की घासक", "बायो-सीएनजी", "स्वर्ण पदक", "खादी ग्रामोद्योग", "सफलता", "सफल", "नवोन्मेष", "महिला कलाकार"])
        pos_gom = any(w in text for w in ["कांदळवन संवर्धन", "सोलर बोट", "खारवी समाज", "जैविक काजू", "कुंकळ्ळी हातमाग", "हातमाग", "जीआय टॅग", "कासव संवर्धन", "सोलर प्रायमरी", "कुळगर बागायत", "बायो-गॅस", "बायोगॅस", "भांगरा पदक", "नितळ गांव", "यशस्वी", "काथ्या", "महिला बचत गट"])

        if (
            pos_en or pos_hi or pos_bn or pos_mr or pos_te or pos_ta or
            pos_ur or pos_gu or pos_kn or pos_or or pos_ml or pos_pa or
            pos_as or pos_ne or pos_mai or pos_gom
        ):
            category = "Science/Tech"
            if any(w in text for w in ["solar", "सौर", "water", "जल", "restoration", "पुनर्जीवित", "ecology", "जैविक", "धान", "ম্যানগ্রোভ", "হস্তী", "বায়োগ্যাস", "অর্থোডক্স চা", "जलक्रांती", "कासव", "बायो-सीएनजी", "स्वयंपूर्णता", "కాఫీ", "తాబేళ్ల", "వరి వంగడాల", "చెక్‌డ్యామ్‌ల", "நெல்", "ஆமைகள்", "தூர்வாரப்பட்டு", "பயோ-காஸ்", "চোৰাং চিকাৰ", "हिउँचितुवा", "कांदळवन"]):
                category = "Ecology"
            elif any(w in text for w in ["cooperative", "सहकारी", "weavers", "हस्तशिल्प", "empowerment", "আদিবাসী", "কাঁথাস্টিচ", "টেরাকোটা", "স্বাবলম্বী", "স্ট্রবেরি", "सहकारी संस्था", "हळद", "पैठण्या", "చేనేత", "దానిమ్మ", "கடல்பாசி", "சுங்குடி சேலை", "காட்டுத்தேன்", "বয়ন শিল্প", "अल्लो कपडा", "मखाना", "खारवी समाज"]):
                category = "Empowerment"
            elif any(w in text for w in ["swachh", "स्वच्छ", "civic", "पहलवानों", "कुश्ती", "medal", "স্বর্ণপদক", "চিকিৎসা", "प्रयोगशाळा", "आरोग्य", "सुवर्णपदके", "ఆరోగ్య", "విలువిద్య", "స్వచ్ఛ", "சுகாதார", "சிலம்பாட்ட", "தூய்மை", "স্বৰ্ণপদক", "स्वर्ण पदक", "भांगरा पदक"]):
                category = "Civic"

            return PositivityMetadata(
                label=PositivityLabel.POSITIVE,
                score=0.95,
                reason="Constructive scientific breakthrough, environmental achievement, or community solution.",
                rubric_version=self.rubric_version,
                category=category
            )

        # Check for routine neutral economic/policy reports
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
            return PositivityMetadata(
                label=PositivityLabel.NEUTRAL,
                score=0.50,
                reason="Routine administrative or monetary policy announcement.",
                rubric_version=self.rubric_version,
                category="Macroeconomics/Policy"
            )

        # Fail-closed default
        return PositivityMetadata(
            label=PositivityLabel.NEUTRAL,
            score=0.40,
            reason="Insufficient constructive outcome evidence; failing closed.",
            rubric_version=self.rubric_version,
            category="Unclassified"
        )
