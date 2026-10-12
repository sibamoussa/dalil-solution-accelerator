const words = {
  en: {accelerator:'Solution accelerator', collection:'SOURCE COLLECTION', gazette:'Abu Dhabi Official Gazette', issues:'8 Arabic issues', originals:'Original publications ↗', legal:'Public-source demonstration. Not an official government service or legal advice.', title:'Policy conversation', newChat:'New conversation', welcome:'What would you like to know?', question1:"What changed for the fishermen’s cooperative?", question2:'What are the early customs release provisions?', question3:'What does the 2026 ADAFSA board decision say?', inputLabel:'Your policy question', ready:'Ready', send:'Send', disclaimer:'Check the original publication before relying on an answer. Publication in 2026 does not establish current legal validity.', placeholder:'Ask about the 2026 gazettes...', thinking:'Reviewing the evidence...', failed:'Request unavailable', retry:'Retry', you:'You', issue:'Issue'},
  ar: {accelerator:'مسرّع حلول', collection:'مجموعة المصادر', gazette:'الجريدة الرسمية لحكومة أبوظبي', issues:'8 أعداد عربية', originals:'المنشورات الأصلية ↗', legal:'عرض تجريبي بمصادر عامة. ليس خدمة حكومية رسمية أو استشارة قانونية.', title:'محادثة حول التشريعات', newChat:'محادثة جديدة', welcome:'ما الذي تود معرفته؟', question1:'ما القرار المتعلق بجمعية أبوظبي التعاونية لصيادي الأسماك؟', question2:'ما أحكام الإفراج الجمركي المبكر؟', question3:'ما قرار تشكيل مجلس إدارة هيئة أبوظبي للزراعة والسلامة الغذائية لعام 2026؟', inputLabel:'سؤالك حول التشريعات', ready:'جاهز', send:'إرسال', disclaimer:'راجع المنشور الأصلي قبل الاعتماد على الإجابة. النشر في عام 2026 لا يثبت السريان القانوني الحالي.', placeholder:'اسأل عن إصدارات الجريدة الرسمية لعام 2026...', thinking:'جارٍ مراجعة الأدلة...', failed:'تعذر إكمال الطلب', retry:'إعادة المحاولة', you:'أنت', issue:'العدد'}
};
let language = 'en';
let busy = false;
let history = [];
let configuration = null;
let conversationId = null;
let saving = false;
let historyAvailable = false;
let historyBusy = false;
let savedConversations = [];
let historyMessage = '';
Object.assign(words.en, {saveHistory:'Save conversations', deleteHistory:'Delete saved history', confirmDelete:'Delete all saved conversations for this browser?', saved:'Saving on', notSaved:'Saving off', unavailable:'History unavailable', saveFailed:'Answer received. Conversation was not saved.', historyError:'History request failed', genericCollection:'Policy documents', genericPlaceholder:'Ask about your policy documents...', genericDisclaimer:'Check the original publication before relying on an answer. Publication does not establish current legal validity.'});
Object.assign(words.ar, {saveHistory:'حفظ المحادثات', deleteHistory:'حذف سجل المحادثات', confirmDelete:'حذف جميع المحادثات المحفوظة لهذا المتصفح؟', saved:'الحفظ مفعّل', notSaved:'الحفظ متوقف', unavailable:'السجل غير متاح', saveFailed:'تم استلام الإجابة ولم يتم حفظ المحادثة.', historyError:'تعذر الوصول إلى السجل', genericCollection:'وثائق السياسات', genericPlaceholder:'اسأل عن وثائق السياسات...', genericDisclaimer:'راجع المنشور الأصلي قبل الاعتماد على الإجابة. النشر لا يثبت السريان القانوني الحالي.'});
const prompt = document.querySelector('#prompt');
const messages = document.querySelector('#messages');
const status = document.querySelector('#status');
const send = document.querySelector('#send');
const clear = document.querySelector('#clear');
const welcome = document.querySelector('#welcome');
const historyToggle = document.querySelector('#historyToggle');
const deleteHistory = document.querySelector('#deleteHistory');

