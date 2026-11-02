import Ajv2020 from 'ajv/dist/2020.js';
import { useEffect, useState } from 'react';
import indexSchema from '../../../docs/contracts/schemas/softqp-experiment-index.schema.json';
import campaignSchema from '../../../docs/contracts/schemas/softqp-campaign.schema.json';
import streamSchema from '../../../docs/contracts/schemas/softqp-stream.schema.json';
import type { components } from './contract.gen';
import { softQPSource, type SoftQPSource } from './softqp';

export type ExperimentIndex = components['schemas']['SoftQPExperimentIndex'];
export type Campaign = components['schemas']['SoftQPCampaign'];
export type Stream = components['schemas']['SoftQPStream'];
const ajv = new Ajv2020({ strict: true, allErrors: true });
const validators = { index: ajv.compile(indexSchema), campaign: ajv.compile(campaignSchema), stream: ajv.compile(streamSchema) };
export function validateExperiment<T extends 'index'|'campaign'|'stream'>(kind:T,value:unknown): T extends 'index'?ExperimentIndex:T extends 'campaign'?Campaign:Stream {
  if (!validators[kind](value)) throw new Error(`Invalid ${kind}: ${ajv.errorsText(validators[kind].errors)}`);
  return value as T extends 'index'?ExperimentIndex:T extends 'campaign'?Campaign:Stream;
}
const canonical=import.meta.glob<string>('../../../data/derived/experiments/*.json',{query:'?raw',import:'default'});
const fixtures=import.meta.glob<string>('../../../docs/contracts/fixtures/data/derived/experiments/*.json',{query:'?raw',import:'default'});
async function rawDocument(path:string,source:SoftQPSource,signal?:AbortSignal){
  signal?.throwIfAborted();
  const prefix=source==='fixture'?'../../../docs/contracts/fixtures/data/derived/experiments/':'../../../data/derived/experiments/';
  const load=(source==='fixture'?fixtures:canonical)[prefix+path];
  if(!load)throw new Error(`${path}: experiment evidence unavailable`);
  const raw=await load();signal?.throwIfAborted();return raw;
}
export async function loadExperimentIndex(source:SoftQPSource=softQPSource,signal?:AbortSignal){
  return validateExperiment('index',JSON.parse(await rawDocument('index.json',source,signal)));
}
export async function loadExperimentArtifact<T extends 'campaign'|'stream'>(kind:T,entry:ExperimentIndex['artifacts'][number],source:SoftQPSource=softQPSource,signal?:AbortSignal){
  const raw=await rawDocument(entry.path,source,signal);
  const bytes=new TextEncoder().encode(raw);
  const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
  signal?.throwIfAborted();
  if(digest!==entry.sha256||bytes.length!==entry.bytes)throw new Error(`${entry.path}: SHA-256 or byte-length mismatch`);
  if(entry.schema!==`softqp-${kind}`)throw new Error(`${entry.path}: experimental schema identity mismatch`);
  return validateExperiment(kind,JSON.parse(raw));
}
export function useExperiments(){
  const [evidence,setEvidence]=useState<{index:ExperimentIndex;campaign:Campaign;stream:Stream}|null>(null);
  const [error,setError]=useState<string|null>(null);
  useEffect(()=>{
    const abort=new AbortController();
    loadExperimentIndex(softQPSource,abort.signal).then(async index=>{
      const campaignEntry=index.artifacts.find(e=>e.schema==='softqp-campaign');
      const streamEntry=index.artifacts.find(e=>e.schema==='softqp-stream');
      if(!campaignEntry||!streamEntry)throw new Error('Experiment inventory is incomplete');
      const [campaign,stream]=await Promise.all([
        loadExperimentArtifact('campaign',campaignEntry,softQPSource,abort.signal),
        loadExperimentArtifact('stream',streamEntry,softQPSource,abort.signal),
      ]);
      if(campaign.protocol.protocol_id!==index.protocol_id||stream.protocol_id!==index.protocol_id)throw new Error('Experimental protocol identity mismatch');
      if(!abort.signal.aborted)setEvidence({index,campaign,stream});
    }).catch(e=>{if(!abort.signal.aborted)setError(String(e));});
    return()=>abort.abort();
  },[]);
  return {evidence,error,source:softQPSource};
}
