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
import { signal as preactSignal, computed as preactComputed, effect as preactEffect, batch as preactBatch, Computed as PreactComputed, } from '@preact/signals-core';
let signalImpl;
let computedImpl;
let effectImpl;
let batchWriteImpl;
let isSignalImpl;
let getValueImpl;
let setValueImpl;
let peekValueImpl;
/** Default signal implementations. Exported only for testing purposes. */
export const _PRIVATE_DEFAULT_SIGNAL_IMPLEMENTATION = {
    signal: preactSignal,
    computed: preactComputed,
    effect: preactEffect,
    batchWrite: preactBatch,
    isSignal: (val) => !!val && typeof val === 'object' && 'value' in val && 'peek' in val,
    getValue: (signal) => signal.value,
    setValue: (signal, value) => {
        if (!(signal instanceof PreactComputed)) {
            signal.value = value;
        }
    },
    peekValue: (signal) => signal.peek(),
};
setSignalImplementation(_PRIVATE_DEFAULT_SIGNAL_IMPLEMENTATION);
/**
 * Sets the implementations of the various signal-related functions.
 * This allows for signal libraries to be swapped out.
 */
export function setSignalImplementation(impl) {
    // Intentionally only store the functions so we ignore any mutations of the implementation.
    signalImpl = impl.signal;
    computedImpl = impl.computed;
    effectImpl = impl.effect;
    batchWriteImpl = impl.batchWrite;
    isSignalImpl = impl.isSignal;
    getValueImpl = impl.getValue;
    setValueImpl = impl.setValue;
    peekValueImpl = impl.peekValue;
}
export function signal(initialValue) {
    return signalImpl(initialValue);
}
export function computed(computeFn) {
    return computedImpl(computeFn);
}
export function effect(effectFn) {
    return effectImpl(effectFn);
}
export function batchWrite(batchFn) {
    return batchWriteImpl(batchFn);
}
export function isSignal(val) {
    return isSignalImpl(val);
}
export function getValue(signal) {
    return getValueImpl(signal);
}
export function setValue(signal, value) {
    setValueImpl(signal, value);
}
export function peekValue(signal) {
    return peekValueImpl(signal);
}
//# sourceMappingURL=signals.js.map