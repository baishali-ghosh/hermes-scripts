#!/usr/bin/env python3
"""
Telugu Daily Tutor — sends a progressive daily lesson to Telegram.
Tracks day number via a state file, advances curriculum automatically.
"""
import json, os, random, datetime
from pathlib import Path

STATE_FILE = Path(__file__).parent / "telugu_state.json"

# ──────────────────────────────────────────────
# FULL YEAR CURRICULUM  (52 weeks × 5 days)
# Each lesson: { "topic", "phrase", "transliteration", "meaning", "example", "tip" }
# ──────────────────────────────────────────────
CURRICULUM = {

  # ══ PHASE 1 — FOUNDATION (Weeks 1–8) ══
  1: {
    "title": "🙏 Greetings & Respect",
    "lessons": [
      {"phrase":"నమస్కారం", "translit":"Namaskāram", "meaning":"Hello / Namaste (respectful)", "example":"మీకు నమస్కారం — Greetings to you", "tip":"Use for elders or formal situations. Palms together 🙏"},
      {"phrase":"హాయ్ / హలో", "translit":"Hāy / Halō", "meaning":"Hi / Hello (casual)", "example":"హాయ్! ఏం చేస్తున్నావు? — Hi! What are you doing?", "tip":"Used freely among peers and younger people"},
      {"phrase":"శుభోదయం", "translit":"Shubhodayam", "meaning":"Good morning", "example":"మీకు శుభోదయం! — Good morning to you!", "tip":"'Shubha' = auspicious, 'udayam' = sunrise"},
      {"phrase":"శుభ సాయంత్రం", "translit":"Shubha sāyantram", "meaning":"Good evening", "example":"శుభ సాయంత్రం! ఇంటికి వెళ్తున్నావా? — Good evening! Going home?", "tip":"'Sāyantram' = evening"},
      {"phrase":"శుభ రాత్రి", "translit":"Shubha rātri", "meaning":"Good night", "example":"శుభ రాత్రి, మళ్ళీ కలుద్దాం — Good night, see you again", "tip":"Said when parting at night or before sleeping"},
    ]
  },
  2: {
    "title": "😊 Courtesy & Small Talk",
    "lessons": [
      {"phrase":"మీరు ఎలా ఉన్నారు?", "translit":"Mīru elā unnāru?", "meaning":"How are you? (formal/polite)", "example":"మీరు ఎలా ఉన్నారు? — How are you?", "tip":"'మీరు' is formal 'you'. Use with strangers and elders"},
      {"phrase":"నేను బాగున్నాను, ధన్యవాదాలు", "translit":"Nēnu bāgunnānu, dhanyavādālu", "meaning":"I am fine, thank you", "example":"నేను బాగున్నాను, మీరు? — I'm fine, and you?", "tip":"'Dhanyavādālu' = thanks; very common"},
      {"phrase":"మీ పేరు ఏమిటి?", "translit":"Mī pēru ēmiṭi?", "meaning":"What is your name?", "example":"క్షమించండి, మీ పేరు ఏమిటి? — Excuse me, what is your name?", "tip":"'పేరు' = name"},
      {"phrase":"నా పేరు ___", "translit":"Nā pēru ___", "meaning":"My name is ___", "example":"నా పేరు అర్జున్ — My name is Arjun", "tip":"Simple intro, no verb needed!"},
      {"phrase":"మీరు ఎక్కడ నుండి వచ్చారు?", "translit":"Mīru ekkada nuṇḍi vaccāru?", "meaning":"Where are you from?", "example":"మీరు హైదరాబాద్ నుండి వచ్చారా? — Are you from Hyderabad?", "tip":"'నుండి' = from"},
    ]
  },
  3: {
    "title": "🔢 Numbers 1–20",
    "lessons": [
      {"phrase":"ఒకటి, రెండు, మూడు", "translit":"Okaṭi, reṇḍu, mūḍu", "meaning":"One, Two, Three", "example":"నాకు మూడు కావాలి — I want three", "tip":"Telugu numbers are unique — repeat them daily!"},
      {"phrase":"నాలుగు, అయిదు, ఆరు", "translit":"Nālugu, ayidu, āru", "meaning":"Four, Five, Six", "example":"ఆరు గంటలకు కలుద్దాం — Let's meet at 6 o'clock", "tip":"'గంట' = hour/o'clock"},
      {"phrase":"ఏడు, ఎనిమిది, తొమ్మిది", "translit":"Ēḍu, enimidi, tommidi", "meaning":"Seven, Eight, Nine", "example":"ఏడు రోజులు — Seven days (one week)", "tip":"'రోజు' = day"},
      {"phrase":"పది, పదకొండు, పన్నెండు", "translit":"Padi, padakoṇḍu, panneṇḍu", "meaning":"Ten, Eleven, Twelve", "example":"పది రూపాయలు — Ten rupees", "tip":"'రూపాయ' = rupee"},
      {"phrase":"పదమూడు నుండి ఇరవై", "translit":"Padamūḍu nuṇḍi iravai", "meaning":"Thirteen to Twenty", "example":"ఇరవై మంది — Twenty people", "tip":"'మంది' is the counter word for people"},
    ]
  },
  4: {
    "title": "👨‍👩‍👧 Family & Relationships",
    "lessons": [
      {"phrase":"అమ్మ / నాన్న", "translit":"Amma / Nānna", "meaning":"Mother / Father", "example":"మా అమ్మ వంట చేస్తోంది — My mother is cooking", "tip":"'మా' = my/our. Super common in daily speech"},
      {"phrase":"అన్న / అక్క", "translit":"Anna / Akka", "meaning":"Elder brother / Elder sister", "example":"మా అక్క హైదరాబాద్‌లో ఉంటుంది — My sister lives in Hyderabad", "tip":"Telugu has specific words for elder/younger siblings"},
      {"phrase":"తమ్ముడు / చెల్లి", "translit":"Tammuḍu / Celli", "meaning":"Younger brother / Younger sister", "example":"నా తమ్ముడు పదో క్లాసులో ఉన్నాడు — My younger brother is in 10th grade", "tip":"Age-relative sibling terms are important in Telugu culture"},
      {"phrase":"భార్య / భర్త", "translit":"Bhārya / Bharta", "meaning":"Wife / Husband", "example":"నా భార్య డాక్టర్ — My wife is a doctor", "tip":"Formal terms; colloquially people also say 'wife'"},
      {"phrase":"పిల్లలు / కొడుకు / కూతురు", "translit":"Pillalu / Koḍuku / Kūturu", "meaning":"Children / Son / Daughter", "example":"మాకు ఒక కొడుకు, ఒక కూతురు ఉన్నారు — We have one son and one daughter", "tip":"'పిల్లలు' is plural (children)"},
    ]
  },
  5: {
    "title": "🗣️ Please, Thank You, Sorry",
    "lessons": [
      {"phrase":"ధన్యవాదాలు / థాంక్యూ", "translit":"Dhanyavādālu / Thank you", "meaning":"Thank you", "example":"మీ సహాయానికి ధన్యవాదాలు — Thank you for your help", "tip":"Both Telugu & English 'thank you' are widely used"},
      {"phrase":"దయచేసి", "translit":"Dayacēsi", "meaning":"Please", "example":"దయచేసి మళ్ళీ చెప్పండి — Please say it again", "tip":"'దయ' = kindness/grace — literally 'with kindness'"},
      {"phrase":"క్షమించండి", "translit":"Kṣamincan̩ḍi", "meaning":"Excuse me / I'm sorry (formal)", "example":"క్షమించండి, నేను ఆలస్యం అయ్యాను — Sorry, I got late", "tip":"Also used to get someone's attention politely"},
      {"phrase":"పర్వాలేదు", "translit":"Parvālēdu", "meaning":"It's okay / No problem", "example":"— క్షమించండి! — పర్వాలేదు! — Sorry! — No problem!", "tip":"One of the most useful phrases in casual Telugu"},
      {"phrase":"సరే", "translit":"Sarē", "meaning":"Okay / Alright / Sure", "example":"సరే, రేపు కలుద్దాం — Okay, let's meet tomorrow", "tip":"Universal filler — you'll hear this constantly"},
    ]
  },
  6: {
    "title": "📅 Days, Time & Dates",
    "lessons": [
      {"phrase":"సోమవారం, మంగళవారం, బుధవారం", "translit":"Sōmavāraṁ, Maṅgaḷavāraṁ, Budhavāraṁ", "meaning":"Monday, Tuesday, Wednesday", "example":"సోమవారం మీటింగ్ ఉంది — There's a meeting on Monday", "tip":"Days end in 'వారం' (vāraṁ = day of the week)"},
      {"phrase":"గురువారం, శుక్రవారం, శనివారం, ఆదివారం", "translit":"Guruvāraṁ, Śukravāraṁ, Śanivāraṁ, Ādivāraṁ", "meaning":"Thu, Fri, Sat, Sun", "example":"ఆదివారం సెలవు — Sunday is a holiday", "tip":"'ఆది' = beginning, so Sunday is 'first day'"},
      {"phrase":"ఈరోజు / నిన్న / రేపు", "translit":"Īrōju / Ninna / Rēpu", "meaning":"Today / Yesterday / Tomorrow", "example":"ఈరోజు వేడిగా ఉంది — It's hot today", "tip":"These three are used constantly — master them first"},
      {"phrase":"ఇప్పుడు / తర్వాత / ముందు", "translit":"Ippuḍu / Tarvāta / Mundu", "meaning":"Now / Later / Before/Earlier", "example":"ఇప్పుడు తినటానికి వెళ్దాం — Let's go eat now", "tip":"'తర్వాత' is your 'later, later' for procrastination 😄"},
      {"phrase":"ఎంత సమయం అయింది?", "translit":"Enta samayaṁ ayindi?", "meaning":"What time is it?", "example":"ఇప్పుడు ఎంత సమయం? — What's the time now?", "tip":"Also: 'గంట ఎంత?' — colloquial shortcut"},
    ]
  },
  7: {
    "title": "🍛 Food & Eating",
    "lessons": [
      {"phrase":"నాకు ఆకలిగా ఉంది", "translit":"Nāku ākaligā undi", "meaning":"I am hungry", "example":"నాకు చాలా ఆకలిగా ఉంది — I am very hungry", "tip":"'చాలా' = very. Add it to any adjective to intensify"},
      {"phrase":"భోజనం చేశారా?", "translit":"Bhōjanaṁ cēśārā?", "meaning":"Have you eaten? (formal greeting!)", "example":"భోజనం చేశారా? — Have you had your meal?", "tip":"This IS a greeting in Telugu culture — deeply warm"},
      {"phrase":"ఇది చాలా రుచిగా ఉంది", "translit":"Idi cālā rucigā undi", "meaning":"This is very tasty", "example":"అమ్మ వంట చాలా రుచిగా ఉంది — Mom's cooking is delicious", "tip":"Best compliment you can give a Telugu host!"},
      {"phrase":"కారంగా ఉంది", "translit":"Kāraṁgā undi", "meaning":"It's spicy", "example":"నాకు కారం తక్కువ పెట్టండి — Put less chilli for me", "tip":"'కారం తక్కువ' = less spice. Crucial for survival 🌶️"},
      {"phrase":"నీళ్ళు తీసుకురండి", "translit":"Nīḷḷu tīsukuraṇḍi", "meaning":"Please bring water", "example":"కొంచెం నీళ్ళు ఇవ్వగలరా? — Can you give some water?", "tip":"'కొంచెం' = a little/some. Very useful word"},
    ]
  },
  8: {
    "title": "🏙️ Places & Directions",
    "lessons": [
      {"phrase":"ఇది ఎక్కడ ఉంది?", "translit":"Idi ekkada undi?", "meaning":"Where is this?", "example":"రైల్వే స్టేషన్ ఎక్కడ ఉంది? — Where is the railway station?", "tip":"'ఎక్కడ' = where. One of the most used question words"},
      {"phrase":"ఎడమ / కుడి / నేరుగా", "translit":"Eḍama / Kuḍi / Nērugā", "meaning":"Left / Right / Straight", "example":"కుడి వైపు తిరగండి — Turn to the right", "tip":"'వైపు' = direction/side"},
      {"phrase":"దగ్గర / దూరం", "translit":"Daggara / Dūraṁ", "meaning":"Near / Far", "example":"బస్ స్టాప్ దగ్గరలో ఉంది — The bus stop is nearby", "tip":"'దగ్గరలో' = nearby (with location suffix)"},
      {"phrase":"ఆటో / బస్ / మెట్రో ఎక్కడ ఉంది?", "translit":"Āṭō / bas / meṭrō ekkada undi?", "meaning":"Where is the auto/bus/metro?", "example":"మెట్రో స్టేషన్ ఎక్కడుంది? — Where is the metro station?", "tip":"Hyderabad metro is huge — this phrase saves trips!"},
      {"phrase":"ఎంత దూరం?", "translit":"Enta dūraṁ?", "meaning":"How far is it?", "example":"అక్కడికి ఎంత దూరం? — How far is it from here?", "tip":"'అక్కడికి' = to there. 'ఇక్కడికి' = to here"},
    ]
  },

  # ══ PHASE 2 — DAILY LIFE (Weeks 9–16) ══
  9: {
    "title": "🛒 Shopping & Money",
    "lessons": [
      {"phrase":"ఇది ఎంత?", "translit":"Idi enta?", "meaning":"How much is this?", "example":"ఈ చీర ఎంత? — How much is this saree?", "tip":"The most powerful shopping phrase!"},
      {"phrase":"చాలా ఎక్కువ — తగ్గించండి", "translit":"Cālā ekkuva — taggincaṇḍi", "meaning":"Too expensive — please reduce", "example":"అరవై రూపాయలు చాలా ఎక్కువ — 60 rupees is too much", "tip":"Bargaining is expected at local markets!"},
      {"phrase":"నాకు ఇది కావాలి", "translit":"Nāku idi kāvāli", "meaning":"I want this", "example":"నాకు రెండు కావాలి — I want two of these", "tip":"'కావాలి' = want/need. Core verb to learn"},
      {"phrase":"చిల్లర ఉందా?", "translit":"Cillara undā?", "meaning":"Do you have change?", "example":"వంద రూపాయలకి చిల్లర ఉందా? — Change for 100 rupees?", "tip":"'చిల్లర' = loose change. Always asked at autos!"},
      {"phrase":"బ్యాగ్ ఇవ్వండి", "translit":"Byāg ivaṇḍi", "meaning":"Give me a bag", "example":"ప్లాస్టిక్ బ్యాగ్ ఉందా? — Do you have a plastic bag?", "tip":"Many shops charge for bags now — good to ask"},
    ]
  },
  10: {
    "title": "🤒 Health & Body",
    "lessons": [
      {"phrase":"నాకు బాగా లేదు", "translit":"Nāku bāgā lēdu", "meaning":"I'm not feeling well", "example":"ఈరోజు నాకు బాగా లేదు — I'm not feeling well today", "tip":"Key phrase for calling in sick or visiting a doctor"},
      {"phrase":"తలనొప్పి / జ్వరం / దగ్గు", "translit":"Talanoppi / Jvaraṁ / Daggu", "meaning":"Headache / Fever / Cough", "example":"నాకు జ్వరంగా ఉంది — I have a fever", "tip":"'నొప్పి' = pain. Add body part before it"},
      {"phrase":"డాక్టర్ దగ్గరికి వెళ్ళాలి", "translit":"Ḍākṭar daggariiki veḷḷāli", "meaning":"I need to go to the doctor", "example":"ఈ నొప్పికి డాక్టర్ దగ్గర చూపించాలి — Should show the doctor for this pain", "tip":"'చూపించు' = to show (the doctor examines you)"},
      {"phrase":"మందులు", "translit":"Mandul", "meaning":"Medicine / Tablets", "example":"ఏ మందులు వాడుతున్నారు? — What medicines are you taking?", "tip":"'వాడు' = to use/take (medicine)"},
      {"phrase":"నీళ్ళు ఎక్కువ తాగండి", "translit":"Nīḷḷu ekkuva tāgaṇḍi", "meaning":"Drink more water", "example":"జ్వరానికి నీళ్ళు ఎక్కువ తాగండి — Drink more water for fever", "tip":"Universal Telugu doctor advice 😄"},
    ]
  },
  11: {
    "title": "💼 Work & Office",
    "lessons": [
      {"phrase":"మీటింగ్ ఎప్పుడు?", "translit":"Mīṭiṁg eppuḍu?", "meaning":"When is the meeting?", "example":"రేపు మీటింగ్ ఉందా? — Is there a meeting tomorrow?", "tip":"'ఎప్పుడు' = when. Question word you'll use daily"},
      {"phrase":"పని పూర్తయింది", "translit":"Pani pūrtayindi", "meaning":"Work is done / Task complete", "example":"నా పని పూర్తయింది — My work is done", "tip":"'పూర్తి' = complete. 'పని' = work/task"},
      {"phrase":"నేను ఆలస్యం అవుతున్నాను", "translit":"Nēnu ālas̤yaṁ avutunnānu", "meaning":"I am getting late", "example":"ట్రాఫిక్‌లో చిక్కుకుపోయాను — I got stuck in traffic", "tip":"Hyderabad traffic excuse — instantly understood 😄"},
      {"phrase":"ఇమెయిల్ పంపించాను", "translit":"Imeyil pampin̐cānu", "meaning":"I sent the email", "example":"రిపోర్ట్ మెయిల్ చేశాను — I mailed the report", "tip":"Tech/office vocab is mostly English + Telugu grammar"},
      {"phrase":"సమస్య ఏమిటి?", "translit":"Samasya ēmiṭi?", "meaning":"What is the problem?", "example":"ఏం సమస్య వచ్చింది? — What problem came up?", "tip":"'సమస్య' = problem. 'పరిష్కారం' = solution"},
    ]
  },
  12: {
    "title": "🌦️ Weather & Seasons",
    "lessons": [
      {"phrase":"వేడిగా ఉంది", "translit":"Vēḍigā undi", "meaning":"It is hot", "example":"ఈరోజు చాలా వేడిగా ఉంది — It's very hot today", "tip":"AP/Telangana gets brutal summers — you'll say this a lot"},
      {"phrase":"వర్షం పడుతోంది", "translit":"Varṣaṁ paḍutōṁdi", "meaning":"It is raining", "example":"బయట వర్షం పడుతోంది — It's raining outside", "tip":"'వర్షం' = rain. 'బయట' = outside"},
      {"phrase":"చలిగా ఉంది", "translit":"Caligā undi", "meaning":"It is cold", "example":"డిసెంబర్‌లో చలిగా ఉంటుంది — It's cold in December", "tip":"Winters in Hyderabad are mild but people still say this!"},
      {"phrase":"గాలి వీస్తోంది", "translit":"Gāli vīstōṁdi", "meaning":"Wind is blowing", "example":"చాలా గాలి వీస్తోంది — There's a lot of wind", "tip":"'గాలి' = wind/air. Used to describe breezy days"},
      {"phrase":"ఆకాశం మేఘావృతమైంది", "translit":"Ākāśaṁ mēghāvṛtamayindi", "meaning":"The sky is cloudy", "example":"మేఘంగా ఉంది, వర్షం వస్తుందేమో — Cloudy, might rain", "tip":"Colloquially just say 'మేఘంగా ఉంది' — cloudy/overcast"},
    ]
  },
  13: {
    "title": "🚌 Transport & Travel",
    "lessons": [
      {"phrase":"టికెట్ ఎక్కడ దొరుకుతుంది?", "translit":"Ṭikeṭ ekkada dorukutundi?", "meaning":"Where can I get a ticket?", "example":"బస్ టికెట్ ఎక్కడ కొనాలి? — Where to buy a bus ticket?", "tip":"'దొరుకు' = to be found/obtained"},
      {"phrase":"ఏ బస్ వెళ్తుంది?", "translit":"Ē bas veḷtundi?", "meaning":"Which bus goes (there)?", "example":"సికింద్రాబాద్‌కి ఏ బస్ వెళ్తుంది? — Which bus goes to Secunderabad?", "tip":"'కి/కు' = to (direction suffix)"},
      {"phrase":"ఆటో వస్తావా?", "translit":"Āṭō vastāvā?", "meaning":"Will you come (by auto)?", "example":"మీటర్ మీద వస్తావా? — Will you come on meter?", "tip":"The eternal auto negotiation opener in Hyderabad 🛺"},
      {"phrase":"ఇక్కడ ఆపండి", "translit":"Ikkada āpaṇḍi", "meaning":"Stop here", "example":"ఇక్కడే ఆపండి, థాంక్యూ — Stop right here, thank you", "tip":"'ఆపు' = to stop. Essential for autos/cabs"},
      {"phrase":"ఎంత సమయం పడుతుంది?", "translit":"Enta samayaṁ paḍutundi?", "meaning":"How long will it take?", "example":"అక్కడికి చేరుకోవటానికి ఎంత సమయం? — How long to reach there?", "tip":"'చేరుకోవటానికి' = to reach. Can just say 'చేరుకోవటానికి ఎంత?'"},
    ]
  },
  14: {
    "title": "🏠 Home & Daily Routine",
    "lessons": [
      {"phrase":"లేచాను / నిద్రపోతున్నాను", "translit":"Lēcānu / Nidrapōtunnānu", "meaning":"I woke up / I am sleeping", "example":"ఇప్పుడే లేచాను — I just woke up now", "tip":"'ఇప్పుడే' = just now. Great filler phrase"},
      {"phrase":"స్నానం చేశాను", "translit":"Snānaṁ cēśānu", "meaning":"I took a bath", "example":"స్నానం చేసి వస్తాను — I'll come after bathing", "tip":"'చేసి వస్తాను' = will come after doing"},
      {"phrase":"వంట చేస్తున్నాను", "translit":"Vaṇṭa cēstunnānu", "meaning":"I am cooking", "example":"అమ్మ వంట చేస్తోంది — Mom is cooking", "tip":"'వంట' = cooking. 'అడిగేశాను' = I already asked"},
      {"phrase":"ఇల్లు శుభ్రం చేస్తున్నాను", "translit":"Illu śubhraṁ cēstunnānu", "meaning":"I am cleaning the house", "example":"వీకెండ్‌లో ఇల్లు శుభ్రం చేస్తాను — I clean the house on weekends", "tip":"'శుభ్రం' = clean. 'ఇల్లు' = house"},
      {"phrase":"తలుపు తట్టు / తెరవు / మూయి", "translit":"Talupu taṭṭu / teravu / mūyi", "meaning":"Knock / Open / Close the door", "example":"తలుపు తెరవండి — Please open the door", "tip":"'తలుపు' = door. Very practical!"},
    ]
  },
  15: {
    "title": "📱 Phone & Technology",
    "lessons": [
      {"phrase":"ఫోన్ చేయండి", "translit":"Phōn cēyaṇḍi", "meaning":"Please call (me)", "example":"తర్వాత ఫోన్ చేస్తాను — I'll call later", "tip":"'చేయు' = to do/make. Used for calls, tasks"},
      {"phrase":"మెసేజ్ పంపించు", "translit":"Mesēj pampincu", "meaning":"Send a message", "example":"వాట్సాప్‌లో మెసేజ్ పంపించు — Send a message on WhatsApp", "tip":"WhatsApp is how everyone communicates in Telugu families!"},
      {"phrase":"నెట్ పని చేయటం లేదు", "translit":"Neṭ pani cēyaṭaṁ lēdu", "meaning":"Internet is not working", "example":"నెట్ స్లో గా ఉంది — Internet is slow", "tip":"'పని చేయటం లేదు' = not working. Use for anything broken"},
      {"phrase":"చార్జ్ అయిపోతోంది", "translit":"Cārj ayipōtōṁdi", "meaning":"Battery is dying", "example":"ఫోన్ చార్జ్ అయిపోయింది — Phone battery died", "tip":"'అయిపోయింది' = it ran out/finished"},
      {"phrase":"గూగుల్ చేసి చూడు", "translit":"Gūgal cēsi cūḍu", "meaning":"Google it and check", "example":"ఏదైనా తెలియకపోతే గూగుల్ చేసి చూడు — If you don't know something, Google it", "tip":"Universal advice in modern Telugu households 😄"},
    ]
  },
  16: {
    "title": "😄 Emotions & Feelings",
    "lessons": [
      {"phrase":"నాకు చాలా సంతోషంగా ఉంది", "translit":"Nāku cālā santōṣaṁgā undi", "meaning":"I am very happy", "example":"ఈ వార్త విని సంతోషంగా ఉంది — Hearing this news, I feel happy", "tip":"'సంతోషం' = happiness. Opposite: 'దుఃఖం' = sadness"},
      {"phrase":"నాకు కోపంగా ఉంది", "translit":"Nāku kōpaṁgā undi", "meaning":"I am angry", "example":"అతని మాటలు విని కోపం వచ్చింది — His words made me angry", "tip":"'కోపం వచ్చింది' = anger came (to me) — Telugu idiom"},
      {"phrase":"నాకు భయంగా ఉంది", "translit":"Nāku bhayaṁgā undi", "meaning":"I am scared", "example":"చీకట్లో భయంగా ఉంది — It's scary in the dark", "tip":"'భయం' = fear. 'భయపడకు' = don't be scared"},
      {"phrase":"విసుగుగా ఉంది", "translit":"Visugugā undi", "meaning":"I am bored / annoyed", "example":"ఇంట్లోనే ఉండి విసుగు వచ్చింది — Got bored sitting at home", "tip":"'విసుగు' covers both boredom and mild irritation"},
      {"phrase":"నాకు ఆశ్చర్యంగా ఉంది", "translit":"Nāku āścaryaṁgā undi", "meaning":"I am surprised", "example":"ఈ విషయం విని ఆశ్చర్యపోయాను — I was surprised to hear this", "tip":"'ఆశ్చర్యపోయాను' = I got amazed (past tense)"},
    ]
  },

  # ══ PHASE 3 — CONVERSATIONS (Weeks 17–28) ══
  17: {
    "title": "🗣️ Expressing Opinions",
    "lessons": [
      {"phrase":"నా అభిప్రాయం ఏమిటంటే...", "translit":"Nā abhiprāyaṁ ēmiṭante...", "meaning":"In my opinion...", "example":"నా అభిప్రాయం ఏమిటంటే, ఇది మంచి నిర్ణయం — In my opinion, this is a good decision", "tip":"'నిర్ణయం' = decision. Formal but commonly used"},
      {"phrase":"నేను అంగీకరిస్తున్నాను / అంగీకరించను", "translit":"Nēnu aṅgīkaristunnānu / aṅgīkarincan̐u", "meaning":"I agree / I don't agree", "example":"మీ మాటతో అంగీకరిస్తున్నాను — I agree with what you said", "tip":"'మాటతో' = with the words/speech"},
      {"phrase":"నాకు అర్థం కాలేదు", "translit":"Nāku arthaṁ kālēdu", "meaning":"I didn't understand", "example":"మళ్ళీ చెప్పగలరా? నాకు అర్థం కాలేదు — Can you repeat? I didn't understand", "tip":"Very important learner phrase — use it freely!"},
      {"phrase":"మీరు సరిగ్గా చెప్పారు", "translit":"Mīru sarigga ceppāru", "meaning":"You said it correctly / You're right", "example":"మీరు చెప్పింది సరిగ్గానే ఉంది — What you said is correct", "tip":"Great for affirmation in conversation"},
      {"phrase":"నాకు తెలియదు", "translit":"Nāku teliyadu", "meaning":"I don't know", "example":"క్షమించండి, నాకు తెలియదు — Sorry, I don't know", "tip":"Honest and perfectly polite to say"},
    ]
  },
  18: {
    "title": "🎭 Telling Stories (Past Tense)",
    "lessons": [
      {"phrase":"నేను వెళ్ళాను", "translit":"Nēnu veḷḷānu", "meaning":"I went", "example":"నేను హైదరాబాద్ వెళ్ళాను — I went to Hyderabad", "tip":"Past tense: verb stem + ఆను/ఆడు/ఇంది for different subjects"},
      {"phrase":"అతను చెప్పాడు", "translit":"Atanu ceppāḍu", "meaning":"He said", "example":"అతను రేపు వస్తానని చెప్పాడు — He said he would come tomorrow", "tip":"'అతను' = he; 'ఆమె' = she; verbs change by gender"},
      {"phrase":"మేము చాలా సంతోషించాము", "translit":"Mēmu cālā santōṣin̐cāmu", "meaning":"We were very happy", "example":"ఆ వార్త విని మేము సంతోషించాము — Hearing that news we were happy", "tip":"'మేము' = we (exclusive — not including listener)"},
      {"phrase":"అది జరిగింది", "translit":"Adi jarigindi", "meaning":"That happened / It occurred", "example":"ఏం జరిగింది? — What happened?", "tip":"'జరుగు' = to happen. 'ఏం జరిగింది' — go-to question"},
      {"phrase":"నేను చూశాను / తిన్నాను / విన్నాను", "translit":"Nēnu cūśānu / tinnānu / vinnānu", "meaning":"I saw / I ate / I heard", "example":"ఆ సినిమా నేను చూశాను — I watched that movie", "tip":"Saw=చూశాను, Ate=తిన్నాను, Heard=విన్నాను — three essential past forms"},
    ]
  },
  19: {
    "title": "🔮 Future Plans",
    "lessons": [
      {"phrase":"నేను వెళ్తాను", "translit":"Nēnu veḷtānu", "meaning":"I will go", "example":"రేపు నేను ఆఫీసుకి వెళ్తాను — Tomorrow I will go to office", "tip":"Future: verb + తాను/తాడు/తుంది for I/he/she"},
      {"phrase":"మనం కలుద్దాం", "translit":"Manaṁ kaluddāṁ", "meaning":"Let's meet (us — inclusive)", "example":"సాయంత్రం కలుద్దాం — Let's meet in the evening", "tip":"'మనం' = we inclusive (with the listener). Warm usage"},
      {"phrase":"నేను ప్రయత్నిస్తాను", "translit":"Nēnu prayatnistānu", "meaning":"I will try", "example":"చేయగలిగితే నేను ప్రయత్నిస్తాను — I will try if I can", "tip":"Polite way to commit without over-promising"},
      {"phrase":"రాబోయే సంవత్సరంలో", "translit":"Rābōyē saṁvatsaraṁlō", "meaning":"In the coming year", "example":"రాబోయే సంవత్సరంలో పెళ్ళి చేసుకోవాలని ఉంది — Planning to marry in the coming year", "tip":"'రాబోయే' = coming/upcoming"},
      {"phrase":"నా ప్లాన్ ఏమిటంటే...", "translit":"Nā plān ēmiṭante...", "meaning":"My plan is...", "example":"నా ప్లాన్ ఏమిటంటే, ముందు పని చేసి తర్వాత చదువుతాను — My plan is to work first, then study", "tip":"'ప్లాన్' is borrowed English, totally natural in Telugu"},
    ]
  },
  20: {
    "title": "🎓 Asking & Learning",
    "lessons": [
      {"phrase":"ఇది తెలుగులో ఏమంటారు?", "translit":"Idi teluglō ēmantāru?", "meaning":"What do you call this in Telugu?", "example":"'Computer' తెలుగులో ఏమంటారు? — What's 'computer' in Telugu?", "tip":"Your most powerful learning tool — ask native speakers!"},
      {"phrase":"దయచేసి నెమ్మదిగా మాట్లాడండి", "translit":"Dayacēsi nemmadiga māṭlāḍaṇḍi", "meaning":"Please speak slowly", "example":"నాకు కొంచెం నెమ్మదిగా మాట్లాడండి — Please speak a bit slower for me", "tip":"Never hesitate to ask! Every native speaker appreciates the effort"},
      {"phrase":"మళ్ళీ చెప్పగలరా?", "translit":"Maḷḷī ceppagalarā?", "meaning":"Can you say it again?", "example":"క్షమించండి, మళ్ళీ చెప్పగలరా? — Excuse me, can you say that again?", "tip":"Completely normal — shows engagement"},
      {"phrase":"ఉచ్చారణ సరిగ్గా ఉందా?", "translit":"Uccāraṇa sarigga undā?", "meaning":"Is my pronunciation correct?", "example":"నేను సరిగ్గా అంటున్నానా? — Am I saying it correctly?", "tip":"Asking for correction is the fastest way to improve"},
      {"phrase":"నేను తెలుగు నేర్చుకుంటున్నాను", "translit":"Nēnu Telugu nērcukuntunnānu", "meaning":"I am learning Telugu", "example":"నేను తెలుగు నేర్చుకుంటున్నాను, తప్పులు దయచేసి సరిచేయండి — I'm learning Telugu, please correct my mistakes", "tip":"This phrase alone will make people LOVE helping you"},
    ]
  },
  21: {
    "title": "🎊 Celebrations & Culture",
    "lessons": [
      {"phrase":"శుభాకాంక్షలు!", "translit":"Śubhākāṅkṣalu!", "meaning":"Congratulations! / Best wishes!", "example":"పుట్టినరోజు శుభాకాంక్షలు! — Happy Birthday!", "tip":"Universal for birthdays, weddings, achievements"},
      {"phrase":"పుట్టినరోజు శుభాకాంక్షలు", "translit":"Puṭṭinarōju śubhākāṅkṣalu", "meaning":"Happy Birthday", "example":"మీకు పుట్టినరోజు శుభాకాంక్షలు! — Happy Birthday to you!", "tip":"'పుట్టినరోజు' = birthday (literally 'birth day')"},
      {"phrase":"వివాహ శుభాకాంక్షలు", "translit":"Vivāha śubhākāṅkṣalu", "meaning":"Wedding congratulations", "example":"మీ పెళ్ళికి అభినందనలు! — Congratulations on your wedding!", "tip":"'పెళ్ళి' = wedding. Colloquial. 'వివాహం' = formal"},
      {"phrase":"పండుగ శుభాకాంక్షలు", "translit":"Paṇḍuga śubhākāṅkṣalu", "meaning":"Festival greetings", "example":"ఉగాది/దసరా/దీపావళి శుభాకాంక్షలు! — Happy Ugadi/Dasara/Diwali!", "tip":"Ugadi (Telugu New Year) is the most important — usually in March/April"},
      {"phrase":"చాలా సంతోషం!", "translit":"Cālā santōṣaṁ!", "meaning":"Very happy! / What great news!", "example":"మీ పదోన్నతి విన్నాను — చాలా సంతోషం! — Heard about your promotion — so happy!", "tip":"Works as a standalone exclamation of joy"},
    ]
  },
  22: {
    "title": "🌶️ Colloquial Telugu & Slang",
    "lessons": [
      {"phrase":"ఏంట్రా / ఏంట్రోయ్", "translit":"Ēṇṭrā / Ēṇṭrōy", "meaning":"What man! / Hey what's up (casual male)", "example":"ఏంట్రా, ఎక్కడికి వెళ్తున్నావు? — Hey man, where are you going?", "tip":"Extremely casual, between close male friends. '-rā' suffix = male peer"},
      {"phrase":"సూపర్! / ఫస్టుక్లాసు!", "translit":"Sūpar! / Phastukklāsu!", "meaning":"Super! / First class! (excellent)", "example":"ఆ సినిమా సూపర్‌గా ఉంది! — That movie was super!", "tip":"Telugu people LOVE saying 'super' for anything great"},
      {"phrase":"ఒరే / ఒసే", "translit":"Orē / Osē", "meaning":"Hey! (casual call, male/female)", "example":"ఒరే, ఇటు రా! — Hey, come here!", "tip":"'ఒరే' for males, 'ఒసే' for females. Very casual"},
      {"phrase":"అయ్యో!", "translit":"Ayyō!", "meaning":"Oh no! / Oh dear! (expression of dismay)", "example":"అయ్యో, పడిపోయాను! — Oh no, I fell!", "tip":"Universal Telugu expression — you'll hear it constantly"},
      {"phrase":"బాగుపడతావు", "translit":"Bāgupaḍatāvu", "meaning":"You'll be fine / Get well soon", "example":"అయ్యో, జ్వరమా? బాగుపడతావు — Oh fever? You'll be fine", "tip":"Comforting phrase. 'బాగుపడు' = to recover/improve"},
    ]
  },
  23: {
    "title": "🍽️ Ordering Food Like a Local",
    "lessons": [
      {"phrase":"ఒక్క _____ ఇవ్వండి", "translit":"Okka _____ ivaṇḍi", "meaning":"Give me one _____", "example":"ఒక్క మసాలా దోశ ఇవ్వండి — Give me one masala dosa", "tip":"'ఒక్క' = one (emphatic). Drop it for plural: 'రెండు ఇవ్వండి'"},
      {"phrase":"మీనూ చూపించండి", "translit":"Mīnū cūpincan̩ḍi", "meaning":"Show me the menu", "example":"మీనూ తీసుకొస్తారా? — Can you bring the menu?", "tip":"'తీసుకొస్తారా' = will you bring? Polite request form"},
      {"phrase":"బిల్లు తీసుకురండి", "translit":"Billu tīsukuraṇḍi", "meaning":"Please bring the bill", "example":"బిల్లు ఇవ్వండి, వెళ్తాం — Give the bill, we're leaving", "tip":"'వెళ్తాం' = we're going. Natural to add when asking for bill"},
      {"phrase":"ఫ్రీలో పార్సెల్ చేస్తారా?", "translit":"Pharlō pārsēl cēstārā?", "meaning":"Will you pack it (for takeaway)?", "example":"పార్సెల్ ఇవ్వగలరా? — Can you give it as takeaway?", "tip":"'పార్సెల్' is the Telugu word for takeaway/doggy bag"},
      {"phrase":"నాకు శాకాహారం మాత్రమే", "translit":"Nāku śākāhāraṁ mātraṁ", "meaning":"Only vegetarian for me", "example":"నాకు మాంసాహారం వద్దు — I don't want non-veg", "tip":"'శాకాహారి' = vegetarian person. Important in Telugu culture"},
    ]
  },
  24: {
    "title": "💬 Making Friends",
    "lessons": [
      {"phrase":"మీతో మాట్లాడటం చాలా సంతోషంగా ఉంది", "translit":"Mītō māṭlāḍaṭaṁ cālā santōṣaṁgā undi", "meaning":"It was great talking to you", "example":"మీతో పరిచయం కావటం సంతోషం — Happy to meet you", "tip":"'పరిచయం' = acquaintance/introduction"},
      {"phrase":"మనం స్నేహితులమవుదాం", "translit":"Manaṁ snēhitulamavudāṁ", "meaning":"Let's be friends", "example":"మీతో స్నేహంగా ఉండాలని ఉంది — I'd like to be friends with you", "tip":"'స్నేహం' = friendship. 'స్నేహితుడు' = friend (male)"},
      {"phrase":"మీ నంబర్ ఇస్తారా?", "translit":"Mī nambar istārā?", "meaning":"Will you give your number?", "example":"మళ్ళీ కలుద్దాం — మీ నంబర్ ఇవ్వగలరా? — Let's meet again — can you give your number?", "tip":"Perfectly normal — Telugu people exchange numbers very openly"},
      {"phrase":"మళ్ళీ కలుద్దాం", "translit":"Maḷḷī kaluddāṁ", "meaning":"Let's meet again", "example":"చాలా సేపు మాట్లాడాం — మళ్ళీ కలుద్దాం! — We talked so long — let's meet again!", "tip":"Warm farewell phrase for new acquaintances"},
      {"phrase":"మీరు చాలా మంచివారు", "translit":"Mīru cālā mancivāru", "meaning":"You are very kind/good", "example":"మీ సహాయానికి ధన్యవాదాలు — మీరు చాలా మంచివారు — Thank you for your help — you're very kind", "tip":"'మంచి' = good. 'మంచివారు' = good person (plural/respectful)"},
    ]
  },

  # ══ PHASE 4 — FLUENCY (Weeks 25–40) ══
  25: {
    "title": "🧠 Proverbs & Wisdom (భాషా జ్ఞానం)",
    "lessons": [
      {"phrase":"చేతిలో ఉన్న పిట్ట కంటే కంచె మీది పిట్ట నయం", "translit":"Cētilō unna piṭṭa kaṭā kance mīdi piṭṭa nayaṁ", "meaning":"The bird on the fence is better than the one in hand (= grass is greener)", "example":"అతను కొత్త ఉద్యోగం కోసం ఉన్న ఉద్యోగం వదిలాడు — చేతిలో ఉన్న పిట్ట...", "tip":"Telugu version of 'bird in hand' — used to caution risk"},
      {"phrase":"ఆలస్యం అమృతం విషం", "translit":"Ālasyam amṛtaṁ viṣaṁ", "meaning":"Delay is nectar turned poison (= procrastination hurts)", "example":"పని ఆలస్యం చేయకు — ఆలస్యం అమృతం విషం అంటారు — Don't delay work — they say delay is poison", "tip":"Classic proverb every Telugu parent quotes 😄"},
      {"phrase":"విద్యే వినయం", "translit":"Vidyē vinayam", "meaning":"Education brings humility", "example":"చదువుకున్నవారు ఎప్పుడూ వినయంగా ఉంటారు — Educated people are always humble", "tip":"Deeply valued in Telugu culture"},
      {"phrase":"అన్నదాత సుఖీభవ", "translit":"Annadāta sukhībhava", "meaning":"May the one who feeds you be happy (blessing for food giver)", "example":"అన్నం పెట్టే అమ్మకు ఆశీర్వాదాలు — Blessings to the mother who feeds", "tip":"Said as a blessing at meals and to farmers"},
      {"phrase":"ఒంటరిగా వెళ్తే ఒక అడుగు, కలిసి వెళ్తే వెయ్యి అడుగులు", "translit":"Onṭarigā veḷtē oka aḍugu, kalisi veḷtē veyyi aḍugulu", "meaning":"Go alone one step, go together a thousand steps", "example":"జట్టుగా పని చేద్దాం — కలిసి వెళ్తే వెయ్యి అడుగులు — Let's work as a team", "tip":"Telugu way of saying teamwork makes the dream work"},
    ]
  },
  26: {
    "title": "🎬 Telugu Cinema Culture",
    "lessons": [
      {"phrase":"సినిమా చూశావా?", "translit":"Sinimā cūśāvā?", "meaning":"Did you watch the movie?", "example":"నిన్న కొత్త సినిమా చూశావా? — Did you watch the new movie yesterday?", "tip":"Telugu cinema (Tollywood) is a huge cultural connector"},
      {"phrase":"ఆ పాట చాలా బాగుంది", "translit":"Ā pāṭa cālā bāgundi", "meaning":"That song is very nice", "example":"ఆర్ఆర్ఆర్ పాటలు అన్నీ సూపర్ — All RRR songs are super!", "tip":"Knowing a few Tollywood songs = instant connection with any Telugu speaker"},
      {"phrase":"మనసు పారేసుకున్నాను", "translit":"Manasu pārēsukunnaanu", "meaning":"I lost my heart (fell in love with it)", "example":"ఆ సినిమా చూసి మనసు పారేసుకున్నాను — I fell in love with that movie", "tip":"Romantic/poetic expression beloved in Telugu films"},
      {"phrase":"ఇది మాస్ సినిమా / క్లాస్ సినిమా", "translit":"Idi māss sinimā / klāss sinimā", "meaning":"This is a mass (commercial) / class (art) movie", "example":"బాహుబలి ఒక మాస్ సినిమా — Baahubali is a mass movie", "tip":"'మాస్' = commercial action; 'క్లాస్' = serious/art film"},
      {"phrase":"డైలాగ్ బాగుంది!", "translit":"Ḍailāg bāgundi!", "meaning":"Good dialogue!", "example":"ఆ సీన్‌లో డైలాగ్ చాలా పవర్‌ఫుల్‌గా ఉంది — The dialogue in that scene was very powerful", "tip":"Telugu films are famous for powerful one-liners"},
    ]
  },
  27: {
    "title": "🏏 Sports & Leisure",
    "lessons": [
      {"phrase":"క్రికెట్ ఆడతావా?", "translit":"Krikeṭ āḍatāvā?", "meaning":"Do you play cricket?", "example":"వీకెండ్‌లో క్రికెట్ ఆడదాం — Let's play cricket on the weekend", "tip":"Cricket is a cultural language in Andhra/Telangana"},
      {"phrase":"భారత్ గెలిచింది!", "translit":"Bhārat gelicindi!", "meaning":"India won!", "example":"మ్యాచ్ భారత్ గెలిచింది — ఆడుద్దాం! — India won the match — let's celebrate!", "tip":"'గెలు' = to win. 'ఓడు' = to lose"},
      {"phrase":"పరిగెత్తడం / ఈత కొట్టడం", "translit":"Parigetṭaḍaṁ / Īta koṭṭaḍaṁ", "meaning":"Running / Swimming", "example":"ప్రతి రోజు పరిగెత్తుతాను — I run every day", "tip":"'ఆడటం' = playing. '-డం' suffix turns verb to gerund"},
      {"phrase":"ఆట మొదలైంది / అయిపోయింది", "translit":"Āṭa modalayindi / ayipōyindi", "meaning":"The game started / ended", "example":"ఆట మొదలైంది, త్వరగా రా! — Game started, come fast!", "tip":"'మొదలు' = start/beginning. 'మొదలుపెట్టు' = to start"},
      {"phrase":"జిమ్‌కి వెళ్తున్నావా?", "translit":"Jimki veḷtunnāvā?", "meaning":"Are you going to the gym?", "example":"ఇవాళ జిమ్ స్కిప్ చేస్తాను — I'll skip the gym today", "tip":"'స్కిప్ చేయు' = to skip. English+Telugu combo is very natural"},
    ]
  },
  28: {
    "title": "💰 Money, Banking & Business",
    "lessons": [
      {"phrase":"డబ్బు అవసరం", "translit":"Ḍabbu avaśyaṁ", "meaning":"Need money", "example":"నాకు ఈ నెల డబ్బు కొంచెం తక్కువగా ఉంది — I'm a bit short on money this month", "tip":"'డబ్బు' = money (colloquial). 'ధనం' = formal"},
      {"phrase":"జీతం ఎంత?", "translit":"Jītaṁ enta?", "meaning":"How much is the salary?", "example":"కొత్త ఉద్యోగంలో జీతం బాగుందా? — Is the salary good in the new job?", "tip":"'జీతం' = salary/wages. Very commonly discussed"},
      {"phrase":"ATM ఎక్కడ ఉంది?", "translit":"ĒṭiEM ekkada undi?", "meaning":"Where is the ATM?", "example":"దగ్గర్లో ATM ఉందా? — Is there an ATM nearby?", "tip":"'దగ్గర్లో' = nearby. Useful travel phrase"},
      {"phrase":"UPI/GPay చేయగలవా?", "translit":"UPI/GPay cēyagalavā?", "meaning":"Can you pay via UPI/GPay?", "example":"UPI తీసుకుంటారా? — Do you accept UPI?", "tip":"Digital payments are huge in Telangana/AP now"},
      {"phrase":"అప్పు ఇవ్వగలవా?", "translit":"Appu ivvagalavā?", "meaning":"Can you lend me money?", "example":"కొంచెం అప్పు ఇవ్వగలవా, తర్వాత ఇస్తాను — Can you lend me some? I'll return later", "tip":"'అప్పు' = loan/borrow. 'తిరిగి ఇవ్వు' = return/repay"},
    ]
  },

  # ══ PHASE 5 — ADVANCED (Weeks 29–52) ══
  29: {
    "title": "📚 Literature & Classical Telugu",
    "lessons": [
      {"phrase":"తెలుగు భాష అమృతం", "translit":"Telugu bhāṣa amṛtaṁ", "meaning":"Telugu language is nectar", "example":"తెనుగు దేల మిన్న — Telugu is the best (from poet Krishnadeva Raya)", "tip":"Telugu was called 'Italian of the East' for its vowel-rich sweetness"},
      {"phrase":"చదువు లేకుంటే చీకటే", "translit":"Caduvu lēkunṭē cīkaṭē", "meaning":"Without education, there is only darkness", "example":"విద్య వెలుగు — Education is light", "tip":"Classical Telugu valued education above all — echoes in every household"},
      {"phrase":"నీతి కావ్యాలు", "translit":"Nīti kāvyālu", "meaning":"Ethical poems / Moral literature", "example":"సుమతి శతకం చదివావా? — Have you read Sumati Shatakam?", "tip":"Vemana and Sumati Shatakam are pillars of Telugu ethical verse"},
      {"phrase":"జానపద పాటలు", "translit":"Jānapada pāṭalu", "meaning":"Folk songs", "example":"తెలంగాణ జానపద పాటలు చాలా బాగుంటాయి — Telangana folk songs are very beautiful", "tip":"Lavani, Oggukatha, Burrakatha — rich oral traditions"},
      {"phrase":"ఇది మన సంస్కృతి", "translit":"Idi mana saṁskṛti", "meaning":"This is our culture", "example":"బతుకమ్మ మన తెలంగాణ సంస్కృతిలో ముఖ్యమైన పండుగ — Bathukamma is an important festival in our Telangana culture", "tip":"'మన' = our (inclusive). Shows belonging and pride"},
    ]
  },
  30: {
    "title": "🌿 Nature & Environment",
    "lessons": [
      {"phrase":"చెట్లు నరకకండి", "translit":"Ceṭlu narakakandi", "meaning":"Don't cut trees", "example":"చెట్లు పెంచండి, చల్లని గాలి పీల్చండి — Grow trees, breathe cool air", "tip":"Environmental awareness is rising in Telugu-speaking states"},
      {"phrase":"నది / కొండ / అడవి", "translit":"Nadi / Koṇḍa / Aḍavi", "meaning":"River / Hill / Forest", "example":"కృష్ణా నది చాలా పవిత్రమైనది — Krishna river is very sacred", "tip":"Rivers like Krishna, Godavari are culturally central"},
      {"phrase":"వాతావరణ కాలుష్యం", "translit":"Vātāvaraṇa kāluṣyaṁ", "meaning":"Environmental pollution", "example":"వాయు కాలుష్యం తగ్గించాలి — Air pollution must be reduced", "tip":"'కాలుష్యం' = pollution. Increasingly heard in news/debates"},
      {"phrase":"వర్షాకాలం / వేసవికాలం / శీతాకాలం", "translit":"Varṣākālaṁ / Vēsavikālaṁ / Śītākālaṁ", "meaning":"Monsoon / Summer / Winter", "example":"వర్షాకాలంలో కోస్తా ప్రాంతాలు అందంగా ఉంటాయి — Coastal areas are beautiful in monsoon", "tip":"Three main seasons recognized in Telugu calendar"},
      {"phrase":"పచ్చని ప్రకృతి", "translit":"Paccani prakṛti", "meaning":"Green nature", "example":"పల్లె లో పచ్చని ప్రకృతి చూస్తే మనసు తేలికవుతుంది — Seeing green nature in the village lightens the heart", "tip":"'పచ్చని' = green/lush. 'ప్రకృతి' = nature"},
    ]
  },
}

