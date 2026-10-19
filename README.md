# 詩歌選集 Poetry App

一個以繁體中文詩歌為核心的 Android 離線閱讀 App。介面以 HTML、CSS、JavaScript 製作，Android 端以 `WebView` 包裝並提供原生的音訊播放、檔案儲存與匯入／匯出功能。

目前資料庫收錄五個歌本、共 **1,611 首**：

| 歌本 | key | 目前首數 |
| --- | --- | ---: |
| 詩歌 | `hymns` | 786 |
| 補充 | `supplement` | 513 |
| 新歌頌詠 | `new-songs` | 142 |
| 新詩 | `new-poems` | 76 |
| 藍本 | `blue-poems` | 94 |

## 目前功能

### 查找與瀏覽

- 可在五個歌本間切換，使用數字鍵盤依編號直接開啟詩歌；支援「附」號。
- 提供快速瀏覽，依歌本實際編號分組顯示，並附標題與歌詞開頭預覽。
- 可搜尋詩歌編號、標題與歌詞全文；搜尋會忽略空白、標點與部分常見異體字，並在結果中標記命中的歌詞片段。
- 搜尋資料採分片 JSON 載入，以降低初次載入時的資料量。

### 詩歌閱讀

- 顯示單頁或多頁歌譜圖片，提供上一首／下一首與頁碼切換。
- 支援左右滑動換頁或換歌、雙指縮放歌譜、放大後單指拖曳平移。
- 可切換「歌譜」與「文字歌詞」模式；結構化歌詞會區分節與副歌。
- 長按歌譜可將目前圖片儲存至 Android 的 `Download/Poetry_APP`。
- Android 返回鍵會優先執行 App 內返回，而非直接離開。

### 音檔播放與下載

- `詩歌` 與 `補充` 的歌曲可播放旋律；`新歌頌詠`、`新詩`與`藍本`目前僅提供圖文內容。
- 播放器提供播放／暫停、目前時間、總時長、點選或拖曳進度條跳轉，以及 `0.75x` 至 `2x` 倍速。
- 可開啟或關閉播放列。
- Android 版可下載尚未存在的音檔、略過已下載的檔案，以及一次刪除已下載音檔。下載後的檔案會存於 App 專用儲存空間，更新 App 後仍會保留。
- Lite APK 不內嵌 MP3；Full APK 只有在本機 `database/audio/` 存在音檔時才會把音檔打包進去。

### 使用者資料與易讀性

- **最近開啟**：在詩歌頁停留超過 30 秒才會記錄，最多保留 50 首，並可手動清除。
- **我的最愛**：可建立多個群組、重新命名、排序群組與歌曲、加入或移除歌曲，並支援快速刪除模式。
- **最愛備份**：可匯出／匯入 JSON；匯入只更新最愛資料，不會覆蓋最近開啟紀錄。
- **設定**：可調整歌詞字級、整體 UI 字級，以及預設開啟歌譜或文字歌詞模式。
- 在 Android 裝置上，最愛、最近開啟與設定由原生儲存保存；瀏覽器開發模式則使用 `localStorage`。

## 技術架構

```text
index.html + style.css + app.js
            │
            ├─ database/indexes/     首頁與歌本索引
            ├─ database/search/      搜尋分片
            └─ database/songs/       每首歌的 song.json、歌詞與歌譜圖片
                         │
                         └─ Android WebView（MainActivity.java）
                              ├─ MediaPlayer 音訊播放
                              ├─ 音檔下載與刪除
                              ├─ 圖片與最愛備份儲存
                              └─ Android 檔案選擇器匯入
```

Android 專案位於 `android/`，目前設定為：

- package / application ID：`com.local.poetryapp`
- 最低 Android 版本：API 23
- target / compile SDK：35
- 原生依賴：`androidx.webkit`

## 專案結構

| 路徑 | 用途 |
| --- | --- |
| `index.html`、`style.css`、`app.js` | WebView UI 與互動邏輯 |
| `android/` | 原生 Android 專案；`MainActivity.java` 提供 JavaScript bridge |
| `database/` | App 直接讀取的索引、搜尋資料、每首歌的 JSON 與歌譜圖片 |
| `pdf/` | 用於重建歌譜資料的來源 PDF |
| `build_database.py` | 從來源 PDF 擷取歌名、歌詞與歌譜圖片，重建 `database/` |
| `build_web_bundle.js` | 將索引與搜尋資料組成 `database/web-db.js`，供 WebView 使用 |
| `download_audio.py` | 從 hymnal.net 下載詩歌與補充的音檔到本機 `database/audio/` |
| `build_apk.ps1` | 建立 Lite 或 Full Debug APK |
| `setup_android_tools.ps1` | 下載並設定專案本機使用的 JDK、Gradle 與 Android SDK |
| `scripts/`、`tools/` | 歌詞、編號、標題與 PDF 資料的修正／稽核工具 |

