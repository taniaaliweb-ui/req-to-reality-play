// Deterministic economic calculations. Never performed by an LLM.
import type { EconomicYear } from "@/types/lifespan";

export const householdIncome = (y: EconomicYear) => y.income + y.spouseIncome;
export const totalExpenses = (y: EconomicYear) =>
  y.housing + y.food + y.education + y.healthcare + y.transport + y.familySupport;
export const netWorth = (y: EconomicYear) => y.assets + y.investments - y.liabilities;

/** Convert nominal value to real terms of a base year using the row's price index. */
export const toReal = (value: number, index: number, baseIndex: number) =>
  Math.round((value * baseIndex) / index);

export const formatMoney = (n: number, currency = "INR") => {
  const sym = currency === "INR" ? "₹" : currency === "AED" ? "AED " : "$";
  const abs = Math.abs(n);
  const s =
    abs >= 1e7 ? `${(abs / 1e7).toFixed(2)} cr` : abs >= 1e5 ? `${(abs / 1e5).toFixed(1)} L` : abs.toLocaleString("en-IN");
  return `${n < 0 ? "-" : ""}${sym}${s}`;
};
