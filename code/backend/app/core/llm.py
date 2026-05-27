import os
from typing import Optional
from dotenv import load_dotenv, find_dotenv, dotenv_values
from openai import OpenAI
from typing import Callable, Dict, Any
try:
    from .audit import AuditLogger
    from .settings_manager import SettingsManager
except ImportError:
    # Fallback for direct script execution
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from core.audit import AuditLogger
    from core.settings_manager import SettingsManager


def _default_base_url_for_model(model: str) -> str | None:
    if "minimax" in (model or "").casefold():
        return "https://api.minimax.io/v1"
    return None


def show_loaded_envs(mask=True, interpolate=True, override=False):
    """
    返回本次 load_dotenv() 导入到 os.environ 的键值对。
    mask=True 时仅显示变量名或打码后的值。
    """
    env_path = find_dotenv(usecwd=True)
    # print("env_path:", env_path)
    # .env 中的“候选项”（不改环境）
    raw = dotenv_values(env_path, interpolate=interpolate)

    before = dict(os.environ)
    load_dotenv(dotenv_path=env_path, override=override)
    after = dict(os.environ)

    # 只统计 .env 里出现过的键，且值发生了变更或新增的
    changed = {}
    for k in raw.keys():
        if before.get(k) != after.get(k):
            v = after.get(k)
            if mask and v is not None:
                v = v[:2] + "****" + v[-2:] if len(v) > 4 else "****"
            changed[k] = v

    return changed


