import { describe, it, expect } from 'vitest';
import { loadExperimentIndex, loadExperimentArtifact, validateExperiment } from './experiments';

describe('Measured experimental producer / reader boundary',()=>{
  for(const source of ['canonical','fixture'] as const){
    it(`reads checksummed campaign and stream from ${source}`,async()=>{
      const index=await loadExperimentIndex(source);
      const campaign=await loadExperimentArtifact('campaign',index.artifacts.find(e=>e.schema==='softqp-campaign')!,source);
      const stream=await loadExperimentArtifact('stream',index.artifacts.find(e=>e.schema==='softqp-stream')!,source);
      expect(campaign.completed_instances).toBe(campaign.planned_instances);
      expect(stream.frames).toHaveLength(32);
      expect(stream.counts.accepted).toBe(192);
    });
  }
  it('adversarial: rejects corrupt bytes, a missing frame and false timing',async()=>{
    const index=await loadExperimentIndex();const entry=index.artifacts.find(e=>e.schema==='softqp-stream')!;
    await expect(loadExperimentArtifact('stream',{...entry,sha256:'0'.repeat(64)})).rejects.toThrow('SHA-256');
    const stream=await loadExperimentArtifact('stream',entry);
    expect(()=>validateExperiment('stream',{...stream,frames:stream.frames.slice(1)})).toThrow();
    stream.frames[0].runs[0].elapsed_seconds=true as unknown as number;
    expect(()=>validateExperiment('stream',stream)).toThrow();
    const abort=new AbortController();abort.abort();
    await expect(loadExperimentIndex('canonical',abort.signal)).rejects.toThrow();
  });
});
