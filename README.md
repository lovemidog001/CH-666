# CH-666 怪聞局 - 自動怪談生成系統

> **Version: 2.0.0** (2026-10-09) — 統一 3/6/9 頻道，單一工作流重構版

---

## 📋 版本歷程

| 版本 | 日期 | 重點更新 |
|------|------|----------|
| **2.0.0** | 2026-10-09 | 🔄 完全重構：統一 CH-3/6/9 為單一頻道、單一工作流、決定性骰子分配、即時儲存、失敗閾值保護 |
| 1.x | 2026-10-08 | 多頻道矩陣任務、獨立計數器、舊驗證邏輯、Agnes 圖片整合 |

---

## 🏗 系統架構

```
GitHub Actions (每日 03:05 / 15:05 UTC)
         │
         ▼
┌──────────────────────────────────────┐
│ main.py (Orchestrator)               │
├──────────────────────────────────────┤
│ 1. fetch_news  →  NewsAPI (最近3天)   │
│ 2. classify    →  Seed + Dice Roll   │
│ 3. generate    →  AI Story JSON      │
│ 4. validate    →  Schema + Category  │
│ 5. images      →  Agnes → WebP → FTP │
│ 6. storage     →  JSON + daily merge │
│ 7. notify      →  POST serv00        │
└──────────────────────────────────────┘
```

---

## 📁 專案結構

```
CH-666/
├── .github/workflows/daily.yml        # 單一工作流 (排程 + 手動)
├── config/
│   ├── generation.json                # enabled, articles_per_day: 6
│   ├── providers.json                 # 4 AI Providers (優先級排序)
│   └── channels.json                  # 3/6/9 類別定義 (horror_types, fantasy_levels, etc.)
├── scripts/
│   ├── config.py                      # 統一配置載入器
│   ├── fetch_news.py                  # 新聞抓取 + 去重
│   ├── classify.py                    # Seed 建立 + 類別分配 + DiceRoller
│   ├── generate.py                    # AI 生成 (Provider fallback + retry)
│   ├── validate.py                    # JSON Schema + 類別規則驗證
│   ├── images.py                      # Agnes Image 2.5 Flash + FTP
│   ├── storage.py                     # 儲存故事 / prompts / daily 合併
│   ├── notify.py                      # POST 完整故事到 serv00
│   ├── determine_date.py              # 目標日期邏輯
│   ├── load_config.py                 # Workflow 輸出 GITHUB_OUTPUT
│   └── main.py                        # 總協調器
├── requirements.txt
└── content/                           # Git 追蹤輸出
    ├── stories/CH-{3|6|9}-XXXX.json
    ├── prompts/
    └── daily/YYYY-MM-DD.json + latest.json
```

---

## 🔄 核心流程邏輯

### 每日產出：6 篇故事 (dice 分布)
- 類別分配：`MD5(seed_id + event_hash) % 3` → 3 / 6 / 9
- 可能分布：`0/2/4`、`3/1/2`、`1/1/4` 等自然分布

### 骰子系統 (決定性)
| 參數 | 規則 |
|------|------|
| **Horror Score** | reality >70: 20-55 / 40-70: 40-75 / <40: 60-95 |
| **Horror Type** | 從類別允許清單抽 1-3 個 |
| **Fantasy Level** | 從類別允許清單抽 1 個 |
| **其他** | narrative_style, pacing, ending, perspective 同理 |

### 失敗保護機制
```python
MAX_CONSECUTIVE_FAILURES = 3      # 連續 3 次失敗 → 跳過該類別剩餘
MAX_CATEGORY_FAILURE_RATE = 0.8   # 失敗率 >80% → 跳過該類別剩餘
# 單一類別全失敗 → 繼續下一類別
# 三類別全 0 生成 → sys.exit(1) (Actions 紅叉)
```

---

## 🎭 三大頻道定義 (config/channels.json)

| 代碼 | 名稱 | 類型 | 色調 | 核心 Horror Types |
|------|------|------|------|-------------------|
| **3** | CH-333 靈頻頻道 | occult | #ff6b35 | possession, haunting, ritual, curse, mediumship... |
| **6** | CH-666 怪聞頻道 | anomalous | #00ff88 | psychological, urban_legend, supernatural, crime... |
| **9** | CH-999 禁忌頻道 | forbidden | #ff0044 | cognitive_hazard, memetic, ontological, cosmic... |

> 前端可直接讀取 `channels.json` 做 UI mapping (label, color, description)

---

## 🖼 圖片生成

- **模型**: Agnes Image 2.5 Flash (專為恐怖風格調教)
- **輸出**: WebP 1024px, quality=85
- **兩張/篇**: `cover` (封面) + `scene` (關鍵場景)
- **上傳**: FTP → `{FTP_PATH}/CH-{3|6|9}-XXXX_cover.webp`
- **公開 URL**: `{SITE_URL}/images/CH-{3|6|9}-XXXX_cover.webp`

