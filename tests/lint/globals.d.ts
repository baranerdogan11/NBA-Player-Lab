// What the type check assumes beyond the browser's own types.
//
// The page treats the DOM loosely, the way plain browser JavaScript does: $('#x').hidden, e.target.closest(...). TypeScript
// would flag every one of those (a querySelector result is an Element, not an HTMLElement), which is noise rather than
// bugs, so these widen the DOM types the page uses. Everything else is checked as written.
interface Element extends ElementCSSInlineStyle, HTMLOrSVGElement {
  hidden: boolean; disabled: boolean; value: any; href: string; offsetLeft: number; checked: boolean; title: string; innerText: string;
  setAttribute(qualifiedName: string, value: string | number | boolean): void;   // the browser turns the value into text
}
interface EventTarget { closest(selectors: string): any; value?: any; dataset?: DOMStringMap; }
