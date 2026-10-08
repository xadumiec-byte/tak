"""Bounded real research acquisition reproduction; never certifies a live gate."""
import asyncio
import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services/research'))
import app as research

async def main():
    question = 'According to https://docs.python.org/3/library/asyncio.html what is asyncio used for?'
    output = {'question': question, 'queries': [], 'status': 'DIAGNOSTIC'}
    output['model_outputs'] = []
    original_llm = research.llm
    async def traced_llm(*args, **kwargs):
        answer = await original_llm(*args, **kwargs)
        output['model_outputs'].append({'max_tokens': kwargs.get('max_tokens'), 'answer': answer})
        (ROOT / 'reports/RESEARCH_ACQUISITION_REPRO.json').write_text(json.dumps(output, indent=2), encoding='utf-8')
        return answer
    research.llm = traced_llm
    try:
        if '--lifecycle' in sys.argv:
            output['pipeline_result'] = await research.run_research(research.ResearchRequest(
                question=question, max_rounds=1, queries_per_round=2, results_per_query=2))
            (ROOT / 'reports/RESEARCH_ACQUISITION_REPRO.json').write_text(json.dumps(output, indent=2), encoding='utf-8')
            print(json.dumps(output, indent=2), flush=True)
            return
        queries = await research.plan_queries(question, 2)
        for query in queries:
            row = {'query': query}
            async with research.httpx.AsyncClient(timeout=research.TIMEOUT) as client:
                response = await client.get(research.SEARXNG_URL + '/search', params={
                    'q': query, 'format': 'json', 'language': 'all', 'safesearch': 0})
                response.raise_for_status()
                data = response.json()
                row.update(raw_result_count=len(data.get('results', [])),
                    unresponsive_engines=data.get('unresponsive_engines', []))
            sources = await research.search(query, 2)
            row['accepted_urls'] = [source.url for source in sources]
            row['fetched'] = []
            for source in sources:
                try:
                    html, url = await research.fetch_html(source.url)
                    row['fetched'].append({'url': url, 'html_chars': len(html)})
                    crawled = await research.crawl(source)
                    row['fetched'][-1]['extracted_chars'] = len(crawled.text)
                except Exception:
                    row['fetched'].append({'url': source.url, 'error': traceback.format_exc()})
            output['queries'].append(row)
    except Exception:
        output['error'] = traceback.format_exc()
    (ROOT / 'reports/RESEARCH_ACQUISITION_REPRO.json').write_text(json.dumps(output, indent=2), encoding='utf-8')
    print(json.dumps(output, indent=2), flush=True)

if __name__ == '__main__':
    asyncio.run(main())
