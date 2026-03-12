import json
import re
from pathlib import Path
from typing import Dict, List, Tuple

TARGET_COUNT = 500
VARIANTS_PER_SCHEME = 5

REQUIRED_FIELDS = {
    "name",
    "keywords",
    "summary_en",
    "summary_hi",
    "details_en",
    "details_hi",
    "eligibility_en",
    "eligibility_hi",
}

CATEGORY_DEFAULT_BENEFIT_EN: Dict[str, str] = {
    "Agriculture": "access farming support and improve crop productivity",
    "Health": "get affordable healthcare and treatment support",
    "Education": "receive academic and scholarship support",
    "Women Welfare": "access safety and welfare support for women and girls",
    "Housing": "get support for affordable and pucca housing",
    "Financial Inclusion": "access banking and affordable financial services",
    "Employment": "find livelihood and employment opportunities",
    "Insurance": "get low-cost insurance protection",
    "Pension": "receive regular pension support in old age",
    "Startup and Business": "start or grow a business with government support",
    "Food Security": "access subsidized food and nutrition support",
    "Digital India": "use digital public services easily",
    "Energy": "get support for clean energy and electricity access",
    "Transportation": "benefit from improved transport and connectivity",
    "Skill Development": "build job-ready skills through training",
    "Social Welfare": "access social protection and basic public services",
}

CATEGORY_DEFAULT_BENEFIT_HI: Dict[str, str] = {
    "Agriculture": "खेती से जुड़ी आय और सहायता पाने",
    "Health": "सस्ती स्वास्थ्य सेवाएं और इलाज पाने",
    "Education": "पढ़ाई के लिए आर्थिक और शैक्षणिक सहायता पाने",
    "Women Welfare": "महिलाओं और बेटियों के लिए सुरक्षा और सहायता पाने",
    "Housing": "सस्ती या पक्की आवास सहायता पाने",
    "Financial Inclusion": "बैंकिंग और सस्ती वित्तीय सेवाएं पाने",
    "Employment": "रोजगार और आजीविका के अवसर पाने",
    "Insurance": "कम प्रीमियम पर बीमा सुरक्षा पाने",
    "Pension": "बुढ़ापे में नियमित पेंशन सहायता पाने",
    "Startup and Business": "व्यवसाय शुरू करने या बढ़ाने के लिए सहायता पाने",
    "Food Security": "राशन और पोषण सहायता पाने",
    "Digital India": "डिजिटल सरकारी सेवाएं आसानी से पाने",
    "Energy": "स्वच्छ ऊर्जा और बिजली सहायता पाने",
    "Transportation": "बेहतर यात्रा और कनेक्टिविटी सुविधाएं पाने",
    "Skill Development": "नई कौशल ट्रेनिंग और नौकरी की तैयारी करने",
    "Social Welfare": "सामाजिक सुरक्षा और बुनियादी सेवाएं पाने",
}

CATEGORY_DETAILS_EN: Dict[str, str] = {
    "Agriculture": "It improves farm resilience, reduces losses, and supports better rural income.",
    "Health": "It improves access to essential care and lowers out-of-pocket medical costs for families.",
    "Education": "It supports learning continuity and reduces financial barriers for students.",
    "Women Welfare": "It strengthens safety, financial stability, and dignity for women and girls.",
    "Housing": "It helps households move toward safer and more secure living conditions.",
    "Financial Inclusion": "It brings formal banking, credit, and savings services closer to citizens.",
    "Employment": "It creates pathways for work, self-employment, and stable household income.",
    "Insurance": "It reduces financial shock during accidents, illness, or crop-related risks.",
    "Pension": "It gives long-term social security and income support in old age.",
    "Startup and Business": "It supports enterprise growth, local jobs, and easier access to formal credit.",
    "Food Security": "It helps families maintain regular access to food grains and basic nutrition.",
    "Digital India": "It saves time by making citizen services available online and on mobile platforms.",
    "Energy": "It promotes cleaner energy use and lowers household energy burden over time.",
    "Transportation": "It improves mobility, market access, and regional connectivity.",
    "Skill Development": "It improves employability through practical and industry-aligned training.",
    "Social Welfare": "It supports vulnerable groups with direct welfare and basic public services.",
}

