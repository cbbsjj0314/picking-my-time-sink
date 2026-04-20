declare module 'react' {
  export type ReactNode = any
  export type SetStateAction<S> = S | ((prevState: S) => S)
  export type Dispatch<A> = (value: A) => void

  export const StrictMode: any

  export function useState<S>(initialState: S): [S, Dispatch<SetStateAction<S>>]
  export function useEffect(effect: () => void | (() => void), deps?: readonly unknown[]): void
  export function useDeferredValue<T>(value: T): T
  export function useMemo<T>(factory: () => T, deps: readonly unknown[]): T
  export function startTransition(scope: () => void): void
}

declare module 'react-dom/client' {
  export function createRoot(container: Element | DocumentFragment): {
    render(node: any): void
  }
}

declare module 'react/jsx-runtime' {
  export const Fragment: any
  export function jsx(type: any, props: any, key?: any): any
  export function jsxs(type: any, props: any, key?: any): any
}

declare namespace JSX {
  interface IntrinsicElements {
    [elementName: string]: any
  }
}
