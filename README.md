# AI 写词与作曲

方案二（AI 规划＋规则作曲）的本地脚手架。目前只有首页、前后端健康检查和 worker 入口，没有歌词、作曲、存储或音频生成业务。

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
MODEL_API_URL=https://api.deepseek.com/v1   # 服务商提供的 OpenAI 兼容地址
MODEL_API_KEY=你的密钥
MODEL_NAME=deepseek-chat
```

密钥只保存在后端 `.env`（已被 `.gitignore` 排除），不会出现在前端代码、数据库、任务文件或接口响应中。没有密钥时可设置 `MODEL_PROVIDER=mock` 使用离线演示模型：它按固定模板返回示例歌词与默认规划，只用于走通流程；配置真实模型后，模型失败时会直接提示重试，不会改用演示内容。

检查模型配置：`bash scripts/dev.sh check-model`。配置正确时“示例请求”会打印模型返回的结构化数据；同时会验证错误密钥和超时分别得到 `MODEL_AUTH_FAILED`、`MODEL_TIMEOUT`。

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
| `bash scripts/dev.sh test` | 全部自动测试（pytest）。 |

## 第一次安装

在项目根目录执行：

```bash
cd /Users/a1-6/AI音乐
bash scripts/setup.sh
```

setup 创建 `.venv`、安装依赖、生成锁定文件，并在 `.env` 不存在时复制模板。重复运行不会覆盖已有 `.env`。

## 启动（两个终端）

终端一，后端：

```bash
cd /Users/a1-6/AI音乐
bash scripts/dev.sh api
```

终端二，前端：

```bash
cd /Users/a1-6/AI音乐
bash scripts/dev.sh web
```

打开 `http://127.0.0.1:5173`。停止服务时在对应终端按 Ctrl+C。

## 确认搭建成功

1. 页面显示“AI 写词与作曲”“React + TypeScript + FastAPI 项目已启动。”以及“后端已连接 · /api/health 返回 ok”。
2. 浏览器打开 `http://127.0.0.1:8000/api/health`，看到 `{"status":"ok"}`；`http://127.0.0.1:8000/docs` 能看到接口说明。
3. 后端终端出现 `Application startup complete`，前端显示 `http://127.0.0.1:5173/`。
4. 可另开终端执行 `curl http://127.0.0.1:8000/api/health`，得到相同 JSON。

如果首页提示后端未连接，确认后端终端在运行，再刷新。5173/8000 被占用时先停止占用端口的开发服务；前端不会悄悄换端口。

如果安装时出现 npm 仓库 `ECONNRESET`，说明下载连接被重置，不能仅由错误确定原因。先检查网络或代理；也可仅为本次安装指定可访问的仓库，例如：

```bash
NPM_REGISTRY=https://registry.npmmirror.com bash scripts/setup.sh
```

这是第三方 npm 镜像；脚本默认仍使用官方仓库，不修改全局设置，也不关闭 HTTPS 校验。

pnpm 安装已设置单连接下载和较短重试间隔，降低同时下载导致连接重置的概率。重跑会复用已有缓存，不需要删除 `work/pnpm-store`。如果仍失败，在普通终端运行 `curl -I --connect-timeout 10 --max-time 20 https://registry.npmmirror.com/rollup`，用于区分整个下载地址不通还是 pnpm 下载失败；成功应出现 HTTP 200。

可选检查（从项目根目录执行）：

```bash
bash scripts/check.sh
bash scripts/dev.sh worker
```

worker 当前只打印“Worker 脚手架可用，未接入任务处理。”然后退出，这是预期行为。check 执行类型检查、前端构建、Python 语法检查，不调用外部模型。`build` 不代替启动命令；当前代理由 Vite 开发服务提供。

## 目录说明

| 路径 | 用途 |
|---|---|
| `frontend/src/main.tsx`、`App.tsx` | 页面启动入口与首页占位、连接状态。 |
| `frontend/src/styles.css` | 首页基础样式。 |
| `frontend/src/components/` | 后续放表单、编辑器和播放器组件。 |
| `frontend/src/api/`、`types/` | 前端接口请求与数据类型。 |
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
| `backend/app/planner/` | 后续放音乐规划。 |
| `backend/app/rendering/environment.py` | 音频环境检查（`env-check`）。 |
| `backend/app/rendering/midi.py` | 乐谱 JSON 导出 MIDI 及读回。 |
| `backend/app/rendering/audio.py` | FluidSynth 渲染 WAV、裁剪尾部静音、峰值检查。 |
| `backend/app/rendering/encode.py` | WAV 转 MP3（按峰值统一响度）与成品检查。 |
| `backend/app/rendering/`、`storage/` | 后续放音频渲染与 SQLite/文件存储。 |
| `backend/app/worker.py` | 后台任务入口占位，当前不会执行任务。 |
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

SQLite 是 Python 标准库，不额外安装数据库驱动。mido、httpx 等已声明为后续模块必要依赖，本次尚未调用。依赖以锁定文件为准，修改依赖后需重新生成锁；不要同时维护两种前端锁文件。

Vite 运行版本要求参考 [官方指南](https://vite.dev/guide/)。项目使用本地 Git 管理，未部署到云端。

## 本次验证状态

依赖安装、前端类型检查、Vite 构建、Python 语法检查及 worker 入口检查通过；本机已实际启动后端和前端，浏览器首页显示“后端已连接”，`/api/health` 返回 `{"status":"ok"}`。
