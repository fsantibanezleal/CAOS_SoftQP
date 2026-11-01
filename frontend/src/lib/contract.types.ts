// Generated schema aliases and the generic readiness descriptor.
import type { components } from './contract.gen';
type Schemas = components['schemas'];
export type Text = Schemas['text'];
export type CaseIndex = Schemas['CaseIndex'];
export type CaseManifest = Schemas['CaseManifest'];
export type Trace = Schemas['SoftQPCaseResult'];
export type Readiness = Schemas['Readiness'];
export type ReadinessEntry = Readiness['contracts'][number];
export type ContractState = ReadinessEntry['state'];
export type Provenance = NonNullable<ReadinessEntry['provenance']>;
export type UnavailableBody = Schemas['UnavailableBody'];
export type NotFoundBody = Schemas['NotFoundBody'];
export const SCHEMAS = {readiness:'softqp.readiness/v2',index:'softqp.artifact-index/v1',manifest:'softqp.manifest/v1'} as const;
export const UNAVAILABLE = {detail:{object:{state:'string',reason:'text'}}} satisfies Record<keyof UnavailableBody,Kind>;
export type Kind='string'|'number'|'integer'|'boolean'|'text'|{array:Kind}|{object:Record<string,Kind>}|{map:Kind}|{nullable:Kind};
export const READINESS = {
  schema: 'string',
  product_version: 'string',
  catalog_sha256: 'string',
  contracts: {
    array: {
      object: {
        id: 'string',
        version: 'string',
        status: 'string',
        provenance: { nullable: 'string' },
        state: 'string',
        reason: { nullable: 'text' },
        missing: { array: 'string' },
      } satisfies Record<keyof ReadinessEntry, Kind>,
    },
  },
} satisfies Record<keyof Readiness, Kind>;

/** Every way `value` departs from `kind`, with its path; empty when it conforms. Booleans are not numbers. */
export function conform(value: unknown, kind: Kind, path = '$'): string[] {
  if (kind === 'string') return typeof value === 'string' ? [] : [`${path}: expected a string`];
  if (kind === 'number') return typeof value === 'number' && Number.isFinite(value) ? [] : [`${path}: expected a finite number`];
  if (kind === 'integer') return Number.isInteger(value) ? [] : [`${path}: expected an integer`];
  if (kind === 'boolean') return typeof value === 'boolean' ? [] : [`${path}: expected a boolean`];
  if (kind === 'text') return conform(value, { object: { en: 'string', es: 'string' } }, path);
  if ('nullable' in kind) return value === null ? [] : conform(value, kind.nullable, path);
  if ('array' in kind) {
    if (!Array.isArray(value)) return [`${path}: expected an array`];
    return value.flatMap((v, i) => conform(v, kind.array, `${path}[${i}]`));
  }
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return [`${path}: expected an object`];
  const obj = value as Record<string, unknown>;
  if ('map' in kind) return Object.entries(obj).flatMap(([k, v]) => conform(v, kind.map, `${path}.${k}`));
  const want = Object.keys(kind.object);
  const out = [
    ...want.filter((k) => !(k in obj)).map((k) => `${path}.${k}: declared by the web, not written by the pipeline`),
    ...Object.keys(obj).filter((k) => !want.includes(k)).map((k) => `${path}.${k}: written by the pipeline, not declared by the web`),
  ];
  for (const k of want) if (k in obj) out.push(...conform(obj[k], kind.object[k], `${path}.${k}`));
  return out;
}
