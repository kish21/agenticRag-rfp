/**
 * Format a monetary value using the ISO 4217 currency code.
 * Falls back to showing the code as a prefix if Intl.NumberFormat doesn't
 * recognise the currency (e.g. a custom code entered by an org admin).
 */
export function formatCurrency(value: number | null | undefined, currency = "GBP"): string {
  if (value == null) return "—";
  try {
    return new Intl.NumberFormat("en-GB", {
      style: "currency",
      currency: currency.toUpperCase(),
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value);
  } catch {
    return `${currency.toUpperCase()} ${value.toLocaleString("en-GB")}`;
  }
}
