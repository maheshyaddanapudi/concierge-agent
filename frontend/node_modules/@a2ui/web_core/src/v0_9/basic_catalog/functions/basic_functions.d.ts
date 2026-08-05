import { FunctionImplementation } from '../../catalog/types.js';
/**
 * Implementation of the addition function.
 * Adds two numbers 'a' and 'b'.
 */
export declare const AddImplementation: FunctionImplementation;
/**
 * Implementation of the subtraction function.
 * Subtracts 'b' from 'a'.
 */
export declare const SubtractImplementation: FunctionImplementation;
/**
 * Implementation of the multiplication function.
 * Multiplies 'a' and 'b'.
 */
export declare const MultiplyImplementation: FunctionImplementation;
/**
 * Implementation of the division function.
 * Divides 'a' by 'b'. Returns NaN if inputs are invalid, and Infinity if dividing by zero.
 */
export declare const DivideImplementation: FunctionImplementation;
/**
 * Implementation of the equality comparison.
 * Checks if 'a' is strictly equal to 'b'.
 */
export declare const EqualsImplementation: FunctionImplementation;
/**
 * Implementation of the inequality comparison.
 * Checks if 'a' is not strictly equal to 'b'.
 */
export declare const NotEqualsImplementation: FunctionImplementation;
/**
 * Implementation of the greater-than comparison.
 * Checks if 'a' is greater than 'b'.
 */
export declare const GreaterThanImplementation: FunctionImplementation;
/**
 * Implementation of the less-than comparison.
 * Checks if 'a' is less than 'b'.
 */
export declare const LessThanImplementation: FunctionImplementation;
/**
 * Implementation of the logical AND function.
 * Returns true if all values in the array are truthy.
 */
export declare const AndImplementation: FunctionImplementation;
/**
 * Implementation of the logical OR function.
 * Returns true if at least one value in the array is truthy.
 */
export declare const OrImplementation: FunctionImplementation;
/**
 * Implementation of the logical NOT function.
 * Returns the negation of the value.
 */
export declare const NotImplementation: FunctionImplementation;
/**
 * Implementation of the string contains function.
 * Checks if 'string' contains 'substring'.
 */
export declare const ContainsImplementation: FunctionImplementation;
/**
 * Implementation of the string starts-with function.
 * Checks if 'string' starts with 'prefix'.
 */
export declare const StartsWithImplementation: FunctionImplementation;
/**
 * Implementation of the string ends-with function.
 * Checks if 'string' ends with 'suffix'.
 */
export declare const EndsWithImplementation: FunctionImplementation;
/**
 * Implementation of the required validation function.
 * Checks if the value is not null, undefined, empty string, or empty array.
 */
export declare const RequiredImplementation: FunctionImplementation;
/**
 * Implementation of the regex validation function.
 * Checks if the value matches the regular expression pattern.
 * Throws A2uiExpressionError if the pattern is invalid.
 */
export declare const RegexImplementation: FunctionImplementation;
/**
 * Implementation of the length validation function.
 * Checks if the length of the string or array is within [min, max] range.
 */
export declare const LengthImplementation: FunctionImplementation;
/**
 * Implementation of the numeric validation function.
 * Checks if the value is a number and within [min, max] range.
 */
export declare const NumericImplementation: FunctionImplementation;
/**
 * Implementation of the email validation function.
 * Uses a simple regex to check if the value looks like an email address.
 * Note: This is a basic check and not fully compliant with all email standards.
 */
export declare const EmailImplementation: FunctionImplementation;
/**
 * Implementation of the string formatting function.
 * Parses a template string and resolves any embedded expressions using the provided context.
 * Returns a computed signal that updates when referenced signals change.
 */
export declare const FormatStringImplementation: FunctionImplementation;
/**
 * Creates the number formatting function implementation.
 */
export declare function createFormatNumberImplementation(locale?: string): FunctionImplementation;
/**
 * Implementation of the number formatting function.
 * Formats a number using Intl.NumberFormat with specified decimals and grouping.
 */
export declare const FormatNumberImplementation: FunctionImplementation;
/**
 * Creates the currency formatting function implementation.
 */
export declare function createFormatCurrencyImplementation(locale?: string): FunctionImplementation;
/**
 * Implementation of the currency formatting function.
 * Formats a number as currency using Intl.NumberFormat.
 * Falls back to toFixed if formatting fails.
 */
export declare const FormatCurrencyImplementation: FunctionImplementation;
/**
 * Implementation of the date formatting function.
 * Formats a date using date-fns or returns ISO string.
 */
export declare const FormatDateImplementation: FunctionImplementation;
/**
 * Creates the pluralization function implementation.
 */
export declare function createPluralizeImplementation(locale?: string): FunctionImplementation;
/**
 * Implementation of the pluralization function.
 * Selects the appropriate plural form based on the value using Intl.PluralRules.
 */
export declare const PluralizeImplementation: FunctionImplementation;
/**
 * Implementation of the open URL action.
 * Opens the specified URL in a new window/tab.
 */
export declare const OpenUrlImplementation: FunctionImplementation;
/**
 * Creates standard function implementations for the Basic Catalog.
 *
 * @param options Configuration options.
 * @param options.locale Optional locale to close-over.
 */
export declare function createBasicCatalogFunctions(options?: {
    locale?: string;
}): FunctionImplementation[];
/**
 * Standard function implementations for the Basic Catalog.
 * These functions cover arithmetic, comparison, logic, string manipulation, validation, and formatting.
 */
export declare const BASIC_FUNCTIONS: FunctionImplementation[];
//# sourceMappingURL=basic_functions.d.ts.map