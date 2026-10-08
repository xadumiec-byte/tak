from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import CrossEncoder
import os
from huggingface_hub import snapshot_download
app=FastAPI()
model=CrossEncoder(snapshot_download(os.getenv("RERANKER_MODEL","BAAI/bge-reranker-v2-m3"),
    revision=os.getenv("RERANKER_MODEL_REVISION","953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"),
    allow_patterns=["*.json","*.safetensors","*.model","vocab*"]), device="cpu")
class Req(BaseModel): query:str; documents:list[str]
@app.get("/health")
def health(): return {"status":"ok"}
@app.post("/rerank")
def rerank(r:Req):
    scores=model.predict([(r.query,d) for d in r.documents]).tolist()
    order=sorted(range(len(scores)), key=lambda i:scores[i], reverse=True)
    return {"results":[{"index":i,"score":float(scores[i])} for i in order]}
