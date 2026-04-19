# 🤖 Habit & Budget Tracker Bot

O'zbek tilida ishlaydigan, AI bilan kuchaytirilgan Telegram bot: kundalik odatlar va budjetni kuzatish uchun. Gemini AI matn va ovozli xabarlarni tushunadi, Excel/PDF hisobotlar tayyorlaydi, **manual to'lov orqali Premium** obuna tizimi mavjud.

---

## ✨ Asosiy imkoniyatlar

### 🆓 Bepul tarif
- Matn orqali odat va xarajat qo'shish
- Kuniga 10 tagacha log
- Kunlik xulosa (21:00)
- Haftalik hisobot (Yakshanba 20:00)
- 7 kungacha Excel hisobot

### 💎 Premium tarif
- **Cheksiz** log
- 🎤 Ovozli xabarlar (Gemini orqali transkripsiya)
- 📄 PDF hisobot — grafik va tahlillar bilan
- 📅 Istalgan sana oralig'ida hisobot
- 📊 Kengaytirilgan statistika, streak tracking
- 🔔 Obuna tugash ogohlantirishlari

### 👮 Admin imkoniyatlari
- **Manual to'lov tasdiqlash** — admin guruhida tugmalar orqali
- `/admin` panel: DAU/WAU statistika, daromad, kutilayotgan to'lovlar
- Broadcast yuborish
- User qidirish va boshqarish (ban/unban/Premium hadya)

---

## 🏗 Arxitektura

```
habit_bot/
├── bot/
│   ├── main.py                  # Entry point
│   ├── config.py                # Environment config
│   ├── database/
│   │   └── schema.sql           # Supabase schema
│   ├── handlers/                # Telegram handlers
│   │   ├── start.py
│   │   ├── messages.py          # Matn + ovoz parsing
│   │   ├── reports.py           # /report
│   │   ├── settings.py          # /settings, /reset
│   │   ├── subscription.py      # /premium user flow
│   │   ├── admin_approval.py    # Admin group tasdiqlash
│   │   └── admin_panel.py       # /admin panel
│   ├── services/
│   │   ├── ai_service.py        # Gemini integration
│   │   ├── fast_parser.py       # Regex parser (70% AI'ni tejaydi)
│   │   ├── db_service.py        # Async Supabase wrapper
│   │   ├── cache_service.py     # TTL cache
│   │   ├── excel_service.py     # Excel generation
│   │   ├── pdf_service.py       # PDF + chartlar
│   │   ├── subscription_service.py
│   │   ├── analytics_service.py
│   │   └── scheduler.py         # Cron: kunlik/haftalik/oylik
│   ├── middlewares/
│   │   ├── throttling.py        # Anti-spam
│   │   ├── user_context.py      # Auto-register
│   │   └── error.py             # Global error handler
│   ├── keyboards/               # Inline klaviaturalar
│   ├── states/                  # FSM holatlar
│   └── utils/                   # Logger, formatters, validators, decorators
├── .env.example
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## 🚀 O'rnatish

### 1. Reponi klonlash
```bash
git clone <your-repo-url> habit_bot
cd habit_bot
```

### 2. Supabase loyihasi
1. [supabase.com](https://supabase.com) ga kiring va yangi **project** oching
2. **Settings → API** bo'limidan `URL` va `service_role` key ni oling
3. **SQL Editor** ga o'ting va `bot/database/schema.sql` tarkibini nusxalab bajaring

### 3. Telegram bot token
1. [@BotFather](https://t.me/BotFather) ga yozing
2. `/newbot` → bot nomi va username tanlang
3. HTTP API token ni saqlang

### 4. Admin guruh yaratish
1. Telegram'da **yangi private group** yarating
2. Yaratgan botingizni guruhga qo'shing va **admin** qiling
3. Guruhda har qanday xabar yozing
4. Guruh ID ni olish uchun vaqtincha [@username_to_id_bot](https://t.me/username_to_id_bot) ni qo'shib, `/id` yozing
5. ID odatda `-100XXXXXXXXXX` ko'rinishida bo'ladi — uni `.env` ga yozing
6. Yordamchi botni o'chiring

### 5. Gemini API key
1. [Google AI Studio](https://aistudio.google.com/app/apikey) ga kiring
2. **Create API Key** bosing
3. Kalit'ni saqlang

### 6. Environment sozlash
```bash
cp .env.example .env
```

`.env` faylini ochib to'ldiring:
```bash
BOT_TOKEN=7XXX:AAAA...
GEMINI_API_KEY=AIza...
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJhbGc...

