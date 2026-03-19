/**
 * Projects future temperatures using least-squares linear regression.
 */
export function projectTemperature(
  readings: number[],
  stepsAhead = 10,
): number[] {
  const n = readings.length;
  if (n < 2) return [];

  const xMean = (n - 1) / 2;
  const yMean = readings.reduce((sum, value) => sum + value, 0) / n;

  let numerator = 0;
  let denominator = 0;

  for (let x = 0; x < n; x++) {
    numerator += (x - xMean) * (readings[x] - yMean);
    denominator += (x - xMean) ** 2;
  }

  const slope = denominator === 0 ? 0 : numerator / denominator;

  return Array.from({ length: stepsAhead }, (_, i) => {
    const futureX = n + i;
    return yMean + slope * (futureX - xMean);
  });
}
