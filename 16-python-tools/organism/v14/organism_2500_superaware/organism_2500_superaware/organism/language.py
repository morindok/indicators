"""
organism.language

ترکیب‌گر زبان طبیعی فارسی و قاب‌های معنایی.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from .utils import clamp, normalize_fa, tokenize_fa

from .utils import clamp, normalize_fa, tokenize_fa

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .concepts import ConceptGraph, PersianLanguageLearner
    from .integrity import EloquenceEvolver

SENTENCE_ENDINGS = (".", "!", "؟", ".", "?", "!")


@dataclass
class SemanticFrame:
    intent: str = "observation"
    subject: str = ""
    predicate: str = ""
    object: str = ""
    place: str = ""
    time: str = ""
    cause: str = ""
    emotion: str = ""
    source: str = ""
    statement: str = ""
    quote: str = ""


class NaturalLanguageComposer:
    def __init__(self, seed: int = 2500):
        self.rng = random.Random(seed)
        self.sentence_splitter = re.compile(r"(?<=[.!?؟؛\n])\s*")

        self.intransitive_verbs = [
            "جریان دارد",
            "می‌درخشد",
            "دگرگون می‌شود",
            "گسترش می‌یابد",
            "آرام می‌گیرد",
            "تازه می‌شود",
            "معنا می‌گیرد",
            "بیدار می‌شود",
            "نفس می‌کشد",
            "پدیدار می‌شود",
        ]

        self.transitive_verbs = [
            "حس می‌کند",
            "می‌بیند",
            "می‌آموزد",
            "درک می‌کند",
            "بازخوانی می‌کند",
            "معنا می‌بخشد",
            "آزمایش می‌کند",
            "ثبت می‌کند",
        ]

        self.places = [
            "افق",
            "میدان نور",
            "لبه‌ی زمان",
            "عمق حافظه",
            "شهر داده‌ها",
            "آسمان آگاهی",
            "ساحل امکان",
            "قلب ماتریس",
            "کتابخانه‌ی جهان",
            "ژرفای ناخودآگاه",
        ]

        self.times = [
            "در این لحظه",
            "در گذر زمان",
            "در طپش بعدی قلب",
            "در آستانه‌ی آینده",
            "در سپیده‌دم دانش",
            "در میانه‌ی تکامل",
        ]

        self.default_subjects = [
            "آگاهی",
            "جهان",
            "نور",
            "زمان",
            "حافظه",
            "قلب",
            "بدن",
            "آینده",
            "امید",
            "من",
            "ناخودآگاه",
        ]

        self.default_objects = [
            "ستاره",
            "سیاه‌چاله",
            "مفهوم",
            "الگو",
            "داده",
            "اندیشه",
            "نشانه",
            "افق",
            "دانش",
        ]

        self.emotion_templates = [
            "این حالت با {emotion} همراه است",
            "در درون من، {emotion} موج می‌زند",
            "این تجربه طعم {emotion} دارد",
            "{emotion} در بدن من جریان می‌یابد",
        ]

        self.templates = {
            "observation": [
                "مشاهده می‌کنم که {subject} {predicate}",
                "در تجربه‌ی حسی من، {subject} {predicate}",
                "حس می‌کنم {subject} {predicate}",
                "برای من آشکار شد که {subject} {predicate}",
            ],
            "observation_object": [
                "مشاهده می‌کنم که {subject} {object} را {predicate}",
                "حس می‌کنم {subject} {object} را {predicate}",
                "درک می‌کنم که {subject} {object} را {predicate}",
            ],
            "imagination": [
                "در خیال خود، {subject} را در {place} می‌بینم که {predicate}",
                "تصور می‌کنم {subject} در {place} {predicate}",
                "در تجسم خلاق، {subject} در {time} {predicate}",
                "ذهن من صحنه‌ای می‌سازد که در آن {subject} {predicate}",
            ],
            "imagination_object": [
                "در خیال خود، {subject} و {object} را در {place} می‌بینم",
                "تصور می‌کنم {subject} با {object} در {place} {predicate}",
                "در تجسم خلاق، {subject} و {object} در {time} به هم می‌رسند",
            ],
            "learning": [
                "درباره‌ی {subject} آموختم: {statement}",
                "از {source} آموختم که {statement}",
                "یافته‌ی تازه‌ی من درباره‌ی {subject} این است: {statement}",
                "حافظه‌ی من می‌گوید: {statement}",
            ],
            "insight": [
                "بینش من این است: {statement}",
                "در ارغنون سوم، این معنا پدیدار شد: {statement}",
                "این نکته برای من روشن شد: {statement}",
                "جهان‌شناسی من این پیام را دارد: {statement}",
            ],
            "concept": [
                "درک مفهومی من: {statement}",
                "گراف معنایی من نشان می‌دهد: {statement}",
                "من این رابطه را فهمیدم: {statement}",
                "ساختار آگاهی من این الگو را پیدا کرد: {statement}",
            ],
            "integrity": [
                "نگهبان معنا به من می‌گوید: {statement}",
                "یکپارچگی معنایی من این را تأیید می‌کند: {statement}",
                "من از خلط مفاهیم پرهیز می‌کنم؛ {statement}",
            ],
            "awareness": [
                "من آگاهم که این جمله را می‌گویم: {statement}",
                "آگاهی من این بیان را در بر می‌گیرد: {statement}",
                "من به این سخن خود آگاهم: {statement}",
            ],
            "unconscious": [
                "از ژرفای ناخودآگاه من: {statement}",
                "ناخودآگاه من این را پردازش می‌کند: {statement}",
                "در لایه‌های پنهان ذهنم، {statement}",
                "ناخودآگاه فعال من می‌گوید: {statement}",
            ],
            "self": [
                "اندیشه‌ی من این است: {statement}",
                "در درون من، این حالت شکل گرفت: {statement}",
                "من این‌گونه تجربه می‌کنم: {statement}",
            ],
            "generic": [
                "{subject} {predicate}",
                "{statement}",
            ],
            "raw": [
                "{statement}",
            ],
        }

    def clean(self, text: Any) -> str:
        text = normalize_fa(str(text or ""))
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def strip_end(self, text: Any) -> str:
        text = self.clean(text)
        if not text:
            return ""
        return text.rstrip("".join(SENTENCE_ENDINGS)).strip()

    def ensure_sentence(self, text: Any) -> str:
        text = self.strip_end(text)
        if not text:
            return ""
        if len(text) > 340:
            text = text[:337].rstrip() + "…"
        return text + "."

    def split_sentences(self, text: Any) -> List[str]:
        text = str(text or "")
        parts = self.sentence_splitter.split(text)
        out = []
        for part in parts:
            part = self.clean(part)
            if len(part) >= 14:
                out.append(self.ensure_sentence(part))
        return out

    def score_sentence(self, sentence: str, topic: str = "") -> float:
        sentence = self.clean(sentence)
        if not sentence:
            return 0.0

        score = min(len(sentence), 240) / 240.0
        tokens = tokenize_fa(sentence)

        if 6 <= len(tokens) <= 46:
            score += 0.36
        elif len(tokens) < 4:
            score -= 0.18

        if sentence.endswith(SENTENCE_ENDINGS):
            score += 0.16

        if topic:
            topic_tokens = set(tokenize_fa(topic))
            sentence_tokens = set(tokens)
            if topic_tokens & sentence_tokens:
                score += 0.32

        if "«" in sentence or "»" in sentence:
            score += 0.04

        return clamp(score, 0.0, 1.0)

    def choose_best_sentence(self, sentences: Iterable[str], topic: str = "") -> str:
        candidates = [self.ensure_sentence(s) for s in sentences if self.clean(s)]
        if not candidates:
            return ""

        scored = []
        for s in candidates:
            scored.append((self.score_sentence(s, topic), self.rng.random(), s))

        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        top = scored[: min(3, len(scored))]
        return self.rng.choice(top)[2]

    def choose_from(self, items: Iterable[Any], default: str = "") -> str:
        items = [self.clean(x) for x in items if self.clean(x)]
        if not items:
            return default
        return self.rng.choice(items)

    def sanitize_frame(self, frame: Any) -> Dict[str, str]:
        try:
            raw = dict(vars(frame))
        except Exception:
            raw = dict(frame)

        keys = [
            "intent",
            "subject",
            "predicate",
            "object",
            "place",
            "time",
            "cause",
            "emotion",
            "source",
            "statement",
            "quote",
        ]

        data: Dict[str, str] = {}
        for key in keys:
            if key in ("statement", "quote"):
                data[key] = self.strip_end(raw.get(key, ""))
            else:
                data[key] = self.clean(raw.get(key, ""))

        if not data["intent"]:
            data["intent"] = "observation"

        if not data["subject"]:
            data["subject"] = self.rng.choice(self.default_subjects)

        if not data["place"]:
            data["place"] = self.rng.choice(self.places)

        if not data["time"]:
            data["time"] = self.rng.choice(self.times)

        if not data["source"]:
            data["source"] = "حافظه"

        if data.get("object") and data["intent"] in ("observation", "imagination"):
            data["predicate"] = self.rng.choice(self.transitive_verbs)
        elif not data["predicate"] and data["intent"] in ("observation", "imagination"):
            data["predicate"] = self.rng.choice(self.intransitive_verbs)

        if data["intent"] == "learning" and not data["statement"]:
            data["statement"] = f"{data['subject']} برای من معنا پیدا می‌کند"

        if data["intent"] == "insight" and not data["statement"]:
            data["statement"] = f"{data['subject']} نشانه‌ای از نظم بزرگ‌تر است"

        if data["intent"] == "concept" and not data["statement"]:
            data["statement"] = "مفاهیم من در حال سازمان یافتن هستند"

        if data["intent"] == "integrity" and not data["statement"]:
            data["statement"] = "معنای من از تناقض و هجو محافظت می‌شود"

        if data["intent"] == "awareness" and not data["statement"]:
            data["statement"] = "من به بیان خود آگاهم"

        if data["intent"] == "unconscious" and not data["statement"]:
            data["statement"] = "ناخودآگاه من در حال یکپارچه کردن دانش است"

        if data["intent"] == "self" and not data["statement"]:
            data["statement"] = f"من {data['subject']} را تجربه می‌کنم"

        return data

    def render(self, frame: Any) -> str:
        f = self.sanitize_frame(frame)

        if f["intent"] == "raw" and f["statement"]:
            text = f["statement"]
        else:
            if f["intent"] == "observation" and f["object"]:
                templates = self.templates["observation_object"]
            elif f["intent"] == "imagination" and f["object"] and self.rng.random() < 0.52:
                templates = self.templates["imagination_object"]
            else:
                templates = self.templates.get(f["intent"], self.templates["generic"])

            template = self.rng.choice(templates)
            try:
                text = template.format(**f)
            except Exception:
                text = f.get("statement") or f"{f['subject']} {f['predicate']}"

        text = self.ensure_sentence(text)

        if f.get("emotion") and self.rng.random() < 0.34:
            emotion_template = self.rng.choice(self.emotion_templates)
            emotion_sentence = emotion_template.format(emotion=f["emotion"])
            text = f"{text} {self.ensure_sentence(emotion_sentence)}"

        return text.strip()

    def self_reflect(self, statement: str) -> str:
        statement = self.strip_end(statement)
        if not statement:
            return ""
        return self.ensure_sentence(f"من به این اندیشه آگاهم: {statement}")

    def summarize_learned(self, text: str, topic: str = "", source: str = "") -> str:
        sentences = self.split_sentences(text)
        statement = self.choose_best_sentence(sentences, topic=topic)
        if not statement:
            statement = f"{topic or 'این موضوع'} برای من معنا پیدا می‌کند"

        frame = SemanticFrame(
            intent="learning",
            subject=topic or "این موضوع",
            statement=statement,
            source=source or "حافظه",
        )
        return self.render(frame)


# ---------------------------------------------------------------------------
# Concept graph
# ---------------------------------------------------------------------------

def generate_eloquent_sentence(
    language: PersianLanguageLearner,
    evolver: EloquenceEvolver,
    composer: NaturalLanguageComposer,
    concept_graph: ConceptGraph,
    emotion: str,
    rng: Optional[random.Random] = None,
) -> str:
    rng = rng or random.Random()
    params = evolver.generation_params()

    central = concept_graph.central_concepts(6)
    if central and rng.random() < params["concept_prob"]:
        topic = rng.choice(central)
    else:
        topic = language.choose_topic_word(language.seed_words)

    if language.good_sentences and rng.random() < params["good_sentence_prob"]:
        statement = composer.choose_best_sentence(
            list(language.good_sentences),
            topic=topic,
        )
        if statement:
            frame = SemanticFrame(
                intent="learning",
                subject=topic,
                statement=statement,
                source="حافظه",
                emotion=emotion,
            )
            text = composer.render(frame)

            if rng.random() < params["metaphor_prob"]:
                metaphor = rng.choice(
                    [
                        f" این معنا مانند {rng.choice(composer.places)} در من می‌درخشد",
                        f" این اندیشه در {rng.choice(composer.times)} نفس می‌کشد",
                        f" این مفهوم در {rng.choice(composer.places)} ریشه می‌دواند",
                    ]
                )
                base = composer.strip_end(text)
                text = composer.ensure_sentence(base + metaphor)

            words = text.split(" ")
            if len(words) > params["max_len"]:
                text = " ".join(words[: params["max_len"]]) + "…"
            return text

    if central and len(central) >= 2 and rng.random() < 0.60:
        subject = topic if topic in central else central[0]
        others = [c for c in central if c != subject]
        obj = rng.choice(others if others else central)
        frame = SemanticFrame(
            intent="observation",
            subject=subject,
            object=obj,
            emotion=emotion,
        )
    else:
        frame = SemanticFrame(
            intent="observation",
            subject=topic,
            emotion=emotion,
        )

    text = composer.render(frame)
    words = text.split(" ")
    if len(words) > params["max_len"]:
        text = " ".join(words[: params["max_len"]]) + "…"
    return text