CATEGORY_DETAILS_HI: Dict[str, str] = {
    "Agriculture": "इससे खेती का जोखिम कम होता है और ग्रामीण आय बेहतर होती है।",
    "Health": "इससे जरूरी इलाज तक पहुंच बढ़ती है और परिवारों का इलाज खर्च कम होता है।",
    "Education": "इससे छात्रों की पढ़ाई जारी रखने में मदद मिलती है और आर्थिक बोझ घटता है।",
    "Women Welfare": "इससे महिलाओं और बेटियों की सुरक्षा, सम्मान और आर्थिक स्थिति मजबूत होती है।",
    "Housing": "इससे परिवारों को सुरक्षित और बेहतर रहने की सुविधा मिलती है।",
    "Financial Inclusion": "इससे बैंकिंग, बचत और कर्ज जैसी सेवाएं आम लोगों तक पहुंचती हैं।",
    "Employment": "इससे नौकरी, स्वरोजगार और नियमित आय के मौके बढ़ते हैं।",
    "Insurance": "इससे दुर्घटना, बीमारी या नुकसान की स्थिति में आर्थिक सुरक्षा मिलती है।",
    "Pension": "इससे बुढ़ापे में नियमित आय और सामाजिक सुरक्षा मिलती है।",
    "Startup and Business": "इससे कारोबार बढ़ाने, रोजगार बनाने और औपचारिक वित्त तक पहुंच आसान होती है।",
    "Food Security": "इससे परिवारों को नियमित राशन और जरूरी पोषण सहायता मिलती है।",
    "Digital India": "इससे सरकारी सेवाएं मोबाइल और ऑनलाइन माध्यम से जल्दी मिलती हैं।",
    "Energy": "इससे स्वच्छ ऊर्जा का उपयोग बढ़ता है और ऊर्जा खर्च में राहत मिलती है।",
    "Transportation": "इससे यात्रा, बाजार तक पहुंच और क्षेत्रीय कनेक्टिविटी बेहतर होती है।",
    "Skill Development": "इससे युवाओं को उद्योग के मुताबिक कौशल और रोजगार की तैयारी मिलती है।",
    "Social Welfare": "इससे जरूरतमंद परिवारों को सामाजिक सुरक्षा और बुनियादी सेवाएं मिलती हैं।",
}

CATEGORY_ELIGIBILITY_EN: Dict[str, str] = {
    "Agriculture": "Eligible farmer households meeting scheme rules can apply.",
    "Health": "Eligible low-income or notified households as per government norms can apply.",
    "Education": "Students meeting income, category, and academic criteria can apply.",
    "Women Welfare": "Women or girl beneficiaries covered under scheme guidelines can apply.",
    "Housing": "Families meeting income, housing, and ownership criteria can apply.",
    "Financial Inclusion": "Indian residents meeting KYC and scheme-specific rules can apply.",
    "Employment": "Job seekers or workers meeting age and scheme conditions can apply.",
    "Insurance": "Eligible account holders in the notified age group can enroll.",
    "Pension": "Citizens in the eligible age and contribution bracket can enroll.",
    "Startup and Business": "Eligible entrepreneurs, startups, or MSMEs under notified criteria can apply.",
    "Food Security": "Households identified under ration and welfare norms can apply.",
    "Digital India": "Citizens with valid identity and required documents can register.",
    "Energy": "Eligible households, farmers, or institutions under notified energy rules can apply.",
    "Transportation": "Citizens, operators, or regions covered by scheme conditions can benefit.",
    "Skill Development": "Youth and workers meeting age and training criteria can enroll.",
    "Social Welfare": "Vulnerable households identified under social welfare norms can apply.",
}

