from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from backend.schemas import LLMRouterSettings

logger = logging.getLogger("horology.llm_router")

# Cost per 1M tokens (input_usd, output_usd)
MODEL_PRICING_PER_1M: dict[str, tuple[float, float]] = {
    "gemini-3.1-flash-lite-preview": (0.075, 0.30),
    "gemini-3-flash-preview": (0.15, 0.60),
    "gemini-3.1-pro-preview": (1.25, 5.00),
    "gemini-2.5-flash-lite": (0.075, 0.30),
    "gemini-3.8-flash": (0.12, 0.48),
    "gemini-2.5-flash": (0.15, 0.60),
    "gemini-2.5-pro": (1.25, 5.00),
    "gemini-4-argon": (1.50, 6.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "claude-3-5-sonnet": (3.00, 15.00),
    "claude-3-5-sonnet-latest": (3.00, 15.00),
    "claude-3-7-sonnet": (3.00, 15.00),
    "claude-3-7-sonnet-latest": (3.00, 15.00),
    "llama-3.3-70b-versatile": (0.06, 0.06),
    "llama-3.2-90b-vision-preview": (0.18, 0.18),
    "deepseek-chat": (0.14, 0.28),
    "deepseek-reasoner": (0.55, 2.19),
    "google/gemini-2.5-flash": (0.15, 0.60),
    "ollama/llama3.2": (0.0, 0.0),
    "ollama/llava": (0.0, 0.0),
}

USD_TO_EUR_RATE = 0.92


@dataclass
class LLMCallResult:
    content: str
    parsed_json: dict[str, Any]
    provider_used: str
    model_used: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    used_fallback: bool = False


class MultiProviderLLMRouter:
    """
    Dynamic Multi-Provider LLM Router supporting Google Gemini, OpenAI, Anthropic,
    Groq, DeepSeek, OpenRouter, and local Ollama with automatic fallback and
    exact token/cost accounting.
    """

    def __init__(self, settings: Optional[LLMRouterSettings] = None) -> None:
        self.settings = settings or LLMRouterSettings()

    @staticmethod
    def compute_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
        pricing = MODEL_PRICING_PER_1M.get(model)
        if not pricing:
            for key, val in MODEL_PRICING_PER_1M.items():
                if key in model or model in key:
                    pricing = val
                    break
        if not pricing:
            pricing = (0.15, 0.60)
        in_cost = (input_tokens / 1_000_000.0) * pricing[0]
        out_cost = (output_tokens / 1_000_000.0) * pricing[1]
        return round(in_cost + out_cost, 6)

    @staticmethod
    def extract_json_object(raw_text: str) -> dict[str, Any]:
        """Extracts and parses a JSON object from raw LLM response text or markdown code blocks."""
        cleaned = raw_text.strip()
        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
        if fence_match:
            cleaned = fence_match.group(1)
        else:
            brace_start = cleaned.find("{")
            brace_end = cleaned.rfind("}")
            if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
                cleaned = cleaned[brace_start : brace_end + 1]
        return json.loads(cleaned)

    def get_api_key_for_provider(self, provider: str) -> str:
        p = provider.lower().strip()
        mapping = {
            "gemini": self.settings.gemini_api_key,
            "openai": self.settings.openai_api_key,
            "anthropic": self.settings.anthropic_api_key,
            "groq": self.settings.groq_api_key,
            "deepseek": self.settings.deepseek_api_key,
            "openrouter": self.settings.openrouter_api_key,
            "ollama": "ollama-local",
        }
        return (mapping.get(p) or "").strip()

    def auto_optimize_settings(self) -> LLMRouterSettings:
        """
        Applies the 'Auto-Optimize Cost/Performance' preset based on available API keys.
        Selects the fastest ultra-low-cost model for Tier 1, multimodal vision flash model
        for Tier 2, and high-reasoning frontier model for Tier 3.
        """
        s = self.settings.model_copy(deep=True)
        s.auto_optimize_enabled = True

        # Tier 1: Ultra-low-cost batch text triage
        if s.groq_api_key:
            s.tier1_provider = "groq"
            s.tier1_model = "llama-3.3-70b-versatile"
        elif s.gemini_api_key:
            s.tier1_provider = "gemini"
            s.tier1_model = "gemini-3.1-flash-lite-preview"
        elif s.deepseek_api_key:
            s.tier1_provider = "deepseek"
            s.tier1_model = "deepseek-chat"
        elif s.openai_api_key:
            s.tier1_provider = "openai"
            s.tier1_model = "gpt-4o-mini"
        else:
            s.tier1_provider = "gemini"
            s.tier1_model = "gemini-3.1-flash-lite-preview"

        # Tier 2: Multimodal vision horologist
        if s.gemini_api_key:
            s.tier2_provider = "gemini"
            s.tier2_model = "gemini-3-flash-preview"
        elif s.openai_api_key:
            s.tier2_provider = "openai"
            s.tier2_model = "gpt-4o-mini"
        elif s.anthropic_api_key:
            s.tier2_provider = "anthropic"
            s.tier2_model = "claude-3-5-sonnet-latest"
        else:
            s.tier2_provider = "gemini"
            s.tier2_model = "gemini-3-flash-preview"

        # Tier 3: Senior Horology Arbitrator (High-Reasoning)
        if s.gemini_api_key:
            s.tier3_provider = "gemini"
            s.tier3_model = "gemini-3-flash-preview"
        elif s.anthropic_api_key:
            s.tier3_provider = "anthropic"
            s.tier3_model = "claude-3-7-sonnet-latest"
        elif s.deepseek_api_key:
            s.tier3_provider = "deepseek"
            s.tier3_model = "deepseek-reasoner"
        elif s.openai_api_key:
            s.tier3_provider = "openai"
            s.tier3_model = "gpt-4o"
        else:
            s.tier3_provider = "gemini"
            s.tier3_model = "gemini-3-flash-preview"

        self.settings = s
        return s

    def _build_candidate_chain(
        self, tier: int, require_vision: bool = False
    ) -> list[tuple[str, str]]:
        """Builds an ordered fallback list of (provider, model) pairs for a given tier."""
        if tier == 1:
            primary = (self.settings.tier1_provider, self.settings.tier1_model)
            alternates = [
                ("gemini", "gemini-3.1-flash-lite-preview"),
                ("groq", "llama-3.3-70b-versatile"),
                ("openai", "gpt-4o-mini"),
                ("deepseek", "deepseek-chat"),
                ("openrouter", "google/gemini-2.5-flash"),
            ]
        elif tier == 2:
            primary = (self.settings.tier2_provider, self.settings.tier2_model)
            alternates = [
                ("gemini", "gemini-3-flash-preview"),
                ("openai", "gpt-4o-mini"),
                ("anthropic", "claude-3-5-sonnet-latest"),
                ("openrouter", "google/gemini-2.5-flash"),
            ]
        else:
            primary = (self.settings.tier3_provider, self.settings.tier3_model)
            alternates = [
                ("gemini", "gemini-3-flash-preview"),
                ("anthropic", "claude-3-7-sonnet-latest"),
                ("deepseek", "deepseek-reasoner"),
                ("openai", "gpt-4o"),
                ("openrouter", "google/gemini-2.5-flash"),
            ]

        chain: list[tuple[str, str]] = [primary]
        for cand in alternates:
            if cand not in chain:
                if require_vision and cand[0] in ("deepseek",):
                    continue
                chain.append(cand)
        return chain

    async def generate_json(
        self,
        tier: int,
        system_prompt: str,
        user_prompt: str,
        images: Optional[list[dict[str, str]]] = None,
        fallback_generator: Optional[Any] = None,
        use_search_grounding: bool = False,
    ) -> LLMCallResult:
        """
        Routes a structured JSON request to the configured provider for `tier`.
        Automatically falls back across configured providers if an API key is missing
        or rate-limited, and finally uses `fallback_generator` if offline/unconfigured.
        """
        require_vision = bool(images)
        chain = self._build_candidate_chain(tier=tier, require_vision=require_vision)

        for idx, (provider, model) in enumerate(chain):
            api_key = self.get_api_key_for_provider(provider)
            if not api_key:
                continue

            try:
                result = await self._dispatch_provider(
                    provider=provider,
                    model=model,
                    api_key=api_key,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    images=images,
                    use_search_grounding=use_search_grounding,
                )
                result.used_fallback = idx > 0
                return result
            except Exception as exc:
                logger.warning(
                    "Tier %d call failed on provider=%s model=%s (%s); trying next fallback...",
                    tier,
                    provider,
                    model,
                    exc,
                )

        # Clean deterministic fallback when no external API keys are configured or reachable
        configured_model = chain[0][1]
        configured_provider = chain[0][0]
        if fallback_generator is not None:
            fallback_dict = fallback_generator()
        else:
            fallback_dict = {}

        content_str = json.dumps(fallback_dict, ensure_ascii=False)
        est_input_tokens = max(120, (len(system_prompt) + len(user_prompt)) // 4 + (len(images or []) * 258))
        est_output_tokens = max(80, len(content_str) // 4)
        total_tokens = est_input_tokens + est_output_tokens
        cost_usd = self.compute_cost_usd(configured_model, est_input_tokens, est_output_tokens)

        return LLMCallResult(
            content=content_str,
            parsed_json=fallback_dict,
            provider_used=configured_provider,
            model_used="Euristico Locale (Fallback Offline)",
            input_tokens=est_input_tokens,
            output_tokens=est_output_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            used_fallback=True,
        )

    async def _dispatch_provider(
        self,
        provider: str,
        model: str,
        api_key: str,
        system_prompt: str,
        user_prompt: str,
        images: Optional[list[dict[str, str]]] = None,
        use_search_grounding: bool = False,
    ) -> LLMCallResult:
        p = provider.lower().strip()
        if p == "gemini":
            return await self._call_gemini(
                model,
                api_key,
                system_prompt,
                user_prompt,
                images,
                use_search_grounding=use_search_grounding,
            )
        if p in ("openai", "groq", "deepseek", "openrouter"):
            return await self._call_openai_compatible(
                p, model, api_key, system_prompt, user_prompt, images
            )
        if p == "anthropic":
            return await self._call_anthropic(model, api_key, system_prompt, user_prompt, images)
        if p == "ollama":
            return await self._call_ollama(model, system_prompt, user_prompt, images)
        raise ValueError(f"Unsupported LLM provider: {provider}")

    async def _call_gemini(
        self,
        model: str,
        api_key: str,
        system_prompt: str,
        user_prompt: str,
        images: Optional[list[dict[str, str]]] = None,
        use_search_grounding: bool = False,
    ) -> LLMCallResult:
        # Map Gemini aliases to currently active Google AI Studio models with automatic fallback
        if "lite" in model:
            candidate_models = [
                "gemini-3.1-flash-lite-preview",
                "gemini-3-flash-preview",
                "gemini-2.5-flash-lite",
            ]
        else:
            candidate_models = [
                "gemini-3-flash-preview",
                "gemini-3.1-flash-lite-preview",
                "gemini-2.5-flash",
            ]
        if model not in candidate_models and not model.startswith("gemini-2.5") and model not in ("gemini-4-argon", "gemini-3.8-flash"):
            candidate_models.insert(0, model)

        parts: list[dict[str, Any]] = [{"text": f"{system_prompt}\n\n{user_prompt}"}]
        for img in images or []:
            parts.append(
                {
                    "inline_data": {
                        "mime_type": img.get("mime_type", "image/jpeg"),
                        "data": img["base64"],
                    }
                }
            )

        payload_standard: dict[str, Any] = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": 0.0,
                "responseMimeType": "application/json",
            },
        }
        payload_grounded: dict[str, Any] = {
            "contents": [{"parts": parts}],
            "tools": [{"google_search": {}}],
            "generationConfig": {
                "temperature": 0.0,
            },
        }

        last_exc: Optional[Exception] = None
        async with httpx.AsyncClient(timeout=45.0) as client:
            for api_model in candidate_models:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{api_model}:generateContent?key={api_key}"
                payloads_to_try = (
                    [(payload_grounded, True), (payload_standard, False)]
                    if use_search_grounding
                    else [(payload_standard, False)]
                )
                for active_payload, is_grounded in payloads_to_try:
                    try:
                        resp = await client.post(url, json=active_payload)
                        if resp.status_code in (400, 404, 429, 503):
                            last_exc = RuntimeError(
                                f"Gemini {api_model} HTTP {resp.status_code}: {resp.text[:200]}"
                            )
                            continue
                        resp.raise_for_status()
                        data = resp.json()

                        candidates = data.get("candidates") or []
                        content_parts = candidates[0].get("content", {}).get("parts", [])
                        text_out = ""
                        for p in content_parts:
                            if "text" in p and not p.get("thought", False):
                                text_out += p["text"] + "\n"
                        if not text_out.strip() and content_parts:
                            text_out = content_parts[-1].get("text", "{}")

                        parsed = self.extract_json_object(text_out)
                        if is_grounded and not parsed:
                            # If grounded output didn't contain a valid JSON block, retry standard JSON mode
                            continue

                        usage = data.get("usageMetadata") or {}
                        in_tok = int(usage.get("promptTokenCount") or 350)
                        out_tok = int(usage.get("candidatesTokenCount") or 180)
                        suffix = "LIVE API + Google Search" if is_grounded else "LIVE API"
                        return LLMCallResult(
                            content=text_out,
                            parsed_json=parsed,
                            provider_used="gemini",
                            model_used=f"{api_model} ({suffix})",
                            input_tokens=in_tok,
                            output_tokens=out_tok,
                            total_tokens=in_tok + out_tok,
                            cost_usd=self.compute_cost_usd(api_model, in_tok, out_tok),
                        )
                    except Exception as exc:
                        last_exc = exc
                        continue

        raise last_exc or RuntimeError("All Gemini candidate models failed")

    async def _call_openai_compatible(
        self,
        provider: str,
        model: str,
        api_key: str,
        system_prompt: str,
        user_prompt: str,
        images: Optional[list[dict[str, str]]] = None,
    ) -> LLMCallResult:
        endpoints = {
            "openai": "https://api.openai.com/v1/chat/completions",
            "groq": "https://api.groq.com/openai/v1/chat/completions",
            "deepseek": "https://api.deepseek.com/v1/chat/completions",
            "openrouter": "https://openrouter.ai/api/v1/chat/completions",
        }
        url = endpoints[provider]
        user_content: Any
        if images and provider in ("openai", "openrouter", "groq"):
            user_content = [{"type": "text", "text": user_prompt}]
            for img in images:
                data_uri = f"data:{img.get('mime_type', 'image/jpeg')};base64,{img['base64']}"
                user_content.append({"type": "image_url", "image_url": {"url": data_uri}})
        else:
            user_content = user_prompt

        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.0,
        }
        if provider in ("openai", "groq", "deepseek"):
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        text_out = data["choices"][0]["message"]["content"]
        usage = data.get("usage") or {}
        in_tok = int(usage.get("prompt_tokens") or 350)
        out_tok = int(usage.get("completion_tokens") or 180)
        parsed = self.extract_json_object(text_out)
        return LLMCallResult(
            content=text_out,
            parsed_json=parsed,
            provider_used=provider,
            model_used=model,
            input_tokens=in_tok,
            output_tokens=out_tok,
            total_tokens=in_tok + out_tok,
            cost_usd=self.compute_cost_usd(model, in_tok, out_tok),
        )

    async def _call_anthropic(
        self,
        model: str,
        api_key: str,
        system_prompt: str,
        user_prompt: str,
        images: Optional[list[dict[str, str]]] = None,
    ) -> LLMCallResult:
        url = "https://api.anthropic.com/v1/messages"
        content_blocks: list[dict[str, Any]] = []
        for img in images or []:
            content_blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": img.get("mime_type", "image/jpeg"),
                        "data": img["base64"],
                    },
                }
            )
        content_blocks.append({"type": "text", "text": user_prompt})

        payload = {
            "model": model,
            "max_tokens": 1200,
            "temperature": 0.0,
            "system": system_prompt,
            "messages": [{"role": "user", "content": content_blocks}],
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        text_out = data["content"][0]["text"]
        usage = data.get("usage") or {}
        in_tok = int(usage.get("input_tokens") or 400)
        out_tok = int(usage.get("output_tokens") or 220)
        parsed = self.extract_json_object(text_out)
        return LLMCallResult(
            content=text_out,
            parsed_json=parsed,
            provider_used="anthropic",
            model_used=model,
            input_tokens=in_tok,
            output_tokens=out_tok,
            total_tokens=in_tok + out_tok,
            cost_usd=self.compute_cost_usd(model, in_tok, out_tok),
        )

    async def _call_ollama(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        images: Optional[list[dict[str, str]]] = None,
    ) -> LLMCallResult:
        base = self.settings.ollama_base_url.rstrip("/")
        url = f"{base}/api/chat"
        msg: dict[str, Any] = {"role": "user", "content": user_prompt}
        if images:
            msg["images"] = [img["base64"] for img in images]

        payload = {
            "model": model.replace("ollama/", ""),
            "messages": [
                {"role": "system", "content": system_prompt},
                msg,
            ],
            "format": "json",
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        text_out = data.get("message", {}).get("content", "{}")
        in_tok = int(data.get("prompt_eval_count") or 300)
        out_tok = int(data.get("eval_count") or 150)
        parsed = self.extract_json_object(text_out)
        return LLMCallResult(
            content=text_out,
            parsed_json=parsed,
            provider_used="ollama",
            model_used=model,
            input_tokens=in_tok,
            output_tokens=out_tok,
            total_tokens=in_tok + out_tok,
            cost_usd=0.0,
        )
