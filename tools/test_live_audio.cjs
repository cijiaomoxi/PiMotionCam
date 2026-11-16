'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {PCMPlayer,decodePCM}=require('../static/live_audio.js');
class Context {
  constructor(){this.currentTime=0;this.destination={};this.buffers=[];this.sources=[];Context.instances.push(this);}
  createGain(){return {gain:{value:0},connect(){}};}
  resume(){return Promise.resolve();}
  close(){this.closed=true;return Promise.resolve();}
  createBuffer(channels,frames,rate){const data=Array.from({length:channels},()=>new Float32Array(frames));const buffer={duration:frames/rate,getChannelData:ch=>data[ch]};this.buffers.push(buffer);return buffer;}
  createBufferSource(){const node={connect(){},start(time){this.time=time;},stop(){this.stopped=true;}};this.sources.push(node);return node;}
}
Context.instances=[];
const headers={get:name=>({'X-Audio-Rate':'16000','X-Audio-Channels':'1','X-Audio-Format':'s16le'})[name]};
test('PCM stereo decoding keeps channels, signed samples and endianness',()=>{
  const result=decodePCM(Uint8Array.from([0,128,255,127,0,64,0,192]),2);
  assert.deepEqual(Array.from(result[0]),[-1,.5]);assert.deepEqual(Array.from(result[1]),[32767/32768,-.5]);
});
test('network fragments are joined at complete sample boundaries',()=>{
  const player=new PCMPlayer({AudioContext:Context});player.context=new Context();player.gain=player.context.createGain();player.rate=16000;player.channels=1;player.carry=new Uint8Array();player.nextTime=.06;
  player.consume(Uint8Array.from([0]));assert.equal(player.context.buffers.length,0);
  player.consume(Uint8Array.from([64,0,192]));assert.deepEqual(Array.from(player.context.buffers[0].getChannelData(0)),[.5,-.5]);assert.equal(player.carry.length,0);player.stop();
});
test('slow playback skips backlog and caps the next buffered chunk',()=>{
  const player=new PCMPlayer({AudioContext:Context});player.context=new Context();player.gain=player.context.createGain();player.rate=16000;player.channels=1;player.carry=new Uint8Array();player.nextTime=3;
  const stale={stop(){this.stopped=true;}};player.sources.add(stale);player.consume(new Uint8Array(32000));
  assert.equal(stale.stopped,true);assert.ok(player.context.buffers[0].duration<=.35);assert.ok(player.nextTime<.5);player.stop();
});
test('disabled audio reports a translated state key and closes the audio context',async()=>{
  const states=[];const player=new PCMPlayer({AudioContext:Context,fetch:async()=>({ok:false,status:409}),onState:s=>states.push(s)});
  await player.start('/api/audio/stream');assert.equal(states.at(-1),'disabled');assert.equal(player.active,false);assert.equal(Context.instances.at(-1).closed,true);
});
test('stopping a pending connection cannot start playback later',async()=>{
  let finish;const pending=new Promise(resolve=>finish=resolve);const states=[];
  const player=new PCMPlayer({AudioContext:Context,fetch:()=>pending,onState:s=>states.push(s)});
  const started=player.start('/api/audio/stream');await Promise.resolve();player.stop();
  finish({ok:true,headers,body:{getReader(){throw new Error('reader must not be acquired');}}});await started;
  assert.equal(player.active,false);assert.ok(!states.includes('playing'));
});
