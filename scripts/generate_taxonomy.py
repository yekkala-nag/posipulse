"""
Taxonomy Configuration Generator and Checksum Calculator
"""

import hashlib
import json
from pathlib import Path

TAXONOMY_CATEGORIES = [
    {
        "id": 1,
        "slug": "agriculture-rural",
        "visibility": "visible",
        "positive_fit": "high",
        "special_rules": {
            "promotional_content_check": False,
            "corroboration_required": False,
            "gossip_excluded": False
        },
        "iptc_reference": {
            "qcode": "medtop:20000210",
            "uri": "http://cv.iptc.org/newscodes/mediatopic/20000210",
            "name_en": "agriculture",
            "standard_version": "2024.1"
        },
        "display_names": {
            "en": "Agriculture & Rural",
            "hi": "कृषि एवं ग्रामीण",
            "bn": "কৃষি ও গ্রামীণ",
            "mr": "शेती आणि ग्रामीण",
            "te": "వ్యవసాయం మరియు గ్రామీణం",
            "ta": "வேளாண்மை மற்றும் கிராமப்புறம்",
            "ur": "زراعت اور دیہی",
            "gu": "કૃષિ અને ગ્રામીણ",
            "kn": "ಕೃಷಿ ಮತ್ತು ಗ್ರಾಮೀಣ",
            "or": "କୃଷି ଏବଂ ଗ୍ରାମୀଣ",
            "ml": "കൃഷിയും ഗ്രാമീണവും",
            "pa": "ਖੇਤੀਬਾੜੀ ਅਤੇ ਪੇਂਡੂ",
            "as": "কৃষি আৰু গ্ৰাম্য",
            "ne": "कृषि तथा ग्रामीण",
            "mai": "कृषि आ ग्रामीण",
            "gom": "शेतकाम आनी ग्रामीण"
        },
        "subcategories": [
            {"id": "agri_farming_practices", "slug": "farming-practices", "name_en": "Farming Practices", "description": "Agronomic practices, soil health, regenerative techniques"},
            {"id": "agri_crops_yields", "slug": "crops-and-yields", "name_en": "Crops & Yields", "description": "Crop production, harvest milestones, resilient crop varieties"},
            {"id": "agri_irrigation", "slug": "irrigation", "name_en": "Irrigation", "description": "Canals, micro-irrigation, check-dams, rural water conservation"},
            {"id": "agri_dairy_fisheries", "slug": "dairy-and-fisheries", "name_en": "Dairy & Fisheries", "description": "Milk production, dairy unions, aquaculture, marine fisheries"},
            {"id": "agri_rural_enterprise", "slug": "rural-enterprise", "name_en": "Rural Enterprise", "description": "Agri-tech startups, village crafts, rural cottage industries"},
            {"id": "agri_cooperatives", "slug": "cooperatives", "name_en": "Cooperatives", "description": "Farmer producer organisations, credit societies, milk cooperatives"}
        ]
    },
    {
        "id": 2,
        "slug": "science-technology",
        "visibility": "visible",
        "positive_fit": "high",
        "special_rules": {
            "promotional_content_check": False,
            "corroboration_required": False,
            "gossip_excluded": False
        },
        "iptc_reference": {
            "qcode": "medtop:14000000",
            "uri": "http://cv.iptc.org/newscodes/mediatopic/14000000",
            "name_en": "science and technology",
            "standard_version": "2024.1"
        },
        "display_names": {
            "en": "Science & Technology",
            "hi": "विज्ञान एवं प्रौद्योगिकी",
            "bn": "বিজ্ঞান ও প্রযুক্তি",
            "mr": "विज्ञान आणि तंत्रज्ञान",
            "te": "సైన్స్ మరియు టెక్నాలజీ",
            "ta": "அறிவியல் மற்றும் தொழில்நுட்பம்",
            "ur": "سائنس اور ٹیکنالوجی",
            "gu": "વિજ્ઞાન અને ટેકનોલોજી",
            "kn": "ವಿಜ್ಞಾನ ಮತ್ತು ತಂತ್ರಜ್ಞಾನ",
            "or": "ବିଜ୍ଞାନ ଏବଂ ପ୍ରଯୁକ୍ତିବିଦ୍ୟା",
            "ml": "ശാസ്ത്രവും സാങ്കേതികവിദ്യയും",
            "pa": "ਵਿਗਿਆਨ ਅਤੇ ਤਕਨਾਲੋਜੀ",
            "as": "বিজ্ঞান আৰু প্ৰযুক্তি",
            "ne": "विज्ञान तथा प्रविधि",
            "mai": "विज्ञान आ प्रौद्योगिकी",
            "gom": "विज्ञान आनी तंत्रज्ञान"
        },
        "subcategories": [
            {"id": "scitech_research_discovery", "slug": "research-and-discovery", "name_en": "Research & Discovery", "description": "Scientific discoveries, fundamental research, academic breakthroughs"},
            {"id": "scitech_space", "slug": "space", "name_en": "Space", "description": "Satellite launches, space exploration, planetary research, observatories"},
            {"id": "scitech_ai_software", "slug": "ai-and-software", "name_en": "AI & Software", "description": "Artificial intelligence, open-source software, computing advances"},
            {"id": "scitech_electronics_telecom", "slug": "electronics-and-telecom", "name_en": "Electronics & Telecom", "description": "Semiconductor manufacturing, telecom networks, hardware innovation"},
            {"id": "scitech_innovation", "slug": "innovation", "name_en": "Innovation", "description": "Grassroots inventors, patent grants, indigenous technology prototypes"},
            {"id": "scitech_digital_public_infrastructure", "slug": "digital-public-infrastructure", "name_en": "Digital Public Infrastructure", "description": "Digital identity, instant payments, open network protocols"}
        ]
    },
    {
        "id": 3,
        "slug": "education-skills",
        "visibility": "visible",
        "positive_fit": "high",
        "special_rules": {
            "promotional_content_check": False,
            "corroboration_required": False,
            "gossip_excluded": False
        },
        "iptc_reference": {
            "qcode": "medtop:06000000",
            "uri": "http://cv.iptc.org/newscodes/mediatopic/06000000",
            "name_en": "education",
            "standard_version": "2024.1"
        },
        "display_names": {
            "en": "Education & Skills",
            "hi": "शिक्षा एवं कौशल",
            "bn": "শিক্ষা ও দক্ষতা",
            "mr": "शिक्षण आणि कौशल्य",
            "te": "విద్య మరియు నైపుణ్యాలు",
            "ta": "கல்வி மற்றும் திறன்கள்",
            "ur": "تعلیم اور مہارتیں",
            "gu": "શિક્ષણ અને કૌશલ્ય",
            "kn": "ಶಿಕ್ಷಣ ಮತ್ತು ಕೌಶಲ್ಯಗಳು",
            "or": "ଶିକ୍ଷା ଏବଂ ଦକ୍ଷତା",
            "ml": "വിദ്യാഭ്യാസവും നൈപുണ്യവും",
            "pa": "ਸਿੱਖਿਆ ਅਤੇ ਹੁਨਰ",
            "as": "শিক্ষা আৰু দক্ষতা",
            "ne": "शिक्षा तथा सीप",
            "mai": "शिक्षा आ कौशल",
            "gom": "शिक्षण आनी कसब"
        },
        "subcategories": [
            {"id": "edu_results_admissions", "slug": "results-and-admissions", "name_en": "Results & Admissions", "description": "Academic merit, board exam toppers, university admissions"},
            {"id": "edu_scholarships", "slug": "scholarships", "name_en": "Scholarships", "description": "Student fellowships, research grants, educational financial assistance"},
            {"id": "edu_research_institutions", "slug": "research-institutions", "name_en": "Research Institutions", "description": "Premier universities, academic rankings, laboratory accreditations"},
            {"id": "edu_skilling", "slug": "skilling", "name_en": "Skilling", "description": "Vocational education, apprentice schemes, industrial training institutes"},
            {"id": "edu_edtech", "slug": "edtech", "name_en": "EdTech", "description": "Digital classrooms, remote learning infrastructure, open educational resources"},
            {"id": "edu_schools", "slug": "schools", "name_en": "Schools", "description": "Primary and secondary schools, model schools, rural classroom upgrades"}
        ]
    },
    {
        "id": 4,
        "slug": "environment-climate",
        "visibility": "visible",
        "positive_fit": "high",
        "special_rules": {
            "promotional_content_check": False,
            "corroboration_required": False,
            "gossip_excluded": False
        },
        "iptc_reference": {
            "qcode": "medtop:07000000",
            "uri": "http://cv.iptc.org/newscodes/mediatopic/07000000",
            "name_en": "environment",
            "standard_version": "2024.1"
        },
        "display_names": {
            "en": "Environment & Climate",
            "hi": "पर्यावरण एवं जलवायु",
            "bn": "পরিবেশ ও জলবায়ু",
            "mr": "पर्यावरण आणि हवामान",
            "te": "పర్యావరణం మరియు వాతావరణం",
            "ta": "சுற்றுச்சூழல் மற்றும் காலநிலை",
            "ur": "ماحولیات اور موسمیات",
            "gu": "પર્યાવરણ અને આબોહવા",
            "kn": "ಪರಿಸರ ಮತ್ತು ಹವಾಮಾನ",
            "or": "ପରିବେଶ ଏବଂ ଜଳବାୟୁ",
            "ml": "പരിസ്ഥിതിയും കാലാവസ്ഥയും",
            "pa": "ਵਾਤਾਵਰਣ ਅਤੇ ਜਲਵਾਯੂ",
            "as": "পৰিৱেশ আৰু জলবায়ু",
            "ne": "वातावरण तथा जलवायु",
            "mai": "पर्यावरण आ जलवायु",
            "gom": "पर्यावरण आनी हवामान"
        },
        "subcategories": [
            {"id": "env_wildlife_conservation", "slug": "wildlife-and-conservation", "name_en": "Wildlife & Conservation", "description": "Endangered species protection, habitat corridors, tiger and elephant reserves"},
            {"id": "env_renewable_energy", "slug": "renewable-energy", "name_en": "Renewable Energy", "description": "Solar installations, wind farms, green hydrogen, clean energy targets"},
            {"id": "env_water_rivers", "slug": "water-and-rivers", "name_en": "Water & Rivers", "description": "River rejuvenation, wetland restoration, lake cleaning campaigns"},
            {"id": "env_waste_cleanup", "slug": "waste-and-cleanup", "name_en": "Waste & Cleanup", "description": "Recycling systems, plastic elimination, zero-waste municipal models"},
            {"id": "env_forests", "slug": "forests", "name_en": "Forests", "description": "Afforestation drives, mangrove restoration, sacred groves protection"}
        ]
    },
    {
        "id": 5,
        "slug": "sports",
        "visibility": "visible",
        "positive_fit": "high",
        "special_rules": {
            "promotional_content_check": False,
            "corroboration_required": False,
            "gossip_excluded": False
        },
        "iptc_reference": {
            "qcode": "medtop:16000000",
            "uri": "http://cv.iptc.org/newscodes/mediatopic/16000000",
            "name_en": "sport",
            "standard_version": "2024.1"
        },
        "display_names": {
            "en": "Sports",
            "hi": "खेल",
            "bn": "খেলাধুলা",
            "mr": "क्रीडा",
            "te": "క్రీడలు",
            "ta": "விளையாட்டு",
            "ur": "کھیل",
            "gu": "રમતો",
            "kn": "ಕ್ರೀಡೆ",
            "or": "ଖେଳ",
            "ml": "കായികം",
            "pa": "ਖੇਡਾਂ",
            "as": "ক্ৰীড়া",
            "ne": "खेलकुद",
            "mai": "खेलकूद",
            "gom": "खेळ"
        },
        "subcategories": [
            {"id": "sports_cricket", "slug": "cricket", "name_en": "Cricket", "description": "Domestic, test, ODI, and franchise cricket triumphs and milestones"},
            {"id": "sports_hockey", "slug": "hockey", "name_en": "Hockey", "description": "Field hockey tournaments, national leagues, international trophies"},
            {"id": "sports_football", "slug": "football", "name_en": "Football", "description": "National and state football league victories, club achievements"},
            {"id": "sports_kabaddi", "slug": "kabaddi", "name_en": "Kabaddi", "description": "Pro Kabaddi, national and indigenous kabaddi championships"},
            {"id": "sports_athletics", "slug": "athletics", "name_en": "Athletics", "description": "Track and field, marathon records, sprint and javelin achievements"},
            {"id": "sports_olympic_paralympic", "slug": "olympic-and-paralympic", "name_en": "Olympic & Paralympic", "description": "Olympic and Paralympic podium finishes, Asian Games medals"},
            {"id": "sports_badminton_tennis_chess", "slug": "badminton-tennis-chess", "name_en": "Badminton, Tennis & Chess", "description": "Grandmasters, Grand Slam performances, BWF badminton titles"},
            {"id": "sports_grassroots", "slug": "grassroots", "name_en": "Grassroots", "description": "Rural talent scouting, sports academies, youth developmental athletics"}
        ]
    },
    {
        "id": 6,
        "slug": "society-community",
        "visibility": "visible",
        "positive_fit": "high",
        "special_rules": {
            "promotional_content_check": False,
            "corroboration_required": False,
            "gossip_excluded": False
        },
        "iptc_reference": {
            "qcode": "medtop:15000000",
            "uri": "http://cv.iptc.org/newscodes/mediatopic/15000000",
            "name_en": "society",
            "standard_version": "2024.1"
        },
        "display_names": {
            "en": "Society & Community",
            "hi": "समाज एवं समुदाय",
            "bn": "সমাজ ও সম্প্রদায়",
            "mr": "समाज आणि समुदाय",
            "te": "సమాజం మరియు సముదాయం",
            "ta": "சமூகம் மற்றும் சமூகம்",
            "ur": "معاشرہ اور برادری",
            "gu": "સમાજ અને સમુદાય",
            "kn": "ಸಮಾಜ ಮತ್ತು ಸಮುದಾಯ",
            "or": "ସମାଜ ଏବଂ ସମୁଦାୟ",
            "ml": "സമൂഹവും കൂട്ടായ്മയും",
            "pa": "ਸਮਾਜ ਅਤੇ ਭਾਈਚਾਰਾ",
            "as": "সমাজ আৰু সম্প্ৰদায়",
            "ne": "समाज तथा समुदाय",
            "mai": "समाज आ समुदाय",
            "gom": "समाज आनी समुदाय"
        },
        "subcategories": [
            {"id": "soc_inspiring_individuals", "slug": "inspiring-individuals", "name_en": "Inspiring Individuals", "description": "Civilian altruism, everyday heroes, self-sacrifice for community welfare"},
            {"id": "soc_social_enterprise", "slug": "social-enterprise", "name_en": "Social Enterprise", "description": "Non-profit foundations, social impact ventures, community cooperatives"},
            {"id": "soc_volunteering", "slug": "volunteering", "name_en": "Volunteering", "description": "Civic volunteer corps, blood donation campaigns, mutual aid groups"},
            {"id": "soc_women_child_welfare", "slug": "women-and-child-welfare", "name_en": "Women & Child Welfare", "description": "Maternal health, girl child literacy, women self-help collectives"},
            {"id": "soc_inclusion_accessibility", "slug": "inclusion-and-accessibility", "name_en": "Inclusion & Accessibility", "description": "Assistive tech, barrier-free infrastructure, neurodiversity initiatives"},
            {"id": "soc_senior_citizens", "slug": "senior-citizens", "name_en": "Senior Citizens", "description": "Geriatric care models, active ageing clubs, elder welfare"},
            {"id": "soc_youth", "slug": "youth", "name_en": "Youth", "description": "Student innovations, adolescent leadership, youth civic engagement"}
        ]
    },
    {
        "id": 7,
        "slug": "arts-culture-heritage",
        "visibility": "visible",
        "positive_fit": "high",
        "special_rules": {
            "promotional_content_check": False,
            "corroboration_required": False,
            "gossip_excluded": False
        },
        "iptc_reference": {
            "qcode": "medtop:01000000",
            "uri": "http://cv.iptc.org/newscodes/mediatopic/01000000",
            "name_en": "arts, culture, entertainment and media",
            "standard_version": "2024.1"
        },
        "display_names": {
            "en": "Arts, Culture & Heritage",
            "hi": "कला, संस्कृति एवं विरासत",
            "bn": "শিল্প, সংস্কৃতি ও ঐতিহ্য",
            "mr": "कला, संस्कृती आणि वारसा",
            "te": "కళలు, సంస్కృతి మరియు వారసత్వం",
            "ta": "கலை, கலாச்சாரம் மற்றும் பாரம்பரியம்",
            "ur": "فن، ثقافت اور ورثہ",
            "gu": "કલા, સંસ્કૃતિ અને વારસો",
            "kn": "ಕಲೆ, ಸಂಸ್ಕೃತಿ ಮತ್ತು ಪರಂಪರೆ",
            "or": "କଳା, ସଂସ୍କୃତି ଏବଂ ଐତିହ୍ୟ",
            "ml": "കല, സംസ്കാരം, പൈതൃകം",
            "pa": "ਕਲਾ, ਸੱਭਿਆਚਾਰ ਅਤੇ ਵਿਰਾਸਤ",
            "as": "কলা, সংস্কৃতি আৰু ঐতিহ্য",
            "ne": "कला, संस्कृति तथा सम्पदा",
            "mai": "कला, संस्कृति आ धरोहर",
            "gom": "कला, संस्कृती आनी दायज"
        },
        "subcategories": [
            {"id": "arts_festivals", "slug": "festivals", "name_en": "Festivals", "description": "Traditional festivals, harvest celebrations, multi-cultural melas"},
            {"id": "arts_crafts", "slug": "crafts", "name_en": "Crafts", "description": "Handloom weaving, artisanal pottery, craft revival, GI-tagged goods"},
            {"id": "arts_heritage_sites", "slug": "heritage-sites", "name_en": "Heritage Sites", "description": "Archaeological monuments, temple restoration, UNESCO World Heritage conservation"},
            {"id": "arts_languages_literature", "slug": "languages-and-literature", "name_en": "Languages & Literature", "description": "Literary awards, indigenous linguistic revival, classical poetry releases"},
            {"id": "arts_museums", "slug": "museums", "name_en": "Museums", "description": "Museum exhibitions, repatriation of ancient artefacts, public art galleries"},
            {"id": "arts_folk_traditions", "slug": "folk-traditions", "name_en": "Folk Traditions", "description": "Tribal dances, oral folklore preservation, classical performing arts"}
        ]
    },
    {
        "id": 8,
        "slug": "lifestyle-travel",
        "visibility": "visible",
        "positive_fit": "medium",
        "special_rules": {
            "promotional_content_check": False,
            "corroboration_required": False,
            "gossip_excluded": False
        },
        "iptc_reference": {
            "qcode": "medtop:11000000",
            "uri": "http://cv.iptc.org/newscodes/mediatopic/11000000",
            "name_en": "lifestyle and leisure",
            "standard_version": "2024.1"
        },
        "display_names": {
            "en": "Lifestyle & Travel",
            "hi": "जीवनशैली एवं यात्रा",
            "bn": "জীবনধারা ও ভ্রমণ",
            "mr": "जीवनशैली आणि पर्यटन",
            "te": "జీవనశైలి మరియు ప్రయాణం",
            "ta": "வாழ்க்கை முறை மற்றும் பயணம்",
            "ur": "طرز زندگی اور سفر",
            "gu": "જીવનશૈલી અને પ્રવાસ",
            "kn": "ಜೀವನಶೈಲಿ ಮತ್ತು ಪ್ರವಾಸ",
            "or": "ଜୀବନଶୈଳୀ ଏବଂ ଯାତ୍ରା",
            "ml": "ജീവിതശൈലിയും യാത്രയും",
            "pa": "ਜੀਵਨ ਸ਼ੈਲੀ ਅਤੇ ਯਾਤਰਾ",
            "as": "জীৱনশৈলী আৰু ভ্ৰমণ",
            "ne": "जीवनशैली तथा यात्रा",
            "mai": "जीवनशैली आ यात्रा",
            "gom": "जिवनशैली आनी भोंवडी"
        },
        "subcategories": [
            {"id": "life_tourism", "slug": "tourism", "name_en": "Tourism", "description": "Eco-tourism destinations, heritage trails, scenic rural exploration"},
            {"id": "life_food_cuisine", "slug": "food-and-cuisine", "name_en": "Food & Cuisine", "description": "Regional recipes, indigenous grains, culinary heritage preservation"},
            {"id": "life_fashion", "slug": "fashion", "name_en": "Fashion", "description": "Sustainable textiles, khadi revival, ethical organic fashion"},
            {"id": "life_home", "slug": "home", "name_en": "Home", "description": "Vernacular home design, urban rooftop gardening, sustainable living"},
            {"id": "life_hobbies", "slug": "hobbies", "name_en": "Hobbies", "description": "Bird watching, amateur astronomy, nature photography"}
        ]
    },
    {
        "id": 9,
        "slug": "economy-business",
        "visibility": "visible",
        "positive_fit": "medium",
        "special_rules": {
            "promotional_content_check": True,
            "corroboration_required": False,
            "gossip_excluded": False
        },
        "iptc_reference": {
            "qcode": "medtop:05000000",
            "uri": "http://cv.iptc.org/newscodes/mediatopic/05000000",
            "name_en": "economy, business and finance",
            "standard_version": "2024.1"
        },
        "display_names": {
            "en": "Economy & Business",
            "hi": "अर्थव्यवस्था एवं व्यापार",
            "bn": "অর্থনীতি ও বাণিজ্য",
            "mr": "अर्थव्यवस्था आणि व्यवसाय",
            "te": "ఆర్థిక వ్యవస్థ మరియు వ్యాపారం",
            "ta": "பொருளாதாரம் மற்றும் வணிகம்",
            "ur": "معیشت اور تجارت",
            "gu": "અર્થતંત્ર અને વેપાર",
            "kn": "ಆರ್ಥಿಕತೆ ಮತ್ತು ವ್ಯಾಪಾರ",
            "or": "ଅର୍ଥନୀତି ଏବଂ ବାଣିଜ୍ୟ",
            "ml": "സമ്പദ്‌വ്യവസ്ഥയും ബിസിനസും",
            "pa": "ਆਰਥਿਕਤਾ ਅਤੇ ਵਪਾਰ",
            "as": "অৰ্থনীতি আৰু ব্যৱসায়",
            "ne": "अर्थतन्त्र तथा व्यापार",
            "mai": "अर्थव्यवस्था आ व्यापार",
            "gom": "अर्थवेवस्था आनी वेपार"
        },
        "subcategories": [
            {"id": "econ_startups", "slug": "startups", "name_en": "Startups", "description": "Deep-tech innovation, social enterprises, homegrown startup milestones"},
            {"id": "econ_jobs", "slug": "jobs", "name_en": "Jobs", "description": "Formal job additions, employment expansion, apprenticeships"},
            {"id": "econ_msmes_trade", "slug": "msmes-and-trade", "name_en": "MSMEs & Trade", "description": "Micro and small business growth, manufacturing export records"},
            {"id": "econ_banking", "slug": "banking", "name_en": "Banking", "description": "Financial inclusion, priority sector credit, digital banking milestones"},
            {"id": "econ_consumer", "slug": "consumer", "name_en": "Consumer", "description": "Consumer protection verdicts, quality standards, transparent pricing"},
            {"id": "econ_corporate", "slug": "corporate", "name_en": "Corporate", "description": "Renewable corporate transitions, green investments, ESG achievements"}
        ]
    },
    {
        "id": 10,
        "slug": "health-wellness",
        "visibility": "visible",
        "positive_fit": "medium",
        "special_rules": {
            "promotional_content_check": False,
            "corroboration_required": True,
            "gossip_excluded": False
        },
        "iptc_reference": {
            "qcode": "medtop:08000000",
            "uri": "http://cv.iptc.org/newscodes/mediatopic/08000000",
            "name_en": "health",
            "standard_version": "2024.1"
        },
        "display_names": {
            "en": "Health & Wellness",
            "hi": "स्वास्थ्य एवं कल्याण",
            "bn": "স্বাস্থ্য ও কল্যাণ",
            "mr": "आरोग्य आणि निरोगी जीवन",
            "te": "ఆరోగ్యం మరియు శ్రేయస్సు",
            "ta": "சுகாதாரம் மற்றும் நல்வாழ்வு",
            "ur": "صحت اور تندرستی",
            "gu": "આરોગ્ય અને સુખાકારી",
            "kn": "ಆರೋಗ್ಯ ಮತ್ತು ಯೋಗಕ್ಷೇಮ",
            "or": "ସ୍ୱାସ୍ଥ୍ୟ ଏବଂ କଲ୍ୟାଣ",
            "ml": "ആരോഗ്യവും ക്ഷേമവും",
            "pa": "ਸਿਹਤ ਅਤੇ ਤੰਦਰੁਸਤੀ",
            "as": "স্বাস্থ্য আৰু কল্যাণ",
            "ne": "स्वास्थ्य तथा तन्दुरुस्ती",
            "mai": "स्वास्थ्य आ कल्याण",
            "gom": "भलायकी आनी बरेपण"
        },
        "subcategories": [
            {"id": "health_medical_research", "slug": "medical-research", "name_en": "Medical Research", "description": "Clinical discoveries, vaccine breakthroughs, disease diagnostic tools"},
            {"id": "health_public_health_programs", "slug": "public-health-programs", "name_en": "Public Health Programs", "description": "Immunization drives, tuberculosis eradication, maternal healthcare"},
            {"id": "health_hospitals_care", "slug": "hospitals-and-care", "name_en": "Hospitals & Care", "description": "Primary healthcare centers, specialized surgery camps, telemedicine"},
            {"id": "health_nutrition_fitness", "slug": "nutrition-and-fitness", "name_en": "Nutrition & Fitness", "description": "Community nutrition, wellness practices, lifestyle disease prevention"}
        ]
    },
    {
        "id": 11,
        "slug": "infrastructure-transport",
        "visibility": "visible",
        "positive_fit": "high",
        "special_rules": {
            "promotional_content_check": False,
            "corroboration_required": False,
            "gossip_excluded": False
        },
        "iptc_reference": {
            "qcode": "medtop:20000337",
            "uri": "http://cv.iptc.org/newscodes/mediatopic/20000337",
            "name_en": "transport",
            "standard_version": "2024.1"
        },
        "display_names": {
            "en": "Infrastructure & Transport",
            "hi": "बुनियादी ढांचा एवं परिवहन",
            "bn": "পরিকাঠামো ও পরিবহন",
            "mr": "पायाभूत सुविधा आणि वाहतूक",
            "te": "మౌలిక సదుపాయాలు మరియు రవాణా",
            "ta": "உள்கட்டமைப்பு மற்றும் போக்குவரத்து",
            "ur": "بنیادی ڈھانچہ اور نقل و حمل",
            "gu": "માળખાગત સુવિધાઓ અને પરિવહન",
            "kn": "ಮೂಲಸೌಕರ್ಯ ಮತ್ತು ಸಾರಿಗೆ",
            "or": "ମୌଳିକ ଢାଞ୍ଚା ଏବଂ ପରିବହନ",
            "ml": "അടിസ്ഥാന സൗകര്യങ്ങളും ഗതാഗതവും",
            "pa": "ਬੁਨਿਆਦੀ ਢਾਂਚਾ ਅਤੇ ਆਵਾਜਾਈ",
            "as": "গাঁথনি আৰু পৰিবহণ",
            "ne": "पूर्वाधार तथा यातायात",
            "mai": "पूर्वाधार आ परिवहन",
            "gom": "बुन्यादी सुविधा आनी येरादारी"
        },
        "subcategories": [
            {"id": "infra_roads", "slug": "roads", "name_en": "Roads", "description": "Highway corridors, rural road connectivity, bridge completions"},
            {"id": "infra_rail_metro", "slug": "rail-and-metro", "name_en": "Rail & Metro", "description": "Metro rail commissioning, Vande Bharat lines, railway electrification"},
            {"id": "infra_ports", "slug": "ports", "name_en": "Ports", "description": "Deepwater maritime ports, inland cargo waterways, logistics efficiency"},
            {"id": "infra_aviation", "slug": "aviation", "name_en": "Aviation", "description": "Regional airport connectivity, solar-powered terminals, air cargo"},
            {"id": "infra_housing", "slug": "housing", "name_en": "Housing", "description": "Affordable public housing construction, sustainable tenements"},
            {"id": "infra_urban_development", "slug": "urban-development", "name_en": "Urban Development", "description": "Smart city infrastructure, urban storm drainage, pedestrian walkways"},
            {"id": "infra_power", "slug": "power", "name_en": "Power", "description": "National power grid resilience, continuous power supply, substations"}
        ]
    },
    {
        "id": 12,
        "slug": "entertainment-media",
        "visibility": "visible",
        "positive_fit": "medium",
        "special_rules": {
            "promotional_content_check": False,
            "corroboration_required": False,
            "gossip_excluded": True
        },
        "iptc_reference": {
            "qcode": "medtop:01000000",
            "uri": "http://cv.iptc.org/newscodes/mediatopic/01000000",
            "name_en": "arts, culture, entertainment and media",
            "standard_version": "2024.1"
        },
        "display_names": {
            "en": "Entertainment & Media",
            "hi": "मनोरंजन एवं मीडिया",
            "bn": "বিনোদন ও মিডিয়া",
            "mr": "मनोरंजन आणि माध्यम",
            "te": "వినోదం మరియు మీడియా",
            "ta": "பொழுதுபோக்கு மற்றும் ஊடகம்",
            "ur": "تفریح اور میڈیا",
            "gu": "મનોરંજન અને મીડિયા",
            "kn": "ಮನರಂಜನೆ ಮತ್ತು ಮಾಧ್ಯಮ",
            "or": "ମନୋରଞ୍ଜନ ଏବଂ ଗଣମାଧ୍ୟମ",
            "ml": "വിനോദവും മാധ്യമവും",
            "pa": "ਮਨੋਰੰਜਨ ਅਤੇ ਮੀਡੀਆ",
            "as": "মনোৰঞ্জন আৰু মাধ্যম",
            "ne": "मनोरञ्जन तथा सञ्चार",
            "mai": "मनोरंजन आ मीडिया",
            "gom": "मनोरंजन आनी प्रसारमाध्यमां"
        },
        "subcategories": [
            {"id": "ent_cinema", "slug": "cinema", "name_en": "Cinema", "description": "Constructive cinema releases, classic film restoration, documentary honours"},
            {"id": "ent_music", "slug": "music", "name_en": "Music", "description": "Classical and fusion music albums, symphony orchestra performances"},
            {"id": "ent_tv_ott", "slug": "tv-and-ott", "name_en": "TV & OTT", "description": "Educational streaming series, non-fiction documentary broadcasts"},
            {"id": "ent_theatre", "slug": "theatre", "name_en": "Theatre", "description": "Regional theatre festivals, stage drama preservation, street theatre"},
            {"id": "ent_books", "slug": "books", "name_en": "Books", "description": "Literary book launches, public library initiatives, author achievements"},
            {"id": "ent_awards", "slug": "awards", "name_en": "Awards", "description": "National Film Awards, Academy recognitions, creative lifetime honours"}
        ]
    },
    {
        "id": 13,
        "slug": "world-diplomacy",
        "visibility": "visible",
        "positive_fit": "medium",
        "special_rules": {
            "promotional_content_check": False,
            "corroboration_required": False,
            "gossip_excluded": False
        },
        "iptc_reference": {
            "qcode": "medtop:20000638",
            "uri": "http://cv.iptc.org/newscodes/mediatopic/20000638",
            "name_en": "international relations",
            "standard_version": "2024.1"
        },
        "display_names": {
            "en": "World & Diplomacy",
            "hi": "विश्व एवं कूटनीति",
            "bn": "বিশ্ব ও কূটনীতি",
            "mr": "विश्व आणि मुत्सद्देगिरी",
            "te": "ప్రపంచం మరియు దౌత్యం",
            "ta": "உலகம் மற்றும் ராஜதந்திரம்",
            "ur": "دنیا اور سفارت کاری",
            "gu": "વિશ્વ અને મુત્સદ્દીગીરી",
            "kn": "ವಿಶ್ವ ಮತ್ತು ರಾಜತಾಂತ್ರಿಕತೆ",
            "or": "ବିଶ୍ୱ ଏବଂ କୂଟନୀତି",
            "ml": "ലോകവും നയതന്ത്രവും",
            "pa": "ਵਿਸ਼ਵ ਅਤੇ ਕੂਟਨੀਤੀ",
            "as": "বিশ্ব আৰু কূটনীতি",
            "ne": "विश्व तथा कूटनीति",
            "mai": "विश्व आ कूटनीति",
            "gom": "संवसार आनी राजनय"
        },
        "subcategories": [
            {"id": "world_bilateral_cooperation", "slug": "bilateral-cooperation", "name_en": "Bilateral Cooperation", "description": "Joint bilateral scientific, cultural and trade partnerships"},
            {"id": "world_agreements", "slug": "agreements", "name_en": "Agreements", "description": "Multilateral accords, environmental treaties, cross-border pacts"},
            {"id": "world_diaspora_achievements", "slug": "diaspora-achievements", "name_en": "Diaspora Achievements", "description": "Global Indian community milestones, overseas civic leadership"},
            {"id": "world_global_collaboration", "slug": "global-collaboration", "name_en": "Global Collaboration", "description": "International disaster relief, multinational scientific consortia"}
        ]
    },
    {
        "id": 14,
        "slug": "governance-public-services",
        "visibility": "hidden",
        "positive_fit": "low",
        "special_rules": {
            "promotional_content_check": False,
            "corroboration_required": False,
            "gossip_excluded": False
        },
        "iptc_reference": {
            "qcode": "medtop:12000000",
            "uri": "http://cv.iptc.org/newscodes/mediatopic/12000000",
            "name_en": "politics and government",
            "standard_version": "2024.1"
        },
        "display_names": {
            "en": "Governance & Public Services",
            "hi": "शासन एवं सार्वजनिक सेवाएं",
            "bn": "প্রশাসন ও জনসেবা",
            "mr": "प्रशासन आणि सार्वजनिक सेवा",
            "te": "పాలన మరియు ప్రజా సేవలు",
            "ta": "ஆளுகை மற்றும் பொது சேவைகள்",
            "ur": "حکمرانی اور عوامی خدمات",
            "gu": "શાસન અને જાહેર સેવાઓ",
            "kn": "ಆಡಳಿತ ಮತ್ತು ಸಾರ್ವಜನಿಕ ಸೇವೆಗಳು",
            "or": "ଶାସନ ଏବଂ ସର୍ବସାଧାରଣ ସେବା",
            "ml": "ഭരണവും പൊതുസേവനങ്ങളും",
            "pa": "ਪ੍ਰਸ਼ਾਸਨ ਅਤੇ ਜਨਤਕ ਸੇਵਾਵਾਂ",
            "as": "প্ৰশাসন আৰু ৰাজহুৱা সেৱা",
            "ne": "सुशासन तथा सार्वजनिक सेवा",
            "mai": "शासन आ सार्वजनिक सेवा",
            "gom": "शासन आनी भौशीक सेवा"
        },
        "subcategories": [
            {"id": "gov_civic_administration", "slug": "civic-administration", "name_en": "Civic Administration", "description": "Administrative reforms, municipal governance improvements"},
            {"id": "gov_public_schemes", "slug": "public-schemes", "name_en": "Public Schemes", "description": "Direct benefit transfers, social security coverage"},
            {"id": "gov_citizen_services", "slug": "citizen-services", "name_en": "Citizen Services", "description": "Public grievance portals, single-window citizen services"}
        ]
    },
    {
        "id": 15,
        "slug": "law-justice-safety",
        "visibility": "hidden",
        "positive_fit": "low",
        "special_rules": {
            "promotional_content_check": False,
            "corroboration_required": False,
            "gossip_excluded": False
        },
        "iptc_reference": {
            "qcode": "medtop:03000000",
            "uri": "http://cv.iptc.org/newscodes/mediatopic/03000000",
            "name_en": "crime, law and justice",
            "standard_version": "2024.1"
        },
        "display_names": {
            "en": "Law, Justice & Safety",
            "hi": "कानून, न्याय एवं सुरक्षा",
            "bn": "আইন, বিচার ও নিরাপত্তা",
            "mr": "कायदा, न्याय आणि सुरक्षा",
            "te": "చట్టం, న్యాయం మరియు భద్రత",
            "ta": "சட்டம், நீதி மற்றும் பாதுகாப்பு",
            "ur": "قانون، انصاف اور تحفظ",
            "gu": "કાયદો, ન્યાય અને સલામતી",
            "kn": "ಕಾನೂನು, ನ್ಯಾಯ ಮತ್ತು ಸುರಕ್ಷತೆ",
            "or": "ଆଇନ, ନ୍ୟାୟ ଏବଂ ସୁରକ୍ଷା",
            "ml": "നിയമം, നീതി, സുരക്ഷ",
            "pa": "ਕਾਨੂੰਨ, ਨਿਆਂ ਅਤੇ ਸੁਰੱਖਿਆ",
            "as": "আইন, ন্যায় আৰু সুৰক্ষা",
            "ne": "कानुन, न्याय तथा सुरक्षा",
            "mai": "कानून, न्याय आ सुरक्षा",
            "gom": "कायदो, न्याय आनी सुरक्षा"
        },
        "subcategories": [
            {"id": "law_legal_aid", "slug": "legal-aid", "name_en": "Legal Aid", "description": "Pro bono legal services, Lok Adalat resolutions"},
            {"id": "law_judicial_reforms", "slug": "judicial-reforms", "name_en": "Judicial Reforms", "description": "Fast-track dispute mechanisms, court digital record initiatives"},
            {"id": "law_consumer_rights", "slug": "consumer-rights", "name_en": "Consumer Rights", "description": "Consumer protection judgements, citizen safety advocacy"}
        ]
    },
    {
        "id": 16,
        "slug": "religion-spirituality",
        "visibility": "hidden",
        "positive_fit": "low",
        "special_rules": {
            "promotional_content_check": False,
            "corroboration_required": False,
            "gossip_excluded": False
        },
        "iptc_reference": {
            "qcode": "medtop:13000000",
            "uri": "http://cv.iptc.org/newscodes/mediatopic/13000000",
            "name_en": "religion",
            "standard_version": "2024.1"
        },
        "display_names": {
            "en": "Religion & Spirituality",
            "hi": "धर्म एवं आध्यात्मिकता",
            "bn": "ধর্ম ও আধ্যাত্মিকতা",
            "mr": "धर्म आणि अध्यात्म",
            "te": "మతం మరియు ఆధ్యాత్మికత",
            "ta": "மதம் மற்றும் ஆன்மீகம்",
            "ur": "مذہب اور روحانیت",
            "gu": "ધર્મ અને આધ્યાત્મિકતા",
            "kn": "ಧರ್ಮ ಮತ್ತು ಆಧ್ಯಾತ್ಮಿಕತೆ",
            "or": "ଧର୍ମ ଏବଂ ଆଧ୍ୟାତ୍ମିକତା",
            "ml": "മതവും ആത്മീയതയും",
            "pa": "ਧਰਮ ਅਤੇ ਅਧਿਆਤਮਿਕਤਾ",
            "as": "ধৰ্ম আৰু আধ্যাত্মিকতা",
            "ne": "धर्म तथा आध्यात्मिकता",
            "mai": "धर्म आ आध्यात्मिकता",
            "gom": "धर्म आनी अध्यात्म"
        },
        "subcategories": [
            {"id": "rel_interfaith_initiatives", "slug": "interfaith-initiatives", "name_en": "Interfaith Initiatives", "description": "Inter-community communal harmony, shared spiritual traditions"},
            {"id": "rel_spiritual_wellness", "slug": "spiritual-wellness", "name_en": "Spiritual Wellness", "description": "Mindfulness philosophy, meditation traditions"},
            {"id": "rel_sacred_architecture", "slug": "sacred-architecture", "name_en": "Sacred Architecture", "description": "Heritage shrine restoration, pilgrim facilitation infrastructure"}
        ]
    },
    {
        "id": 17,
        "slug": "defence-security",
        "visibility": "hidden",
        "positive_fit": "low",
        "special_rules": {
            "promotional_content_check": False,
            "corroboration_required": False,
            "gossip_excluded": False
        },
        "iptc_reference": {
            "qcode": "medtop:02000000",
            "uri": "http://cv.iptc.org/newscodes/mediatopic/02000000",
            "name_en": "conflict, war and peace",
            "standard_version": "2024.1"
        },
        "display_names": {
            "en": "Defence & Security",
            "hi": "रक्षा एवं सुरक्षा",
            "bn": "প্রতিরক্ষা ও নিরাপত্তা",
            "mr": "संरक्षण आणि सुरक्षा",
            "te": "రక్షణ మరియు భద్రత",
            "ta": "பாதுகாப்பு மற்றும் தற்காப்பு",
            "ur": "دفاع اور سلامتی",
            "gu": "સંરક્ષણ અને સુરક્ષા",
            "kn": "ರಕ್ಷಣೆ ಮತ್ತು ಭದ್ರತೆ",
            "or": "ପ୍ରତିରକ୍ଷା ଏବଂ ସୁରକ୍ଷା",
            "ml": "പ്രതിരോധവും സുരക്ഷയും",
            "pa": "ਰੱਖਿਆ ਅਤੇ ਸੁਰੱਖਿਆ",
            "as": "প্ৰতিৰক্ষা আৰু সুৰক্ষা",
            "ne": "रक्षा तथा सुरक्षा",
            "mai": "रक्षा आ सुरक्षा",
            "gom": "राखण आनी सुरक्षा"
        },
        "subcategories": [
            {"id": "def_veteran_welfare", "slug": "veteran-welfare", "name_en": "Veteran Welfare", "description": "Ex-servicemen rehabilitation, gallantry welfare initiatives"},
            {"id": "def_peacekeeping", "slug": "peacekeeping", "name_en": "Peacekeeping", "description": "UN peacekeeping missions, humanitarian relief assignments"},
            {"id": "def_border_infrastructure", "slug": "border-infrastructure", "name_en": "Border Infrastructure", "description": "Strategic border roads, high-altitude bridges"}
        ]
    },
    {
        "id": 18,
        "slug": "disaster-emergency",
        "visibility": "hidden",
        "positive_fit": "low",
        "special_rules": {
            "promotional_content_check": False,
            "corroboration_required": False,
            "gossip_excluded": False
        },
        "iptc_reference": {
            "qcode": "medtop:04000000",
            "uri": "http://cv.iptc.org/newscodes/mediatopic/04000000",
            "name_en": "disaster, accident and emergency incident",
            "standard_version": "2024.1"
        },
        "display_names": {
            "en": "Disaster & Emergency",
            "hi": "आपदा एवं आपातकाल",
            "bn": "দুর্যোগ ও জরুরি অবস্থা",
            "mr": "आपत्ती आणि आणीबाणी",
            "te": "విపత్తు మరియు అత్యవసర పరిస్థితి",
            "ta": "பேரிடர் மற்றும் அவசரநிலை",
            "ur": "آفات اور ایمرجنسی",
            "gu": "આપત્તિ અને કટોકટી",
            "kn": "ವಿಪತ್ತು ಮತ್ತು ತುರ್ತುಸ್ಥಿತಿ",
            "or": "ବିପର୍ଯ୍ୟୟ ଏବଂ ଜରୁରୀକାଳୀନ",
            "ml": "ദുരന്തവും അടിയന്തരാവസ്ഥയും",
            "pa": "ਆਫ਼ਤ ਅਤੇ ਐਮਰਜੈਂਸੀ",
            "as": "দুৰ্যোগ আৰু জৰুৰীকালীন",
            "ne": "विपद् तथा आपतकाल",
            "mai": "आपदा आ आपातकाल",
            "gom": "आपत्ती आनी आपत्कालीन"
        },
        "subcategories": [
            {"id": "dis_disaster_resilience", "slug": "disaster-resilience", "name_en": "Disaster Resilience", "description": "Cyclone shelter construction, earthquake-resilient structures"},
            {"id": "dis_relief_operations", "slug": "relief-operations", "name_en": "Relief Operations", "description": "NDRF humanitarian rescues, flood relief supply logistics"},
            {"id": "dis_early_warning", "slug": "early-warning-systems", "name_en": "Early Warning Systems", "description": "Doppler weather radars, tsunami warning buoys"}
        ]
    }
]


def generate_taxonomy_v1_json():
    from src.taxonomy.models import Category
    validated_cats = [Category.model_validate(c).model_dump(mode="json") for c in TAXONOMY_CATEGORIES]
    canonical_repr = json.dumps(validated_cats, sort_keys=True, ensure_ascii=False)
    checksum = hashlib.sha256(canonical_repr.encode("utf-8")).hexdigest()

    manifest = {
        "version": "1.0.0",
        "effective_date": "2026-10-22",
        "description": "Taxonomy v1: 13 visible constructive categories, 5 reserved hidden categories, IPTC 2024.1 crosswalk",
        "checksum": checksum,
        "categories": validated_cats
    }

    out_dir = Path(__file__).resolve().parent.parent / "config" / "taxonomy"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "v1.json"

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"Generated {out_file} with checksum {checksum}")


if __name__ == "__main__":
    generate_taxonomy_v1_json()
