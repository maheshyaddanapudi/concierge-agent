import * as Types from '@a2ui/web_core';
/**
 * A pre-configured instance of markdown-it to render markdown in A2UI web.
 *
 * This renderer does not perform any sanitization of the outgoing HTML.
 */
export declare class MarkdownItRenderer {
    private markdownIt;
    constructor();
    /**
     * Registers rules to apply tag class maps from the environment.
     */
    private registerTagClassMapRules;
    /**
     * Renders the markdown string to HTML using the internal MarkdownIt instance.
     *
     * @param tagClassMap A map of tag names to classes to apply when rendering a tag.
     *
     * This method does not perform any sanitization of the outgoing HTML.
     */
    render(value: string, tagClassMap?: Types.MarkdownRendererTagClassMap): string;
}
/**
 * A pre-configured instance of markdown-it to render markdown in A2UI web.
 *
 * This renderer does not perform any sanitization of the outgoing HTML.
 */
export declare const rawMarkdownRenderer: MarkdownItRenderer;
//# sourceMappingURL=raw-markdown.d.ts.map