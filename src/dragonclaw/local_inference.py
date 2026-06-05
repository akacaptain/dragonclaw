"""Load and run the DragonClaw local language model (base instruct only at ship)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from dragonclaw.inference_capability import DEFAULT_BASE_MODEL

_ENGINE: "LocalInferenceEngine | None" = None
_ENGINE_KEY: str | None = None


class LocalInferenceError(RuntimeError):
    pass


def use_adapter_enabled() -> bool:
    """LoRA adapter is opt-in only; base instruct is the ship default."""
    return os.environ.get("DRAGONCLAW_USE_ADAPTER", "").strip().lower() in {"1", "true", "yes"}


def _configure_inference_logging() -> None:
    import logging
    import warnings

    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    logging.getLogger("transformers").setLevel(logging.ERROR)
    warnings.filterwarnings("ignore", message=".*clean_up_tokenization_spaces.*")


def _load_tokenizer(base_model: str):
    from transformers import AutoTokenizer

    _configure_inference_logging()
    return AutoTokenizer.from_pretrained(
        base_model,
        trust_remote_code=True,
        clean_up_tokenization_spaces=False,
    )


def _require_runtime_deps() -> None:
    missing = []
    for name in ("torch", "transformers"):
        try:
            __import__(name)
        except ImportError:
            missing.append(name)
    if missing:
        raise LocalInferenceError(
            "Local model runtime requires PyTorch + Transformers. "
            f'Install with: pip install -e ".[runtime]" (missing: {", ".join(missing)})'
        )


def _pick_device_and_dtype():
    import torch

    if torch.cuda.is_available():
        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        return "cuda", dtype
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps", torch.float16
    return "cpu", torch.float32


@dataclass
class LocalInferenceEngine:
    model_label: str
    base_model: str
    device: str
    model: Any
    tokenizer: Any

    @classmethod
    def load(cls, *, base_model: str | None = None) -> "LocalInferenceEngine":
        if use_adapter_enabled():
            raise LocalInferenceError(
                "LoRA adapters are not shipped in this build. "
                "Unset DRAGONCLAW_USE_ADAPTER or use cloud assistant."
            )

        _require_runtime_deps()
        _configure_inference_logging()
        import torch
        from transformers import AutoModelForCausalLM

        resolved_base = base_model or os.environ.get("DRAGONCLAW_BASE_MODEL", DEFAULT_BASE_MODEL)
        device, dtype = _pick_device_and_dtype()
        tokenizer = _load_tokenizer(resolved_base)
        load_kw: dict[str, Any] = {"dtype": dtype, "trust_remote_code": True}
        if device == "cuda":
            load_kw["device_map"] = "auto"
        model = AutoModelForCausalLM.from_pretrained(resolved_base, **load_kw)
        if device != "cuda":
            model = model.to(device)

        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        model.eval()

        return cls(
            model_label=f"base:{resolved_base}",
            base_model=resolved_base,
            device=device,
            model=model,
            tokenizer=tokenizer,
        )

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_new_tokens: int | None = None,
        temperature: float = 0.1,
    ) -> str:
        import warnings

        import torch

        _configure_inference_logging()
        warnings.filterwarnings(
            "ignore",
            message=".*copy construct from a tensor.*",
            category=UserWarning,
        )

        if getattr(self.tokenizer, "chat_template", None) is None:
            raise LocalInferenceError("Tokenizer has no chat_template.")

        max_new = max_new_tokens or int(os.environ.get("DRAGONCLAW_MAX_NEW_TOKENS", "384"))
        prompt_text = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = self.tokenizer(
            prompt_text,
            return_tensors="pt",
            truncation=True,
            max_length=int(os.environ.get("DRAGONCLAW_MAX_INPUT_TOKENS", "4096")),
        )
        inputs = {k: v.to(self.model.device) for k, v in inputs.items()}

        gen_kw: dict[str, Any] = {
            "max_new_tokens": max_new,
            "do_sample": temperature > 0,
            "pad_token_id": self.tokenizer.pad_token_id,
            "eos_token_id": self.tokenizer.eos_token_id,
        }
        if temperature > 0:
            gen_kw["temperature"] = temperature

        with torch.inference_mode():
            output = self.model.generate(**inputs, **gen_kw)

        new_tokens = output[0, inputs["input_ids"].shape[1] :]
        return self.tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


def get_inference_engine(*, base_model: str | None = None) -> LocalInferenceEngine:
    global _ENGINE, _ENGINE_KEY
    resolved = base_model or os.environ.get("DRAGONCLAW_BASE_MODEL", DEFAULT_BASE_MODEL)
    if _ENGINE is None or _ENGINE_KEY != resolved:
        _ENGINE = LocalInferenceEngine.load(base_model=resolved)
        _ENGINE_KEY = resolved
    return _ENGINE


def complete_chat(
    messages: list[dict[str, str]],
    *,
    base_model: str | None = None,
) -> str:
    return get_inference_engine(base_model=base_model).generate(messages)


def reset_inference_engine() -> None:
    global _ENGINE, _ENGINE_KEY
    _ENGINE = None
    _ENGINE_KEY = None
