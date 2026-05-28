from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

from backend.intelligence.llm_engine import get_llm_engine
from backend.intelligence.service_registry import (
    DEFAULT_QUEST_SERVICE_ID,
    QUEST_SERVICE_IDS,
    QUEST_SERVICE_REGISTRY,
)

logger = logging.getLogger(__name__)


@dataclass
class RoutingResult:
    quest_service_id: str
    persona_key: str
    is_first_route: bool
    confidence: str = "high"  # "high" | "medium" | "default"
    confidence_score: float = 0.0  # 0.0–1.0 for re-lock gating


class RouterEngine:
    """
    Phase 1 (voice-only):
    - Routes directly to EXISTING quest service IDs only (no new service IDs introduced).
    - Writes routing tags into Session.extracted_fields:
        - "__router:service_id": quest service id (auditing)
        - "__quest:service_id": quest service id (quest engine source of truth)
    - Sets Session.persona_key using existing persona.py identities.
    - Idempotent: once routed, route() becomes a no-op for the session.
    """

    QUEST_SERVICE_FIELD = "__quest:service_id"
    ROUTER_SERVICE_FIELD = "__router:service_id"
    AWAITING_SELECTION_FIELD = "__router:awaiting_service_selection"

    def __init__(self):
        self._trie = self._build_trie()

    def _normalize_for_routing(self, text: str) -> str:
        """
        Normalize high-precision voice-ASR confusions before routing.

        Keep this list small and word-boundary-based to avoid misroutes.
        """
        s = (text or "").strip().lower()
        if not s:
            return ""
        # Replace punctuation with spaces; collapse whitespace.
        s = "".join(ch if (ch.isalnum() or ch.isspace()) else " " for ch in s)
        s = re.sub(r"\s+", " ", s).strip()

        subs = {
            r"\banterior\b": "interior",
            r"\bsolo\b": "solar",
            r"\bso\s+large\b": "solar",
            r"\bso\s+lar\b": "solar",
            r"\bso\s+low\b": "solar",
            r"\bso\s+la\b": "solar",
            r"\bsoler\b": "solar",
            r"\bsolah\b": "solar",
            r"\bplumming\b": "plumbing",
            r"\beletrical\b": "electrical",
            r"\bautomat(?:ion|e)\b": "automation",
            r"\blent\b": "slant",
            r"\bslent\b": "slant",
        }
        for pat, rep in subs.items():
            s = re.sub(pat, rep, s)
        return s

    def _build_trie(self) -> dict[str, str]:
        trie: dict[str, str] = {}
        for quest_service_id, manifest in QUEST_SERVICE_REGISTRY.items():
            kws = manifest.get("keywords") or []
            for kw in kws:
                k = str(kw).strip().lower()
                if not k:
                    continue
                if k in trie:
                    logger.warning(
                        "ROUTER_KEYWORD_DUPLICATE kw='%s' first=%s duplicate=%s",
                        k,
                        trie[k],
                        quest_service_id,
                    )
                    continue
                trie[k] = quest_service_id
        logger.info(
            "RouterEngine trie built: %d keywords, %d services",
            len(trie),
            len(QUEST_SERVICE_REGISTRY),
        )
        return trie

    async def route(self, message: str, *, channel: str, session) -> RoutingResult:
        """
        Route a message to a quest service ID. Voice-only in Phase 1.

        Idempotent:
        - If session is already tagged with __quest:service_id, returns immediately.
        """
        ch = (channel or "").strip().lower()

        extracted = getattr(session, "extracted_fields", None)
        if not isinstance(extracted, dict):
            extracted = {}
            session.extracted_fields = extracted

        awaiting = bool(extracted.get(self.AWAITING_SELECTION_FIELD))
        clarify_count = int(extracted.get("__router:clarify_count") or 0)

        def _has_any_captured_field(ex: dict) -> bool:
            params = ex.get("__quest:parameters")
            if not isinstance(params, dict) or not params:
                return False
            for v in params.values():
                if isinstance(v, dict) and v.get("value") is not None:
                    return True
            return False

        already = extracted.get(self.QUEST_SERVICE_FIELD)
        already_str = str(already).strip() if isinstance(already, str) else ""
        if already_str:
            # FIX 2 — Service re-lock allowance (strict):
            # Allow switching ONLY if:
            # - No quest fields have been captured yet (__quest:parameters is empty)
            # - New service is detected with confidence_score > 0.75
            # Once even one field is captured, service is permanently locked.
            if _has_any_captured_field(extracted):
                persona_key = getattr(session, "persona_key", None) or str(
                    QUEST_SERVICE_REGISTRY.get(already_str, {}).get("persona_key") or "sophia"
                )
                return RoutingResult(
                    quest_service_id=already_str,
                    persona_key=persona_key,
                    is_first_route=False,
                    confidence="high",
                    confidence_score=1.0,
                )

            # Try to detect a new service on this turn.
            msg = (message or "").strip()
            msg_lower = self._normalize_for_routing(msg)
            score, quest_service_id = self._trie_classify(msg_lower)

            # Only re-lock on strong signal.
            cand_sid: str | None = None
            cand_score = 0.0
            cand_conf = "default"
            if quest_service_id and score >= 2:
                cand_sid = quest_service_id
                cand_score = 0.9
                cand_conf = "high"
            else:
                llm_sid = await self._llm_classify(msg_lower or msg, session) if (ch == "voice") else None
                if isinstance(llm_sid, str) and llm_sid in QUEST_SERVICE_IDS:
                    cand_sid = llm_sid
                    cand_score = 0.8
                    cand_conf = "medium"

            if cand_sid and cand_sid != already_str and cand_score > 0.75:
                return self._tag_and_return(
                    session,
                    cand_sid,
                    confidence=cand_conf,
                    confidence_score=cand_score,
                    is_first_route=False,
                )

            persona_key = getattr(session, "persona_key", None) or str(
                QUEST_SERVICE_REGISTRY.get(already_str, {}).get("persona_key") or "sophia"
            )
            return RoutingResult(
                quest_service_id=already_str,
                persona_key=persona_key,
                is_first_route=False,
                confidence="high",
                confidence_score=1.0,
            )

        msg = (message or "").strip()
        msg_lower = self._normalize_for_routing(msg)

        # Tier 1: keyword trie
        score, quest_service_id = self._trie_classify(msg_lower)
        session_id = getattr(session, "session_id", "unknown")

        if quest_service_id and score >= 2:
            logger.info(
                "ROUTER_TIER1_HIGH score=%s service=%s session=%s",
                score,
                quest_service_id,
                session_id,
            )
            extracted[self.AWAITING_SELECTION_FIELD] = False
            return self._tag_and_return(session, quest_service_id, confidence="high", confidence_score=0.9, is_first_route=True)

        # Tier 2: LLM classify when keyword signal is weak.
        # Enable for WhatsApp as well (text channel needs robust routing too).
        if ch in ("voice", "whatsapp") and score < 2:
            # Feed normalized text so the LLM can recover from common ASR variants.
            llm_sid = await self._llm_classify(msg_lower or msg, session)
            if isinstance(llm_sid, str) and llm_sid in QUEST_SERVICE_IDS:
                extracted[self.AWAITING_SELECTION_FIELD] = False
                logger.info(
                    "ROUTER_TIER2_LLM service=%s session=%s",
                    llm_sid,
                    session_id,
                )
                return self._tag_and_return(session, llm_sid, confidence="medium", confidence_score=0.8, is_first_route=True)

        if quest_service_id and score == 1:
            logger.info(
                "ROUTER_TIER1_MED score=%s service=%s session=%s",
                score,
                quest_service_id,
                session_id,
            )
            extracted[self.AWAITING_SELECTION_FIELD] = False
            return self._tag_and_return(session, quest_service_id, confidence="medium", confidence_score=0.75, is_first_route=True)

        # Tier 3: default fallback (voice) with clarification attempt tracking.
        # If there's zero keyword signal on the first utterance, do NOT lock the service yet.
        if score == 0 and not awaiting:
            extracted["__router:clarify_count"] = 1
            extracted[self.AWAITING_SELECTION_FIELD] = True
            logger.warning(
                "ROUTER_TIER3_AWAIT_SELECTION message_preview='%s' session=%s",
                msg[:40].replace("\n", " "),
                session_id,
            )
            return RoutingResult(
                quest_service_id="",
                persona_key=str(getattr(session, "persona_key", None) or "sophia"),
                is_first_route=False,
                confidence="default",
            )

        # If we're already awaiting selection (clarifying question was asked) and still no signal,
        # do NOT lock to the default for voice/whatsapp immediately. Track attempts and eventually lock.
        if awaiting and score == 0 and ch in ("voice", "whatsapp"):
            clarify_count = int(extracted.get("__router:clarify_count") or 1)
            clarify_count += 1
            extracted["__router:clarify_count"] = clarify_count
            if clarify_count >= 4:
                extracted["__router:clarify_count"] = 0
                extracted[self.AWAITING_SELECTION_FIELD] = False
                logger.warning(
                    "ROUTER_TIER3_DEFAULT_AFTER_CLARIFY message_preview='%s' session=%s",
                    msg[:40].replace("\n", " "),
                    session_id,
                )
                return self._tag_and_return(session, DEFAULT_QUEST_SERVICE_ID, confidence="default", confidence_score=0.0, is_first_route=True)

            extracted[self.AWAITING_SELECTION_FIELD] = True
            logger.warning(
                "ROUTER_TIER3_STILL_AWAITING_SELECTION message_preview='%s' session=%s",
                msg[:40].replace("\n", " "),
                session_id,
            )
            return RoutingResult(
                quest_service_id="",
                persona_key=str(getattr(session, "persona_key", None) or "sophia"),
                is_first_route=False,
                confidence="default",
            )

        # Non-voice (or when we have some signal) may lock to the default.
        # Note: WhatsApp is treated like voice above to avoid premature default-locking.
        extracted[self.AWAITING_SELECTION_FIELD] = False
        logger.warning(
            "ROUTER_TIER3_DEFAULT message_preview='%s' session=%s",
            msg[:40].replace("\n", " "),
            session_id,
        )
        return self._tag_and_return(session, DEFAULT_QUEST_SERVICE_ID, confidence="default", confidence_score=0.0, is_first_route=True)

    async def _llm_classify(self, message: str, session) -> Optional[str]:
        """
        Tier 2: map free-text intent to a quest service id via JSON extract.
        Returns a valid QUEST_SERVICE_IDS member, or None.
        """
        text = (message or "").strip()
        if not text:
            return None
        sid = str(getattr(session, "session_id", "") or "router_tier2")
        lines: list[str] = []
        for qid in QUEST_SERVICE_IDS:
            manifest = QUEST_SERVICE_REGISTRY.get(qid) or {}
            label = str(manifest.get("webhook_service_name") or qid.replace("_", " "))
            lines.append(f"- {qid}: {label}")
        catalog = "\n".join(lines)
        system_prompt = (
            "You are a routing classifier for PropFlow services.\n"
            "Your task: choose exactly ONE quest_service_id from the allowed list.\n"
            "If the message is only greeting or small talk with no identifiable service intent, return an empty string.\n\n"
            "Allowed quest_service_id values:\n"
            f"{catalog}\n\n"
            "Return ONLY the quest_service_id as plain text.\n"
            "- No JSON\n"
            "- No quotes\n"
            "- No markdown\n"
            "- No explanation\n"
            "- If none, return empty output\n"
        )
        try:
            raw_text = await get_llm_engine().chat(
                session_id=sid,
                user_message=text,
                system_prompt=system_prompt,
                history=[],
                temperature=0.1,
                max_tokens=16,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ROUTER_TIER2_ERROR session=%s err=%s",
                sid,
                str(exc)[:200],
            )
            return None
        qsid = str(raw_text or "").strip()
        if not qsid:
            return None
        if qsid not in QUEST_SERVICE_IDS:
            return None
        return qsid

    def _trie_classify(self, message_lower: str) -> tuple[int, Optional[str]]:
        scores: dict[str, int] = {}
        # Normalize: strip non-alphanumeric chars (keep spaces) so e.g. "construction." matches "construction".
        normalized = "".join(ch if (ch.isalnum() or ch == " ") else " " for ch in message_lower)
        words = set(normalized.split())
        word_list = normalized.split()
        bigrams = {f"{word_list[i]} {word_list[i + 1]}" for i in range(len(word_list) - 1)}

        for token in words | bigrams:
            sid = self._trie.get(token)
            if sid:
                scores[sid] = scores.get(sid, 0) + 1

        if not scores:
            return 0, None

        best = max(scores, key=scores.get)
        return int(scores[best]), str(best)

    def _tag_and_return(
        self,
        session,
        quest_service_id: str,
        *,
        confidence: str,
        confidence_score: float,
        is_first_route: bool,
    ) -> RoutingResult:
        if quest_service_id not in QUEST_SERVICE_IDS:
            quest_service_id = DEFAULT_QUEST_SERVICE_ID

        manifest = QUEST_SERVICE_REGISTRY.get(quest_service_id) or {}
        persona_key = str(manifest.get("persona_key") or "sophia")

        extracted = getattr(session, "extracted_fields", None)
        if not isinstance(extracted, dict):
            extracted = {}
            session.extracted_fields = extracted

        extracted[self.ROUTER_SERVICE_FIELD] = quest_service_id
        extracted[self.QUEST_SERVICE_FIELD] = quest_service_id
        session.persona_key = persona_key

        logger.info(
            "ROUTER_TAGGED service=%s persona=%s confidence=%s",
            quest_service_id,
            persona_key,
            confidence,
        )

        return RoutingResult(
            quest_service_id=quest_service_id,
            persona_key=persona_key,
            is_first_route=is_first_route,
            confidence=confidence,
            confidence_score=float(confidence_score or 0.0),
        )

