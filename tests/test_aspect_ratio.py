"""Test cho check thưởng aspect_ratio (học viên tự viết). Ảnh giả 640x480 từ fixture make_ds."""
from pipeline.checks import aspect_ratio


def flagged(issues):
    return [(issue.image, issue.line) for issue in issues if issue.code == "BOX_ODD_ASPECT"]


def run(make_ds, cfg, lines, size=(640, 480)):
    ds = make_ds(images={"a": 1}, labels={"a": lines}, size=size)
    return aspect_ratio.run(ds, cfg)


def test_normal_boxes_are_silent(make_ds, cfg):
    # 128x144 px (tỉ lệ 1.1) và 64x192 px (tỉ lệ 3.0, người đứng)
    assert run(make_ds, cfg, ["0 0.5 0.5 0.2 0.3", "1 0.3 0.5 0.1 0.4"]) == []


def test_very_thin_box_is_a_warning(make_ds, cfg):
    issues = run(make_ds, cfg, ["1 0.5 0.5 0.2 0.3", "1 0.5 0.5 0.02 0.4"])   # dòng 2: 12.8x192 px -> tỉ lệ 15
    assert flagged(issues) == [("a", 2)]
    assert issues[0].severity == "warn" and issues[0].extra["aspect_ratio"] == 15.0


def test_very_flat_box_is_also_flagged(make_ds, cfg):
    assert flagged(run(make_ds, cfg, ["2 0.5 0.5 0.6 0.05"])) == [("a", 1)]    # 384x24 px -> tỉ lệ 16


def test_ratio_is_measured_in_pixels_not_normalised_units(make_ds, cfg):
    # w=0.1, h=0.6 trên ảnh 640x480: 64x288 px -> tỉ lệ 4.5 (không báo); theo số chuẩn hoá sẽ là 6.0 (báo nhầm)
    assert run(make_ds, cfg, ["1 0.5 0.5 0.1 0.6"]) == []


def test_threshold_is_read_from_config(make_ds, cfg):
    cfg["aspect_ratio"] = {"max_ratio": 2.0}
    assert flagged(run(make_ds, cfg, ["1 0.3 0.5 0.1 0.4"])) == [("a", 1)]       # tỉ lệ 3.0 > 2.0


def test_exactly_at_threshold_is_not_flagged(make_ds, cfg):
    cfg["aspect_ratio"] = {"max_ratio": 3.0}
    assert run(make_ds, cfg, ["1 0.3 0.5 0.1 0.4"]) == []                        # tỉ lệ đúng 3.0


def test_touches_edge_is_reported(make_ds, cfg):
    issues = run(make_ds, cfg, ["1 0.01 0.5 0.02 0.4", "1 0.5 0.5 0.02 0.4"])    # dòng 1 sát mép trái
    assert [issue.extra["touches_edge"] for issue in issues] == [True, False]


def test_broken_lines_and_blank_lines_do_not_crash_and_keep_line_numbers(make_ds, cfg):
    lines = ["garbage", "", "93 0.5 0.5 0.02 0.4", "1 0.5 0.5 0 0.4", "1 0.5 0.5 0.02 0.4"]
    assert flagged(run(make_ds, cfg, lines)) == [("a", 5)]


def test_image_without_label_file_is_skipped(make_ds, cfg):
    ds = make_ds(images={"a": 1, "b": 2}, labels={"a": ["1 0.5 0.5 0.02 0.4"]})
    assert flagged(aspect_ratio.run(ds, cfg)) == [("a", 1)]
