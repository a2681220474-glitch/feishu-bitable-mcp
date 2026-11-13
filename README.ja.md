# Feishu Bitable MCP

[English](README.en.md) | [简体中文](README.md) | **日本語**

飛書の多次元テーブル、クラウド文書、オンライン表計算、クラウドドライブ上の Excel を読むセルフホスト型 MCP です。ChatGPT にリンクを渡し、毎回 Excel を出力せずにデータを分析する目的で作られました。

**開発候補 0.2.0rc1：** 飛書ユーザー認可と文書・Excel 読み取りを実装し、模擬 API で検証しています。実際の飛書と ChatGPT ブラウザーの接続検証は未完了です。公開済み v0.1.1 には追加機能は含まれません。独立したコミュニティプロジェクトであり公式製品ではありません。Lark 国際版は非対応です。

## 自分の環境で使う

各利用者が自分の飛書アプリ、アカウント、HTTPS サービスを用意します。管理者による本プロジェクトの利用承認や OpenAI API Key は不要です。ソース公開だけでホスティングが提供されるわけではありません。

ユーザーモードでは ChatGPT から飛書にログインして同意し、そのユーザーの認可で読み取ります。自動更新が利用できない場合は再接続・再ログインします。実効権限は本人の権限、アプリ権限、同意、企業ポリシーに制限されます。ユーザーモードは読み取り専用です。

## ツール

| ツール | 読み取り内容 |
| --- | --- |
| get_bitable_info | Base と指定テーブルの情報 |
| list_fields | 全フィールドページと元の設定 |
| list_records | レコード 1 ページと次ページのカーソル |
| inspect_table | 構造、メタデータ、先頭サンプル |
| resolve_resource | Wiki を含むリソースの型と token |
| read_document | 書式・親子参照を保つ docx ブロックのページ |
| get_spreadsheet_info | 表計算と全ワークシートの属性 |
| read_spreadsheet | 最大 5000 セルの範囲、値または数式 |
| read_excel_file | ドライブ上 .xlsx の値・型・表示形式と行カーソル |

既存のアプリ身份モードも利用できます。create_record は従来の認証・許可リスト・型検証・確認を必要とし、ユーザーモードでは利用できません。更新、削除、構造変更のツールはありません。

## インストール

この README を含むソース版で、Python 3.11–3.13 を使用します。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
feishu-bitable-mcp --setup
feishu-bitable-mcp --doctor
feishu-bitable-mcp
```

ウィザードで自分のアプリ情報と HTTPS /mcp URL を保存します。既存設定は上書きしません。飛書アプリに /auth/callback を登録し、読み取り権限とアプリの公開・承認を設定してください。HTTP サービス全体を HTTPS で転送し、ChatGPT に /mcp を追加して OAuth を選び、飛書にログインします。[詳細設定](docs/setup.md)と[認可の範囲](docs/user-access.md)（中国語）を参照してください。既定は 127.0.0.1:8000/mcp です。

## 制約と検証

ページと範囲を続けて取得してください。文書内の画像等は参照のまま保持し、自動描画・取得しません。オンライン表の全書式取得は保証しません。Excel は通常の .xlsx のみで、ダウンロード 20 MiB、ZIP 展開後 100 MiB、範囲 5000 セルです。数式やマクロは実行せず、保存済み計算結果は古い/存在しない場合があります。.xls、マクロ・暗号化ブック、ローカルパスは非対応です。

模擬テストには認可、同意、PKCE、更新、失効後の拒否、ユーザー分離を含みます。実環境の権限や ChatGPT 接続の成功を意味しません。過去の実際の飛書テストは旧非公開プロトタイプの実績です。

.env、認証状態、token、業務データを公開しないでください。[安全方針](SECURITY.md)、[貢献](CONTRIBUTING.md)、[変更履歴](CHANGELOG.md)、[MIT ライセンス](LICENSE)も参照してください。公式 [CLI](https://github.com/larksuite/cli) と [OpenAPI MCP](https://github.com/larksuite/lark-openapi-mcp) はより広い API を提供します。本プロジェクトは URL 指向の少数ツールと明示的な読み取り上限を重視します。
