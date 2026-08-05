/**
 * Injects CSS variables for the A2UI basic catalog into the document.
 *
 * This method is used by the A2UI-provided basic catalogs of each renderer
 * so design token values can be shared across all of them.
 *
 * It is only meant to be used by the basic catalog implementations provided
 * by `@a2ui/lit`, `@a2ui/angular` and `@a2ui/react`, and should not be
 * considered as part of the A2UI spec. This package is just a convenient
 * location for it.
 *
 * Users may redefine the values of the CSS variables exposed in the default
 * stylesheet above (and the specific ones exposed by each basic catalog
 * package) to customize the appearance of the items of the basic catalog.
 */
export declare function injectBasicCatalogStyles(): void;
/**
 * Options for computing light and dark color variants.
 */
export interface ColorVariantLightDarkOptions {
    /** The CSS variable name of the base color (e.g., '--a2ui-color-primary'). */
    colorVar: string;
    /** The percentage of the base color to retain in the mix (default 85). */
    percentage?: number;
    /** The color to mix with (default 'white' for light, 'black' for dark). */
    mixColor?: string;
}
/**
 * Options for computing hover color variants using light-dark().
 */
export interface ColorVariantHoverOptions {
    /** The CSS variable name of the dark variant. */
    darkVar: string;
    /** The CSS variable name of the light variant. */
    lightVar: string;
}
/**
 * Computes the formula for light or dark variants of a color.
 * @param type The type of variant to compute ('light' or 'dark').
 * @param options Options containing the base color variable and optional percentage.
 * @returns The CSS formula string.
 */
export declare function computeColorVariant(type: 'light' | 'dark', options: ColorVariantLightDarkOptions): string;
/**
 * Computes the formula for hover variants of a color.
 * @param type The type of variant to compute ('hover').
 * @param options Options containing the dark and light variant variable names.
 * @returns The CSS formula string.
 */
export declare function computeColorVariant(type: 'hover', options: ColorVariantHoverOptions): string;
//# sourceMappingURL=default.d.ts.map