ADMIN_IDS=123456789                    # Sizning Telegram ID
ADMIN_GROUP_ID=-1001234567890          # Admin guruh ID

PAYMENT_CARD_NUMBER=8600 1234 5678 9012
PAYMENT_CARD_HOLDER=ABDULAZIZ KARIMOV
PAYMENT_CLICK_PHONE=+998901234567
PAYMENT_PAYME_PHONE=+998901234567
```

Sizning Telegram ID ni olish uchun [@userinfobot](https://t.me/userinfobot) ga `/start` yozing.

### 7. Virtual muhit va botni ishga tushirish
```bash
python3.11 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m bot.main
```

Botingiz ishlayotganini tekshiring — Telegram'da botingizga `/start` yozing.

---

## 🐳 Docker orqali deployment

### Local Docker
```bash
docker-compose up -d --build
docker-compose logs -f
```

### Railway / Fly.io / DigitalOcean
1. Reponi GitHub ga push qiling
2. Railway/Fly da yangi project oching
3. `.env` faylidagi barcha o'zgaruvchilarni Environment Variables bo'limiga nusxalang
4. Deploy — `Dockerfile` avtomatik aniqlanadi

### Webhook rejim (ixtiyoriy, Render/Railway uchun)
`.env` da:
```
WEBHOOK_URL=https://your-domain.com
WEBAPP_PORT=8080
```
va `docker-compose.yml` da port mapping'ni yoqing.

---

## 🎛 Foydalanish

### Oddiy user
```
/start             — botni boshlash
/habits            — bugungi odatlar
/budget            — budjet xulosasi
/report            — Excel/PDF hisobot
/premium           — Premium obuna
/settings          — sozlamalar
/reset             — barcha ma'lumotni o'chirish
```

**Matn misollari:**
- "Bugun 30 daqiqa yugurdim"
- "Taksiga 25 ming to'ladim"
- "Maosh 3 mln so'm keldi"
- "Kitob 2 soat o'qidim"

### Admin
```
/admin             — admin panel (statistika, broadcast, user qidirish)
```

**To'lov tasdiqlash oqimi:**
1. User `/premium` → plan tanlaydi → chek yuboradi
2. Bot admin guruhga chekni yuboradi + ✅ / ❌ tugmalar
3. Admin tugma bosadi → user avtomatik xabar oladi

---

## 🔧 Konfiguratsiya

### Narxlarni o'zgartirish
`.env` faylida:
```
PRICE_1_MONTH=50000
PRICE_3_MONTHS=135000
PRICE_6_MONTHS=250000
```

### Eslatma vaqtlarini o'zgartirish
```
DAILY_REMINDER_HOUR=21            # Kunlik (21:00)
WEEKLY_REPORT_WEEKDAY=6           # Yakshanba (0=Du, 6=Ya)
WEEKLY_REPORT_HOUR=20
MONTHLY_REPORT_DAY=1              # Oyning 1-kuni
MONTHLY_REPORT_HOUR=9
```

### Free tier limitlarni o'zgartirish
```
FREE_DAILY_LOG_LIMIT=10
FREE_REPORT_MAX_DAYS=7
```

---

## 🧪 Xato aniqlash

### Log qatorlari
```bash
docker-compose logs -f bot        # Docker
tail -f logs.txt                   # Bare metal (agar redirect qilgan bo'lsangiz)
```

### Eng ko'p uchraydigan xatolar

| Xato | Sabab | Yechim |
|---|---|---|
| `Missing required env variable` | `.env` to'liq emas | Hamma majburiy o'zgaruvchilarni to'ldiring |
| `ADMIN_GROUP_ID not configured` | Guruh ID `0` | To'g'ri guruh ID ni yozing |
| `Bot is not a member of the group` | Bot guruhga qo'shilmagan | Botni guruhga admin qiling |
| `Supabase connection failed` | URL/key noto'g'ri | Supabase Settings → API ni tekshiring |
| Voice ishlamaydi | `ffmpeg` o'rnatilmagan | `apt install ffmpeg` yoki Docker'da ishlating |

### Supabase bilan bog'lanishni sinash
```python
from bot.services.db_service import db
import asyncio
print(asyncio.run(db.count_users()))
```

---

## 🧠 AI va Fast Parser

Bot **ikki bosqichli** parsing ishlatadi:

1. **Fast parser** (`fast_parser.py`) — regex orqali umumiy xabarlarni aniqlaydi
   - "Taksiga 25 ming" → transport, 25000 UZS
   - "30 daqiqa yugurdim" → Yugurish, 30 min
   - **~70% xabarlarni Gemini'siz tushunadi** → tezroq + arzon

2. **Gemini fallback** — fast parser ishonchsiz bo'lsa
   - JSON format, temperature=0.1
   - Model: `gemini-2.0-flash`

Bu arxitektura bitta xabar uchun Gemini chaqirig'ini **0.0001$** atrofida ushlab turadi.

---

## 📊 Obuna holati ma'lumotlar oqimi

```
User → /premium → plan tanlaydi → chek yuboradi
                                    ↓
                    payment_requests (status: pending)
                                    ↓
              Admin guruhga forward + tugmalar
                                    ↓
                ┌───────────────┴───────────────┐
        ✅ Approve                        ❌ Reject
        ↓                                   ↓
    subscriptions (premium)         Sabab so'raladi
    User xabar oladi                User xabar oladi
