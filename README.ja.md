# Feishu Bitable MCP

[English](README.en.md) | [简体中文](README.md) | **日本語**

Feishu（飛書）の多次元テーブル（Bitable）の URL を AI クライアントに渡すだけで、テーブル構造の確認やレコードの読み取りを行える、軽量なセルフホスト型 Python MCP サーバーです。表計算ファイルを毎回エクスポートしたり、Feishu OpenAPI との連携を一から実装したりする手間を減らすことを目的としています。

> **対応地域について：** v0.1.0 が対応するのは **Feishu 中国版のみ**です。**Lark 国際版**は関連製品ですが、API のホストとアプリ認証情報が異なります。現行版は Lark の URL や国際版アプリには**対応していません**。Lark 対応には名称変更だけでなく、実装と検証が必要です。
>
> 本リポジトリはコミュニティによる独立プロジェクトであり、Feishu、Lark、OpenAI の公式製品ではありません。

## 開発の背景

元々の目的は、ChatGPT に Feishu Bitable のリンクを渡すだけで、認可された MCP 接続を通じてデータ構造とレコードを直接取得し、ファイルを手動で出力せずに分析できるようにすることでした。非公開の初期プロトタイプでは、ChatGPT から実際の Bitable を読み取り、固定のテストテーブルにレコードを 1 件作成する操作も確認しました。

公開版は汎用的なコードとして新たに実装し、架空データと Mock API でテストしています。**v0.1.0 について、実際の Feishu 環境や ChatGPT Web との接続を再検証したわけではありません。**

## 利用可能な MCP ツール
## 開発目的と現在の対応範囲

**当初の利用目的：** Feishu Bitable の URL を ChatGPT に渡し、認可された MCP 接続を使ってテーブル構造やレコードを直接読み取り、ファイルのエクスポートや個別の API 実装なしで分析できるようにすることです。ただし、この利用目的は v0.1.0 で ChatGPT Web との接続が再検証済みであることを意味しません。

- **実装済み（Feishu 中国版）：** Base 情報、フィールド構造、レコードのページング、テーブル検査、および認証・許可リスト・フィールド検証が必要なレコード 1 件の作成（オプション）。
- **未実装：** 既存レコードの更新、テーブルの新規作成、通常の Feishu 文書の編集。
- **非対応：** Lark 国際版のテナント・ドメイン・アプリ認証情報。別途実装と検証が必要です。

公開版の自動テストは架空データと Mock API によるものです。実際の Feishu テスト表を ChatGPT から読み書きした実績は、**以前の非公開プロトタイプ**に関するものです。


| ツール | 機能 |
| --- | --- |
| `get_bitable_info(url)` | Bitable URL を解析して Base とテーブルの基本情報を返します。 |
| `list_fields(url)` | ページ分割されたフィールド一覧と元のメタデータを取得します。 |
| `list_records(url, page_size, page_token)` | レコードを 1 ページ取得し、次ページのトークンを返します。 |
| `inspect_table(url, sample_size)` | テーブル構造と少量のレコードを確認します。 |
| `create_record(url, fields, confirm)` | **既定では無効**。認証・テーブル許可リスト・フィールド検証を設定した場合に限り、レコードを 1 件作成します。 |

対応する URL 形式は `https://<tenant>.feishu.cn/base/<base_token>?table=<table_id>` で、`view` パラメーターは任意です。Wiki、短縮 URL、Lark 国際版ドメイン、通常の文書には対応していません。`view` は上流 API に転送されますが、**アクセス権限を分離する仕組みではありません**。

既存レコードの更新・削除、テーブルの新規作成、通常の Feishu 文書の編集は実装していません。

## インストールと起動

Python 3.11 以降が必要です。

```bash
git clone https://github.com/a2681220474-glitch/feishu-bitable-mcp.git
cd feishu-bitable-mcp
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
cp .env.example .env
```

ローカルの `.env` に **Feishu 中国版の企業自社開発アプリ**の認証情報を設定します。

```dotenv
FEISHU_APP_ID=
FEISHU_APP_SECRET=
```

[Feishu 開発者コンソール](https://open.feishu.cn/app)でアプリを作成し、対象 API と Base へのアクセス権限を付与してください。認証情報を Issue や公開チャットに貼り付けないでください。

HTTP MCP サーバーを起動：

```bash
feishu-bitable-mcp
```

ローカル MCP URL は `http://127.0.0.1:8000/mcp` です。stdio に対応した MCP クライアントでは次を使用できます。

```bash
feishu-bitable-mcp --transport stdio
```

詳細な設定、Windows での操作、MCP 初期化の例は [中国語の完全版 README](README.md)を参照してください。

## リモートアクセスとセキュリティ

Feishu の App Secret は上流 API 用の認証情報であり、**MCP サーバーへのアクセスを認証するものではありません**。

- ループバック以外で HTTP を公開する際は、32 文字以上のランダムな `MCP_AUTH_TOKEN` が必要です。クライアントは `Authorization: Bearer …` に対応している必要があります。
- HTTPS トンネルを使っても、ポートは外部からアクセス可能になります。認証のない業務データ API を公開しないでください。
- このプロジェクトは OAuth サーバーを提供しません。ChatGPT Web など、一部の MCP クライアントでは外部 OAuth/OIDC ゲートウェイが必要な場合があります。**本リリースで ChatGPT Web の認証を実環境検証したわけではありません。**
- 必要に応じて `FEISHU_READ_TABLE_URLS` で読み取り対象を制限できます。
- レコード作成を有効にするには、`FEISHU_ENABLE_WRITES=true`、`MCP_AUTH_TOKEN`、`FEISHU_WRITE_TABLE_URLS` を設定します。許可されたフィールド型のみ書き込めます。
- `confirm=true` はクライアントからの承認申告であり、独立した本人承認の証明ではありません。適切な承認手続きがない場合、書き込みは無効のままにしてください。

現行版は既存レコードやスキーマを変更せず、結果が不明な書き込みを自動再試行しません。

## テストと制限事項

```bash
python -m pip install '.[dev]'
ruff check src tests examples
pytest -q
python -m build
```

初回公開版には **203 件の Mock ベースのテスト**と Python 3.11–3.13 の CI 設定があります。`examples/` には架空データの例を用意しています。Mock テストは実装の期待動作を検証するものであり、**実際の Feishu テナントや Lark 国際版との連携実績を意味しません**。

認証方式は Feishu アプリの `tenant_access_token` です。アクセス範囲はアプリへの権限付与によって決まり、依頼した個々のユーザーの権限と自動的に一致するわけではありません。レコードのページングには `has_more` と `page_token` を使用してください。

## 公式ツールとの違い

公式の [Feishu/Lark OpenAPI MCP](https://github.com/larksuite/lark-openapi-mcp) はより広範な API と、中国版・国際版の切り替えに対応しています。幅広い機能やユーザー OAuth が必要な場合は公式ツールを先に検討してください。本プロジェクトは URL からの表構造確認と読み取りを中心に、機能を限定して理解しやすくした実装です。

貢献方法は [CONTRIBUTING.md](CONTRIBUTING.md)、脆弱性報告は [SECURITY.md](SECURITY.md)、ライセンスは [LICENSE](LICENSE)（MIT）をご覧ください。
