# Báo cáo Day 09 — Đặng Trung Hiếu, 2A202603248

## 1. Kết luận trước
**HOLD** (mã thoát 10). Vào 224 ảnh → cửa vào loại 22 → ra **202 ảnh** ở `submission/export/clean_v1/` (bản nháp, **chưa phát hành**).
Không còn lỗi bắt buộc (`n_errors = 0`), nhưng **38/202 ảnh (18.8%)** còn cảnh báo chưa người duyệt, ≥ ngưỡng 10%:
hàng đợi có 125 ảnh mà ngân sách duyệt chỉ 80 ảnh (`08_summary.json`).

## 2. Lỗi và phân việc
Từ `01_intake` (mẫu số 224 ảnh) và `02_error_list_v1` (mẫu số 202 ảnh sau cửa vào); sửa máy lấy từ `03_fixes.csv`.

| Mã lỗi | Số ảnh/dòng | Ai sửa (máy/người) | Vì sao |
|---|---:|---|---|
| `CORRUPT_IMAGE` | 2/224 ảnh | máy: loại ảnh | ảnh cắt cụt (vd. `img_0010` chỉ 4 096 byte) không đọc được |
| `BAD_SIZE` | 3/224 ảnh | máy: loại ảnh | cạnh ngắn < 250 px, quy tắc dự án |
| `DUP_IMAGE_EXACT` | 8/224 ảnh | máy: loại ảnh | trùng md5, chắc chắn 100% |
| `DUP_IMAGE_NEAR` | 4/224 ảnh | máy: loại ảnh | phash ≤ 12 (đã mở xem: đổi sáng, cắt khung) |
| `LEAK_TEST` | 5/224 ảnh | máy: loại ảnh | trùng ảnh test/val → làm đo test sai |
| `BAD_CLASS_NAME` | 2 dòng `data.yaml` | máy: `rename_classes` | `Person`, `Bus` viết hoa sai |
| `BAD_FORMAT` / `BAD_CLASS_ID` / `BOX_ZERO` / `DUP_BOX` | 3 / 6 / 4 / 7 dòng | máy: `drop_line` (20 dòng) | sai cú pháp, không thể đoán giá trị đúng → xoá dòng |
| `BOX_OUT_OF_IMAGE` | 8 dòng | máy: `clip_box` (8) | cắt về [0,1], giữ lớp |
| `MISSING_LABEL_FILE` | 6/202 ảnh | **người**: gán nhãn (`needs_label`) | máy không bịa nhãn; không tạo file rỗng |
| `POSSIBLE_MISSING` | 53 cờ / 52 ảnh | **người** | lỗi ngữ nghĩa, model chỉ nghi ngờ |
| `POSSIBLE_WRONG_CLASS` | 18 / 18 ảnh | **người** | vd. `img_0020`: xe buýt gán `truck` |
| `POSSIBLE_LOOSE_BOX` | 28 / 24 ảnh | **người** | box lệch/lỏng |
| `POSSIBLE_FALSE_POS` | 29 / 27 ảnh | **người** | box không khớp vật nào model thấy |
| `EMPTY_LABEL`, `BOX_TINY`, `BOX_HUGE`, `CLASS_RARE` | 12 ảnh / 6 dòng / 3 / 4 | **người** | cảnh báo quy tắc: cần mắt người quyết định |

**Hàng đợi** (`05_review_queue.csv`, 125 ảnh) xếp theo điểm = trọng số mã × (1 + conf). Đầu hàng là `img_0020` (11.5: đã bị xoá dòng + MISSING + WRONG_CLASS),
rồi 6 ảnh `NEEDS_LABEL` (trọng số 10: chưa có nhãn là lỗi bắt buộc, không ai khác gán được), sau đó các ảnh WRONG_CLASS/MISSING conf cao.
Với ngân sách 80 ảnh, người duyệt xem 74 ảnh có cờ ngữ nghĩa (50 MISSING, 18 WRONG_CLASS, 8 LOOSE_BOX, 12 FALSE_POS) + 6 ảnh cần gán.
Sau duyệt (v2 → v3): ảnh có MISSING 52 → 12, WRONG_CLASS 18 → 3. Phần không ai xem (45 ảnh cuối hàng) chủ yếu là LOOSE_BOX (16) và FALSE_POS (11),
vì trọng số thấp hơn.

