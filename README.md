# AI 写词与作曲

方案二（AI 规划＋规则作曲）的本地版本：选择主题、情绪、风格并填写故事，AI 生成三版中文歌词；选一版修改后，系统按 AI 音乐规划和规则作曲生成约 1 分钟的钢琴旋律与伴奏小样（无人声演唱），可在线试听、下载和重新生成。

## 快速开始（第一次运行）

在项目根目录依次执行：

```bash
cd /Users/a1-6/AI音乐
bash scripts/setup.sh          # Python 虚拟环境与前端依赖，生成 .env
bash scripts/setup_audio.sh    # FluidSynth、FFmpeg、钢琴音源（装在项目内 tools/）
bash scripts/dev.sh env-check  # 三项 ✅ 且最后一行“音频环境可用”
```

然后在 `.env` 中配置文本模型（见下文“文本模型”）；暂时没有密钥时写 `MODEL_PROVIDER=mock` 可先走通流程。

再开三个终端，分别启动后端、worker 和前端（都在项目根目录执行，按 Ctrl+C 停止）：

```bash
bash scripts/dev.sh api      # 终端一：后端接口 http://127.0.0.1:8000
bash scripts/dev.sh worker   # 终端二：作曲与渲染后台进程
bash scripts/dev.sh web      # 终端三：网页 http://127.0.0.1:5173
```

浏览器打开 http://127.0.0.1:5173，按“完整流程验收”操作。

## 运行要求

- Node.js 22.12+，npm 或 pnpm。
- 使用 pnpm 时需版本 11+，构建依赖许可在 `frontend/pnpm-workspace.yaml` 中。
- Python 3.10+，建议 Python 3.12。
- 首次安装依赖需要联网。

启动脚本先查终端里的工具；本机没有时会识别 Codex 已有的 bundled Node/Python/pnpm，仅改变脚本自身 PATH，不改系统配置。这里的系统 Python 3.9 不满足要求，脚本会使用已找到的 Python 3.12。换电脑时可正常安装运行要求中的工具。

## 音频工具（FluidSynth、FFmpeg、钢琴音源）

音乐渲染需要 FluidSynth、FFmpeg 和 SF2 钢琴音源。执行下面的命令会把它们装进项目内的 `tools/`（不修改系统、不需要管理员密码），并把路径写入 `.env` 中为空的 `FLUIDSYNTH_PATH`、`FFMPEG_PATH`、`SOUNDFONT_PATH`：

```bash
bash scripts/setup_audio.sh
# 官方 conda 源连接不上时，可指定镜像：
CONDA_CHANNEL=https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge bash scripts/setup_audio.sh
```

