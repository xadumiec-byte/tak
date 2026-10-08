"""Exercise the real pinned CPU service models; no generated-code execution."""
import asyncio
import gc
import importlib.util
import importlib.metadata
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

async def main():
    report = {}
    for name, relative in [('embedding', 'services/embedding/app.py'), ('reranker', 'services/reranker/app.py')]:
        start = time.monotonic()
        try:
            module = load(name, relative)
            if name == 'embedding':
                async with module.lifespan(module.app):
                    result = module.embed(module.Req(texts=['Paris is the capital of France.', 'Bananas are yellow.']))
                    assert len(result['vectors']) == 2 and len(result['vectors'][0]) == 1024
                    assert all(v['indices'] for v in result['sparse_vectors'])
                    report[name] = {'status': 'PASS', 'dense_dimension': 1024, 'sparse_nonempty': True, 'device': 'cpu'}
                    del module.app.state.model
            else:
                result = module.rerank(module.Req(query='What is the capital of France?', documents=['Paris is the capital of France.', 'Bananas are yellow.']))
                assert result['results'][0]['index'] == 0
                report[name] = {'status': 'PASS', 'ranking': result, 'device': 'cpu'}
                del module.model
            del module
            gc.collect()
        except Exception as exc:
            report[name] = {'status': 'FAIL', 'error': str(exc), 'exception': type(exc).__name__}
        report[name]['elapsed_s'] = round(time.monotonic() - start, 3)
        report[name]['revision'] = ('5617a9f61b028005a4858fdac845db406aefb181' if name == 'embedding'
                                    else '953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e')
        report[name]['packages'] = {package: importlib.metadata.version(package)
            for package in ['torch', 'transformers', 'FlagEmbedding', 'sentence-transformers', 'fastapi', 'pydantic']}
        (ROOT / 'reports/CPU_MODEL_SMOKE.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps({name: report[name]}), flush=True)
    return 0 if all(r['status'] == 'PASS' for r in report.values()) else 1

if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
