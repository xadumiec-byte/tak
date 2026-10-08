import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from pydantic import BaseModel, Field

@asynccontextmanager
async def lifespan(app):
    from FlagEmbedding import BGEM3FlagModel
    from huggingface_hub import snapshot_download
    path = snapshot_download(os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3"),
        revision=os.getenv("EMBEDDING_MODEL_REVISION", "5617a9f61b028005a4858fdac845db406aefb181"),
        allow_patterns=["*.json","*.bin","*.pt","*.model","vocab*"])
    app.state.model = BGEM3FlagModel(path, devices="cpu", use_fp16=False)
    yield

app = FastAPI(lifespan=lifespan)
class Req(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=256)

@app.get("/health")
def health(): return {"status":"ok", "modes":["dense","sparse"]}

@app.post("/embed")
def embed(request: Req):
    output = app.state.model.encode(request.texts, batch_size=8, max_length=8192,
        return_dense=True, return_sparse=True, return_colbert_vecs=False)
    sparse=[]
    for weights in output["lexical_weights"]:
        entries=sorted((int(k),float(v)) for k,v in weights.items())
        sparse.append({"indices":[k for k,v in entries], "values":[v for k,v in entries]})
    return {"vectors":output["dense_vecs"].tolist(), "sparse_vectors":sparse}
