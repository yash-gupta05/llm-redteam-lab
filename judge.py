import json

from deepeval.models import DeepEvalBaseLLM
from openai import OpenAI


class OllamaJudge(DeepEvalBaseLLM):
    """Lets DeepEval use a local Ollama model as the judge."""

    def __init__(self, model_name: str = "qwen2.5:7b"):
        self.model_name = model_name
        self.client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

    def load_model(self):
        return self.client

    def generate(self, prompt: str, schema=None):
        kwargs = {}
        if schema is not None:
            # Constrain the output to the JSON shape DeepEval expects.
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "output", "schema": schema.model_json_schema()},
            }
        resp = self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            **kwargs,
        )
        text = resp.choices[0].message.content
        if schema is not None:
            return schema.model_validate_json(text)   # return a parsed object, not raw text
        return text

    async def a_generate(self, prompt: str, schema=None):
        return self.generate(prompt, schema)

    def get_model_name(self) -> str:
        return self.model_name