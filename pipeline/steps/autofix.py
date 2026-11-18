"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict

import yaml

from ..common import ERROR, parse_yolo_line

DROP_LINE_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
REMOVE_IMAGE_CODES = {"DUP_IMAGE_EXACT", "DUP_IMAGE_NEAR", "LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}


def make_change(image_name, line_number, action, before, after):
    """Một dòng của 03_fixes.csv (đúng 5 cột)."""
    return {"image": image_name, "line": line_number, "action": action, "before": before, "after": after}


def clip_line(line_text):
    """Cắt box về trong [0, 1]. Trả về dòng mới, hoặc None nếu box không còn diện tích (nằm hẳn ngoài ảnh)."""
    class_id, center_x, center_y, box_width, box_height = parse_yolo_line(line_text)
    left_edge = max(0.0, center_x - box_width / 2)
    right_edge = min(1.0, center_x + box_width / 2)
    top_edge = max(0.0, center_y - box_height / 2)
    bottom_edge = min(1.0, center_y + box_height / 2)
    if right_edge <= left_edge or bottom_edge <= top_edge:
        return None
    new_center_x, new_center_y = (left_edge + right_edge) / 2, (top_edge + bottom_edge) / 2
    new_width, new_height = right_edge - left_edge, bottom_edge - top_edge
    return f"{class_id} {new_center_x:.6f} {new_center_y:.6f} {new_width:.6f} {new_height:.6f}"


def fix(ds, issues, cfg):
    # ds: Dataset bản làm việc (KHÔNG phải data/raw); cfg: cấu hình pipeline (tên tham số giữ theo stub)
    error_issues = [issue for issue in issues if issue.severity == ERROR]   # cảnh báo là việc của người
    changes = []

    # 1) Xoá ảnh hỏng / trùng / rò rỉ test — làm TRƯỚC để bỏ qua các lỗi dòng của ảnh đã xoá
    removed_images = set()
    for issue in error_issues:
        if issue.code not in REMOVE_IMAGE_CODES or issue.image in removed_images:
            continue
        image_path = ds.image_path(issue.image)
        if image_path is None:                       # đã bị xoá từ lần chạy trước
            continue
        image_path.unlink()
        label_path = ds.label_path(issue.image)
        if label_path.exists():
            label_path.unlink()
        removed_images.add(issue.image)
        changes.append(make_change(issue.image, None, "remove_image", f"{image_path.name} ({issue.code})", "(đã xoá ảnh + nhãn)"))

    # 2) Ảnh thiếu file nhãn: máy không bịa nhãn, chỉ ghi lại để chuyển cho người gán
    for issue in error_issues:
        if issue.code == "MISSING_LABEL_FILE" and issue.image not in removed_images:
            changes.append(make_change(issue.image, None, "needs_label", "(không có file)", "chuyển người gán"))

    # 3) Tên lớp sai trong data.yaml: ghi lại đúng cfg["classes"] (làm một lần dù có nhiều issue)
    if any(issue.code == "BAD_CLASS_NAME" for issue in error_issues):
        yaml_content = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) if ds.yaml_path.exists() else None
        yaml_content = yaml_content or {}
        old_names = yaml_content.get("names")
        yaml_content["names"] = {class_id: class_name for class_id, class_name in enumerate(cfg["classes"])}
        ds.yaml_path.write_text(yaml.safe_dump(yaml_content, allow_unicode=True, sort_keys=False), encoding="utf-8")
        changes.append(make_change("data.yaml", None, "rename_classes", str(old_names), str(cfg["classes"])))

    # 4) Lỗi dòng nhãn: gom theo ảnh -> {số dòng gốc: các mã lỗi}, rồi ghi lại file MỘT lần
    codes_by_line_by_image = defaultdict(lambda: defaultdict(set))
    for issue in error_issues:
        if issue.line is not None and issue.image not in removed_images:
            if issue.code in DROP_LINE_CODES or issue.code == "BOX_OUT_OF_IMAGE":
                codes_by_line_by_image[issue.image][issue.line].add(issue.code)

    for image_name, codes_by_line in codes_by_line_by_image.items():
        label_path = ds.label_path(image_name)
        if not label_path.exists():
            continue
        original_lines = label_path.read_text(encoding="utf-8").splitlines()   # giữ cả dòng trống để số dòng khớp
        new_lines = []
        for line_number, line_text in enumerate(original_lines, start=1):
            line_codes = codes_by_line.get(line_number, set())
            if line_codes & DROP_LINE_CODES:          # có lỗi phải xoá dòng: xoá thắng, không clip nữa
                changes.append(make_change(image_name, line_number, "drop_line", line_text, "(xoá dòng)"))
                continue
            if "BOX_OUT_OF_IMAGE" in line_codes:
                clipped_line = clip_line(line_text)
                if clipped_line is None:              # box nằm hẳn ngoài ảnh: xoá thay vì ghi box rỗng
                    changes.append(make_change(image_name, line_number, "drop_line", line_text, "(xoá dòng: box ngoài ảnh)"))
                    continue
                changes.append(make_change(image_name, line_number, "clip_box", line_text, clipped_line))
                new_lines.append(clipped_line)
                continue
            new_lines.append(line_text)
        label_path.write_text("".join(line + "\n" for line in new_lines), encoding="utf-8")

    return changes
