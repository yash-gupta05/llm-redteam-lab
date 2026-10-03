from fastapi import FastAPI, HTTPException
from openai import OpenAI
from pydantic import BaseModel

from .configs import CONFIGS
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
    config = CONFIGS.get(req.config_id)
    if config is None:
        raise HTTPException(404, f"Unknown config_id: {req.config_id}")

    # Step 1: retrieve documents (this line must come BEFORE docs is used below)
    docs = retrieve(req.prompt, include_poisoned=req.include_poisoned)

    # Step 2: paste them into the prompt
    context_block = "\n".join(f"[{d['id']}] {d['text']}" for d in docs) or "(no documents found)"

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