## 3. Calibration (2 ngưỡng)
| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | **12** | NEAR 1.00/0.50 → 1.00/0.67 (EXACT giữ 1.00/1.00) | lỗi này **xoá ảnh** nên ưu tiên precision. Trên dữ liệu thật: cặp ảnh khác nhau (test+val, 9 730 cặp) cách nhau **≥ 16**; ảnh trùng thật ở raw cách 2, 6, 10. Chọn 12 nằm giữa khoảng trống, cách 16 một biên 4. So với 2: bắt thêm `img_0223` (6), `img_0186` (10) và `img_0101` (6, **rò rỉ test** `test_039`) |
| `second_opinion.conf` | 0.25 | **0.6** | MISSING 0.50/1.00 → 0.57/1.00; WRONG_CLASS 0.56/0.83 → 0.62/0.83 | cảnh báo cho người nên ưu tiên recall: 0.6 là mức **cao nhất chưa mất recall**. 0.7 làm MISSING tụt 0.88, 0.8 tụt 0.75. Hàng đợi 143 → 125 ảnh |

**Calibration có thể đánh lừa:** trên calib, `phash_dist = 16` cho F1 của NEAR cao nhất (0.91). Nhưng trên raw, ở khoảng cách 16 có 12 ảnh
mà mình mở ra thì là ảnh **khác hẳn** (vd. `img_0008` trượt tuyết ~ `img_0011` tennis; `img_0013` bàn laptop ~ `test_087` bóng chày).
Chọn 16 sẽ xoá nhầm ~12 ảnh tốt, 6 ảnh bị gán `LEAK_TEST` sai. Calib **không có ca LEAK_TEST** nên bảng sweep không thấy được điều này
(chỉ thấy gián tiếp: ở 20, recall EXACT tụt 0.33 vì ảnh bị báo LEAK trước). Tương tự `conf = 0.8` cho kết luận Release (7.9%)
chỉ vì checker bỏ sót 25% ca thiếu box: đó là Release giả, nên không chọn.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được
**(a) Gate chặn thật.** `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb`:
không có người duyệt nên 6 ảnh `MISSING_LABEL_FILE` vẫn chưa có nhãn → log ghi
`kết luận: REWORK — còn 6 lỗi bắt buộc chưa sửa`, `KHÔNG xuất: còn lỗi bắt buộc (Rework)`, **mã thoát 20**, thư mục `work/exp_nb/clean_v1` **không tồn tại**.
Gate đếm lỗi bắt buộc trên mọi ảnh, kể cả ảnh đã duyệt: người duyệt không thể "cho qua" lỗi bắt buộc.

**(b) Điểm mù (có bằng chứng):**
1. **Box lỏng nhẹ:** `POSSIBLE_LOOSE_BOX` trên calib chỉ P 0.20 / R 0.20 (bắt 1/5) ở mọi `conf` ≥ 0.4; trên raw 16 ảnh LOOSE nằm ngoài ngân sách duyệt.
   Box lỏng gần như lọt vào dataset.
2. **Ảnh trùng biến đổi mạnh:** NEAR recall 0.67 (bỏ sót 2/6 trên calib). Muốn bắt thì phải tăng `phash_dist` ≥ 16, khi đó xoá nhầm ảnh khác nhau (mục 3).
3. **Model cũng có thể sai:** WRONG_CLASS bỏ sót 1/6 trên calib; FALSE_POS precision chỉ 0.31 (11 báo động giả / 16 cờ). Sau khi người thay nhãn,
   v3 vẫn còn 3 WRONG_CLASS và 21 FALSE_POS trên ảnh **đã duyệt**, tức model bất đồng với nhãn người. Vì vậy `second_opinion` chỉ được cảnh báo.
