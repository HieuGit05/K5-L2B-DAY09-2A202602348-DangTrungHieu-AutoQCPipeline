"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line

CHECK_NAME = "label_format"


def overflow_amount(center_x, center_y, box_width, box_height):
    """Mép box vượt ra ngoài [0, 1] bao nhiêu (lấy mép tràn nhiều nhất); 0 nếu nằm gọn trong ảnh."""
    left_edge, right_edge = center_x - box_width / 2, center_x + box_width / 2
    top_edge, bottom_edge = center_y - box_height / 2, center_y + box_height / 2
    return max(0.0, -left_edge, right_edge - 1, -top_edge, bottom_edge - 1)


def run(ds, cfg):
    # ds: Dataset cần kiểm; cfg: cấu hình pipeline (tên tham số giữ theo stub vì pipeline gọi run(ds, cfg))
    rules = cfg["label_format"]
    num_classes = len(ds.classes)
    issues = []

    for image_file in ds.image_files():
        image_name = image_file.stem                 # tên ảnh không đuôi, vd. "img_0001"
        label_lines = ds.read_label_lines(image_name)
        if label_lines is None:                      # thiếu file nhãn: check missing_labels đã báo
            continue
        image_size = ds.image_size(image_name)       # (rộng, cao) px; None nếu ảnh hỏng
        previous_boxes = []                          # các box hợp lệ ở những dòng trước, để tìm box lặp

        for line_number, line_text in label_lines:
            def report(severity, code, message, extra=None):
                issues.append(Issue(CHECK_NAME, severity, code, image_name, message, line_number, extra or {}))

            # 1) Định dạng: phải đúng 5 cột số
            try:
                class_id, center_x, center_y, box_width, box_height = parse_yolo_line(line_text)
            except ValueError as parse_error:
                report(ERROR, "BAD_FORMAT", f"dòng sai định dạng ({parse_error}): {line_text!r}")
                continue

            # 2) ID lớp phải nằm trong 0..num_classes-1
            if not 0 <= class_id < num_classes:
                report(ERROR, "BAD_CLASS_ID", f"id lớp {class_id} ngoài 0..{num_classes - 1}")
                continue

            # 3) Box phải có chiều rộng và chiều cao dương
            if box_width <= 0 or box_height <= 0:
                report(ERROR, "BOX_ZERO", f"box rỗng: rộng={box_width}, cao={box_height}")
                continue

            # 4) Box tràn ra ngoài ảnh quá mức cho phép
            overflow = overflow_amount(center_x, center_y, box_width, box_height)
            if overflow > rules["overflow_tol"]:
                report(ERROR, "BOX_OUT_OF_IMAGE", f"box tràn ảnh {overflow:.4f}", {"overflow": round(overflow, 6)})

            # 5) Box lặp: cùng lớp và trùng gần hết với một box ở dòng trước
            box = (center_x, center_y, box_width, box_height)
            for previous_class_id, previous_box, previous_line_number in previous_boxes:
                iou = iou_xywh(box, previous_box)
                if previous_class_id == class_id and iou > rules["dup_box_iou"]:
                    report(ERROR, "DUP_BOX", f"trùng box ở dòng {previous_line_number} (IoU={iou:.2f})",
                           {"iou": round(iou, 4), "same_as_line": previous_line_number})
                    break
            previous_boxes.append((class_id, box, line_number))

            # 6) Box quá nhỏ (theo pixel) — cần biết kích thước ảnh
            if image_size is not None:
                image_width_px, image_height_px = image_size
                short_side_px = min(box_width * image_width_px, box_height * image_height_px)
                if short_side_px < rules["min_box_px"]:
                    report(WARN, "BOX_TINY", f"cạnh ngắn {short_side_px:.1f}px < {rules['min_box_px']}px",
                           {"short_side_px": round(short_side_px, 1)})

            # 7) Box quá lớn (gần phủ cả ảnh)
            box_area_fraction = box_width * box_height   # diện tích box / diện tích ảnh
            if box_area_fraction > rules["max_box_frac"]:
                report(WARN, "BOX_HUGE", f"box chiếm {box_area_fraction:.0%} ảnh",
                       {"area_frac": round(box_area_fraction, 4)})

    return issues