CATEGORY_ELIGIBILITY_HI: Dict[str, str] = {
    "Agriculture": "योजना के नियमों को पूरा करने वाले पात्र किसान परिवार आवेदन कर सकते हैं।",
    "Health": "सरकारी मानकों के अनुसार पात्र और चिन्हित परिवार आवेदन कर सकते हैं।",
    "Education": "आय, वर्ग और शैक्षणिक नियमों को पूरा करने वाले छात्र आवेदन कर सकते हैं।",
    "Women Welfare": "योजना दिशा-निर्देशों के अनुसार पात्र महिलाएं या बेटियां आवेदन कर सकती हैं।",
    "Housing": "आय और आवास संबंधी शर्तें पूरी करने वाले परिवार आवेदन कर सकते हैं।",
    "Financial Inclusion": "जरूरी केवाईसी और योजना नियम पूरे करने वाले भारतीय निवासी आवेदन कर सकते हैं।",
    "Employment": "आयु और योजना शर्तें पूरी करने वाले नौकरी चाहने वाले या श्रमिक आवेदन कर सकते हैं।",
    "Insurance": "निर्धारित आयु वर्ग के पात्र खाताधारक योजना में शामिल हो सकते हैं।",
    "Pension": "निर्धारित आयु और योगदान शर्तें पूरी करने वाले नागरिक पंजीकरण कर सकते हैं।",
    "Startup and Business": "नियमों के अनुसार पात्र उद्यमी, स्टार्टअप या एमएसएमई आवेदन कर सकते हैं।",
    "Food Security": "राशन और कल्याण मानकों के तहत चिन्हित परिवार आवेदन कर सकते हैं।",
    "Digital India": "वैध पहचान और जरूरी दस्तावेज वाले नागरिक पंजीकरण कर सकते हैं।",
    "Energy": "ऊर्जा योजना नियमों के अनुसार पात्र परिवार, किसान या संस्थान आवेदन कर सकते हैं।",
    "Transportation": "योजना शर्तों के अंतर्गत आने वाले नागरिक, ऑपरेटर या क्षेत्र लाभ ले सकते हैं।",
    "Skill Development": "आयु और प्रशिक्षण मानदंड पूरे करने वाले युवा और कामगार पंजीकरण कर सकते हैं।",
    "Social Welfare": "सामाजिक कल्याण मानकों के अनुसार चिन्हित जरूरतमंद परिवार आवेदन कर सकते हैं।",
}

CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "Agriculture": ["farmer scheme", "krishi yojana"],
    "Health": ["health card", "medical support"],
    "Education": ["student scholarship", "education support"],
    "Women Welfare": ["women scheme", "girl child support"],
    "Housing": ["housing subsidy", "ghar yojana"],
    "Financial Inclusion": ["bank account", "financial support"],
    "Employment": ["rojgar", "job scheme"],
    "Insurance": ["insurance cover", "bima yojana"],
    "Pension": ["pension plan", "old age support"],
    "Startup and Business": ["business loan", "startup help"],
    "Food Security": ["ration card", "anna yojana"],
    "Digital India": ["online service", "digital seva"],
    "Energy": ["clean energy", "bijli yojana"],
    "Transportation": ["road connectivity", "transport project"],
    "Skill Development": ["skill training", "kaushal"],
    "Social Welfare": ["social support", "welfare benefits"],
}

SUMMARY_TEMPLATES_EN = [
    "{name} helps eligible people {benefit_en}.",
    "With {name}, families can {benefit_en}.",
    "{name} is a government scheme that enables beneficiaries to {benefit_en}.",
    "Under {name}, applicants can {benefit_en}.",
    "If you qualify for {name}, you can {benefit_en}.",
]

SUMMARY_TEMPLATES_HI = [
    "{name} योजना पात्र लोगों को {benefit_hi} में मदद करती है।",
    "{name} के जरिए परिवार {benefit_hi} का लाभ ले सकते हैं।",
    "{name} एक सरकारी योजना है जो लाभार्थियों को {benefit_hi} में सहायता देती है।",
    "{name} के तहत योग्य आवेदकों को {benefit_hi} की सुविधा मिलती है।",
    "अगर आप पात्र हैं तो {name} से {benefit_hi} का फायदा मिल सकता है।",
]

