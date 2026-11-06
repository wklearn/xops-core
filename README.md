# XOps Core (v0.1.0)

**中文 / English** · MIT · Python 3.11+ · SQLite · No paid API · Offline-first

A small, independent, human-in-the-loop approval pipeline for `PUBLIC_POSTS_V1` candidate content. **This repository is a new reference implementation, not an export of any user's private XOps system.** It does not fetch mail, call AI models, post to X, or publish to any other platform.

## 中文：快速开始（Windows / macOS / Linux）

安装 Python 3.11 或更新版本。下载并解压项目，然后在项目文件夹内打开终端：

```powershell
python -m xops_core init
python -m xops_core import examples/sample.json
python -m xops_core stats
python -m xops_core serve
```

在本机浏览器打开 `http://127.0.0.1:8765/`，看到待审核内容后点击 **Approve** 或 **Reject**。例如，批准后执行：

```powershell
python -m xops_core export approved.json
```

这一步**只导出 JSON 文件，绝不自动发布**。`approved.json` 应由你自己的发布程序再次核验并处理。已导出的候选默认标记为 `exported`，防止重复导出。再次导出前保留批准状态的选项：`--keep-approved`。

还可以在终端完成同样的审核：

```powershell
python -m xops_core list --status pending
python -m xops_core review 1 approve
python -m xops_core export approved.json
```

数据库默认写入本文件夹 `xops-core.sqlite3`，不会扫描或修改任何现有 XOps 数据文件。如需独立路径，请在子命令前添加 `--db`，例如：

```powershell
python -m xops_core --db D:\XOpsCoreData\review.sqlite3 init
```

`import` 支持纯 JSON 或邮件内容中**恰好一个** ```json 代码块。一次最多 100 个候选；最大 2 MiB。重复 `(account, event_id)` 自动跳过；同一文件出现重复事件或 `post_id` 则校验失败。不同账号可以保留同一事件的独立候选。

## Input protocol

Required top-level format:

```json
{"version": "PUBLIC_POSTS_V1", "posts": []}
```

The marker may also be in `schema` or `format`. Each post requires:

- `event_id`, `post_id`, `account`, `lang`, `pillar`, `evidence_stage`
- `text`, `alt_texts` (exactly two full alternatives)
- `source_name`, `source_tier`, `source_url` (HTTPS), `source_quote`
- optional `priority`, `key_numbers`

Source fields may also appear under a `source` object with `name`, `tier`, `url`, `quote`. Each text variant must be **≤260 weighted characters**, where ASCII counts as 1 and non-ASCII as 2. This is a conservative default, not a guarantee of any platform's actual character limits. The project does **not** verify source quotations against websites or make factual claims on behalf of the user.

## What is intentionally absent

- No Gmail access, X/Buffer API, auto-scheduling or auto-publishing
- No LLM dependency, network crawler, secret storage or user authentication
- No migration path for private production databases
- No promise that arbitrary private XOps email formats will import unchanged

The local browser UI listens only on `127.0.0.1`; do **not** expose it to the internet. The sample post and `example.com` URL are placeholders, **not real news**.

## Tests

```sh
python -m unittest discover -s tests -v
```

GitHub Actions runs the test suite on Windows and Ubuntu, Python 3.11 and 3.13.

## Roadmap

- [ ] Optional import adapters for differing PUBLIC_POSTS_V1 producers
- [ ] Manual conflict-review workflow and detailed evidence preview
- [ ] One-click export UI and schema-versioning tools
- [ ] Optional desktop packaging (without exposing a web port)

## English quick start

From the repository directory, run `python -m xops_core init`, `python -m xops_core import examples/sample.json`, then `python -m xops_core serve`. Open `http://127.0.0.1:8765/`, approve a candidate, and run `python -m xops_core export approved.json` to save approved candidates **without publishing them**. Data stays in a local SQLite database. See the Chinese instructions above for CLI details.

## License

MIT. Contributions welcome; never commit personal credentials or private data.

## Compatibility note

`text_zh` and its two `alt_texts_zh` variants, `stage_now`, and `evergreen` are supported when present. Unexpected fields are deliberately not re-exported to reduce accidental release of private metadata. Confirm your **actual producer schema** with synthetic data before using this tool with a production workflow. No existing XOps version is modified by this package.

See [PUBLISHING.md](PUBLISHING.md) for public-repository publication steps.
