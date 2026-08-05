'use strict';

var Styles = require('@a2ui/web_core/styles/index');

function _interopNamespace(e) {
  if (e && e.__esModule) return e;
  var n = Object.create(null);
  if (e) {
    Object.keys(e).forEach(function (k) {
      if (k !== 'default') {
        var d = Object.getOwnPropertyDescriptor(e, k);
        Object.defineProperty(n, k, d.get ? d : {
          enumerable: true,
          get: function () { return e[k]; }
        });
      }
    });
  }
  n.default = e;
  return Object.freeze(n);
}

var Styles__namespace = /*#__PURE__*/_interopNamespace(Styles);

// src/v0_8/styles/index.ts

// src/v0_8/styles/reset.ts
var resetStyles = `
@layer a2ui-reset {
  :where(.a2ui-surface) :where(*:not(svg, svg *:not(foreignObject *))) {
    all: revert;
  }
}
`;

// src/v0_8/styles/index.ts
var structuralStyles2 = Styles__namespace.structuralStyles.replace(
  /:host\s*\{/g,
  ".a2ui-surface {"
);
var componentSpecificStyles = `
.a2ui-surface .a2ui-card {
  display: block;
  flex: var(--weight);
  min-height: 0;
  overflow: auto;
}
.a2ui-surface .a2ui-card > section {
  height: 100%;
  width: 100%;
  min-height: 0;
  overflow: auto;
}
.a2ui-surface .a2ui-card > section > * {
  height: 100%;
  width: 100%;
}

.a2ui-surface .a2ui-divider {
  display: block;
  min-height: 0;
  overflow: auto;
}
:where(.a2ui-surface .a2ui-divider) hr {
  height: 1px;
  background: #ccc;
  border: none;
}

.a2ui-surface .a2ui-text {
  display: block;
  flex: var(--weight);
}
:where(.a2ui-surface .a2ui-text) h1,
:where(.a2ui-surface .a2ui-text) h2,
:where(.a2ui-surface .a2ui-text) h3,
:where(.a2ui-surface .a2ui-text) h4,
:where(.a2ui-surface .a2ui-text) h5 {
  line-height: inherit;
  font: inherit;
}
.a2ui-surface .a2ui-text p {
  margin: 0;
}

.a2ui-surface .a2ui-textfield {
  display: flex;
  flex: var(--weight);
}
:where(.a2ui-surface .a2ui-textfield) input {
  display: block;
  width: 100%;
}
:where(.a2ui-surface .a2ui-textfield) label {
  display: block;
  margin-bottom: 4px;
}
:where(.a2ui-surface .a2ui-textfield) textarea {
  display: block;
  width: 100%;
}

.a2ui-surface .a2ui-checkbox {
  display: block;
  flex: var(--weight);
  min-height: 0;
  overflow: auto;
}
:where(.a2ui-surface .a2ui-checkbox) input {
  display: block;
  width: 100%;
}

.a2ui-surface .a2ui-slider {
  display: block;
  flex: var(--weight);
}
:where(.a2ui-surface .a2ui-slider) input {
  display: block;
  width: 100%;
}

.a2ui-surface .a2ui-button {
  display: block;
  flex: var(--weight);
  min-height: 0;
}

.a2ui-surface .a2ui-icon {
  display: block;
  flex: var(--weight);
  min-height: 0;
  overflow: auto;
}
:where(.a2ui-surface .a2ui-icon) .g-icon {
  font-size: 24px;
}

.a2ui-surface .a2ui-tabs {
  display: block;
  flex: var(--weight);
}

.a2ui-surface .a2ui-modal {
  display: block;
  flex: var(--weight);
}
:where(.a2ui-surface .a2ui-modal) dialog {
  padding: 0;
  border: none;
  background: none;
}
.a2ui-surface .a2ui-modal dialog section #controls {
  display: flex;
  justify-content: end;
  margin-bottom: 4px;
}
.a2ui-surface .a2ui-modal dialog section #controls button {
  padding: 0;
  background: none;
  width: 20px;
  height: 20px;
  cursor: pointer;
  border: none;
}

.a2ui-surface .a2ui-image {
  display: block;
  flex: var(--weight);
  min-height: 0;
  overflow: auto;
}
:where(.a2ui-surface .a2ui-image) img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: var(--object-fit, fill);
}

.a2ui-surface .a2ui-video {
  display: block;
  flex: var(--weight);
  min-height: 0;
  overflow: auto;
}
:where(.a2ui-surface .a2ui-video) video {
  display: block;
  width: 100%;
}

.a2ui-surface .a2ui-audio {
  display: block;
  flex: var(--weight);
  min-height: 0;
  overflow: auto;
}
:where(.a2ui-surface .a2ui-audio) audio {
  display: block;
  width: 100%;
}

.a2ui-surface .a2ui-multiplechoice {
  display: block;
  flex: var(--weight);
  min-height: 0;
  overflow: auto;
}
:where(.a2ui-surface .a2ui-multiplechoice) select {
  width: 100%;
}

.a2ui-surface .a2ui-column {
  display: flex;
  flex: var(--weight);
}
.a2ui-surface .a2ui-column > section {
  display: flex;
  flex-direction: column;
  min-width: 100%;
  height: 100%;
}
.a2ui-surface .a2ui-column[data-alignment="start"] > section { align-items: start; }
.a2ui-surface .a2ui-column[data-alignment="center"] > section { align-items: center; }
.a2ui-surface .a2ui-column[data-alignment="end"] > section { align-items: end; }
.a2ui-surface .a2ui-column[data-alignment="stretch"] > section { align-items: stretch; }
.a2ui-surface .a2ui-column[data-distribution="start"] > section { justify-content: start; }
.a2ui-surface .a2ui-column[data-distribution="center"] > section { justify-content: center; }
.a2ui-surface .a2ui-column[data-distribution="end"] > section { justify-content: end; }
.a2ui-surface .a2ui-column[data-distribution="spaceBetween"] > section { justify-content: space-between; }
.a2ui-surface .a2ui-column[data-distribution="spaceAround"] > section { justify-content: space-around; }
.a2ui-surface .a2ui-column[data-distribution="spaceEvenly"] > section { justify-content: space-evenly; }

.a2ui-surface .a2ui-row {
  display: flex;
  flex: var(--weight);
}
.a2ui-surface .a2ui-row > section {
  display: flex;
  flex-direction: row;
  width: 100%;
  min-height: 100%;
}
.a2ui-surface .a2ui-row[data-alignment="start"] > section { align-items: start; }
.a2ui-surface .a2ui-row[data-alignment="center"] > section { align-items: center; }
.a2ui-surface .a2ui-row[data-alignment="end"] > section { align-items: end; }
.a2ui-surface .a2ui-row[data-alignment="stretch"] > section { align-items: stretch; }
.a2ui-surface .a2ui-row[data-distribution="start"] > section { justify-content: start; }
.a2ui-surface .a2ui-row[data-distribution="center"] > section { justify-content: center; }
.a2ui-surface .a2ui-row[data-distribution="end"] > section { justify-content: end; }
.a2ui-surface .a2ui-row[data-distribution="spaceBetween"] > section { justify-content: space-between; }
.a2ui-surface .a2ui-row[data-distribution="spaceAround"] > section { justify-content: space-around; }
.a2ui-surface .a2ui-row[data-distribution="spaceEvenly"] > section { justify-content: space-evenly; }

.a2ui-surface .a2ui-list {
  display: block;
  flex: var(--weight);
  min-height: 0;
  overflow: auto;
}
.a2ui-surface .a2ui-list[data-direction="vertical"] > section {
  display: grid;
}
.a2ui-surface .a2ui-list[data-direction="horizontal"] > section {
  display: flex;
  max-width: 100%;
  overflow-x: scroll;
  overflow-y: hidden;
  scrollbar-width: none;
}
.a2ui-surface .a2ui-list[data-direction="horizontal"] > section > * {
  flex: 1 0 fit-content;
  max-width: min(80%, 400px);
}

.a2ui-surface .a2ui-datetime-input {
  display: block;
  flex: var(--weight);
  min-height: 0;
  overflow: auto;
}
:where(.a2ui-surface .a2ui-datetime-input) input {
  display: block;
  border-radius: 8px;
  padding: 8px;
  border: 1px solid #ccc;
  width: 100%;
  color: #333;
}
:where(.a2ui-surface .a2ui-datetime-input) input::-webkit-datetime-edit,
:where(.a2ui-surface .a2ui-datetime-input) input::-webkit-datetime-edit-fields-wrapper {
  color: #333;
}

.a2ui-surface *,
.a2ui-surface *::before,
.a2ui-surface *::after {
  box-sizing: border-box;
}
`;
function injectStyles() {
  if (typeof document === "undefined") {
    return;
  }
  const styleId = "a2ui-structural-styles";
  if (document.getElementById(styleId)) {
    return;
  }
  const styleElement = document.createElement("style");
  styleElement.id = styleId;
  styleElement.textContent = resetStyles + "\n" + structuralStyles2 + "\n" + componentSpecificStyles;
  document.head.appendChild(styleElement);
}
function removeStyles() {
  if (typeof document === "undefined") {
    return;
  }
  const styleElement = document.getElementById("a2ui-structural-styles");
  if (styleElement) {
    styleElement.remove();
  }
}

exports.componentSpecificStyles = componentSpecificStyles;
exports.injectStyles = injectStyles;
exports.removeStyles = removeStyles;
exports.structuralStyles = structuralStyles2;
//# sourceMappingURL=index.cjs.map
//# sourceMappingURL=index.cjs.map