## 本機開發

### 1. 預覽 Web 介面

需要 Python 3。

```powershell
python app.py
```

接著在瀏覽器開啟 <http://127.0.0.1:8000>。此開發伺服器會停用快取，方便檢查資料或 UI 修改。

### 2. 重新產生 Web 資料 bundle

需要 Node.js。每次改動 `database/indexes/`、`database/search/` 或本機音檔清單後執行：

```powershell
node .\build_web_bundle.js
```

它會產生／更新 `database/web-db.js`。這個檔案需隨資料變更一併提交。

### 3. 從 PDF 重建資料庫

只有更新來源 PDF、歌譜圖片、歌名或基礎歌詞資料時才需要執行。需要 Python 3 與 PyMuPDF：

```powershell
python -m pip install PyMuPDF
python .\build_database.py
node .\build_web_bundle.js
```

請先檢查輸出的 `database/` 差異，再提交資料更新。藍本的頁面與標題有額外維護工具，位於 `tools/blue_poem_titles/`、`rebuild_blue_poems_94.py` 與 `update_blue_titles.py`。

### 4. 取得本機音檔（選用）

音檔不在 Git repository 中。若需建立有音檔索引的版本，可在確認來源與授權適用後執行：

```powershell
python .\download_audio.py
node .\build_web_bundle.js
```

下載器目前只處理 `hymns` 與 `supplement`，並從 hymnal.net 取得實際音檔 URL。請勿將下載的 MP3 加入 Git。

### 5. 建立 Android APK

首次在 Windows 環境建置時，先準備專案本機的工具鏈：

```powershell
.\setup_android_tools.ps1
```

建立不含 MP3 的 Lite APK：

```powershell
.\build_apk.ps1 -Lite
```

建立 Full APK（會在本機有音檔時將其打包）：

```powershell
.\build_apk.ps1
```

APK 會輸出於專案根目錄；它們屬於建置產物，不應提交至 Git。

## 資料格式

每首歌位於：

```text
database/songs/<book>/<number>/
├─ song.json       # 標題、頁面路徑與完整資料
├─ lyrics.json     # 有結構時的歌詞節／副歌資料（並非每首都有）
└─ 01.jpg ...      # 一頁或多頁歌譜圖片
```

歌本索引位於 `database/indexes/<book>.json`；搜尋分片則位於 `database/search/<book>/part-*.json`。修改資料格式或重建邏輯時，請同時確認 `app.js` 的讀取與搜尋流程。

## Git 與大型檔案規則

為保持 repository 易於 clone 與協作，下列內容已列入 `.gitignore`，不可重新加入追蹤：

- `database/audio/` 與 `*.mp3`：大型音檔，請本機生成或下載。
- `*.apk`、`android/app/build/`、`android/.gradle/`：可重建的 Android 產物與快取。
- `.android-tools/`：由設定腳本下載的本機工具鏈。
- `.agents/`、`.codex/`、Python 快取：個人／工具執行資料。

提交前建議執行：

```powershell
git status
git diff --check
```

若有新的大檔、授權不明的素材或帳密／簽章金鑰，請先不要加入 Git，並與維護者確認。

## 給新加入開發者的建議

1. 先用 `python app.py` 了解 Web 介面與現有資料。
2. 修改 UI 或互動後，至少在瀏覽器與 Android APK 各驗證一次。
3. 修改資料庫內容後，重新執行 `node .\build_web_bundle.js`，並檢查搜尋、編號開啟、文字歌詞與圖片頁數是否正確。
4. 修改 Android bridge 時，測試音訊、圖片儲存、最愛匯入／匯出與返回鍵行為。
5. 本專案目前未提供自動化測試套件；提交前請進行上述手動驗證。

## 授權與內容來源

Repository 目前未設定開放原始碼授權。歌譜 PDF、歌詞、圖片與音檔可能受各自權利人保護；在公開散布、重新使用或新增素材前，請先確認適用的授權與使用權限。
