import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const reportDirectory = path.resolve(process.argv[2] ?? "artifacts/lighthouse");
const routes = ["bn-home", "bn-product", "en-home", "en-product"];

function median(values) {
  const ordered = [...values].sort((left, right) => left - right);
  return ordered[Math.floor(ordered.length / 2)];
}

function finiteMetric(value, label) {
  if (!Number.isFinite(value)) {
    throw new Error(`Missing Lighthouse metric: ${label}`);
  }
  return value;
}

const summary = { generated_at: new Date().toISOString(), routes: {} };
const failures = [];

for (const route of routes) {
  const runs = [];
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    const filePath = path.join(reportDirectory, `${route}-${attempt}.json`);
    const report = JSON.parse(await readFile(filePath, "utf8"));
    runs.push({
      performance: finiteMetric(
        report.categories?.performance?.score,
        `${route} performance`,
      ),
      accessibility: finiteMetric(
        report.categories?.accessibility?.score,
        `${route} accessibility`,
      ),
      lcp_ms: finiteMetric(
        report.audits?.["largest-contentful-paint"]?.numericValue,
        `${route} LCP`,
      ),
    });
  }

  const result = {
    runs,
    median_performance: median(runs.map((run) => run.performance)),
    median_accessibility: median(runs.map((run) => run.accessibility)),
    median_lcp_ms: Math.round(median(runs.map((run) => run.lcp_ms))),
  };
  summary.routes[route] = result;

  if (result.median_performance < 0.9) {
    failures.push(
      `${route} median performance ${result.median_performance} is below 0.90`,
    );
  }
  if (result.median_accessibility < 0.95) {
    failures.push(
      `${route} median accessibility ${result.median_accessibility} is below 0.95`,
    );
  }
  if (result.median_lcp_ms >= 2500) {
    failures.push(
      `${route} median LCP ${result.median_lcp_ms}ms is not below 2500ms`,
    );
  }
}

await mkdir(reportDirectory, { recursive: true });
await writeFile(
  path.join(reportDirectory, "lighthouse-summary.json"),
  `${JSON.stringify(summary, null, 2)}\n`,
  "utf8",
);

console.log(JSON.stringify(summary, null, 2));
if (failures.length > 0) {
  throw new Error(failures.join("\n"));
}
