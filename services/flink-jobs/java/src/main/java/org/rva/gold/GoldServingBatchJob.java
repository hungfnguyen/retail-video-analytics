package org.rva.gold;

import org.apache.flink.table.api.TableEnvironment;

import java.util.LinkedHashMap;
import java.util.Map;

public class GoldServingBatchJob {

    private static final String SQL_BASE = "sql/gold-serving/";

    public static void main(String[] args) throws Exception {
        Args parsed = Args.parse(args);
        TableEnvironment tEnv = GoldServingSupport.createBatchEnvironment();
        GoldServingSupport.configureBatchParallelism(tEnv, parsed.domain);
        GoldServingSupport.ensureServingTables(tEnv);

        switch (parsed.domain) {
            case "traffic_hourly":
                runTrafficHourly(tEnv, parsed);
                break;
            case "traffic_daily":
                runTrafficDaily(tEnv, parsed);
                break;
            case "heatmap_5min":
                runHeatmap5Min(tEnv, parsed);
                break;
            case "heatmap_hour":
                runHeatmapHour(tEnv, parsed);
                break;
            case "queue_hourly":
                runQueueHourly(tEnv, parsed);
                break;
            case "queue_daily":
                runQueueDaily(tEnv, parsed);
                break;
            case "zone_hourly":
                runZoneHourly(tEnv, parsed);
                break;
            case "zone_daily":
                runZoneDaily(tEnv, parsed);
                break;
            case "dwell_daily":
                runDwellDaily(tEnv, parsed);
                break;
            case "alert_hourly":
                runAlertHourly(tEnv, parsed);
                break;
            case "alert_daily":
                runAlertDaily(tEnv, parsed);
                break;
            case "executive_daily":
                runExecutiveDaily(tEnv, parsed);
                break;
            default:
                throw new IllegalArgumentException("Unsupported domain: " + parsed.domain);
        }
    }

    private static void runTrafficHourly(TableEnvironment tEnv, Args args) throws Exception {
        executeStep(tEnv, args, "traffic_hourly.sql");
    }

    private static void runTrafficDaily(TableEnvironment tEnv, Args args) throws Exception {
        executeStep(tEnv, args, "traffic_daily.sql");
    }

    private static void runHeatmap5Min(TableEnvironment tEnv, Args args) throws Exception {
        executeStep(tEnv, args, "heatmap_5min.sql");
    }

    private static void runHeatmapHour(TableEnvironment tEnv, Args args) throws Exception {
        executeStep(tEnv, args, "heatmap_hour.sql");
    }

    private static void runQueueHourly(TableEnvironment tEnv, Args args) throws Exception {
        executeStep(tEnv, args, "queue_hourly.sql");
    }

    private static void runQueueDaily(TableEnvironment tEnv, Args args) throws Exception {
        executeStep(tEnv, args, "queue_daily.sql");
    }

    private static void runZoneHourly(TableEnvironment tEnv, Args args) throws Exception {
        executeStep(tEnv, args, "zone_hourly.sql");
    }

    private static void runZoneDaily(TableEnvironment tEnv, Args args) throws Exception {
        executeStep(tEnv, args, "zone_daily.sql");
    }

    private static void runDwellDaily(TableEnvironment tEnv, Args args) throws Exception {
        executeStep(tEnv, args, "dwell_daily.sql");
    }

    private static void runAlertHourly(TableEnvironment tEnv, Args args) throws Exception {
        executeStep(tEnv, args, "alert_hourly.sql");
    }

    private static void runAlertDaily(TableEnvironment tEnv, Args args) throws Exception {
        executeStep(tEnv, args, "alert_daily.sql");
    }

    private static void runExecutiveDaily(TableEnvironment tEnv, Args args) throws Exception {
        executeStep(tEnv, args, "executive_daily.sql");
    }

    private static void executeStep(TableEnvironment tEnv, Args args, String sqlResource) throws Exception {
        String sql = GoldServingSupport.renderSqlResource(SQL_BASE + sqlResource, replacements(args));
        GoldServingSupport.executeAndAwait(tEnv, sql);
    }

    private static Map<String, String> replacements(Args args) {
        Map<String, String> values = new LinkedHashMap<>();
        values.put("{{START_SQL}}", GoldServingSupport.sqlString(args.start));
        values.put("{{END_SQL}}", GoldServingSupport.sqlString(args.end));
        return values;
    }

    private static final class Args {
        final String domain;
        final String start;
        final String end;
        final String runMode;

        private Args(String domain, String start, String end, String runMode) {
            this.domain = domain;
            this.start = start;
            this.end = end;
            this.runMode = runMode;
        }

        static Args parse(String[] args) {
            String domain = null;
            String start = null;
            String end = null;
            String runMode = "airflow";
            for (int i = 0; i < args.length; i++) {
                switch (args[i]) {
                    case "--domain":
                        domain = args[++i];
                        break;
                    case "--start":
                        start = args[++i];
                        break;
                    case "--end":
                        end = args[++i];
                        break;
                    case "--run-mode":
                        runMode = args[++i];
                        break;
                    default:
                        throw new IllegalArgumentException("Unknown arg: " + args[i]);
                }
            }
            if (domain == null || start == null || end == null) {
                throw new IllegalArgumentException("Usage: --domain <traffic_hourly|traffic_daily|heatmap_5min|heatmap_hour|queue_hourly|queue_daily|zone_hourly|zone_daily|dwell_daily|alert_hourly|alert_daily|executive_daily> --start YYYY-MM-DD --end YYYY-MM-DD [--run-mode mode]");
            }
            return new Args(domain, start, end, runMode);
        }
    }
}
