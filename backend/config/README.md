# 配置目录

- `presets.json`：主题、情绪、风格的稳定 ID 与中文显示名称。数据和规则只按 ID 关联，修改显示名称不影响已有数据。
- `styles.json`：七种风格的速度范围、调式、旋律音区、和弦模板、节奏模板与默认音乐规划，以及每种情绪对调式、速度、力度、副歌升高幅度的调整。

和弦用调内级数表示：`1`～`7` 为调内三和弦，后缀 `:7` 为调内七和弦，`:M` 强制大三和弦。节奏模板中 `grid` 为每小节格子数（8＝八分音符，16＝十六分音符），`notesPerBar` 为旋律每小节音符数范围，`phraseEndBeats` 为句尾停顿与长音预算（拍），`accompaniment` 为伴奏织体。

修改后运行 `bash scripts/dev.sh check-presets` 与 `bash scripts/dev.sh test` 确认引用一致。
