/**
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
export interface Signal<T = unknown> {
    __signalBrand?: T;
    unsubscribe?: () => void;
}
export interface SignalImplementations {
    signal: <T>(initialValue: T) => Signal<T>;
    computed: <T>(computeFn: () => T) => Signal<T>;
    effect: (effectFn: () => void | (() => void)) => () => void;
    batchWrite: (batchFn: () => void) => void;
    isSignal: (val: unknown) => val is Signal<unknown>;
    getValue: <T>(signal: Signal<T>) => T;
    setValue: <T>(signal: Signal<T>, value: T) => void;
    peekValue: <T>(signal: Signal<T>) => T;
}
/** Default signal implementations. Exported only for testing purposes. */
export declare const _PRIVATE_DEFAULT_SIGNAL_IMPLEMENTATION: SignalImplementations;
/**
 * Sets the implementations of the various signal-related functions.
 * This allows for signal libraries to be swapped out.
 */
export declare function setSignalImplementation(impl: SignalImplementations): void;
export declare function signal<T>(initialValue: T): Signal<T>;
export declare function computed<T>(computeFn: () => T): Signal<T>;
export declare function effect(effectFn: () => void | (() => void)): () => void;
export declare function batchWrite(batchFn: () => void): void;
export declare function isSignal(val: unknown): val is Signal<unknown>;
export declare function getValue<T>(signal: Signal<T>): T;
export declare function setValue<T>(signal: Signal<T>, value: T): void;
export declare function peekValue<T>(signal: Signal<T>): T;
//# sourceMappingURL=signals.d.ts.map