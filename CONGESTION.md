# コールセンター混雑状況

`docs/congestion.html` をハブの「コールセンター混雑」から表示する。
リアルタイム待ち時間ではなく、公式が掲載する時間帯別の目安を比較する。

- SBI: 公式サポートHTMLの `karte_home_support_call_busy` と直後の凡例・注記。
- 楽天: 公式 `cs-congestion.json` の電話・チャットと、連絡先ページの対象セクションの注記。
- マネックス: 公式混雑表。現在このPCのHTTP取得は403のため未取得を表示。アクセス制限の回避や検索結果からの履歴補完はしない。
- 大和: ユーザーの追加指示により取得・表示対象から除外。
- 野村・松井: 詳細表の取得先が未確認のため対象外を表示。

## 実行

Python環境に `requirements_congestion.txt` の依存が必要。既存自動化のPythonには導入済み。

```powershell
& 'C:\Users\yt\AppData\Local\Python\pythoncore-3.14-64\python.exe' fetch_congestion.py
& 'C:\Users\yt\AppData\Local\Python\pythoncore-3.14-64\python.exe' -m unittest test_congestion -v
.\install_congestion_task.ps1
```

Windowsタスク `\StockAutomation\callcenter-congestion` が毎日0時と12時（Tokyo Standard Time）に既存の `C:\Users\yt\automation\run_task.py callcenter-congestion` を実行。アプリ常駐不要。既存ランナーが `docs/data_congestion` のみをaddしてcommit/pull/push。ログは `C:\Users\yt\automation\logs\callcenter-congestion.log`。定時実行にはPC・ユーザーのログイン・ネットワークが必要。スリープ復帰と実行取りこぼし後の追随を有効化。重複実行はIgnoreNew。

## データと判定

`data.json` に実際の観測日時、成功・失敗、HTTPヘッダー、全観測履歴を保存。各観測には時刻とハッシュを記録し、異なる内容を `versions/<company>/<sha256>.json` に保存。同じ内容への復帰も観測があれば検出。初回は基準点のみ。失敗時は最後の成功内容を保持してエラーを履歴に追加。部分失敗・全社失敗でも観測結果を公開するため終了コードは0（ランナーログに社別の結果が残る）。ファイルI/O失敗等は例外で停止する。

内容比較にHTTP Last-Modified、ETag、取得日時を混ぜない。広告等のページ全体差分も対象外。Last-Modifiedは公式の実績基準日ではない。キャッシュ期限から更新周期は推定しない。現状の頻度は未判定。観測間の変更・復帰や同内容の再保存は検出できない。パーサーの列数・値の検証に失敗した場合は「内容変更」にせず取得エラーとして手動確認する。

実装変更で内容の正規化方式が変わる場合は、その変更によるハッシュ差を公式の更新と誤記録しないように移行すること。既存履歴を削除して初回を捏造しない。