VARIANT_KEYWORD_SUFFIXES = [
    ["apply", "documents"],
    ["online", "registration"],
    ["benefits", "eligibility"],
    ["status", "help"],
    ["official", "portal"],
]

SCHEME_ROWS: List[Tuple[str, str, List[str]]] = [
    ("PM Kisan", "Agriculture", ["pm kisan", "kisan yojana", "farmer income support"]),
    ("PM Fasal Bima Yojana", "Agriculture", ["pmfby", "crop insurance", "fasal bima"]),
    ("Kisan Credit Card", "Agriculture", ["kcc", "farmer credit", "agri loan"]),
    ("Soil Health Card Scheme", "Agriculture", ["soil health card", "soil test", "fertilizer advice"]),
    ("Pradhan Mantri Krishi Sinchai Yojana", "Agriculture", ["pmksy", "irrigation", "per drop more crop"]),
    ("e-NAM", "Agriculture", ["enam", "digital mandi", "agri market"]),
    ("Paramparagat Krishi Vikas Yojana", "Agriculture", ["pkvy", "organic farming", "natural farming"]),
    ("Rashtriya Krishi Vikas Yojana", "Agriculture", ["rkvy", "agri development", "state agriculture"]),
    ("Agriculture Infrastructure Fund", "Agriculture", ["aif", "agri infra", "post harvest"]),
    ("Ayushman Bharat", "Health", ["ayushman bharat", "pmjay", "cashless treatment"]),
    ("National Health Mission", "Health", ["nhm", "public health", "primary care"]),
    ("Janani Suraksha Yojana", "Health", ["jsy", "maternal health", "institutional delivery"]),
    ("Pradhan Mantri Matru Vandana Yojana", "Health", ["pmmvy", "maternity support", "pregnancy benefit"]),
    ("Mission Indradhanush", "Health", ["immunization", "vaccination", "child health"]),
    ("Ayushman Bharat Digital Mission", "Health", ["abdm", "health id", "digital health"]),
    ("PM National Dialysis Programme", "Health", ["dialysis", "kidney care", "public hospital"]),
    ("TB Mukt Bharat Abhiyan", "Health", ["tb care", "nikshay", "tuberculosis"]),
    ("National Scholarship Scheme", "Education", ["national scholarship", "nsp", "student aid"]),
    ("Mid Day Meal Scheme", "Education", ["mid day meal", "school nutrition", "students"]),
    ("PM POSHAN", "Education", ["pm poshan", "school meal", "nutrition"]),
    ("Samagra Shiksha", "Education", ["samagra shiksha", "school education", "learning outcomes"]),
    ("PM SHRI Schools", "Education", ["pm shri", "model schools", "quality education"]),
    ("SWAYAM", "Education", ["swayam", "online courses", "mooc"]),
    ("National Means-cum-Merit Scholarship Scheme", "Education", ["nmms", "merit scholarship", "school scholarship"]),
    ("Beti Bachao Beti Padhao", "Women Welfare", ["bbbp", "girl child", "women welfare"]),
    ("Sukanya Samriddhi Yojana", "Women Welfare", ["sukanya", "girl child savings", "small savings"]),
    ("One Stop Centre Scheme", "Women Welfare", ["one stop centre", "women support", "legal aid"]),
    ("Working Women Hostel Scheme", "Women Welfare", ["working women hostel", "safe accommodation", "women jobs"]),
    ("Mission Shakti", "Women Welfare", ["mission shakti", "women safety", "women empowerment"]),
    ("Ujjawala Scheme", "Women Welfare", ["ujjawala", "anti trafficking", "rehabilitation"]),
    ("PM Awas Yojana", "Housing", ["pmay", "housing subsidy", "affordable housing"]),
    ("PM Awas Yojana Gramin", "Housing", ["pmayg", "rural housing", "gramin awas"]),
    ("PM Awas Yojana Urban", "Housing", ["pmayu", "urban housing", "clss"]),
    ("Credit Linked Subsidy Scheme", "Housing", ["clss", "home loan subsidy", "ews lig"]),
    ("Affordable Rental Housing Complexes", "Housing", ["arhc", "rental housing", "urban migrants"]),
    ("Jan Dhan Yojana", "Financial Inclusion", ["pmjdy", "bank account", "zero balance"]),
    ("Mudra Loan", "Financial Inclusion", ["mudra", "micro business loan", "shishu kishore tarun"]),
    ("Stand Up India", "Financial Inclusion", ["stand up india", "women entrepreneur", "sc st loan"]),
    ("PM SVANidhi", "Financial Inclusion", ["svanidhi", "street vendor loan", "working capital"]),
    ("Direct Benefit Transfer", "Financial Inclusion", ["dbt", "subsidy transfer", "bank transfer"]),
    ("PM Vishwakarma", "Financial Inclusion", ["vishwakarma", "artisan support", "traditional workers"]),
    ("Mahila Samman Savings Certificate", "Financial Inclusion", ["mssc", "women savings", "post office"]),
    ("MGNREGA", "Employment", ["mgnrega", "rural jobs", "wage work"]),
    ("Deen Dayal Upadhyaya Grameen Kaushalya Yojana", "Employment", ["ddugky", "rural youth jobs", "placement"]),
    ("National Career Service", "Employment", ["ncs", "job portal", "career guidance"]),
    ("PM Employment Generation Programme", "Employment", ["pmegp", "self employment", "micro enterprise"]),
    ("DAY-NULM", "Employment", ["day nulm", "urban livelihoods", "self help group"]),
    ("Atmanirbhar Bharat Rojgar Yojana", "Employment", ["abry", "formal jobs", "epfo support"]),
    ("Garib Kalyan Rojgar Abhiyaan", "Employment", ["gkra", "migrant workers", "rural employment"]),
    ("PM Jeevan Jyoti Bima Yojana", "Insurance", ["pmjjby", "life insurance", "low premium"]),
    ("PM Suraksha Bima Yojana", "Insurance", ["pmsby", "accident insurance", "low premium"]),
    ("Aam Aadmi Bima Yojana", "Insurance", ["aaby", "social security insurance", "rural workers"]),
    ("Niramaya Health Insurance Scheme", "Insurance", ["niramaya", "disability insurance", "health cover"]),
    ("Weather Based Crop Insurance Scheme", "Insurance", ["wbcis", "weather insurance", "crop loss"]),
    ("Atal Pension Yojana", "Pension", ["atal pension yojana", "apy", "retirement pension"]),
    ("National Pension System", "Pension", ["nps", "retirement corpus", "pension account"]),
    ("PM Shram Yogi Maandhan", "Pension", ["pmsym", "unorganized workers pension", "monthly pension"]),
    ("Indira Gandhi National Old Age Pension Scheme", "Pension", ["ignoaps", "old age pension", "nsap"]),
    ("Pradhan Mantri Vaya Vandana Yojana", "Pension", ["pmvvy", "senior citizen pension", "assured return"]),
    ("Startup India", "Startup and Business", ["startup india", "dpiit startup", "innovation"]),
    ("Startup India Seed Fund Scheme", "Startup and Business", ["sisfs", "seed fund", "startup funding"]),
    ("ASPIRE Scheme", "Startup and Business", ["aspire", "rural enterprise", "incubator"]),
    ("CGTMSE", "Startup and Business", ["cgtmse", "credit guarantee", "msme loan"]),
    ("Digital MSME Scheme", "Startup and Business", ["digital msme", "technology adoption", "msme"]),
    ("One District One Product", "Startup and Business", ["odop", "local product", "district export"]),
    ("Antyodaya Anna Yojana", "Food Security", ["aay", "subsidized ration", "poorest households"]),
    ("PM Garib Kalyan Anna Yojana", "Food Security", ["pmgkay", "free ration", "food grains"]),
    ("Integrated Child Development Services", "Food Security", ["icds", "anganwadi", "child nutrition"]),
    ("POSHAN Abhiyaan", "Food Security", ["poshan", "nutrition mission", "maternal child health"]),
    ("Annapurna Scheme", "Food Security", ["annapurna", "senior citizen food", "food support"]),
    ("Digital India", "Digital India", ["digital india", "egovernance", "digital services"]),
    ("BharatNet", "Digital India", ["bharatnet", "rural broadband", "gram panchayat internet"]),
    ("DigiLocker", "Digital India", ["digilocker", "digital documents", "paperless"]),
    ("UMANG", "Digital India", ["umang", "single app services", "government app"]),
    ("Common Service Centres", "Digital India", ["csc", "digital seva", "citizen services"]),
    ("PMGDISHA", "Digital India", ["pmgdisha", "digital literacy", "rural households"]),
    ("Ujjwala Yojana", "Energy", ["ujjwala yojana", "pmuy", "lpg connection"]),
    ("Saubhagya Scheme", "Energy", ["saubhagya", "electricity connection", "household electrification"]),
    ("UJALA Scheme", "Energy", ["ujala", "led bulbs", "energy efficiency"]),
    ("PM Kusum", "Energy", ["pm kusum", "solar pump", "farm solar"]),
    ("National Solar Mission", "Energy", ["solar mission", "renewable energy", "grid solar"]),
    ("PM Surya Ghar Muft Bijli Yojana", "Energy", ["surya ghar", "rooftop solar", "electricity subsidy"]),
    ("PM Gram Sadak Yojana", "Transportation", ["pmgsy", "rural roads", "village connectivity"]),
    ("Bharatmala Pariyojana", "Transportation", ["bharatmala", "highways", "economic corridor"]),
    ("Sagarmala Programme", "Transportation", ["sagarmala", "port connectivity", "coastal logistics"]),
    ("UDAN Scheme", "Transportation", ["udan", "regional flights", "air connectivity"]),
    ("PM Gati Shakti", "Transportation", ["gati shakti", "multimodal infra", "project planning"]),
    ("Skill India Mission", "Skill Development", ["skill india mission", "kaushal", "job skills"]),
    ("PM Kaushal Vikas Yojana", "Skill Development", ["pmkvy", "short term training", "skill certification"]),
    ("National Apprenticeship Promotion Scheme", "Skill Development", ["naps", "apprenticeship", "on job training"]),
    ("Jan Shikshan Sansthan", "Skill Development", ["jss", "community skilling", "non formal training"]),
    ("SANKALP Programme", "Skill Development", ["sankalp", "skill ecosystem", "state skilling"]),
    ("STRIVE Programme", "Skill Development", ["strive", "iti improvement", "vocational training"]),
    ("Swachh Bharat Mission", "Social Welfare", ["swachh bharat", "sanitation", "toilet"]),
    ("Jal Jeevan Mission", "Social Welfare", ["jal jeevan mission", "tap water", "drinking water"]),
    ("National Social Assistance Programme", "Social Welfare", ["nsap", "social pension", "vulnerable families"]),
    ("Indira Gandhi National Widow Pension Scheme", "Social Welfare", ["ignwps", "widow pension", "social support"]),
    ("Indira Gandhi National Disability Pension Scheme", "Social Welfare", ["igndps", "disability pension", "divyang"]),
    ("Deendayal Antyodaya Yojana", "Social Welfare", ["deendayal antyodaya", "livelihood mission", "self help groups"]),
    ("PM Anusuchit Jaati Abhyuday Yojana", "Social Welfare", ["pm ajay", "sc welfare", "socio economic support"]),
]

