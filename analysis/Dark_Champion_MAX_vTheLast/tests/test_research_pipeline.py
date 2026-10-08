import asyncio
import importlib.util
import sys
from pathlib import Path
import pytest

def load(monkeypatch):
    directory=Path(__file__).parents[1]/'services/research'
    monkeypatch.syspath_prepend(str(directory))
    monkeypatch.setenv('CRAWL4AI_API_TOKEN','test')
    spec=importlib.util.spec_from_file_location('research_pipeline_test',directory/'app.py')
    module=importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules,spec.name,module)
    spec.loader.exec_module(module)
    return module

def test_research_full_local_contract_and_citations(monkeypatch):
    app=load(monkeypatch)
    indexed=[]
    async def plan(*args,**kwargs): return ['query']
    async def search(*args): return [app.Source('Source','https://example.org/?utm_source=x#fragment')]
    async def crawl(source,**kwargs): source.text='Public source evidence. '*100; return source
    async def gaps(*args): return 'SUFFICIENT'
    async def index(chunks): indexed.extend(chunks)
    async def retrieve(question,job_id,attempt_id):
        assert job_id=='job-A'
        return [vars(c)|{'chunk_id':c.id} for c in indexed]
    async def llm(messages,**kwargs):
        assert messages[0]['role']=='system' and 'untrusted_evidence' in messages[-1]['content']
        return 'Supported answer [1].'
    for name,fn in [('plan_queries',plan),('search',search),('crawl',crawl),('identify_gaps',gaps),
                    ('index_chunks',index),('retrieve',retrieve),('llm',llm)]: monkeypatch.setattr(app,name,fn)
    result=asyncio.run(app.run_research(app.ResearchRequest(question='Question?'),'job-A'))
    assert result['retrieval_mode']=='dense+sparse+rrf+reranker'
    assert result['citations']['1']['chunk_id']==indexed[0].id
    assert result['citations']['1']['url']=='https://example.org/'
    assert indexed[0].job_id=='job-A'

def test_synthesis_rejects_nonexistent_citation(monkeypatch):
    app=load(monkeypatch)
    async def llm(*args,**kw):return 'Invented [999].'
    monkeypatch.setattr(app,'llm',llm)
    with pytest.raises(ValueError):
        asyncio.run(app.synthesize('question',[{'chunk_id':'c1','url':'https://example.org','text':'evidence'}]))

def test_modal_research_generation_caps_are_applied(monkeypatch):
    for key, value in {
        'RESEARCH_QUERY_MAX_TOKENS':'300',
        'RESEARCH_GAP_MAX_TOKENS':'300',
        'RESEARCH_ANSWER_MAX_TOKENS':'2000',
    }.items():
        monkeypatch.setenv(key, value)
    app=load(monkeypatch)
    calls=[]
    async def llm(messages, **kwargs):
        calls.append(kwargs['max_tokens'])
        return '["query"]' if len(calls)==1 else ('SUFFICIENT' if len(calls)==2 else 'Supported [1].')
    monkeypatch.setattr(app,'llm',llm)
    monkeypatch.setattr(app,'bounded_context',lambda *args,**kwargs:{
        'messages':[{'role':'user','content':'question'}], 'citations':{'1':{'url':'https://example.org'}},
        'prompt_tokens':1,'generation_reserve':2000,'estimator':'test'})
    assert asyncio.run(app.plan_queries('Question?',1)) == ['query']
    assert asyncio.run(app.identify_gaps('Question?',[app.Source('Source','https://example.org','evidence')])) == 'SUFFICIENT'
    result=asyncio.run(app.synthesize('Question?',[{'chunk_id':'c1','url':'https://example.org','text':'evidence'}]))
    assert calls == [300,300,2000]
    assert result['used_citations'] == ['1']

def test_explicit_source_survives_empty_search(monkeypatch):
    app=load(monkeypatch)
    url='https://docs.python.org/3/library/asyncio.html'
    crawled=[]; indexed=[]
    async def plan(*args,**kw):return ['query']
    async def search(*args):return []
    async def crawl(source,**kw):
        crawled.append(source.url);source.text='asyncio provides concurrent asynchronous I/O. '*100;return source
    async def gaps(*args):return 'SUFFICIENT'
    async def index(chunks):indexed.extend(chunks)
    async def retrieve(*args,**kw):return [vars(c)|{'chunk_id':c.id} for c in indexed]
    async def llm(*args,**kw):return 'Concurrent asynchronous I/O [1].'
    for name,fn in [('plan_queries',plan),('search',search),('crawl',crawl),('identify_gaps',gaps),
                    ('index_chunks',index),('retrieve',retrieve),('llm',llm)]:monkeypatch.setattr(app,name,fn)
    result=asyncio.run(app.run_research(app.ResearchRequest(question=f'According to {url} what is asyncio?')))
    assert crawled==[url]
    assert result['citations']['1']['url']==url

@pytest.mark.parametrize('url',['http://127.0.0.1/','http://169.254.169.254/',
    'https://user:password@example.org/','https://example.org:8090/'])
def test_explicit_sources_reject_unsafe_targets(monkeypatch,url):
    assert load(monkeypatch).explicit_sources('Read '+url)==[]
