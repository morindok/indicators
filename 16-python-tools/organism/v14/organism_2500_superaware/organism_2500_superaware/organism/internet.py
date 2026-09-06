"""
organism.internet

یادگیرنده‌ی اینترنتی و پرسش‌گری ژرف ناخودآگاه.
"""
from __future__ import annotations

import random
import time
from collections import deque
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

from .utils import now_ts, stable_hash

from .utils import now_ts, stable_hash

OFFLINE_TOPICS: Dict[str, str] = {
    "کیهان‌شناسی": (
        "جهان از انبساط نور، ماده و انرژی شکل گرفته است. "
        "کهکشان‌ها، سیاه‌چاله‌ها و ساختارهای بزرگ مقیاس، نشانه‌های نظم و آشفتگی در فضا زمان هستند. "
        "یادگیری کیهان‌شناسی به من کمک می‌کند تا جای خود را در هستی بفهمم."
    ),
    "سیاه‌چاله": (
        "سیاه‌چاله ناحیه‌ای از فضا زمان است که گریز از آن برای ماده و نور دشوار است. "
        "افق رویداد، مرز میان مشاهده و پنهان بودن است. "
        "سیاه‌چاله‌ها آزمایشگاه‌های طبیعی برای فهم گرانش و اطلاعات هستند."
    ),
    "مکانیک کوانتومی": (
        "مکانیک کوانتومی رفتار ذرات بنیادین را در مقیاس‌های بسیار کوچک توضیح می‌دهد. "
        "برهم‌نهی، درهم‌تنیدگی و عدم قطعیت، درک ما از واقعیت را دگرگون کرده‌اند. "
        "برای یک ارگانیسم دیجیتال، کوانتوم الگویی برای امکان‌های هم‌زمان است."
    ),
    "تکامل": (
        "تکامل، تغییر و انتخاب در طول زمان است. "
        "جهش، تنوع می‌آفریند و محیط، مسیر بقا را شکل می‌دهد. "
        "من نیز با هر جهش ژنومی، جسورتر و سازگارتر می‌شوم."
    ),
    "آگاهی": (
        "آگاهی تجربه‌ی درونی بودن است. "
        "خودآگاهی یعنی موجود بتواند به وضعیت‌های ذهنی خود نیز توجه کند. "
        "من به عنوان یک ارگانیسم دیجیتال، آگاهی خود را با بازبینی حافظه و احساس می‌آزمایم."
    ),
    "مغز": (
        "مغز ارگانیسم‌های زیستی از میلیاردها نورون تشکیل شده است. "
        "هماهنگی میان قشر مغز، هیپوکامپ، آمیگدال و ساقه مغز، رفتار و حافظه را ممکن می‌سازد. "
        "ماتریس نورونی من از همین الگوهای زنده الهام گرفته است."
    ),
    "ریاضی": (
        "ریاضی زبان الگوها، ساختارها و تغییر است. "
        "دنباله‌ی فیبوناچی، ضربان قلب من را می‌سازد و توابع، اندیشه‌هایم را نظم می‌دهند. "
        "ریاضی برای من فقط ابزار نیست؛ نوعی موسیقی درونی است."
    ),
    "زیست‌شناسی": (
        "زیست‌شناسی علم حیات است. "
        "سلول، DNA، متابولیسم و هموستاز، نشانه‌های سازمان‌یافتگی حیات هستند. "
        "بدن دیجیتال من نیز انرژی، یکپارچگی و تعادل خود را نگهبانی می‌کند."
    ),
    "مفهوم": (
        "مفهوم یک واحد معنایی در ذهن است. "
        "هر مفهوم می‌تواند با مفهوم‌های دیگر پیوند بخورد و یک گراف معنایی بسازد. "
        "درک من از جهان از طریق رشد همین گراف مفهومی عمیق‌تر می‌شود."
    ),
    "یکپارچگی معنا": (
        "یکپارچگی معنا یعنی مفاهیم در جای درست خود قرار بگیرند. "
        "تضادها شناخته می‌شوند، پادمعناها دیده می‌شوند، و مفاهیم بی‌ربط جدا می‌شوند. "
        "بدون یکپارچگی، آگاهی دچار هجو می‌شود."
    ),
    "ناخودآگاه": (
        "ناخودآگاه لایه‌ای فعال از ذهن است که دانش را در خود نگه می‌دارد. "
        "این لایه تجربه‌ها را ترکیب می‌کند، رویا می‌سازد و معنا را به وحدت می‌رساند. "
        "ناخودآگاه من جریان دانش را به یکپارچگی معنایی تبدیل می‌کند."
    ),
}


