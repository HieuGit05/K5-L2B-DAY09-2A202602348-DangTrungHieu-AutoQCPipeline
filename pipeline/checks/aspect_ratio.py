"""CHECK THƯỞNG — Box lệch tỉ lệ khung hình (quá dẹt hoặc quá mảnh so với bình thường).

Test:  pytest tests/test_aspect_ratio.py -q
Chạy thử trên một dataset (chỉ đọc):  python -m pipeline.checks.aspect_ratio data/raw

Tỉ lệ khung hình = cạnh dài / cạnh ngắn của box, tính theo PIXEL (box chuẩn hoá 0.1 x 0.1 trên ảnh 640x480 không phải hình vuông).

| code            | severity | khi nào                                                           |
|-----------------|----------|-------------------------------------------------------------------|
| BOX_ODD_ASPECT  | WARN     | tỉ lệ > max_ratio; extra = {"aspect_ratio", "touches_edge"}       |

Vì sao chỉ là CẢNH BÁO: box rất mảnh thường là vật bị cắt ở mép ảnh (hợp lệ), nhưng cũng có thể là box chỉ bao
một phần vật (vd. chỉ bao chân người). Máy không phân biệt được — người xem quyết định. `touches_edge` giúp người
duyệt biết nhanh trường hợp nào là vật bị cắt mép.

Ngưỡng: `cfg["aspect_ratio"]["max_ratio"]` nếu có, mặc định DEFAULT_MAX_RATIO = 5.0. Không thêm vào
configs/pipeline.yaml vì file đó bị ghim (chỉ được đổi 2 khoá CALIBRATE). Chọn 5.0 vì nhãn người của bộ calib
có tỉ lệ lớn nhất 4.0; trên raw, 11/719 box vượt 5.0.

Dòng hỏng / id lạ / box rỗng bị bỏ qua (check label_format đã báo). Ảnh không mở được cũng bỏ qua.
"""
import sys

from ..common import WARN, Dataset, Issue, load_config, parse_yolo_line

CHECK_NAME = "aspect_ratio"
DEFAULT_MAX_RATIO = 5.0
EDGE_MARGIN = 0.01        # mép box cách mép ảnh < 1% thì coi là "chạm mép"


def touches_image_edge(center_x, center_y, box_width, box_height):
    """Box có chạm (hoặc gần chạm) một trong 4 mép ảnh không."""
    left_edge, right_edge = center_x - box_width / 2, center_x + box_width / 2
    top_edge, bottom_edge = center_y - box_height / 2, center_y + box_height / 2
    return (left_edge < EDGE_MARGIN or top_edge < EDGE_MARGIN
            or right_edge > 1 - EDGE_MARGIN or bottom_edge > 1 - EDGE_MARGIN)


def run(ds, cfg):
    # ds: Dataset cần kiểm; cfg: cấu hình pipeline (giống chữ ký các check khác)
    max_ratio = cfg.get("aspect_ratio", {}).get("max_ratio", DEFAULT_MAX_RATIO)
    issues = []

    for image_file in ds.image_files():
        image_name = image_file.stem
        label_lines = ds.read_label_lines(image_name)
        image_size = ds.image_size(image_name)
        if label_lines is None or image_size is None:
            continue
        image_width_px, image_height_px = image_size

        for line_number, line_text in label_lines:
            try:
                class_id, center_x, center_y, box_width, box_height = parse_yolo_line(line_text)
            except ValueError:
                continue
            if not 0 <= class_id < len(ds.classes) or box_width <= 0 or box_height <= 0:
                continue

            box_width_px = box_width * image_width_px
            box_height_px = box_height * image_height_px
            aspect_ratio = max(box_width_px / box_height_px, box_height_px / box_width_px)
            if aspect_ratio <= max_ratio:
                continue

            at_edge = touches_image_edge(center_x, center_y, box_width, box_height)
            shape = "dẹt" if box_width_px > box_height_px else "mảnh"
            message = (f"box {ds.classes[class_id]} quá {shape}: {box_width_px:.0f}x{box_height_px:.0f}px, "
                       f"tỉ lệ {aspect_ratio:.1f} > {max_ratio}" + (" (chạm mép ảnh: có thể bị cắt)" if at_edge else ""))
            issues.append(Issue(CHECK_NAME, WARN, "BOX_ODD_ASPECT", image_name, message, line_number,
                                {"aspect_ratio": round(aspect_ratio, 2), "touches_edge": at_edge}))
    return issues


if __name__ == "__main__":
    dataset_folder = sys.argv[1] if len(sys.argv) > 1 else "data/raw"
    config = load_config()
    found_issues = run(Dataset(dataset_folder, config["classes"]), config)
    print(f"{len(found_issues)} box lệch tỉ lệ khung hình trong {dataset_folder}:")
    for issue in found_issues:
        print(f"  {issue.image}:{issue.line}  {issue.message}")
