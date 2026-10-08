"""Networkless static Crawl4AI extraction; HTML fetching belongs to the pinned fetcher."""
import os
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

app=FastAPI()
class Extract(BaseModel):
    url:str=Field(max_length=4096)
    html:str=Field(max_length=2000000)

@app.get('/health')
def health():
    from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
    from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
    return {'status':'ok','mode':'static-no-browser'}

@app.post('/extract')
def extract(request:Extract,authorization:str|None=Header(default=None)):
    if authorization != 'Bearer '+os.environ['CRAWL4AI_API_TOKEN']:
        raise HTTPException(401,'Invalid crawler key')
    from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
    from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
    from lxml import html
    tree=html.fragment_fromstring(request.html,create_parent='div')
    allowed={'html','body','main','article','section','div','span','p','a','h1','h2','h3','h4','h5','h6',
             'ul','ol','li','dl','dt','dd','table','thead','tbody','tr','td','th','pre','code','blockquote',
             'br','hr','strong','b','i','em'}
    for element in list(tree.iter()):
        if element.tag not in allowed:
            if element is not tree: element.drop_tree()
        else:
            for attr in list(element.attrib):
                if attr != 'href' or element.tag != 'a': del element.attrib[attr]
    sanitized=html.tostring(tree,encoding='unicode')
    result=LXMLWebScrapingStrategy().scrap(request.url,sanitized,
        excluded_tags=['script','style','iframe','object','embed','form','nav','footer'],
        word_count_threshold=1)
    markdown=DefaultMarkdownGenerator().generate_markdown(result.cleaned_html,base_url=request.url,citations=False)
    return {'markdown':markdown.raw_markdown[:12000]}
