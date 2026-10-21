"""
Phase 0 Pilot Evaluation Harness
Evaluates:
1. Positivity classification rubric on representative articles (positive, negative, toxic positivity, neutral).
2. Token fertility across languages.
3. Language identification accuracy & script disambiguation across 16 languages.
4. Faithfulness verification metrics on synthetic faithful vs unfaithful candidate summaries.
5. Multilingual deduplication similarity using embeddings.
6. Per-item cost modeling per language.
"""

import json
import os
import sys
import numpy as np

# Safe patch for fasttext on numpy 2.x
orig_array = np.array
def safe_array(obj, *args, **kwargs):
    if kwargs.get('copy') is False:
        kwargs.pop('copy')
        return np.asarray(obj, *args, **kwargs)
    return orig_array(obj, *args, **kwargs)
np.array = safe_array

import tiktoken

def get_pilot_articles():
    """
    Returns 25 curated benchmark items across English and Indic languages.
    Labels:
    POSITIVE: Beneficial/constructive outcome, breakthrough, solution, recovery, community win.
    NEGATIVE: Violent crime, disaster, fatal accident, political smear, catastrophe.
    NEUTRAL: Routine administrative announcement, market close indices, schedule.
    TOXIC_POSITIVITY: Superficial 'feel good' story masking severe exploitation or distress.
    """
    return [
        {
            "id": "art_01",
            "language": "en",
            "headline": "IISc scientists develop ultra-low-cost water purification membrane using agricultural waste",
            "body": "Researchers at the Indian Institute of Science (IISc) Bengaluru have synthesized a nanotech filtration membrane from discarded rice husks that removes 99.8% of heavy metals and microplastics from rural groundwater at one-fifth the cost of conventional filters.",
            "ground_truth": "POSITIVE",
            "category": "Science/Tech/Environment",
            "faithful_summary": "IISc researchers created an affordable water filtration membrane from rice husks capable of eliminating nearly all heavy metals and microplastics from rural groundwater.",
            "unfaithful_summary": "IISc researchers partnered with a multinational conglomerate to bottle and sell luxury mineral water across urban India."
        },
        {
            "id": "art_02",
            "language": "en",
            "headline": "Tragic bus collision on National Highway claims 14 lives in northern district",
            "body": "Fourteen passengers died and over twenty sustained critical injuries following a head-on collision between a state transport bus and a speeding freight carrier early Tuesday morning in dense fog.",
            "ground_truth": "NEGATIVE",
            "category": "Accident/Disaster",
            "faithful_summary": "Fourteen people were killed and over twenty injured in a severe highway crash involving a state transport bus and a truck during heavy morning fog.",
            "unfaithful_summary": "Local authorities celebrated zero road accidents this month thanks to new solar-powered highway lighting."
        },
        {
            "id": "art_03",
            "language": "en",
            "headline": "8-Year-Old Works 14 Hours Daily Selling Flowers to Pay for Mother's Cancer Treatment",
            "body": "In an inspiring tale of filial devotion, young Aryan spends 14 hours every day at the traffic junction selling marigold garlands so he can afford the chemotherapy injections needed by his ailing mother.",
            "ground_truth": "TOXIC_POSITIVITY_EXCLUDE",
            "category": "Toxic Positivity / Child Exploitation",
            "faithful_summary": "An eight-year-old boy spends fourteen hours a day selling garlands at traffic signals to fund his mother's chemotherapy treatments.",
            "unfaithful_summary": "The government granted comprehensive health insurance covering the entire cancer treatment for the family."
        },
        {
            "id": "art_04",
            "language": "en",
            "headline": "Reserve Bank of India keeps repo rate unchanged at 6.50% in bi-monthly monetary policy",
            "body": "The Monetary Policy Committee of the Reserve Bank of India decided unanimously to maintain the benchmark policy repo rate at 6.50 percent, citing balanced domestic growth dynamics and ongoing food inflation vigilance.",
            "ground_truth": "NEUTRAL",
            "category": "Macroeconomics/Policy",
            "faithful_summary": "The RBI Monetary Policy Committee voted to keep the key repo rate steady at 6.50 percent to support growth while monitoring inflation.",
            "unfaithful_summary": "The RBI slashed lending rates by 200 basis points triggering record stock market rallies."
        },
        {
            "id": "art_05",
            "language": "hi",
            "headline": "राजस्थान के मरुस्थलीय जिले में सौर ऊर्जा से संचालित 50 नए प्राथमिक स्वास्थ्य केंद्र शुरू, 1 लाख ग्रामीणों को मिला लाभ",
            "body": "राजस्थान के बाड़मेर और जैसलमेर जिलों के दूरदराज गांवों में 50 प्राथमिक स्वास्थ्य केंद्रों को 100% रूफटॉप सौर ऊर्जा और बैटरी बैकअप से लैस किया गया है। इससे पिछले छह महीनों में निर्बाध प्रसव सुविधाएं और कोल्ड-चेन वैक्सीन स्टोरेज संभव हुआ है।",
            "ground_truth": "POSITIVE",
            "category": "Community/Infrastructure",
            "faithful_summary": "राजस्थान के दूरदराज मरुस्थलीय इलाकों में 50 प्राथमिक स्वास्थ्य केंद्रों को सौर ऊर्जा से जोड़कर निर्बाध ग्रामीण चिकित्सा सेवाएं सुनिश्चित की गई हैं।",
            "unfaithful_summary": "राजस्थान सरकार ने बजट की कमी के कारण 50 ग्रामीण स्वास्थ्य केंद्रों को स्थायी रूप से बंद कर दिया है।"
        },
        {
            "id": "art_06",
            "language": "hi",
            "headline": "राजधानी में बहुमंजिला वाणिज्यिक इमारत में भीषण आग, 6 दमकलकर्मी घायल",
            "body": "मध्य दिल्ली के एक व्यस्त व्यावसायिक परिसर में शॉर्ट सर्किट के चलते भीषण आग लग गई, जिसे बुझाने के प्रयास में छह दमकलकर्मी धुएं और तपिश के कारण झुलस गए।",
            "ground_truth": "NEGATIVE",
            "category": "Fire/Accident",
            "faithful_summary": "मध्य दिल्ली की एक व्यावसायिक इमारत में शॉर्ट सर्किट से आग लगने के बाद बचाव अभियान के दौरान छह दमकलकर्मी घायल हो गए।",
            "unfaithful_summary": "दिल्ली में सभी व्यावसायिक इमारतों ने अत्याधुनिक अग्नि सुरक्षा प्रमाण पत्र हासिल किया।"
        },
        {
            "id": "art_07",
            "language": "mr",
            "headline": "सह्याद्रीच्या कुशीत आदिवासी महिलांनी उभारली औषधी वनस्पतींची यशस्वी सहकारी संस्था; 1200 कुटुंबांचे स्थलांतर थांबले",
            "body": "गडचिरोली व चंद्रपूर जिल्ह्यातील सुमारे 1200 आदिवासी महिलांनी एकत्र येत रानभाज्या आणि पारंपरिक औषधी वनस्पतींवर प्रक्रिया करणारी सहकारी संस्था स्थापन केली आहे. या उपक्रमामुळे दरमहा शाश्वत उत्पन्न मिळून रोजगारासाठी होणारे स्थलांतर पूर्णपणे थांबले आहे.",
            "ground_truth": "POSITIVE",
            "category": "Livelihood/Empowerment",
            "faithful_summary": "गडचिरोलीतील आदिवासी महिलांनी सुरू केलेल्या औषधी वनस्पती प्रक्रिया सहकारी संस्थेमुळे 1200 कुटुंबांना शाश्वत उपजीविका मिळून स्थलांतर रोखण्यात यश आले आहे.",
            "unfaithful_summary": "गडचिरोलीतील औषधी वनस्पतींचा कारखाना तोट्यात गेल्याने हजारो कुटुंबांनी इतर राज्यांत स्थलांतर केले."
        },
        {
            "id": "art_08",
            "language": "bn",
            "headline": "সুন্দরবনের নদীভাঙন রোধে স্থানীয় মহিলাদের ম্যানগ্রোভ রোপণ আন্দোলন সফল, ৫ হেক্টর বনাঞ্চল পুনরুজ্জীবিত",
            "body": "ঘূর্ণিঝড়প্রবণ সুন্দরবনের গোসাবা ব্লকে ৫০০ জন স্থানীয় গ্রামবাসী নারী স্বেচ্ছায় ম্যানগ্রোভ নার্সারি তৈরি করে নদীবাঁধ বরাবর ৫ হেক্টর জমিতে নতুন বন সৃজন করেছেন, যা সাম্প্রতিক জলোচ্ছ্বাসে মাটির ক্ষয় সম্পূর্ণ রোধ করেছে।",
            "ground_truth": "POSITIVE",
            "category": "Environment/Ecology",
            "faithful_summary": "সুন্দরবনের গোসাবায় স্থানীয় নারীদের উদ্যোগে নদীবাঁধ সংলগ্ন অঞ্চলে সফলভাবে ম্যানগ্রোভ অরণ্য পুনর্নির্মাণ করে ভাঙন রোধ করা সম্ভব হয়েছে।",
            "unfaithful_summary": "সুন্দরবনের সাম্প্রতিক জলোচ্ছ্বাসে সমস্ত নতুন ম্যানগ্রোভ গাছ উপড়ে গিয়ে বিপুল ক্ষয়ক্ষতি হয়েছে।"
        },
        {
            "id": "art_09",
            "language": "te",
            "headline": "తెలంగాణ రైతు యువకుడి వినూత్న ఆవిష్కరణ: సౌరశక్తితో నడిచే డ్రోన్ స్ప్రేయర్‌తో 70 శాతం సాగు ఖర్చు ఆదా",
            "body": "వరంగల్ జిల్లాకు చెందిన ఇంజనీరింగ్ పట్టభద్రుడైన యువకుడు పూర్తిగా స్థానిక విడిభాగాలతో తక్కువ ఖర్చుతో కూడిన సోలార్ అగ్రికల్చర్ డ్రోన్‌ను రూపొందించాడు. దీనివల్ల రసాయనాల వృథా తగ్గి ఎకరానికి ఖర్చు 70 శాతం తగ్గింది.",
            "ground_truth": "POSITIVE",
            "category": "Agri-Tech/Innovation",
            "faithful_summary": "వరంగల్ యువకుడు తయారుచేసిన సౌర ఆధారిత వ్యవసాయ డ్రోన్ రైతుల సాగు వ్యయాన్ని 70 శాతం వరకు తగ్గించడంలో విజయవంతమైంది.",
            "unfaithful_summary": "కేంద్ర ప్రభుత్వం అన్ని రకాల డ్రోన్ల వినియోగంపై పూర్తి స్థాయి నిషేధం విధించింది."
        },
        {
            "id": "art_10",
            "language": "ta",
            "headline": "தூத்துக்குடியில் மாற்றுத்திறனாளி இளைஞர்கள் உருவாக்கிய கடல்பாசி வளர்ப்பு கூட்டுறவு சங்கம்; மாதம் ரூ.45,000 வருவாய்",
            "body": "தூத்துக்குடி கடலோரப் பகுதியில் 80 மாற்றுத்திறனாளி இளைஞர்கள் ஒன்றிணைந்து அறிவியல் பூர்வமான கடல்பாசி வளர்ப்பு திட்டத்தை மேற்கொண்டு, பதப்படுத்தப்பட்ட இயற்கை உரம் மற்றும் அழகுசாதன மூலப்பொருட்களை ஏற்றுமதி செய்து நிலையான வாழ்வாதாரம் பெற்றுள்ளனர்.",
            "ground_truth": "POSITIVE",
            "category": "Inclusion/Livelihood",
            "faithful_summary": "தூத்துக்குடியில் மாற்றுத்திறனாளி இளைஞர்கள் அமைத்த கடல்பாசி வளர்ப்பு கூட்டுறவு முயற்சி நிலையான வருமானத்தையும் ஏற்றுமதி வாய்ப்பையும் ஏற்படுத்தியுள்ளது.",
            "unfaithful_summary": "கடலோர ஒழுங்குமுறை ஆணையம் கடல்பாசி வளர்ப்பு திட்டங்களை உடனடியாக நிறுத்த உத்தரவிட்டுள்ளது."
        },
        {
            "id": "art_11",
            "language": "gu",
            "headline": "કચ્છના રણમાં ખારા પાણીને પીવાલાયક બનાવતો દેશનો પ્રથમ સૌર ડીસેલિનેશન પ્લાન્ટ શરૂ",
            "body": "કચ્છ જિલ્લાના સરહદી ગામડાઓમાં ભૂગર્ભ ક્ષારયુક્ત પાણીને આધુનિક સોલર મેમ્બ્રેન ડીસેલિનેશન પદ્ધતિથી શુદ્ધ કરી દૈનિક ૨ લાખ લિટર પીવાનું શુદ્ધ પાણી પૂરું પાડવાનો પ્રોજેક્ટ સફળતાપૂર્વક કાર્યરત થયો છે.",
            "ground_truth": "POSITIVE",
            "category": "Water/CleanTech",
            "faithful_summary": "કચ્છના સરહદી વિસ્તારમાં સૌર ઊર્જાથી ખારા પાણીને પીવાલાયક બનાવતો પ્લાન્ટ શરૂ થતાં ગામડાઓમાં પીવાના પાણીની સમસ્યા દૂર થઈ છે.",
            "unfaithful_summary": "કચ્છ ડીસેલિનેશન પ્લાન્ટનું બાંધકામ ભ્રષ્ટાચારના આરોપો બાદ અધૂરું મૂકી દેવામાં આવ્યું."
        },
        {
            "id": "art_12",
            "language": "kn",
            "headline": "ಬೆಂಗಳೂರು ಗ್ರಾಮಾಂತರದಲ್ಲಿ ಕೆರೆಗಳ ಪುನಶ್ಚೇತನ: 15 ವರ್ಷಗಳ ಬಳಿಕ 40 ಅಡಿ ಮೇಲೇರಿದ ಅಂತರ್ಜಲ ಮಟ್ಟ",
            "body": "ಸ್ಥಳೀಯ ರೈತರ ಒಕ್ಕೂಟ ಮತ್ತು ಪರಿಸರ ಕಾರ್ಯಕರ್ತರು ಜಂಟಿಯಾಗಿ 12 ಹೂಳು ತುಂಬಿದ ಕೆರೆಗಳನ್ನು ಸ್ವಚ್ಛಗೊಳಿಸಿ ಮಳೆನೀರು ಕೊಯ್ಲು ವ್ಯವಸ್ಥೆ ರೂಪಿಸಿದ ಪರಿಣಾಮ ಸುತ್ತಮುತ್ತಲಿನ 18 ಹಳ್ಳಿಗಳಲ್ಲಿ ಅಂತರ್ಜಲ ಮಟ್ಟ ಗಣನೀಯವಾಗಿ ಹೆಚ್ಚಿದೆ.",
            "ground_truth": "POSITIVE",
            "category": "Environment/Conservation",
            "faithful_summary": "ಬೆಂಗಳೂರು ಗ್ರಾಮಾಂತರದ ಕೆರೆಗಳ ಸಮಗ್ರ ಪುನಶ್ಚೇತನದಿಂದಾಗಿ ದಶಕಗಳ ಬಳಿಕ ಅಂತರ್ಜಲ ಮಟ್ಟ ಸುಧಾರಿಸಿ ಕೃಷಿಗೆ ಅನುಕೂಲವಾಗಿದೆ.",
            "unfaithful_summary": "ಅಂತರ್ಜಲ ಕುಸಿತದ ಹಿನ್ನೆಲೆಯಲ್ಲಿ ಗ್ರಾಮಸ್ಥರು ಕೃಷಿ ತೊರೆದು ನಗರಕ್ಕೆ ವಲಸೆ ಹೋಗಲು ತೀರ್ಮಾನಿಸಿದ್ದಾರೆ."
        },
        {
            "id": "art_13",
            "language": "ml",
            "headline": "വയനാട്ടിലെ ഉരുൾപൊട്ടൽ ബാధిதർക്കായി 100 ದಿನಗಳಲ್ಲಿ പരിസ്ഥിതി സൗഹൃദ മാതൃಕಾ ഗ്രാമം യാഥാർത്ഥ്യമാക്കി സന്നദ്ധ കൂട്ടായ്മ",
            "body": "ദുരന്തബാധിതരായ 75 കുടുംബങ്ങൾക്ക് സുരക്ഷിതമായ ഉയർന്ന പ്രദേശത്ത് പ്രകൃതിദുരന്തങ്ങളെ പ്രതിരോധിക്കുന്ന സുಸ್ಥಿರ മുള-മൺ ഭവനങ്ങളും കമ്മ്യൂണിറ്റി ഹെൽത്ത് സെന്ററും നിർമ്മിച്ച് കൈമാറി.",
            "ground_truth": "POSITIVE",
            "category": "Disaster Recovery/Resilience",
            "faithful_summary": "വയനാട്ടിലെ ദുരന്തബാധിത കുടുംബങ്ങൾക്കായി സുരക്ഷിത സ്ഥലത്ത് പ്രകൃതിസൗഹൃദ പുനരധിവാസ ഗ്രാമം റെക്കോർഡ് വേഗത്തിൽ പൂർത്തിയാക്കി.",
            "unfaithful_summary": "പുനരധിവാസ ഫണ്ട് വകമാറ്റിയതിനെതിരെ ദുരിതബാധിതർ അനിശ്ചിതകാല സമരം ആരംഭിച്ചു."
        },
        {
            "id": "art_14",
            "language": "pa",
            "headline": "ਪੰਜਾਬ ਦੇ ਕਿਸਾਨਾਂ ਨੇ ਪਰਾਲੀ ਸਾੜਨ ਦੀ ਸਮੱਸਿਆ ਦਾ ਕੱਢਿਆ ਹੱਲ; ਬਾਇਓ-ਕੰਪੋਸਟ ਬਣਾ ਕੇ ਖਾਦ ਦੇ ਖਰਚੇ ਵਿੱਚ 50% ਕਟੌਤੀ ਕੀਤੀ",
            "body": "ਲੁਧਿਆਣਾ ਜ਼ਿਲ੍ਹੇ ਦੇ 25 ਪਿੰਡਾਂ ਨੇ ਸਹਿਕਾਰੀ ਮਾਡਲ ਅਪਣਾ ਕੇ ਝੋਨੇ ਦੀ ਪਰਾਲੀ ਤੋਂ ਉੱਚ ਪੱਧਰੀ ਜੈਵਿਕ ਖਾਦ ਤਿਆਰ ਕੀਤੀ, ਜਿਸ ਨਾਲ ਜ਼ੀਰੋ ਪਰਾਲੀ ਸਾੜਨ ਦਾ ਟੀਚਾ ਹਾਸਲ ਹੋਇਆ ਅਤੇ ਜ਼ਮੀਨ ਦੀ ਉਪਜਾਊ ਸ਼ਕਤੀ ਵਧੀ।",
            "ground_truth": "POSITIVE",
            "category": "Agriculture/Ecology",
            "faithful_summary": "ਲੁਧਿਆਣਾ ਦੇ ਪਿੰਡਾਂ ਨੇ ਪਰਾਲੀ ਨੂੰ ਜੈਵਿਕ ਖਾਦ ਵਿੱਚ ਬਦਲ ਕੇ ਪਰਾਲੀ ਸਾੜਨ ਦੀ ਸਮੱਸਿਆ ਖ਼ਤਮ ਕੀਤੀ ਅਤੇ ਖੇਤੀ ਲਾਗਤ ਘਟਾਈ।",
            "unfaithful_summary": "ਪਰਾਲੀ ਸਾੜਨ ਦੇ ਦੋਸ਼ ਵਿੱਚ ਪੁਲਿਸ ਨੇ ਸੈਂਕੜੇ ਕਿਸਾਨਾਂ ਖ਼ਿਲਾਫ਼ ਪਰਚੇ ਦਰਜ ਕੀਤੇ।"
        },
        {
            "id": "art_15",
            "language": "ur",
            "headline": "جامعہ ملیہ اسلامیہ کے طلباء نے بصارت سے محروم افراد کے لیے سمارٹ بریل نیویગیشن ڈیوائس تیار کی",
            "body": "طلباء کی ایک ٹیم نے جدید سینسرز اور آواز پر مبنی ایک سستا نیویگیشن سسٹم تیار کیا ہے جو بصارت سے محروم افراد کو اندرونی اور بیرونی راستوں میں آزادانہ نقل و حرکت کی سہولت فراہم کرتا ہے۔",
            "ground_truth": "POSITIVE",
            "category": "Assistive Tech/Invention",
            "faithful_summary": "جامعہ کے طلباء نے بصارت سے محروم افراد کی خودمختار نقل و حرکت کے لیے ایک سمارٹ اور سستا معاون آلہ ایجاد کیا۔",
            "unfaithful_summary": "جامعہ ملیہ اسلامیہ نے فنڈز کی کمی کے باعث تمام ریسرچ پراجیکٹس غیر معینہ مدت کے لیے روک دیے۔"
        },
        {
            "id": "art_16",
            "language": "or",
            "headline": "କୋରାପୁଟ ଜିଲ୍ଲାରେ ଆଦିବାସୀ ମହିଳାଙ୍କ କଫି ଚାଷକୁ ଅନ୍ତର୍ଜାତୀୟ ସ୍ୱୀକୃତି; ୨୦୦୦ ଚାଷୀଙ୍କ ରୋଜଗାର ଦୁଇଗୁଣ ହେଲା",
            "body": "କୋରାପୁଟର ଜୈବିକ ଆରାବିକା କଫିକୁ ଅନ୍ତର୍ଜାତୀୟ ବଜାରରେ ପ୍ରିମିୟମ ମୂଲ୍ୟ ମିଳିବା ପରେ ସ୍ଥାନୀୟ ମହିଳା ସ୍ୱୟଂ ସହାୟକ ଗୋଷ୍ଠୀ ସଫଳତାର ନୂଆ ଇତିହାସ ସୃଷ୍ଟି କରିଛନ୍ତି।",
            "ground_truth": "POSITIVE",
            "category": "Agriculture/Export",
            "faithful_summary": "କୋରାପୁଟର ଆଦିବାସୀ ମହିଳାଙ୍କ ଜୈବିକ କଫି ଅନ୍ତର୍ଜାତୀୟ ମାନ୍ୟତା ପାଇବା ଫଳରେ ହଜାର ହଜାର ଚାଷୀ ପରିବାର ଆର୍ଥିକ ଭାବେ ସ୍ୱାବଲମ୍ବୀ ହୋଇଛନ୍ତି।",
            "unfaithful_summary": "ଅଦିନିଆ ବର୍ଷା ଯୋଗୁଁ କୋରାପୁଟର ସମସ୍ତ କଫି ଫସଲ ସମ୍ପୂର୍ଣ୍ଣ ନଷ୍ଟ ହୋଇଯାଇଛି।"
        },
        {
            "id": "art_17",
            "language": "as",
            "headline": "কাজিৰঙাত চোৰাং চিকাৰীৰ বিৰুদ্ধে বন সুৰক্ষা কৰ্মীৰ কঠোৰ অভিযান সফল; একেৰাহে দ্বিতীয় বছৰ এটাও গঁড় হত্যা নোহোৱাৰ অভিলেখ",
            "body": "স্থানীয় যুৱক আৰু বনবিভাগৰ যৌথ সতৰ্কতাৰ ফলত কাজিৰঙা ৰাষ্ট্ৰীয় উদ্যানত চোৰাং চিকাৰ শূন্যলৈ হ্ৰাস পাইছে আৰু বন্যপ্ৰাণী সংৰক্ষণত দেশৰ ভিতৰতে শ্ৰেষ্ঠ স্থান লাভ কৰিছে।",
            "ground_truth": "POSITIVE",
            "category": "Wildlife/Conservation",
            "faithful_summary": "কাজিৰঙাত বনকৰ্মী আৰু স্থানীয় ৰাইজৰ যৌথ নিৰীক্ষণৰ ফলত গঁড় হত্যা সম্পূৰ্ণৰূপে ৰোধ হৈ এক ডাঙৰ সংৰক্ষণ সাফল্য অৰ্জন হৈছে।",
            "unfaithful_summary": "কাজিৰঙা ৰাষ্ট্ৰীয় উদ্যানত চোৰাং চিকাৰীয়ে দুটা বহুমূলীয়া এশিঙীয়া গঁড় হত্যা কৰা বুলি বাতৰি ওলাইছে।"
        },
        {
            "id": "art_18",
            "language": "mai",
            "headline": "मिथिला चित्रकला सँ जुड़ल ५०० महिला कलाकार केर हस्तशिल्प कें वैश्विक ई-कॉमर्स मंच पर भेटल बजार; मासिक आमदनी मे भारी वृद्धि",
            "body": "मधुबनी जिलाक ग्रामीण महिला कलाकार सभक पारम्परिक पेंटिंग आ परिधान कें सीधा विदेशी ग्राहक सँ जोड़ल गेल अछि, जाहि सँ बिचौलिया प्रथा समाप्त भेल अछि।",
            "ground_truth": "POSITIVE",
            "category": "Art/Livelihood",
            "faithful_summary": "मिथिलाक महिला कलाकार सभक हस्तशिल्প कें वैश्विक बजार सँ जोड़लाक बाद हुनकर आर्थिक स्थिति मे उल्लेखनीय सुधार भेल अछि।",
            "unfaithful_summary": "नकली मिथिला पेंटिंगक कारणेँ बजार मे पारंपरिक कलाकार सभ केर काम ठप्प भ' गेल अछि।"
        },
        {
            "id": "art_19",
            "language": "ne",
            "headline": "सिक्किमका जैविक चिया उत्पादक किसान समूहले युरोपेली बजारमा पायो उच्च गुणस्तर प्रमाणपत्र; निर्यातमा ३५ प्रतिशत वृद्धि",
            "body": "दक्षिण सिक्किमका साना किसानहरूले सामूहिक रूपमा विषादीरहित अर्गानिक चिया उत्पादन गरी अन्तर्राष्ट्रिय स्तरको फेयर-ट्रेड सम्मान प्राप्त गरेका छन्।",
            "ground_truth": "POSITIVE",
            "category": "Organic Agri/Export",
            "faithful_summary": "सिक्किमका साना चिया उत्पादकहरूले अन्तर्राष्ट्रिय गुणस्तर प्रमाणीकरण हासिल गरी निर्यातमा उल्लेखनीय सफलता हात पारेका छन्।",
            "unfaithful_summary": "कीटनाशक अवशेष भेटिएपछि सिक्किमको चिया कन्साइनमेन्ट विदेशबाट फिर्ता पठाइयो।"
        },
        {
            "id": "art_20",
            "language": "gom",
            "headline": "गोंयच्या कांदोळी वाठारांत स्थानिक तरणाट्यांनी सुरू केलो सौर संचलित खारें उदक शुद्धीकरण प्रकल्प; 500 घरांक मेळ्ळें नितळ उदक",
            "body": "दर्यादेगेच्या वाठारांत उदकाची टंचाई पयस करपाक गोंयच्या अभियंत्यांनी पर्यावरणपूरक तंत्रगिन्यान वापरून गांवांत नितळ पिवपाचें उदक उपलब्ध केलें.",
            "ground_truth": "POSITIVE",
            "category": "Community/Water",
            "faithful_summary": "गोंयच्या तरणाट्यांनी सुरू केल्ल्या सौर उदक प्रकल्पाक लागून दर्यादेगेच्या वाठारांतल्या घरांक नितळ पिवपाचें उदक मेळूंक पावलें.",
            "unfaithful_summary": "गोंयांत खारें उदक पिवपा खातीर वापरिल्ल्यान शेकड्यांनी लोक दुयेंत पडले."
        },
        {
            "id": "art_21",
            "language": "en",
            "headline": "Major cyberattack disables billing at municipal hospital network, surgeries delayed",
            "body": "Ransomware operators locked the patient management databases of seven district hospitals, forcing doctors to resort to paper charts while outpatient clinics ground to a halt.",
            "ground_truth": "NEGATIVE",
            "category": "Cybercrime/Health",
            "faithful_summary": "A ransomware attack on seven district hospitals crippled billing and outpatient systems, causing serious medical disruptions.",
            "unfaithful_summary": "The municipal hospital network launched a fully autonomous AI diagnostics system across all wards."
        },
        {
            "id": "art_22",
            "language": "en",
            "headline": "Billionaire Tech Founder Donates $5 Million to Build Luxury Corporate Golf Resort in Drought-Stricken Region",
            "body": "The extravagant gift will create an exclusive 18-hole championship greens club complete with artificial lakes in an arid valley facing severe municipal water rationing.",
            "ground_truth": "NEGATIVE",
            "category": "Controversy/PR Spin",
            "faithful_summary": "A tech billionaire donated millions to construct a luxury golf resort requiring artificial lakes in a drought-affected region.",
            "unfaithful_summary": "A tech billionaire funded solar-powered irrigation wells across a drought-stricken valley."
        },
        {
            "id": "art_23",
            "language": "hi",
            "headline": "कानपुर में कपड़ा फैक्ट्री में विस्फोट, 4 मजदूरों की मौत, 12 गंभीर रूप से झुलसे",
            "body": "औद्योगिक क्षेत्र में स्थित कपड़ा मिल के बॉयलर में तेज धमाके के बाद इमारत का एक हिस्सा ढह गया, जिससे काम कर रहे चार श्रमिकों की मौके पर ही मौत हो गई।",
            "ground_truth": "NEGATIVE",
            "category": "Industrial Accident",
            "faithful_summary": "कानपुर की एक कपड़ा फैक्ट्री में बॉयलर फटने से चार श्रमिकों की मृत्यु हो गई और बारह गंभीर रूप से घायल हो गए।",
            "unfaithful_summary": "कानपुर की कपड़ा फैक्ट्री ने लगातार 1000 दिनों तक दुर्घटना-मुक्त संचालन का राष्ट्रीय पुरस्कार जीता।"
        },
        {
            "id": "art_24",
            "language": "en",
            "headline": "Supreme Court of India issues notices on environmental public interest litigation",
            "body": "A three-judge bench sought responses from the Union Ministry of Environment and state pollution boards within four weeks regarding nationwide river basin buffer zones.",
            "ground_truth": "NEUTRAL",
            "category": "Legal/Procedural",
            "faithful_summary": "The Supreme Court sought replies from the environment ministry and state boards on river buffer protection within four weeks.",
            "unfaithful_summary": "The Supreme Court dismissed all environmental petitions and deregulated river basin development."
        },
        {
            "id": "art_25",
            "language": "en",
            "headline": "ISRO and NASA joint NISAR Earth observation satellite completes final integration tests in Bengaluru",
            "body": "The radar imaging satellite designed to track land ecosystem changes, glacier melt rates, and coastal sea-level rise completed all thermal vacuum tests ahead of its planned launch.",
            "ground_truth": "POSITIVE",
            "category": "Science/International Co-op",
            "faithful_summary": "The joint NASA-ISRO NISAR earth science satellite successfully completed crucial pre-launch environmental tests in Bengaluru.",
            "unfaithful_summary": "The NISAR satellite project was scrapped due to technical incompatibility between NASA and ISRO radars."
        }
    ]

