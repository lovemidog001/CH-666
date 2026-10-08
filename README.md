# ODDITY HUB / CH-666

> 怪聞局 · 虛構恐怖電視頻道 · 每日更新原創怪談

[![Deploy Status](https://github.com/your-org/oddity-hub/actions/workflows/daily-generation.yml/badge.svg)](https://github.com/your-org/oddity-hub/actions)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## 專案簡介

ODDITY HUB 是一個原創恐怖故事網站，核心頻道 **CH-666** 是一個虛構的深夜恐怖電視頻道。

## 目錄結構

```
.
├── .github/
│   └── workflows/
│       └── daily-generation.yml     # 每日自動生成 workflow
├── content/                          # GitHub 內容儲存 (版本控管)
│   ├── config/
│   │   ├── ai-providers.json        # AI Provider 設定
│   │   └── generation.json          # 每日產出設定
│   ├── stories/                      # 完成故事 JSON
│   ├── seeds/                        # Story Seeds & 原始新聞
│   ├── channels/                     # 頻道索引
│   └── logs/                         # 每日執行日誌
├── public_html/                      # Serv00 部署根目錄
│   ├── index.php                     # 前端控制器
│   ├── 0.html                        # CRT 開場動畫
│   ├── config.php                    # 站台設定
│   ├── .htaccess                     # Apache 設定
│   ├── database.sqlite               # SQLite 資料庫 (自動建立)
│   ├── api/
│   │   ├── update.php               # GitHub 更新端點
│   │   ├── stories.php              # 故事 API
│   │   └── ads.php                  # 廣告 API
│   ├── admin/                        # 後台管理
│   │   ├── router.php
│   │   ├── login.php
│   │   ├── stories.php
│   │   ├── story_create.php
│   │   ├── story_edit.php
│   │   ├── ads.php
│   │   └── ad_slots.php
│   ├── includes/
│   │   ├── Database.php             # PDO 單例
│   │   ├── functions.php            # 共用函數
│   │   ├── schema.sql               # 資料庫結構
│   │   ├── init_db.php              # 資料庫初始化
│   │   ├── header.php
│   │   └── footer.php
│   ├── pages/                        # 前端頁面
│   │   ├── home.php                 # 首頁 (INDEX)
│   │   ├── story.php                # 故事詳情
│   │   ├── channel.php              # 頻道列表
│   │   ├── archive.php              # 歸檔
│   │   ├── search.php               # 搜尋
│   │   ├── about.php                # 關於
│   │   ├── contact.php              # 聯繫
│   │   └── 404.php
│   ├── css/
│   │   ├── main.css                 # 主樣式
│   │   └── 0.css                    # 開場動畫樣式
│   ├── js/
│   │   ├── main.js                  # 主腳本
│   │   └── 0.js                     # 開場動畫腳本
│   └── images/                       # 靜態圖片
├── scripts/                          # 生成管線腳本
│   ├── load_config.py
│   ├── check_enabled.py
│   ├── fetch_news.py
│   ├── process_news.py
│   ├── generate_stories.py
│   ├── save_stories.py
│   ├── notify_serv00.py
│   └── generate_log.py
└── docs/
    └── DEPLOYMENT.md                # 部署說明
```

## 授權

MIT License - 詳見 [LICENSE](LICENSE)

