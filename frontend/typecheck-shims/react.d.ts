// Minimal React typings used ONLY for the offline type-check in the build sandbox (no @types/react available).
// Real builds use @types/react from package.json.
declare module "react" {
  export type ReactNode = any;
  export type FC<P = {}> = (props: P & { children?: ReactNode }) => any;
  export type Dispatch<T> = (v: T | ((prev: T) => T)) => void;
  export function useState<T>(init: T | (() => T)): [T, Dispatch<T>];
  export function useState<T = undefined>(): [T | undefined, Dispatch<T | undefined>];
  export function useEffect(fn: () => void | (() => void), deps?: any[]): void;
  export function useLayoutEffect(fn: () => void | (() => void), deps?: any[]): void;
  export function useMemo<T>(fn: () => T, deps: any[]): T;
  export function useCallback<T extends (...a: any[]) => any>(fn: T, deps: any[]): T;
  export function useRef<T>(init: T): { current: T };
  export function useRef<T>(init: T | null): { current: T | null };
  export function useContext<T>(c: Context<T>): T;
  export interface Context<T> { Provider: any }
  export function createContext<T>(v: T): Context<T>;
  export const StrictMode: any;
  export const Fragment: any;
  const React: any;
  export default React;
}
declare module "react/jsx-runtime" { export const jsx: any; export const jsxs: any; export const Fragment: any; }
declare namespace JSX { interface IntrinsicElements { [k: string]: any } type Element = any; interface ElementChildrenAttribute { children: {} } }
declare namespace JSX { interface IntrinsicAttributes { key?: any } }
declare module "*.css";