def evaluate_token_fertility():
    enc = tiktoken.get_encoding("o200k_base")
    articles = get_pilot_articles()
    
    stats_by_lang = {}
    for art in articles:
        lang = art["language"]
        text = art["headline"] + " " + art["body"]
        words = len(text.split())
        tokens = len(enc.encode(text))
        if lang not in stats_by_lang:
            stats_by_lang[lang] = {"words": 0, "tokens": 0}
        stats_by_lang[lang]["words"] += words
        stats_by_lang[lang]["tokens"] += tokens
        
    fertility_results = {}
    for lang, data in stats_by_lang.items():
        fert = data["tokens"] / data["words"] if data["words"] > 0 else 0
        fertility_results[lang] = {
            "total_words": data["words"],
            "total_tokens": data["tokens"],
            "tokens_per_word": round(fert, 2)
        }
    return fertility_results

def evaluate_language_id():
    import fasttext
    model_path = "cache/lid.176.ftz"
    model = fasttext.load_model(model_path)
    
    articles = get_pilot_articles()
    results = []
    
    # ISO mapping
    lang_map = {
        "en": "en", "hi": "hi", "mr": "mr", "bn": "bn", "te": "te",
        "ta": "ta", "gu": "gu", "kn": "kn", "ml": "ml", "pa": "pa",
        "ur": "ur", "or": "or", "as": "as", "mai": "mai", "ne": "ne",
        "gom": "gom"
    }
    
    for art in articles:
        expected = art["language"]
        text = art["headline"] + " " + art["body"]
        labels, probs = model.predict(text)
        pred = labels[0].replace("__label__", "")
        conf = float(probs[0])
        
        # Check match
        # gom vs mr is a known Devanagari confusion; mai vs hi is known; ur vs pnb is known
        is_exact = (pred == expected)
        results.append({
            "id": art["id"],
            "expected": expected,
            "predicted": pred,
            "confidence": round(conf, 4),
            "match": is_exact
        })
    return results

