import Ajv2020 from 'ajv/dist/2020.js';
import indexSchema from '../../../docs/contracts/schemas/softqp-index.schema.json';
import resultSchema from '../../../docs/contracts/schemas/softqp-case-result.schema.json';
import problemSchema from '../../../docs/contracts/schemas/softqp-case-spec.schema.json';
import requestSchema from '../../../docs/contracts/schemas/softqp-run-request.schema.json';
import localSchema from '../../../docs/contracts/schemas/softqp-local-export.schema.json';
import type { components } from './contract.gen';
import indexDocument from '../../../data/derived/softqp/index.json';
import fixtureIndex from '../../../docs/contracts/fixtures/data/derived/softqp/index.json';

export type SoftQPIndex = components['schemas']['SoftQPIndex'];
export type SoftQPResult = components['schemas']['SoftQPCaseResult'];
export type SoftQPRun = SoftQPResult['runs'][number];
export type SoftQPProblem = components['schemas']['SoftQPCaseSpec'];
export type SoftQPRequest = components['schemas']['SoftQPRunRequest'];
export type SoftQPLocalExport = components['schemas']['SoftQPLocalExport'];

const ajv = new Ajv2020({ allErrors: true, strict: true });
ajv.addSchema(problemSchema);
ajv.addSchema(requestSchema);
ajv.addSchema(resultSchema);
const indexValidator = ajv.compile(indexSchema);
const resultValidator = ajv.compile(resultSchema);
const requestValidator = ajv.compile(requestSchema);
const localValidator = ajv.compile(localSchema);
export function validateSoftQPRequest(value: unknown): SoftQPRequest {
  if (!requestValidator(value)) throw new Error(`Invalid local request: ${ajv.errorsText(requestValidator.errors)}`);
  return value as SoftQPRequest;
}
export function validateSoftQPLocalExport(value: unknown): SoftQPLocalExport {
  if (!localValidator(value)) throw new Error(`Invalid local result: ${ajv.errorsText(localValidator.errors)}`);
  return value as SoftQPLocalExport;
}
export function validateSoftQPIndex(value: unknown): SoftQPIndex {
  if (!indexValidator(value)) throw new Error(`Invalid SoftQP index: ${ajv.errorsText(indexValidator.errors)}`);
  return value as SoftQPIndex;
}
export function validateSoftQPResult(value: unknown): SoftQPResult {
  if (!resultValidator(value)) throw new Error(`Invalid SoftQP result: ${ajv.errorsText(resultValidator.errors)}`);
  return value as SoftQPResult;
}
const documents = import.meta.glob<string>('../../../data/derived/softqp/C*.json', { query: '?raw', import: 'default' });
const fixtures = import.meta.glob<string>('../../../docs/contracts/fixtures/data/derived/softqp/C*.json', { query: '?raw', import: 'default' });
export type SoftQPSource = 'canonical' | 'fixture';
export const softQPSource: SoftQPSource = import.meta.env.VITE_SOFTQP_SOURCE === 'fixture' ? 'fixture' : 'canonical';
export async function loadSoftQPIndex(signal?: AbortSignal, source: SoftQPSource = softQPSource): Promise<SoftQPIndex> {
  signal?.throwIfAborted();
  return validateSoftQPIndex(source === 'fixture' ? fixtureIndex : indexDocument);
}
export async function loadSoftQPCase(entry: SoftQPIndex['cases'][number], signal?: AbortSignal, source: SoftQPSource = softQPSource): Promise<SoftQPResult> {
  signal?.throwIfAborted();
  const root = source === 'fixture' ? '../../../docs/contracts/fixtures/data/derived/softqp/' : '../../../data/derived/softqp/';
  const load = (source === 'fixture' ? fixtures : documents)[`${root}${entry.path}`];
  if (!load) throw new Error(`${entry.path}: artifact unavailable`);
  const raw = await load();
  signal?.throwIfAborted();
  const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(raw))), b => b.toString(16).padStart(2, '0')).join('');
  if (digest !== entry.sha256) throw new Error(`${entry.path}: SHA-256 mismatch`);
  const doc = validateSoftQPResult(JSON.parse(raw));
  if (doc.case_id !== entry.case_id) throw new Error(`${entry.path}: case ID mismatch`);
  return doc;
}
