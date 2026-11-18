"""BƯỚC 4 — Cửa chặn: quyết định Release / Hold / Rework.   ★

Test:  pytest tests/test_gate.py -q

Cây quyết định Day 07 (slide Day 09: "Lỗi bắt buộc chặn pipeline; lỗi cảnh báo chuyển người xem"):

  còn ≥ 1 lỗi bắt buộc (severity ERROR)                          -> "Rework"
  không còn lỗi bắt buộc, nhưng tỉ lệ ẢNH còn cảnh báo
      >= cfg["gate"]["warn_ratio_hold"]                          -> "Hold"
  còn lại                                                        -> "Release"

Tỉ lệ cảnh báo = (số ẢNH khác nhau có ≥ 1 cảnh báo) / (tổng số ảnh).  Chú ý:
- chỉ đếm issue có `image` nằm trong `image_stems` (bỏ "<dataset>", "data.yaml");
- bỏ qua ảnh nằm trong `reviewed` (người đã xem, cảnh báo của ảnh đó coi như đã xử lý) — nhưng LỖI BẮT BUỘC thì không bao giờ được bỏ qua;
- mẫu số là số ảnh, không phải số issue.

Trả về dict: decision, n_errors, n_warn_images, n_images, warn_ratio (làm tròn 4 chữ số), reasons (list[str], giải thích bằng tiếng Việt, có số liệu).
"""
from ..common import ERROR, WARN


def decide(issues, image_stems, cfg, reviewed=frozenset()):
    # image_stems: tên (không đuôi) của mọi ảnh trong dataset; reviewed: tên các ảnh người đã duyệt
    hold_threshold = cfg["gate"]["warn_ratio_hold"]
    image_names = set(image_stems)
    reviewed_images = set(reviewed)

    # Lỗi bắt buộc: đếm TẤT CẢ, kể cả lỗi cấp dataset (data.yaml) và ảnh đã duyệt — không bao giờ bỏ qua
    error_count = sum(1 for issue in issues if issue.severity == ERROR)

    # Ảnh còn cảnh báo: chỉ tính ảnh thuộc dataset và chưa được người duyệt; mỗi ảnh đếm một lần
    images_with_warnings = {
        issue.image for issue in issues
        if issue.severity == WARN and issue.image in image_names and issue.image not in reviewed_images
    }
    image_count = len(image_names)
    warn_image_count = len(images_with_warnings)
    warn_ratio = round(warn_image_count / image_count, 4) if image_count > 0 else 0.0

    if error_count > 0:
        decision = "Rework"
        reasons = [f"còn {error_count} lỗi bắt buộc chưa sửa: phải sửa rồi chạy lại"]
    elif warn_ratio >= hold_threshold:
        decision = "Hold"
        reasons = [f"không còn lỗi bắt buộc, nhưng {warn_image_count}/{image_count} ảnh ({warn_ratio:.1%}) "
                   f"còn cảnh báo chưa người duyệt, >= ngưỡng {hold_threshold:.0%}"]
    else:
        decision = "Release"
        reasons = [f"không còn lỗi bắt buộc; {warn_image_count}/{image_count} ảnh ({warn_ratio:.1%}) "
                   f"còn cảnh báo chưa duyệt, < ngưỡng {hold_threshold:.0%}"]

    return {
        "decision": decision,
        "n_errors": error_count,
        "n_warn_images": warn_image_count,
        "n_images": image_count,
        "warn_ratio": warn_ratio,
        "reasons": reasons,
    }