function renderHistory() {
  historyToggle.checked = saving;
  historyToggle.disabled = !historyAvailable || busy || historyBusy;
  deleteHistory.disabled = !savedConversations.length || busy || historyBusy;
  document.querySelector('#historyStatus').textContent = historyMessage || words[language][historyAvailable ? (saving ? 'saved' : 'notSaved') : 'unavailable'];
  document.querySelector('#conversationList').replaceChildren(...savedConversations.map(conversation => {
    const item = document.createElement('li');
    const button = document.createElement('button');
    button.type = 'button'; button.textContent = conversation.title; button.title = conversation.title;
    button.disabled = busy || historyBusy;
    button.addEventListener('click', () => loadConversation(conversation.id));
    item.append(button); return item;
  }));
}

async function historyRequest(path='', options={}) {
  const response = await fetch(`/api/history${path}`, {...options, headers:{'Content-Type':'application/json','X-Dalil-Request':'1'}, cache:'no-store'});
  if (!response.ok) throw new Error(words[language].historyError);
  return response.json();
}

async function refreshHistory() {
  const data = await historyRequest();
  historyAvailable = data.available;
  saving = data.enabled;
  savedConversations = data.conversations;
  renderHistory();
}

async function loadConversation(id) {
  if (busy || historyBusy) return;
  historyBusy = true; send.disabled = true; clear.disabled = true; renderHistory();
  try {
    const data = await historyRequest(`/${encodeURIComponent(id)}`);
    messages.querySelectorAll('.message').forEach(entry => entry.remove());
    history = data.messages.slice(-4);
    conversationId = data.id;
    data.messages.forEach(message => append(message.role, message.content));
    historyMessage = '';
  } catch { historyMessage = words[language].historyError; }
  finally { historyBusy = false; send.disabled = false; clear.disabled = false; renderHistory(); }
}