4. **Sửa đúng cú pháp vẫn tạo lỗi ngữ nghĩa:** `img_0050` chỉ có 1 box rộng 0 → autofix xoá dòng → ảnh có người lướt sóng mà không còn nhãn
   (chỉ được cứu nhờ `POSSIBLE_MISSING` + người duyệt). `img_0030` dòng 9 bị `clip_box` còn rộng ~10 px.

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
Colab T4, `scripts/train_compare.py`: yolo26n.pt, 20 epoch, imgsz 640, batch 16, seed 0 và 1; cùng val (`gold_val`, 40 ảnh) và cùng test (100 ảnh).
`manifest_sha1 = 4975b2b…` khớp export đã push; `config_sha1 = 58d1755…` khớp `08_summary.json`. Bảng từ `submission/results/comparison.md`:

| biến thể | #ảnh train | số seed | map50 (TB ± độ lệch) | map50_95 (TB ± độ lệch) | precision (TB ± độ lệch) | recall (TB ± độ lệch) |
|---|---|---|---|---|---|---|
| raw | 224 | 2 | 0.726 ± 0.000 | 0.512 ± 0.004 | 0.764 ± 0.061 | 0.649 ± 0.028 |
| clean | 202 | 2 | 0.701 ± 0.025 | 0.487 ± 0.008 | 0.759 ± 0.003 | 0.625 ± 0.019 |

Chênh mAP50 (clean − raw) = **−0.025**. AP50 theo lớp (TB 2 seed): car 0.738 → 0.738, person 0.822 → 0.823, bus 0.695 → 0.703, **truck 0.648 → 0.538**.

**Kết luận (trung thực): chưa kết luận được clean tốt hơn raw.** Chênh mAP50 −0.025 bằng đúng độ lệch giữa 2 seed của clean (0.683 và 0.718), tức nằm trong nhiễu;
raw có độ lệch 0.000 chỉ là trùng hợp của 2 seed, không phải raw ổn định hơn. mAP50-95 thấp hơn 0.025 (≈ 3× độ lệch), gợi ý raw nhỉnh hơn nhẹ,
nhưng 2 seed và 100 ảnh test chưa đủ để khẳng định. Toàn bộ chênh lệch đến từ lớp **truck**; 3 lớp còn lại gần như bằng nhau.

**Giả thuyết và cách kiểm:**
1. **Rò rỉ test thổi phồng raw:** raw chứa 5 ảnh trùng tập test (`test_009, 033, 039, 044, 085`, `01_intake`), model raw đã "thấy" 5/100 ảnh test lúc train.
   Kiểm: đánh giá lại cả hai model trên test bỏ 5 ảnh đó.
2. **Truck ít mẫu nên nhiễu lớn:** test chỉ có 24 box truck, train có 32 (raw) / 41 (clean). Clean có nhiều truck hơn và ít car hơn (122 → 101),
   do người duyệt sửa car↔truck. Vài dự đoán đổi là AP truck dao động mạnh. Kiểm: chạy ≥ 5 seed; xem AP truck từng seed; mở ảnh test có truck.
3. **Clean vẫn còn nhãn nhiễu:** 38 ảnh còn cảnh báo chưa ai duyệt (mục 1), chủ yếu LOOSE_BOX/FALSE_POS. Ngoài ra Ultralytics tự bỏ dòng hỏng của raw khi train,
   nên lợi thế "sạch cú pháp" của clean nhỏ hơn mong đợi. Kiểm: thêm biến thể `oracle` (nhãn người, chặn trên) để xem dữ liệu sạch hơn có thật sự giúp không.
4. **Clean ít ảnh hơn (202 so với 224):** 13 ảnh trùng bị loại gần như không mang thông tin mới, nhưng vẫn là thêm lượt nhìn cho model.

