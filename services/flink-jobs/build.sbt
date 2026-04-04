ThisBuild / organization := "com.rva"
ThisBuild / scalaVersion := "2.12.18"
ThisBuild / version      := "0.1.0"

val flinkVersion     = "1.18.1"
val icebergVersion   = "1.4.3"
val pulsarVersion    = "3.3.2"

lazy val root = (project in file("."))
  .settings(
    name := "flink-jobs",

    libraryDependencies ++= Seq(
      // Flink core (provided — runtime in the cluster)
      "org.apache.flink" %% "flink-scala"          % flinkVersion % Provided,
      "org.apache.flink" %% "flink-streaming-scala" % flinkVersion % Provided,
      "org.apache.flink"  % "flink-clients"        % flinkVersion % Provided,

      // Flink CEP
      "org.apache.flink"  % "flink-cep"            % flinkVersion,

      // Flink Pulsar connector
      "io.streamnative.connectors" % "flink-connector-pulsar" % s"4.1.0-${flinkVersion}",

      // Flink Iceberg connector
      "org.apache.iceberg"  % "iceberg-flink-runtime-1.18" % icebergVersion,

      // Redis state backend
      "org.apache.bahir"   %% "flink-connector-redis" % "1.1.0",

      // Logging
      "org.apache.logging.log4j" % "log4j-slf4j-impl"    % "2.17.1" % Runtime,
      "org.apache.logging.log4j" % "log4j-api"           % "2.17.1" % Runtime,
      "org.apache.logging.log4j" % "log4j-core"          % "2.17.1" % Runtime,
    ),

    assembly / assemblyJarName := "flink-jobs-assembly.jar",
    assembly / assemblyMergeStrategy := {
      case PathList("META-INF", xs @ _*) => MergeStrategy.discard
      case "reference.conf"              => MergeStrategy.concat
      case x                             => MergeStrategy.first
    },
  )
