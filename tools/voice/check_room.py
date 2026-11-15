"""Walks the owner's room with the quote by voice on several screens, the way a salesperson would.
Usage: python3 -I check_room.py <verse dir> <room folder> <out dir>"""
import sys, json, pathlib, threading, functools, http.server, socketserver, time
from playwright.sync_api import sync_playwright

verse, room, out = pathlib.Path(sys.argv[1]).resolve(), sys.argv[2], pathlib.Path(sys.argv[3])
out.mkdir(parents=True, exist_ok=True)
PORT = 8765


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


socketserver.TCPServer.allow_reuse_address = True
srv = socketserver.ThreadingTCPServer(('127.0.0.1', PORT), functools.partial(Quiet, directory=str(verse)))
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f'http://localhost:{PORT}/'

SENT = 'משפחת כהן טלפון 0521234567 80 מטר סמנט גריי ב-66 3 ברזים ב-450 הובלה מתנה'
SCREENS = {'phone': (390, 844), 'small': (360, 740), 'ziv_phone': (412, 915), 'landscape': (844, 390), 'desk17': (1440, 900), 'touch32': (1920, 1080)}
# a stand-in for the phone's speech engine: three stretches of speech with pauses between them, then silence
MOCK = """
(function(){
  var PARTS=['משפחת כהן טלפון 0521234567','80 מטר סמנט גריי ב-66','3 ברזים ב-450 הובלה מתנה'], n=0;
  function R(){ this.lang=''; }
  var tooSoon=1;
  R.prototype.start=function(){ var me=this; if(n===1&&tooSoon){ tooSoon=0; throw new Error('InvalidStateError'); } me.dead=false;
    setTimeout(function(){ if(me.dead) return; me.onstart&&me.onstart();
      if(n>=PARTS.length){ setTimeout(function(){ if(me.dead) return; me.onerror&&me.onerror({error:'no-speech'}); me.onend&&me.onend(); },300); return; }
      var t=PARTS[n++], half=t.slice(0,Math.ceil(t.length/2));
      setTimeout(function(){ if(me.dead) return; me.onresult&&me.onresult({results:[Object.assign([{transcript:half}],{isFinal:false})]}); },80);
      setTimeout(function(){ if(me.dead) return; me.onresult&&me.onresult({results:[Object.assign([{transcript:t}],{isFinal:true})]}); },160);
      setTimeout(function(){ if(me.dead) return; me.onend&&me.onend(); },240);
    },20); };
  R.prototype.stop=function(){ var me=this; me.dead=true; setTimeout(function(){ me.onend&&me.onend(); },10); };
  window.webkitSpeechRecognition=R; window.SpeechRecognition=R; window.__mockN=function(){ return n; };
})();
"""
NOSR = "Object.defineProperty(window,'webkitSpeechRecognition',{value:undefined,configurable:true}); Object.defineProperty(window,'SpeechRecognition',{value:undefined,configurable:true});"
bad, notes = [], []


def need(cond, msg):
    (notes if cond else bad).append(('✅ ' if cond else '❌ ') + msg)


def block(route):
    u = route.request.url
    if u.startswith(BASE) and not u.endswith('.mp4'):
        route.continue_()
    else:
        route.abort()


def fresh(browser, w, h, touch=True, init=None):
    ctx = browser.new_context(viewport={'width': w, 'height': h}, device_scale_factor=2, has_touch=touch, is_mobile=touch and w < 900, locale='he-IL')
    ctx.route('**/*', block)
    if init:
        ctx.add_init_script(init)
    page = ctx.new_page()
    errs = []
    page.on('pageerror', lambda e: errs.append(str(e)))
    return ctx, page, errs


def state(page):
    return page.evaluate("""() => {
      var f=document.querySelector('#f').elements, rows=[].map.call(document.querySelectorAll('#rows .row'),d=>({t:d.querySelector('[data-k=t]').value,q:d.querySelector('[data-k=q]').value,p:d.querySelector('[data-k=p]').value,u:d.querySelector('.u').textContent,s:d.querySelector('[data-k=s]').value}));
      return {fam:f.fam.value,name:f.name.value,phone:f.phone.value,gift:f.gift.value,rows:rows,tot:document.querySelector('#tot').textContent,
        sum:!document.querySelector('#vsum').hidden, miss:document.querySelector('#vmiss').hidden?'':document.querySelector('#vmiss').textContent,
        over:document.documentElement.scrollWidth-window.innerWidth, list:document.querySelector('#vlist').innerText};
    }""")