# Fill weeks 31-52 by rotating through advanced topics
ADVANCED_TOPICS = [
  {"title": "🏛️ Politics & Current Affairs", "lessons": [
    {"phrase":"ఎన్నికలు ఎప్పుడు?", "translit":"Enniakalu eppuḍu?", "meaning":"When are the elections?", "example":"రాష్ట్ర ఎన్నికలు వచ్చాయి — State elections have come", "tip":"'రాష్ట్రం' = state. 'దేశం' = country/nation"},
    {"phrase":"ప్రభుత్వ పథకాలు", "translit":"Prabhutva pathakālu", "meaning":"Government schemes", "example":"కొత్త పథకం గురించి విన్నావా? — Did you hear about the new scheme?", "tip":"'పథకం' = scheme/plan. Very common in news"},
    {"phrase":"నేను ఓటు వేశాను", "translit":"Nēnu ōṭu vēśānu", "meaning":"I voted", "example":"నువ్వు ఓటు వేశావా? — Did you vote?", "tip":"Voting participation is culturally valued — discussed openly"},
    {"phrase":"రాజకీయం అర్థం కాదు", "translit":"Rājakīyaṁ arthaṁ kādu", "meaning":"Politics is incomprehensible", "example":"రాజకీయం అంటే నాకు అర్థం కాదు — I don't understand politics", "tip":"Common sentiment! 'అర్థం కాదు' = doesn't make sense"},
    {"phrase":"అభివృద్ధి కావాలి", "translit":"Abhivṛddhi kāvāli", "meaning":"We need development/progress", "example":"మన రాష్ట్రానికి మరింత అభివృద్ధి కావాలి — Our state needs more development", "tip":"'అభివృద్ధి' = development. Central word in all political discourse"},
  ]},
  {"title": "🧘 Spirituality & Temples", "lessons": [
    {"phrase":"దేవుడి మీద నమ్మకం", "translit":"Dēvuḍi mīda nammakaṁ", "meaning":"Faith in God", "example":"ఏ కష్టం వచ్చినా దేవుడి మీద నమ్మకం ఉండాలి — Whatever hardship comes, have faith in God", "tip":"Deep spiritual culture — never mock religious sentiments"},
    {"phrase":"గుడికి వెళ్దాం", "translit":"Guḍiki veḷdāṁ", "meaning":"Let's go to the temple", "example":"శనివారం తిరుపతి వెళ్తున్నాం — Going to Tirupati on Saturday", "tip":"Tirupati is the most visited temple on Earth — pilgrimage is huge"},
    {"phrase":"నమస్కారం చేస్తాను", "translit":"Namaskāraṁ cēstānu", "meaning":"I will pay respects", "example":"పెద్దలకు నమస్కారం చేయాలి — One should pay respects to elders", "tip":"Touching elders' feet (నమస్కారం) is a living cultural practice"},
    {"phrase":"ఆశీర్వాదం ఇవ్వండి", "translit":"Āśīrvādaṁ ivaṇḍi", "meaning":"Please give your blessings", "example":"మీ ఆశీర్వాదం కావాలి — I need your blessings", "tip":"Seeking blessings before important events is universal in Telugu culture"},
    {"phrase":"పూజ చేశారా?", "translit":"Pūja cēśārā?", "meaning":"Did you do the puja (worship)?", "example":"ఉదయం పూజ చేశావా? — Did you do morning puja?", "tip":"Daily puja is a ritual in most Telugu households"},
  ]},
  {"title": "🎵 Music & Dance", "lessons": [
    {"phrase":"కర్ణాటక సంగీతం", "translit":"Karnāṭaka saṅgītaṁ", "meaning":"Carnatic music", "example":"కర్ణాటక సంగీతం నేర్చుకుంటున్నాను — I am learning Carnatic music", "tip":"Classical tradition of South India — deeply Telugu-rooted"},
    {"phrase":"కూచిపూడి నాట్యం", "translit":"Kūcipūḍi nāṭyaṁ", "meaning":"Kuchipudi classical dance", "example":"మా అమ్మ కూచిపూడి నేర్చుకుంది — My mom learned Kuchipudi", "tip":"Kuchipudi originates from Andhra Pradesh — iconic Telugu art form"},
    {"phrase":"పాట పాడతావా?", "translit":"Pāṭa pāḍatāvā?", "meaning":"Do you sing?", "example":"నీకు పాడటం వస్తుందా? — Do you know how to sing?", "tip":"'వస్తుంది' = 'it comes to you' = you know how"},
    {"phrase":"తబలా / వీణ / వేణువు", "translit":"Tabolā / Vīṇa / Vēṇuvu", "meaning":"Tabla / Veena / Flute", "example":"వీణ వాయించడం నేర్చుకోవాలని ఉంది — I want to learn to play Veena", "tip":"Veena is the divine instrument of Saraswati — iconic in Telugu homes"},
    {"phrase":"సంగీతం వింటున్నాను", "translit":"Saṅgītaṁ vintunnānu", "meaning":"I am listening to music", "example":"ఏం పాట వింటున్నావు? — What song are you listening to?", "tip":"'వినడం' = listening. 'పాడటం' = singing"},
  ]},
]

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"day": 1, "start_date": str(datetime.date.today())}

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))

