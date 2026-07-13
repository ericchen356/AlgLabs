/**
 * Trainer module public surface (CONTRACTS.md §12.2). App.tsx imports ONLY
 * from here, behind the prop seam defined in ./types.
 */
export { default as SetPicker } from './SetPicker'
export { default as CasePick } from './CasePick'
export { default as Trainer } from './Trainer'
// (RecordsScreen.tsx, not Records.tsx: the records STORE lives at records.ts
// per §12.5 and macOS's case-insensitive filesystem cannot host both names.)
export { default as Records } from './RecordsScreen'
export * from './types'
