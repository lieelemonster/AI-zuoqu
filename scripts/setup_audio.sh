#!/usr/bin/env bash
# 把 FluidSynth、FFmpeg 和钢琴音源安装到项目内 tools/，不修改系统，不需要管理员密码。
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
cd "$PROJECT_ROOT"

CONDA_CHANNEL="${CONDA_CHANNEL:-conda-forge}"
SOUNDFONT_URL="https://raw.githubusercontent.com/mrbumpy409/GeneralUser-GS/main/GeneralUser-GS.sf2"
SOUNDFONT_FILE="tools/soundfonts/GeneralUser-GS.sf2"

case "$(uname -s)-$(uname -m)" in
  Darwin-arm64) PLATFORM="osx-arm64" ;;
  Darwin-x86_64) PLATFORM="osx-64" ;;
  Linux-x86_64) PLATFORM="linux-64" ;;
  Linux-aarch64) PLATFORM="linux-aarch64" ;;
  *) echo "暂不支持的平台：$(uname -s)-$(uname -m)" >&2; exit 1 ;;
esac

mkdir -p tools/bin tools/soundfonts
if [ ! -x tools/bin/micromamba ]; then
  echo "下载 micromamba（$PLATFORM）…"
  curl -fSL --retry 3 -o tools/bin/micromamba.part \
    "https://github.com/mamba-org/micromamba-releases/releases/latest/download/micromamba-$PLATFORM"
  chmod +x tools/bin/micromamba.part
  mv tools/bin/micromamba.part tools/bin/micromamba
fi

if [ ! -x tools/env/bin/fluidsynth ] || [ ! -x tools/env/bin/ffmpeg ]; then
  echo "从 $CONDA_CHANNEL 安装 FluidSynth 和 FFmpeg…"
  MAMBA_ROOT_PREFIX="$PROJECT_ROOT/tools/mamba" tools/bin/micromamba create -y \
    -p "$PROJECT_ROOT/tools/env" --override-channels -c "$CONDA_CHANNEL" fluidsynth ffmpeg
fi

if [ ! -f "$SOUNDFONT_FILE" ]; then
  echo "下载 GeneralUser GS 钢琴音源（约 31 MB）…"
  curl -fSL --retry 3 -o "$SOUNDFONT_FILE.part" "$SOUNDFONT_URL"
  mv "$SOUNDFONT_FILE.part" "$SOUNDFONT_FILE"
fi

[ -f .env ] || cp .env.example .env
fill_env() {
  local key="$1" value="$2"
  if ! grep -q "^$key=" .env; then
    echo "$key=$value" >> .env
  elif grep -q "^$key=$" .env; then
    sed -i.bak "s|^$key=$|$key=$value|" .env && rm -f .env.bak
  fi
}
fill_env FLUIDSYNTH_PATH tools/env/bin/fluidsynth
fill_env FFMPEG_PATH tools/env/bin/ffmpeg
fill_env SOUNDFONT_PATH "$SOUNDFONT_FILE"

echo "音频工具安装完成，运行 bash scripts/dev.sh env-check 检查。"
