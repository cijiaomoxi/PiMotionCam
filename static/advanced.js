/* v2.8.2 optional controls, using the same authenticated API and locale packs. */
'use strict';
(async function () {
  const tr = key => t('v282.' + key);
  const groups = [
    ['detect','analysis','analysisHint',[
      ['motion.analysis.enabled','enabled','check'],['motion.analysis.vectors','vectors','check'],
      ['motion.analysis.direction','direction',['any','left','right','up','down']],
      ['motion.analysis.threshold','threshold','number',1,255],['motion.analysis.burst_ratio','burstRatio','number',0,1,.01],
      ['motion.analysis.burst_frames','burstFrames','number',1,60],['motion.analysis.confirm_gap_frames','confirmGap','number',0,60],
      ['motion.settle_seconds','settle','number',0,60,.1],['motion.output.csv','csv','check'],
      ['motion.output.events','events','check'],['motion.output.fifo','fifo','check']]],
    ['media','recording','recordHint',[
      ['record.motion_stills','motionStills','check'],['record.stills_interval','stillsInterval','number',.2,3600,.1],
      ['record.name_template','nameTemplate','text'],['camera.stills_resolution','stillsResolution','size']]],
    ['media','archive','archiveHint',[
      ['media.archive_target','archiveTarget','text'],['media.archive_require_mount','archiveMount','check'],
      ['media.archive_min_free_percent','archiveReserve','number',0,99]]],
    ['detect','imageProcessing','imageHint',[
      ['camera.processing.crop','crop','crop'],['camera.processing.effect','effect',
        ['none','negative','solarise','sketch','denoise','emboss','oilpaint','hatch','gpen','pastel','watercolour','film','blur','saturation','colourswap','washedout','posterise','colourpoint','colourbalance','cartoon','deinterlace1','deinterlace2']],
      ['camera.processing.stabilize','stabilize','check'],['web.burn_in.enabled','burnIn','check'],
      ['web.burn_in.timestamp','timestamp','check'],['web.burn_in.text','caption','text'],['web.burn_in.font_size','fontSize','number',10,64],
      ['web.burn_in.background','background','check'],['web.burn_in.frame_info','frameInfo','check'],['web.burn_in.vu_meter','vuMeter','check']]],
    ['system','appearance','',[
      ['web.theme','theme',['dark','light','auto']],['web.custom_links','customLinks','links'],['web.log_lines','logLines','number',20,5000]]],
    ['schedule','location','solarHint',[
      ['location.latitude','latitude','coordinate',-89.9,89.9,.0001],['location.longitude','longitude','coordinate',-180,180,.0001],
      ['location.timezone','timezone','text']]],
    ['servo','servoOptions','',[
      ['servo.pan_invert','panInvert','check'],['servo.tilt_invert','tiltInvert','check'],
      ['servo.step_degrees','stepDegrees','number',.1,30,.1],['servo.multi_steps','multiSteps','number',1,50],['servo.scan_seconds','scanSeconds','number',1,3600]]],
    ['system','network','networkHint',[
      ['network.tcp_enabled','tcpEnabled','check'],['network.tcp_host','tcpHost','text'],['network.tcp_port','tcpPort','number',1,65535],
      ['network.multicast_enabled','multicastEnabled','check'],['network.multicast_group','multicastGroup','text'],['network.multicast_port','multicastPort','number',1,65535],
      ['network.allow_hosts','allowHosts','hosts'],['network.secret','secret','password']]]
  ];
  const valueAt = (object,path) => path.split('.').reduce((a,key) => a == null ? undefined : a[key],object);
  const put = (object,path,value) => { const keys=path.split('.'); let p=object; keys.slice(0,-1).forEach(key => p=p[key]||(p[key]={})); p[keys[keys.length-1]]=value; };
  const action = async (fn) => { try { return await fn(); } catch(error) { toast(error.message,'err'); return null; } };
  const panels = {};
  function button(parent,label,fn) {
    const el=document.createElement('button');el.type='button';el.textContent=tr(label);
    el.addEventListener('click',()=>action(async()=>{el.disabled=true;try{return await fn();}finally{el.disabled=false;}}));
    parent.appendChild(el);return el;
  }
  function input(parent,label,type) {
    const field=document.createElement('label');field.className='field';
    const title=document.createElement('span');title.textContent=tr(label);field.appendChild(title);
    const el=document.createElement('input');el.type=type||'text';field.appendChild(el);parent.appendChild(field);return el;
  }
  function panel(tab,title) {
    const el=document.createElement('details');el.className='panel advanced-panel';
    const summary=document.createElement('summary');summary.textContent=tr(title);el.appendChild(summary);
    $('page-'+tab).appendChild(el);return el;
  }
  function appearance(config) {
    const theme=config.web.theme;
    document.documentElement.dataset.theme=theme==='auto'?(matchMedia('(prefers-color-scheme: light)').matches?'light':'dark'):(theme||'dark');
    let links=$('extension-links');if(!links){links=document.createElement('div');links.id='extension-links';links.className='row';$('page-system').appendChild(links);}
    links.replaceChildren();
    for(const link of config.web.custom_links||[]){
      if(!/^https?:\/\//.test(link.url||''))continue;
      const a=document.createElement('a');a.textContent=link.title||link.url;a.href=link.url;a.target='_blank';a.rel='noopener noreferrer';links.appendChild(a);
    }
  }
  let config;
  try{config=await GET('/api/config');}catch(error){return;}
  appearance(config);
  for(const [tab,title,hint,fields] of groups){
    const el=panel(tab,title);panels[title]=el;
    if(hint){const p=document.createElement('p');p.className='hint';p.textContent=tr(hint);el.appendChild(p);}
    const columns=document.createElement('div');columns.className='cols';el.appendChild(columns);
    const controls=[];
    for(const [path,label,type,min,max,step] of fields){
      const field=document.createElement('label');field.className=type==='check'?'check':'field';
      const text=document.createElement('span');text.textContent=tr(label);
      let input;
      if(Array.isArray(type)){
        input=document.createElement('select');for(const key of type){const option=document.createElement('option');option.value=key;const localized=tr(key);option.textContent=localized==='v282.'+key?key:localized;input.appendChild(option);}
      }else{input=document.createElement(type==='links'?'textarea':'input');if(type!=='links')input.type=type==='check'?'checkbox':(['number','coordinate'].includes(type)?'number':(type==='password'?'password':'text'));}
      input.id='opt-'+path.replaceAll('.','-');
      if(min!==undefined){input.min=min;input.max=max;input.step=step||1;}
      const value=valueAt(config,path);
      if(type==='check')input.checked=!!value;
      else if(type==='size')input.value=Array.isArray(value)?value.join('x'):'';
      else if(type==='crop'||type==='hosts')input.value=(value||[]).join(',');
      else if(type==='links')input.value=(value||[]).map(v=>v.title+' | '+v.url).join('\n');
      else input.value=value==null?'':value;
      field.appendChild(text);field.appendChild(input);columns.appendChild(field);controls.push({path,type,input});
    }
    const row=document.createElement('div');row.className='row';el.appendChild(row);
    button(row,'save',async()=>{
      const patch={};
      for(const {path,type,input} of controls){
        if(!input.checkValidity()){input.reportValidity();return;}
        let value=input.value.trim();
        if(type==='check')value=input.checked;
        else if(type==='number'||type==='coordinate')value=value===''&&type==='coordinate'?null:Number(value);
        else if(type==='size'){value=value?value.toLowerCase().split(/[x,×]/).map(Number):null;if(value&&(value.length!==2||!value.every(Number.isInteger)))throw new Error(tr('stillsResolution'));}
        else if(type==='crop')value=value.split(',').map(Number);
        else if(type==='hosts')value=value.split(',').map(v=>v.trim()).filter(Boolean);
        else if(type==='links')value=value.split('\n').filter(v=>v.trim()).map(line=>{const split=line.indexOf('|');return{title:line.slice(0,split).trim(),url:line.slice(split+1).trim()};});
        put(patch,path,value);
      }
      const result=await POST('/api/config',patch);config=result.config;CFG=config;appearance(config);toast(tr('saved'),'ok');
    });
  }
  const motion=panels.analysis;
  for(const [label,name] of [['downloadCsv','motion.csv'],['downloadEvents','motion-events.jsonl']]){
    const a=document.createElement('a');a.href=API+'/api/detection/log/'+name;a.textContent=tr(label);a.style.marginRight='16px';motion.appendChild(a);
  }
  const record=panels.recording;
  const nameHint=document.createElement('p');nameHint.className='hint';nameHint.textContent=tr('nameHint');record.appendChild(nameHint);
  const duration=input(record,'seconds','number');duration.min=1;duration.max=3600;duration.value=120;
  const recordingRow=document.createElement('div');recordingRow.className='row';record.appendChild(recordingRow);
  button(recordingRow,'manualStart',()=>POST('/api/manual',{action:'start',seconds:Number(duration.value)}));
  button(recordingRow,'manualStop',()=>POST('/api/manual',{action:'stop'}));
  button(recordingRow,'externalTrigger',()=>POST('/api/motion/trigger',{seconds:2}));
  button(recordingRow,'repairThumbs',async()=>{await POST('/api/maintenance/thumbnails',{});toast(tr('repairStarted'),'ok');});
  const previewRow=$('btn-still').parentElement;
  button(previewRow,'manualStart',()=>POST('/api/manual',{action:'start',seconds:120}));
  button(previewRow,'manualStop',()=>POST('/api/manual',{action:'stop'}));
  const audioPanel=$('btn-audio-save').closest('.panel');
  const trigger=input(audioPanel,'soundTrigger','checkbox');trigger.checked=!!config.record.audio_trigger_enabled;
  const level=input(audioPanel,'soundLevel','number');level.min=.001;level.max=1;level.step=.01;level.value=config.record.audio_trigger_level;
  const hold=input(audioPanel,'soundDuration','number');hold.min=0;hold.max=10;hold.step=.1;hold.value=config.record.audio_trigger_seconds;
  button(audioPanel,'save',async()=>{await POST('/api/audio',{trigger_enabled:trigger.checked,trigger_level:Number(level.value),trigger_seconds:Number(hold.value)});toast(tr('saved'),'ok');});
  const audioRow=document.createElement('div');audioRow.className='row';audioPanel.appendChild(audioRow);
  const audioDuration=input(audioPanel,'seconds','number');audioDuration.min=1;audioDuration.max=3600;audioDuration.value=120;
  const audioFiles=document.createElement('div');audioFiles.className='rlist';audioFiles.setAttribute('aria-label',tr('audioFiles'));audioPanel.appendChild(audioFiles);
  async function refreshAudioFiles(){const files=await GET('/api/audio/files');audioFiles.replaceChildren();for(const file of files){const a=document.createElement('a');a.href=MEDIA('audio',file.name);a.textContent=file.name+' · '+bytes(file.size);a.target='_blank';a.rel='noopener';a.className='rrow';audioFiles.appendChild(a);}}
  button(audioRow,'audioRecord',()=>POST('/api/audio/record',{action:'start',seconds:Number(audioDuration.value)}));
  button(audioRow,'audioStop',async()=>{await POST('/api/audio/record',{action:'stop'});await refreshAudioFiles();});
  button(audioRow,'browse',refreshAudioFiles);
  const archive=panels.archive;
  const day=input(archive,'date','date');day.value=new Date().toLocaleDateString('en-CA');
  const archiveList=document.createElement('div');archiveList.className='rlist';archive.appendChild(archiveList);
  button(archive,'browse',async()=>{
    const files=await GET('/api/archive/calendar?date='+encodeURIComponent(day.value));archiveList.replaceChildren();
    if(!files.length){archiveList.textContent=tr('empty');return;}
    for(const file of files){const a=document.createElement('a');a.className='rrow';a.textContent=file.id+' · '+bytes(file.size);a.href=API+'/api/archive/file/'+encodeURIComponent(file.archive_day)+'/videos/'+encodeURIComponent(file.video);a.target='_blank';a.rel='noopener';archiveList.appendChild(a);}
  });
  const solar=panels.location;
  const solarTable=document.createElement('p');solarTable.className='hint';solar.appendChild(solarTable);
  button(solar,'solarRefresh',async()=>{const result=await GET('/api/solar');solarTable.textContent=Object.entries(result.times).map(([key,value])=>tr(key)+': '+(value?new Date(value).toLocaleTimeString():'—')).join(' · ');});
  // The existing schedule editor accepts fixed times and solar expressions.
  $('sc-time').type='text';$('sc-time').placeholder='08:00 / sunrise / sunset-30';
  const servo=panels.servoOptions;const servoRow=document.createElement('div');servoRow.className='row';servo.appendChild(servoRow);
  const binding=input($('pos-name').parentElement,'source');binding.id='pos-preset';
  binding.setAttribute('list','position-preset-names');
  const presetNames=document.createElement('datalist');presetNames.id='position-preset-names';
  for(const name of Object.keys(config.presets||{})){const option=document.createElement('option');option.value=name;presetNames.appendChild(option);}
  binding.parentElement.appendChild(presetNames);
  button(servoRow,'scanStart',()=>POST('/api/servo/scan',{enabled:true}));button(servoRow,'scanStop',()=>POST('/api/servo/scan',{enabled:false}));
  for(const [direction,axis,sign] of [['left','pan',-1],['right','pan',1],['up','tilt',1],['down','tilt',-1]])button(servoRow,direction,()=>POST('/api/servo/step',{axis,direction:sign}));
  const transfer=panel('system','presetTransfer');
  const source=input(transfer,'source');const target=input(transfer,'target');const section=input(transfer,'section');
  for(const move of [false,true])button(transfer,move?'move':'copy',async()=>{await POST('/api/presets/transfer',{source:source.value,target:target.value,section:section.value||null,move});await loadPresets();toast(tr('saved'),'ok');});
  const camera=panel('system','cameraProfile');
  const exportLink=document.createElement('a');exportLink.href=API+'/api/camera/profile';exportLink.textContent=tr('exportCamera');camera.appendChild(exportLink);
  const file=input(camera,'importCamera','file');file.accept='application/json,.json';
  file.addEventListener('change',()=>action(async()=>{if(!file.files.length)return;const data=JSON.parse(await file.files[0].text());await POST('/api/camera/profile',data);toast(tr('saved'),'ok');await loadConfig();}));
  const hookParent=$('hk-on_timelapse_end').parentElement.parentElement;
  for(const key of ['on_startup','on_motion_enable','on_loop_end','on_manual_end','on_still_capture','on_multicast_pkc_message']){const el=input(hookParent,key);el.id='hk-'+key;}
  loadHooks();
  const quickActions=panel('preview','menu');
  const message=input(quickActions,'inform');
  button(quickActions,'inform',()=>POST('/api/command',{command:'inform '+JSON.stringify(message.value)}));
  const menuRow=document.createElement('div');menuRow.className='row';quickActions.appendChild(menuRow);
  const menuText=document.createElement('span');menuText.className='hint';menuRow.appendChild(menuText);
  for(const [label,key] of [['left','<'],['right','>'],['menu','sel'],['none','back']])button(menuRow,label,()=>POST('/api/command',{command:'display '+key}));
  const notify=document.createElement('div');notify.id='preview-notice';notify.className='preview-notice hidden';notify.setAttribute('role','status');$('page-preview').prepend(notify);
  const vectorLayer=document.createElementNS('http://www.w3.org/2000/svg','svg');vectorLayer.setAttribute('viewBox','0 0 1000 1000');vectorLayer.setAttribute('preserveAspectRatio','none');vectorLayer.classList.add('motion-vector-layer');$('regions').parentElement.appendChild(vectorLayer);
  function updateExtras(){
    if(!ST)return;
    const info=ST.inform||{};const text=ST.preview_stalled?tr('previewStalled'):(info.until>Date.now()/1000?info.text:'');
    const menu=ST.menu||{};menuText.textContent=menu.visible?[t('btn.enableDetect'),t('btn.resumeRecord'),t('btn.snapshot')][menu.index||0]:'';
    notify.textContent=text;notify.classList.toggle('hidden',!text);
    const vectors=(ST.detection&&ST.detection.analysis&&ST.detection.analysis.vectors)||[];
    vectorLayer.replaceChildren();
    if(!config.motion.analysis.enabled||!config.motion.analysis.vectors)return;
    for(const v of vectors){if(![v.x,v.y,v.dx,v.dy].every(Number.isFinite))continue;const line=document.createElementNS(vectorLayer.namespaceURI,'path');const x=v.x*1000,y=v.y*1000,dx=v.dx*3000,dy=v.dy*3000;const angle=Math.atan2(dy,dx);const endX=x+dx,endY=y+dy;line.setAttribute('d',`M${x},${y}L${endX},${endY}M${endX-10*Math.cos(angle-.5)},${endY-10*Math.sin(angle-.5)}L${endX},${endY}L${endX-10*Math.cos(angle+.5)},${endY-10*Math.sin(angle+.5)}`);line.setAttribute('stroke','#6dffb3');line.setAttribute('stroke-width','3');line.setAttribute('fill','none');vectorLayer.appendChild(line);}
  }
  PKCPolling.createPoller(async()=>updateExtras(),1000,()=>!document.hidden).start();
})();
