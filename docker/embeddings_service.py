import os
from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

MODEL_NAME = os.getenv("MODEL_NAME", "paraphrase-multilingual-MiniLM-L12-v2")
model = SentenceTransformer(MODEL_NAME)

app = FastAPI(title="Embeddings Service")


class EmbedRequest(BaseModel):
    texts: list[str]


class EmbedResponse(BaseModel):
    embeddings: list[list[float]]
    model: str


@app.post("/embed", response_model=EmbedResponse)
def embed(req: EmbedRequest) -> EmbedResponse:
    vecs = model.encode(req.texts, normalize_embeddings=True).tolist()
    return EmbedResponse(embeddings=vecs, model=MODEL_NAME)


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_NAME}