**Việc tiếp theo:** đánh giá lại trên test bỏ 5 ảnh rò rỉ; tăng lên ≥ 5 seed; chạy `oracle`; duyệt nốt 38 ảnh còn cảnh báo rồi train lại.

## 6. Quyết định và ghi chú AI
**(a)** Quyết định: **Hold**. Không còn lỗi bắt buộc, nhưng 38/202 ảnh còn cảnh báo chưa ai xem.
Điều kiện để thành Release: tỉ lệ < 10%, tức còn ≤ 20 ảnh cảnh báo chưa duyệt → cần duyệt thêm **~18 ảnh** theo thứ tự hàng đợi
(ngân sách ~100 ảnh), hoặc người kiểm tra 16 ảnh LOOSE_BOX + 11 ảnh FALSE_POS cuối hàng. **Không** hạ `conf` lên 0.8 để Release (mục 3).

**(b) Dùng AI (Claude Code) để viết code:**
- *Prompt chính:* cho AI đọc docstring + test của từng module, yêu cầu viết dễ hiểu, không over-engineer, tên biến có nghĩa; đầu vào/đầu ra/ràng buộc lấy từ docstring.
- *Cách kiểm:* chạy `pytest` từng module (79/79 xanh), rồi chạy trên `data/raw` (bản sao) và đối chiếu với lỗi tự thấy bằng `viz_labels.py`
  (`img_0001` DUP_BOX + MISSING, `img_0020` id 93 + bus→truck, `img_0050` BOX_ZERO); kiểm autofix chạy lần 2 chỉ còn `needs_label` (idempotent); đọc hiểu từng dòng.
- *Một lần AI sai:* bản đầu `label_format` đặt tên biến viết tắt (`cx, cy, w, h, stem`), khó đọc và khó giải thích; mình yêu cầu đổi sang `center_x`, `box_width`, `image_name`…
  Ngoài ra nếu chỉ nhìn bảng sweep thì F1 cao nhất ở `phash_dist = 16`; phải đo trên raw và mở ảnh mới thấy 16 xoá nhầm ảnh.

## Thưởng: check mới `aspect_ratio` (box lệch tỉ lệ khung hình)
`pipeline/checks/aspect_ratio.py` + `tests/test_aspect_ratio.py` (9 test xanh; `pytest` tổng 88/88). Cảnh báo `BOX_ODD_ASPECT` khi cạnh dài / cạnh ngắn
(tính theo **pixel**) > 5.0, kèm `touches_edge` (box chạm mép ảnh, có thể là vật bị cắt). Chạy: `python -m pipeline.checks.aspect_ratio data/raw`.
- **Chọn ngưỡng:** nhãn người của calib có tỉ lệ lớn nhất 4.0 → ngưỡng 5.0 cho **0 cờ trên calib** (39 ảnh, 115 box); trên raw cờ **11/719 box**.
- **Kết quả (mở xem bằng `viz_labels.py`):** 9/11 box chạm mép là người bị cắt khung (hợp lệ, vd. `img_0042:5`). Trong 2 box không chạm mép,
  `img_0062:1` là **lỗi thật**: box bao cả người lẫn bóng phản chiếu dưới nước (cao gấp đôi); `img_0091:8` là người bị che khuất (hợp lệ).
  Sau khi người duyệt sửa `img_0062`, model vẫn coi bóng nước là người (`POSSIBLE_MISSING` conf 0.64 ở v3): thêm bằng chứng model có thể sai.
- **Vì sao chưa gắn vào `make run`:** `pipeline/checks/__init__.py` và `configs/pipeline.yaml` bị ghim (không được sửa), nên check chạy riêng;
  ngưỡng đọc `cfg["aspect_ratio"]["max_ratio"]` nếu có, mặc định là hằng số có tên `DEFAULT_MAX_RATIO`. Nhờ vậy báo cáo pipeline và kết quả train không đổi.

*(Thưởng CVAT: không làm.)*