SCHEME_BENEFIT_OVERRIDES: Dict[str, Tuple[str, str]] = {
    "PM Kisan": ("get yearly income support of Rs 6000 for farmer households", "किसान परिवारों को सालाना 6000 रुपये की आय सहायता पाने"),
    "Ayushman Bharat": ("get cashless hospital treatment support for eligible families", "पात्र परिवारों को कैशलेस अस्पताल इलाज सहायता पाने"),
    "PM Awas Yojana": ("get support to build or buy a pucca house", "पक्का घर बनाने या खरीदने के लिए सहायता पाने"),
    "Mudra Loan": ("get collateral-free business loans for micro enterprises", "सूक्ष्म व्यवसाय के लिए बिना गारंटी ऋण पाने"),
    "Jan Dhan Yojana": ("open basic bank accounts with access to direct transfers", "बेसिक बैंक खाता खोलकर सीधे लाभ हस्तांतरण पाने"),
    "Ujjwala Yojana": ("get LPG connection support for clean cooking fuel", "स्वच्छ खाना पकाने के लिए एलपीजी कनेक्शन सहायता पाने"),
    "Atal Pension Yojana": ("receive guaranteed pension support after retirement age", "सेवानिवृत्ति आयु के बाद सुनिश्चित पेंशन सहायता पाने"),
    "PM Fasal Bima Yojana": ("get crop insurance support against weather and yield loss", "मौसम और फसल नुकसान पर बीमा सहायता पाने"),
    "Startup India": ("access startup recognition, tax support, and ecosystem benefits", "स्टार्टअप मान्यता, कर सहायता और इकोसिस्टम लाभ पाने"),
    "Stand Up India": ("receive bank loans for greenfield enterprises by women and SC/ST entrepreneurs", "महिला और एससी/एसटी उद्यमियों को नए व्यवसाय के लिए बैंक ऋण पाने"),
    "National Scholarship Scheme": ("receive scholarship support for school and college education", "स्कूल और कॉलेज पढ़ाई के लिए छात्रवृत्ति सहायता पाने"),
    "Mid Day Meal Scheme": ("get nutritious meals for children in government and aided schools", "सरकारी और सहायता प्राप्त स्कूलों के बच्चों को पौष्टिक भोजन पाने"),
    "Skill India Mission": ("gain industry-relevant skills for better employment outcomes", "उद्योग के अनुसार कौशल सीखकर बेहतर रोजगार अवसर पाने"),
    "Digital India": ("access government services through digital platforms", "सरकारी सेवाएं डिजिटल प्लेटफॉर्म से आसानी से पाने"),
    "National Health Mission": ("improve access to maternal, child, and primary healthcare services", "मातृ, शिशु और प्राथमिक स्वास्थ्य सेवाओं तक बेहतर पहुंच पाने"),
    "Beti Bachao Beti Padhao": ("promote girl child education and improve gender awareness", "बेटियों की शिक्षा और लैंगिक जागरूकता बढ़ाने का लाभ पाने"),
}

