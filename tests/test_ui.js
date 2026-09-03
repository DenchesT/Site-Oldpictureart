const { chromium } = require('playwright');
const D=require('path').join(__dirname, '..', 'docs');
const f=n=>'file://'+D+'/'+encodeURIComponent(n).replace(/%2F/g,'/');
const R=[]; const ok=(n,c,e)=>R.push({n,p:!!c,e:e||''});

// Свой браузер можно указать переменной CHROME_PATH — пригодится,
// если Playwright не скачивал Chromium, а системный уже есть.
const LAUNCH = process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {};
(async()=>{
  const b=await chromium.launch(LAUNCH);
  for (const theme of ['light','dark']) {
    const ctx=await b.newContext({viewport:{width:1440,height:900}});
    const p=await ctx.newPage();
    await p.addInitScript(t=>{try{localStorage.setItem('theme',t)}catch(e){}}, theme);
    await p.goto(f('index.html')); await p.waitForTimeout(800);

    // селекты нарисованы нами, а не системой
    for (const id of ['sort','year-from','year-to']) {
      const st = await p.evaluate(i=>{const e=document.getElementById(i);const c=getComputedStyle(e);
        return {ap:c.appearance, ff:c.fontFamily.split(',')[0], br:c.borderRadius, bi:c.backgroundImage.slice(0,20)};}, id);
      ok(`${theme}: #${id} не системный`, st.ap==='none', st.ap);
      ok(`${theme}: #${id} моноширинный`, /IBM Plex Mono/.test(st.ff), st.ff);
      ok(`${theme}: #${id} с прямыми углами`, st.br==='2px', st.br);
      ok(`${theme}: #${id} со своим шевроном`, st.bi.startsWith('url('), st.bi);
    }
    // выпадающий список следует теме
    const cs = await p.evaluate(()=>getComputedStyle(document.documentElement).colorScheme);
    ok(`${theme}: color-scheme выставлен`, cs.includes(theme), cs);

    // единая высота элементов управления
    const hs = await p.evaluate(()=>['sort','year-from','year-to'].map(i=>Math.round(document.getElementById(i).getBoundingClientRect().height))
      .concat([Math.round(document.querySelector('.view-switch').getBoundingClientRect().height)]));
    ok(`${theme}: элементы управления одной высоты`, new Set(hs).size===1, hs.join('/'));

    // подписи разделов сайдбара выровнены по левому краю
    const lefts = await p.evaluate(()=>[...document.querySelectorAll('.sidebar-content')].length &&
      [...document.querySelectorAll('.sidebar-title')].map(t=>Math.round(t.getBoundingClientRect().left)));
    ok(`${theme}: разделы сайдбара выровнены`, new Set(lefts).size===1, [...new Set(lefts)].join('/'));

    // кольцо прогресса не пропадает при наведении
    await p.evaluate(()=>window.scrollTo(0, document.documentElement.scrollHeight*0.5));
    await p.waitForTimeout(600);
    const before = await p.evaluate(()=>getComputedStyle(document.querySelector('.scroll-top')).backgroundImage);
    await p.locator('.scroll-top').hover(); await p.waitForTimeout(300);
    const after = await p.evaluate(()=>getComputedStyle(document.querySelector('.scroll-top')).backgroundImage);
    // процент мог измениться, пока догружались картинки, — сравниваем тип фона
    ok(`${theme}: кольцо остаётся при наведении`,
       before.includes('conic-gradient') && after.includes('conic-gradient'),
       after.slice(0, 28));
    ok(`${theme}: одно правило .scroll-top`, (await p.evaluate(()=>getComputedStyle(document.querySelector('.scroll-top')).display))==='grid');
    await ctx.close();
  }

  // версия у стилей — чтобы браузер не держал старый файл
  {
    const ctx=await b.newContext(); const p=await ctx.newPage();
    await p.goto(f('index.html')); await p.waitForTimeout(300);
    const href = await p.evaluate(()=>document.querySelector('link[href*="style.css"]').getAttribute('href'));
    ok('у стилей есть версия в адресе', /^style\.css\?v=[a-f0-9]{8}$/.test(href), href);
    await ctx.close();
  }
  await b.close();
  const bad=R.filter(r=>!r.p);
  console.log('\n===== ВНЕШНИЙ ВИД УПРАВЛЕНИЯ =====');
  R.forEach(r=>console.log(`${r.p?'OK  ':'FAIL'}  ${r.n}${r.e?'  — '+r.e:''}`));
  console.log(`\nВсего: ${R.length}, провалено: ${bad.length}`);
  process.exit(bad.length?1:0);
})();
