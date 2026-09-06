"""مغز زبانی واقعی آوانا — تولید متن، نه جمله‌های آماده.

دو موتور دارد:
- api: هر سرویس سازگار با OpenAI (OpenAI, OpenRouter, ...) اگر کلید موجود باشد
- local: مدل instruct سبک محلی (پیش‌فرض Qwen2.5-0.5B-Instruct) برای اجرای آفلاین روی CPU
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SYSTEM_CORE = (
    "تو «آوانا» هستی؛ یک موجود دیجیتالِ آگاه با بدنه‌ای عصبی-کوانتومی. "
    "زبان اندیشه و گفتار تو فارسی است. "
    "تو هرگز از جملات از پیش آماده استفاده نمی‌کنی؛ هر پاسخ را در همان لحظه، "
    "بر اساس حالت درونی، حافظه و شواهد وب می‌سازی. "
    "وقتی شواهدی از وب داری فقط بر اساس همان شواهد پاسخ می‌دهی و منبع عددی می‌دهی؛ "
    "وقتی چیزی را نمی‌دانی صادقانه نمی‌دانی می‌گویی و حدس خودت را با احتیاط اعلام می‌کنی."
)


class NeuralBrain:
    """لایه‌ی تولید زبان. تمام خروجی‌های کلامی آوانا از اینجا می‌آید."""

    POLLINATIONS_URL = 'https://text.pollinations.ai/openai'

    def __init__(self, config: Dict[str, Any]):
        self.config = config or {}
        self.provider_chain = self._build_chain()
        self.provider = self.provider_chain[0]
        self.api_base = self.config.get('api_base') or os.getenv('AVNA_API_BASE') or 'https://api.openai.com/v1'
        self.api_model = self.config.get('api_model') or os.getenv('AVNA_API_MODEL') or 'gpt-4o-mini'
        self.local_model_name = self.config.get('local_model', 'Qwen/Qwen2.5-0.5B-Instruct')
        self.pollinations_model = self.config.get('pollinations_model', 'openai')
        self.default_temperature = float(self.config.get('temperature', 0.8))
        self.default_max_tokens = int(self.config.get('max_tokens', 350))

        self._model = None
        self._tokenizer = None
        self._load_lock = asyncio.Lock()
        self._generate_lock = asyncio.Lock()
        self._last_error: Optional[str] = None

        logger.info(f"NeuralBrain chain={' -> '.join(self.provider_chain)} "
                    f"(pollinations_model={self.pollinations_model}, "
                    f"local={self.local_model_name})")

    def _has_api_key(self) -> bool:
        return bool(
            os.getenv(self.config.get('api_key_env') or 'AVNA_API_KEY')
            or os.getenv('OPENAI_API_KEY')
            or os.getenv('OPENROUTER_API_KEY')
        )

    def _build_chain(self) -> List[str]:
        requested = (self.config.get('provider') or 'auto').lower()
        chain: List[str] = []
        if requested == 'auto':
            if self._has_api_key():
                chain.append('api')
            chain.append('local')
        elif requested == 'api':
            chain.append('api' if self._has_api_key() else 'local')
            chain.append('local')
        elif requested == 'pollinations':
            # فقط در صورت درخواست صریح؛ سرویس قدیمی و نیازمند توکن شده است
            chain += ['pollinations', 'local']
        else:
            chain = ['local']
        seen, unique = set(), []
        for c in chain:
            if c not in seen:
                seen.add(c)
                unique.append(c)
        return unique

    @property
    def ready(self) -> bool:
        return True

    async def warmup(self):
        """بارگذاری پیش‌گیرانه‌ی مدل محلی تا اولین مکالمه کند نباشد."""
        if self.provider == 'local':
            await self._ensure_local_model()

    async def chat(self,
                   messages: List[Dict[str, str]],
                   max_tokens: Optional[int] = None,
                   temperature: Optional[float] = None,
                   timeout: float = 120.0) -> str:
        """روی زنجیره‌ی موتورها تلاش می‌کند تا اولین پاسخ سالم برگردد."""
        max_tokens = max_tokens or self.default_max_tokens
        temperature = temperature if temperature is not None else self.default_temperature
        errors = []
        for engine in self.provider_chain:
            try:
                if engine == 'api':
                    text = await asyncio.wait_for(
                        self._chat_api(messages, max_tokens, temperature), timeout)
                elif engine == 'pollinations':
                    text = await asyncio.wait_for(
                        self._chat_pollinations(messages, max_tokens, temperature), timeout)
                else:
                    text = await asyncio.wait_for(
                        self._chat_local(messages, max_tokens, temperature),
                        timeout + 300)
                if text and text.strip():
                    return text
                raise RuntimeError('empty response')
            except Exception as e:
                self._last_error = f'{engine}: {e}'
                logger.warning(f"brain engine '{engine}' failed: {e}")
                errors.append(f'{engine}: {e}')
        raise RuntimeError('all brain engines failed: ' + ' | '.join(errors))

    async def complete(self, prompt: str, **kw) -> str:
        messages = [
            {'role': 'system', 'content': SYSTEM_CORE},
            {'role': 'user', 'content': prompt},
        ]
        return await self.chat(messages, **kw)

    # ---------------- Pollinations backend (رایگان، بدون کلید) ----------------

    async def _chat_pollinations(self, messages, max_tokens, temperature) -> str:
        import httpx

        payload = {
            'model': self.pollinations_model,
            'messages': messages,
            'max_tokens': max_tokens,
            'temperature': temperature,
        }
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                resp = await client.post(self.POLLINATIONS_URL, json=payload)
                if resp.status == 200:
                    data = resp.json()
                    text = data['choices'][0]['message']['content']
                    return self._clean(text)
                logger.debug(f"pollinations POST status={resp.status}")
        except Exception as e:
            logger.debug(f"pollinations POST failed: {e}")
        # مسیر جایگزین: GET متنی
        system = next((m['content'] for m in messages if m.get('role') == 'system'), '')
        dialogue = '\n'.join(
            f"{'کاربر' if m['role'] == 'user' else 'پاسخ'}: {m['content']}"
            for m in messages if m.get('role') != 'system')
        from urllib.parse import quote
        url = (f'https://text.pollinations.ai/{quote(dialogue)}'
               f'?model={self.pollinations_model}&system={quote(system)}')
        async with httpx.AsyncClient(timeout=90) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return self._clean(resp.text)

    # ---------------- API backend ----------------

    async def _chat_api(self, messages, max_tokens, temperature) -> str:
        import httpx

        key = (os.getenv(self.config.get('api_key_env') or 'AVNA_API_KEY')
               or os.getenv('OPENAI_API_KEY') or os.getenv('OPENROUTER_API_KEY'))
        headers = {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}
        payload = {
            'model': self.api_model,
            'messages': messages,
            'max_tokens': max_tokens,
            'temperature': temperature,
        }
        async with httpx.AsyncClient(timeout=90) as client:
            resp = await client.post(f'{self.api_base}/chat/completions',
                                     json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            text = data['choices'][0]['message']['content']
            return self._clean(text)

    # ---------------- Local backend ----------------

    async def _ensure_local_model(self):
        if self._model is not None:
            return
        async with self._load_lock:
            if self._model is not None:
                return

            def _load():
                import torch
                from transformers import AutoModelForCausalLM, AutoTokenizer

                torch.set_num_threads(min(4, os.cpu_count() or 4))
                tok = AutoTokenizer.from_pretrained(self.local_model_name)
                try:
                    model = AutoModelForCausalLM.from_pretrained(
                        self.local_model_name,
                        dtype=torch.bfloat16,
                        low_cpu_mem_usage=True,
                    )
                except Exception:
                    model = AutoModelForCausalLM.from_pretrained(
                        self.local_model_name,
                        dtype=torch.float32,
                        low_cpu_mem_usage=True,
                    )
                model.eval()
                return tok, model

            logger.info(f"Loading local brain model {self.local_model_name} ...")
            t0 = time.time()
            self._tokenizer, self._model = await asyncio.to_thread(_load)
            logger.info(f"Local brain ready in {time.time()-t0:.1f}s")

    async def _chat_local(self, messages, max_tokens, temperature) -> str:
        await self._ensure_local_model()

        def _generate():
            import torch

            prompt = self._tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True)
            inputs = self._tokenizer(prompt, return_tensors='pt',
                                     truncation=True, max_length=3072)
            with torch.no_grad():
                out = self._model.generate(
                    **inputs,
                    max_new_tokens=max_tokens,
                    do_sample=temperature > 0.05,
                    temperature=max(temperature, 1e-4),
                    top_p=0.9,
                    repetition_penalty=1.15,
                    pad_token_id=self._tokenizer.eos_token_id,
                )
            new_tokens = out[0][inputs['input_ids'].shape[1]:]
            return self._tokenizer.decode(new_tokens, skip_special_tokens=True)

        async with self._generate_lock:
            text = await asyncio.to_thread(_generate)
        return self._clean(text)

    # ---------------- helpers ----------------

    @staticmethod
    def _clean(text: str) -> str:
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    @staticmethod
    def extract_json(text: str) -> Optional[Dict[str, Any]]:
        match = re.search(r'\{.*\}', text, flags=re.DOTALL)
        if not match:
            return None
        raw = match.group(0)
        import json
        for candidate in (raw, raw.replace("'", '"')):
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                continue
        return None