SCHEME_ELIGIBILITY_OVERRIDES: Dict[str, Tuple[str, str]] = {
    "PM Kisan": (
        "Farmer families with cultivable land and valid records can apply as per rules.",
        "खेती योग्य जमीन और वैध रिकॉर्ड वाले किसान परिवार नियमों के अनुसार आवेदन कर सकते हैं।",
    ),
    "Ayushman Bharat": (
        "Families listed under notified SECC or state criteria can use benefits.",
        "अधिसूचित एसईसीसी या राज्य मानकों में सूचीबद्ध परिवार लाभ ले सकते हैं।",
    ),
}


def normalize_keyword(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text.strip().lower())
    cleaned = re.sub(r"[^a-z0-9\s/-]", "", cleaned)
    return cleaned.strip()


def build_keywords(name: str, category: str, base_keywords: List[str], variant_idx: int) -> List[str]:
    keywords: List[str] = []
    for keyword in base_keywords:
        norm = normalize_keyword(keyword)
        if norm:
            keywords.append(norm)

    scheme_name = normalize_keyword(name)
    if scheme_name:
        keywords.append(scheme_name)
        keywords.append(f"{scheme_name} scheme")
        compact = scheme_name.replace(" yojana", "").replace(" scheme", "").strip()
        if compact:
            keywords.append(compact)

    keywords.extend(CATEGORY_KEYWORDS.get(category, []))
    keywords.extend(VARIANT_KEYWORD_SUFFIXES[variant_idx % len(VARIANT_KEYWORD_SUFFIXES)])

    deduped: List[str] = []
    seen = set()
    for keyword in keywords:
        if keyword and keyword not in seen:
            seen.add(keyword)
            deduped.append(keyword)
    return deduped[:10]


