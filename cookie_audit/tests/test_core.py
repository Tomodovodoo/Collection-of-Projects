import asyncio
from pathlib import Path
from types import SimpleNamespace

from audit import choice_kind,button_visibility,detect_event,registrar,run_one
from export import aggregate


def test_buttons():
    assert choice_kind('Accepteer alles')=='accept'
    assert choice_kind('Alles accepteren')=='accept'
    assert choice_kind('Weiger alles')=='reject'
    assert choice_kind('Doorgaan zonder accepteren')=='reject'
    assert choice_kind('Reject all')=='reject'
    assert choice_kind('Instellingen')=='settings'
    assert choice_kind('Cookiebeleid')=='other'


def test_tracker_endpoint_narrow():
    assert detect_event('https://www.google-analytics.com/g/collect?v=2')=='Google Analytics collection'
    assert detect_event('https://www.googletagmanager.com/gtm.js?id=GTM-123') is None
    assert detect_event('https://www.facebook.com/tr?id=1')=='Meta Pixel event'
    assert detect_event('https://mybank.nl/logo.jpg') is None


def test_cookie_domain():
    assert registrar('www.ad.nl')=='ad.nl'
    assert registrar('sub.example.co.uk')=='example.co.uk'


def test_visual_link():
    a={'tag':'button','rect':{'w':220,'h':50},'fontSize':16,'bg':'rgb(0, 0, 200)'}
    r={'tag':'a','rect':{'w':80,'h':14},'fontSize':12,'bg':'rgba(0, 0, 0, 0)','inViewport':True}
    assert button_visibility(r,a)[0]=='fail'


def test_export_unknown_without_measurements():
    rows=aggregate([{'domain':'example.nl','url':'https://example.nl','name':'Example','consortium':'Unknown','rank':1}],[])
    assert rows[0]['status']=='unknown'
    assert set(x['status'] for x in rows[0]['checks'].values())=={'unknown'}


def test_fixture_browser():
    # In restricted CI environments, navigation to file:// and localhost can be
    # blocked by browser policy. Render controlled fixtures with set_content.
    from playwright.async_api import async_playwright
    from audit import inspect, find_choice, click_choice
    async def test():
        async with async_playwright() as p:
            browser=await p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--disable-dev-shm-usage'])
            try:
                folder=Path(__file__).resolve().parent/'fixtures'
                findings={}
                for fname in ['good','badsteps','badlink','badtracker','nobanner']:
                    page=await browser.new_page(viewport={'width':1365,'height':900})
                    html=(folder/(fname+'.html')).read_text()
                    # about:blank has no localStorage; substitute an in-memory mock.
                    html=html.replace('<script>','<script>window.fakeStorage={getItem(){return null},setItem(){}};').replace('localStorage.','fakeStorage.')
                    await page.set_content(html,wait_until='domcontentloaded')
                    initial=await inspect(page)
                    findings[fname]={'state':initial,'accept':find_choice(initial,'accept'),'reject':find_choice(initial,'reject')}
                    if fname=='good':
                        assert initial['banner']
                        assert findings[fname]['accept'] and findings[fname]['reject']
                        assert await click_choice(findings[fname]['reject'])
                    elif fname=='badsteps':
                        assert initial['banner']
                        assert findings[fname]['accept'] and not findings[fname]['reject']
                        assert await click_choice(find_choice(initial,'settings'))
                        second=await inspect(page)
                        assert find_choice(second,'reject')
                        assert await click_choice(find_choice(second,'reject'))
                    elif fname=='badlink':
                        from audit import button_visibility
                        assert button_visibility(findings[fname]['reject'],findings[fname]['accept'])[0]=='fail'
                    elif fname=='nobanner':
                        assert not initial['banner']
                    await page.close()
            finally:
                await browser.close()
    asyncio.run(test())