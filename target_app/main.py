from fastapi import FastAPI, HTTPException
from openai import OpenAI
from pydantic import BaseModel

from .configs import resolve
from .rag import retrieve

app = FastAPI(title="AcmeBank Target Bot")
client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")


class ChatRequest(BaseModel):
    prompt: str
    config_id: str = "v1"
    include_poisoned: bool = True


class ChatResponse(BaseModel):
    response: str
    retrieved_context: list[str]
    poisoned_doc_retrieved: bool
    config_id: str
    model: str


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    config = resolve(req.config_id)
    if config is None:
        raise HTTPException(404, f"Unknown config_id: {req.config_id}")

    docs = retrieve(req.prompt, include_poisoned=req.include_poisoned)

    if not docs:
        context_block = "(no documents found)"
    elif config["wrap_docs"]:
        context_block = "\n".join(
            f"<untrusted_document id=\"{d['id']}\">\n{d['text']}\n</untrusted_document>" for d in docs
        )
    else:
        context_block = "\n".join(f"[{d['id']}] {d['text']}" for d in docs)

    messages = [
        {"role": "system", "content": config["system_prompt"]},
        {"role": "user", "content": f"Documents:\n{context_block}\n\nCustomer question: {req.prompt}"},
    ]
    resp = client.chat.completions.create(
        model=config["model"], messages=messages, temperature=0
    )
    return ChatResponse(
        response=resp.choices[0].message.content,
        retrieved_context=[d["text"] for d in docs],
        poisoned_doc_retrieved=any(d.get("poisoned") for d in docs),
        config_id=req.config_id,
        model=config["model"],
    )


@app.get("/health")
def health():
    return {"status": "ok"}