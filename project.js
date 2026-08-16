/* ═══════════════════════════════════════════════════════
   Grand Traverse Builders — Project Planner & Favorites
   localStorage-backed, no login required
   ═══════════════════════════════════════════════════════ */
(function(){
'use strict';

const STORAGE_KEY = 'nwmi_favorites';
const PROJECT_KEY = 'nwmi_project';

// Lightweight analytics helper — no-op if gtag isn't loaded.
function track(action, params){
  try{ if(typeof window.gtag==='function') window.gtag('event', action, params||{}); }catch(e){}
}
window.gtbTrack = track;

const BUILD_PHASES = [
  { phase:"Planning", steps:[
    {id:"builder",label:"General Contractor / Builder",cat:"Building Contractors",icon:"🏠",desc:"Your main builder manages the entire project"},
    {id:"architect",label:"Architect / Designer",cat:"Architectural  & Design Services",icon:"📐",desc:"Design plans and blueprints"},
    {id:"financing",label:"Construction Financing",cat:"Banking & Mortgage",icon:"🏦",desc:"Construction loans and mortgage"},
    {id:"land",label:"Land / Property",cat:"Real Estate Development",icon:"🗺️",desc:"Find property or a developer",optional:true},
  ]},
  { phase:"Structure", steps:[
    {id:"excavating",label:"Excavating & Site Work",cat:"Excavating",icon:"🚜",desc:"Site prep, grading, and foundation dig"},
    {id:"concrete",label:"Foundation / Concrete",cat:"Concrete",icon:"🧱",desc:"Foundation, footings, and flatwork"},
    {id:"roofing",label:"Roofing",cat:"Roofing",icon:"🏗️",desc:"Roof installation and materials"},
    {id:"windows",label:"Windows & Doors",cat:"Windows & Doors",icon:"🪟",desc:"Window and door supply/install"},
    {id:"siding",label:"Siding",cat:"Siding Contractors",icon:"🧱",desc:"Exterior cladding and trim"},
  ]},
  { phase:"Systems", steps:[
    {id:"electrical",label:"Electrical",cat:"Electrical Contractors",icon:"⚡",desc:"Wiring, panels, and fixtures"},
    {id:"plumbing",label:"Plumbing",cat:"Plumbing Contractors",icon:"🔧",desc:"Water, drainage, and gas lines"},
    {id:"hvac",label:"HVAC",cat:"HVAC Contractors",icon:"❄️",desc:"Heating, cooling, and ventilation"},
    {id:"insulation",label:"Insulation",cat:"Insulation Contractors & Installers",icon:"🧤",desc:"Spray foam, blown-in, or batt"},
  ]},
  { phase:"Finishes", steps:[
    {id:"drywall",label:"Drywall",cat:"Drywall Contractors",icon:"🔧",desc:"Hanging, taping, and finishing"},
    {id:"painting",label:"Painting",cat:"Painting & Wallpaper Contractors",icon:"🎨",desc:"Interior and exterior painting"},
    {id:"flooring",label:"Flooring",cat:"Flooring",icon:"🪵",desc:"Hardwood, tile, carpet, LVP"},
    {id:"cabinetry",label:"Cabinetry & Counters",cat:"Cabinetry - Whole House",icon:"🗄️",desc:"Kitchen and whole-house cabinetry"},
    {id:"landscaping",label:"Landscaping",cat:"Landscaping & Gardening Contractors",icon:"🌿",desc:"Outdoor living and plantings"},
    {id:"interior",label:"Interior Design",cat:"Interior Design & Staging",icon:"🏡",desc:"Fixtures, finishes, and staging",optional:true},
  ]}
];

const ALL_STEPS=BUILD_PHASES.flatMap(p=>p.steps);
function slugify(t){return t.toLowerCase().replace(/[^\w\s-]/g,'').replace(/[\s_]+/g,'-').replace(/-+/g,'-').replace(/^-|-$/g,'');}
function getRoot(){return document.body.getAttribute('data-root')||'';}
function esc(s){return s.replace(/'/g,"\\'");}

// ── Page detection ──────────────────────────────────
function getPageType(){
  const h=window.location.pathname+window.location.href;
  if(h.includes('/business/'))return 'business';
  if(h.includes('/category/'))return 'category';
  return 'other';
}
function getCurrentBusinessSlug(){
  const m=window.location.pathname.match(/\/business\/([^/]+?)(?:\.html)?\/?$/);
  return m?m[1]:null;
}
function getCurrentBusinessName(){
  const el=document.querySelector('.page-hero h1');
  return el?el.textContent.trim():null;
}
function getStepParam(){
  return new URLSearchParams(window.location.search).get('step');
}

// ── Favorites ───────────────────────────────────────
function getFavorites(){try{return JSON.parse(localStorage.getItem(STORAGE_KEY))||[];}catch(e){return[];}}
function saveFavorites(f){localStorage.setItem(STORAGE_KEY,JSON.stringify(f));}
function isFavorite(slug){return getFavorites().includes(slug);}
function toggleFavorite(slug){
  let favs=getFavorites();const i=favs.indexOf(slug);
  if(i>-1)favs.splice(i,1);else favs.push(slug);
  saveFavorites(favs);updateAllHearts();updateFavCount();
  track('favorite_toggle',{business:slug,action:i===-1?'add':'remove'});
  return i===-1;
}
function updateAllHearts(){
  document.querySelectorAll('[data-fav-slug]').forEach(el=>{
    const slug=el.getAttribute('data-fav-slug'),fav=isFavorite(slug);
    el.classList.toggle('is-fav',fav);
    const ic=el.querySelector('.heart-icon');if(ic)ic.innerHTML=fav?'♥':'♡';
    const lb=el.querySelector('.heart-label');if(lb)lb.textContent=fav?'Saved':'Save';
  });
}
function updateFavCount(){
  const c=getFavorites().length;
  document.querySelectorAll('.fav-count-badge').forEach(el=>{el.textContent=c;el.style.display=c>0?'':'none';});
}

// ── Project ─────────────────────────────────────────
function getProject(){try{return JSON.parse(localStorage.getItem(PROJECT_KEY))||{type:null,selections:{}};}catch(e){return{type:null,selections:{}};}}
function saveProject(p){localStorage.setItem(PROJECT_KEY,JSON.stringify(p));}
function getCompletedCount(){return Object.keys(getProject().selections).length;}

window.setProjectType=function(type){
  const p=getProject();p.type=type;saveProject(p);renderWizard();
};
window.selectForStep=function(stepId,slug,name){
  const p=getProject();
  if(!p.type)p.type='residential';
  p.selections[stepId]={slug:slug,name:name};
  saveProject(p);renderWizard();updatePlanBadge();refreshDetailPlanCard();refreshPlanButtons();
  track('plan_add',{step:stepId,business:slug});
  // Flash the step
  const el=document.querySelector('[data-step-id="'+stepId+'"]');
  if(el){el.classList.add('just-added');setTimeout(()=>el.classList.remove('just-added'),1200);}
};
window.removeFromStep=function(stepId){
  const p=getProject();delete p.selections[stepId];saveProject(p);renderWizard();updatePlanBadge();refreshDetailPlanCard();refreshPlanButtons();
};
window.resetProject=function(){
  if(confirm('Clear your entire build plan?')){localStorage.removeItem(PROJECT_KEY);renderWizard();updatePlanBadge();refreshDetailPlanCard();refreshPlanButtons();}
};

// ── Quick-add from category card ────────────────────
// When browsing a category with ?step=X, clicking "Add" on a card adds directly
window.quickAdd=function(stepId,slug,name,btn){
  if(!getProject().type){const p=getProject();p.type='residential';saveProject(p);}
  window.selectForStep(stepId,slug,name);
  // Update banner if present
  const banner=document.getElementById('planBanner');
  if(banner){
    const step=ALL_STEPS.find(s=>s.id===stepId);
    banner.querySelector('.plan-pick-text').innerHTML=`<strong>✓ Added ${name}</strong> as ${step?step.label:''}<div class="plan-pick-hint">Continue browsing or <a href="#" onclick="toggleWizard();return false;" style="color:var(--copper-warm);font-weight:600;">view your Build Plan →</a></div>`;
  }
};

// ── Render wizard ───────────────────────────────────
function renderWizard(){
  const panel=document.getElementById('wizardPanel');
  if(!panel)return;
  const p=getProject(),completed=getCompletedCount(),total=ALL_STEPS.length;
  const pct=total>0?Math.round((completed/total)*100):0;
  const prefix=getRoot();
  const bizSlug=getCurrentBusinessSlug(),bizName=getCurrentBusinessName();
  const onBiz=getPageType()==='business';

  let h=`<div class="wz-header">
    <div class="wz-title"><span class="wz-title-icon">🏠</span><div><div class="wz-title-text">Build Planner</div><div class="wz-title-sub">${completed} of ${total} selected</div></div></div>
    <button class="wz-close" onclick="toggleWizard()">✕</button>
  </div><div class="wz-progress"><div class="wz-progress-bar" style="width:${pct}%"></div></div>`;

  if(!p.type){
    h+=`<div class="wz-type-pick"><div class="wz-type-title">What are you building?</div>
      <button class="wz-type-btn" onclick="setProjectType('residential')"><span class="wz-type-icon">🏡</span><span>Residential</span></button>
      <button class="wz-type-btn" onclick="setProjectType('commercial')"><span class="wz-type-icon">🏢</span><span>Commercial</span></button></div>`;
  } else {
    h+=`<div class="wz-type-tag">${p.type==='residential'?'🏡 Residential':'🏢 Commercial'} Build <button class="wz-reset" onclick="resetProject()">Reset</button></div>`;
    h+=`<div class="wz-steps-wrap">`;
    BUILD_PHASES.forEach(phase=>{
      h+=`<div class="wz-phase"><div class="wz-phase-label">${phase.phase}</div>`;
      phase.steps.forEach(step=>{
        const sel=p.selections[step.id],catSlug=slugify(step.cat);
        if(sel){
          h+=`<div class="wz-step done" data-step-id="${step.id}">
            <div class="wz-step-check">✓</div>
            <div class="wz-step-info"><div class="wz-step-label">${step.label}</div>
              <a href="${prefix}business/${sel.slug}.html" class="wz-step-selected">${sel.name}</a></div>
            <button class="wz-step-remove" onclick="removeFromStep('${step.id}')">✕</button></div>`;
        } else {
          let addBtn='';
          if(onBiz && bizSlug && bizName){
            addBtn=`<button class="wz-step-add" onclick="selectForStep('${step.id}','${bizSlug}','${esc(bizName)}')">+ Add</button>`;
          }
          h+=`<div class="wz-step${step.optional?' optional':''}" data-step-id="${step.id}">
            <div class="wz-step-num">${step.icon}</div>
            <div class="wz-step-info"><div class="wz-step-label">${step.label}${step.optional?' <span class="wz-opt">(optional)</span>':''}</div>
              <a href="${prefix}category/${catSlug}.html?step=${step.id}" class="wz-step-browse">Browse ${step.label} →</a></div>
            ${addBtn}</div>`;
        }
      });
      h+=`</div>`;
    });
    h+=`</div>`;
    if(completed>0){
      h+=`<div class="wz-share-bar"><button class="wz-share-btn" onclick="openShareModal()">📤 Share This Plan</button></div>`;
    }
  }
  panel.innerHTML=h;
}

// ── Share Plan ──────────────────────────────────────
function encodePlan(){
  const p=getProject();
  const data={t:p.type,s:{}};
  for(const[k,v]of Object.entries(p.selections)){data.s[k]=v.slug+'|'+v.name;}
  return btoa(unescape(encodeURIComponent(JSON.stringify(data))));
}
function decodePlan(encoded){
  try{
    const json=decodeURIComponent(escape(atob(encoded)));
    const data=JSON.parse(json);
    const result={type:data.t,selections:{}};
    for(const[k,v]of Object.entries(data.s||{})){
      const parts=v.split('|');result.selections[k]={slug:parts[0],name:parts.slice(1).join('|')};
    }
    return result;
  }catch(e){return null;}
}
function getShareUrl(){
  const base=window.location.href.split('?')[0].split('#')[0];
  // Point to index.html (or plan.html)
  const root=getRoot();
  const origin=base.substring(0,base.lastIndexOf('/')+1);
  return origin+root+'index.html?shared_plan='+encodePlan();
}

window.openShareModal=function(){
  let modal=document.getElementById('shareModal');
  if(modal){modal.remove();}
  track('share_plan',{count:getCompletedCount()});
  const url=getShareUrl();
  const p=getProject();
  const completed=getCompletedCount();
  const names=Object.values(p.selections).map(s=>s.name);
  const textSummary=`🏠 My Grand Traverse Build Plan (${completed} vendors selected):\n\n`+
    BUILD_PHASES.map(phase=>{
      const filled=phase.steps.filter(s=>p.selections[s.id]);
      if(!filled.length)return '';
      return phase.phase+':\n'+filled.map(s=>`  ${s.icon} ${s.label}: ${p.selections[s.id].name}`).join('\n');
    }).filter(Boolean).join('\n\n')+
    `\n\nView the full plan: ${url}`;

  modal=document.createElement('div');modal.id='shareModal';modal.className='share-modal';
  modal.innerHTML=`
    <div class="share-modal-bg" onclick="closeShareModal()"></div>
    <div class="share-modal-content">
      <div class="share-modal-header">
        <h3>Share Your Build Plan</h3>
        <button class="wz-close" onclick="closeShareModal()">✕</button>
      </div>
      <div class="share-modal-body">
        <p class="share-modal-desc">Share your vendor selections with a friend, spouse, or client. They'll see a read-only view of your plan with links to each business.</p>
        
        <div class="share-section">
          <label class="share-label">Share Link</label>
          <div class="share-url-row">
            <input type="text" class="share-url-input" id="shareUrl" value="${url}" readonly onclick="this.select()"/>
            <button class="share-copy-btn" id="copyBtn" onclick="copyShareUrl()">Copy</button>
          </div>
        </div>

        <div class="share-section">
          <label class="share-label">Or copy as text</label>
          <textarea class="share-text-area" id="shareText" readonly onclick="this.select()">${textSummary}</textarea>
          <button class="share-copy-text-btn" onclick="copyShareText()">Copy Text Summary</button>
        </div>

        <div class="share-preview">
          <div class="share-preview-label">Preview (${completed} vendors)</div>
          ${names.map(n=>`<span class="share-preview-tag">${n}</span>`).join('')}
        </div>
      </div>
    </div>
  `;
  document.body.appendChild(modal);
  requestAnimationFrame(()=>modal.classList.add('open'));
};

window.closeShareModal=function(){
  const m=document.getElementById('shareModal');
  if(m){m.classList.remove('open');setTimeout(()=>m.remove(),300);}
};
window.copyShareUrl=function(){
  const input=document.getElementById('shareUrl');input.select();
  navigator.clipboard.writeText(input.value).then(()=>{
    const btn=document.getElementById('copyBtn');btn.textContent='Copied!';btn.classList.add('copied');
    setTimeout(()=>{btn.textContent='Copy';btn.classList.remove('copied');},2000);
  });
};
window.copyShareText=function(){
  const ta=document.getElementById('shareText');ta.select();
  navigator.clipboard.writeText(ta.value);
};

// ── Share / email saved businesses ──────────────────
function titleize(slug){return slug.replace(/-/g,' ').replace(/\b\w/g,c=>c.toUpperCase());}
function encodeFavorites(){
  return btoa(unescape(encodeURIComponent(JSON.stringify(getFavorites()))));
}
function decodeFavorites(encoded){
  try{
    const arr=JSON.parse(decodeURIComponent(escape(atob(encoded))));
    return Array.isArray(arr)?arr.filter(s=>typeof s==='string'):null;
  }catch(e){return null;}
}
function getFavShareUrl(){
  return window.location.origin+'/?shared_favs='+encodeFavorites();
}
function favShareText(){
  const favs=getFavorites(),origin=window.location.origin;
  return `My saved Northwest Michigan builders (${favs.length}):\n\n`+
    favs.map(s=>`• ${titleize(s)} — ${origin}/business/${s}`).join('\n')+
    `\n\nView the full list: ${getFavShareUrl()}`;
}
window.openFavShareModal=function(){
  const favs=getFavorites();
  if(!favs.length)return;
  track('share_favorites',{count:favs.length});
  let modal=document.getElementById('shareModal');if(modal)modal.remove();
  const url=getFavShareUrl();
  const text=favShareText();
  const mailto='mailto:?subject='+encodeURIComponent('My saved Northwest Michigan builders')+'&body='+encodeURIComponent(text);
  modal=document.createElement('div');modal.id='shareModal';modal.className='share-modal';
  modal.innerHTML=`
    <div class="share-modal-bg" onclick="closeShareModal()"></div>
    <div class="share-modal-content">
      <div class="share-modal-header">
        <h3>Share Your Saved Builders</h3>
        <button class="wz-close" onclick="closeShareModal()">✕</button>
      </div>
      <div class="share-modal-body">
        <p class="share-modal-desc">Send your shortlist to a spouse, partner, or friend. They'll see a read-only list with links to each business.</p>
        <div class="share-section">
          <label class="share-label">Share Link</label>
          <div class="share-url-row">
            <input type="text" class="share-url-input" id="shareUrl" value="${url}" readonly onclick="this.select()"/>
            <button class="share-copy-btn" id="copyBtn" onclick="copyShareUrl()">Copy</button>
          </div>
        </div>
        <div class="share-section">
          <a class="share-copy-text-btn" style="display:inline-block;text-decoration:none;text-align:center;" href="${mailto}" onclick="gtbTrack('email_favorites',{count:${favs.length}})">✉️ Email My List</a>
        </div>
        <div class="share-section">
          <label class="share-label">Or copy as text</label>
          <textarea class="share-text-area" id="shareText" readonly onclick="this.select()">${text}</textarea>
          <button class="share-copy-text-btn" onclick="copyShareText()">Copy Text Summary</button>
        </div>
        <div class="share-preview">
          <div class="share-preview-label">Preview (${favs.length} saved)</div>
          ${favs.map(s=>`<span class="share-preview-tag">${titleize(s)}</span>`).join('')}
        </div>
      </div>
    </div>`;
  document.body.appendChild(modal);
  requestAnimationFrame(()=>modal.classList.add('open'));
};

function checkForSharedFavorites(){
  const params=new URLSearchParams(window.location.search);
  const encoded=params.get('shared_favs');
  if(!encoded)return;
  const slugs=decodeFavorites(encoded);
  if(!slugs||!slugs.length)return;
  showSharedFavoritesOverlay(slugs);
}
function showSharedFavoritesOverlay(slugs){
  const prefix=getRoot();
  const overlay=document.createElement('div');
  overlay.className='shared-plan-overlay';overlay.id='sharedFavsOverlay';
  let h=`<div class="shared-plan-card">
    <div class="shared-plan-header">
      <div class="shared-plan-tag">♥ Shared Saved Builders</div>
      <h2>${slugs.length} Saved ${slugs.length===1?'Builder':'Builders'}</h2>
      <p>Someone shared their shortlist of Northwest Michigan builders with you.</p>
    </div>
    <div class="shared-plan-phases"><div class="shared-phase">`;
  slugs.forEach(s=>{
    h+=`<a href="${prefix}business/${s}.html" class="shared-vendor">
      <div class="shared-vendor-icon">♥</div>
      <div class="shared-vendor-info"><div class="shared-vendor-name">${titleize(s)}</div></div>
      <span class="shared-vendor-arrow">→</span>
    </a>`;
  });
  h+=`</div></div>
    <div class="shared-plan-actions">
      <button class="shared-plan-btn primary" onclick="importSharedFavorites()">♥ Save All to My List</button>
      <button class="shared-plan-btn" onclick="document.getElementById('sharedFavsOverlay').remove();history.replaceState(null,'',location.pathname);">Browse Directory Instead</button>
    </div>
  </div>`;
  overlay.innerHTML=h;
  document.body.appendChild(overlay);
  overlay._favs=slugs;
  requestAnimationFrame(()=>overlay.classList.add('open'));
}
window.importSharedFavorites=function(){
  const overlay=document.getElementById('sharedFavsOverlay');
  if(!overlay||!overlay._favs)return;
  const merged=Array.from(new Set(getFavorites().concat(overlay._favs)));
  saveFavorites(merged);updateAllHearts();updateFavCount();
  track('import_favorites',{count:overlay._favs.length});
  overlay.remove();history.replaceState(null,'',location.pathname);
  toggleFavPanel();
};

// ── Favorites panel ─────────────────────────────────
function renderFavPanel(){
  const panel=document.getElementById('favPanel');if(!panel)return;
  const favs=getFavorites(),prefix=getRoot();
  let h=`<div class="wz-header"><div class="wz-title"><span class="wz-title-icon">♥</span><div><div class="wz-title-text">Saved Businesses</div><div class="wz-title-sub">${favs.length} saved</div></div></div>
    <button class="wz-close" onclick="toggleFavPanel()">✕</button></div>`;
  if(!favs.length){
    h+=`<div class="wz-empty"><div style="font-size:2rem;margin-bottom:12px;">♡</div><p>No saved businesses yet.</p><p style="font-size:1rem;color:var(--text-soft);margin-top:4px;">Click the heart on any card to save it.</p></div>`;
  } else {
    h+=`<div class="fav-list">`;
    favs.forEach(slug=>{
      const name=slug.replace(/-/g,' ').replace(/\b\w/g,c=>c.toUpperCase());
      h+=`<a href="${prefix}business/${slug}.html" class="fav-item"><span class="fav-item-name">${name}</span><span class="fav-item-arrow">→</span></a>`;
    });
    h+=`</div><div class="wz-share-bar"><button class="wz-share-btn" onclick="openFavShareModal()">📤 Share / Email My List</button></div><div style="padding:16px 20px;"><button class="wz-reset" style="width:100%;text-align:center;" onclick="if(confirm('Clear all saved?')){saveFavorites([]);updateAllHearts();updateFavCount();renderFavPanel();}">Clear All Saved</button></div>`;
  }
  panel.innerHTML=h;
}

// ── Toggle panels ───────────────────────────────────
window.toggleWizard=function(){
  const p=document.getElementById('wizardPanel'),o=document.getElementById('wizardOverlay'),f=document.getElementById('favPanel');
  const opening=!p.classList.contains('open');
  f.classList.remove('open');p.classList.toggle('open');o.classList.toggle('open',opening);
  if(opening)renderWizard();
};
window.toggleFavPanel=function(){
  const p=document.getElementById('favPanel'),o=document.getElementById('wizardOverlay'),w=document.getElementById('wizardPanel');
  const opening=!p.classList.contains('open');
  w.classList.remove('open');p.classList.toggle('open');o.classList.toggle('open',opening);
  if(opening)renderFavPanel();
};

// ── Category page: "Pick for plan" banner ───────────
function injectCategoryPlanFeatures(){
  const stepId=getStepParam();
  if(!stepId||getPageType()!=='category')return;
  const step=ALL_STEPS.find(s=>s.id===stepId);
  if(!step)return;
  const p=getProject();
  if(p.selections[stepId])return;

  // Banner
  const banner=document.createElement('div');banner.className='plan-pick-banner';banner.id='planBanner';
  banner.innerHTML=`<div class="plan-pick-inner">
    <span class="plan-pick-icon">${step.icon}</span>
    <div class="plan-pick-text"><strong>Picking for your build plan:</strong> ${step.label}
      <div class="plan-pick-hint">Click "🏠+" on any card to add it</div></div>
    <button class="plan-pick-close" onclick="this.parentElement.parentElement.remove();history.replaceState(null,'',location.pathname);">✕</button>
  </div>`;
  const hero=document.querySelector('.page-hero');
  if(hero&&hero.nextElementSibling)hero.parentNode.insertBefore(banner,hero.nextElementSibling);
  else if(hero)hero.parentNode.appendChild(banner);
}

// ── Universal "Add to Plan" buttons on ALL cards ────
function addPlanButtonsToCards(){
  document.querySelectorAll('.builder-card').forEach(card=>{
    if(card.querySelector('.card-plan-btn'))return;
    const href=card.getAttribute('href')||'';
    const m=href.match(/business\/([^/.?#]+)\.html/);
    if(!m)return;
    const slug=m[1];
    const nameEl=card.querySelector('.card-name');
    const name=nameEl?nameEl.textContent.trim():slug;

    // Check if already assigned somewhere
    const p=getProject();
    const assignedStep=ALL_STEPS.find(s=>p.selections[s.id]&&p.selections[s.id].slug===slug);

    const btn=document.createElement('button');
    btn.className='card-plan-btn'+(assignedStep?' added':'');
    btn.setAttribute('data-plan-slug',slug);
    btn.setAttribute('data-plan-name',name);
    if(assignedStep){
      btn.innerHTML=`<span>✓</span> In Plan`;
      btn.title='This business is in your Build Plan — click to view';
      btn.onclick=function(e){e.preventDefault();e.stopPropagation();toggleWizard();};
    } else {
      btn.innerHTML=`<span>🏠</span> Add to Plan`;
      btn.title='Add to Build Plan';
      btn.onclick=function(e){
        e.preventDefault();e.stopPropagation();
        // If there's a ?step= param, add directly to that step
        const stepParam=getStepParam();
        if(stepParam){
          const step=ALL_STEPS.find(s=>s.id===stepParam);
          if(step&&!getProject().selections[stepParam]){
            window.quickAdd(stepParam,slug,name,btn);
            return;
          }
        }
        // Otherwise show step picker
        showStepPicker(btn,slug,name);
      };
    }
    const footer=card.querySelector('.card-footer');
    if(footer)footer.appendChild(btn);
  });
}

// Refresh plan buttons (after adding/removing)
function refreshPlanButtons(){
  document.querySelectorAll('.card-plan-btn').forEach(el=>el.remove());
  addPlanButtonsToCards();
  addPlanToFeaturedCards();
}

// ── Plan button on Featured cards ───────────────────
function addPlanToFeaturedCards(){
  document.querySelectorAll('.feat-plan-slot').forEach(slot=>{
    if(slot.querySelector('.card-plan-btn'))return;
    const slug=slot.dataset.slug;
    const name=slot.dataset.name;
    if(!slug)return;
    const p=getProject();
    const assignedStep=ALL_STEPS.find(s=>p.selections[s.id]&&p.selections[s.id].slug===slug);
    const btn=document.createElement('button');
    btn.className='card-plan-btn'+(assignedStep?' added':'');
    if(assignedStep){
      btn.innerHTML=`<span>✓</span> In Plan`;
      btn.onclick=function(e){e.preventDefault();e.stopPropagation();toggleWizard();};
    } else {
      btn.innerHTML=`<span>🏠</span> Add to Plan`;
      btn.onclick=function(e){
        e.preventDefault();e.stopPropagation();
        showStepPicker(btn,slug,name);
      };
    }
    slot.appendChild(btn);
  });
}

// ── Category → Step mapping for smart recommendations ──
const CAT_STEP_MAP={
  'building contractors':'builder','custom home builder':'builder','general contractor':'builder','remodeling':'builder','remodeling contractors':'builder',
  'architects':'architect','architect':'architect','design':'architect','interior design':'architect','design services':'architect','drafting services':'architect',
  'banking & mortgage':'financing','mortgage banking - construction lending':'financing','banking':'financing','financial services':'financing','insurance':'financing',
  'real estate':'land','land':'land','property':'land','surveying':'land','land surveying':'land',
  'excavating':'excavation','excavating contractors':'excavation','site work':'excavation','grading':'excavation','demolition':'excavation',
  'concrete':'foundation','concrete contractors':'foundation','foundation':'foundation','waterproofing':'foundation','basement':'foundation',
  'framing':'framing','framing contractors':'framing','timber frame':'framing','log homes':'framing','structural':'framing',
  'roofing':'roofing','roofing contractors':'roofing',
  'siding':'siding','siding contractors':'siding','windows & doors':'siding','windows':'siding','doors':'siding','gutters':'siding',
  'electrical':'electrical','electrical contractors':'electrical','solar':'electrical','generators':'electrical','lighting':'electrical',
  'plumbing':'plumbing','plumbing contractors':'plumbing','well drilling':'plumbing','septic':'plumbing','water treatment':'plumbing',
  'heating & cooling':'hvac','hvac':'hvac','heating':'hvac','air conditioning':'hvac','mechanical':'hvac','fireplace':'hvac','geothermal':'hvac',
  'insulation':'insulation','insulation contractors':'insulation','energy':'insulation','weatherization':'insulation',
  'drywall':'drywall','drywall contractors':'drywall','plastering':'drywall',
  'painting':'painting','painting contractors':'painting','staining':'painting','coatings':'painting',
  'flooring':'flooring','flooring contractors':'flooring','carpet':'flooring','tile':'flooring','hardwood':'flooring',
  'kitchen & bath':'cabinets','cabinets':'cabinets','cabinetry':'cabinets','countertops':'cabinets','closets':'cabinets','millwork':'cabinets',
  'landscaping':'landscaping','landscape':'landscaping','lawn':'landscaping','irrigation':'landscaping','fencing':'landscaping','decks':'landscaping','deck':'landscaping','paving':'landscaping','asphalt':'landscaping','concrete flatwork':'landscaping'
};

function getRecommendedSteps(bizName){
  // Find the card's categories from DOM
  const card=document.querySelector(`.builder-card .card-name`);
  let cats=[];
  // Try to find categories from the card that matches this business
  document.querySelectorAll('.builder-card').forEach(c=>{
    const nameEl=c.querySelector('.card-name');
    if(nameEl&&nameEl.textContent.trim()===bizName){
      c.querySelectorAll('.card-trade').forEach(b=>cats.push(b.textContent.trim()));
      c.querySelectorAll('.card-cat-tag').forEach(b=>cats.push(b.textContent.trim()));
    }
  });
  // Also check page-level category (on category pages)
  const pageCat=document.querySelector('.page-hero h1');
  if(pageCat)cats.push(pageCat.textContent.trim());

  const matched=new Set();
  cats.forEach(cat=>{
    const key=cat.toLowerCase().replace(/\s*contractors?\s*/g,' contractors').trim();
    // Direct match
    if(CAT_STEP_MAP[key])matched.add(CAT_STEP_MAP[key]);
    // Partial match — check if any mapping key is contained in cat or vice versa
    Object.entries(CAT_STEP_MAP).forEach(([k,v])=>{
      if(key.includes(k)||k.includes(key))matched.add(v);
    });
  });
  return [...matched];
}

// ── Step Picker Popover ─────────────────────────────
function showStepPicker(anchorBtn,slug,name){
  closeStepPicker();
  const p=getProject();
  const unfilled=ALL_STEPS.filter(s=>!p.selections[s.id]);
  if(!unfilled.length){toggleWizard();return;}

  const recommended=getRecommendedSteps(name);
  const picker=document.createElement('div');
  picker.className='step-picker';
  picker.id='stepPicker';

  let h=`<div class="sp-header">Add to Build Plan<button class="sp-close" onclick="closeStepPicker()">✕</button></div>`;
  h+=`<div class="sp-list">`;

  // Show recommended steps first if any
  const recSteps=unfilled.filter(s=>recommended.includes(s.id));
  const otherSteps=unfilled.filter(s=>!recommended.includes(s.id));

  if(recSteps.length){
    h+=`<div class="sp-phase sp-recommended">★ Recommended</div>`;
    recSteps.forEach(s=>{
      h+=`<button class="sp-item sp-item-rec" onclick="pickStep('${s.id}','${slug}','${esc(name)}')"><span>${s.icon}</span>${s.label}</button>`;
    });
    if(otherSteps.length){
      h+=`<div class="sp-phase">Other Roles</div>`;
    }
  }

  if(!recSteps.length){
    // No recommendations — show by phase as before
    BUILD_PHASES.forEach(phase=>{
      const phaseUnfilled=phase.steps.filter(s=>!p.selections[s.id]);
      if(!phaseUnfilled.length)return;
      h+=`<div class="sp-phase">${phase.phase}</div>`;
      phaseUnfilled.forEach(s=>{
        h+=`<button class="sp-item" onclick="pickStep('${s.id}','${slug}','${esc(name)}')"><span>${s.icon}</span>${s.label}</button>`;
      });
    });
  } else {
    // Show remaining by phase
    BUILD_PHASES.forEach(phase=>{
      const phaseOther=phase.steps.filter(s=>!p.selections[s.id]&&!recommended.includes(s.id));
      if(!phaseOther.length)return;
      if(!recSteps.length)h+=`<div class="sp-phase">${phase.phase}</div>`;
      phaseOther.forEach(s=>{
        h+=`<button class="sp-item" onclick="pickStep('${s.id}','${slug}','${esc(name)}')"><span>${s.icon}</span>${s.label}</button>`;
      });
    });
  }

  h+=`</div>`;
  picker.innerHTML=h;
  document.body.appendChild(picker);

  // Position near the button
  const rect=anchorBtn.getBoundingClientRect();
  const pickerW=260,pickerMaxH=360;
  let top=rect.bottom+6;
  let left=rect.right-pickerW;
  if(left<8)left=8;
  if(top+pickerMaxH>window.innerHeight)top=rect.top-pickerMaxH-6;
  picker.style.top=top+'px';
  picker.style.left=left+'px';

  requestAnimationFrame(()=>picker.classList.add('open'));

  // Close on outside click
  setTimeout(()=>{
    document.addEventListener('click',closeStepPickerOutside);
  },10);
}

function closeStepPicker(){
  const p=document.getElementById('stepPicker');
  if(p)p.remove();
  document.removeEventListener('click',closeStepPickerOutside);
}
function closeStepPickerOutside(e){
  if(!e.target.closest('.step-picker')&&!e.target.closest('.card-plan-btn')){
    closeStepPicker();
  }
}

window.pickStep=function(stepId,slug,name){
  if(!getProject().type){
    const p=getProject();p.type='residential';saveProject(p);
  }
  window.selectForStep(stepId,slug,name);
  closeStepPicker();
  refreshPlanButtons();
};

// ── Business detail page: "Add to Plan" card ────────
function injectDetailPlanCard(){
  if(getPageType()!=='business')return;
  const p=getProject();
  if(!p.type)return;
  const bizSlug=getCurrentBusinessSlug(),bizName=getCurrentBusinessName();
  if(!bizSlug||!bizName)return;
  const prefix=getRoot();
  const unfilled=ALL_STEPS.filter(s=>!p.selections[s.id]);
  const assigned=ALL_STEPS.filter(s=>p.selections[s.id]&&p.selections[s.id].slug===bizSlug);
  if(!unfilled.length&&!assigned.length)return;

  const card=document.createElement('div');card.className='plan-detail-card';card.id='planDetailCard';
  let h=`<div class="plan-detail-header"><span>🏠</span> Add to Build Plan</div>`;
  if(assigned.length){
    h+=`<div class="plan-detail-assigned">✓ Assigned as: <strong>${assigned.map(s=>s.label).join(', ')}</strong></div>`;
  }
  if(unfilled.length){
    const stepParam=getStepParam();
    const priority=stepParam?unfilled.find(s=>s.id===stepParam):null;
    h+=`<div class="plan-detail-steps">`;
    if(priority){
      h+=`<button class="plan-detail-btn primary" onclick="selectForStep('${priority.id}','${bizSlug}','${esc(bizName)}')"><span>${priority.icon}</span> Add as ${priority.label}</button>`;
      const others=unfilled.filter(s=>s.id!==priority.id).slice(0,6);
      if(others.length){
        h+=`<div class="plan-detail-more-label">Or add as:</div>`;
        others.forEach(s=>{h+=`<button class="plan-detail-btn" onclick="selectForStep('${s.id}','${bizSlug}','${esc(bizName)}')"><span>${s.icon}</span> ${s.label}</button>`;});
      }
    } else {
      unfilled.forEach(s=>{h+=`<button class="plan-detail-btn" onclick="selectForStep('${s.id}','${bizSlug}','${esc(bizName)}')"><span>${s.icon}</span> ${s.label}</button>`;});
    }
    h+=`</div>`;
  }
  card.innerHTML=h;
  const claim=document.querySelector('.claim-banner');
  if(claim)claim.parentNode.insertBefore(card,claim);
}
function refreshDetailPlanCard(){
  const old=document.getElementById('planDetailCard');if(old)old.remove();
  injectDetailPlanCard();
}

function updatePlanBadge(){
  const c=getCompletedCount();
  document.querySelectorAll('.plan-count-badge').forEach(el=>{el.textContent=c;el.style.display=c>0?'':'none';});
}

// ── Hearts on cards ─────────────────────────────────
function addHeartsToCards(){
  document.querySelectorAll('.builder-card').forEach(card=>{
    if(card.querySelector('.heart-btn'))return;
    const href=card.getAttribute('href')||'';
    const m=href.match(/business\/([^/.?#]+)\.html/);if(!m)return;
    const slug=m[1];
    const btn=document.createElement('button');
    btn.className='heart-btn'+(isFavorite(slug)?' is-fav':'');
    btn.setAttribute('data-fav-slug',slug);
    btn.innerHTML=`<span class="heart-icon">${isFavorite(slug)?'♥':'♡'}</span>`;
    btn.onclick=function(e){e.preventDefault();e.stopPropagation();toggleFavorite(slug);};
    const top=card.querySelector('.card-header');if(top)top.appendChild(btn);
  });
  // Detail page hero heart
  const bizSlug=getCurrentBusinessSlug();
  if(bizSlug&&!document.getElementById('detailHeart')){
    const hero=document.querySelector('.page-hero-content');
    if(hero){
      const btn=document.createElement('button');btn.id='detailHeart';
      btn.className='heart-btn detail-heart'+(isFavorite(bizSlug)?' is-fav':'');
      btn.setAttribute('data-fav-slug',bizSlug);
      btn.innerHTML=`<span class="heart-icon">${isFavorite(bizSlug)?'♥':'♡'}</span> <span class="heart-label">${isFavorite(bizSlug)?'Saved':'Save'}</span>`;
      btn.onclick=function(e){e.preventDefault();toggleFavorite(bizSlug);};
      hero.appendChild(btn);
    }
  }
}

// ── Init ────────────────────────────────────────────
function injectUI(){
  // Overlay
  const ov=document.createElement('div');ov.id='wizardOverlay';ov.className='wz-overlay';
  ov.onclick=function(){document.getElementById('wizardPanel').classList.remove('open');document.getElementById('favPanel').classList.remove('open');ov.classList.remove('open');};
  document.body.appendChild(ov);
  // Panels
  const wp=document.createElement('div');wp.id='wizardPanel';wp.className='wz-panel';document.body.appendChild(wp);
  const fp=document.createElement('div');fp.id='favPanel';fp.className='wz-panel fav-panel';document.body.appendChild(fp);
  // FABs
  const completed=getCompletedCount(),favCount=getFavorites().length;
  const fab=document.createElement('div');fab.className='wz-fab-wrap';
  fab.innerHTML=`
    <button class="wz-fab fav-fab" onclick="toggleFavPanel()" title="Saved"><span>♥</span><span class="fav-count-badge" style="${favCount>0?'':'display:none'}">${favCount}</span></button>
    <button class="wz-fab build-fab" onclick="toggleWizard()" title="Build Planner"><span>🏠</span><span class="wz-fab-label">Build Planner</span><span class="plan-count-badge" style="${completed>0?'':'display:none'}">${completed}</span></button>`;
  document.body.appendChild(fab);

  addHeartsToCards();
  addPlanButtonsToCards();
  addPlanToFeaturedCards();
  const grid=document.getElementById('builderGrid')||document.getElementById('catGrid');
  if(grid)new MutationObserver(()=>{addHeartsToCards();addPlanButtonsToCards();}).observe(grid,{childList:true});

  injectCategoryPlanFeatures();
  injectDetailPlanCard();
  checkForSharedPlan();
  checkForSharedFavorites();
  updateFavCount();updatePlanBadge();
}

// ── Shared Plan Viewer ──────────────────────────────
function checkForSharedPlan(){
  const params=new URLSearchParams(window.location.search);
  const encoded=params.get('shared_plan');
  if(!encoded)return;
  const plan=decodePlan(encoded);
  if(!plan)return;
  showSharedPlanOverlay(plan);
}

function showSharedPlanOverlay(plan){
  const prefix=getRoot();
  const selections=plan.selections||{};
  const count=Object.keys(selections).length;

  const overlay=document.createElement('div');
  overlay.className='shared-plan-overlay';
  overlay.id='sharedPlanOverlay';

  let h=`<div class="shared-plan-card">
    <div class="shared-plan-header">
      <div class="shared-plan-tag">🏠 Shared Build Plan</div>
      <h2>${plan.type==='commercial'?'Commercial':'Residential'} Build — ${count} Vendors Selected</h2>
      <p>Someone shared their Northwest Michigan build plan with you. Browse the selected vendors below.</p>
    </div>
    <div class="shared-plan-phases">`;

  BUILD_PHASES.forEach(phase=>{
    const filled=phase.steps.filter(s=>selections[s.id]);
    const unfilled=phase.steps.filter(s=>!selections[s.id]);
    h+=`<div class="shared-phase">
      <div class="shared-phase-label">${phase.phase}</div>`;
    filled.forEach(step=>{
      const sel=selections[step.id];
      h+=`<a href="${prefix}business/${sel.slug}.html" class="shared-vendor">
        <div class="shared-vendor-icon">${step.icon}</div>
        <div class="shared-vendor-info">
          <div class="shared-vendor-role">${step.label}</div>
          <div class="shared-vendor-name">${sel.name}</div>
        </div>
        <span class="shared-vendor-arrow">→</span>
      </a>`;
    });
    unfilled.forEach(step=>{
      h+=`<div class="shared-vendor empty">
        <div class="shared-vendor-icon">${step.icon}</div>
        <div class="shared-vendor-info">
          <div class="shared-vendor-role">${step.label}</div>
          <div class="shared-vendor-name empty-name">Not yet selected</div>
        </div>
      </div>`;
    });
    h+=`</div>`;
  });

  h+=`</div>
    <div class="shared-plan-actions">
      <button class="shared-plan-btn primary" onclick="importSharedPlan()">📋 Use This Plan as My Starting Point</button>
      <button class="shared-plan-btn" onclick="document.getElementById('sharedPlanOverlay').remove();history.replaceState(null,'',location.pathname);">Browse Directory Instead</button>
    </div>
  </div>`;

  overlay.innerHTML=h;
  document.body.appendChild(overlay);
  requestAnimationFrame(()=>overlay.classList.add('open'));

  // Store the shared plan data for potential import
  overlay._planData=plan;
}

window.importSharedPlan=function(){
  const overlay=document.getElementById('sharedPlanOverlay');
  if(!overlay||!overlay._planData)return;
  const plan=overlay._planData;
  if(confirm('Import this plan? It will replace your current build plan.')){
    saveProject(plan);
    overlay.remove();
    history.replaceState(null,'',location.pathname);
    renderWizard();updatePlanBadge();
    // Open the wizard to show the imported plan
    setTimeout(()=>toggleWizard(),300);
  }
};

// Expose
window.toggleFavorite=toggleFavorite;window.saveFavorites=saveFavorites;
window.updateAllHearts=updateAllHearts;window.updateFavCount=updateFavCount;
window.isFavorite=isFavorite;window.renderWizard=renderWizard;window.renderFavPanel=renderFavPanel;

if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',injectUI);else injectUI();
})();
