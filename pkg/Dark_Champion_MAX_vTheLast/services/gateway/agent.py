import json,os,re,httpx
from fastapi import HTTPException
VLLM_BASE_URL=os.getenv("VLLM_BASE_URL","http://host.docker.internal:8000/v1")
VLLM_API_KEY=os.getenv("VLLM_API_KEY",""); VLLM_MODEL=os.getenv("VLLM_MODEL","")
SANDBOX_URL=os.getenv("SANDBOX_URL","http://code-sandbox:8091"); RESEARCH_URL=os.getenv("RESEARCH_URL","http://research:8090")
TOOLS=[
{"type":"function","function":{"name":"execute_code","description":"Execute Python in isolated networkless sandbox.","parameters":{"type":"object","properties":{"code":{"type":"string"},"timeout":{"type":"integer"}},"required":["code"]}}},
{"type":"function","function":{"name":"submit_research","description":"Submit web research job.","parameters":{"type":"object","properties":{"question":{"type":"string"}},"required":["question"]}}},
{"type":"function","function":{"name":"research_status","description":"Check research job.","parameters":{"type":"object","properties":{"job_id":{"type":"string"}},"required":["job_id"]}}}]
async def tool(name,args):
    async with httpx.AsyncClient(timeout=45) as c:
        if name=="execute_code": r=await c.post(f"{SANDBOX_URL}/execute",json=args,headers={"Authorization":f"Bearer {os.environ['SANDBOX_API_KEY']}"})
        elif name=="submit_research": r=await c.post(f"{RESEARCH_URL}/research",json={"question":args["question"]})
        elif name=="research_status": r=await c.get(f"{RESEARCH_URL}/research/{args['job_id']}")
        else:return {"error":"unknown tool"}
        r.raise_for_status(); return r.json()
AGENT_POLICY = """When the user requests code execution or research, call the corresponding
available tool before explaining its result. Emit calls as <tool_call> containing
JSON with name and arguments, followed by </tool_call>. The <tools> tag defines
available functions; it is never a call. Never claim a tool executed before its
result arrives. After receiving its result, explain it without repeating the call."""

def requested_tool_choice(messages):
    """Honor a positive, explicit user command naming a registered tool."""
    names=[tool['function']['name'] for tool in TOOLS]
    pattern=r'^\s*(?:please\s+)?(?:use|call|run)\s+(?:the\s+)?('+'|'.join(map(re.escape,names))+r')\b'
    for message in reversed(messages):
        if message.get('role')!='user':continue
        content=message.get('content')
        match=re.match(pattern,content,re.IGNORECASE) if isinstance(content,str) else None
        if match:return {'type':'function','function':{'name':match.group(1).lower()}}
        break
    return 'auto'

async def run_agent(messages,max_steps=8):
    history=[dict(message) for message in messages]
    if history and history[0].get('role')=='system':
        history[0]['content']=str(history[0].get('content') or '')+'\n\n'+AGENT_POLICY
    else:
        history.insert(0,{'role':'system','content':AGENT_POLICY})
    headers={"Authorization":f"Bearer {VLLM_API_KEY}"}; trace=[]
    async with httpx.AsyncClient(timeout=180) as c:
        for step in range(max_steps):
            prompt_bound=len(json.dumps(history,ensure_ascii=False).encode())+512*len(history)+2048
            if prompt_bound>int(os.getenv('VLLM_MAX_MODEL_LEN','32768')):
                raise HTTPException(413,'Agent context budget exhausted')
            r=await c.post(f"{VLLM_BASE_URL}/chat/completions",headers=headers,json={"model":VLLM_MODEL,"messages":history,"tools":TOOLS,"tool_choice":requested_tool_choice(messages) if step==0 else "auto","temperature":0.2,"max_tokens":2048})
            r.raise_for_status(); msg=r.json()["choices"][0]["message"]; history.append(msg)
            calls=msg.get("tool_calls") or []
            if not calls:return {"message":msg,"steps":step+1,"tool_trace":trace}
            for call in calls:
                try: result=await tool(call["function"]["name"],json.loads(call["function"].get("arguments") or "{}"))
                except Exception as e: result={"error":str(e)}
                trace.append({'tool_call':call,'result':result})
                history.append({"role":"tool","tool_call_id":call["id"],"content":json.dumps(result,ensure_ascii=False)})
    return {"message":{"role":"assistant","content":"Agent step budget exhausted."},"steps":max_steps,"tool_trace":trace,"error":"step_budget_exhausted"}