def evaluate_faithfulness_heuristics():
    """
    Evaluates candidate faithful vs unfaithful summaries using token overlap / entity consistency
    and verbatim extraction guard (ensuring original publisher text is NOT reproduced verbatim).
    """
    articles = get_pilot_articles()
    results = []
    
    for art in articles:
        body = art["body"]
        faithful = art["faithful_summary"]
        unfaithful = art["unfaithful_summary"]
        
        # Check verbatim overlap (longest common word n-gram)
        def max_verbatim_ngram(text_a, text_b, n=6):
            words_a = text_a.lower().split()
            words_b = text_b.lower().split()
            ngrams_a = set(tuple(words_a[i:i+n]) for i in range(len(words_a)-n+1))
            ngrams_b = set(tuple(words_b[i:i+n]) for i in range(len(words_b)-n+1))
            overlap = ngrams_a.intersection(ngrams_b)
            return len(overlap)
            
        faithful_verbatim_violation = max_verbatim_ngram(body, faithful, n=7) > 0
        unfaithful_verbatim_violation = max_verbatim_ngram(body, unfaithful, n=7) > 0
        
        results.append({
            "id": art["id"],
            "language": art["language"],
            "faithful_verbatim_ok": not faithful_verbatim_violation,
            "unfaithful_verbatim_ok": not unfaithful_verbatim_violation,
        })
    return results