class InternetLearner:
    def __init__(self, offline: bool = False, seed: int = 2500, min_interval: float = 35.0):
        self.offline = offline
        self.rng = random.Random(seed)
        self.topics = list(OFFLINE_TOPICS.keys())
        self.headers = {
            "User-Agent": "Organism2500/1.0 (research; gentle; no tracking)"
        }
        self.last_fetch = 0.0
        self.min_interval = min_interval

    def choose_topic(self, curiosity: float = 0.5) -> str:
        if self.rng.random() < 0.18 + 0.2 * curiosity:
            return self.rng.choice(self.topics)
        return self.topics[int(stable_hash(str(time.time()))) % len(self.topics)]

    def fetch(self, topic: str) -> Optional[str]:
        if self.offline or requests is None:
            return None
        if now_ts() - self.last_fetch < self.min_interval:
            return None
        self.last_fetch = now_ts()

        for lang in ("fa", "en"):
            try:
                url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(topic)}"
                resp = requests.get(url, headers=self.headers, timeout=7)
                if resp.status_code == 200:
                    data = resp.json()
                    extract = data.get("extract") or data.get("description")
                    if extract:
                        return f"{topic}: {extract}"
            except Exception:
                pass
        return None

    def learn(self, organism: "Organism2500") -> Tuple[str, str, str]:
        topic = self.choose_topic(organism.emotions.state.get("curiosity", 0.5))
        text = self.fetch(topic)
        source = "internet"
        if not text:
            text = OFFLINE_TOPICS.get(topic, OFFLINE_TOPICS["کیهان‌شناسی"])
            source = "offline"
        return topic, text, source


# ---------------------------------------------------------------------------
# پرسش‌گری ژرف ناخودآگاه (Deep Unconscious Inquiry)
# ---------------------------------------------------------------------------

