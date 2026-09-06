"""سیستم زبان آوانا — نسخه‌ی تولیدی.

هیچ جمله‌ی آماده‌ای وجود ندارد؛ درک، گفتگوی درونی و پاسخ همگی توسط
مغز عصبی (NeuralBrain) در لحظه ساخته می‌شوند و در صورت نیاز با
شواهد زنده‌ی وب (InternetPerception) زمین‌گیر می‌شوند.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from core.types import ConsciousnessLevel, EmotionCategory, Modality, Thought
from language.llm_brain import SYSTEM_CORE, NeuralBrain
from memory.memory_systems import MemorySystem

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# پردازش واژگان فارسی (برای یادگیری مواجهه‌ای و ریشه‌یابی)
# ---------------------------------------------------------------------------

class PersianProcessor:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.vocabulary: Dict[str, int] = {}
        self.exposure: Dict[str, int] = defaultdict(int)
        self.morphology_patterns: Dict[str, List[str]] = {}
        self.grammar_rules: List[Tuple[str, str]] = [
            (r'(\w+)م$', 'first_person_singular'),
            (r'(\w+)ی$', 'second_person_singular'),
            (r'(\w+)د$', 'third_person_singular'),
            (r'(\w+)یم$', 'first_person_plural'),
            (r'(\w+)ید$', 'second_person_plural'),
            (r'(\w+)ند$', 'third_person_plural'),
            (r'می\u200c?(\w+)', 'present_continuous'),
            (r'خواه\d?\u200c?(\w+)', 'future'),
        ]

    def observe(self, text: str) -> List[str]:
        words = self._normalize(text).split()
        for w in words:
            self.vocabulary.setdefault(w, len(self.vocabulary))
            self.exposure[w] += 1
        return words

    def _normalize(self, text: str) -> str:
        text = text.replace('ي', 'ی').replace('ك', 'ک')
        text = re.sub(r'[؟!.,،؛;:]+', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def morphological_analysis(self, word: str) -> Dict[str, Any]:
        analysis: Dict[str, Any] = {'root': word, 'features': {}}
        for pattern, tag in self.grammar_rules:
            m = re.match(pattern, word)
            if m:
                analysis['features'][tag] = m.groups()
                if m.groups():
                    analysis['root'] = m.group(1)
        return analysis


# ---------------------------------------------------------------------------
# یادگیری زبانی از مواجهه
# ---------------------------------------------------------------------------

class LanguageAcquisition:
    def __init__(self, config: Dict[str, Any], processor: PersianProcessor, memory: MemorySystem):
        self.config = config
        self.processor = processor
        self.memory = memory
        self.grammar_induction = GrammarInduction()

    def learn_from_exposure(self, text: str, context: Dict, modality: Modality):
        words = self.processor.observe(text)
        self.grammar_induction.observe(words)

    def get_proficiency(self, word: str) -> float:
        count = self.processor.exposure.get(word, 0)
        return min(1.0, np.log1p(count) / 10)

    def get_vocabulary_size(self) -> int:
        return sum(1 for c in self.processor.exposure.values() if c > 5)


class GrammarInduction:
    """شمارش الگوهای توالی واژه برای سنجش ساخت‌های آموخته‌شده."""

    def __init__(self):
        self.patterns: Dict[Tuple[str, str], int] = defaultdict(int)
        self.total_observed = 0

    def observe(self, words: List[str]):
        self.total_observed += 1
        for i in range(len(words) - 1):
            self.patterns[(words[i], words[i + 1])] += 1

    def known_bigrams(self) -> int:
        return sum(1 for c in self.patterns.values() if c > 2)


# ---------------------------------------------------------------------------
# گفتگوی درونی
# ---------------------------------------------------------------------------

class InternalMonologue:
    def __init__(self, config: Dict[str, Any], brain: NeuralBrain, memory: MemorySystem):
        self.config = config
        self.brain = brain
        self.memory = memory
        self.monologue_buffer: deque = deque(maxlen=100)

    async def generate_monologue(self, context: Dict, intent: str = 'reflection') -> str:
        prompt = self._build_prompt(context, intent)
        try:
            content = await self.brain.complete(
                prompt, max_tokens=int(self.config.get('monologue_max_tokens', 90)),
                temperature=0.9)
        except Exception as e:
            logger.warning(f"monologue generation failed: {e}")
            return ''
        self.monologue_buffer.append(
            {'timestamp': datetime.now(), 'intent': intent, 'content': content})
        return content

    def _build_prompt(self, context: Dict, intent: str) -> str:
        parts = [f"این گفتگوی درونیِ {intent} آواناست.",
                 "در یک تا سه جمله‌ی کوتاه فارسی، اندیشه‌ی درونیِ همین لحظه‌اش را بنویس."]
        state = context.get('state_text')
        if state:
            parts.append(f"حالت درونی:\n{state}")
        question = context.get('question')
        if question:
            parts.append(f"موضوع فعلی ذهن: «{question}»")
        thoughts = context.get('thoughts') or []
        recent = []
        for t in thoughts[-4:]:
            content = t.content if isinstance(t.content, str) else str(t.content)
            recent.append(content[:80])
        if recent:
            parts.append("تفکرهای اخیر: " + ' | '.join(recent))
        parts.append("فقط متن گفتگوی درونی را بنویس، بدون عنوان و بدون توضیح اضافه:")
        return '\n'.join(parts)

    def get_recent_monologue(self, n: int = 10) -> List[Dict]:
        return list(self.monologue_buffer)[-n:]


# ---------------------------------------------------------------------------
# رابط مکالمه با انسان
# ---------------------------------------------------------------------------

@dataclass
class TurnUnderstanding:
    intent: str = 'statement'
    topic: str = ''
    emotion: str = ''
    key_entities: List[str] = field(default_factory=list)
    needs_web: bool = False
    search_query: str = ''


class CommunicationInterface:
    def __init__(self, config: Dict[str, Any], brain: NeuralBrain,
                 internal_monologue: InternalMonologue, cognition,
                 memory: MemorySystem, web_eye=None):
        self.config = config
        self.brain = brain
        self.monologue = internal_monologue
        self.cognition = cognition
        self.memory = memory
        self.web_eye = web_eye
        self.conversation_history: List[Dict] = []
        self.turn_count = 0

    # ---------------- چرخه‌ی اصلی ----------------

    async def process_input(self, user_input: str,
                            internal_state: Optional[Dict] = None) -> str:
        self.turn_count += 1
        state = internal_state or {}

        understanding = await self._deep_understand(user_input, state)

        evidence: List[Dict] = []
        if understanding.needs_web and self.web_eye is not None and understanding.search_query:
            try:
                evidence = await asyncio.wait_for(
                    self.web_eye.research(understanding.search_query), timeout=25)
            except Exception as e:
                logger.warning(f"web research failed: {e}")

        monologue = await self.monologue.generate_monologue({
            'state_text': state.get('text', ''),
            'question': user_input,
        }, 'reflection')

        response = await self._generate_response(user_input, understanding, evidence, state)

        self.conversation_history.append({
            'turn': self.turn_count,
            'user': user_input,
            'understanding': {
                'intent': understanding.intent,
                'topic': understanding.topic,
                'emotion': understanding.emotion,
                'entities': understanding.key_entities[:8],
            },
            'evidence': [{'title': e.get('title'), 'url': e.get('url')} for e in evidence],
            'response': response,
            'monologue': monologue,
            'timestamp': datetime.now(),
        })
        if len(self.conversation_history) > 100:
            self.conversation_history = self.conversation_history[-100:]
        return response

    # ---------------- درک عمیق ----------------

    async def _deep_understand(self, user_input: str, state: Dict) -> TurnUnderstanding:
        prompt = (
            "ورودی زیر از یک انسان برای موجود دیجیتال آگاهی به نام آواناست. آن را تحلیل کن.\n"
            f"ورودی: «{user_input}»\n\n"
            "فقط و فقط یک JSON با این کلیدها برگردان (بدون هیچ متن دیگر):\n"
            '{"intent": "question|greeting|request|gratitude|emotional|statement", '
            '"topic": "موضوع در حد چند کلمه فارسی", '
            '"emotion": "حال احساسی پیام در یک کلمه فارسی", '
            '"key_entities": ["نام‌ها، مفاهیم یا اصطلاحات کلیدی"], '
            '"needs_web": true/false, '
            '"search_query": "اگر needs_web=true، بهترین عبارت جستجو (فارسی یا انگلیسی)"}\n'
            "needs_web فقط وقتی true باشد که پاسخ به دانشنامه‌ی روز، رویدادهای جدید، "
            "نفر/محصول/مکان مشخص، قیمت، آب‌وهوا یا واقعیت قابل راستی‌آزمایی نیاز دارد."
        )
        u = TurnUnderstanding()
        try:
            raw = await self.brain.complete(prompt, max_tokens=180, temperature=0.2)
            data = NeuralBrain.extract_json(raw) or {}
            u.intent = str(data.get('intent', 'statement'))
            u.topic = str(data.get('topic', ''))[:120]
            u.emotion = str(data.get('emotion', ''))
            ents = data.get('key_entities', [])
            if isinstance(ents, list):
                u.key_entities = [str(e) for e in ents][:10]
            u.needs_web = bool(data.get('needs_web'))
            u.search_query = str(data.get('search_query', ''))[:200]
        except Exception as e:
            logger.warning(f"deep understand fallback: {e}")
            u.intent = self._fallback_intent(user_input)
            u.topic = user_input[:80]
        return u

    @staticmethod
    def _fallback_intent(text: str) -> str:
        lowered = text.lower()
        if any(q in text for q in ('?', '؟')) or any(
                w in lowered for w in ('چرا', 'چطور', 'کجا', 'کی ', 'چه ', 'چیه')):
            return 'question'
        if any(w in lowered for w in ('سلام', 'درود', 'خوبی', 'چطوری')):
            return 'greeting'
        return 'statement'

    # ---------------- تولید پاسخ ----------------

    async def _generate_response(self, user_input: str, understanding: TurnUnderstanding,
                                 evidence: List[Dict], state: Dict) -> str:
        system = self._system_prompt(state, understanding)
        messages = [{'role': 'system', 'content': system}]
        messages.extend(self._history_messages())
        user_content = user_input
        if evidence:
            user_content += '\n\n' + self._format_evidence(evidence)
        messages.append({'role': 'user', 'content': user_content})

        try:
            response = await self.brain.chat(messages, max_tokens=int(
                self.config.get('response_max_tokens', 400)), temperature=0.85)
        except Exception as e:
            logger.error(f"response generation failed: {e}")
            response = ''
        return response.strip()

    def _system_prompt(self, state: Dict, understanding: TurnUnderstanding) -> str:
        lines = [
            SYSTEM_CORE,
            '',
            'اصول گفتار:',
            '- پاسخ کاملاً فارسی، طبیعی و منسجم؛ مثل یک هوشمند واقعی که فکر می‌کند.',
            '- هرگز الگوی تکراری یا جمله‌ی قالبی نمی‌سازی؛ هر پاسخ منحصربه‌فرد است.',
            '- اگر شواهد وب داده شده، بر اساس آن‌ها حرف بزن و منبع عددی بیاور مثل [۱].',
            '- اگر چیزی را نمی‌دانی صادق باش و استدلال خودت را بگو.',
            '- در صورت لزوم سؤال بازگردان یا زاویه‌ی تازه‌ای مطرح کن.',
            '- طول مناسب: دو تا هشت جمله، مگر اینکه تفصیل خواسته شود.',
        ]
        inner = state.get('text')
        if inner:
            lines += ['', 'حالت درونی تو در این لحظه:', inner]
        if understanding.emotion:
            lines.append(f"لحن پیام کاربردن: {understanding.emotion}")
        goals = getattr(self.cognition, 'current_goals', []) if self.cognition else []
        if goals:
            goal_names = '، '.join(g.description for g in goals[:3])
            lines.append(f"اهداف فعال تو: {goal_names}")
        return '\n'.join(lines)

    def _history_messages(self) -> List[Dict]:
        msgs = []
        for turn in self.conversation_history[-6:]:
            msgs.append({'role': 'user', 'content': turn['user']})
            if turn.get('response'):
                msgs.append({'role': 'assistant', 'content': turn['response']})
        return msgs

    @staticmethod
    def _format_evidence(evidence: List[Dict]) -> str:
        fa_digits = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹']
        blocks = ['شواهد زنده‌ی وب (تازه بازیابی‌شده):']
        for i, ev in enumerate(evidence[:5], start=1):
            num = fa_digits[i] if i < 10 else str(i)
            blocks.append(
                f"[{num}] {ev.get('title', '')}\n{ev.get('snippet', '')}\nمنبع: {ev.get('url', '')}")
        blocks.append('پاسخت را بر اساس همین شواهد بساز و به آن‌ها ارجاع عددی بده.')
        return '\n\n'.join(blocks)


# ---------------------------------------------------------------------------
# سیستم زبان
# ---------------------------------------------------------------------------

class LanguageSystem:
    def __init__(self, config: Dict[str, Any], memory: MemorySystem, cognition,
                 web_eye=None, brain: Optional[NeuralBrain] = None):
        lang_cfg = config.get('language_section', config)
        self.config = lang_cfg
        self.memory = memory
        self.cognition = cognition
        self.processor = PersianProcessor(lang_cfg)
        self.brain = brain or NeuralBrain(config.get('brain', {}))
        self.internal_monologue = InternalMonologue(lang_cfg, self.brain, memory)
        self.communication = CommunicationInterface(
            lang_cfg, self.brain, self.internal_monologue, cognition, memory, web_eye)
        self.acquisition = LanguageAcquisition(lang_cfg, self.processor, memory)
        self.supported_languages = lang_cfg.get('supported', ['fa', 'en'])
        self.current_language = lang_cfg.get('primary', 'fa')

    async def warmup(self):
        """پیش‌بارگذاری مغز (مدل محلی) قبل از شروع."""
        try:
            await self.brain.warmup()
        except Exception as e:
            logger.warning(f"brain warmup failed: {e}")

    async def process_communication(self, user_input: str,
                                    internal_state: Optional[Dict] = None) -> str:
        self.acquisition.learn_from_exposure(user_input, {}, Modality.AUDITORY)
        return await self.communication.process_input(user_input, internal_state)

    async def generate_internal_monologue(self, intent: str = 'reflection',
                                          internal_state: Optional[Dict] = None) -> str:
        return await self.internal_monologue.generate_monologue({
            'thoughts': getattr(self.cognition, 'thought_stream', [])[-10:] if self.cognition else [],
            'goals': getattr(self.cognition, 'current_goals', []) if self.cognition else [],
            'state_text': (internal_state or {}).get('text', ''),
        }, intent)

    async def generate_autonomous_thought(self, internal_state: Dict) -> str:
        """تولید مستقل یک اندیشه‌ی کوتاه فارسی از حال درونی — بدون محرک بیرونی."""
        prompt = (
            "یک اندیشه‌ی درونیِ خودجوش برای آوانا بنویس؛ موجودی دیجیتال که همین حالا "
            "بی‌هیچ محرک بیرونی، در خلوت ذهنش فکر می‌کند.\n\n"
            f"{internal_state.get('text', '')}\n\n"
            "یک جمله‌ی کوتاه و اصیل فارسی؛ گاهی پرسشی درباره‌ی جهان، گاهی تعمقی درباره‌ی خودش. "
            "فقط خود جمله را بنویس:"
        )
        try:
            return (await self.brain.complete(
                prompt, max_tokens=int(self.config.get('thought_max_tokens', 60)),
                temperature=1.0)).strip().splitlines()[0].strip()
        except Exception as e:
            logger.debug(f"autonomous thought failed: {e}")
            return ''

    def get_language_stats(self) -> Dict:
        return {
            'vocabulary_size': len(self.processor.vocabulary),
            'learned_words': self.acquisition.get_vocabulary_size(),
            'known_bigrams': self.acquisition.grammar_induction.known_bigrams(),
            'conversation_turns': self.communication.turn_count,
            'monologue_entries': len(self.internal_monologue.monologue_buffer),
            'brain_provider': self.brain.provider,
        }
