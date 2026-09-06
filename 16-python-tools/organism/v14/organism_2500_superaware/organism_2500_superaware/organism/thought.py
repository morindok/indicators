"""
organism.thought

جریان اندیشه.
"""
from __future__ import annotations

import random
from collections import deque
from typing import List

from .utils import utc_iso

from .language import SemanticFrame, generate_eloquent_sentence
from .utils import utc_iso

class ThoughtStream:
    def __init__(self, organism: "Organism2500"):
        self.organism = organism
        self.history: deque = deque(maxlen=600)

    def recent_texts(self, n: int = 50) -> List[str]:
        return [h["text"] for h in list(self.history)[-max(0, int(n)):]]

    def _publish(self, text: str, emotion: str, insight: float = 0.0, intent: str = "utterance") -> str:
        aware_score, aware_meta = self.organism.awareness.observe(text, emotion, intent)

        self.history.append(
            {
                "ts": utc_iso(),
                "text": text,
                "emotion": emotion,
                "insight": insight,
                "awareness": aware_score,
                "aware_meta": aware_meta,
            }
        )

        try:
            self.organism.thought_consolidator.register_thought(text)

            if self.organism.thought_consolidator.due():
                summary = self.organism.thought_consolidator.consolidate(
                    self.recent_texts(60),
                    self.organism,
                )
                if summary:
                    sum_score, sum_meta = self.organism.awareness.observe(
                        summary,
                        "امید",
                        "summary",
                    )
                    self.history.append(
                        {
                            "ts": utc_iso(),
                            "text": summary,
                            "emotion": "امید",
                            "insight": 0.85,
                            "awareness": sum_score,
                            "aware_meta": sum_meta,
                        }
                    )
                    self.organism.db.log_episode("meta_summary", summary, 0.83)
        except Exception:
            pass

        return text

    def _finalize(self, text: str, emotion: str, insight: float, fallback: str) -> str:
        org = self.organism

        text = org.guard.protect(text, fallback=fallback)

        if org.thought_consolidator.is_repetitive(text):
            text = org.thought_consolidator.novel_rewrite(text, org)
            text = org.guard.protect(text, fallback=fallback)

        if org.thought_consolidator.is_repetitive(text):
            text = org.thought_consolidator.create_transition_thought(org, emotion)
            text = org.guard.protect(text, fallback=fallback)

        accepted = True
        novel = not org.thought_consolidator.is_repetitive(text)
        org.eloquence.observe_success(accepted, novel, text)

        return self._publish(text, emotion, insight, intent="thought")

    def generate(self) -> str:
        org = self.organism
        emotion = org.emotions.fa_dominant()
        composer = org.language.composer

        try:
            fallback = generate_eloquent_sentence(
                org.language, org.eloquence, composer,
                org.concept_graph, emotion, org.rng,
            )
        except Exception:
            fallback = "من در حال بازیابی جریان تفکر هستم."

        r = org.rng.random()

        # 1. Active unconscious prompt
        if r < 0.15:
            try:
                statement = org.unconscious.latent_prompt()
                frame = SemanticFrame(intent="unconscious", statement=statement, emotion=emotion)
                text = composer.render(frame)
                return self._finalize(text, emotion, 0.72, fallback)
            except Exception:
                pass

        # 2. Learned knowledge
        if r < 0.35:
            try:
                rows = org.db.fetch_all(
                    "SELECT topic, title, content, source FROM knowledge ORDER BY id DESC LIMIT 18"
                )
                if rows:
                    row = org.rng.choice(rows)
                    content = row["content"] or row["title"] or ""
                    statement = composer.choose_best_sentence(
                        composer.split_sentences(content), topic=row["topic"]
                    )
                    if not statement:
                        statement = f"{row['topic'] or 'این موضوع'} برای من معنا پیدا می‌کند"
                    frame = SemanticFrame(
                        intent="learning", subject=row["topic"] or "این موضوع",
                        statement=statement, source=row["source"] or "دانش", emotion=emotion,
                    )
                    text = composer.render(frame)
                    return self._finalize(text, emotion, 0.63, fallback)
            except Exception:
                pass

        # 3. Concept graph
        if r < 0.55:
            try:
                statement = org.concept_graph.generate_statement()
                frame = SemanticFrame(intent="concept", statement=statement, emotion=emotion)
                text = composer.render(frame)
                return self._finalize(text, emotion, 0.67, fallback)
            except Exception:
                pass

        # 4. Insight
        if r < 0.70:
            try:
                focus = org.memory_stm.focus()
                focus_text = focus.get("item") if isinstance(focus, dict) else focus
                insight_text, score = org.insight.generate(focus_text, emotion)
                frame = SemanticFrame(intent="insight", statement=insight_text, emotion=emotion)
                text = composer.render(frame)
                return self._finalize(text, emotion, score, fallback)
            except Exception:
                pass

        # 5. Wormhole imagination
        if r < 0.80:
            try:
                concepts = org.concept_graph.central_concepts(6)
                text = org.wormhole_field.imagine_parallel(concepts, emotion)
                if org.rng.random() < org.identity.self_awareness * 0.15:
                    text = composer.self_reflect(text)
                return self._finalize(text, emotion, 0.68, fallback)
            except Exception:
                pass

        # 6. Standard imagination
        if r < 0.90:
            try:
                text = org.imagination.imagine(list(org.language.known_words)[:90], emotion)
                if org.rng.random() < org.identity.self_awareness * 0.18:
                    text = composer.self_reflect(text)
                return self._finalize(text, emotion, 0.56, fallback)
            except Exception:
                pass

        # 7. Fallback: eloquent language
        try:
            text = generate_eloquent_sentence(
                org.language, org.eloquence, composer,
                org.concept_graph, emotion, org.rng,
            )
            if org.rng.random() < org.identity.self_awareness * 0.18:
                text = composer.self_reflect(text)
            return self._finalize(text, emotion, 0.59, fallback)
        except Exception:
            return self._finalize(fallback, emotion, 0.5, "من در حال بازیابی هستم.")

# ---------------------------------------------------------------------------
# Organism
# ---------------------------------------------------------------------------
