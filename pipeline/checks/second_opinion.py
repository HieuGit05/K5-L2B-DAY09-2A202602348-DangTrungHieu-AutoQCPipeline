"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★ (khó nhất, đáng điểm nhất)

Test:  pytest tests/test_second_opinion.py -q

Máy kiểm quy tắc, người kiểm ý nghĩa (slide). Các lỗi như thiếu nhãn / gán nhầm lớp hợp lệ / box lỏng
KHÔNG bắt được bằng quy tắc cú pháp. Ta nhờ một model mạnh hơn "nhìn lại" và CHỈ CẢNH BÁO (model cũng có thể sai):
những ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.

`preds[stem]` = list `[id_lớp, conf, cx, cy, w, h]` của model (lấy qua `get_preds(ds, cfg, "checker")` nếu preds=None).
`L = ds.valid_boxes(stem)` = list `(id_lớp, cx, cy, w, h)` của nhãn (đã bỏ dòng hỏng).
Ngưỡng ở `cfg["second_opinion"]`: conf, min_area_px, fp_conf, iou_missing, iou_match, iou_loose.

Thuật toán gợi ý, với từng ảnh (bỏ qua ảnh không có trong preds hoặc không có file nhãn):
  P = dự đoán có conf >= conf  VÀ diện tích px (w*W * h*H) >= min_area_px
  Với mỗi dự đoán r trong P: lấy các nhãn có IoU(r, nhãn) >= iou_missing  (cands)
   - không có cands                            -> POSSIBLE_MISSING     (model thấy vật mà nhãn không có box)
   - có cands cùng lớp, tốt nhất IoU < iou_loose -> POSSIBLE_LOOSE_BOX  (đúng vật, box lỏng/lệch)
   - không có cands cùng lớp, nhưng cands tốt nhất IoU >= iou_match (khác lớp) -> POSSIBLE_WRONG_CLASS
  Với mỗi dòng nhãn hợp lệ: nếu IoU với MỌI dự đoán (conf >= fp_conf, không lọc diện tích) đều < iou_missing
                                             -> POSSIBLE_FALSE_POS  (box nhãn không khớp vật nào model thấy; Issue.line = số dòng)

Chi tiết các ca biên (test kiểm đúng các ca này)
- `cands` gồm nhãn MỌI lớp có IoU >= iou_missing; "tốt nhất cùng lớp" = cands cùng lớp có IoU lớn nhất; "tốt nhất khác lớp" tương tự với cands khác lớp.
- Thứ tự quyết định cho mỗi dự đoán: (1) cands rỗng -> MISSING. (2) có cands cùng lớp: IoU tốt nhất < iou_loose -> LOOSE_BOX, ngược lại KHÔNG cờ
  (nhãn đúng lớp đã phủ vật này, kể cả khi còn nhãn khác lớp chồng lên). (3) không có cands cùng lớp: nếu IoU tốt nhất khác lớp >= iou_match -> WRONG_CLASS;
  nếu chỉ có khác lớp với IoU trong [iou_missing, iou_match) -> không cờ gì (mơ hồ: để cho FALSE_POS / lần duyệt khác).
- Một dự đoán sinh tối đa MỘT issue (MISSING / LOOSE_BOX / WRONG_CLASS); một ảnh có thể có nhiều issue.
- Thứ tự issue: theo `ds.image_files()` rồi theo thứ tự dự đoán trong `preds[stem]`, cuối cùng là các FALSE_POS theo số dòng; `Issue.image` = stem, `Issue.line` chỉ đặt cho FALSE_POS.

Lưu ý số dòng: dùng `ds.read_label_lines(stem)` (giữ số dòng gốc, kể cả dòng hỏng/trống) để lấy `Issue.line`; `valid_boxes` KHÔNG giữ số dòng.

Tất cả severity WARN; `Issue.extra` nên có {"conf": ...} hoặc {"iou": ...} (hàng đợi duyệt dùng conf để xếp ưu tiên).

