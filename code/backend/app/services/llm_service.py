import json
import os
import re
import socket
import time
import urllib.error
import urllib.request
from http.client import RemoteDisconnected
from dataclasses import dataclass
from pathlib import Path

from openai import OpenAI

try:
    from app.core.settings_manager import SettingsManager
except Exception:  # pragma: no cover - keeps standalone utility imports tolerant
    SettingsManager = None  # type: ignore


class LLMConfigurationError(RuntimeError):
    """Raised when the LLM config is incomplete."""


class LLMInvocationError(RuntimeError):
    """Raised when the LLM request fails."""


class LLMStageError(LLMInvocationError):
    def __init__(self, message: str, *, intermediate_files: list[dict[str, str]]) -> None:
        super().__init__(message)
        self.intermediate_files = intermediate_files


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    base_url: str
    api_key: str
    model: str
    temperature: float = 0.2
    timeout_seconds: int = 300
    max_retries: int = 4
    compact_retries: bool = False


def resolve_llm_config(job: dict[str, object]) -> LLMConfig:
    settings = _load_rws_settings()
    settings_llm = settings.get("llm") if isinstance(settings.get("llm"), dict) else {}
    model = str(
        job.get("llm_model")
        or settings.get("active_model")
        or (settings_llm or {}).get("active_model")
        or os.getenv("LLM_MODEL")
        or ""
    ).strip()
    provider = str(job.get("llm_provider") or _infer_provider(model) or os.getenv("LLM_PROVIDER") or "openai_compatible")
    base_url = str(
        job.get("llm_base_url")
        or settings.get("api_base_url")
        or os.getenv("LLM_BASE_URL")
        or _default_base_url_for_model(model)
        or ""
    ).strip()
    api_keys = settings.get("api_keys") if isinstance(settings.get("api_keys"), dict) else {}
    api_key = str(
        job.get("llm_api_key")
        or api_keys.get(_infer_api_key_name(model))
        or api_keys.get("openai")
        or os.getenv("LLM_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or ""
    ).strip()
    is_deepseek = _is_deepseek_provider(provider)
    timeout_seconds = _resolve_timeout_seconds_for_provider(
        job.get("llm_timeout_seconds") or os.getenv("LLM_TIMEOUT_SECONDS"),
        provider=provider,
    )
    max_retries = _resolve_retry_count(
        job.get("llm_retry_count") or os.getenv("LLM_RETRY_COUNT"),
        default=4,
    )

    if not base_url:
        raise LLMConfigurationError("Missing LLM base URL. Please configure API Base URL in RWS system settings.")
    if not api_key:
        raise LLMConfigurationError("Missing LLM API key. Please configure the API key in RWS system settings.")
    if not model:
        raise LLMConfigurationError("Missing LLM model. Please configure the active model in RWS system settings.")

    return LLMConfig(
        provider=provider,
        base_url=base_url,
        api_key=api_key,
        model=model,
        temperature=0.1 if is_deepseek else 0.2,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        compact_retries=True,
    )


def _load_rws_settings() -> dict[str, object]:
    if SettingsManager is None:
        return {}
    try:
        settings = SettingsManager().get_settings()
        return settings if isinstance(settings, dict) else {}
    except Exception:
        return {}


def _infer_provider(model: str) -> str:
    return "deepseek" if "deepseek" in model.casefold() else "openai_compatible"


def _infer_api_key_name(model: str) -> str:
    normalized = model.casefold()
    if "deepseek" in normalized:
        return "deepseek"
    if "claude" in normalized or "anthropic" in normalized:
        return "anthropic"
    if "gemini" in normalized or "google" in normalized:
        return "google"
    if "qwen" in normalized:
        return "qwen"
    if "minimax" in normalized:
        return "minimax"
    return "openai"


def _default_base_url_for_model(model: str) -> str | None:
    if "minimax" in (model or "").casefold():
        return "https://api.minimax.io/v1"
    return None


def call_llm_stage(
    config: LLMConfig,
    *,
    system_prompt: str,
    user_prompt: str,
    intermediate_dir: Path,
    stage_slug: str,
    output_filename: str,
    output_format: str = "markdown",
) -> dict[str, object]:
    intermediate_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = intermediate_dir / f"{stage_slug}_prompt.txt"
    prompt_path.write_text(
        f"[system]\n{system_prompt}\n\n[user]\n{user_prompt}\n",
        encoding="utf-8",
    )

    endpoint = _normalize_chat_completions_url(config.base_url)
    request_payload = _build_request_payload(
        config,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        compact=False,
    )

    sanitized_request_path = intermediate_dir / f"{stage_slug}_request.json"
    sanitized_request_path.write_text(
        json.dumps(
            {
                "provider": config.provider,
                "endpoint": endpoint,
                "model": config.model,
                "temperature": config.temperature,
                "max_retries": config.max_retries,
                "messages": request_payload["messages"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    partial_artifacts = [
        {"name": f"{stage_slug}_prompt", "path": str(prompt_path), "category": "llm"},
        {"name": f"{stage_slug}_request", "path": str(sanitized_request_path), "category": "llm"},
    ]

    raw_response = ""
    last_error_message = ""
    for attempt in range(1, config.max_retries + 1):
        compact_attempt = config.compact_retries and attempt >= 2
        current_payload = _build_request_payload(
            config,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            compact=compact_attempt,
        )
        try:
            raw_response = _call_openai_sdk(config, current_payload)
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            last_error_message = f"LLM HTTP error {exc.code}: {detail}"
            if attempt < config.max_retries and _is_retryable_http_status(exc.code):
                _sleep_before_retry(attempt, provider=config.provider)
                continue
            raise _stage_error(
                intermediate_dir=intermediate_dir,
                stage_slug=stage_slug,
                message=last_error_message,
                partial_artifacts=partial_artifacts,
            ) from exc
        except urllib.error.URLError as exc:
            last_error_message = f"LLM request failed: {exc.reason}"
            if attempt < config.max_retries and _is_retryable_transport_reason(exc.reason):
                _sleep_before_retry(attempt, provider=config.provider)
                continue
            raise _stage_error(
                intermediate_dir=intermediate_dir,
                stage_slug=stage_slug,
                message=last_error_message,
                partial_artifacts=partial_artifacts,
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            last_error_message = (
                f"LLM request timed out after {config.timeout_seconds}s during `{stage_slug}`. "
                "You can increase `LLM_TIMEOUT_SECONDS`, reduce prompt size, or retry later."
            )
            if attempt < config.max_retries:
                _sleep_before_retry(attempt, provider=config.provider)
                continue
            raise _stage_error(
                intermediate_dir=intermediate_dir,
                stage_slug=stage_slug,
                message=last_error_message,
                partial_artifacts=partial_artifacts,
            ) from exc
        except RemoteDisconnected as exc:
            last_error_message = f"LLM request failed unexpectedly: {exc}"
            if attempt < config.max_retries:
                _sleep_before_retry(attempt, provider=config.provider)
                continue
            raise _stage_error(
                intermediate_dir=intermediate_dir,
                stage_slug=stage_slug,
                message=last_error_message,
                partial_artifacts=partial_artifacts,
            ) from exc
        except Exception as exc:
            last_error_message = f"LLM request failed unexpectedly: {exc}"
            if attempt < config.max_retries and _is_retryable_transport_reason(exc):
                _sleep_before_retry(attempt, provider=config.provider)
                continue
            raise _stage_error(
                intermediate_dir=intermediate_dir,
                stage_slug=stage_slug,
                message=last_error_message,
                partial_artifacts=partial_artifacts,
            ) from exc

    if not raw_response:
        raise _stage_error(
            intermediate_dir=intermediate_dir,
            stage_slug=stage_slug,
            message=last_error_message or "LLM request failed without a response.",
            partial_artifacts=partial_artifacts,
        )

    raw_response_path = intermediate_dir / f"{stage_slug}_response.json"
    raw_response_path.write_text(raw_response, encoding="utf-8")

    try:
        parsed = json.loads(raw_response)
        content = parsed["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise LLMInvocationError("LLM response format is not compatible with chat completions.") from exc

    cleaned_output = _sanitize_llm_output(str(content).strip(), output_format=output_format)
    output_path = intermediate_dir / output_filename
    output_path.write_text(cleaned_output, encoding="utf-8")

    artifacts = [
        *partial_artifacts,
        {"name": f"{stage_slug}_response", "path": str(raw_response_path), "category": "llm"},
        {"name": Path(output_filename).stem, "path": str(output_path), "category": "llm"},
    ]
    return {"text": cleaned_output, "artifacts": artifacts}


def build_latex_prompt(markdown_text: str, summary: dict[str, object], report_name: str) -> tuple[str, str]:
    system_prompt = (
        "You are a scientific writing assistant. "
        "Transform the provided markdown report into publication-ready LaTeX body content. "
        "Return only LaTeX content for the document body. "
        "Do not include \\documentclass, \\begin{document}, or \\end{document}. "
        "Preserve technical meaning, keep section hierarchy, and convert image references into figure environments "
        "that keep the original file names under the assets/ directory."
    )
    user_prompt = (
        f"Report title: {report_name}\n"
        f"Detected summary: {json.dumps(summary, ensure_ascii=False, indent=2)}\n\n"
        "Source markdown:\n"
        "----- BEGIN MARKDOWN -----\n"
        f"{markdown_text}\n"
        "----- END MARKDOWN -----\n\n"
        "Output only LaTeX body content."
    )
    return system_prompt, user_prompt


def call_openai_compatible_llm(
    config: LLMConfig,
    *,
    system_prompt: str,
    user_prompt: str,
    intermediate_dir: Path,
) -> dict[str, object]:
    result = call_llm_stage(
        config,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        intermediate_dir=intermediate_dir,
        stage_slug="06_latex_body",
        output_filename="06_latex_body.tex",
        output_format="latex",
    )
    return {"latex_body": result["text"], "artifacts": result["artifacts"]}


def _normalize_chat_completions_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    return f"{normalized}/v1/chat/completions"


def _normalize_openai_base_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        normalized = normalized[: -len("/chat/completions")]
    if normalized.endswith("/v1"):
        return normalized
    return f"{normalized}/v1"


def _call_openai_sdk(config: LLMConfig, request_payload: dict[str, object]) -> str:
    client = OpenAI(
        api_key=config.api_key,
        base_url=_normalize_openai_base_url(config.base_url),
        timeout=config.timeout_seconds,
        max_retries=0,
    )
    response = client.chat.completions.create(
        model=str(request_payload["model"]),
        messages=request_payload["messages"],  # type: ignore[arg-type]
        temperature=float(request_payload.get("temperature") or config.temperature),
    )
    if hasattr(response, "model_dump_json"):
        return response.model_dump_json()
    if hasattr(response, "model_dump"):
        return json.dumps(response.model_dump(), ensure_ascii=False)
    return json.dumps(response, default=lambda obj: getattr(obj, "__dict__", str(obj)), ensure_ascii=False)


def _build_request_payload(
    config: LLMConfig,
    *,
    system_prompt: str,
    user_prompt: str,
    compact: bool,
) -> dict[str, object]:
    normalized_system = _compact_prompt_text(system_prompt) if compact else system_prompt
    normalized_user = _compact_prompt_text(user_prompt) if compact else user_prompt
    return {
        "model": config.model,
        "temperature": config.temperature,
        "messages": [
            {"role": "system", "content": normalized_system},
            {"role": "user", "content": normalized_user},
        ],
    }


def _build_request_headers(api_key: str, provider: str) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
        "Connection": "close",
        "User-Agent": "ai4rws-paper-llm-client/1.0",
    }
    if _is_deepseek_provider(provider):
        headers["User-Agent"] = "ai4rws-paper-llm-client/1.0 deepseek"
    return headers


def _compact_prompt_text(text: str) -> str:
    compact = text.replace("\r\n", "\n")
    compact = re.sub(r"[ \t]+\n", "\n", compact)
    compact = re.sub(r"\n{3,}", "\n\n", compact)
    compact = re.sub(r"[ \t]{2,}", " ", compact)
    return compact.strip()


def _strip_code_fences(text: str) -> str:
    fenced = re.match(r"^```(?:[a-zA-Z0-9_-]+)?\s*(.*?)\s*```$", text, flags=re.DOTALL)
    return fenced.group(1).strip() if fenced else text


def _sanitize_llm_output(text: str, *, output_format: str) -> str:
    cleaned = _strip_code_fences(text).strip()
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL | re.IGNORECASE).strip()
    cleaned = re.sub(
        r"^(?:Here is .*?:|Below is .*?:|Let me create .*?:|Sure, here is .*?:)\s*",
        "",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    ).strip()
    if output_format == "latex":
        return cleaned
    if output_format == "markdown":
        return cleaned
    return cleaned


def _resolve_timeout_seconds(raw_value: object) -> int:
    try:
        timeout = int(str(raw_value).strip())
    except (TypeError, ValueError, AttributeError):
        return 300
    return max(timeout, 30)


def _resolve_timeout_seconds_for_provider(raw_value: object, *, provider: str) -> int:
    base_timeout = _resolve_timeout_seconds(raw_value)
    if _is_deepseek_provider(provider):
        return max(base_timeout, 480)
    return base_timeout


def _resolve_retry_count(raw_value: object, *, default: int) -> int:
    try:
        retry_count = int(str(raw_value).strip())
    except (TypeError, ValueError, AttributeError):
        return default
    return min(max(retry_count, 1), 5)


def _is_deepseek_provider(provider: str) -> bool:
    return "deepseek" in provider.casefold()


def _is_retryable_http_status(status_code: int) -> bool:
    return status_code in {408, 409, 425, 429} or status_code >= 500


def _is_retryable_transport_reason(reason: object) -> bool:
    normalized = str(reason).casefold()
    retryable_markers = (
        "remote end closed connection without response",
        "temporarily unavailable",
        "connection reset",
        "connection aborted",
        "connection error",
        "server disconnected",
        "eof occurred",
        "unexpected_eof",
        "ssl",
        "timed out",
        "timeout",
        "bad gateway",
        "service unavailable",
        "gateway timeout",
    )
    return any(marker in normalized for marker in retryable_markers)


def _sleep_before_retry(attempt: int, *, provider: str = "") -> None:
    if _is_deepseek_provider(provider):
        time.sleep(min(12, 2 + attempt * 2.5))
        return
    time.sleep(min(6, attempt * 1.5))


def _stage_error(
    *,
    intermediate_dir: Path,
    stage_slug: str,
    message: str,
    partial_artifacts: list[dict[str, str]],
) -> LLMStageError:
    error_path = intermediate_dir / f"{stage_slug}_error.txt"
    error_path.write_text(message, encoding="utf-8")
    return LLMStageError(
        message,
        intermediate_files=[
            *partial_artifacts,
            {"name": f"{stage_slug}_error", "path": str(error_path), "category": "llm"},
        ],
    )