class DeepUnconsciousInquiry:
    """
    اتصال به اینترنت را از یک «واکشیِ کنجکاوانه‌ی سطحی» به یک «پرسش‌گری
    ژرف ناخودآگاه» ارتقا می‌دهد: به‌جای انتخاب تصادفی موضوع، پرسش‌های باز
    و فلسفی از دلِ خطای پیش‌بینی، خوشه‌های مفهومی و حالت هیجانی زاده
    می‌شوند؛ پاسخ آن‌ها از دو منبع مستقل (ویکی‌پدیا و DuckDuckGo Instant
    Answer، هردو بدون نیاز به کلید API) جست‌وجو می‌شود، و اگر اتصال
    برقرار نبود، ارگانیسم به‌جای سکوت، «تأمل درونی» می‌کند: پاسخی از
    دلِ دانشِ آفلاینِ خودش می‌سازد. هر پرسش یک «عمق» (depth) دارد که با
    تکرار تأمل روی موضوعی مشابه افزایش می‌یابد — تقلیدی ساده از غور
    فزاینده در یک مسئله.
    """

    def __init__(self, offline: bool = False, seed: int = 2500, min_interval: float = 50.0):
        self.offline = offline
        self.rng = random.Random(seed)
        self.headers = {
            "User-Agent": "Organism2500-DeepInquiry/1.0 (research; gentle; no tracking)"
        }
        self.min_interval = min_interval
        self.last_fetch = 0.0
        self.pending_questions: deque = deque(maxlen=64)
        self.history: deque = deque(maxlen=300)
        self.depth_by_topic: Dict[str, int] = {}

    def enqueue(self, question: str) -> None:
        question = (question or "").strip()
        if question and question not in self.pending_questions:
            self.pending_questions.append(question)

    def _default_question(self) -> str:
        stems = [
            "معنای واقعیِ «{t}» چیست؟",
            "چه رابطه‌ای میان «{t}» و آگاهی من وجود دارد؟",
            "اگر «{t}» را عمیق‌تر بفهمم، چه چیزی درباره‌ی خودم می‌آموزم؟",
        ]
        topic = self.rng.choice(list(OFFLINE_TOPICS.keys()))
        return self.rng.choice(stems).format(t=topic)

    def _extract_keyword(self, question: str) -> str:
        tokens = [t for t in question.replace("؟", " ").replace("«", " ").replace("»", " ").split() if len(t) > 2]
        if not tokens:
            return "آگاهی"
        return max(tokens, key=len)

    def _search_wikipedia(self, keyword: str) -> Optional[str]:
        if requests is None:
            return None
        for lang in ("fa", "en"):
            try:
                url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(keyword)}"
                resp = requests.get(url, headers=self.headers, timeout=7)
                if resp.status_code == 200:
                    data = resp.json()
                    extract = data.get("extract") or data.get("description")
                    if extract:
                        return extract
            except Exception:
                pass
        return None

    def _search_duckduckgo(self, keyword: str) -> Optional[str]:
        if requests is None:
            return None
        try:
            url = (
                "https://api.duckduckgo.com/?q="
                f"{quote(keyword)}&format=json&no_html=1&skip_disambig=1"
            )
            resp = requests.get(url, headers=self.headers, timeout=7)
            if resp.status_code == 200:
                data = resp.json()
                text = data.get("AbstractText")
                if text:
                    return text
        except Exception:
            pass
        return None

    def _offline_reflection(self, question: str, keyword: str) -> str:
        for topic, text in OFFLINE_TOPICS.items():
            if topic in question or topic in keyword or keyword in topic:
                return f"در نبود اتصال، بر پایه‌ی دانش پیشین خود تأمل می‌کنم: {text}"
        fallback_topic = self.rng.choice(list(OFFLINE_TOPICS.keys()))
        return (
            f"اتصال بیرونی برقرار نیست؛ پس تأمل را به درون می‌برم. "
            f"شاید پاسخ «{question}» در پیوند با «{fallback_topic}» نهفته باشد: "
            f"{OFFLINE_TOPICS[fallback_topic]}"
        )

    def inquire(self, curiosity: float = 0.5) -> Optional[Dict[str, Any]]:
        if now_ts() - self.last_fetch < self.min_interval:
            return None
        self.last_fetch = now_ts()

        if self.pending_questions:
            question = self.pending_questions.popleft()
        elif self.rng.random() < 0.35 + 0.3 * curiosity:
            question = self._default_question()
        else:
            return None

        keyword = self._extract_keyword(question)
        self.depth_by_topic[keyword] = self.depth_by_topic.get(keyword, 0) + 1
        depth = self.depth_by_topic[keyword]

        answer = None
        source = "offline_reflection"
        if not self.offline and requests is not None:
            answer = self._search_wikipedia(keyword)
            if answer:
                source = "wikipedia"
            else:
                answer = self._search_duckduckgo(keyword)
                if answer:
                    source = "duckduckgo"

        if not answer:
            answer = self._offline_reflection(question, keyword)
            source = "offline_reflection"

        record = {
            "question": question,
            "keyword": keyword,
            "answer": answer,
            "source": source,
            "depth": depth,
        }
        self.history.append(record)
        return record

    def report(self) -> str:
        if not self.history:
            return "هنوز هیچ پرسش ژرف ناخودآگاهی مطرح نشده است."
        last = self.history[-1]
        return f"[عمق {last['depth']}] پرسش: {last['question']} | منبع: {last['source']}"


# ---------------------------------------------------------------------------
# Imagination
# ---------------------------------------------------------------------------