def overlaps(page):
    """buttons and fields of the voice card must not sit on each other or leave the card"""
    return page.evaluate("""() => {
      var card=document.querySelector('#voice').getBoundingClientRect(), bad=[];
      var els=[].filter.call(document.querySelectorAll('#voice button, #voice textarea, #voice .vex, #voice h2, #voice li'),e=>e.offsetParent!==null);
      var r=els.map(e=>e.getBoundingClientRect());
      r.forEach((a,i)=>{ if(a.left<card.left-1||a.right>card.right+1) bad.push('out:'+els[i].id+els[i].className);
        r.forEach((b,j)=>{ if(j<=i||els[i].contains(els[j])||els[j].contains(els[i])) return; if(a.left<b.right-1&&b.left<a.right-1&&a.top<b.bottom-1&&b.top<a.bottom-1) bad.push('on:'+(els[i].id||els[i].tagName)+'/'+(els[j].id||els[j].tagName)); }); });
      var small=[].filter.call(document.querySelectorAll('#voice button'),e=>e.offsetParent!==null&&e.getBoundingClientRect().height<40).map(e=>e.id);
      return {bad:bad,small:small};
    }""")


with sync_playwright() as pw:
    browser = pw.chromium.launch(args=['--no-sandbox'])
    link = None
    for name, (w, h) in SCREENS.items():
        ctx, page, errs = fresh(browser, w, h, touch=name != 'desk17')
        page.goto(BASE + room + '/', wait_until='domcontentloaded')
        page.wait_for_selector('#vmic')
        page.screenshot(path=str(out / f'{name}_1_open.png'))
        need(page.evaluate("document.documentElement.scrollWidth<=window.innerWidth"), f'{name}: הדף לא גולש הצידה בפתיחה')
        page.fill('#vtext', SENT)
        page.click('#vfill')
        page.wait_for_selector('#vsum:not([hidden])')
        page.wait_for_timeout(500)
        st = state(page)
        need(st['fam'] == 'כהן' and st['phone'] == '052-1234567' and st['gift'] == 'הובלה', f'{name}: שם, טלפון ומתנה מולאו ({st["fam"]}, {st["phone"]}, {st["gift"]})')
        need(len(st['rows']) == 2 and st['rows'][0]['t'] == 'סמנט גריי' and st['rows'][0]['q'] == '80' and st['rows'][0]['p'] == '66' and st['rows'][0]['u'] == 'מ״ר'
             and st['rows'][1]['t'] == 'ברזים' and st['rows'][1]['q'] == '3' and st['rows'][1]['p'] == '450' and st['rows'][1]['u'] == 'יח׳', f'{name}: שתי שורות עם כמות, יחידה ומחיר')
        need('6,630' in st['tot'], f'{name}: הסכום 6,630 ({st["tot"]})')
        need(st['miss'] == '', f'{name}: לא חסר כלום ({st["miss"]})')
        need(st['over'] <= 0, f'{name}: הדף לא גולש הצידה אחרי המילוי ({st["over"]})')
        ov = overlaps(page)
        need(not ov['bad'], f'{name}: שום דבר בכרטיס לא עולה על דבר אחר ({ov["bad"]})')
        need(not ov['small'], f'{name}: כל הכפתורים בכרטיס בגובה נגיעה ({ov["small"]})')
        page.locator('#voice').screenshot(path=str(out / f'{name}_2_understood.png'))
        page.locator('#parsed').scroll_into_view_if_needed()
        page.locator('#parsed').screenshot(path=str(out / f'{name}_3_rows.png'))
        # the unit button cycles
        page.click('#rows .row:nth-of-type(2) .u') if False else page.locator('#rows .row').nth(0).locator('.u').click()
        need(page.locator('#rows .row').nth(0).locator('.u').inner_text() == 'יח׳', f'{name}: נגיעה ביחידה מחליפה אותה')
        for _ in range(3):
            page.locator('#rows .row').nth(0).locator('.u').click()
        need(page.locator('#rows .row').nth(0).locator('.u').inner_text() == 'מ״ר', f'{name}: היחידה חוזרת למ״ר')
        # confirm → the link
        page.click('#vgo')
        page.wait_for_selector('#out.on')
        page.wait_for_timeout(300)
        link = page.inner_text('#link')
        msg = page.inner_text('#msg')
        wa = page.get_attribute('#wa', 'href')
        need('#q=' in link and 'משפחת כהן' in msg and 'wa.me/972521234567' in wa, f'{name}: קישור, הודעה וואטסאפ ללקוח נוצרו')
        need(not errs, f'{name}: בלי שגיאות בדף ({errs})')
        ctx.close()

    # the link opens on the customer's page with the same lines and units
    ctx, page, errs = fresh(browser, 390, 844)
    page.goto(link, wait_until='domcontentloaded')
    page.wait_for_function("document.querySelector('#total')&&document.querySelector('#total').textContent.length>20")
    txt = page.evaluate("document.querySelector('#total').innerText+' | '+document.querySelector('#who').innerText+' | '+document.title")
    flat = ' '.join(txt.split())
    need('סמנט גריי' in flat and '80 מ״ר' in flat and 'ברזים' in flat and '3 יח׳' in flat and '6,630' in flat and 'משפחת כהן' in flat, 'דף הלקוח: אותן שורות, 80 מ״ר ו־3 יח׳, 6,630 ₪, משפחת כהן')
    need(page.evaluate("!document.querySelector('#qgift').hidden"), 'דף הלקוח: קופסת המתנה מופיעה')
    notes.append('   דף הלקוח: ' + flat[:260])
    ctx.close()

    # the microphone button, with a stand-in speech engine: three stretches, pauses, then a long silence ends it
    ctx, page, errs = fresh(browser, 390, 844, init=MOCK)
    page.goto(BASE + room + '/', wait_until='domcontentloaded')
    page.click('#vmic')
    page.wait_for_timeout(120)
    need(page.get_attribute('#vmic', 'aria-pressed') == 'true' and page.inner_text('#vmicT') == 'לסיים', 'מיקרופון: בזמן הקשבה הכפתור הופך ל״לסיים״')
    page.screenshot(path=str(out / 'mic_listening.png'))
    page.wait_for_selector('#vsum:not([hidden])', timeout=8000)
    st = state(page)
    need(page.input_value('#vtext') == SENT, 'מיקרופון: שלושה קטעי דיבור עם הפסקות התחברו למשפט אחד (' + page.input_value('#vtext') + ')')
    need(st['fam'] == 'כהן' and len(st['rows']) == 2 and '6,630' in st['tot'], 'מיקרופון: שתיקה ארוכה סיימה, והטופס התמלא')
    need(page.get_attribute('#vmic', 'aria-pressed') == 'false', 'מיקרופון: הכפתור חזר ל״לדבר״')
    need(not errs, f'מיקרופון: בלי שגיאות ({errs})')
    ctx.close()

    # pressing "לסיים" in the middle
    ctx, page, errs = fresh(browser, 390, 844, init=MOCK)
    page.goto(BASE + room + '/', wait_until='domcontentloaded')
    page.click('#vmic')
    page.wait_for_function("window.__mockN()>=2&&document.querySelector('#vtext').value.indexOf('ב-66')>0")
    page.click('#vmic')
    page.wait_for_selector('#vsum:not([hidden])')
    st = state(page)
    need(st['fam'] == 'כהן' and len(st['rows']) == 1 and st['rows'][0]['t'] == 'סמנט גריי', 'מיקרופון: ״לסיים״ באמצע ממלא את מה שנאמר עד אז')
    page.wait_for_timeout(700)
    need(page.get_attribute('#vmic', 'aria-pressed') == 'false' and len(state(page)['rows']) == 1, 'מיקרופון: אחרי ״לסיים״ ההקשבה לא ממשיכה לבד')
    ctx.close()

    # a browser with no speech engine: the keyboard path
    ctx, page, errs = fresh(browser, 390, 844, init=NOSR)
    page.goto(BASE + room + '/', wait_until='domcontentloaded')
    page.click('#vmic')
    page.wait_for_timeout(200)
    need('המיקרופון של המקלדת' in page.inner_text('#vstate') and page.evaluate("document.activeElement.id") == 'vtext', 'בלי מנוע דיבור: הסבר על המיקרופון של המקלדת, והסמן בתיבה')
    page.locator('#voice').screenshot(path=str(out / 'no_engine.png'))
    # something missing: no phone, a line with no price, a stray word
    page.fill('#vtext', 'משפחת לוי 80 מטר סמנט גריי')
    page.click('#vfill')
    page.wait_for_selector('#vsum:not([hidden])')
    st = state(page)
    need('טלפון' in st['miss'] and 'מחיר' in st['miss'], 'חסר: הדף אומר שחסרים טלפון ומחיר (' + st['miss'] + ')')
    page.locator('#voice').screenshot(path=str(out / 'missing.png'))
    need(page.inner_text('#vgo') == 'להשלים את החסר', 'חסר: הכפתור הגדול אומר ״להשלים את החסר״')
    page.click('#vgo'); page.wait_for_timeout(500)
    need(page.evaluate("document.activeElement.name") == 'phone', 'חסר: נגיעה בכפתור מביאה לשדה הטלפון')
    page.fill('input[name=phone]', '0521234567'); page.click('#vgo'); page.wait_for_timeout(500)
    need(page.evaluate("document.activeElement.dataset.k") == 'p', 'חסר: אחרי הטלפון, הכפתור מביא למחיר שחסר')
    page.keyboard.type('66'); page.wait_for_timeout(100)
    need(page.inner_text('#vgo') == 'נכון. צור את הסרט האישי', 'חסר: כשהכול הושלם, הכפתור חוזר ל״נכון. צור את הסרט האישי״')
    page.click('#vgo'); page.wait_for_selector('#out.on')
    need('#q=' in page.inner_text('#link'), 'חסר: אחרי ההשלמה הסרט האישי נוצר')
    page.click('#vclear')
    need(page.input_value('#vtext') == '' and page.evaluate("document.querySelector('#vsum').hidden"), '״לנקות״ מנקה את התיבה ואת הסיכום')
    need(not errs, f'בלי מנוע דיבור: בלי שגיאות ({errs})')
    ctx.close()

    # words the phone hears wrong: the shop's words, undo, learning from a hand correction, names already sent, teaching, forgetting
    ctx, page, errs = fresh(browser, 390, 844)
    page.goto(BASE + room + '/', wait_until='domcontentloaded')
    H = 'משפחת כהן טלפון 0521234567 80 מטר צמנט גרי ב-66 40 מטר טרסו ב-180'
    def say(text):
        page.fill('#vtext', text); page.click('#vfill'); page.wait_for_selector('#vsum:not([hidden])'); page.wait_for_timeout(250)
        return state(page)
    def fixline():
        return '' if page.evaluate("document.querySelector('#vfix').hidden") else page.inner_text('#vfix')
    st = say(H)
    need(st['rows'][0]['t'] == 'צמנט גרי' and st['rows'][1]['t'] == 'טרצו', 'מילון: מילה של החנות מתוקנת לבד (טרסו ← טרצו), ושם לא מוכר נשאר כמו שנשמע')
    need('טרסו' in fixline() and 'לבטל' in fixline(), 'מילון: הדף אומר מה תיקן לבד, עם ״לבטל״ (' + ' '.join(fixline().split()) + ')')
    ov = overlaps(page)
    need(not ov['bad'] and not ov['small'], f'מילון: שורת התיקונים לא עולה על כלום והכפתורים בגובה נגיעה ({ov})')
    page.locator('#voice').screenshot(path=str(out / 'dict_1_autofix.png'))
    page.click('#vfix button[data-keep]'); page.wait_for_timeout(250)
    need(state(page)['rows'][1]['t'] == 'טרסו' and fixline() == '', 'מילון: ״לבטל״ מחזיר את מה שנשמע')
    need(say(H)['rows'][1]['t'] == 'טרסו', 'מילון: מה שבוטל לא מתוקן שוב')
    page.locator('#rows .row').nth(0).locator('[data-k=t]').fill('סמנט גריי 120/60')
    page.click('#go'); page.wait_for_selector('#out.on')
    need('צמנט גרי' in page.evaluate("localStorage.getItem('bq_dict')||''") and 'סמנט גריי' in page.evaluate("localStorage.getItem('bq_names')||''"), 'מילון: תיקון ביד נלמד כשהסרט נוצר, והשם שנשלח נשמר')
    page.click('#vclear')
    st = say(H)
    need(st['rows'][0]['t'] == 'סמנט גריי' and 'לשכוח' in fixline(), 'מילון: בפעם הבאה אותה מילה מתוקנת לבד (' + st['rows'][0]['t'] + ')')
    page.click('#vdict summary'); page.wait_for_timeout(150)
    need('צמנט גרי' in page.inner_text('#vdl') and page.inner_text('#vdn') == '(1)', 'מילון: הזוג מופיע ברשימה של הטלפון')
    page.locator('#voice').screenshot(path=str(out / 'dict_2_panel.png'))
    ov = overlaps(page)
    need(not ov['bad'] and not ov['small'], f'מילון: הרשימה הפתוחה לא עולה על כלום ({ov})')
    need(page.evaluate("document.documentElement.scrollWidth<=window.innerWidth"), 'מילון: הדף לא גולש הצידה כשהמילון פתוח')
    page.click('#vfix button[data-forget]'); page.wait_for_timeout(250)
    st = state(page)
    need(page.inner_text('#vdl').strip() == '' and st['rows'][0]['t'] == 'סמנט גריי' and 'לבטל' in fixline(), 'מילון: אחרי ״לשכוח״ השם עדיין מתוקן, כי הוא כבר נשלח פעם מהטלפון הזה')
    page.click('#vfix button[data-keep]'); page.wait_for_timeout(250)
    need(state(page)['rows'][0]['t'] == 'צמנט גרי', 'מילון: ו״לבטל״ מחזיר גם אותו')
    page.fill('#vdh', 'גרי'); page.fill('#vds', 'גריי'); page.click('#vdadd'); page.wait_for_timeout(300)
    need(state(page)['rows'][0]['t'] == 'צמנט גריי' and 'גרי' in page.inner_text('#vdl'), 'מילון: מלמדים מילה ביד, והטופס מתעדכן מיד')
    page.click('#vdadd'); page.wait_for_timeout(100)
    need('שתי התיבות' in page.inner_text('#vdsay'), 'מילון: ״ללמד״ בלי מילים מסביר מה חסר')
    # choosing another product teaches nothing
    before = page.evaluate("localStorage.getItem('bq_dict')")
    page.locator('#rows .row').nth(0).locator('[data-k=t]').fill('ונוס בז 60/60')
    page.click('#go'); page.wait_for_selector('#out.on')
    need(page.evaluate("localStorage.getItem('bq_dict')") == before, 'מילון: החלפה למוצר אחר לא נלמדת')
    page.reload(wait_until='domcontentloaded'); page.wait_for_selector('#vmic')
    need(page.inner_text('#vdn') == '(1)', 'מילון: נשאר אחרי טעינה מחדש של הדף')
    st = say('משפחת לוי טלפון 0521234567 30 מטר וונוס בז ב-90 2 אסלות שחורות ב-1500')
    need(st['rows'][0]['t'] == 'ונוס בז' and st['rows'][1]['t'] == 'אסלות שחורות', 'מילון: שם שכבר נשלח מזוהה גם כשנשמע קצת אחרת, ומילים רגילות לא נפגעות (' + st['rows'][0]['t'] + ' | ' + st['rows'][1]['t'] + ')')
    need(not errs, f'מילון: בלי שגיאות ({errs})')
    ctx.close()

    # the live room's own way still works in the copy: paste, read, make
    ctx, page, errs = fresh(browser, 390, 844)
    page.goto(BASE + room + '/', wait_until='domcontentloaded')
    page.fill('input[name=fam]', 'בן משה'); page.fill('input[name=phone]', '052-4476717')
    page.fill('#paste', 'פריט   כמות   מחיר   סה״כ\nונוס גריי 120/60   120   55   6,600\nסמנט בז׳ 120/60   160   68   10,880')
    page.click('#parse')
    st = state(page)
    need(len(st['rows']) == 2 and st['rows'][0]['q'] == '120' and st['rows'][1]['p'] == '68' and '17,480' in st['tot'], 'הדרך הישנה (להדביק ולקרוא) עובדת כמו קודם')
    page.click('#go'); page.wait_for_selector('#out.on')
    need('#q=' in page.inner_text('#link') and not errs, 'הדרך הישנה: הסרט האישי נוצר')
    ctx.close()
    browser.close()

srv.shutdown()
print('\n'.join(notes + bad))
print(('❌ ' if bad else '✅ ') + f'{len(notes)} בדיקות עברו, {len(bad)} נכשלו')
sys.exit(1 if bad else 0)