---

## 📦 輸出格式 (Story JSON)

```json
{
  "story_code": "CH-3-0001",
  "category": "3",
  "channel": "CH-333",
  "title": "七號公路的後照鏡——我錄下了自己消失的過程",
  "subtitle": "CH-333 檔案 // 鏡中出現非當事人影子",
  "slug": "zone-three-highway-rearview-mirror-disappearance",
  "summary": "深夜巡邏員連續七次回報同一輛廢棄車輛...",
  "content": "完整故事內容 (≥1500字，繁體中文，偽紀錄格式)...",
  "horror_score": 67,
  "horror_type": ["haunting", "surveillance_horror"],
  "fantasy_level": "supernatural",
  "narrative_style": "found_footage",
  "pacing": "slow_burn",
  "ending_type": "open",
  "perspective": "witness",
  "source_date": "2026-10-08",
  "source_hash": "abc123def456",
  "event_hash": "evt789xyz",
  "source_url": "https://news.example.com/...",
  "provider_used": "agnes",
  "dice_seed": 1234567890,
  "director_analysis": {},
  "created_at": "2026-10-09T03:05:00Z",
  "cover_image": "https://ailoom.ccwu.cc/images/CH-3-0001_cover.webp",
  "scene_images": "https://ailoom.ccwu.cc/images/CH-3-0001_scene.webp"
}
```

---

## ⚙️ GitHub Secrets (10 個必填)

| Secret | 用途 |
|--------|------|
| `NEWSAPI_KEY` | NewsAPI.org 抓新聞 |
| `NVIDIA_API_KEY` / `OPENAI_API_KEY` / `GOOGLE_API_KEY` / `AGNES_API_KEY` | 文字生成 (至少一組) |
| `AGNES_API_KEY` | **圖片生成專用** (必要) |
| `SERV00_UPDATE_URL` | `https://ailoom.ccwu.cc/api/update.php` |
| `SERV00_UPDATE_TOKEN` | Bearer Token |
| `FTP_HOST` / `FTP_USER` / `FTP_PASS` / `FTP_PATH` | 圖片 FTP 上傳 |
| `SITE_URL` | `https://ailoom.ccwu.cc` (圖片公開網址前綴) |

---

## 🚀 部署與觸發

### 自動排程
- **03:05 UTC** (11:05 CST) — 針對前一日新聞
- **15:05 UTC** (23:05 CST) — 補抓/備援

### 手動觸發
```
GitHub Actions → Daily CH-666 Generation → Run workflow
  → Mode: generate
  → Count override: 6 (或自訂總篇數)
```

---

## 🔧 serv00 端必要修改

**`public_html/api/update.php`** (約第 60 行)
```php
// 舊: if (!preg_match('/^CH-666-\d{4}$/', $story['story_code']))
// 新:
if (!preg_match('/^CH-[369]-\d{4}$/', $story['story_code']))
```

**`public_html/admin/sync.php`** (約第 150 行)
```php
// 舊: preg_match('/^CH-666-\d{4}\.json$/', $f['name'])
// 新:
preg_match('/^CH-[369]-\d{4}\.json$/', $f['name'])
```

---

## 🛠 本地開發

```bash
# 安裝依賴
pip install -r requirements.txt

# 設定環境變數 (.env 或 export)
export NEWSAPI_KEY=xxx
export NVIDIA_API_KEY=xxx
export AGNES_API_KEY=xxx
export SERV00_UPDATE_URL=https://ailoom.ccwu.cc/api/update.php
export SERV00_UPDATE_TOKEN=xxx
export FTP_HOST=xxx
export FTP_USER=xxx
export FTP_PASS=xxx
export FTP_PATH=/public_html/images/
export SITE_URL=https://ailoom.ccwu.cc

# 執行 (產生 6 篇)
python scripts/main.py \
  --date 2026-10-09 \
  --count 6 \
  --config config/generation.json \
  --providers config/providers.json \
  --channels config/channels.json \
  --content-dir content
```

---

## 📝 設計決策摘要

| 決策 | 理由 |
|------|------|
| **單一工作流序列處理** | 避免 matrix 3 parallel jobs 資源浪費、日誌混亂 |
| **故事代碼 `CH-{3|6|9}-XXXX`** | 類別可從代碼直接解析，無需查 DB |
| **決定性亂數 (MD5 seed)** | 同一 seed 永遠產生相同參數，可重現、可除錯 |
| **分類由骰子決定** | 符合「投骰子分配」需求，自然分布 |
| **Agnes 專用圖片 API** | 風格一致 (negative prompt)、品質穩定 |
| **即時儲存 + 合併 daily** | 部分成功不丟失、前端讀取 `daily/latest.json` 即可 |

---

## 📄 授權

Internal use only — ODDITY HUB / CH-666 怪聞局

---

*Last updated: 2026-10-09 | Version 2.0.0*