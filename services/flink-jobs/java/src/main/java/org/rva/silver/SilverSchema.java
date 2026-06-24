package org.rva.silver;

import org.apache.flink.table.api.TableEnvironment;

final class SilverSchema {
    private SilverSchema() {}

    static void ensureTables(TableEnvironment tEnv) {
        String createSilverV2 = String.join("\n",
            "CREATE TABLE IF NOT EXISTS rva.silver_detections_v2 (",
            "  schema_version        STRING,",
            "  event_type            STRING,",
            "  event_id              STRING,",
            "  detection_id          STRING,",
            "  pipeline_run_id       STRING,",
            "  store_id              STRING,",
            "  camera_id             STRING,",
            "  frame_index           BIGINT,",
            "  source_frame_index    BIGINT,",
            "  capture_ts            TIMESTAMP_LTZ(3),",
            "  img_w                 INT,",
            "  img_h                 INT,",
            "  det_id                STRING,",
            "  class_name            STRING,",
            "  class_id              INT,",
            "  conf                  DOUBLE,",
            "  bbox_x1               INT,",
            "  bbox_y1               INT,",
            "  bbox_x2               INT,",
            "  bbox_y2               INT,",
            "  track_id              BIGINT,",
            "  raw_track_id          BIGINT,",
            "  global_track_id       STRING,",
            "  track_state           STRING,",
            "  is_predicted          BOOLEAN,",
            "  anchor_type           STRING,",
            "  anchor_x              INT,",
            "  anchor_y              INT,",
            "  anchor_x_norm         DOUBLE,",
            "  anchor_y_norm         DOUBLE,",
            "  primary_zone_id       STRING,",
            "  primary_zone_type     STRING,",
            "  in_queue              BOOLEAN,",
            "  queue_zone_id         STRING,",
            "  model_name            STRING,",
            "  detector_type         STRING,",
            "  tracker_type          STRING,",
            "  supervision_version   STRING,",
            "  trackers_version      STRING,",
            "  zone_config_version   STRING,",
            "  processing_ts         TIMESTAMP_LTZ(3),",
            "  capture_date          DATE",
            ") PARTITIONED BY (store_id, capture_date) WITH (",
            "  'format-version' = '2',",
            "  'write.format.default' = 'parquet'",
            ")"
        );
        tEnv.executeSql(createSilverV2);

        String createParseErrors = String.join("\n",
            "CREATE TABLE IF NOT EXISTS rva.silver_detection_parse_errors (",
            "  schema_version        STRING,",
            "  event_id              STRING,",
            "  pipeline_run_id       STRING,",
            "  store_id              STRING,",
            "  camera_id             STRING,",
            "  frame_index           BIGINT,",
            "  source_frame_index    BIGINT,",
            "  parse_error_reason    STRING,",
            "  capture_ts_raw        STRING,",
            "  raw_payload           STRING,",
            "  processing_ts         TIMESTAMP_LTZ(3)",
            ") WITH (",
            "  'format-version' = '2',",
            "  'write.format.default' = 'parquet',",
            "  'partitioning' = 'days(processing_ts)'",
            ")"
        );
        tEnv.executeSql(createParseErrors);
    }
}
