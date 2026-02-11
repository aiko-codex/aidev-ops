"""
NVIDIA AI Provider for AIDEV-OPS.

Wraps the OpenAI-compatible client for NVIDIA's integrate.api.nvidia.com/v1
endpoint. Handles streaming and non-streaming responses.
"""

from openai import OpenAI, APIError, RateLimitError, APIConnectionError
from src.logger import setup_logger


class NvidiaProvider:
    """
    NVIDIA API provider using OpenAI-compatible interface.

    Supports:
    - Chat completions (streaming and non-streaming)
    - Rate limit detection (429 errors)
    - Connection error handling
    """

    PROVIDER_NAME = "nvidia"

    def __init__(self, base_url, api_key, config):
        """
        Initialize the NVIDIA provider.

        Args:
            base_url: NVIDIA API base URL
            api_key: NVIDIA API key
            config: Application config dict
        """
        self.base_url = base_url
        self.api_key = api_key
        self.config = config
        self.logger = setup_logger('nvidia_provider', config)

        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key
        )

        # Track usage for this key
        self.request_count = 0
        self.error_count = 0
        self.last_error = None

    def chat(self, model, messages, temperature=0.7, top_p=0.8,
             max_tokens=4096, stream=False, extra_params=None):
        """
        Send a chat completion request.

        Args:
            model: Model identifier (e.g., 'moonshotai/kimi-k2.5')
            messages: List of message dicts [{"role": "...", "content": "..."}]
            temperature: Sampling temperature
            top_p: Top-p sampling
            max_tokens: Maximum response tokens
            stream: Whether to stream the response
            extra_params: Additional parameters (e.g., chat_template_kwargs)

        Returns:
            str: Complete response text (non-streaming) or generator (streaming)

        Raises:
            RateLimitError: When API quota is exceeded
            APIError: For other API errors
        """
        self.request_count += 1

        # Build request payload
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "stream": stream,
        }

        # Add extra parameters (e.g., thinking mode for Kimi)
        if extra_params:
            payload.update(extra_params)

        self.logger.debug(
            f"Sending request to {model} "
            f"(tokens={max_tokens}, stream={stream})"
        )

        try:
            completion = self.client.chat.completions.create(**payload)

            if stream:
                return self._handle_stream(completion)
            else:
                return self._handle_response(completion)

        except RateLimitError as e:
            self.error_count += 1
            self.last_error = str(e)
            self.logger.warning(f"Rate limit hit on key ...{self.api_key[-8:]}: {e}")
            raise

        except APIConnectionError as e:
            self.error_count += 1
            self.last_error = str(e)
            self.logger.error(f"Connection error: {e}")
            raise

        except APIError as e:
            self.error_count += 1
            self.last_error = str(e)
            self.logger.error(f"API error: {e}")
            raise

    def _handle_response(self, completion):
        """Extract text from a non-streaming response."""
        if completion.choices and completion.choices[0].message:
            return completion.choices[0].message.content or ""
        return ""

    def _handle_stream(self, completion):
        """Yield text chunks from a streaming response."""
        full_response = []
        for chunk in completion:
            if chunk.choices and chunk.choices[0].delta.content is not None:
                text = chunk.choices[0].delta.content
                full_response.append(text)
        return "".join(full_response)

    def health_check(self):
        """Quick health check — sends a minimal request."""
        try:
            response = self.chat(
                model="qwen/qwen3-next-80b-a3b-instruct",
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
                temperature=0.0
            )
            return {"status": "healthy", "response": response[:50]}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    @property
    def stats(self):
        """Return usage stats for this provider instance."""
        return {
            "provider": self.PROVIDER_NAME,
            "key_suffix": f"...{self.api_key[-8:]}",
            "requests": self.request_count,
            "errors": self.error_count,
            "last_error": self.last_error,
        }
