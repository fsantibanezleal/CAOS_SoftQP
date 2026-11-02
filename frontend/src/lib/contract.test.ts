// Deployment wrapper and actual scientific results, on both producer and fixture roots.
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import Ajv from 'ajv/dist/2020.js';
import indexSchema from '../../../docs/contracts/schemas/case-index.schema.json';
import manifestSchema from '../../../docs/contracts/schemas/case-manifest.schema.json';
import readinessSchema from '../../../docs/contracts/schemas/readiness.schema.json';
import { validateSoftQPResult } from './softqp';
import { conform,UNAVAILABLE } from './contract.types';
const ajv=new Ajv({strict:true,allErrors:true});
const indexValid=ajv.compile(indexSchema),manifestValid=ajv.compile(manifestSchema),readyValid=ajv.compile(readinessSchema);
for(const relative of ['../../../data/derived/','../../../docs/contracts/fixtures/data/derived/']){
  const root=new URL(relative,import.meta.url);
  const read=(path:string)=>JSON.parse(readFileSync(new URL(path,root),'utf8'));
  describe(`scientific deployment contract ${relative}`,()=>{
    it('validates the index, manifest, result and byte inventory',()=>{
      const index=read('manifests/index.json');expect(indexValid(index),ajv.errorsText(indexValid.errors)).toBe(true);
      expect(index.n_cases).toBe(index.cases.length);expect(index.cases.map((c:any)=>c.case_id)).toContain(index.default_case);
      for(const entry of index.cases){
        const manifest=read(entry.manifest_path);expect(manifestValid(manifest),ajv.errorsText(manifestValid.errors)).toBe(true);
        expect(manifest.case_id).toBe(entry.case_id);expect(manifest.lane).toBe('precompute');
        const result=validateSoftQPResult(read(manifest.artifact.path));expect(result.case_id).toBe(entry.case_id);
        expect(readFileSync(new URL(manifest.artifact.path,root)).length).toBe(manifest.artifact.bytes);
      }
    });
    it('validates readiness and rejects a changed schema identifier',()=>{
      const doc=read('readiness.json');expect(readyValid(doc),ajv.errorsText(readyValid.errors)).toBe(true);
      expect(readyValid({...doc,schema:'invalid'})).toBe(false);
    });
  });
}
it('rejects unavailable API bodies without a reason',()=>{
  expect(conform({detail:{state:'missing',reason:{en:'Missing',es:'Ausente'}}},{object:UNAVAILABLE})).toEqual([]);
  expect(conform({detail:{state:'missing'}},{object:UNAVAILABLE})).not.toEqual([]);
});
