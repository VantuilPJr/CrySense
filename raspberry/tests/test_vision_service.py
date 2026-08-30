from crysense.vision_service import (
    Detection,
    SafetyEvaluator,
    VisionConfig,
    VisionRunner,
    _risk_zone_values,
)


def config(**changes) -> VisionConfig:
    values = {
        "pi_url": "http://raspberry:8080",
        "model_source": "yolo11n.pt",
        "image_size": 320,
        "confidence_threshold": 0.45,
        "interval_seconds": 0.5,
        "report_interval_seconds": 2.0,
        "consecutive_frames": 3,
        "risk_labels": (),
        "risk_zone": (0.1, 0.0, 0.9, 0.28),
        "token": "",
    }
    values.update(changes)
    return VisionConfig(**values)


def test_generic_person_in_exit_zone_alerts_only_after_confirmation():
    evaluator = SafetyEvaluator(config())
    person = Detection("person", 0.88, (80, 5, 240, 100))

    assert evaluator.evaluate([person], 320, 240).alert is False
    assert evaluator.evaluate([person], 320, 240).alert is False

    decision = evaluator.evaluate([person], 320, 240)

    assert decision.alert is True
    assert decision.label == "near_exit_zone"


def test_generic_person_outside_exit_zone_does_not_alert():
    evaluator = SafetyEvaluator(config(consecutive_frames=1))
    person = Detection("person", 0.88, (80, 120, 240, 230))

    assert evaluator.evaluate([person], 320, 240).alert is False


def test_zone_update_resets_previous_confirmation():
    evaluator = SafetyEvaluator(config())
    person = Detection("person", 0.88, (80, 5, 240, 100))
    assert evaluator.evaluate([person], 320, 240).alert is False

    evaluator.set_risk_zone((0.1, 0.5, 0.9, 0.8))

    assert evaluator.evaluate([person], 320, 240).alert is False
    assert _risk_zone_values([0.1, 0.0, 0.9, 0.28]) == (0.1, 0.0, 0.9, 0.28)


def test_display_detections_only_exposes_people_in_normalized_coordinates():
    detections = [
        Detection("person", 0.83, (32, 24, 160, 216)),
        Detection("chair", 0.91, (20, 20, 100, 200)),
    ]

    visible = VisionRunner._display_detections(detections, 320, 240)

    assert visible == [{"label": "person", "confidence": 0.83, "box": (0.1, 0.1, 0.5, 0.9)}]