function renderLanguage() {
  document.documentElement.lang = language;
  document.documentElement.dir = language === 'ar' ? 'rtl' : 'ltr';
  document.querySelectorAll('[data-text]').forEach(element => { element.textContent = words[language][element.dataset.text]; });
  document.querySelector('#language').textContent = language === 'en' ? 'العربية' : 'English';
  prompt.placeholder = words[language].placeholder;
  status.textContent = busy ? words[language].thinking : words[language].ready;
  const list = document.querySelector('#issueList');
  const documents = configuration?.documents || [];
  const gazettes = documents.length > 0 && documents.every(document => Number.isInteger(document.issue));
  if (configuration && !gazettes) {
    document.querySelector('[data-text="gazette"]').textContent = words[language].genericCollection;
    document.querySelector('.year').textContent = String(documents.length);
    prompt.placeholder = words[language].genericPlaceholder;
    document.querySelector('[data-text="disclaimer"]').textContent = words[language].genericDisclaimer;
  }
  list.replaceChildren(...documents.map((documentSource, index) => {
    const item = document.createElement('li');
    const link = document.createElement('a');
    link.href = documentSource.url;
    link.target = '_blank'; link.rel = 'noopener noreferrer';
    link.textContent = gazettes ? `${words[language].issue} ${String(index + 1).padStart(2,'0')}` : documentSource.title;
    const format = document.createElement('span'); format.textContent = `${(documentSource.format || 'pdf').toUpperCase()} ↗`; link.append(format); item.append(link); return item;
  }));
  renderHistory();
}
function append(role, text, markup='') {
  welcome.hidden = true;
  const entry = document.createElement('article'); entry.className = `message ${role}`;
  const author = document.createElement('div'); author.className = 'author'; author.textContent = role === 'user' ? words[language].you : (configuration?.branding.title || document.title);
  const content = document.createElement('div'); content.className = 'content'; content.dir = 'auto';
  if (markup) {
    const parsed = new DOMParser().parseFromString(markup, 'text/html');
    const allowed = new Set(['P','UL','OL','LI','STRONG','EM','A','BR']);
    for (const element of [...parsed.body.querySelectorAll('*')].reverse()) {
      if (!allowed.has(element.tagName)) { element.replaceWith(document.createTextNode(element.textContent)); continue; }
      const href = element.getAttribute('href');
      for (const attribute of [...element.attributes]) element.removeAttribute(attribute.name);
      if (element.tagName === 'A' && href) {
        try { const url = new URL(href); if(url.protocol === 'https:' && configuration?.documents.some(source => new URL(source.url).href === url.href)) {element.href=url.href; element.target='_blank'; element.rel='noopener noreferrer';} } catch {}
      }
    }
    content.append(...parsed.body.childNodes);
  } else content.textContent = text;
  entry.append(author,content); messages.append(entry); messages.scrollTop=messages.scrollHeight; return entry;
}
async function submit(message) {
  if(!configuration || busy || historyBusy || !message.trim()) return;
  busy=true; send.disabled=true; clear.disabled=true;
  renderHistory();
  append('user',message); prompt.value=''; document.querySelector('#counter').textContent='0 / 4000';
  status.textContent=words[language].thinking;
  const waiting=append('assistant',words[language].thinking);
  try {
    const response=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json','X-Dalil-Request':'1'},body:JSON.stringify({message,history:history.slice(-4),save_history:saving,conversation_id:saving ? conversationId : null})});
    const data=await response.json();
    if(!response.ok) throw new Error(typeof data.detail==='string' ? data.detail : words[language].failed);
    waiting.remove(); append('assistant',data.answer || '',data.answer_html || '');
    history.push({role:'user',content:message},{role:'assistant',content:(data.answer || '').slice(0,4000)});
    history=history.slice(-4); status.textContent=words[language].ready;
    if (saving) {
      if (data.history_saved) {
        conversationId = data.conversation_id;
        try { await refreshHistory(); historyMessage = ''; } catch { historyMessage = words[language].historyError; }
      } else { historyMessage = words[language].saveFailed; }
    }
  } catch(error) {
    waiting.remove(); const entry=append('assistant',error.message); entry.classList.add('error');
    const retry=document.createElement('button'); retry.type='button'; retry.textContent=words[language].retry;
    retry.addEventListener('click',()=>{if(!busy){entry.remove(); submit(message);}}); entry.append(retry); status.textContent=words[language].failed;
  } finally {
    busy=false; send.disabled=false; clear.disabled=false;
    renderHistory();
    prompt.focus();
  }
}
document.querySelector('#composer').addEventListener('submit',event=>{event.preventDefault();submit(prompt.value.trim());});
prompt.addEventListener('keydown',event=>{if(event.key==='Enter' && !event.shiftKey && !event.isComposing){event.preventDefault();submit(prompt.value.trim());}});
prompt.addEventListener('input',()=>{document.querySelector('#counter').textContent=`${prompt.value.length} / 4000`;});
document.querySelector('#language').addEventListener('click',()=>{language=language==='en'?'ar':'en';renderLanguage();});
clear.addEventListener('click',()=>{if(busy || historyBusy)return;history=[];conversationId=null;messages.querySelectorAll('.message').forEach(entry=>entry.remove());welcome.hidden=false;status.textContent=words[language].ready;prompt.focus();});
historyToggle.addEventListener('change', async () => {
  historyBusy = true; send.disabled = true; clear.disabled = true;
  const enabled = historyToggle.checked;
  renderHistory();
  try {
    await historyRequest('/preference', {method:'POST', body:JSON.stringify({enabled})});
    saving = enabled; conversationId = null; historyMessage = '';
    await refreshHistory();
  } catch { historyMessage = words[language].historyError; }
  finally { historyBusy = false; send.disabled = false; clear.disabled = false; renderHistory(); }
});
deleteHistory.addEventListener('click', async () => {
  if (busy || historyBusy || !window.confirm(words[language].confirmDelete)) return;
  historyBusy = true; send.disabled = true; clear.disabled = true; renderHistory();
  try {
    await historyRequest('', {method:'DELETE'});
    conversationId = null; historyMessage = '';
    await refreshHistory();
  } catch { historyMessage = words[language].historyError; }
  finally { historyBusy = false; send.disabled = false; clear.disabled = false; renderHistory(); }
});
async function initialize() {
  send.disabled = true;
  try {
    const response = await fetch('/api/config');
    if (!response.ok) throw new Error('Configuration unavailable');
    configuration = await response.json();
    document.documentElement.style.setProperty('--accent', configuration.branding.accentColor);
    document.querySelector('.source-link').href = configuration.website;
    document.querySelectorAll('.default-arabic').forEach(element => { element.hidden = configuration.branding.title !== 'Dalil'; });
    renderLanguage();
    try { await refreshHistory(); } catch { historyMessage = words[language].historyError; renderHistory(); }
    send.disabled = false;
  } catch { status.textContent = words[language].failed; }
}
renderLanguage();
initialize();