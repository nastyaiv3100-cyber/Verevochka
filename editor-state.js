/* Project persistence, history and export checks. No project data leaves this browser. */
(() => {
 'use strict';
 const storageKey='verevochka:editor:v1:'+new URL('.',location.href).pathname;
 const clone=value=>structuredClone(value);
 const object=value=>value!==null&&typeof value==='object'&&!Array.isArray(value);
 const own=(value,key)=>Object.prototype.hasOwnProperty.call(value,key);
 let restoring=false,resetting=false,timer=null,dirty=false,saveFailed=false;
 let history=[],historyIndex=-1;

 const actions=document.querySelector('.actions');
 for(const [id,text] of [['undoEdit','Отменить'],['redoEdit','Повторить']]){
  const button=document.createElement('button');button.id=id;button.type='button';
  button.className='btn subtle';button.textContent=text;button.disabled=true;
  button.title=text+(id==='undoEdit'?' (Ctrl+Z)':' (Ctrl+Shift+Z)');
  actions.insertBefore(button,$('saveConfig'));
 }
 const status=document.createElement('small');status.id='saveStatus';status.setAttribute('role','status');status.setAttribute('aria-live','polite');
 document.querySelector('.brand>div').appendChild(status);
 const header=document.querySelector('.top');
 const syncHeaderHeight=()=>document.documentElement.style.setProperty('--editor-header-height',header.getBoundingClientRect().height+'px');
 if(typeof ResizeObserver==='function')new ResizeObserver(syncHeaderHeight).observe(header);
 window.addEventListener('resize',syncHeaderHeight);syncHeaderHeight();
 const setStatus=(text,failed=false)=>{status.textContent=text;status.classList.toggle('saveFailed',failed)};
 const questionState=()=>typeof getQuestionEditorState==='function'?getQuestionEditorState():null;
 const capture=()=>({settings:clone(readSettings()),editor:clone(questionState())});
 const signature=snapshot=>JSON.stringify(snapshot);
 const updateHistoryButtons=()=>{$('undoEdit').disabled=historyIndex<=0;$('redoEdit').disabled=historyIndex>=history.length-1};

 function record(snapshot){
  const serialized=signature(snapshot);
  if(history[historyIndex]!==serialized){
   history=history.slice(0,historyIndex+1);history.push(serialized);historyIndex=history.length-1;
   while(history.length>40||(history.length>2&&history.reduce((size,item)=>size+item.length,0)>25*1024*1024)){history.shift();historyIndex--}
  }
  updateHistoryButtons();
 }
 function persist(snapshot){
  if(resetting)return false;
  try{
   localStorage.setItem(storageKey,JSON.stringify({version:1,...snapshot}));
   dirty=false;saveFailed=false;setStatus('Сохранено на этом устройстве');return true;
  }catch(e){
   dirty=true;saveFailed=true;
   setStatus('Автосохранение недоступно. Скачайте настройки JSON, чтобы сохранить работу.',true);return false;
  }
 }
 function checkpoint(){
  clearTimeout(timer);timer=null;
  if(restoring||resetting)return;
  const snapshot=capture();record(snapshot);persist(snapshot);
 }
 function scheduleEditorState(){
  if(restoring||resetting)return;
  dirty=true;setStatus('Сохранение…');clearTimeout(timer);timer=setTimeout(checkpoint,180);
 }
 window.scheduleEditorState=scheduleEditorState;

 function checkProjectShape(data){
  if(!object(data))throw new Error('Настройки должны быть JSON-объектом.');
  const current=readSettings();
  for(const [key,value] of Object.entries(data)){
   if(key==='_editor'){
    if(value!==null&&!object(value))throw new Error('Некорректные данные редактора.');
    continue;
   }
   if(!own(current,key))continue;
   const expected=current[key];
   if(Array.isArray(expected)){
    if(!Array.isArray(value))throw new Error(`Поле «${key}» должно быть списком.`);
   }else if(object(expected)){
    if(!object(value))throw new Error(`Поле «${key}» должно быть объектом.`);
    for(const [name,item] of Object.entries(value)){
     if(['assetFiles','assetOverrides'].includes(key)){if(item!==null&&typeof item!=='string')throw new Error(`Некорректная картинка «${key}.${name}».`)}else if(own(expected,name)&&typeof item!==typeof expected[name])throw new Error(`Некорректное значение «${key}.${name}».`);
    }
   }else if(typeof value!==typeof expected||typeof value==='number'&&!Number.isFinite(value))throw new Error(`Некорректное значение «${key}».`);
  }
  if(own(data,'questions'))for(const [index,q] of data.questions.entries()){
   const label=`Вопрос ${index+1}`;
   if(!object(q))throw new Error(`${label}: ожидается объект вопроса.`);
   for(const name of ['type','q','image','sentence','errorWord'])if(own(q,name)&&typeof q[name]!=='string')throw new Error(`${label}: некорректное поле «${name}».`);
   for(const name of ['a','accepted','items'])if(own(q,name)&&(!Array.isArray(q[name])||q[name].some(item=>typeof item!=='string')))throw new Error(`${label}: поле «${name}» должно содержать строки.`);
   if(own(q,'pairs')&&(!Array.isArray(q.pairs)||q.pairs.some(pair=>!object(pair)||typeof pair.left!=='string'||typeof pair.right!=='string')))throw new Error(`${label}: некорректный список пар.`);
   if(own(q,'categories')&&(!Array.isArray(q.categories)||q.categories.some(group=>!object(group)||typeof group.name!=='string'||!Array.isArray(group.items)||group.items.some(item=>typeof item!=='string'))))throw new Error(`${label}: некорректные категории.`);
   if(own(q,'gaps')&&(!Array.isArray(q.gaps)||q.gaps.some(item=>typeof item!=='string'&&(!Array.isArray(item)||item.some(answer=>typeof answer!=='string')))))throw new Error(`${label}: некорректные ответы для пропусков.`);
  }
  if(own(data,'ropeLayout')&&data.ropeLayout.some(rope=>!object(rope)||['x','y','length'].some(key=>own(rope,key)&&(typeof rope[key]!=='number'||!Number.isFinite(rope[key])))))throw new Error('Некорректные положения верёвок.');
 }
 function mergeSettings(data){
  checkProjectShape(data);
  const previous=clone(readSettings()),settings={...previous,...clone(data)};
  delete settings._editor;
  for(const key of ['theme','sceneLayout','feedbackImages','soundEffects','soundPresets'])if(own(data,key))settings[key]={...previous[key],...clone(data[key])};
  // Sparse image maps describe this project's complete set of custom assets.
  // An explicit empty map must clear another project's uploads and URLs.
  for(const key of ['assetFiles','assetOverrides'])if(own(data,key))settings[key]=clone(data[key]);
  return settings;
 }

 function applyControls(data,editor=null){
  clearImageOptimization();
  $('gameTitle').value=data.title;
  for(const key of ['startTitle','startText','cardLabel','loseTitle','winTitle','startButton','againButton','playAgainButtonText','accentA','accentB','ropeColor','textColor'])$(key).value=data[key];
  $('fontName').value=data.font;
  for(const key of ['ropeWidth','fishSize','foodRotation','catSize','ropeHeroSize','ropeHeroOffsetX','ropeHeroOffsetY','jumpHeroSize','jumpHeroOffsetX','jumpHeroOffsetY','ropeLength','swingSpeed','swingAmount','lives'])$(key).value=key==='ropeLength'?Number(data[key])*100:data[key];
  for(const [key,id] of [['sound','soundStart'],['shuffleQuestions','shuffleQuestions'],['revealCorrect','revealCorrect'],['showTitlePage','showTitlePage'],['winImageEnabled','winImageEnabled'],['loseImageEnabled','loseImageEnabled'],['draftEnabled','draftEnabled'],['translateInterface','autoTranslateUI']])$(id).checked=!!data[key];
  $('cardWidth').value=data.cardWidth;$('cardHeight').value=data.cardHeight;
  sceneLayout=clone(data.sceneLayout);ropeLayout=clone(data.ropeLayout);
  originalConfig.questions=clone(data.questions);originalConfig.assetFiles=clone(data.assetFiles);originalConfig.assetOverrides=clone(data.assetOverrides);
  for(const kind of ['win','lose']){
   feedbackImages[kind]=data.feedbackImages[kind]||'';
   $(`${kind}ImageUrl`).value=String(feedbackImages[kind]).startsWith('data:image/')?'':feedbackImages[kind];
  }
  for(const kind of Object.keys(soundEffects)){
   soundEffects[kind]=data.soundEffects[kind]||'';
   const select=$(`${kind}SoundPreset`),value=data.soundPresets[kind];
   if([...select.options].some(option=>option.value===value))select.value=value;
   showSoundPreview(kind);
  }
  const themeKeys=Object.keys(readThemeSettings());
  for(const key of themeKeys){
   if(key==='titleImageData')continue;
   const el=$(key),value=data.theme[key];
   if(!el||value===undefined)continue;
   if(el.type==='checkbox')el.checked=!!value;else if(el.type!=='file')el.value=value;
  }
  titleImageData=data.theme.titleImageData||'';
  $('titleImageUrl').value=String(titleImageData).startsWith('data:image/')?'':titleImageData;
  $('celebrationEffect').value=data.celebrationEffect;$('draftBg').value=data.draftBg;$('uiLanguage').value=data.uiLanguage;
  $('uiLanguage').disabled=!$('autoTranslateUI').checked;
  if(typeof restoreQuestionEditorState==='function')restoreQuestionEditorState(null);
  renderAssets();renderQuestions();watchFields();updateEditorMetrics();renderPreviewHandles();syncOptimizedImagePreviews();
  if(typeof restoreQuestionEditorState==='function')restoreQuestionEditorState(editor);
  refreshPreview();
 }
 function restoreSnapshot(snapshot){
  restoring=true;clearTimeout(timer);clearTimeout(previewTimer);timer=null;
  try{applyControls(clone(snapshot.settings),clone(snapshot.editor))}finally{restoring=false}
 }
 window.loadEditorProject=data=>{
  const settings=mergeSettings(data),before=capture();
  try{restoreSnapshot({settings,editor:clone(data._editor??null)})}catch(error){restoreSnapshot(before);throw error}
  history=[];historyIndex=-1;record(capture());persist(capture());toast('Настройки загружены.');
 };
 window.saveEditorProject=()=>{
  checkpoint();
  download('kot_protiv_goloda_settings.json',JSON.stringify({...readSettings(),_editor:questionState()},null,2),'application/json');
 };
 window.resetEditorProject=()=>{
  resetting=true;clearTimeout(timer);
  try{localStorage.removeItem(storageKey)}catch(e){}
  location.reload();
 };
 function navigateHistory(direction){
  if(timer||dirty)checkpoint();const index=historyIndex+direction;
  if(index<0||index>=history.length)return;
  const before=capture();
  try{restoreSnapshot(JSON.parse(history[index]));historyIndex=index;updateHistoryButtons();persist(capture())}
  catch(error){restoreSnapshot(before);toast('Не удалось отменить действие: '+error.message)}
 }
 $('undoEdit').addEventListener('click',()=>navigateHistory(-1));$('redoEdit').addEventListener('click',()=>navigateHistory(1));
 document.addEventListener('keydown',event=>{
  if(!(event.ctrlKey||event.metaKey)||event.altKey||event.target.closest('input,textarea,[contenteditable="true"]'))return;
  const key=event.key.toLowerCase();
  if(key==='z'||key==='y'){
   event.preventDefault();navigateHistory(key==='y'||event.shiftKey?1:-1);
  }
 });
 const previousQueuePreview=queuePreview;
 queuePreview=function(){previousQueuePreview();scheduleEditorState()};
 for(const name of ['input','change'])document.querySelector('.editor').addEventListener(name,event=>{
  if(event.target.id==='geniallyEmbedCode')return;
  scheduleEditorState();
 });
 document.addEventListener('question-editor-change',scheduleEditorState);
 window.addEventListener('pagehide',()=>{if(!resetting&&!restoring)checkpoint()});
 window.addEventListener('beforeunload',event=>{
  if(!resetting&&!restoring&&dirty)checkpoint();
  if(!resetting&&dirty&&saveFailed){event.preventDefault();event.returnValue=''}
 });

 function questionErrors(includeDraft=true){
  const errors=typeof validateQuestions==='function'?validateQuestions(readSettings().questions):[];
  if(includeDraft&&typeof getQuestionEditorErrors==='function')errors.push(...getQuestionEditorErrors());
  return [...new Set(errors)];
 }
 function showExportErrors(errors){
  $('copyGeniallyCode').disabled=true;$('downloadGame').disabled=true;$('openHtmlPreview').disabled=true;
  $('geniallyEmbedCode').value='';$('gameFileSize').textContent='Нужна проверка заданий';$('gameSizeStatus').textContent=errors.join(' ');
  $('geniallyWarningTitle').textContent='Исправьте задания перед экспортом.';$('geniallyWarningText').textContent=errors.join(' ');$('geniallyWarning').hidden=false;
 }
 function previewErrors(errors){
  $('preview').srcdoc='<!doctype html><html lang="ru"><meta charset="utf-8"><style>body{font:16px system-ui;padding:24px;background:#faf7ed;color:#343723}li{margin:12px 0}</style><h1>Проверьте задания</h1><ul>'+errors.map(error=>'<li>'+esc(error)+'</li>').join('')+'</ul>';
  $('previewStatus').textContent='Исправьте задания';
 }
 const previousBuildGame=buildGame;
 buildGame=function(previewMode=false){
  const errors=questionErrors(false);
  if(errors.length)throw new Error(errors.join(' '));
  return previousBuildGame(previewMode);
 };
 const previousRefreshPreview=refreshPreview;
 refreshPreview=function(){
  if(!restoring)scheduleEditorState();
  const errors=questionErrors(false);
  if(errors.length){previewErrors(errors);showExportErrors(errors);return}
  previousRefreshPreview();
 };
 const previousUpdateExport=updateExportInfo;
 updateExportInfo=async function(html){
  const errors=questionErrors();
  if(errors.length){exportBuildSequence++;showExportErrors(errors);return}
  $('downloadGame').disabled=false;$('openHtmlPreview').disabled=false;
  return previousUpdateExport(html);
 };
 const previousRefreshExport=refreshExportSummary;
 refreshExportSummary=async function(){
  const errors=questionErrors();
  if(errors.length){exportBuildSequence++;showExportErrors(errors);return false}
  await previousRefreshExport();return true;
 };
 window.canExportProject=()=>{
  const errors=questionErrors();
  if(errors.length){showExportErrors(errors);toast(errors[0]);return false}
  return true;
 };
 window.copyGeniallyCode=async()=>{
  if(!window.canExportProject())return;
  if(!await refreshExportSummary())return;
  const area=$('geniallyEmbedCode'),code=area.value;
  if(!code){toast('Код для Genially пока недоступен. Проверьте сообщение в разделе экспорта.');return}
  try{
   if(!navigator.clipboard?.writeText)throw new Error('Clipboard unavailable');
   await navigator.clipboard.writeText(code);toast('iframe-код скопирован.');return;
  }catch(e){}
  area.focus();area.select();area.setSelectionRange(0,area.value.length);
  let copied=false;
  try{copied=document.execCommand('copy')===true}catch(e){}
  toast(copied?'iframe-код скопирован.':'Автоматическое копирование недоступно. Код выделен: нажмите Ctrl+C или ⌘C.');
 };
 document.addEventListener('question-editor-change',()=>{refreshExportSummary()});

 const initial=capture();let restored=false,unreadable=false;
 try{
  const raw=localStorage.getItem(storageKey);
  if(raw){
   const saved=JSON.parse(raw);
   if(saved.version!==1||!object(saved.settings))throw new Error('Неизвестный формат сохранения.');
   const settings=mergeSettings(saved.settings);
   restoreSnapshot({settings,editor:saved.editor??null});restored=true;
  }
 }catch(error){
  unreadable=true;
  try{restoreSnapshot(initial)}catch(e){}
  setStatus('Не удалось восстановить автосохранение. Загрузите настройки JSON, если они сохранены.',true);
 }
 record(capture());
 if(!unreadable){persist(capture());if(restored)setStatus('Проект восстановлен. Сохранено на этом устройстве')}
 refreshExportSummary();
})();