```

---

## 🔐 Xavfsizlik

- **Rate limiting** — har userga daqiqada 20 ta xabar
- **Anti-spam** — faqat bir marta ogohlantirish
- **FSM holat** — noto'g'ri yo'ldan boshqaruvni cheklaydi
- **Admin group isolation** — admin faqat belgilangan guruhda ishlaydi
- **User validation** — barcha input'lar sanitizatsiya qilinadi
- **Non-root Docker** — `botuser` UID 1000
- **Ban tizimi** — suiiste'mol uchun user bloklanadi

---

## 🛠 Texnik detallar

- **Python:** 3.11+
- **Framework:** aiogram 3.x (async)
- **DB:** Supabase PostgreSQL (via `supabase-py`, async wrapper)
- **AI:** Google Gemini 2.0 Flash
- **Scheduler:** APScheduler (cron)
- **Audio:** pydub + ffmpeg
- **Reports:** openpyxl (Excel), reportlab + matplotlib (PDF)
- **Cache:** cachetools TTL (in-memory)

---

## 📝 To-Do / Kelgusi versiyalar

- [ ] OCR orqali chek avtomatik tekshirish
- [ ] Payme/Click API integratsiyasi (avtomatik to'lov)
- [ ] Budjet limit ogohlantirish (premium)
- [ ] Custom kategoriyalar (premium)
- [ ] Web dashboard (Next.js)
- [ ] Multilingual (o'zbek + rus + ingliz)

---

## 📄 Litsenziya

MIT License. O'zgartirib, qayta foydalanishingiz mumkin.

---

## 🙏 Muallif

**Bot by:** _Your Name_ · [@your_telegram](https://t.me/your_telegram)

Muammo bo'lsa Issues oching yoki admin bilan bog'laning.