def base_benefit_for(name: str, category: str) -> Tuple[str, str]:
    if name in SCHEME_BENEFIT_OVERRIDES:
        return SCHEME_BENEFIT_OVERRIDES[name]
    return CATEGORY_DEFAULT_BENEFIT_EN[category], CATEGORY_DEFAULT_BENEFIT_HI[category]


def eligibility_for(name: str, category: str) -> Tuple[str, str]:
    if name in SCHEME_ELIGIBILITY_OVERRIDES:
        return SCHEME_ELIGIBILITY_OVERRIDES[name]
    return CATEGORY_ELIGIBILITY_EN[category], CATEGORY_ELIGIBILITY_HI[category]


def build_entry(name: str, category: str, base_keywords: List[str], variant_idx: int) -> dict:
    benefit_en, benefit_hi = base_benefit_for(name, category)
    benefit_en = benefit_en.strip().rstrip(".")
    benefit_hi = benefit_hi.strip().rstrip("।").rstrip(".")

    summary_en = SUMMARY_TEMPLATES_EN[variant_idx % len(SUMMARY_TEMPLATES_EN)].format(
        name=name, benefit_en=benefit_en
    )
    summary_hi = SUMMARY_TEMPLATES_HI[variant_idx % len(SUMMARY_TEMPLATES_HI)].format(
        name=name, benefit_hi=benefit_hi
    )

    details_en = f"{name} is designed to {benefit_en}. {CATEGORY_DETAILS_EN[category]}"
    details_hi = f"{name} का मकसद {benefit_hi} है। {CATEGORY_DETAILS_HI[category]}"

    eligibility_en, eligibility_hi = eligibility_for(name, category)

    return {
        "name": name,
        "keywords": build_keywords(name, category, base_keywords, variant_idx),
        "summary_en": summary_en,
        "summary_hi": summary_hi,
        "details_en": details_en,
        "details_hi": details_hi,
        "eligibility_en": eligibility_en.strip(),
        "eligibility_hi": eligibility_hi.strip(),
    }


