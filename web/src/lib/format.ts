const integerFormatter = new Intl.NumberFormat("en-US");
const dateFormatter = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
});
const dateTimeFormatter = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
});
const percentFormatter = new Intl.NumberFormat("en-US", {
  style: "percent",
  maximumFractionDigits: 1,
});

const currencyFormatters = new Map<string, Intl.NumberFormat>();

function getCurrencyFormatter(currencyCode: string): Intl.NumberFormat {
  const cached = currencyFormatters.get(currencyCode);
  if (cached) {
    return cached;
  }

  const formatter = new Intl.NumberFormat("ko-KR", {
    style: "currency",
    currency: currencyCode,
    maximumFractionDigits: 0,
  });
  currencyFormatters.set(currencyCode, formatter);
  return formatter;
}

export function formatInteger(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "Pending";
  }

  return integerFormatter.format(Math.round(value));
}

export function formatCompactInteger(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "Pending";
  }

  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

export function formatSignedInteger(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "No prior delta";
  }

  const prefix = value > 0 ? "+" : "";
  return `${prefix}${integerFormatter.format(value)}`;
}

export function formatSignedPercent(
  value: number | null | undefined,
  digits = 1,
): string {
  if (value === null || value === undefined) {
    return "No prior delta";
  }

  const prefix = value > 0 ? "+" : "";
  return `${prefix}${value.toFixed(digits)}%`;
}

export function formatPercentRatio(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "Pending";
  }

  return percentFormatter.format(value);
}

export function formatCurrencyMinor(
  amountMinor: number | null | undefined,
  currencyCode: string | null | undefined,
): string {
  if (amountMinor === null || amountMinor === undefined || !currencyCode) {
    return "Pending";
  }

  return getCurrencyFormatter(currencyCode).format(amountMinor / 100);
}

export function formatDateLabel(value: string | null | undefined): string {
  if (!value) {
    return "Pending";
  }

  return dateFormatter.format(new Date(`${value}T00:00:00`));
}

export function formatDateTimeLabel(value: string | null | undefined): string {
  if (!value) {
    return "Pending";
  }

  return dateTimeFormatter.format(new Date(value));
}
