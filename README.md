# Plano Supply Desk — Python V1

手機與桌機自適應的美國 Plano 水管材料採購概念驗證。

## 本機開啟

安裝 Python 3.12 或以上，解壓後在此資料夾執行：

```sh
python app.py
```

瀏覽器開啟 http://127.0.0.1:8000 。Windows 亦可使用 `py app.py`。
本機啟動不需要安裝任何第三方套件。

## 已完成

- 英文響應式介面、6 項示範材料、數量選擇、兩家門市的示範整單比較。
- 帳號註冊、密碼登入登出、個人採購清單儲存與載入。
- SQLite 持久化、PBKDF2 密碼雜湊、HttpOnly Session、CSRF 與同來源檢查、登入頻率限制。
- 管理員可查看供應商連線狀態、會員和清單數量。
- 所有價格與庫存明確標示為模擬；沒有向供應商發出請求。
- 未登入介面顯示一家，會員介面顯示兩家。示範 API 資料為公開測試資料，不是正式訂閱權限控制。

## 尚未完成，請勿直接對外收費

- 尚無真實供應商 API、爬蟲或商用授權。
- 商品不是已驗證的跨店同型號商品，不可當真實比價結果。
- 不支援付款、付費方案、試用額度、Email 驗證碼或密碼找回。
- 不含背景排程、PWA 離線安裝、推播或通知信；TTL 僅判定資料過期，不會自行刷新。
- 本機伺服器只監聽 127.0.0.1，供開發使用。

## 更新政策（建議初值，不是 API 承諾）

- 商品規格：每日一次，或收到供應商變更事件時更新。
- 價格：每 60 分鐘；促銷期間視條款縮短。
- 門市庫存：每 15 分鐘；活躍採購清單可在有額度時縮至 5 分鐘。
- 清單查詢：只刷新超過 TTL 的必要項目；送出採購建議前重新驗證。
- 官方提供 Webhook/事件 Feed 時優先使用，另以低頻同步補漏。
- 每個供應商獨立限流、快取、去重、失敗退避；遵守 Retry-After。出錯不能更新成功時間。
- 以 50 商品 × 2 門市估算，逐項庫存每 15 分鐘一次約 9,600 requests/day；若價格也分開逐項每小時查詢，另 2,400/day。批次 API 或同回應含價量可降低次數。正式排程依授權、預算、用量調整。

## API 接入規格

新增供應商 adapter 時，輸出 product/model/UPC、store_id、ZIP、包裝數量、幣別、一般/會員/促銷價格、庫存狀態、取貨時間、來源 URL、供應商更新時間（若提供）、我們成功取得時間。price 與 stock 應各自保存觀測時間、來源證據與最後成功狀態。

未驗證型號、門市不符、缺值或不合理價差不進入推薦排名。保留官方商品連結；供應商確認取貨才代表確定可取，網頁庫存不能作保證。

`DEMO_MODE=0` 會停用示範資料插入，但若沿用曾經跑過 Demo 的資料庫，舊示範列仍存在。因此正式切換必須使用全新資料庫並接入 adapter；V1 介面始終標示 DEMO，不能直接轉正式環境。

## 管理員

首次啟動前，設定 `ADMIN_EMAIL` 與至少 12 字元的 `ADMIN_PASSWORD` 環境變數。啟動時建立管理員，之後從網站登入。不內建共用管理員或預設密碼。

## Heroku ＋ GitHub 部署

已支援 DATABASE_URL 連接 PostgreSQL；本機未設定此變數時使用 SQLite。

1. 建立 GitHub repository（建議 private），將資料夾內檔案放到 repository 根目錄，直接看到 app.py、Procfile、requirements.txt、.python-version，不要再包一層資料夾。
2. 在 Heroku 建立 App，使用 Python buildpack。
3. 在 Resources 加入 PostgreSQL 資料庫，先確認畫面顯示的費用；掛載後應產生 DATABASE_URL，勿將其寫入 GitHub。
4. Settings → Config Vars 設定 DEMO_MODE=1、COOKIE_SECURE=1、ADMIN_EMAIL=管理員信箱、ADMIN_PASSWORD=至少12字元的不重複密碼、PRICE_TTL_SECONDS=3600、STOCK_TTL_SECONDS=900。
5. Deploy → Deployment method 選 GitHub，連接帳號，搜尋並連接 repository。
6. 選 main → Deploy Branch。release 階段會執行 python init_db.py 建表及建立管理員，不清除既有會員或清單。
7. Resources 確認 web process 已啟動，Open app，測試註冊、存清單、登出與重新載入。再重新啟動 App，確認清單仍在。
8. 成功後可 Enable Automatic Deploys，推送 main 即重新部署。

Heroku 未設定 DATABASE_URL 會拒絕啟動，避免誤用暫存 SQLite。正式營運仍需郵件驗證/密碼找回、付款權限、備份、供應商 adapter 與排程。此版未建立 Heroku 或 GitHub 資源，未購買服務，PostgreSQL 連線尚未在實際 Heroku 環境測試。

管理員環境變數僅在帳號不存在時建立帳號，不覆寫密碼或升級既有普通會員。首次啟動前先設定管理員，建立後建議移除 ADMIN_PASSWORD。測試版勿收集正式客戶重要資料。

## 驗證

```sh
python -m unittest test_app.py
```