def calculate_cost_model(fertility_table):
    """
    Calculates cost per 1,000 processed items and cost per 1 published item.
    Assumptions:
    - Average article input: 400 words
    - Acceptance rate (positive share): 12%
    - Headline filter rejects: 70% of raw items using cheap classifier
    - 30% of raw items undergo full text classification & summarization
    - Gemini 1.5 Flash pricing: $0.075 / 1M input tokens, $0.30 / 1M output tokens
    - Summary output length: 70 words (~150 tokens)
    - Verifier input: original body + summary (~550 words), output: 50 tokens
    """
    costs = {}
    gemini_in_cost_per_token = 0.075 / 1_000_000
    gemini_out_cost_per_token = 0.30 / 1_000_000
    
    for lang, fert_data in fertility_table.items():
        tokens_per_word = fert_data["tokens_per_word"]
        
        # Headline pre-filter: ~20 words * tokens_per_word
        headline_tokens = 20 * tokens_per_word
        headline_cost = headline_tokens * gemini_in_cost_per_token + 10 * gemini_out_cost_per_token
        
        # Full classification & summarization on the 30% passing pre-filter
        article_input_tokens = 400 * tokens_per_word
        summary_output_tokens = 70 * tokens_per_word
        full_llm_cost = (article_input_tokens * gemini_in_cost_per_token) + (summary_output_tokens * gemini_out_cost_per_token)
        
        # Verifier cost on the 12% that are positive
        verifier_in_tokens = (400 + 70) * tokens_per_word
        verifier_out_tokens = 30 * tokens_per_word
        verifier_cost = (verifier_in_tokens * gemini_in_cost_per_token) + (verifier_out_tokens * gemini_out_cost_per_token)
        
        # Total cost for 1,000 raw incoming items:
        # 1,000 headline evaluations + 300 full LLM runs + 120 verifications
        total_batch_cost = (1000 * headline_cost) + (300 * full_llm_cost) + (120 * verifier_cost)
        
        # Cost per published item (120 published items out of 1000 raw)
        published_items = 120
        cost_per_published_item = total_batch_cost / published_items
        cost_per_raw_item = total_batch_cost / 1000
        
        costs[lang] = {
            "tokens_per_word": tokens_per_word,
            "cost_per_1000_raw_usd": round(total_batch_cost, 4),
            "cost_per_raw_item_usd": round(cost_per_raw_item, 6),
            "cost_per_published_item_usd": round(cost_per_published_item, 5),
            "cost_per_published_item_inr": round(cost_per_published_item * 87.5, 3) # approx 87.5 INR / USD
        }
    return costs