def get_lesson(day):
    week = ((day - 1) // 5) + 1
    day_in_week = (day - 1) % 5

    if week <= 30 and week in CURRICULUM:
        topic = CURRICULUM[week]
    else:
        # Advanced rotation
        adv_idx = (week - 31) % len(ADVANCED_TOPICS)
        topic = ADVANCED_TOPICS[adv_idx]

    lessons = topic["lessons"]
    lesson = lessons[day_in_week % len(lessons)]
    return week, day_in_week + 1, topic["title"], lesson

def phase_name(week):
    if week <= 8: return "Phase 1 — Foundation 🌱"
    if week <= 16: return "Phase 2 — Daily Life 🏡"
    if week <= 28: return "Phase 3 — Conversations 🗣️"
    if week <= 40: return "Phase 4 — Fluency 🎯"
    return "Phase 5 — Advanced 🏆"

def format_message(day, week, day_in_week, title, lesson):
    progress = min(100, int(day / 260 * 100))
    bars = "█" * (progress // 10) + "░" * (10 - progress // 10)
    progress_text = f"Day {day}/260  [{bars}] {progress}%"

    msg = f"""🇮🇳 **తెలుగు Daily Lesson — Day {day}**
{phase_name(week)} · Week {week} · Lesson {day_in_week}/5

─────────────────────────
**📖 Today's Topic:** {title}
─────────────────────────

**Telugu:**  {lesson['phrase']}
**Speak:**  /{lesson['translit']}/
**Meaning:** {lesson['meaning']}

**Example:**
> {lesson['example']}

💡 **Tip:** {lesson['tip']}

─────────────────────────
{progress_text}
*Keep going! Consistency beats intensity. నువ్వు చేయగలవు! (You can do it!)*"""
    return msg

def save_lesson_log(day, week, day_in_week, title, lesson, msg):
    """Append today's lesson to a markdown log file for git history."""
    log_dir = Path(__file__).parent / "lessons"
    log_dir.mkdir(exist_ok=True)
    date_str = datetime.date.today().isoformat()
    log_file = log_dir / f"{date_str}.md"
    content = f"""# Telugu Lesson — Day {day} ({date_str})

**Week {week} · Lesson {day_in_week}/5 · {title}**

- **Telugu:** {lesson['phrase']}
- **Speak:** /{lesson['translit']}/
- **Meaning:** {lesson['meaning']}
- **Example:** {lesson['example']}
- **Tip:** {lesson['tip']}
"""
    log_file.write_text(content, encoding="utf-8")

def main():
    state = load_state()
    day = state["day"]
    week, day_in_week, title, lesson = get_lesson(day)
    msg = format_message(day, week, day_in_week, title, lesson)
    print(msg)
    # Save lesson log for git
    save_lesson_log(day, week, day_in_week, title, lesson, msg)
    # Advance to next day
    state["day"] = day + 1
    save_state(state)

if __name__ == "__main__":
    main()
