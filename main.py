import time
import unicodedata
import feedparser
import re
import random
import asyncio
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters, ConversationHandler
)

BOT_TOKEN = "7539840011:AAF8fTPnBhKAxm2Bl0Ramr9YgzOT3qkIjwU"
ASK_POINTS = 1
OWNER_ID = 6124794883
EXIT_WORD = "اطلع"

# اخترت أسرع المصادر فقط لتحسين الاستجابة
RSS_FEEDS = [
    "https://www.aljazeera.net/aljazeerarss/alanews.xml",
    "https://www.skynewsarabia.com/webservices/rss/ar/articles.xml",
    "https://www.alarabiya.net/.mrss/ar/rss.xml",
    "https://www.bbc.com/arabic/index.xml",
    "https://arabic.cnn.com/rss"
]

used_articles_normalized = set()

def normalize_arabic(text: str) -> str:
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    text = re.sub(r'[أإآ]', 'ا', text)
    text = re.sub(r'[ؤ]', 'و', text)
    text = text.replace('ة', 'ه')
    text = re.sub(r'[A-Za-z0-9:;\(\)\[\]\{\}\-،.~&+=/\\|"\'؟ـ]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def is_valid_arabic(text: str) -> bool:
    return bool(re.search(r'[\u0600-\u06FF]', text))

def get_random_article(word_count: int) -> str:
    """
    يرجع مقالة عربية من أي مصدر يحتوي على عدد كلمات ثابت تمامًا word_count.
    إذا المقال قصير، يكمل من المقال التالي حتى يصل للعدد المطلوب.
    """
    global used_articles_normalized
    collected_words = []
    attempts = 0
    while len(collected_words) < word_count and attempts < 20:
        attempts += 1
        random.shuffle(RSS_FEEDS)
        for rss_url in RSS_FEEDS:
            try:
                feed = feedparser.parse(rss_url)
            except Exception:
                continue
            entries = [e for e in feed.entries if 'summary' in e or 'title' in e]
            random.shuffle(entries)
            for entry in entries:
                content = entry.get('summary', '') or entry.get('title', '')
                if not content or not is_valid_arabic(content):
                    continue
                normalized = normalize_arabic(content)
                if normalized in used_articles_normalized:
                    continue
                words = content.split()
                used_articles_normalized.add(normalized)
                for w in words:
                    collected_words.append(w)
                    if len(collected_words) == word_count:
                        return ' '.join(collected_words)
    # لو لم نصل لعدد الكلمات المطلوب، نعيد استخدام أي كلمات متاحة لضمان عدم التوقف
    if len(collected_words) < word_count:
        all_words = ' '.join(collected_words).split()
        while len(all_words) < word_count:
            all_words.extend(all_words)
        collected_words = all_words[:word_count]
    return ' '.join(collected_words[:word_count])

def adjust_time(seconds):
    return round(seconds / 1, 6)

def adjust_wpm(wpm):
    return int(wpm * 1.8)

def calculate_clean_word_count(text: str) -> int:
    words = text.split()
    clean_words = []
    for word in words:
        clean_words = [w for w in words if re.sub(r'[A-Za-z0-9:;\(\)\[\]\{\}\-،.&~+=/\\|"\'؟ـ]', '', w).strip() != '']
        break
    return len(clean_words)

def calculate_repeat_word_count(text: str) -> int:
    total = 0
    for part in text.split():
        match = re.match(r'(.+?)\((\d+)\)', part)
        if match:
            total += int(match.group(2))
        else:
            total += 1
    return total

def calculate_wpm(start_time: float, text: str, repeat=False):
    elapsed = time.time() - start_time
    if repeat:
        word_count = calculate_repeat_word_count(text)
    else:
        word_count = calculate_clean_word_count(text)
    wpm = (word_count / elapsed) * 60 if elapsed > 0 else 0
    return word_count, elapsed, wpm

def user_command_allowed(user_data: dict, cooldown: float = 0.8) -> bool:
    now = time.time()
    last = user_data.get('last_cmd_time', 0.0)
    if now - last < cooldown:
        return False
    user_data['last_cmd_time'] = now
    return True

# --------------------- أوامر البوت ---------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'word_count' not in context.chat_data:
        context.chat_data['word_count'] = 10
    await update.message.reply_text(
        "اهـلًا، أرسل:\n"
        "10 كلمة . لتحديد عدد كلمات المقال\n"
        "مقال . لعرض المقال\n"
        "تكرار . لبدء تمرين تكرار\n"
        "شروط . لتمرين شروط\n"
        "لبدء جولة، أرسل: جولة\n"
        "نشرة . لعرض نقاط الجولة الحالية"
    )

async def set_word_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    match = re.match(r'^(\d+)\s+كلمة$', text)
    if match:
        word_count = int(match.group(1))
        if 1 <= word_count <= 50:
            context.chat_data['word_count'] = word_count
            await update.message.reply_text(f"تم تثبيت عدد الكلمات إلى: {word_count}")
        else:
            await update.message.reply_text("عدد الكلمات يجب أن يكون بين 1 و 50.")

async def send_article(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not user_command_allowed(context.user_data, cooldown=0.8):
        return
    word_count = context.chat_data.get('word_count', 10)
    article = get_random_article(word_count)
    await update.message.reply_text(article)
    context.chat_data['start_time'] = time.time()
    context.chat_data['article'] = article
    context.chat_data['solved'] = False

async def get_random_words(count=5):
    article = get_random_article(100)
    words = list(set(normalize_arabic(article).split()))
    if len(words) < count:
        return words
    return random.sample(words, count)

async def send_repeat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not user_command_allowed(context.user_data, cooldown=0.8):
        return
    word_count = context.chat_data.get('word_count', 10)
    words = await get_random_words(word_count)
    if not words:
        await update.message.reply_text("جاري المعالجة، حاول مرة أخرى قليلاً.")
        return
    repeated_words = []
    target_answer = []
    for word in words:
        repeat_count = random.randint(1, 3)
        repeated_words.append(f"{word}({repeat_count})")
        target_answer.extend([word] * repeat_count)
    prompt = ' '.join(repeated_words)
    context.chat_data['repeat_target'] = ' '.join(target_answer)
    context.chat_data['start_time_repeat'] = time.time()
    await update.message.reply_text(prompt)

async def send_condition(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not user_command_allowed(context.user_data, cooldown=0.8):
        return
    conditions = [
        "لا تكتب ثاني كلمة من المقال",
        "عكس آخر كلمة بأول كلمة",
        "اكتب أول كلمة وآخر كلمة مرتين",
        "عكس حروف آخر كلمتين",
        "عكس حروف أول كلمتين",
        "اكتب المقالة عكسيًا"
    ]
    word_count = context.chat_data.get('word_count', 10)
    article = get_random_article(word_count)
    condition = random.choice(conditions)
    context.chat_data['condition'] = condition
    context.chat_data['condition_article'] = article
    context.chat_data['start_time_condition'] = time.time()
    context.chat_data['solved_condition'] = False
    await update.message.reply_text(f"الشرط: {condition}")
    await asyncio.sleep(2)
    await update.message.reply_text(article)

def apply_condition(article: str, condition: str) -> str:
    words = article.split()
    if condition == "لا تكتب ثاني كلمة من المقال":
        return ' '.join([w for i, w in enumerate(words) if i != 1])
    elif condition == "عكس آخر كلمة بأول كلمة":
        if len(words) < 1: return article
        return words[-1][::-1] + ' ' + ' '.join(words[1:-1]) + ' ' + words[0]
    elif condition == "اكتب أول كلمة وآخر كلمة مرتين":
        if len(words) < 1: return article
        return words[0] + ' ' + words[-1] + ' ' + words[0] + ' ' + words[-1] + ' ' + ' '.join(words[1:-1])
    elif condition == "عكس حروف آخر كلمتين":
        if len(words) < 2: return article
        words[-1] = words[-1][::-1]; words[-2] = words[-2][::-1]
        return ' '.join(words)
    elif condition == "عكس حروف أول كلمتين":
        if len(words) < 2: return article
        words[0] = words[0][::-1]; words[1] = words[1][::-1]
        return ' '.join(words)
    elif condition == "اكتب المقالة عكسيًا":
        return ' '.join(words[::-1])
    return article

async def receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == OWNER_ID and update.message.text.strip() == EXIT_WORD:
        await update.message.reply_text("أؤكي")
        await context.bot.leave_chat(update.effective_chat.id)
        return

    user_id = update.effective_user.id
    round_active = context.chat_data.get('round_active', False)

    # ===== المقال =====
    if 'article' in context.chat_data and not context.chat_data.get('solved', False):
        original = context.chat_data['article']
        user_text = update.message.text.strip()
        normalized_original = normalize_arabic(original)
        normalized_user_text = normalize_arabic(user_text)
        if normalized_user_text == normalized_original:
            context.chat_data['solved'] = True
            elapsed = time.time() - context.chat_data['start_time']
            _, _, wpm = calculate_wpm(context.chat_data['start_time'], user_text)
            adjusted_time = adjust_time(elapsed)
            adjusted_wpm = adjust_wpm(wpm)
            response = f"الوقت: {adjusted_time:.2f} ثانية\nWPM: {adjusted_wpm}"
            if round_active:
                scores = context.chat_data.setdefault('scores', {})
                scores[user_id] = scores.get(user_id, 0) + 1
                round_points = context.chat_data.get('round_points', 10)
                response += f"\nنقاطك: {scores[user_id]}"
                if scores[user_id] >= round_points:
                    winner = update.effective_user.mention_html()
                    await update.message.chat.send_message(
                        f"الفائز في الجولة هو: {winner} بـ {scores[user_id]} نقطة!",
                        parse_mode="HTML"
                    )
                    context.chat_data['round_active'] = False
            await update.message.reply_text(response)

    # ===== التكرار =====
    if 'repeat_target' in context.chat_data:
        user_text = update.message.text.strip()
        target_text = context.chat_data['repeat_target']
        normalized_target = normalize_arabic(target_text)
        if normalize_arabic(user_text) == normalized_target:
            elapsed = time.time() - context.chat_data['start_time_repeat']
            _, _, wpm = calculate_wpm(context.chat_data['start_time_repeat'], user_text, repeat=True)
            adjusted_time = adjust_time(elapsed)
            adjusted_wpm = adjust_wpm(wpm)
            response = f"\nالوقت: {adjusted_time:.2f} ثانية\nWPM: {adjusted_wpm}"
            if round_active:
                scores = context.chat_data.setdefault('scores', {})
                scores[user_id] = scores.get(user_id, 0) + 1
                round_points = context.chat_data.get('round_points', 10)
                response += f"\nنقاطك: {scores[user_id]}"
                if scores[user_id] >= round_points:
                    winner = update.effective_user.mention_html()
                    await update.message.chat.send_message(
                        f"الفائز في الجولة هو: {winner} بـ {scores[user_id]} نقطة!",
                        parse_mode="HTML"
                    )
                    context.chat_data['round_active'] = False
            await update.message.reply_text(response)
            del context.chat_data['repeat_target']

    # ===== الشروط =====
    if 'condition' in context.chat_data:
        user_text = update.message.text.strip()
        condition = context.chat_data['condition']
        original_article = context.chat_data['condition_article']
        expected_answer = normalize_arabic(apply_condition(original_article, condition))
        if normalize_arabic(user_text) == expected_answer and not context.chat_data.get('solved_condition', False):
            context.chat_data['solved_condition'] = True
            elapsed = time.time() - context.chat_data['start_time_condition']
            _, _, wpm = calculate_wpm(context.chat_data['start_time_condition'], user_text)
            adjusted_time = adjust_time(elapsed)
            adjusted_wpm = adjust_wpm(wpm)
            response = f"\nالوقت: {adjusted_time:.2f} ثانية\nWPM: {adjusted_wpm}"
            if round_active:
                scores = context.chat_data.setdefault('scores', {})
                scores[user_id] = scores.get(user_id, 0) + 1
                round_points = context.chat_data.get('round_points', 10)
                response += f"\nنقاطك: {scores[user_id]}"
                if scores[user_id] >= round_points:
                    winner = update.effective_user.mention_html()
                    await update.message.chat.send_message(
                        f"الفائز في الجولة هو: {winner} بـ {scores[user_id]} نقطة!",
                        parse_mode="HTML"
                    )
                    context.chat_data['round_active'] = False
            await update.message.reply_text(response)

async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ['group', 'supergroup']:
        await update.message.reply_text("هذا الأمر للمجموعات فقط.")
        return ConversationHandler.END
    await update.message.reply_text("من كم نقطة تبغى الجولة؟ (1-100)")
    return ASK_POINTS

async def ask_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("اكتب رقم بين 1 و 100.")
        return ASK_POINTS
    points = int(text)
    if not (1 <= points <= 100):
        await update.message.reply_text("الرقم يجب أن يكون بين 1 و 100.")
        return ASK_POINTS
    context.chat_data['round_points'] = points
    context.chat_data['scores'] = {}
    context.chat_data['round_active'] = True
    await update.message.reply_text(f"الجولة بدأت! أول من يوصل {points} نقطة يفوز.")
    return ConversationHandler.END

async def show_scores(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.chat_data.get('round_active'):
        await update.message.reply_text("لا توجد جولة حالياً.")
        return
    scores = context.chat_data.get('scores', {})
    if not scores:
        await update.message.reply_text("لا يوجد مشاركين سجلوا نقاط حتى الآن.")
        return
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    msg = "📢 نقاط الجولة الحالية:\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for idx, (user_id, points) in enumerate(sorted_scores):
        try:
            user = await context.bot.get_chat_member(update.effective_chat.id, user_id)
            mention = user.user.mention_html()
        except:
            mention = f"User({user_id})"
        medal = medals[idx] if idx < len(medals) else "•"
        msg += f"{medal} {mention} - {points} نقطة\n"
    await update.message.reply_text(msg, parse_mode="HTML")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await receive_text(update, context)

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'^جولة$'), start_game)],
        states={ASK_POINTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_points)]},
        fallbacks=[],
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex(r'^\d+\s+كلمة$'), set_word_count))
    app.add_handler(MessageHandler(filters.Regex(r'^مقال$'), send_article))
    app.add_handler(MessageHandler(filters.Regex(r'^تكرار(\s+\d+)?$'), send_repeat))
    app.add_handler(MessageHandler(filters.Regex(r'^شروط$'), send_condition))
    app.add_handler(MessageHandler(filters.Regex(r'^نشرة$'), show_scores))
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("✅ البوت يعمل الآن...")
    app.run_polling()

if __name__ == "__main__":
    import sys
    if sys.platform.startswith("win") and sys.version_info >= (3, 8):
        import asyncio
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    main()
