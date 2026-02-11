
# Nvdia api

```md
https://integrate.api.nvidia.com/v1
```

API KEY 1

```md
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
```

API KEY 2

```md
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
```

```py

import requests, base64

invoke_url = "https://integrate.api.nvidia.com/v1/chat/completions"
stream = True


headers = {
  "Authorization": "Bearer $NVIDIA_API_KEY",
  "Accept": "text/event-stream" if stream else "application/json"
}

payload = {
  "model": "moonshotai/kimi-k2.5",
  "messages": [{"role":"user","content":""}],
  "max_tokens": 16384,
  "temperature": 1.00,
  "top_p": 1.00,
  "stream": stream,
  "chat_template_kwargs": {"thinking":True},
}



response = requests.post(invoke_url, headers=headers, json=payload)

if stream:
    for line in response.iter_lines():
        if line:
            print(line.decode("utf-8"))
else:
    print(response.json())

```

```py
from openai import OpenAI
import json

client = OpenAI(
  base_url="https://integrate.api.nvidia.com/v1",
  api_key="$NVIDIA_API_KEY"
)

completion = client.chat.completions.create(
  model="qwen/qwen3-next-80b-a3b-instruct",
  messages=[{"role":"user","content":""}],
  temperature=0.6,
  top_p=0.7,
  max_tokens=4096,
  stream=True
)


for chunk in completion:
  if chunk.choices[0].delta.content:
    print(chunk.choices[0].delta.content, end="")


```

```
from openai import OpenAI

client = OpenAI(
  base_url = "https://integrate.api.nvidia.com/v1",
  api_key = "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"
)

completion = client.chat.completions.create(
  model="qwen/qwen3-coder-480b-a35b-instruct",
  messages=[{"role":"user","content":""}],
  temperature=0.7,
  top_p=0.8,
  max_tokens=4096,
  stream=True
)

for chunk in completion:
  if chunk.choices and chunk.choices[0].delta.content is not None:
    print(chunk.choices[0].delta.content, end="")


```
