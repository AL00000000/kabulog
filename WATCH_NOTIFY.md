# 注目銘柄のDiscord通知

公開中の `docs/data_personal/bottom-up.json` の全件を毎回読み込みます。銘柄の追加・削除はこのリストに追従します。既存のTOPIX除外候補通知とは独立しています。

- 毎営業日17:10（日本時間）：前営業日終値→当日終値。休日の古い終値は再送しません。
- 毎週水曜12:00（日本時間）：前週水曜始値→今週水曜始値。片方が休場・上場前等なら算出不可と表示し、別の日へ置換しません。
- 株価はYahoo Financeの日足OHLC（株式分割調整済みの価格）を取得します。配当再投資の総収益率ではありません。取得不能銘柄も名前と理由を残します。
- 上場前の銘柄は `listed_from` まで算出不可。上場初日や比較対象の始値がない期間も算出不可です。
- Windowsタスクスケジューラ `\StockAutomation\kabulog-notes-daily` / `kabulog-notes-weekly`。PCとネットワーク、Windowsユーザーのログインが必要です。スリープ復帰と取りこぼし時の後追い実行は有効ですが、別の日の値へのすり替え・過去日の自動送信は行いません。

`install-watch-notify.ps1` で登録します。秘密と状態は `%LOCALAPPDATA%\KabulogWatchNotify` に置き、WebhookはWindowsユーザーにひも付くDPAPIで暗号化します。Git・公開ページ・ログへWebhookを出しません。

```powershell
py -m unittest test_watch_notify -v
py watch_notify.py daily --dry-run --as-of 2026-10-23
py watch_notify.py weekly --dry-run --as-of 2026-10-21
```

プレビューは保存先の `preview-daily.json` / `preview-weekly.json` で確認できます。`--as-of` は未送信の検証専用です。通常送信はモード・当日の日付単位で重複防止し、Discordの受領確認後にsentを保存します。送信の成否が不明な場合はpendingを残し、自動再送しません。`monitor.log` とDiscordを照合して対処してください。