Gợi ý
- `iou_xywh` có sẵn. Dòng nhãn hỏng không được làm script chết (dùng `ds.valid_boxes` và `parse_yolo_line` trong try).
- Kết quả phụ thuộc mạnh vào ngưỡng: calibrate chúng ở Bước 3 thay vì đoán.
"""
from ..common import WARN, Issue, iou_xywh, parse_yolo_line
from ..model_cache import get_preds

CHECK_NAME = "second_opinion"
DESCRIPTIONS = {
    "POSSIBLE_MISSING": "model thấy vật mà nhãn không có box",
    "POSSIBLE_LOOSE_BOX": "đúng vật, đúng lớp nhưng box lệch/lỏng",
    "POSSIBLE_WRONG_CLASS": "cùng vị trí nhưng nhãn khác lớp",
}


def read_valid_labels(ds, image_name):
    """[(số dòng gốc, id lớp, box (cx, cy, w, h))] — bỏ dòng hỏng / id lớp lạ (check label_format đã báo)."""
    valid_labels = []
    for line_number, line_text in ds.read_label_lines(image_name):
        try:
            class_id, center_x, center_y, box_width, box_height = parse_yolo_line(line_text)
        except ValueError:
            continue
        if 0 <= class_id < len(ds.classes):
            valid_labels.append((line_number, class_id, (center_x, center_y, box_width, box_height)))
    return valid_labels


def compare_prediction(prediction, labels, rules):
    """So MỘT dự đoán với các nhãn. Trả về (mã cảnh báo, extra) hoặc None nếu không có gì đáng ngờ."""
    predicted_class, confidence, *predicted_box = prediction

    # Các nhãn (mọi lớp) chồng lên dự đoán đủ nhiều: (IoU, id lớp)
    candidates = []
    for _, label_class, label_box in labels:
        iou = iou_xywh(predicted_box, label_box)
        if iou >= rules["iou_missing"]:
            candidates.append((iou, label_class))

    # (1) Không nhãn nào phủ vật model thấy
    if not candidates:
        return "POSSIBLE_MISSING", {"conf": confidence, "pred_class": predicted_class}

    same_class_ious = [iou for iou, label_class in candidates if label_class == predicted_class]
    other_class_ious = [iou for iou, label_class in candidates if label_class != predicted_class]

    # (2) Có nhãn đúng lớp: chỉ cờ nếu box lệch/lỏng
    if same_class_ious:
        best_iou = max(same_class_ious)
        if best_iou < rules["iou_loose"]:
            return "POSSIBLE_LOOSE_BOX", {"conf": confidence, "iou": round(best_iou, 4)}
        return None

    # (3) Chỉ có nhãn khác lớp: trùng vị trí rõ ràng thì nghi gán nhầm lớp; mơ hồ thì im lặng
    best_iou = max(other_class_ious)
    if best_iou >= rules["iou_match"]:
        return "POSSIBLE_WRONG_CLASS", {"conf": confidence, "iou": round(best_iou, 4), "pred_class": predicted_class}
    return None


def run(ds, cfg, preds=None):
    # ds: Dataset cần kiểm; cfg: cấu hình pipeline; preds: {tên ảnh: [[id lớp, conf, cx, cy, w, h], ...]}
    rules = cfg["second_opinion"]
    if preds is None:
        preds = get_preds(ds, cfg, "checker")
    issues = []

    for image_file in ds.image_files():
        image_name = image_file.stem
        image_size = ds.image_size(image_name)
        if image_name not in preds or ds.read_label_lines(image_name) is None or image_size is None:
            continue
        image_width_px, image_height_px = image_size
        labels = read_valid_labels(ds, image_name)
        predictions = preds[image_name]

        # Phần A — từng dự đoán đáng tin (conf đủ cao, vật đủ lớn) -> MISSING / LOOSE_BOX / WRONG_CLASS
        for prediction in predictions:
            confidence, box_width, box_height = prediction[1], prediction[4], prediction[5]
            area_px = box_width * image_width_px * box_height * image_height_px
            if confidence < rules["conf"] or area_px < rules["min_area_px"]:
                continue
            result = compare_prediction(prediction, labels, rules)
            if result is not None:
                code, extra = result
                message = f"{DESCRIPTIONS[code]} (model: {ds.classes[prediction[0]]}, conf {confidence:.2f})"
                issues.append(Issue(CHECK_NAME, WARN, code, image_name, message, None, extra))

        # Phần B — từng dòng nhãn: không khớp dự đoán nào (conf >= fp_conf, KHÔNG lọc diện tích) -> FALSE_POS
        loose_predicted_boxes = [prediction[2:] for prediction in predictions if prediction[1] >= rules["fp_conf"]]
        for line_number, label_class, label_box in labels:
            best_iou = max((iou_xywh(label_box, predicted_box) for predicted_box in loose_predicted_boxes), default=0.0)
            if best_iou < rules["iou_missing"]:
                message = f"nhãn {ds.classes[label_class]} ở dòng {line_number} không khớp vật nào model thấy"
                issues.append(Issue(CHECK_NAME, WARN, "POSSIBLE_FALSE_POS", image_name, message, line_number,
                                    {"iou": round(best_iou, 4)}))

    return issues
