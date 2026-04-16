# 🛒 Retail Object Tracking System

Hệ thống tracking người và vật thể trong môi trường bán lẻ sử dụng YOLO11 và BoTSORT/ByteTrack.

## 📋 Mục lục
- [Tính năng](#-tính-năng)
- [Cấu trúc thư mục](#-cấu-trúc-thư-mục)
- [Yêu cầu hệ thống](#-yêu-cầu-hệ-thống)
- [Cài đặt](#-cài-đặt)
- [Sử dụng](#-sử-dụng)
- [Cấu hình](#-cấu-hình)

---

## ✨ Tính năng

- ✅ Phát hiện và tracking đối tượng real-time
- ✅ Hỗ trợ nhiều thuật toán tracking: BoTSORT, ByteTrack
- ✅ Filter theo class (person, car, v.v.)
- ✅ Xuất metadata tracking sang JSON Lines (.jsonl)
- ✅ Hỗ trợ GPU (CUDA) và CPU
- ✅ Nhiều mô hình YOLO11 (nano → xlarge)

---

## 📁 Cấu trúc thư mục

```
retail/
├── data/                    # Video đầu vào
│   ├── video.mp4
│   └── ...
│
├── detect/                  # Module phát hiện đối tượng
│   ├── models/              # Các file weight YOLO (.pt)
│   │   ├── yolo11n.pt       # nano (nhanh nhất, nhẹ nhất)
│   │   ├── yolo11s.pt       # small
│   │   ├── yolo11m.pt       # medium
│   │   ├── yolo11l.pt       # large (khuyên dùng)
│   │   └── yolo11x.pt       # xlarge (chính xác nhất)
│   ├── coco_classes.txt     # Danh sách 80 class COCO
│   └── yolo_detector.py     # Class YoloDetector
│
├── ingest/                  # Module đọc video
│   └── CVSource.py          # Đọc video từ file/camera
│
├── track/                   # Module tracking
│   ├── config/              # YAML config cho tracker
│   │   ├── botsort.yaml
│   │   └── bytetrack.yaml
│   ├── yolo_tracker_base.py      # Base class cho tracker
│   ├── yolo_tracker_botsort.py   # Tracker sử dụng BoTSORT
│   ├── yolo_tracker_bytetrack.py # Tracker sử dụng ByteTrack
│   ├── deepsort_tracker.py       # Tracker sử dụng DeepSORT
│   └── tracker_factory.py        # Factory tạo tracker
│
├── emit/                    # Module xuất metadata
│   └── json_emitter.py      # Ghi tracking results sang JSONL
│
├── metadata/                # Thư mục lưu output JSONL
│   └── video.jsonl
│
├── main.py                  # Script chính để chạy tracking
├── setup.txt                # Dependencies
├── README.md                # File này
└── AGENTS.md                # Coding rules cho agents
```

---

## 💻 Yêu cầu hệ thống

### Phần cứng
- **CPU**: Intel/AMD 4+ cores
- **RAM**: 8GB+ (16GB khuyến nghị)
- **GPU** (tùy chọn): NVIDIA GPU với CUDA 12.4+
  - Ví dụ: RTX 3060, RTX 4070, v.v.

### Phần mềm
- **Python**: 3.9 - 3.11 (khuyên dùng 3.10)
- **CUDA Toolkit**: 12.4 (nếu dùng GPU)
- **Git**: Để clone repo

---

## 🚀 Cài đặt

### Bước 1: Clone repository

```bash
git clone https://github.com/CongDon1207/retail_tracking_object.git
cd retail_tracking_object
```

### Bước 2: Tạo môi trường ảo Python

**Windows (PowerShell/CMD):**
```bash
python -m venv venv
venv\Scripts\activate
```

**Linux/macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### Bước 3: Nâng cấp pip và công cụ build

```bash
python -m pip install --upgrade pip wheel setuptools
```

### Bước 4: Cài đặt dependencies

```bash
pip install -r setup.txt
```

**Lưu ý:** 
- File `setup.txt` đã cấu hình PyTorch với CUDA 12.4
- Nếu dùng **CPU only**, sửa trong `setup.txt`:
  ```
  torch==2.4.1
  torchvision==0.19.1
  ```

### Bước 5: Tải các model YOLO11

Truy cập trang chính thức Ultralytics và tải model:
- 🔗 [https://docs.ultralytics.com/models/yolo11/](https://docs.ultralytics.com/models/yolo11/)

**Các model khả dụng:**

| Model | Size | Speed | Accuracy | Khuyến nghị |
|-------|------|-------|----------|-------------|
| yolo11n.pt | 2.6 MB | ⚡⚡⚡⚡⚡ | ⭐⭐ | Demo nhanh |
| yolo11s.pt | 9.4 MB | ⚡⚡⚡⚡ | ⭐⭐⭐ | Edge devices |
| yolo11m.pt | 20 MB | ⚡⚡⚡ | ⭐⭐⭐⭐ | Cân bằng |
| yolo11l.pt | 25 MB | ⚡⚡ | ⭐⭐⭐⭐⭐ | **Khuyến nghị** |
| yolo11x.pt | 56 MB | ⚡ | ⭐⭐⭐⭐⭐ | Độ chính xác tối đa |

**Đặt file .pt vào thư mục:**
```
detect/models/yolo11l.pt
```

### Bước 6: Chuẩn bị video test

Đưa video vào thư mục `data/`:
```
data/video.mp4
data/video2.mp4
```

Hoặc dùng video có sẵn trong project (nếu có).

---

## 🎯 Sử dụng

### Chạy tracking cơ bản

```bash
python main.py
```

### Tùy chỉnh trong `main.py`

```python
# --- Cấu hình ---
model_name = "yolo11l.pt"           # Model YOLO sử dụng
video_path = "data/video2.mp4"      # Đường dẫn video
tracker_type = "botsort"            # "botsort" hoặc "bytetrack"
class_filter = [0]                  # [0] = chỉ track người

# Để track nhiều class:
# class_filter = [0, 2, 5]  # person(0), car(2), bus(5)

# Để track tất cả:
# class_filter = None
```

### Đầu ra (Output)

1. **Cửa sổ hiển thị real-time:**
   - Bounding box màu xanh lá
   - Label: `person ID:1 0.95`

2. **File JSONL** (metadata):
   ```
   metadata/video2.jsonl
   ```
   Mỗi dòng là 1 frame với thông tin tracking đầy đủ.

### Dừng chương trình

Nhấn phím `q` trong cửa sổ video để thoát.

---

## ⚙️ Cấu hình

### COCO Classes phổ biến

| Class ID | Tên | Mô tả |
|----------|-----|-------|
| 0 | person | Người |
| 1 | bicycle | Xe đạp |
| 2 | car | Ô tô |
| 5 | bus | Xe buýt |
| 7 | truck | Xe tải |
| 24 | backpack | Ba lô |
| 26 | handbag | Túi xách |
| 39 | bottle | Chai/Lọ |

Xem đầy đủ 80 classes trong `detect/coco_classes.txt`

### So sánh Tracker

| Tracker | Tốc độ | Độ chính xác | Khuyến nghị |
|---------|--------|--------------|-------------|
| ByteTrack | ⚡⚡⚡⚡ | ⭐⭐⭐ | Real-time app |
| BoTSORT | ⚡⚡⚡ | ⭐⭐⭐⭐⭐ | **Khuyến nghị** |

### Cấu hình tracker (YAML)

File config trong `track/config/`:
- `botsort.yaml`: Cấu hình BoTSORT
- `bytetrack.yaml`: Cấu hình ByteTrack

Tham khảo docs Ultralytics để tùy chỉnh nâng cao.

DeepSORT (tinh chỉnh nhanh qua ENV):
- Chọn `tracker_type = "deepsort"` trong `main.py`.
- Biến môi trường hỗ trợ (mặc định tối ưu camera tĩnh, occlusion ~1–3s):
  - `DS_MAX_AGE` (mặc định 90)
  - `DS_N_INIT` (mặc định 3)
  - `DS_MAX_IOU_DISTANCE` (mặc định 0.7)
  - `DEEPSORT_EMBEDDER` = `mobilenet` | `torchreid` (mặc định mobilenet)
  - `DEEPSORT_EMBEDDER_GPU` = 1|0 (mặc định 1)
  - `DS_DET_CONF` (mặc định lấy từ code, ~0.2–0.25)
- Ví dụ (Linux/macOS):
  - `export DS_MAX_AGE=120 DS_N_INIT=3 DS_MAX_IOU_DISTANCE=0.75 DEEPSORT_EMBEDDER=torchreid DS_DET_CONF=0.2`

Gợi ý cho camera tĩnh & đông người (giảm ID nhảy qua occlusion):
- BoT-SORT + ReID: bật `with_reid: True` và ưu tiên `model: auto` để dùng đặc trưng native của YOLO (Ultralytics). Nếu chỉ định model riêng, dùng file YOLO `.pt` hợp lệ, không dùng `.pth`.
- Tăng thời gian giữ track: `track_buffer: 90`
- Siết matching vừa phải: `track_high_thresh: 0.4`, `match_thresh: 0.75`
- Camera tĩnh: `gmc_method: none`

---

## 🔧 Troubleshooting

### Lỗi: CUDA không khả dụng

```bash
# Kiểm tra CUDA
python -c "import torch; print(torch.cuda.is_available())"
```

Nếu `False`, cài đặt lại PyTorch với CUDA 12.4 hoặc dùng CPU.

### Lỗi: Không tìm thấy model

Đảm bảo file `.pt` nằm đúng trong `detect/models/`:
```
detect/models/yolo11l.pt  ✅
detect/yolo11l.pt         ❌
yolo11l.pt                ❌
```

### Lỗi: Thiếu dependencies

```bash
pip install -r setup.txt --force-reinstall
```

---

## 📝 License

MIT License - Xem file LICENSE để biết thêm chi tiết.

---

## 👥 Contributors

- **CongDon1207** - Initial work

---

## 📧 Liên hệ

- GitHub: [@CongDon1207](https://github.com/CongDon1207)
- Issues: [GitHub Issues](https://github.com/CongDon1207/retail_tracking_object/issues)

---

**Happy Tracking! 🎉**