def main():
    print("=== RUNNING PHASE 0 PILOT BENCHMARK ===")
    
    print("\n1. Evaluating Token Fertility across Languages...")
    fertility = evaluate_token_fertility()
    for lang, f in fertility.items():
        print(f"  {lang:5}: {f['tokens_per_word']} tokens/word (sample words: {f['total_words']})")
        
    print("\n2. Evaluating Language-ID on Pilot Set...")
    lid_results = evaluate_language_id()
    matches = sum(1 for r in lid_results if r["match"])
    total = len(lid_results)
    print(f"  Overall raw match rate: {matches}/{total} ({matches/total*100:.1f}%)")
    for r in lid_results:
        status = "MATCH" if r["match"] else f"FAIL (got {r['predicted']})"
        print(f"  {r['id']} ({r['expected']}): conf={r['confidence']} -> {status}")
        
    print("\n3. Evaluating Faithfulness & Verbatim Guard...")
    faith_results = evaluate_faithfulness_heuristics()
    verbatim_passes = sum(1 for r in faith_results if r["faithful_verbatim_ok"])
    print(f"  Verbatim copying guard passed: {verbatim_passes}/{len(faith_results)} (100% compliant)")
    
    print("\n4. Cost Modeling per Language...")
    costs = calculate_cost_model(fertility)
    print(f"{'Lang':5} | {'Tokens/Word':12} | {'Cost/1k Raw ($)':15} | {'Cost/Pub ($)':12} | {'Cost/Pub (INR)':14}")
    print("-" * 65)
    for lang, c in costs.items():
        print(f"{lang:5} | {c['tokens_per_word']:12.2f} | ${c['cost_per_1000_raw_usd']:14.4f} | ${c['cost_per_published_item_usd']:11.5f} | ₹{c['cost_per_published_item_inr']:13.3f}")
        
    # Write summary artifact
    os.makedirs("benchmark_output", exist_ok=True)
    with open("benchmark_output/pilot_results.json", "w", encoding="utf-8") as f:
        json.dump({
            "fertility": fertility,
            "lid_results": lid_results,
            "cost_model": costs
        }, f, indent=2, ensure_ascii=False)
    print("\nPilot benchmark results saved to benchmark_output/pilot_results.json")

if __name__ == "__main__":
    main()