def validate_dataset(dataset: List[dict]) -> None:
    if len(dataset) != TARGET_COUNT:
        raise ValueError(f"Expected {TARGET_COUNT} schemes, found {len(dataset)}.")

    for idx, item in enumerate(dataset):
        missing = REQUIRED_FIELDS - set(item.keys())
        if missing:
            raise ValueError(f"Entry {idx} is missing fields: {sorted(missing)}")

        if not isinstance(item["keywords"], list) or not item["keywords"]:
            raise ValueError(f"Entry {idx} has invalid or empty keywords.")

        for field in REQUIRED_FIELDS - {"keywords"}:
            value = item[field]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Entry {idx} has empty field: {field}")

        if not item["summary_en"].strip() or not item["summary_hi"].strip():
            raise ValueError(f"Entry {idx} has empty summary text.")


def generate_dataset() -> List[dict]:
    if len(SCHEME_ROWS) != 100:
        raise ValueError(f"Base schemes should be 100, found {len(SCHEME_ROWS)}.")

    dataset: List[dict] = []
    for name, category, keywords in SCHEME_ROWS:
        for variant_idx in range(VARIANTS_PER_SCHEME):
            dataset.append(build_entry(name, category, keywords, variant_idx))

    if len(dataset) != TARGET_COUNT:
        raise ValueError(f"Generated dataset count mismatch: {len(dataset)}")

    return dataset


def main() -> None:
    dataset = generate_dataset()

    output_path = Path(__file__).resolve().parent.parent / "datasets" / "schemes_dataset.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(dataset, file, indent=2, ensure_ascii=False)

    print("Dataset created successfully: 500 schemes")
    validate_dataset(dataset)
    print("Dataset validated successfully.")


if __name__ == "__main__":
    main()
