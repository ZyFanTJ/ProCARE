import os
from typing import Optional
from dotenv import load_dotenv, find_dotenv, dotenv_values
from openai import OpenAI
from typing import Callable


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
    """

    def __init__(self):
        loaded = show_loaded_envs(mask=True, interpolate=True, override=True)
        print("Loaded envs:", loaded)
        self.api_key = os.environ.get("OPENAI_API_KEY")
        self.base_url = os.environ.get("OPENAI_API_BASE_URL")
        self.model = os.environ.get("OPENAI_API_MODEL")

        # 输出apikey前4位和后四位
        print("Loaded API key:", self.api_key[:8] + "****" + self.api_key[-8:] if self.api_key else None)
        print("Base URL:", self.base_url)

        self._client = None
        if self.api_key:
            try:
                self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            except Exception as e:
                print(f"OpenAI客户端初始化失败: {e}")
                self._client = None

    def generate(self, prompt: str, model: Optional[str] = None) -> str:
        if self._client is None:
            return "[LLM占位] 未配置OPENAI_API_KEY，返回占位文本。"

        try:
            resp = self._client.chat.completions.create(
                model=model or self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=1,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            return f"[LLM错误] {e}"

    def generate_stream(self, prompt: str, model: Optional[str] = None, on_chunk: Optional[Callable[[str], None]] = None) -> str:
        """
        以流式方式生成内容：边接收边输出到控制台（或自定义回调），同时返回完整文本。
        on_chunk: 接收每个文本增量的回调；默认直接打印到stdout并flush。
        """
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
            print(f"LLM请求 流式: {prompt}")
            stream = self._client.chat.completions.create(
                model=model or self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=1,
                stream=True,
            )
            for event in stream:
                # 兼容不同版本的事件结构
                chunk = None
                try:
                    # 新版事件类型判断
                    if getattr(event, "type", None) == "chat.completion.chunk":
                        chunk = getattr(event.choices[0].delta, "content", None)
                    else:
                        # 旧版直接choices[0].delta.content
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

    def stream_iter(self, prompt: str, model: Optional[str] = None):
        """
        返回一个生成器，逐步yield文本片段，用于服务端流式输出。
        """
        if self._client is None:
            yield "[LLM占位] 未配置OPENAI_API_KEY，返回占位文本。"
            return
        try:
            stream = self._client.chat.completions.create(
                model=model or self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=1,
                stream=True,
            )
            for event in stream:
                chunk = None
                try:
                    if getattr(event, "type", None) == "chat.completion.chunk":
                        chunk = getattr(event.choices[0].delta, "content", None)
                    else:
                        chunk = getattr(event.choices[0].delta, "content", None)
                except Exception:
                    chunk = None
                if chunk:
                    yield chunk
        except Exception as e:
            yield f"[LLM错误] {e}"

    def generate_with_images(self, prompt: str, image_paths: list[str] | None = None, image_urls: list[str] | None = None, model: Optional[str] = None) -> str:
        """
        使用支持视觉的模型进行多模态生成：文本 + 图像。

        - image_paths: 本地图片路径列表（将被读取并以 data URI 形式附加）
        - image_urls: 可直接访问的图片URL列表（如CDN或公网地址）
        """
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

            resp = self._client.chat.completions.create(
                model=model or self.model,
                messages=[{"role": "user", "content": contents}],
                temperature=1,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            return f"[LLM错误] {e}"