- FluidSynth、FFmpeg 来自 conda-forge，经 micromamba 安装到 `tools/env`；首次下载约数百 MB。
- 钢琴音源使用 [GeneralUser GS](https://www.schristiancollins.com/generaluser)（作者允许用于个人或商业音乐创作），保存在 `tools/soundfonts/GeneralUser-GS.sf2`，主旋律与伴奏使用其中的原声钢琴音色。
- 也可自行安装，把 `.env` 中三个路径改为本机绝对路径；相对路径以项目根目录为基准。

检查音频环境：

```bash
bash scripts/dev.sh env-check
```

三项均显示 ✅ 且最后一行为“音频环境可用”时即可渲染；任一项缺失会显示 ❌ 和具体原因（未配置、文件不存在、不可执行或音源无法加载），命令退出码为 1。macOS 首次运行新装的 FFmpeg 可能需要十几秒。

## 文本模型（歌词与音乐规划）

后端通过 OpenAI 兼容的 Chat Completions 接口调用文本模型，DeepSeek、通义千问（兼容模式）、Kimi、智谱、OpenAI 等均可。在根目录 `.env` 中填写：

```bash
MODEL_PROVIDER=openai_compatible
MODEL_API_URL=https://api.deepseek.com
MODEL_API_KEY=你的密钥
MODEL_NAME=deepseek-flash
```

密钥只保存在后端 `.env`（已被 `.gitignore` 排除），不会出现在前端代码、数据库、任务文件或接口响应中。没有密钥时可设置 `MODEL_PROVIDER=mock` 使用离线演示模型：它按固定模板返回示例歌词与默认规划，只用于走通流程；配置真实模型后，模型失败时会直接提示重试，不会改用演示内容。

检查模型配置：`bash scripts/dev.sh check-model`。配置正确时“示例请求”会打印模型返回的结构化数据；同时会验证错误密钥和超时分别得到 `MODEL_AUTH_FAILED`、`MODEL_TIMEOUT`。

### 接口

| 接口 | 说明 |
| --- | --- |
| `GET /api/health` | 健康检查。 |
| `GET /api/presets` | 主题、情绪、风格的 ID 与显示名称，前端据此显示选项。 |
| `POST /api/lyrics` | 提交 `{themeId, emotionId, styleId, story}`，返回故事叙述、情绪表达、意象表达三版歌词。每版主歌 6 行、副歌 4 行，用具体画面来写、少用口语套话，篇幅仍适合约 1 分钟。模型输出太短或格式不符时自动重写一次。 |
| `POST /api/music-jobs` | 提交 `{requestId, sourceRevision, input, lyrics, selectedVariantId}`，返回任务 ID 和状态（新任务为 `queued`）。提交时先检查歌词结构与时长；相同 `requestId` 重复提交返回同一任务。每个任务保存当次的歌词与输入快照及随机种子。 |
| `GET /api/music-jobs/{id}` | 查询任务状态 `queued／running／succeeded／failed`、当前阶段、错误信息，成功后给出音频地址。 |
| `GET /api/music-jobs/{id}/audio` | 播放 MP3，支持 Range 请求（浏览器拖动进度时只取对应片段）。 |
| `GET /api/music-jobs/{id}/download` | 下载同一份 MP3（带下载响应头，文件名形如 `AI作曲小样-20261008-0218.mp3`）。任务未成功返回 409，文件已清理返回 410。 |

接口出错时统一返回 `{"error": {"code", "message", "retryable", "fields"}}`：`retryable` 为 `true` 表示可以直接重试，`fields` 列出具体问题。后端启动后可打开 http://127.0.0.1:8000/docs 查看和试用接口。

## 后端检查命令

从项目根目录执行：

| 命令 | 检查内容 |
|---|---|
| `bash scripts/dev.sh env-check` | FluidSynth、FFmpeg、钢琴音源是否可用。 |
| `bash scripts/dev.sh check-schemas` | 示例乐谱与三版歌词通过校验；音高 128、时值 0、歌词不足三版被拒绝并指出字段。 |
| `bash scripts/dev.sh check-presets` | 列出全部预设；七种风格的默认规划模板均可找到；未知风格被拒绝。 |
| `bash scripts/dev.sh check-midi` | 中央 C、480 tick、120 BPM 导出 MIDI 后读回为一拍约 0.5 秒；旋律与伴奏是独立轨道。生成 `runtime/checks/middle_c.mid`。 |
| `bash scripts/dev.sh check-render` | 用钢琴音源把四小节旋律＋和弦渲染为 `runtime/checks/render_test.wav`，检查非空、无削顶；缺音源时返回错误。用 `open runtime/checks/render_test.wav` 试听。 |
| `bash scripts/dev.sh check-encode` | 渲染约 60 秒和约 11 秒两个测试成品并转 MP3，报告时长；60 秒的通过，11 秒的因超出 45～75 秒不能标记成功。 |
| `bash scripts/dev.sh check-lyrics` | 识别 `[主歌]\n夏夜的风\n[副歌]\n一起向前走` 的两个段落和歌词行；缺副歌标题时提示补齐，原文不变。 |
| `bash scripts/dev.sh check-arrangement` | 24 小节 4/4 100 BPM 输出 57.6 秒乐谱（另计尾音）；短歌词每句后有停顿；过长歌词提示删减且不删词。 |
| `bash scripts/dev.sh check-melody` | 同输入同种子得到相同音符、换种子不同；音符不越音域；副歌音区高于主歌；生成仅含主旋律的 `runtime/checks/melody_only.wav` 供试听。 |
| `bash scripts/dev.sh check-demo` | 合成流行和说唱两版完整小样（`runtime/checks/demo_pop.mp3`、`demo_rap.mp3`）；检查伴奏与旋律对齐、旋律比伴奏响、结尾为主和弦自然衰减、时长合格。 |
| `bash scripts/dev.sh check-model` | 文本模型示例请求返回结构化数据；错误密钥、超时得到明确错误；输出不含密钥。 |
| `bash scripts/dev.sh jobs` | 列出 `runtime/app.db` 中最近 10 个任务的状态、种子、规划来源和歌词快照。 |
| `bash scripts/dev.sh check-worker` | 在临时目录中验证：模拟渲染失败 → `failed`；处理中强制结束 worker，重启后遗留任务 → `failed`；新任务不覆盖上一次成功的音频。 |
| `bash scripts/dev.sh check-plan` | AI 音乐规划：正常规划只引用已有模板；注入未知模板 ID 时修复一次，仍无效则使用默认规划，并打印内部记录。 |
| `bash scripts/dev.sh check-styles` | 七种风格各生成一首短歌词小样到 `runtime/checks/styles/<风格ID>.mp3`，打印结构、时长、字音对应、副歌升高、节奏、旋律响度、结尾衰减等指标表。记录见 `docs/七种风格验证记录.md`。 |
| `bash scripts/dev.sh test` | 全部自动测试（pytest）。 |

## 第一次安装

在项目根目录执行：

```bash
cd /Users/a1-6/AI音乐
bash scripts/setup.sh
```

setup 创建 `.venv`、安装依赖、生成锁定文件，并在 `.env` 不存在时复制模板。重复运行不会覆盖已有 `.env`。

## 启动（三个终端）

| 终端 | 命令 | 启动成功的标志 |
|---|---|---|
| 一：后端 | `bash scripts/dev.sh api` | 出现 `Application startup complete`；浏览器打开 http://127.0.0.1:8000/api/health 看到 `{"status":"ok"}` |
| 二：worker | `bash scripts/dev.sh worker` | 出现“worker 已启动……每 1 秒检查一次排队任务” |
| 三：前端 | `bash scripts/dev.sh web` | 出现 `http://127.0.0.1:5173/` |

三个命令都从项目根目录执行，停止时在对应终端按 Ctrl+C。修改 `.env` 后需重启后端和 worker。

## 完整流程验收

1. 打开 http://127.0.0.1:5173，页面右上角显示“后端已连接”，主题、情绪、风格选项都已列出。
2. 不选任何选项直接点“生成歌词”：主题、情绪、音乐风格下出现“请选择……”，不会发请求。
3. 选择主题、情绪、风格（故事可留空），点“生成歌词”：按钮变为“歌词生成中…”，随后出现“故事叙述／情绪表达／意象表达”三张歌词卡片。
4. 在任意一版点“选用这一版”，下方编辑框出现该版歌词；改几个字后卡片显示“已修改”，可点“恢复原文”撤销。清空歌词时按钮不可点，并提示“歌词为空，无法生成音乐”。
5. 点“生成音乐小样”：依次显示“排队 → 规划音乐 → 生成旋律与伴奏 → 钢琴渲染 → 编码 MP3 → 检查成品”，几秒后出现播放器（标注“钢琴旋律与伴奏小样，无人声演唱”）和时长。
6. 试听：播放、暂停、拖动进度条都正常；点“下载音频”得到 `AI作曲小样-日期-时间.mp3`，可用系统播放器打开。
7. 修改歌词或选项：播放器上方提示“内容已修改，需重新生成音乐”，旧音频仍可播放；点“重新生成”（或“用当前内容重新生成”）得到新任务（新的随机种子），完成后播放器换成新音频。
8. 失败与重试：
   - 生成歌词时关掉后端终端：页面提示“无法连接后端……”和“重试”按钮，已填写的选项和故事保留；重新启动后端后点“重试”即可成功。
   - 生成音乐失败（如音源路径配置错误）：显示失败原因和“重试”按钮，已编辑的歌词和上一次成功的播放器保留；修正后点“重试”或“重新生成”即可。

## 常见问题

- **页面提示“后端未连接”**：确认终端一在运行，再刷新页面。
- **一直停在“排队”，并提示“生成时间比平时长”**：worker 没有启动，在终端二运行 `bash scripts/dev.sh worker`。
- **生成歌词提示模型未配置或密钥错误**：检查 `.env` 中的 `MODEL_*` 配置，运行 `bash scripts/dev.sh check-model` 查看具体原因，改完重启后端和 worker。
- **音乐任务失败并提示渲染或音源错误**：运行 `bash scripts/dev.sh env-check`，按提示修复后重启 worker。
- **查看任务记录**：`bash scripts/dev.sh jobs` 列出最近任务的状态、错误码、种子和规划来源。
- **端口被占用**：5173/8000 被占用时先停止占用端口的开发服务；前端不会悄悄换端口。

如果安装时出现 npm 仓库 `ECONNRESET`，说明下载连接被重置，不能仅由错误确定原因。先检查网络或代理；也可仅为本次安装指定可访问的仓库，例如：

```bash
NPM_REGISTRY=https://registry.npmmirror.com bash scripts/setup.sh
```

这是第三方 npm 镜像；脚本默认仍使用官方仓库，不修改全局设置，也不关闭 HTTPS 校验。

pnpm 安装已设置单连接下载和较短重试间隔，降低同时下载导致连接重置的概率。重跑会复用已有缓存，不需要删除 `work/pnpm-store`。如果仍失败，在普通终端运行 `curl -I --connect-timeout 10 --max-time 20 https://registry.npmmirror.com/rollup`，用于区分整个下载地址不通还是 pnpm 下载失败；成功应出现 HTTP 200。

整体检查（类型检查、前端构建、Python 语法检查、全部自动测试）：

```bash
bash scripts/check.sh
```

## worker 与任务文件

worker 是单独的后台进程：每秒检查一次排队任务，依次完成音乐规划、作曲、渲染 WAV、编码 MP3 与成品检查，文件写入 `runtime/jobs/<任务ID>/`，按 Ctrl+C 退出；`bash scripts/dev.sh worker --once` 只处理一个任务后退出。worker 与网页接口分开运行，渲染时接口仍可正常响应。

任务失败与文件处理：

- 任何一步出错（如渲染失败、成品检查不通过），任务记为 `failed` 并带错误码和中文说明，worker 继续处理下一个任务。
- worker 启动时，会把上次异常退出时遗留的 `running` 任务标记为 `failed`（`WORKER_INTERRUPTED`），用户重新生成即可。
- 每个任务先在 `runtime/jobs/<任务ID>/work/` 中生成，成品检查通过后才改名为同目录下的 `song.mp3`（另有 `song.mid`、`song.score.json`），WAV 删除；失败的任务不会产生或覆盖任何 `song.mp3`。
- worker 只保留最近 `JOB_RETENTION`（默认 50）个已结束任务的文件，更早的自动删除。

`check.sh` 不调用外部模型。前端 `build` 不代替启动命令；`/api` 转发由 Vite 开发服务提供。

## 目录说明

| 路径 | 用途 |
|---|---|
| `frontend/src/main.tsx`、`App.tsx` | 页面启动入口；创作页面的状态与流程。 |
| `frontend/src/styles.css` | 页面样式。 |
| `frontend/src/components/` | 创作表单、三版歌词选择与编辑、音乐进度与播放器、错误提示等组件。 |
| `frontend/src/api/`、`types/` | 前端接口请求（统一错误处理）与数据类型。 |
| `frontend/vite.config.ts` | Vite 配置，将 `/api` 转发到本地后端。 |
| `frontend/package.json`、`tsconfig.json` | 前端依赖、运行命令与 TypeScript 检查。 |
| `frontend/pnpm-lock.yaml` 或 `package-lock.json` | 前端首次成功安装后生成的依赖锁，保留一种。 |
| `frontend/pnpm-workspace.yaml` | pnpm 11 的依赖构建许可配置。 |
| `backend/app/main.py`、`api/health.py` | FastAPI 入口与健康检查接口。 |
| `backend/app/settings.py` | 加载根目录 `.env`，统一管理配置。 |
| `backend/app/schemas/` | 输入、歌词、音乐规划、乐谱与任务的数据格式及校验。 |
| `backend/app/lyrics/parser.py` | 歌词段落标题识别、分句与字符映射。 |
| `backend/app/providers/` | 文本模型适配层（OpenAI 兼容接口、离线演示模型、错误转换）。 |
| `backend/app/composer/arrangement.py`、`rhythm.py` | 段落时长分配与歌词节奏。 |
| `backend/app/composer/harmony.py`、`melody.py`、`accompaniment.py`、`compose.py` | 和弦时间线、主旋律、和弦伴奏与作曲入口。 |
| `backend/app/rendering/pipeline.py` | 乐谱 → MIDI → WAV → MP3 → 成品检查。 |
| `backend/app/planner/` | AI 音乐规划提示词、校验、修复一次与默认规划回退。 |
| `backend/app/rendering/environment.py` | 音频环境检查（`env-check`）。 |
| `backend/app/rendering/midi.py` | 乐谱 JSON 导出 MIDI 及读回。 |
| `backend/app/rendering/audio.py` | FluidSynth 渲染 WAV、裁剪尾部静音、峰值检查。 |
| `backend/app/rendering/encode.py` | WAV 转 MP3（按峰值统一响度）与成品检查。 |
| `backend/app/rendering/` | MIDI 导出、WAV 渲染、MP3 编码与成品检查。 |
| `backend/app/storage/` | SQLite 任务存储（`runtime/app.db`）。 |
| `backend/app/worker.py` | 单个 worker：认领排队任务，串联规划、作曲、渲染与成品检查。 |
| `backend/config/`、`app/presets.py` | 预设、风格规则、默认规划及其加载校验。 |
| `backend/tests/` | 自动测试与示例数据。 |
| `backend/requirements.txt`、`requirements.lock.txt` | 直接依赖约束；锁文件在首次成功安装后生成。 |
| `backend/pyproject.toml` | Python 项目信息及版本要求。 |
| `scripts/` | 安装、启动和检查脚本。 |
| `runtime/`、`.venv/` | 运行产物预留目录与项目隔离的 Python 环境。 |
| `tools/` | 项目内安装的 FluidSynth、FFmpeg 与钢琴音源，不提交。 |
| `.env.example`、`.env` | 配置模板与本机配置，真实 `.env` 不提交。 |
| `.gitignore` | 排除密钥、本地依赖、临时产物等。 |
| `docs/`、`outputs/`、`work/` | 已有文档、交付副本和临时工作目录。 |

SQLite 是 Python 标准库，不额外安装数据库驱动；mido 用于读写 MIDI，httpx 用于调用文本模型。依赖以锁定文件为准，修改依赖后需重新生成锁；不要同时维护两种前端锁文件。

Vite 运行版本要求参考 [官方指南](https://vite.dev/guide/)。项目使用本地 Git 管理，未部署到云端。

## 本次验证状态

任务 01～24 已完成。最终验收在一份全新克隆的代码中进行：按“快速开始”安装依赖，启动后端、worker 和前端，在浏览器中走通“输入→三版歌词→编辑→作曲→试听→下载→重新生成”，并验证歌词请求失败、音乐任务失败后可重试且内容保留。七种风格的客观指标与试听清单见 `docs/七种风格验证记录.md`。

本机没有真实模型密钥，验收使用 `MODEL_PROVIDER=mock`（固定模板歌词与默认规划）。配置真实模型后请运行 `bash scripts/dev.sh check-model`，再按“完整流程验收”试一遍，确认歌词质量与 AI 规划效果。
