"""Unit tests for core.constants — ensure no accidental drift."""

from core import constants


class TestTopicConstants:
    def test_detection_topic_format(self):
        assert constants.TOPIC_DETECTION_FRAMES.startswith("persistent://retail/")

    def test_media_topic_format(self):
        assert constants.TOPIC_MEDIA_EVENTS.startswith("persistent://retail/")

    def test_dlq_topic_format(self):
        assert "dlq" in constants.TOPIC_DLQ.lower()


class TestDefaults:
    def test_conf_thres_in_range(self):
        assert 0 < constants.DEFAULT_CONF_THRES < 1

    def test_class_filter_is_person_only(self):
        assert constants.DEFAULT_CLASS_FILTER == [0]

    def test_fps_target_is_positive(self):
        assert constants.DEFAULT_FPS_TARGET > 0

    def test_interval_sec_is_positive(self):
        assert constants.DEFAULT_FRAME_SAMPLE_INTERVAL_SEC > 0