class LLMClient:
    """
    LLM客户端：优先使用环境变量中的OpenAI API Key。
    未配置时，退回占位响应以保证流程可运行。
    使用单例模式避免重复加载环境变量和初始化客户端。
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(LLMClient, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized") and self._initialized:
            return

        # 仅首次初始化时加载环境
        loaded = show_loaded_envs(mask=True, interpolate=True, override=True)
        print("Loaded envs:", loaded)
        
        self.settings_manager = SettingsManager()
        self._client = None
        self.api_key = None
        self.base_url = None
        self.model = None

        # Initial load from settings/env
        self._refresh_client_config()
        
        self._initialized = True
        try:
            self.audit_logger = AuditLogger()
        except Exception as e:
            print(f"AuditLogger init failed: {e}")
            self.audit_logger = None

    def _refresh_client_config(self):
        """
        Reload configuration from SettingsManager, falling back to env vars.
        Re-initializes OpenAI client if credentials change.
        """
        settings = self.settings_manager.get_settings()
        
        # 1. Determine Active Model
        # Priority: Settings > Env > Default
        active_model = settings.get("active_model")
        env_model = os.environ.get("OPENAI_API_MODEL")
        new_model = active_model or env_model or "gemini-3-pro-preview"
        
        # 2. Determine API Key
        api_keys = settings.get("api_keys", {})
        new_api_key = None
        
        # Try to find key based on model prefix
        normalized_model = new_model.casefold()
        if normalized_model.startswith("gpt") or "openai" in normalized_model:
            new_api_key = api_keys.get("openai")
        elif normalized_model.startswith("claude"):
            new_api_key = api_keys.get("anthropic")
        elif normalized_model.startswith("gemini"):
            new_api_key = api_keys.get("google")
        elif normalized_model.startswith("deepseek"):
            new_api_key = api_keys.get("deepseek")
        elif normalized_model.startswith("qwen"):
            new_api_key = api_keys.get("qwen")
        elif "minimax" in normalized_model:
            new_api_key = api_keys.get("minimax")
        
        # Fallback to generic if single key provided in map and we couldn't match prefix
        if not new_api_key and len(api_keys) == 1:
            new_api_key = list(api_keys.values())[0]
            
        # Fallback to Env
        if not new_api_key:
            new_api_key = os.environ.get("OPENAI_API_KEY")
            
        # 3. Determine Base URL
        # Priority: Settings > Env > Default
        settings_base_url = settings.get("api_base_url")
        env_base_url = os.environ.get("OPENAI_API_BASE_URL")
        new_base_url = settings_base_url or env_base_url or _default_base_url_for_model(new_model)
        
        # Check if re-init needed
        credentials_changed = (
            new_api_key != self.api_key or 
            new_base_url != self.base_url
        )
        
        self.model = new_model
        self.api_key = new_api_key
        self.base_url = new_base_url
        
        if credentials_changed:
            if self.api_key:
                try:
                    masked_key = self.api_key[:8] + "****" + self.api_key[-8:] if len(self.api_key) > 16 else "****"
                    print(f"[LLMClient] Re-initializing client. Model={self.model}, Key={masked_key}, Base URL={self.base_url}")
                    self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
                except Exception as e:
                    print(f"[LLMClient] OpenAI client init failed: {e}")
                    self._client = None
            else:
                self._client = None

    def generate(self, prompt: str = None, messages: list = None, model: Optional[str] = None, job_id: Optional[str] = None) -> str:
        self._refresh_client_config()
        if self._client is None:
            return "[LLM占位] 未配置OPENAI_API_KEY，返回占位文本。"

        try:
            msgs = messages if messages is not None else [{"role": "user", "content": prompt}]
            use_model = model or self.model
            resp = self._client.chat.completions.create(
                model=use_model,
                messages=msgs,
                temperature=1,
            )
            
            # Audit logging
            if self.audit_logger and hasattr(resp, "usage") and resp.usage:
                usage_dict = resp.usage.model_dump() if hasattr(resp.usage, "model_dump") else resp.usage.__dict__
                self.audit_logger.log_usage(
                    model=use_model, 
                    usage=usage_dict, 
                    job_id=job_id, 
                    endpoint="generate"
                )

            return resp.choices[0].message.content or ""
        except Exception as e:
            return f"[LLM错误] {e}"

    def generate_stream(self, prompt: str = None, messages: list = None, model: Optional[str] = None, on_chunk: Optional[Callable[[str], None]] = None, job_id: Optional[str] = None) -> str:
        """
        以流式方式生成内容：边接收边输出到控制台（或自定义回调），同时返回完整文本。
        on_chunk: 接收每个文本增量的回调；默认直接打印到stdout并flush。
        """
        self._refresh_client_config()
        if self._client is None:
            placeholder = "[LLM占位] 未配置OPENAI_API_KEY，返回占位文本。"
            if on_chunk:
                on_chunk(placeholder)
            else:
                try:
                    print(placeholder, end="", flush=True)
                except Exception:
                    pass
            return placeholder

        buf: list[str] = []
        try:
            msgs = messages if messages is not None else [{"role": "user", "content": prompt}]
            use_model = model or self.model
            # print(f"LLM请求 流式: {msgs}")
            
            extra_params = {}
            # Attempt to request usage stats for streaming
            try:
                extra_params["stream_options"] = {"include_usage": True}
            except:
                pass

            stream = self._client.chat.completions.create(
                model=use_model,
                messages=msgs,
                temperature=1,
                stream=True,
                **extra_params
            )
            
            usage_collected = None

            for event in stream:
                # 兼容不同版本的事件结构
                chunk = None
                try:
                    # Capture usage if present (usually in last chunk)
                    if hasattr(event, "usage") and event.usage:
                        usage_collected = event.usage
                    
                    # 新版事件类型判断
                    if getattr(event, "type", None) == "chat.completion.chunk":
                        if event.choices and len(event.choices) > 0:
                            chunk = getattr(event.choices[0].delta, "content", None)
                    else:
                        # 旧版直接choices[0].delta.content
                        if event.choices and len(event.choices) > 0:
                            chunk = getattr(event.choices[0].delta, "content", None)
                except Exception:
                    pass
                
                if not chunk:
                    continue

                buf.append(chunk)
                if on_chunk:
                    try:
                        on_chunk(chunk)
                    except Exception:
                        pass
                else:
                    try:
                        print(chunk, end="", flush=True)
                    except Exception:
                        pass
            
            # Log collected usage
            if self.audit_logger and usage_collected:
                usage_dict = usage_collected.model_dump() if hasattr(usage_collected, "model_dump") else usage_collected.__dict__
                self.audit_logger.log_usage(
                    model=use_model, 
                    usage=usage_dict, 
                    job_id=job_id, 
                    endpoint="generate_stream"
                )

            # 最后打印换行，避免日志挤在一行
            try:
                if not on_chunk:
                    print("")
            except Exception:
                pass
            return "".join(buf)
        except Exception as e:
            err = f"[LLM错误] {e}"
            if on_chunk:
                on_chunk(err)
            else:
                try:
                    print(err)
                except Exception:
                    pass
            return err

    def stream_iter(self, prompt: str = None, messages: list = None, model: Optional[str] = None, job_id: Optional[str] = None):
        """
        返回一个生成器，逐步yield文本片段，用于服务端流式输出。
        """
        self._refresh_client_config()
        if self._client is None:
            yield "[LLM占位] 未配置OPENAI_API_KEY，返回占位文本。"
            return
        try:
            msgs = messages if messages is not None else [{"role": "user", "content": prompt}]
            use_model = model or self.model
            
            extra_params = {}
            try:
                extra_params["stream_options"] = {"include_usage": True}
            except:
                pass

            stream = self._client.chat.completions.create(
                model=use_model,
                messages=msgs,
                temperature=1,
                stream=True,
                **extra_params
            )
            
            usage_collected = None
            
            for event in stream:
                chunk = None
                try:
                    if hasattr(event, "usage") and event.usage:
                        usage_collected = event.usage

                    if getattr(event, "type", None) == "chat.completion.chunk":
                        if event.choices and len(event.choices) > 0:
                            chunk = getattr(event.choices[0].delta, "content", None)
                    else:
                        if event.choices and len(event.choices) > 0:
                            chunk = getattr(event.choices[0].delta, "content", None)
                except Exception:
                    chunk = None
                if chunk:
                    yield chunk
            
            # Log usage after stream ends
            if self.audit_logger and usage_collected:
                usage_dict = usage_collected.model_dump() if hasattr(usage_collected, "model_dump") else usage_collected.__dict__
                self.audit_logger.log_usage(
                    model=use_model, 
                    usage=usage_dict, 
                    job_id=job_id, 
                    endpoint="stream_iter"
                )

        except Exception as e:
            yield f"[LLM错误] {e}"

    def generate_with_images(self, prompt: str, image_paths: list[str] | None = None, image_urls: list[str] | None = None, model: Optional[str] = None, job_id: Optional[str] = None) -> str:
        """
        使用支持视觉的模型进行多模态生成：文本 + 图像。

        - image_paths: 本地图片路径列表（将被读取并以 data URI 形式附加）
        - image_urls: 可直接访问的图片URL列表（如CDN或公网地址）
        """
        self._refresh_client_config()
        if self._client is None:
            return "[LLM占位] 未配置OPENAI_API_KEY，返回占位文本。"

        try:
            contents = [{"type": "text", "text": prompt}]
            # 附加本地图片为data URI
            import base64
            import mimetypes
            for p in (image_paths or []):
                try:
                    with open(p, "rb") as f:
                        data = f.read()
                    b64 = base64.b64encode(data).decode("utf-8")
                    mime = mimetypes.guess_type(p)[0] or "image/png"
                    url = f"data:{mime};base64,{b64}"
                    contents.append({"type": "image_url", "image_url": {"url": url, "detail": "high"}})
                except Exception:
                    # 单张失败不影响整体
                    pass
            # 附加远程图片URL
            for u in (image_urls or []):
                contents.append({"type": "image_url", "image_url": {"url": u, "detail": "high"}})

            use_model = model or self.model
            resp = self._client.chat.completions.create(
                model=use_model,
                messages=[{"role": "user", "content": contents}],
                temperature=1,
            )
            
            # Audit logging
            if self.audit_logger and hasattr(resp, "usage") and resp.usage:
                usage_dict = resp.usage.model_dump() if hasattr(resp.usage, "model_dump") else resp.usage.__dict__
                self.audit_logger.log_usage(
                    model=use_model, 
                    usage=usage_dict, 
                    job_id=job_id, 
                    endpoint="generate_with_images"
                )

            return resp.choices[0].message.content or ""
        except Exception as e:
            return f"[LLM错误] {e}"
