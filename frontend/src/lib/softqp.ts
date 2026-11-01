import Ajv2020 from 'ajv/dist/2020.js';
import indexSchema from '../../../docs/contracts/schemas/softqp-index.schema.json';
import resultSchema from '../../../docs/contracts/schemas/softqp-case-result.schema.json';
import type { components } from './contract.gen';
import indexDocument from '../../../data/derived/softqp/index.json';

export type SoftQPIndex = components['schemas']['SoftQPIndex'];
export type SoftQPResult = components['schemas']['SoftQPCaseResult'];
export type SoftQPRun = SoftQPResult['runs'][number];

const ajv = new Ajv2020({ allErrors: true, strict: true });
const indexValidator = ajv.compile(indexSchema);
const resultValidator = ajv.compile(resultSchema);
export function validateSoftQPIndex(value: unknown): SoftQPIndex {
  if (!indexValidator(value)) throw new Error(`Invalid SoftQP index: ${ajv.errorsText(indexValidator.errors)}`);
  return value as SoftQPIndex;
}
export function validateSoftQPResult(value: unknown): SoftQPResult {
  if (!resultValidator(value)) throw new Error(`Invalid SoftQP result: ${ajv.errorsText(resultValidator.errors)}`);
  return value as SoftQPResult;
}
const documents = import.meta.glob<string>('../../../data/derived/softqp/C*.json', { query: '?raw', import: 'default' });
export async function loadSoftQPIndex(signal?: AbortSignal): Promise<SoftQPIndex> {
  signal?.throwIfAborted();
  return validateSoftQPIndex(indexDocument);
}
export async function loadSoftQPCase(entry: SoftQPIndex['cases'][number], signal?: AbortSignal): Promise<SoftQPResult> {
  signal?.throwIfAborted();
  const load = documents[`../../../data/derived/softqp/${entry.path}`];
  if (!load) throw new Error(`${entry.path}: artifact unavailable`);
  const raw = await load();
  signal?.throwIfAborted();
  const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(raw))), b => b.toString(16).padStart(2, '0')).join('');
  if (digest !== entry.sha256) throw new Error(`${entry.path}: SHA-256 mismatch`);
  const doc = validateSoftQPResult(JSON.parse(raw));
  if (doc.case_id !== entry.case_id) throw new Error(`${entry.path}: case ID mismatch`);
  return doc;
}
